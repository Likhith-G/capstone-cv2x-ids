#!/usr/bin/env python3
"""
Learning curves for the federated panel against a central ceiling, on
VALIDATION only. The test rows are never built into a score here: this script
chooses the round budget, local epochs and server optimiser, and the panel in
federated.py then runs the frozen choice on test once.

Each arm is one long run per seed, scored on validation after the rounds in
--checkpoints. Round r of a long run is round r of a short one (federated.py,
run_method), so this is the same as separate runs at each budget.

The central ceiling is the same MLP and local optimiser trained on the union of
the training clients' rows, scored after every epoch. Each federated
checkpoint is compared with central at the same row exposure (rounds x local
epochs x participation epochs) and with central's best epoch.

An arm is method[:key=value,...], for example
  fedavg
  fedlc:tau=8
  fedavg:server_opt=avgm,server_lr=1.0,server_beta1=0.9
  fedlc:tau=8,server_opt=adam,server_lr=0.01,server_tau=0.001
"""
import argparse
import json
import time

import numpy as np
import pandas as pd

from federated import (CENTRAL_EPOCHS, build_clients, build_clients_tx, evaluate,
                       load_panel_data, run_central, run_method)


def parse_arm(spec):
    method, _, rest = spec.partition(":")
    kw = {}
    for item in filter(None, rest.split(",")):
        k, v = item.split("=")
        try:
            kw[k] = float(v)
        except ValueError:
            kw[k] = v
    return method, kw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--observer-col", default="key_rxNodeId")
    ap.add_argument("--observer-role", default=None)
    ap.add_argument("--restrict-first", action="store_true")
    ap.add_argument("--sample", type=int, default=200000)
    ap.add_argument("--split-file", default=None)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--checkpoints", default="20,50,100,200")
    ap.add_argument("--local-epochs", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--arms", default="fedavg,fedlc:tau=4,fedlc:tau=8,fedlc:tau=16,fedlc:tau=32")
    ap.add_argument("--no-central", action="store_true")
    ap.add_argument("--central-lr", type=float, default=None,
                    help="learning rate for the central run only, to check "
                         "that the ceiling is not an artefact of sharing the "
                         "federated arms' optimiser")
    ap.add_argument("--central-epochs", type=int, default=None,
                    help="default: CENTRAL_EPOCHS, or the largest matched "
                         "exposure in the sweep if that is longer")
    ap.add_argument("--json", default=None, help="write every curve here")
    a = ap.parse_args()

    df = load_panel_data(a.features, a.sample, a.observer_role, a.restrict_first)
    prefixes = ("app_", "phy_", "pool_")
    feats = [c for c in df.columns if c.startswith(prefixes)]
    if a.split_file:
        clients, val, _, n_classes = build_clients_tx(
            df, feats, pd.read_csv(a.split_file), observer_col=a.observer_col)
        protocol = "held-out transmitters"
    else:
        clients, val, _, n_classes = build_clients(df, feats, observer_col=a.observer_col)
        protocol = "held-out observers"
    del df
    cps = [int(c) for c in a.checkpoints.split(",")]
    base = dict(d_in=len(feats), n_classes=n_classes, embed_dim=32, lr=0.05,
                batch_size=128, rounds=max(cps), participation=0.5,
                mu=0.01, tau=1.0, lam=0.1)
    print(f"{protocol}: {len(clients)} clients, "
          f"{sum(len(c[0]) for c in clients)} training rows, {len(val[0])} "
          f"validation rows, {len(feats)} features, {n_classes} classes, "
          f"{a.seeds} seeds, checkpoints {cps}\n", flush=True)

    out = {"protocol": protocol, "clients": len(clients), "val_rows": len(val[0]),
           "checkpoints": cps, "fed": {}, "central": {}}

    p = base["participation"]
    exposures = sorted({max(1, int(round(r * e * p))) for r in cps for e in a.local_epochs})
    if not a.no_central:
        ce = a.central_epochs or max(max(exposures), CENTRAL_EPOCHS)
        for s in range(a.seeds):
            t0 = time.time()
            curve = {}

            def cb(ep, w):
                curve[ep] = evaluate(base, w, val)
            run_central(clients, dict(base, lr=a.central_lr or base["lr"]), s, ce,
                        callback=cb)
            out["central"][s] = {str(k): v for k, v in curve.items()}
            best = max(curve, key=lambda k: curve[k][0])
            print(f"central (lr {a.central_lr or base['lr']}) seed {s}: best validation macro F1 {curve[best][0]:.4f} "
                  f"at epoch {best} of {ce}, MCC {curve[best][1]:.4f}  "
                  f"({time.time() - t0:.0f} s)", flush=True)
        print(flush=True)

    for E in a.local_epochs:
        for spec in filter(None, a.arms.split(",")):
            method, kw = parse_arm(spec)
            cfg = dict(base, local_epochs=E, **kw)
            key = f"{spec}|E={E}"
            out["fed"][key] = {}
            for s in range(a.seeds):
                t0 = time.time()
                curve = {}

                def cb(r, w):
                    if r in cps:
                        curve[r] = evaluate(cfg, w, val)
                run_method(method, clients, val, cfg, s, callback=cb)
                out["fed"][key][s] = {str(k): v for k, v in curve.items()}
                print(f"{key:55s} seed {s}  " + "  ".join(
                    f"r{r} {curve[r][0]:.4f}" for r in cps)
                    + f"  ({time.time() - t0:.0f} s)", flush=True)

    # Summary: mean over seeds at each checkpoint, beside central at matched
    # exposure and central's best.
    print("\nvalidation macro F1 (MCC), mean over seeds")
    if out["central"]:
        cbest_f1 = np.mean([max(v[0] for v in c.values()) for c in out["central"].values()])
        cbest_mcc = np.mean([max(c.values(), key=lambda v: v[0])[1]
                             for c in out["central"].values()])
        print(f"central, best validation epoch within the budget: "
              f"{cbest_f1:.4f} ({cbest_mcc:.4f})")
    hdr = "".join(f"{'r' + str(r):>18s}" for r in cps)
    print(f"{'arm':55s}{hdr}")
    for key, seeds in out["fed"].items():
        cells = []
        for r in cps:
            f = np.mean([seeds[s][str(r)][0] for s in seeds])
            m = np.mean([seeds[s][str(r)][1] for s in seeds])
            cells.append(f"{f:.4f} ({m:.4f})")
        print(f"{key:55s}" + "".join(f"{c:>18s}" for c in cells))
    if out["central"]:
        for E in a.local_epochs:
            cells = []
            for r in cps:
                ep = str(max(1, int(round(r * E * p))))
                f = np.mean([c[ep][0] for c in out["central"].values()])
                m = np.mean([c[ep][1] for c in out["central"].values()])
                cells.append(f"{f:.4f} ({m:.4f})")
            print(f"{'central, matched exposure|E=' + str(E):55s}"
                  + "".join(f"{c:>18s}" for c in cells))
        print("\nshare of central's best epoch, macro F1")
        for key, seeds in out["fed"].items():
            print(f"{key:55s}" + "".join(
                f"{np.mean([seeds[s][str(r)][0] for s in seeds]) / cbest_f1:>18.3f}"
                for r in cps))

    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh)


if __name__ == "__main__":
    main()
