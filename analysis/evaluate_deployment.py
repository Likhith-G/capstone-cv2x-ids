#!/usr/bin/env python3
"""
What the detector does once it is deployed, rather than on a balanced test set.

Two numbers decide whether a V2X misbehaviour detector is usable, and neither
appears in a balanced-set classification report.

**False positive rate on unbalanced data.** Real traffic is overwhelmingly
benign. A model trained at 30 percent attack prevalence and reported at that
prevalence looks far better than it will behave. A headline F1 measured on a
balanced set does not answer this question and is routinely mistaken for an
answer to it.

The held-out set is at the SIMULATED prevalence, about a third of windows from
attackers, which is far above anything a road would see. False positive rate,
recall and the alert rate do not depend on prevalence and are read directly.
Precision and binary MCC do, so they are also given reweighted to a stated
deployment prevalence, --deploy-prevalence, from the same false positive rate
and recall.

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
from sklearn.metrics import classification_report, matthews_corrcoef


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balanced", required=True)
    ap.add_argument("--realism", required=True)
    ap.add_argument("--window-ms", type=float, default=1000.0)
    ap.add_argument("--trees", type=int, default=150)
    ap.add_argument("--deploy-prevalence", type=float, default=0.01,
                    help="share of windows from attackers in a deployment, for "
                         "the reweighted precision and MCC columns")
    ap.add_argument("--sample", type=int, default=300000)
    ap.add_argument("--decisions-per-window", type=float, default=None,
                    help="decisions an observer makes per window. A POOLED "
                         "detector makes one decision per station per window for "
                         "the whole region, so the fleet raises one alert where a "
                         "fleet of independent receivers raises one each.")
    ap.add_argument("--population", default=None,
                    help="the full corpus the splits were cut from. Without "
                         "--decisions-per-window, the decisions per observer per "
                         "window are counted from it: the claimed stations each "
                         "receiver decodes in each window. The realism set holds "
                         "only held-out stations and is subsampled, so counting "
                         "its rows would undercount")
    a = ap.parse_args()
    if a.decisions_per_window is None and a.population is None:
        raise SystemExit("give --decisions-per-window or --population; the alert "
                         "rate is meaningless without a decision count")

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

    if a.decisions_per_window is not None:
        decisions = a.decisions_per_window
    else:
        pop = load(a.population)
        decisions = float(pop.groupby(["key_seed", "key_rxNodeId", "key_window"])
                          .key_claimedStationId.nunique().median())
        del pop
    print(f"decisions per observer per window: {decisions:.1f}")

    X = lambda d: d[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=-1, random_state=0)
    clf.fit(X(tr), tr.label_is_attack)

    proba = clf.predict_proba(X(te))[:, 1]
    y = te.label_is_attack.values
    prevalence = y.mean()

    print(f"trained on {len(tr)} balanced windows "
          f"({(tr.label_is_attack == 0).mean():.1%} benign)")
    print(f"evaluated on {len(te)} held-out windows at the SIMULATED prevalence "
          f"({1 - prevalence:.1%} benign), {te.label_txNodeId.nunique()} unseen stations\n")

    windows_per_hour = 3600.0 / (a.window_ms / 1000.0)
    n_benign = int((y == 0).sum())

    # MCC here is BINARY, benign against attack, at each operating threshold.
    # It is not the multiclass MCC reported by benchmark.py and
    # pooled_consensus.py and the two are not comparable, which is why the
    # column says so. At the simulated prevalence both precision and MCC are
    # flattered; the two right hand columns recompute them at the deployment
    # prevalence from the false positive rate and recall, which do not depend
    # on it.
    q = a.deploy_prevalence
    print(f"{'threshold':>9s} {'FPR':>8s} {'recall':>8s} {'precision':>10s} "
          f"{'false alerts/observer/hour':>28s} {'MCC binary':>12s} "
          f"{'precision @%g%%' % (100 * q):>16s} {'MCC @%g%%' % (100 * q):>10s}")
    for t in [0.5, 0.7, 0.9, 0.95, 0.99]:
        pred = proba >= t
        fp = int((pred & (y == 0)).sum())
        tp = int((pred & (y == 1)).sum())
        fpr = fp / max(1, n_benign)
        recall = tp / max(1, int((y == 1).sum()))
        prec = tp / max(1, tp + fp)
        # One decision per claimed station a receiver decodes in a window, which
        # is the number of rows per (seed, receiver, window). It used to take
        # phy_neighbours, which counts every radio whose control channel appears
        # in the trace, undecodable ones included, and is 89 or 88 on every row
        # of a 90-vehicle road: that is the whole road, not the decisions a
        # receiver makes, and it overstated the alert rate about twofold.
        neigh = decisions
        alerts = fpr * windows_per_hour * float(neigh)
        mcc = matthews_corrcoef(y, pred)
        tp_q, fn_q = recall * q, (1 - recall) * q
        fp_q, tn_q = fpr * (1 - q), (1 - fpr) * (1 - q)
        prec_q = tp_q / (tp_q + fp_q) if tp_q + fp_q > 0 else float("nan")
        den = np.sqrt((tp_q + fp_q) * (tp_q + fn_q) * (tn_q + fp_q) * (tn_q + fn_q))
        mcc_q = (tp_q * tn_q - fp_q * fn_q) / den if den > 0 else float("nan")
        print(f"{t:9.2f} {fpr:8.4f} {recall:8.4f} {prec:10.4f} {alerts:28.0f}"
              f" {mcc:12.4f} {prec_q:16.4f} {mcc_q:10.4f}")

    print(f"\nbinary MCC at threshold 0.5: "
          f"{matthews_corrcoef(y, proba >= 0.5):.4f}, at the simulated prevalence "
          f"({prevalence:.4%} attack); see the right hand columns for "
          f"{100 * q:g} percent")
    print("\nat threshold 0.5, per class:")
    print(classification_report(y, proba >= 0.5, digits=3, zero_division=0,
                                target_names=["benign", "attack"]))


if __name__ == "__main__":
    main()
