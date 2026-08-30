#!/usr/bin/env python3
"""
How many of the 50 features are actually needed, selected without leaking.

Selection is done INSIDE each training fold and scored on the held-out fold.
Ranking features on the whole corpus and then reporting cross-validated scores
on the survivors would let the test fold influence which features exist, which
is a selection leak. That would be a poor thing to do in any project and an
absurd one here, where the entire premise is that the previous dataset was
defeated by leakage.

Two things are reported and they answer different questions:

  performance   how the model scores at each subset size, so a size can be
                chosen against a cost rather than by taste.
  stability     how often each feature is selected across folds. A feature
                chosen in every fold is a real signal; one chosen in two folds
                out of ten is fold noise, and reporting it as important would
                be the same error at a smaller scale.
"""
import argparse
from collections import Counter
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--sizes", type=int, nargs="+",
                    default=[5, 10, 15, 20, 30, 50])
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=150)
    ap.add_argument("--sample", type=int, default=150000)
    a = ap.parse_args()

    df = pd.read_pickle(a.corpus) if a.corpus.endswith(".pkl") else pd.read_csv(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1].reset_index(drop=True)
    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0).reset_index(drop=True)
    feats = [c for c in df.columns if c.startswith(("app_", "phy_"))]
    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    y = df.label_attackId.astype(int).values
    groups = df.label_txNodeId.astype(int).values
    print(f"{len(df)} windows, {len(feats)} features, {len(set(groups))} stations, "
          f"{len(set(y))} classes, {a.folds} grouped folds")

    sizes = sorted(set(a.sizes) | {len(feats)})
    scores = {k: [] for k in sizes}
    chosen = {k: Counter() for k in sizes}
    sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=0)
    for fold, (tr, te) in enumerate(sgkf.split(X, y, groups), 1):
        rank = RandomForestClassifier(n_estimators=a.trees, n_jobs=-1,
                                      random_state=0, class_weight="balanced")
        rank.fit(X[tr], y[tr])                      # training fold ONLY
        order = np.argsort(rank.feature_importances_)[::-1]
        for k in sizes:
            cols = order[:k]
            for c in cols:
                chosen[k][feats[c]] += 1
            clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=-1,
                                         random_state=0, class_weight="balanced")
            clf.fit(X[tr][:, cols], y[tr])
            scores[k].append(f1_score(y[te], clf.predict(X[te][:, cols]),
                                      average="macro"))
        print(f"  fold {fold} done")

    print(f"\n{'features':>9s}  {'macro F1':>18s}  {'vs all 50':>10s}")
    full = np.mean(scores[len(feats)])
    for k in sizes:
        v = np.array(scores[k])
        print(f"{k:>9d}  {v.mean():.4f} +/- {v.std():.4f}  {v.mean() - full:+10.4f}")

    k = min(s for s in sizes if s >= 15)
    print(f"\nselection stability at {k} features, over {a.folds} folds")
    for name, n in chosen[k].most_common():
        if n >= 2:
            print(f"  {n}/{a.folds}  {name}")
    unstable = sum(1 for _, n in chosen[k].items() if n == 1)
    print(f"  {len(chosen[k])} distinct features ever chosen, "
          f"{unstable} of them in only one fold")


if __name__ == "__main__":
    main()
