#!/usr/bin/env python3
"""
What the detector does once it is deployed, rather than on a balanced test set.

Two numbers decide whether a V2X misbehaviour detector is usable, and neither
appears in a balanced-set classification report.

**False positive rate at true prevalence.** Real traffic is overwhelmingly
benign. A model trained at 30 percent attack prevalence and reported at that
prevalence looks far better than it will behave. A headline F1 measured on a
balanced set does not answer this question and is routinely mistaken for an
answer to it.

**Alert rate per observer per hour.** This is the number an operator actually
lives with. A 1 percent false positive rate sounds excellent and, at one
decision per neighbour per second with fifty neighbours in range, means about
eighteen hundred false alerts per hour at a single roadside unit. In a system
where an alert can trigger braking that is not a deployable detector, and the
figure has to be stated plainly rather than left implicit in a percentage.

Usage: evaluate_deployment.py --balanced <balanced.csv> --realism <realism.csv>
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balanced", required=True)
    ap.add_argument("--realism", required=True)
    ap.add_argument("--window-ms", type=float, default=1000.0)
    ap.add_argument("--trees", type=int, default=150)
    ap.add_argument("--sample", type=int, default=300000)
    ap.add_argument("--decisions-per-window", type=float, default=None,
                    help="decisions an observer makes per window. Defaults to "
                         "the median neighbour count. A POOLED detector makes "
                         "one decision per station per window for the whole "
                         "region, so the fleet raises one alert where a fleet "
                         "of independent receivers raises one each.")
    a = ap.parse_args()

    load = lambda x: pd.read_pickle(x) if x.endswith('.pkl') else pd.read_csv(x)
    tr = load(a.balanced)
    te = load(a.realism)
    feats = [c for c in tr.columns if c.startswith(("app_", "phy_", "pool_"))]

    # A station that appears in training must not appear in the realism
    # evaluation, or the false positive rate is measured on stations the model
    # has already seen.
    seen = set(tr.label_txNodeId.unique())
    te = te[~te.label_txNodeId.isin(seen)]
    if te.empty:
        raise SystemExit(
            "every station in the realism set was also in the balanced set. "
            "Hold out whole stations when building the splits.")
    if len(te) > a.sample:
        te = te.sample(n=a.sample, random_state=0)

    X = lambda d: d[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=-1, random_state=0)
    clf.fit(X(tr), tr.label_is_attack)

    proba = clf.predict_proba(X(te))[:, 1]
    y = te.label_is_attack.values
    prevalence = y.mean()

    print(f"trained on {len(tr)} balanced windows "
          f"({(tr.label_is_attack == 0).mean():.1%} benign)")
    print(f"evaluated on {len(te)} held-out windows at true prevalence "
          f"({1 - prevalence:.1%} benign), {te.label_txNodeId.nunique()} unseen stations\n")

    windows_per_hour = 3600.0 / (a.window_ms / 1000.0)
    n_benign = int((y == 0).sum())

    print(f"{'threshold':>9s} {'FPR':>8s} {'recall':>8s} {'precision':>10s} "
          f"{'false alerts/observer/hour':>28s}")
    for t in [0.5, 0.7, 0.9, 0.95, 0.99]:
        pred = proba >= t
        fp = int((pred & (y == 0)).sum())
        tp = int((pred & (y == 1)).sum())
        fpr = fp / max(1, n_benign)
        recall = tp / max(1, int((y == 1).sum()))
        prec = tp / max(1, tp + fp)
        # One decision per observed neighbour per window. The neighbour count
        # the observers actually saw is in the features.
        neigh = (a.decisions_per_window if a.decisions_per_window is not None
                 else (te.phy_neighbours.median()
                       if "phy_neighbours" in te else 1.0))
        alerts = fpr * windows_per_hour * float(neigh)
        print(f"{t:9.2f} {fpr:8.4f} {recall:8.4f} {prec:10.4f} {alerts:28.0f}")

    print("\nat threshold 0.5, per class:")
    print(classification_report(y, proba >= 0.5, digits=3, zero_division=0,
                                target_names=["benign", "attack"]))


if __name__ == "__main__":
    main()
