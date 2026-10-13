#!/usr/bin/env python3
"""
Federated evaluation panel.

Each observer is one client. That is the real systems argument for federating
this problem, and it is a much better one than the usual privacy argument: PHY
and MAC measurements are local to a receiver and cannot be centralised cheaply,
and different observers genuinely see different geography, traffic density and
channel occupancy. The label skew is therefore a property of the deployment,
not something injected with a Dirichlet parameter.

Methods:
  fedavg     weighted average of client weights                    (baseline)
  fedprox    FedAvg plus a proximal term                           (stability)
  fednova    normalises for unequal local work                     (stability)
  fedlc      logit calibration, aimed straight at label skew
  fedproto   class prototypes shared alongside weights

Two robustness options, both off by default so every existing figure is
unchanged (each draws from its own generator, never the global RNG):
  --secure-agg   pairwise-masked secure aggregation (Bonawitz et al. 2017,
                 the masking layer): the server sees only the sum
  --dropout q    clients that were sampled fail to report, at random or, with
                 --dropout-mode persistent, concentrated on a fixed unreliable
                 subset, which is what intermittent connectivity looks like
                 when it follows geography

Protocol: at least five seeds, paired Wilcoxon across
seeds, and a strict client-wise train/validation/test split so no client
appears in more than one role. Three seeds cannot reach p < 0.05 under a
two-sided Wilcoxon, so a three-seed comparison cannot support a significance
claim whatever the numbers happen to be.
"""
import argparse
import copy
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from pooled_consensus import wilcoxon
from sklearn.metrics import f1_score, matthews_corrcoef
from sklearn.preprocessing import StandardScaler


class MLP(nn.Module):
    def __init__(self, d_in, n_classes, hidden=(64, 32)):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(d_in, hidden[0]), nn.ReLU(),
            nn.Linear(hidden[0], hidden[1]), nn.ReLU())
        self.head = nn.Linear(hidden[1], n_classes)

    def forward(self, x, return_embedding=False):
        z = self.body(x)
        out = self.head(z)
        return (out, z) if return_embedding else out


# Local SGD momentum. FedNova's normalisation depends on it, so it is named once.
MOMENTUM = 0.9


def flat(model):
    """Detached flat copy of the weights. For arithmetic, never for a loss."""
    return torch.cat([p.data.view(-1) for p in model.parameters()])


def prox_term(model, global_params):
    """Differentiable ||w - w_global||^2.

    This has to be built from the live parameters. Using the flat() copy above
    detaches it from the graph, the proximal term contributes no gradient, and
    FedProx silently becomes FedAvg. It did: both returned macro F1 0.2072
    to four decimals across two seeds before this was fixed. A panel reporting
    "FedProx is indistinguishable from FedAvg" on that basis would have been
    reporting a bug as a result.
    """
    return sum(((p - g) ** 2).sum() for p, g in zip(model.parameters(), global_params))


def load_flat(model, vec):
    i = 0
    for p in model.parameters():
        n = p.numel()
        p.data.copy_(vec[i:i + n].view_as(p))
        i += n


def local_train(model, global_vec, X, y, method, cfg, class_counts, global_proto):
    global_params = [p.detach().clone() for p in model.parameters()]
    """One client's local work. Returns (weights, n_steps, prototypes)."""
    opt = torch.optim.SGD(model.parameters(), lr=cfg["lr"], momentum=MOMENTUM)
    n = len(X)
    bs = cfg["batch_size"]
    steps = 0
    proto_sum = torch.zeros(cfg["n_classes"], cfg["embed_dim"])
    proto_cnt = torch.zeros(cfg["n_classes"])

    # FedLC: each class's logit is offset by tau * N_c^(-1/4), computed from
    # this client's own label counts. A class the client rarely sees gets a
    # larger offset, so the local model stops being able to win by predicting
    # its majority classes.
    if method == "fedlc":
        counts = class_counts.clamp(min=1).float()
        adjust = cfg["tau"] * counts.pow(-0.25)
    else:
        adjust = None

    for _ in range(cfg["local_epochs"]):
        perm = torch.randperm(n)
        for b in range(0, n, bs):
            idx = perm[b:b + bs]
            xb, yb = X[idx], y[idx]
            opt.zero_grad()
            out, emb = model(xb, return_embedding=True)

            logits = out - adjust if adjust is not None else out
            loss = F.cross_entropy(logits, yb)

            if method == "fedprox":
                loss = loss + cfg["mu"] / 2.0 * prox_term(model, global_params)

            if method == "fedproto" and global_proto is not None:
                # Pull local embeddings toward the global class prototype, so
                # clients that never see a class still place it consistently.
                tgt = global_proto[yb]
                mask = tgt.abs().sum(1) > 0
                if mask.any():
                    loss = loss + cfg["lam"] * F.mse_loss(emb[mask], tgt[mask])

            loss.backward()
            opt.step()
            steps += 1

            if method == "fedproto":
                with torch.no_grad():
                    for c in yb.unique():
                        m = yb == c
                        proto_sum[c] += emb[m].detach().sum(0)
                        proto_cnt[c] += m.sum()

    protos = None
    if method == "fedproto":
        # Sums and counts, not means, so the server can average each class over
        # only the clients that saw it (below).
        protos = (proto_sum, proto_cnt)
    return flat(model).clone(), steps, protos


# Secure aggregation, the pairwise-masking layer of Bonawitz et al. (CCS 2017).
# Each pair of clients sampled in a round agrees a seed (in a deployment, by
# key agreement; here derived from the round and the pair) and expands it to a
# mask over the ring Z_2^64. The lower-numbered client adds the mask and the
# higher subtracts it, so every mask cancels in the sum and the server learns
# the sum alone. Arithmetic is modular on integers: a float mask cancels only
# approximately and leaks the update's magnitude. The update is n_i w_i,
# quantised at SECAGG_SCALE; the counts n_i are public, which FedAvg's own
# weighting already requires. Honest-but-curious server, no collusion.
SECAGG_SCALE = float(2 ** 30)
SECAGG_STATS = {}


def _pair_mask(seed, rnd, i, j, d):
    rng = np.random.default_rng([seed, rnd, min(i, j), max(i, j), 0x5ec])
    return rng.integers(0, np.iinfo(np.uint64).max, size=d, dtype=np.uint64,
                        endpoint=True)


