#!/usr/bin/env python3
"""
Is the detection floor a property of the problem, or of the Random Forest?

Every detection number in this project comes from one RandomForestClassifier.
The paper's central claim is a bound: a single receiver cannot detect a
constant position offset at any magnitude the dataset contains. A bound
evidenced by one estimator's failure is not a bound, it is a fact about that
estimator.

This runs the fused block under learner families that fail in different ways:
a linear model, a boosted tree ensemble, a bagged tree ensemble and a neural
network. Same rows, same folds, same features, so the comparison is paired.
If the position classes sit near zero for all of them, the claim changes from
"our detector cannot" to "no learner on this evidence can", which is the claim
the paper actually makes.

Scaling for the two scale-sensitive learners is inside a pipeline, so it is fit
on the training fold only and cannot leak.
"""
import argparse
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score, matthews_corrcoef

# The three constant-offset classes are one mechanism at three magnitudes and
# they are what the floor claim is about. Everything else is context.
POSITION = {11: "pos_small_offset  20 to 25 m",
            13: "pos_medium_offset 47 to 60 m",
            1: "pos_const_offset  71 to 233 m"}


def learners(trees, jobs, seed):
    """Four families that fail differently. A linear model cannot represent an
    interaction; a boosted ensemble fits residuals greedily; a bagged ensemble
    averages decorrelated trees; a network fits a smooth global function. If a
    signal existed in these features, at least one of them should find it."""
    # Ordered cheapest first so the log shows results early. The random forest
    # runs first and with the same settings as benchmark.py, so its row is a
    # reproduction check on this harness before any new learner is believed.
    return {
        "random forest": RandomForestClassifier(
            n_estimators=trees, n_jobs=jobs, random_state=seed),
        "hist gradient boosting": HistGradientBoostingClassifier(
            max_iter=200, random_state=seed),
        "mlp 128-64": make_pipeline(
            StandardScaler(),
            MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=80,
                          early_stopping=True, n_iter_no_change=8,
                          random_state=seed)),
        # lbfgs is single threaded on this problem and is the slowest of the
        # four despite being the simplest, so it goes last.
        "logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=150, n_jobs=jobs,
                               random_state=seed)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--sample", type=int, default=150000)
    ap.add_argument("--trees", type=int, default=100,
                    help="matches benchmark.py, so the random forest row reproduces\n                         the published figure and checks this harness")
    ap.add_argument("--jobs", type=int, default=-1)
    ap.add_argument("--block", default="fused", choices=["app", "phy", "fused"])
    a = ap.parse_args()

    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1].reset_index(drop=True)
    app = [c for c in df.columns if c.startswith("app_")]
    phy = [c for c in df.columns if c.startswith("phy_")]
    cols = {"app": app, "phy": phy, "fused": app + phy}[a.block]

    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0).reset_index(drop=True)
    y = df.label_attackId.astype(int)
    groups = df.label_txNodeId.astype(int)
    X = df[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    classes = sorted(y.unique())

    sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=0)
    folds = list(sgkf.split(df, y, groups))

    print(f"{len(df)} windows, {len(cols)} features in the {a.block} block, "
          f"{len(classes)} classes, {groups.nunique()} stations, "
          f"{a.folds} folds grouped by transmitting station")
    print("Same rows and same folds for every learner, so the comparison is "
          "paired.\n")

    per_class, summary = {}, {}
    for name, mk in learners(a.trees, a.jobs, 0).items():
        t0 = time.time()
        f1s, mccs, pc = [], [], []
        for tr, te in folds:
            from sklearn.base import clone
            clf = clone(mk)
            clf.fit(X.iloc[tr], y.iloc[tr])
            p = clf.predict(X.iloc[te])
            f1s.append(f1_score(y.iloc[te], p, average="macro"))
            mccs.append(matthews_corrcoef(y.iloc[te], p))
            pc.append(f1_score(y.iloc[te], p, average=None, labels=classes,
                               zero_division=0))
        per_class[name] = np.mean(pc, axis=0)
        summary[name] = (np.mean(f1s), np.std(f1s), np.mean(mccs), time.time() - t0)
        print(f"{name:24s} macro F1 {np.mean(f1s):.4f} +/- {np.std(f1s):.4f}   "
              f"MCC {np.mean(mccs):.4f}   ({summary[name][3]:.0f}s)")

    print(f"\nthe position classes, which are what the floor claim is about")
    print(f"{'class':34s}  " + "  ".join(f"{n:>22s}" for n in per_class)
          + f"  {'best':>8s}")
    for c, label in POSITION.items():
        if c not in classes:
            continue
        i = classes.index(c)
        vals = [per_class[n][i] for n in per_class]
        print(f"{str(c) + ' ' + label:34s}  "
              + "  ".join(f"{v:22.3f}" for v in vals)
              + f"  {max(vals):8.3f}")

    print(f"\nevery class, F1 averaged over {a.folds} folds")
    print(f"{'class':>6s}  " + "  ".join(f"{n:>22s}" for n in per_class)
          + f"  {'best':>8s}")
    for i, c in enumerate(classes):
        vals = [per_class[n][i] for n in per_class]
        print(f"{c:>6d}  " + "  ".join(f"{v:22.3f}" for v in vals)
              + f"  {max(vals):8.3f}")

    best_pos = {c: max(per_class[n][classes.index(c)] for n in per_class)
                for c in POSITION if c in classes}
    print("\nThe 'best' column is the highest score any of these four learners "
          "reached on that\nclass. For the floor claim it is the number that "
          "matters: it is what the evidence\nsupports at its most generous, "
          "not what one estimator happened to get.")
    print("\nbest over all four learners on the position classes: "
          + ", ".join(f"class {c} {v:.3f}" for c, v in best_pos.items()))


if __name__ == "__main__":
    main()
