#!/usr/bin/env python3
"""
Federated evaluation panel.

Each observer is one client. That is the real systems argument for federating
this problem, and it is a much better one than the usual privacy argument: PHY
and MAC measurements are local to a receiver and cannot be centralised cheaply,
and different observers genuinely see different geography, traffic density and
channel occupancy. The label skew is therefore a property of the deployment,
not something injected with a Dirichlet parameter.

Methods, following the panel in PLAN_V2 section 7:
  fedavg     weighted average of client weights                    (baseline)
  fedprox    FedAvg plus a proximal term                           (stability)
  fednova    normalises for unequal local work                     (stability)
  fedlc      logit calibration, aimed straight at label skew
  fedproto   class prototypes shared alongside weights

Protocol, following report 06: at least five seeds, paired Wilcoxon across
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
from scipy.stats import wilcoxon
from sklearn.metrics import f1_score
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
    opt = torch.optim.SGD(model.parameters(), lr=cfg["lr"], momentum=0.9)
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
        protos = torch.where(proto_cnt[:, None] > 0,
                             proto_sum / proto_cnt[:, None].clamp(min=1),
                             torch.zeros_like(proto_sum))
    return flat(model).clone(), steps, protos


def run_method(method, clients, test, cfg, seed):
    torch.manual_seed(seed)
    np.random.seed(seed)
    g = MLP(cfg["d_in"], cfg["n_classes"])
    gvec = flat(g).clone()
    global_proto = None

    for rnd in range(cfg["rounds"]):
        sel = np.random.choice(len(clients),
                               size=max(1, int(cfg["participation"] * len(clients))),
                               replace=False)
        updates, weights, taus, protos = [], [], [], []
        for ci in sel:
            X, y, counts = clients[ci]
            m = MLP(cfg["d_in"], cfg["n_classes"])
            load_flat(m, gvec)
            w, steps, pr = local_train(m, gvec, X, y, method, cfg, counts, global_proto)
            updates.append(w)
            weights.append(len(X))
            taus.append(steps)
            if pr is not None:
                protos.append(pr)

        p = torch.tensor(weights, dtype=torch.float)
        p = p / p.sum()

        if cfg.get("dp_clip"):
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
            tau = torch.tensor(taus, dtype=torch.float)
            d = torch.stack([(gvec - u) / t for u, t in zip(updates, tau)])
            gvec = gvec - (p * tau).sum() * (p[:, None] * d).sum(0)
        else:
            gvec = (p[:, None] * torch.stack(updates)).sum(0)

        if method == "fedproto" and protos:
            global_proto = torch.stack(protos).mean(0)

    load_flat(g, gvec)
    g.eval()
    with torch.no_grad():
        pred = g(test[0]).argmax(1).numpy()
    return f1_score(test[1].numpy(), pred, average="macro")


def dp_epsilon(z, rounds, delta=1e-5):
    """(epsilon, delta) for composing `rounds` Gaussian mechanisms of noise
    multiplier z, by Renyi differential privacy.

    A Gaussian mechanism with noise multiplier z is (alpha, alpha/(2 z^2))-RDP,
    composition adds, and the standard conversion gives
    eps = rounds * alpha / (2 z^2) + log(1/delta) / (alpha - 1), minimised
    over alpha.

    No subsampling amplification is credited. Half the clients are sampled per
    round, which a real accountant would use to report a substantially smaller
    epsilon, so this is an upper bound and is labelled as one. Inventing a
    tighter number than the analysis supports is the failure mode to avoid
    here.
    """
    alphas = np.arange(1.01, 256.0, 0.01)
    eps = rounds * alphas / (2.0 * z ** 2) + np.log(1.0 / delta) / (alphas - 1.0)
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
    ap.add_argument("--lam", type=float, default=0.1)
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
    grids = {"fedprox": ("mu", [0.001, 0.01, 0.1]),
             "fedlc": ("tau", [0.5, 1.0, 2.0]),
             "fedproto": ("lam", [0.01, 0.1, 1.0])}
    chosen = {}
    if a.tune:
        for method, (name, values) in grids.items():
            if method not in a.methods.split(","):
                continue
            best, best_v = None, -1.0
            for v in values:
                c = dict(cfg, **{name: v})
                score = run_method(method, clients, val, c, seed=1000)
                if score > best_v:
                    best, best_v = v, score
            chosen[method] = (name, best)
            print(f"tuned {method}: {name} = {best} (validation macro F1 {best_v:.4f})")
        print()

    if a.dp_clip:
        # Privacy-utility sweep. Each row is one noise multiplier z; z = 0 is
        # clipping with no noise, which separates the cost of bounding a
        # client's influence from the cost of hiding it.
        print(f"DP-FedAvg, update clipped to L2 norm {a.dp_clip}, uniform "
              f"client weights, {len(clients)} clients, "
              f"{int(cfg['participation'] * len(clients))} sampled per round\n")
        print(f"{'z':>6s} {'macro F1':>18s} {'vs no DP':>9s} {'epsilon':>10s}")
        base = None
        for z in [None] + list(a.dp_noise or [0.0]):
            c = dict(cfg)
            if z is not None:
                c["dp_clip"], c["dp_noise"] = a.dp_clip, z
            scores = np.array([run_method("fedavg", clients, test, c, seed=s)
                               for s in range(a.seeds)])
            if z is None:
                base = scores.mean()
                print(f"{'off':>6s} {scores.mean():.4f} +/- {scores.std():.4f}"
                      f" {'':>9s} {'':>10s}")
                continue
            eps = dp_epsilon(z, a.rounds) if z > 0 else float("inf")
            eps_s = f"{eps:10.1f}" if np.isfinite(eps) else f"{'no noise':>10s}"
            print(f"{z:6.2f} {scores.mean():.4f} +/- {scores.std():.4f} "
                  f"{scores.mean() - base:+9.4f} {eps_s}")
        print("\nEpsilon is a CONSERVATIVE bound: Renyi composition of one\n"
              "Gaussian mechanism per round at delta = 1e-5, with NO subsampling\n"
              "amplification credited even though half the clients are sampled\n"
              "each round. A proper accountant would report a smaller number.\n"
              "The clipping norm, the noise multiplier, the round count and the\n"
              "sampling rate are all stated so it can be recomputed.")
        return

    results = {}
    for method in a.methods.split(","):
        c = cfg
        if method in chosen:
            name, v = chosen[method]
            c = dict(cfg, **{name: v})
        scores = [run_method(method, clients, test, c, s) for s in range(a.seeds)]
        results[method] = scores
        print(f"{method:9s} macro F1 {np.mean(scores):.4f} +/- {np.std(scores):.4f}   "
              f"{[round(s, 4) for s in scores]}")

    base = results.get("fedavg")
    if base and len(base) >= 5:
        print("\npaired Wilcoxon against FedAvg (n=%d seeds):" % len(base))
        for m, s in results.items():
            if m == "fedavg":
                continue
            try:
                stat, pval = wilcoxon(s, base)
                delta = np.mean(s) - np.mean(base)
                print(f"  {m:9s} delta {delta:+.4f}  p = {pval:.4f}"
                      f"{'  significant' if pval < 0.05 else ''}")
            except ValueError as e:
                print(f"  {m:9s} {e}")


if __name__ == "__main__":
    main()