def secure_sum(seed, rnd, sel, alive, vectors, recover=True):
    """Masked sum of vectors[k] (float64 numpy) over the clients sel[k] with
    alive[k] True. Masks are agreed among every sampled client before local
    training, so a client that drops leaves its masks uncancelled in the
    survivors' messages. With recover, each survivor reveals the seed it shared
    with each dropped peer and the server removes those masks, which is the
    recovery step of the protocol; without it the sum is wrong, which the
    --no-recover arm exists to show."""
    d = vectors[0].shape[0]
    total = np.zeros(d, dtype=np.uint64)
    masked_first = None
    reveals = 0
    for k, ci in enumerate(sel):
        if not alive[k]:
            continue
        q = np.round(vectors[k] * SECAGG_SCALE).astype(np.int64).view(np.uint64)
        msg = q.copy()
        for l, cj in enumerate(sel):
            if l == k:
                continue
            m = _pair_mask(seed, rnd, int(ci), int(cj), d)
            msg = msg + m if ci < cj else msg - m
        if masked_first is None:
            masked_first = (msg.view(np.int64).astype(np.float64), vectors[k])
        total = total + msg
    if recover:
        for k, ci in enumerate(sel):
            if not alive[k]:
                continue
            for l, cj in enumerate(sel):
                if alive[l]:
                    continue
                reveals += 1
                m = _pair_mask(seed, rnd, int(ci), int(cj), d)
                total = total - m if ci < cj else total + m
    out = total.view(np.int64).astype(np.float64) / SECAGG_SCALE
    return out, masked_first, reveals


def server_step(cfg, state, prev, avg):
    """Server optimiser applied to the aggregate (Reddi et al., ICLR 2021).

    The round's aggregate is read as a pseudo-gradient, prev - avg, and the
    server steps along it with momentum (FedAvgM) or with Adam's per-weight
    scaling (FedAdam, no bias correction, as in the paper). FedAvgM with server
    learning rate 1 and momentum 0 is plain FedAvg, which is the check that the
    option leaves the aggregate alone. It acts on whatever the server receives,
    so it composes with secure aggregation (the server still gets the sum) and
    with DP (the noise is added before this step)."""
    d = prev - avg
    lr = cfg.get("server_lr", 1.0)
    if cfg["server_opt"] == "avgm":
        state["m"] = cfg.get("server_beta1", 0.9) * state.get("m", 0.0) + d
        return prev - lr * state["m"]
    if cfg["server_opt"] == "adam":
        b1, b2 = cfg.get("server_beta1", 0.9), cfg.get("server_beta2", 0.99)
        state["m"] = b1 * state.get("m", 0.0) + (1 - b1) * d
        state["v"] = b2 * state.get("v", 0.0) + (1 - b2) * d * d
        return prev - lr * state["m"] / (state["v"].sqrt() + cfg.get("server_tau", 1e-3))
    raise SystemExit(f"unknown server optimiser {cfg['server_opt']!r}")


def evaluate(cfg, gvec, data):
    """(macro F1, MCC) of the weights gvec on data = (X, y). Building the MLP
    draws an initialisation from torch's global generator, which a callback
    would then shift for every later round; the fork keeps scoring from
    changing the run it scores."""
    with torch.random.fork_rng(devices=[]):
        m = MLP(cfg["d_in"], cfg["n_classes"])
    load_flat(m, gvec)
    m.eval()
    with torch.no_grad():
        pred = m(data[0]).argmax(1).numpy()
    truth = data[1].numpy()
    return f1_score(truth, pred, average="macro"), matthews_corrcoef(truth, pred)


