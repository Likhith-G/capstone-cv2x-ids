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


def run_method(method, clients, test, cfg, seed, detail=False, init=None):
    torch.manual_seed(seed)
    np.random.seed(seed)
    g = MLP(cfg["d_in"], cfg["n_classes"])
    # init: start from given weights (a model trained elsewhere, for
    # adaptation) instead of a fresh initialisation. None keeps every existing
    # run identical, since the fresh model above is still drawn either way.
    gvec = flat(g).clone() if init is None else init.clone()
    global_proto = None

    for rnd in range(cfg["rounds"]):
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
    a = ap.parse_args()

    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    if len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0)
    if a.observer_role and "key_observer_role" in df.columns:
        before = df.key_rxNodeId.nunique()
        df = df[df.key_observer_role == a.observer_role]
        print(f"restricted to {a.observer_role} observers: "
              f"{df.key_rxNodeId.nunique()} of {before} clients\n")
        if df.empty:
            raise SystemExit(f"no observers with role {a.observer_role!r}")
    # pool_ is the cross-receiver consensus block. It exists only in a pooled
    # corpus and it is the part of the feature set a lone receiver cannot
    # compute, so a panel run without it is measuring feature averaging rather
    # than the architecture.
    prefixes = ("app_", "phy_") if a.drop_consensus else ("app_", "phy_", "pool_")
    feats = [c for c in df.columns if c.startswith(prefixes)]

    clients, val, test, n_classes = build_clients(df, feats,
                                                  observer_col=a.observer_col)
    cfg = dict(d_in=len(feats), n_classes=n_classes, embed_dim=32, lr=0.05,
               batch_size=128, local_epochs=a.local_epochs, rounds=a.rounds,
               participation=0.5, mu=a.mu, tau=a.tau, lam=a.lam)

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


if __name__ == "__main__":
    main()
