#!/usr/bin/env python3
"""
What each aggregation method costs a client per round, in bytes and in time.

The federated panel compares five methods on detection. Part A argued for
federation on bandwidth, and the Completion Plan asked for the communication and
compute cost of each method (task 2.6). This measures both on the same clients
and configuration the panel used, by running federated.py's own local training
and reading the size of what it returns, rather than by arithmetic on the model.

What crosses the link each round:

- down, every method: the global weights. FedProto also sends the global class
  prototypes once it has them.
- up, every method: the client's weights and its sample count, which the
  weighted average needs. FedNova adds its local step count. FedProto adds a
  prototype sum and a count per class. FedProx and FedLC send exactly what
  FedAvg sends: the proximal term and the logit offsets are computed locally.
- secure aggregation, for the weighted-average methods: the update is sent as
  int64 rather than float32, so twice the bytes, plus one 32-byte public key per
  other sampled client for key agreement, which is not simulated.

Sizes assume float32 values, an int32 count and no protocol overhead, so they
are a lower bound on the bytes on the air. Timing is local training only, one
client after another on one machine, which is the development laptop and not a
vehicle or roadside unit.

Each method runs one untimed round first so FedProto has prototypes and every
method is warm, then one timed round over every training client.

    fed_cost.py FEATURES [--observer-col key_region] [--observer-role rsu]
"""
import argparse
import platform
import time

import numpy as np
import pandas as pd
import torch

from federated import MLP, build_clients, flat, load_flat, local_train

METHODS = ["fedavg", "fedprox", "fednova", "fedlc", "fedproto"]
F32, I32, I64, KEY = 4, 4, 8, 32


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--observer-col", default="key_rxNodeId")
    ap.add_argument("--observer-role", default=None)
    ap.add_argument("--sample", type=int, default=200000)
    ap.add_argument("--local-epochs", type=int, default=2)
    ap.add_argument("--mu", type=float, default=0.0001)
    ap.add_argument("--tau", type=float, default=4.0)
    ap.add_argument("--lam", type=float, default=0.01)
    ap.add_argument("--rounds", type=int, default=20,
                    help="the panel's round count, for the totals only")
    a = ap.parse_args()

    # The same preparation as federated.main, so the clients are the panel's.
    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    if len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0)
    if a.observer_role and "key_observer_role" in df.columns:
        df = df[df.key_observer_role == a.observer_role]
    feats = [c for c in df.columns if c.startswith(("app_", "phy_", "pool_"))]
    clients, val, test, n_classes = build_clients(df, feats,
                                                  observer_col=a.observer_col)
    cfg = dict(d_in=len(feats), n_classes=n_classes, embed_dim=32, lr=0.05,
               batch_size=128, local_epochs=a.local_epochs, rounds=1,
               participation=0.5, mu=a.mu, tau=a.tau, lam=a.lam)
    print(f"{len(clients)} training clients, {len(val[0])} validation rows, "
          f"{len(test[0])} test rows, {len(feats)} features, {n_classes} classes")
    rows = np.array([len(c[0]) for c in clients])
    print(f"rows per training client: median {np.median(rows):.0f}, "
          f"min {rows.min()}, max {rows.max()}")
    sampled = max(1, int(cfg["participation"] * len(clients)))
    print(f"clients sampled per round: {sampled} of {len(clients)}")
    print(f"machine: {platform.machine()}, {platform.system()} "
          f"{platform.release()}, torch {torch.__version__}, "
          f"{torch.get_num_threads()} threads\n")

    torch.manual_seed(0)
    g = MLP(cfg["d_in"], cfg["n_classes"])
    d = flat(g).numel()
    proto = n_classes * cfg["embed_dim"]
    print(f"model: {d} weights, {d * F32:,} bytes as float32")

    out = []
    for method in METHODS:
        gvec = flat(g).clone()
        global_proto = None
        times, ups = [], []
        for timed in (False, True):
            sums, cnts = [], []
            for X, y, counts in clients:
                m = MLP(cfg["d_in"], cfg["n_classes"])
                load_flat(m, gvec)
                t0 = time.perf_counter()
                w, steps, pr = local_train(m, gvec, X, y, method, cfg, counts,
                                           global_proto)
                dt = time.perf_counter() - t0
                up = w.numel() * F32 + I32
                if method == "fednova":
                    up += I32
                if pr is not None:
                    up += pr[0].numel() * F32 + pr[1].numel() * F32
                    sums.append(pr[0])
                    cnts.append(pr[1])
                if timed:
                    times.append(dt)
                    ups.append(up)
            if method == "fedproto" and sums:
                s, c = torch.stack(sums).sum(0), torch.stack(cnts).sum(0)
                global_proto = torch.where(c[:, None] > 0,
                                           s / c[:, None].clamp(min=1),
                                           torch.zeros_like(s))
        down = d * F32 + (proto * F32 if method == "fedproto" else 0)
        t = np.array(times)
        out.append(dict(method=method, down=down, up=int(np.median(ups)),
                        t_med=np.median(t), t_p90=np.percentile(t, 90),
                        t_max=t.max()))

    print(f"\n{'method':>9s} {'down B':>8s} {'up B':>8s} {'round B':>9s} "
          f"{'local ms median':>16s} {'p90':>7s} {'max':>7s}")
    base = out[0]
    for r in out:
        print(f"{r['method']:>9s} {r['down']:>8,} {r['up']:>8,} "
              f"{r['down'] + r['up']:>9,} {1e3 * r['t_med']:>16.1f} "
              f"{1e3 * r['t_p90']:>7.1f} {1e3 * r['t_max']:>7.1f}")
    print("  round B is one client's download plus upload in one round")

    secure = d * I64 + I32 + (sampled - 1) * KEY
    print(f"\nsecure aggregation, FedAvg and FedLC only: upload {secure:,} bytes "
          f"({d * I64:,} masked int64 weights, a count, and {sampled - 1} public "
          f"keys of {KEY} bytes), {secure / base['up']:.2f} times the plain upload")
    print("  key agreement is not simulated; its size is the X25519 public key")

    rounds = a.rounds
    print(f"\nover the panel's {rounds} rounds, a client sampled every round "
          f"would move at most:")
    for r in out:
        print(f"  {r['method']:>9s} {rounds * (r['down'] + r['up']) / 1e6:.2f} MB")
    print(f"  fedavg with secure aggregation "
          f"{rounds * (base['down'] + secure) / 1e6:.2f} MB")
    print("\nSizes are a lower bound: float32 values, no protocol overhead. "
          "Times are local\ntraining only, on the development machine, not on "
          "vehicle or roadside hardware.")
    print("FED COST DONE")


if __name__ == "__main__":
    main()