def run_method(method, clients, test, cfg, seed, detail=False, init=None,
               callback=None):
    torch.manual_seed(seed)
    np.random.seed(seed)
    g = MLP(cfg["d_in"], cfg["n_classes"])
    # init: start from given weights (a model trained elsewhere, for
    # adaptation) instead of a fresh initialisation. None keeps every existing
    # run identical, since the fresh model above is still drawn either way.
    gvec = flat(g).clone() if init is None else init.clone()
    global_proto = None
    if cfg.get("server_opt") and method == "fednova":
        raise SystemExit("a server optimiser is implemented for the "
                         "weighted-average methods only")
    sstate = {}

    # callback(round, weights) after every round, for learning curves. It only
    # reads, so a run with a callback is the run without one; and because the
    # client draw comes from one stream in round order, round r of a long run
    # is round r of a short one, so one 200 round run gives the 20, 50 and 100
    # round models too.
    for rnd in range(cfg["rounds"]):
        gprev = gvec
        sel = np.random.choice(len(clients),
                               size=max(1, int(cfg["participation"] * len(clients))),
                               replace=False)
        updates, weights, taus, protos = [], [], [], []
        alive = np.ones(len(sel), dtype=bool)
        if cfg.get("dropout"):
            # Its own generator, so the global stream that chose `sel` and
            # every later round is untouched.
            drng = np.random.default_rng([seed, rnd, 0xd0])
            if cfg.get("dropout_mode") == "persistent":
                # A fixed share of clients is unreliable for the whole run and
                # fails 80 percent of the rounds it is sampled in; the rest
                # never fail. Chosen once per seed.
                urng = np.random.default_rng([seed, 0x0b])
                bad = set(urng.choice(len(clients),
                                      int(round(cfg["dropout"] * len(clients))),
                                      replace=False).tolist())
                alive = np.array([not (int(ci) in bad and drng.random() < 0.8)
                                  for ci in sel])
            else:
                alive = drng.random(len(sel)) >= cfg["dropout"]
            SECAGG_STATS.setdefault("dropped", []).append(int((~alive).sum()))
        if not alive.any():
            SECAGG_STATS.setdefault("empty_rounds", []).append(rnd)
            if callback is not None:
                callback(rnd + 1, gvec)
            continue
        for k, ci in enumerate(sel):
            if not alive[k] and not cfg.get("secure_agg"):
                continue
            if not alive[k]:
                # Placeholder so positions in `sel` line up for the mask
                # bookkeeping; a dropped client sends nothing.
                updates.append(None)
                weights.append(0)
                taus.append(0)
                continue
            X, y, counts = clients[ci]
            m = MLP(cfg["d_in"], cfg["n_classes"])
            load_flat(m, gvec)
            w, steps, pr = local_train(m, gvec, X, y, method, cfg, counts, global_proto)
            updates.append(w)
            weights.append(len(X))
            taus.append(steps)
            if pr is not None:
                protos.append(pr)

        if cfg.get("secure_agg"):
            if cfg.get("dp_clip") or method == "fednova":
                raise SystemExit("secure aggregation is implemented for the "
                                 "weighted-average methods only")
            vecs = [None if u is None else u.double().numpy() * n
                    for u, n in zip(updates, weights)]
            d = next(v for v in vecs if v is not None).shape[0]
            vecs = [np.zeros(d) if v is None else v for v in vecs]
            s_sum, first, reveals = secure_sum(seed, rnd, sel, alive, vecs,
                                               recover=cfg.get("recover", True))
            n_tot = float(sum(weights))
            new = s_sum / n_tot
            plain = sum(v for v, a in zip(vecs, alive) if a) / n_tot
            st = SECAGG_STATS
            st.setdefault("max_dev", []).append(float(np.abs(new - plain).max()))
            mv, tv = first
            cos = float(mv @ tv / (np.linalg.norm(mv) * np.linalg.norm(tv) + 1e-300))
            st.setdefault("cos", []).append(abs(cos))
            st.setdefault("reveals", []).append(reveals)
            st["d"] = d
            gvec = torch.tensor(new, dtype=torch.float32)
            # FedProto's prototypes, averaged below, are NOT masked: they travel
            # in the clear, which is stated wherever this option is reported.
            p = None  # skips the plain aggregation branches below
        else:
            p = torch.tensor(weights, dtype=torch.float)
            p = p / p.sum()

        if p is None:
            pass
        elif cfg.get("dp_clip"):
            # DP-FedAvg. Clip each client's UPDATE, not its weights, average
            # with uniform weights so the sensitivity of the release is C/|sel|
            # rather than depending on how much data a client happens to hold,
            # then add Gaussian noise to the average.
            #
            # Uniform weighting is not a detail: with data-proportional weights
            # the largest client's influence sets the sensitivity, and on this
            # partition client sizes vary by a factor of five, so the noise
            # needed would be five times larger for the same guarantee.
            C = cfg["dp_clip"]
            deltas = torch.stack([
                (gvec - u) * min(1.0, C / float((gvec - u).norm() + 1e-12))
                for u in updates])
            agg = deltas.mean(0)
            if cfg.get("dp_noise", 0.0) > 0:
                sigma = cfg["dp_noise"] * C / len(sel)
                agg = agg + torch.randn_like(agg) * sigma
            gvec = gvec - agg
        elif method == "fednova":
            # Normalise each client's update by the work it did, then rescale
            # by the effective number of steps. Clients with more data would
            # otherwise drag the global model toward their own optimum simply
            # by taking more steps.
            #
            # The work is not the step count. Local training uses SGD with
            # momentum rho, its buffer fresh each round, so a gradient taken at
            # step k is applied again at every later step, and after tau steps
            # the update is a_i = [tau - rho (1 - rho^tau) / (1 - rho)] / (1 - rho)
            # gradients' worth (Wang et al. 2020, section 5). Dividing by tau
            # instead gave a client taking sixty steps about six times too much
            # weight against one taking two, the imbalance FedNova removes.
            rho = MOMENTUM
            tau = torch.tensor(taus, dtype=torch.float)
            work = (tau - rho * (1 - rho ** tau) / (1 - rho)) / (1 - rho)
            d = torch.stack([(gvec - u) / w for u, w in zip(updates, work)])
            gvec = gvec - (p * work).sum() * (p[:, None] * d).sum(0)
        else:
            gvec = (p[:, None] * torch.stack(updates)).sum(0)

        if cfg.get("server_opt"):
            gvec = server_step(cfg, sstate, gprev, gvec)

        if method == "fedproto" and protos:
            # FedProto averages each class prototype over the clients that hold
            # that class. Averaging every client's vector, with zeros for classes
            # a client never saw, shrank a class seen by k of m clients toward the
            # origin by about k/m, and on this partition most clients miss at
            # least one class, so the damage fell on the rare classes the method
            # exists for. Weighted by how many embeddings each client contributed.
            s = torch.stack([pr[0] for pr in protos]).sum(0)
            c = torch.stack([pr[1] for pr in protos]).sum(0)
            global_proto = torch.where(c[:, None] > 0, s / c[:, None].clamp(min=1),
                                       torch.zeros_like(s))

        if callback is not None:
            callback(rnd + 1, gvec)

    load_flat(g, gvec)
    g.eval()
    with torch.no_grad():
        pred = g(test[0]).argmax(1).numpy()
    # Both metrics come back from one fit. MCC is the aggregate the proposal
    # names primary; macro F1 is what every comparison in this file is anchored
    # on and what hyperparameter selection uses, so that adding MCC reports a
    # second number without moving any existing one.
    truth = test[1].numpy()
    f1 = f1_score(truth, pred, average="macro")
    mcc = matthews_corrcoef(truth, pred)
    if not detail:
        return f1, mcc
    # A scalar hides which failure happened. A run whose weights blew up, a run
    # that collapsed onto two classes and a run that is merely weak all score
    # low and want different fixes, so report what the model actually did.
    # Off by default: every existing caller unpacks exactly two values.
    return f1, mcc, {
        "gvec": gvec,
        "finite": bool(torch.isfinite(gvec).all().item()),
        "weight_norm": float(gvec.norm().item()),
        "predicted_classes": int(len(np.unique(pred))),
        "per_class_f1": [round(float(v), 3) for v in
                         f1_score(truth, pred, average=None,
                                  labels=list(range(cfg["n_classes"])),
                                  zero_division=0)],
    }


def run_central(clients, cfg, seed, epochs, callback=None):
    """The ceiling: the same MLP and the same local optimiser (SGD, momentum,
    learning rate, batch size), trained on the union of the training clients'
    rows as if they had been pooled at one server. callback(epoch, weights)
    after every epoch, so one run gives both the matched-exposure model and the
    early-stopped one. The momentum buffer persists across epochs, as in any
    central training run."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    X = torch.cat([c[0] for c in clients])
    y = torch.cat([c[1] for c in clients])
    m = MLP(cfg["d_in"], cfg["n_classes"])
    opt = torch.optim.SGD(m.parameters(), lr=cfg["lr"], momentum=MOMENTUM)
    n, bs = len(X), cfg["batch_size"]
    for ep in range(epochs):
        perm = torch.randperm(n)
        for b in range(0, n, bs):
            idx = perm[b:b + bs]
            opt.zero_grad()
            F.cross_entropy(m(X[idx]), y[idx]).backward()
            opt.step()
        if callback is not None and callback(ep + 1, flat(m).clone()) is False:
            break
    return flat(m).clone()


CENTRAL_EPOCHS = 200


def central_arms(clients, val, test, cfg, seed, epochs=CENTRAL_EPOCHS):
    """Two ceilings from one central run. 'matched' stops at the row exposure a
    federated run gets: each client is sampled with probability about
    participation per round and does local_epochs passes, so a row is seen
    about rounds * local_epochs * participation times. 'converged' is the
    epoch with the best validation macro F1 within a fixed budget of `epochs`,
    the same definition fed_sweep.py uses. Selection reads validation only;
    test is recorded at every epoch and read at the epoch validation picked."""
    matched = max(1, int(round(cfg["rounds"] * cfg["local_epochs"]
                               * cfg["participation"])))
    hist = {}
    best = {"ep": 0, "f1": -1.0}

    def cb(ep, w):
        v = evaluate(cfg, w, val)
        hist[ep] = (v, evaluate(cfg, w, test))
        if v[0] > best["f1"]:
            best.update(ep=ep, f1=v[0])

    run_central(clients, cfg, seed, max(epochs, matched), callback=cb)
    return {"matched": hist[matched][1], "matched_val": hist[matched][0],
            "matched_epochs": matched,
            "converged": hist[best["ep"]][1], "converged_val": hist[best["ep"]][0],
            "converged_epochs": best["ep"], "epochs_run": max(hist)}


def dp_epsilon(z, rounds, delta=1e-5):
    """(epsilon, delta) for `rounds` rounds of the DP-FedAvg step above, by
    Renyi differential privacy, with no subsampling amplification credited.

    The sensitivity has to match the sampler, and an earlier version of this
    function did not. Each round samples a FIXED number of clients without
    replacement and adds Gaussian noise of standard deviation z C to the sum of
    their clipped updates (z C / m on the mean). Under that sampler, adding or
    removing one client can do more than add or remove one term: it can change
    which m clients are drawn, and the coupling that bounds this swaps one
    sampled client for another. The sum then moves by the difference of two
    clipped updates, up to 2C. A Gaussian mechanism of sensitivity 2C and noise
    z C is (alpha, 2 alpha / z^2)-RDP per round, four times what the add/remove
    form alpha / (2 z^2) charges, and that form is only valid under Poisson
    sampling with a fixed denominator. So

        eps = rounds * 2 alpha / z^2 + log(1/delta) / (alpha - 1),

    minimised over alpha. It is an upper bound for this sampler. Crediting
    amplification by fixed-size sampling does not rescue the old figures either:
    for the worst adjacent pair the sampled mechanism at this sampling rate is
    still above alpha / (2 z^2) at the orders that set the minimum. So no
    smaller number is claimed here.
    """
    alphas = np.arange(1.01, 256.0, 0.01)
    eps = rounds * 2.0 * alphas / z ** 2 + np.log(1.0 / delta) / (alphas - 1.0)
    return float(eps.min())


def build_clients(df, feats, observer_col="key_rxNodeId", min_rows=200):
    y_all = df.label_attackId.astype("category")
    classes = list(y_all.cat.categories)
    codes = y_all.cat.codes.values

    obs = df[observer_col].values
    uniq = pd.unique(obs)
    rng = np.random.RandomState(0)
    rng.shuffle(uniq)
    n = len(uniq)
    # Strict client-wise split: an observer is a training client, a validation
    # client or a test client, never more than one.
    tr_obs = set(uniq[:int(0.7 * n)])
    va_obs = set(uniq[int(0.7 * n):int(0.85 * n)])
    te_obs = set(uniq[int(0.85 * n):])

    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values.astype(np.float32)
    scaler = StandardScaler().fit(X[np.isin(obs, list(tr_obs))])
    X = scaler.transform(X).astype(np.float32)

    clients = []
    for o in uniq:
        if o not in tr_obs:
            continue
        m = obs == o
        if m.sum() < min_rows:
            continue
        xi = torch.tensor(X[m])
        yi = torch.tensor(codes[m], dtype=torch.long)
        counts = torch.bincount(yi, minlength=len(classes))
        clients.append((xi, yi, counts))

    def pack(obs_set):
        m = np.isin(obs, list(obs_set))
        return (torch.tensor(X[m]), torch.tensor(codes[m], dtype=torch.long))

    return clients, pack(va_obs), pack(te_obs), len(classes)


def build_clients_tx(df, feats, splits, observer_col="key_rxNodeId", min_rows=200,
                     return_ids=False):
    """Held-out TRANSMITTERS, the protocol every other number in the report
    uses. build_clients above holds out observers, but a transmitter is heard
    by a median of eight regions, so all of its test rows came from vehicles
    the training clients had also heard: it measures transfer to a new region,
    not detection of a new vehicle.

    Here every observer is a client and trains on the rows of training
    transmitters only. Validation and test are the rows of validation and test
    transmitters, heard at any observer. That is the deployment question: the
    roadside infrastructure is fixed and trains together, and new vehicles
    arrive. `splits` is the frozen release partition (release_splits.csv), one
    row per transmitter and claimed identity, joined on seed and transmitter."""
    y_all = df.label_attackId.astype("category")
    classes = list(y_all.cat.categories)
    codes = y_all.cat.codes.values

    s = splits.drop_duplicates(["key_seed", "label_txNodeId"])
    if (splits.groupby(["key_seed", "label_txNodeId"]).split.nunique() > 1).any():
        raise SystemExit("a transmitter sits in more than one split")
    part = df[["key_seed", "label_txNodeId"]].merge(
        s[["key_seed", "label_txNodeId", "split"]], how="left",
        on=["key_seed", "label_txNodeId"]).split.values
    if pd.isna(part).any():
        raise SystemExit(f"{int(pd.isna(part).sum())} rows have no split; the "
                         "split file does not cover this table")

    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values.astype(np.float32)
    tr = part == "train"
    scaler = StandardScaler().fit(X[tr])
    X = scaler.transform(X).astype(np.float32)

    obs = df[observer_col].values
    clients, ids = [], []
    for o in pd.unique(obs):
        m = tr & (obs == o)
        if m.sum() < min_rows:
            continue
        xi = torch.tensor(X[m])
        yi = torch.tensor(codes[m], dtype=torch.long)
        clients.append((xi, yi, torch.bincount(yi, minlength=len(classes))))
        ids.append(o)

    def pack(name):
        m = part == name
        return (torch.tensor(X[m]), torch.tensor(codes[m], dtype=torch.long))

    if return_ids:
        return clients, pack("validation"), pack("test"), len(classes), ids
    return clients, pack("validation"), pack("test"), len(classes)


def road_ring(ids, extra_links=2, graph_seed=0x9a):
    """Neighbour sets for decentralised averaging. Region clients are named
    seed<k>_r<i>; sorted by seed then region they are consecutive roadside
    units along each simulated road, and the ring joins each road's last unit
    to the next road's first, as one long road would. A line or plain ring of
    96 nodes mixes too slowly for 200 rounds to say anything about
    decentralisation, so each node also gets extra_links random links, as a
    backhaul mesh would give. The graph is infrastructure, so it is drawn once
    and is the same for every seed."""
    def key(o):
        s, r = str(o).split("_r")
        return int(s.replace("seed", "")), int(r)
    order = sorted(range(len(ids)), key=lambda k: key(ids[k]))
    n = len(ids)
    adj = [set() for _ in range(n)]
    for p in range(n):
        i, j = order[p], order[(p + 1) % n]
        adj[i].add(j)
        adj[j].add(i)
    rng = np.random.default_rng(graph_seed)
    for i in range(n):
        for _ in range(extra_links):
            j = int(rng.integers(n))
            if j != i:
                adj[i].add(j)
                adj[j].add(i)
    return adj


def metropolis(adj, alive):
    """Metropolis-Hastings mixing weights over the live nodes: symmetric and
    doubly stochastic, so repeated averaging converges to the plain mean of
    the live nodes' models. A dead node keeps an identity row and is ignored."""
    n = len(adj)
    deg = [len([j for j in adj[i] if alive[j]]) if alive[i] else 0 for i in range(n)]
    W = np.eye(n)
    for i in range(n):
        if not alive[i]:
            continue
        W[i, i] = 1.0
        for j in adj[i]:
            if alive[j]:
                W[i, j] = 1.0 / (1 + max(deg[i], deg[j]))
                W[i, i] -= W[i, j]
    return torch.tensor(W, dtype=torch.float32)


def run_decentralised(clients, test, cfg, seed, adj, fail_frac=0.0, fail_round=None,
                      gossip_steps=1):
    """Federated averaging with no server. Every node keeps its own model. Each
    round the same share of nodes as FedAvg samples (participation, drawn from
    the same stream, so exposure matches) trains locally from its own model,
    then every live node replaces its model with a Metropolis-weighted average
    of its own and its neighbours' (one gossip step). Weights are uniform per
    neighbour, not by row count as FedAvg's are.

    fail_frac of the nodes stop permanently at fail_round: they neither train
    nor send again, and the survivors re-weight over the links that remain.

    Returns per-node macro F1 on test (mean and worst over live nodes), the
    macro F1 of the live nodes' average, and the consensus distance, the mean
    of |x_i - xbar| / |xbar|, which is zero when every node holds one model."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    g = MLP(cfg["d_in"], cfg["n_classes"])
    x0 = flat(g).clone()
    n = len(clients)
    models = [x0.clone() for _ in range(n)]
    alive = np.ones(n, dtype=bool)
    W = metropolis(adj, alive)
    for rnd in range(cfg["rounds"]):
        if fail_round is not None and fail_frac > 0 and rnd == fail_round:
            frng = np.random.default_rng([seed, 0xfa])
            alive[frng.choice(n, int(round(fail_frac * n)), replace=False)] = False
            W = metropolis(adj, alive)
        sel = np.random.choice(n, size=max(1, int(cfg["participation"] * n)),
                               replace=False)
        for ci in sel:
            if not alive[ci]:
                continue
            X, y, counts = clients[ci]
            m = MLP(cfg["d_in"], cfg["n_classes"])
            load_flat(m, models[ci])
            w, _, _ = local_train(m, models[ci], X, y, "fedavg", cfg, counts, None)
            models[ci] = w
        S = torch.stack(models)
        for _ in range(gossip_steps):
            S = W @ S
        models = list(S)

    live = [i for i in range(n) if alive[i]]
    node = [evaluate(cfg, models[i], test)[0] for i in live]
    xbar = torch.stack([models[i] for i in live]).mean(0)
    cons = float(np.mean([float((models[i] - xbar).norm() / xbar.norm()) for i in live]))
    # Components of the surviving graph: a split network trains separately.
    seen, comps = set(), 0
    for s in live:
        if s in seen:
            continue
        comps += 1
        stack = [s]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(j for j in adj[u] if alive[j] and j not in seen)
    return dict(mean=float(np.mean(node)), worst=float(np.min(node)),
                avg_model=evaluate(cfg, xbar, test)[0], consensus=cons,
                alive=len(live), components=comps)


def load_panel_data(path, sample=200000, observer_role=None, restrict_first=False):
    """The panel's table, cleaned, restricted to an observer role and sampled.
    The original order samples first and restricts second, which on roadside
    unit clients kept 24,552 of 199,890 clean rows; restrict_first fixes that
    and is off by default so every logged panel reproduces."""
    df = pd.read_pickle(path) if path.endswith(".pkl") else pd.read_csv(path)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]

    def restrict(df):
        if observer_role and "key_observer_role" in df.columns:
            before = df.key_rxNodeId.nunique()
            df = df[df.key_observer_role == observer_role]
            print(f"restricted to {observer_role} observers: "
                  f"{df.key_rxNodeId.nunique()} of {before} clients, {len(df)} rows\n")
            if df.empty:
                raise SystemExit(f"no observers with role {observer_role!r}")
        return df

    if restrict_first:
        df = restrict(df)
    if sample and len(df) > sample:
        df = df.sample(n=sample, random_state=0)
    if not restrict_first:
        df = restrict(df)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=25)
    ap.add_argument("--local-epochs", type=int, default=2)
    ap.add_argument("--methods", default="fedavg,fedprox,fednova,fedlc,fedproto")
    ap.add_argument("--sample", type=int, default=200000)
    ap.add_argument("--dp-clip", type=float, default=None,
                    help="clip each client update to this L2 norm, enabling "
                         "DP-FedAvg with uniform client weights")
    ap.add_argument("--dp-noise", type=float, nargs="+", default=None,
                    help="noise multiplier(s) z to sweep. 0 measures the cost "
                         "of clipping alone, which is worth separating from "
                         "the cost of the noise")
    ap.add_argument("--drop-consensus", action="store_true",
                    help="pool the features but withhold the cross-receiver "
                         "consensus block, to separate feature averaging from "
                         "the consensus statistics")
    ap.add_argument("--observer-col", default="key_rxNodeId",
                    help="column that identifies a client. Use key_region for "
                         "the pooled corpus, where a client is an RSU plus the "
                         "vehicles in its region rather than a lone receiver")
    ap.add_argument("--observer-role", default=None,
                    help="restrict clients to this observer role, "
                         "normally 'rsu' for the edge-based framing")
    ap.add_argument("--mu", type=float, default=0.01)
    ap.add_argument("--tau", type=float, default=1.0)
    ap.add_argument("--tau-grid", type=float, nargs="+",
                    default=[0.5, 1.0, 2.0, 4.0, 8.0],
                    help="FedLC's tuning grid. The default is the published one; "
                    "widen it when a panel chooses the top edge")
    ap.add_argument("--lam", type=float, default=0.1)
    ap.add_argument("--secure-agg", action="store_true",
                    help="pairwise-masked secure aggregation, compared against "
                         "the same seeds without it")
    ap.add_argument("--dropout", type=float, default=None,
                    help="share of sampled clients that fail to report, "
                         "compared against the same seeds with none")
    ap.add_argument("--dropout-mode", choices=["random", "persistent"],
                    default="random")
    ap.add_argument("--no-recover", action="store_true",
                    help="with --secure-agg and --dropout, skip the mask "
                         "recovery step, to show what it is for")
    ap.add_argument("--tune", action="store_true",
                    help="select each method's hyperparameter on the "
                         "validation clients before the seeded runs")
    ap.add_argument("--split-file", default=None,
                    help="release_splits.csv: hold out TRANSMITTERS (every "
                         "observer trains, on training transmitters only). "
                         "Without it, observers are held out, the original "
                         "protocol")
    ap.add_argument("--restrict-first", action="store_true",
                    help="apply --observer-role before --sample rather than after")
    ap.add_argument("--server-opt", choices=["avgm", "adam"], default=None,
                    help="server optimiser on the aggregate; off is plain averaging")
    ap.add_argument("--server-lr", type=float, default=1.0)
    ap.add_argument("--server-beta1", type=float, default=0.9)
    ap.add_argument("--server-beta2", type=float, default=0.99)
    ap.add_argument("--server-tau", type=float, default=1e-3)
    ap.add_argument("--decentral", action="store_true",
                    help="no server: decentralised averaging between neighbouring "
                         "clients (needs --split-file and region clients), "
                         "compared with FedAvg on the same seeds")
    ap.add_argument("--extra-links", type=int, default=2,
                    help="random links per node added to the road ring")
    ap.add_argument("--fail-frac", type=float, default=0.1,
                    help="share of nodes that fail permanently in the failure arm")
    ap.add_argument("--fail-round", type=int, default=100)
    ap.add_argument("--gossip-steps", type=int, default=1,
                    help="averaging steps with the neighbours per round; more "
                         "steps bring the units closer to one model at that many "
                         "times the messages")
    a = ap.parse_args()

    df = load_panel_data(a.features, a.sample, a.observer_role, a.restrict_first)
    # pool_ is the cross-receiver consensus block. It exists only in a pooled
    # corpus and it is the part of the feature set a lone receiver cannot
    # compute, so a panel run without it is measuring feature averaging rather
    # than the architecture.
    prefixes = ("app_", "phy_") if a.drop_consensus else ("app_", "phy_", "pool_")
    feats = [c for c in df.columns if c.startswith(prefixes)]

    ids = None
    if a.split_file:
        clients, val, test, n_classes, ids = build_clients_tx(
            df, feats, pd.read_csv(a.split_file), observer_col=a.observer_col,
            return_ids=True)
        print(f"held-out transmitters ({a.split_file}); every observer with "
              f"at least 200 training rows is a client, "
              f"{sum(len(c[0]) for c in clients)} training rows")
    else:
        clients, val, test, n_classes = build_clients(df, feats,
                                                      observer_col=a.observer_col)
    cfg = dict(d_in=len(feats), n_classes=n_classes, embed_dim=32, lr=0.05,
               batch_size=128, local_epochs=a.local_epochs, rounds=a.rounds,
               participation=0.5, mu=a.mu, tau=a.tau, lam=a.lam)
    if a.server_opt:
        cfg.update(server_opt=a.server_opt, server_lr=a.server_lr,
                   server_beta1=a.server_beta1, server_beta2=a.server_beta2,
                   server_tau=a.server_tau)
        print(f"server optimiser {a.server_opt}: lr {a.server_lr}, beta1 "
              f"{a.server_beta1}, beta2 {a.server_beta2}, tau {a.server_tau}")

    print(f"{len(clients)} training clients, {len(val[0])} validation rows, "
          f"{len(test[0])} test rows, {len(feats)} features, {n_classes} classes, "
          f"{a.seeds} seeds\n")

    # Hyperparameters are chosen on VALIDATION clients and then frozen. Tuning
    # each method on the test set and reporting the best is how a panel ends up
    # comparing tuning effort rather than methods. Report 06 is explicit about
    # this and it costs almost nothing to do properly.
    #
    # The grids are wide on purpose. The first ones stopped at mu 0.1 and tau 2,
    # and every panel chose a value on the edge, so each tuned figure was a lower
    # bound on what the method could do. A choice on an edge is now printed as
    # such rather than read as an optimum.
    grids = {"fedprox": ("mu", [0.0001, 0.001, 0.01, 0.1, 1.0]),
             "fedlc": ("tau", list(a.tau_grid)),
             "fedproto": ("lam", [0.01, 0.1, 1.0, 10.0])}
    chosen = {}
    if a.tune:
        for method, (name, values) in grids.items():
            if method not in a.methods.split(","):
                continue
            # Selection stays on macro F1. Selecting on MCC would move the
            # chosen hyperparameters and therefore every federated number in
            # RESULTS.md, which is a results change dressed as a metric
            # addition. Which aggregate is primary is decided when the paper is
            # written, with both in hand.
            best, best_v = None, -1.0
            for v in values:
                c = dict(cfg, **{name: v})
                score, _ = run_method(method, clients, val, c, seed=1000)
                if score > best_v:
                    best, best_v = v, score
            chosen[method] = (name, best)
            edge = best in (values[0], values[-1])
            print(f"tuned {method}: {name} = {best} (validation macro F1 {best_v:.4f})"
                  + ("  AT THE GRID EDGE, so the optimum may lie beyond it"
                     if edge else ""))
        print()

    if a.decentral:
        if ids is None:
            raise SystemExit("--decentral needs --split-file (held-out transmitters)")
        decentral(a, clients, test, cfg, ids)
        return

    if a.secure_agg or a.dropout is not None:
        robustness(a, clients, test, cfg)
        return

    if a.dp_clip:
        # Privacy-utility sweep. Each row is one noise multiplier z; z = 0 is
        # clipping with no noise, which separates the cost of bounding a
        # client's influence from the cost of hiding it.
        print(f"DP-FedAvg, update clipped to L2 norm {a.dp_clip}, uniform "
              f"client weights, {len(clients)} clients, "
              f"{int(cfg['participation'] * len(clients))} sampled per round\n")
        print(f"{'z':>6s} {'macro F1':>18s} {'vs no DP':>9s} {'epsilon':>10s}"
              f" {'MCC multiclass':>18s}")
        base = None
        for z in [None] + list(a.dp_noise or [0.0]):
            c = dict(cfg)
            if z is not None:
                c["dp_clip"], c["dp_noise"] = a.dp_clip, z
            both = [run_method("fedavg", clients, test, c, seed=s)
                    for s in range(a.seeds)]
            scores = np.array([b[0] for b in both])
            mcc = np.array([b[1] for b in both])
            if z is None:
                base = scores.mean()
                print(f"{'off':>6s} {scores.mean():.4f} +/- {scores.std():.4f}"
                      f" {'':>9s} {'':>10s} {mcc.mean():.4f} +/- {mcc.std():.4f}")
                continue
            eps = dp_epsilon(z, a.rounds) if z > 0 else float("inf")
            eps_s = f"{eps:10.1f}" if np.isfinite(eps) else f"{'no noise':>10s}"
            print(f"{z:6.2f} {scores.mean():.4f} +/- {scores.std():.4f} "
                  f"{scores.mean() - base:+9.4f} {eps_s} "
                  f"{mcc.mean():.4f} +/- {mcc.std():.4f}")
        print("\nEpsilon is an upper bound for this sampler: Renyi composition\n"
              "of one Gaussian mechanism per round at delta = 1e-5, sensitivity 2C\n"
              "because a fixed number of clients is sampled without replacement,\n"
              "so one client can displace another. No subsampling amplification\n"
              "is credited. The clipping norm, the noise multiplier, the round\n"
              "count and the sampling rate are all stated so it can be recomputed.")
        return

    results, results_mcc = {}, {}
    for method in a.methods.split(","):
        if method == "central":
            # The ceiling, on the same clients' training rows and the same
            # validation and test rows. Two rows: at the federated arms' row
            # exposure, and early-stopped on validation.
            arms = [central_arms(clients, val, test, cfg, s) for s in range(a.seeds)]
            for key, label in (("matched", "central_matched"),
                               ("converged", "central_conv")):
                f1s = [r[key][0] for r in arms]
                mccs = [r[key][1] for r in arms]
                results[label], results_mcc[label] = f1s, mccs
                ep = [r[f"{key}_epochs"] for r in arms]
                print(f"{label:15s} macro F1 {np.mean(f1s):.4f} +/- {np.std(f1s):.4f}   "
                      f"{[round(s, 4) for s in f1s]}   "
                      f"MCC multiclass {np.mean(mccs):.4f} +/- {np.std(mccs):.4f}   "
                      f"epochs {ep}")
            continue
        c = cfg
        if method in chosen:
            name, v = chosen[method]
            c = dict(cfg, **{name: v})
        both = [run_method(method, clients, test, c, s) for s in range(a.seeds)]
        scores = [b[0] for b in both]
        mcc = [b[1] for b in both]
        results[method] = scores
        results_mcc[method] = mcc
        print(f"{method:9s} macro F1 {np.mean(scores):.4f} +/- {np.std(scores):.4f}   "
              f"{[round(s, 4) for s in scores]}   "
              f"MCC multiclass {np.mean(mcc):.4f} +/- {np.std(mcc):.4f}")

    base = results.get("fedavg")
    if base and len(base) >= 5:
        print("\npaired Wilcoxon against FedAvg (n=%d seeds):" % len(base))
        for m, s in results.items():
            if m == "fedavg":
                continue
            try:
                pval = wilcoxon(s, base)
                delta = np.mean(s) - np.mean(base)
                print(f"  {m:9s} delta {delta:+.4f}  p = {pval:.4f}"
                      f"{'  significant' if pval < 0.05 else ''}")
            except ValueError as e:
                print(f"  {m:9s} {e}")

        # The same paired test on MCC, reported separately rather than folded
        # into the line above, so that a method which wins on one aggregate and
        # not the other is visible instead of averaged away.
        mbase = results_mcc.get("fedavg")
        print("\npaired Wilcoxon on MCC against FedAvg (n=%d seeds):" % len(mbase))
        for m, s in results_mcc.items():
            if m == "fedavg":
                continue
            try:
                pval = wilcoxon(s, mbase)
                delta = np.mean(s) - np.mean(mbase)
                print(f"  {m:9s} MCC delta {delta:+.4f}  p = {pval:.4f}"
                      f"{'  significant' if pval < 0.05 else ''}")
            except ValueError as e:
                print(f"  {m:9s} {e}")

    ceil = results.get("central_conv")
    if ceil:
        # Federated as a share of the central ceiling, per seed (the same seed
        # draws the central model's initialisation), then summarised.
        print("\nshare of the central ceiling (early-stopped), per seed:")
        for m, s in results.items():
            if m.startswith("central"):
                continue
            r = np.array(s) / np.array(ceil)
            rm = np.array(results_mcc[m]) / np.array(results_mcc["central_conv"])
            print(f"  {m:9s} macro F1 {r.mean():.3f} (min {r.min():.3f})   "
                  f"MCC {rm.mean():.3f} (min {rm.min():.3f})")


def robustness(a, clients, test, cfg):
    """Each method twice on the same seeds: as it runs in the panel, and with
    secure aggregation and/or dropout switched on. The first run must reproduce
    the panel's logged figures, which is the check that the options leave the
    default path alone."""
    treat = dict(secure_agg=a.secure_agg, dropout=a.dropout,
                 dropout_mode=a.dropout_mode, recover=not a.no_recover)
    on = [k for k in ("secure_agg", "dropout") if treat[k]]
    desc = []
    if a.secure_agg:
        desc.append("secure aggregation" + ("" if treat["recover"]
                                            else " WITHOUT mask recovery"))
    if a.dropout is not None:
        desc.append(f"dropout {a.dropout:.2f} ({a.dropout_mode})")
    print(f"robustness arm: {', '.join(desc)}; "
          f"{int(cfg['participation'] * len(clients))} of {len(clients)} clients "
          f"sampled per round, {cfg['rounds']} rounds, mu {cfg['mu']}, "
          f"tau {cfg['tau']}, lam {cfg['lam']}\n")
    for method in a.methods.split(","):
        base = [run_method(method, clients, test, cfg, s) for s in range(a.seeds)]
        SECAGG_STATS.clear()
        arm = [run_method(method, clients, test, dict(cfg, **treat), s)
               for s in range(a.seeds)]
        b1, b2 = np.array([x[0] for x in base]), np.array([x[1] for x in base])
        t1, t2 = np.array([x[0] for x in arm]), np.array([x[1] for x in arm])
        print(f"{method:9s} baseline macro F1 {b1.mean():.4f} +/- {b1.std():.4f}"
              f"   MCC {b2.mean():.4f} +/- {b2.std():.4f}")
        print(f"{method:9s} arm      macro F1 {t1.mean():.4f} +/- {t1.std():.4f}"
              f"   MCC {t2.mean():.4f} +/- {t2.std():.4f}")
        for name, x, y in (("macro F1", t1, b1), ("MCC", t2, b2)):
            delta = (x - y).mean()
            if np.allclose(x, y, atol=0, rtol=0):
                print(f"  {name}: identical on all {len(x)} seeds")
                continue
            try:
                pval = wilcoxon(list(x), list(y))
                print(f"  {name}: delta {delta:+.4f}  p = {pval:.4f}"
                      f"  ({int((x > y).sum())} of {len(x)} seeds higher)")
            except ValueError as e:
                print(f"  {name}: delta {delta:+.4f}  {e}")
        st = SECAGG_STATS
        if "dropped" in st:
            print(f"  clients dropped per round, mean {np.mean(st['dropped']):.2f}; "
                  f"rounds with no client reporting {len(st.get('empty_rounds', []))}")
        if "max_dev" in st:
            d = st["d"]
            print(f"  secure sum against the plain weighted sum: largest deviation "
                  f"of any weight in any round {max(st['max_dev']):.3e}")
            print(f"  what the server sees: |cosine| between a masked update and "
                  f"the true one, mean {np.mean(st['cos']):.4f} over "
                  f"{len(st['cos'])} rounds")
            print(f"  payload per client per round: {d} weights, {4 * d} bytes as "
                  f"float32 in the clear, {8 * d} bytes masked as int64")
            if a.dropout is not None:
                print(f"  mask recovery: {sum(st['reveals'])} seed reveals in total, "
                      f"{np.mean(st['reveals']):.1f} per round"
                      + ("" if treat["recover"] else " (recovery OFF)"))
        print()
    print("Key agreement is not simulated: in a deployment each sampled client\n"
          "also exchanges one 32-byte public key per peer per round. FedProto's\n"
          "prototypes are not masked. Threat model: honest-but-curious server.")


def decentral(a, clients, test, cfg, ids):
    """FedAvg against decentralised averaging on the same clients and seeds,
    with and without permanent node failures. The brief names single points of
    failure as a reason central detectors fail; FedAvg still has one, its
    server. This asks what removing it costs."""
    adj = road_ring(ids, a.extra_links)
    deg = np.array([len(s) for s in adj])
    d = sum(p.numel() for p in MLP(cfg["d_in"], cfg["n_classes"]).parameters())
    print(f"decentralised averaging: {len(clients)} nodes on a road ring plus "
          f"{a.extra_links} random links each; degree median {int(np.median(deg))}, "
          f"min {deg.min()}, max {deg.max()}; Metropolis weights; participation "
          f"{cfg['participation']} as FedAvg; {cfg['rounds']} rounds; "
          f"{a.gossip_steps} gossip step(s) per round")
    print(f"per round a node sends its {d} weights to each neighbour: "
          f"{int(np.median(deg)) * 4 * d:,} bytes at the median degree, against "
          f"{2 * 4 * d:,} down and up for a sampled FedAvg client\n")
    rows = {"fedavg": [], "dec_mean": [], "dec_worst": [], "dec_avg": [],
            "fail_mean": [], "fail_worst": [], "fail_avg": []}
    for s in range(a.seeds):
        fa, _ = run_method("fedavg", clients, test, cfg, s)
        r0 = run_decentralised(clients, test, cfg, s, adj, gossip_steps=a.gossip_steps)
        r1 = run_decentralised(clients, test, cfg, s, adj, a.fail_frac, a.fail_round,
                               gossip_steps=a.gossip_steps)
        rows["fedavg"].append(fa)
        for k, r in (("dec", r0), ("fail", r1)):
            rows[f"{k}_mean"].append(r["mean"])
            rows[f"{k}_worst"].append(r["worst"])
            rows[f"{k}_avg"].append(r["avg_model"])
        print(f"seed {s}: fedavg {fa:.4f} | decentralised node mean {r0['mean']:.4f} "
              f"worst {r0['worst']:.4f} average model {r0['avg_model']:.4f} "
              f"consensus {r0['consensus']:.4f} | {a.fail_frac:.0%} failed at round "
              f"{a.fail_round}: node mean {r1['mean']:.4f} worst {r1['worst']:.4f} "
              f"average model {r1['avg_model']:.4f} consensus {r1['consensus']:.4f} "
              f"live {r1['alive']} components {r1['components']}", flush=True)
    print()
    for k, v in rows.items():
        print(f"{k:11s} macro F1 {np.mean(v):.4f} +/- {np.std(v):.4f}")
    if a.seeds >= 5:
        print(f"\npaired Wilcoxon against FedAvg (n={a.seeds} seeds):")
        for k, v in rows.items():
            if k == "fedavg":
                continue
            delta = np.mean(v) - np.mean(rows["fedavg"])
            ahead = int(sum(x > y for x, y in zip(v, rows["fedavg"])))
            print(f"  {k:11s} delta {delta:+.4f}  ahead on {ahead} of {a.seeds}  "
                  f"p = {wilcoxon(v, rows['fedavg']):.4f}")


if __name__ == "__main__":
    main()
