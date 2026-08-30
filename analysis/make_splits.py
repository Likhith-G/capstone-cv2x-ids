#!/usr/bin/env python3
"""
Turn the corpus into the two sets the evaluation needs.

**Balanced set.** Every attack window is kept and benign windows are
subsampled to a target share, default 30 percent. Subsampling is stratified by
observer so it does not quietly delete a whole stretch of road, and by station
so no station disappears entirely. This is what the classifiers train on.

**Deployment-realism set.** The corpus at its natural prevalence, untouched.
Real traffic is overwhelmingly benign, so a model tuned on a balanced set will
have a false positive rate here that looks nothing like its balanced-set
precision. In a safety system a false positive can trigger braking, so this is
a primary metric, not an afterthought. Report both.

Usage: make_splits.py <corpus.csv> --out-dir <dir> [--benign-share 0.30]
"""
import argparse
import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--observer-col", default="key_rxNodeId",
                    help="column identifying an observer. Use key_region for a pooled corpus, where the observer is an RSU region")
    ap.add_argument("--benign-share", type=float, default=0.30)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--holdout", type=float, default=0.30,
                    help="fraction of STATIONS reserved for the realism set")
    a = ap.parse_args()

    load = lambda x: pd.read_pickle(x) if x.endswith('.pkl') else pd.read_csv(x)
    df = load(a.corpus)

    # Hold out whole STATIONS for the realism set. Subsampling benign windows
    # while leaving every station in both sets means the deployment evaluation
    # measures the false positive rate on stations the model has already
    # trained on, which is exactly the thing it exists to avoid.
    stations = df.label_txNodeId.dropna().unique()
    rs = np.random.RandomState(a.seed)
    rs.shuffle(stations)
    held = set(stations[:max(1, int(round(a.holdout * len(stations))))])
    train_df = df[~df.label_txNodeId.isin(held)]
    realism = df[df.label_txNodeId.isin(held)]

    attack = train_df[train_df.label_attackId > 0]
    benign = train_df[train_df.label_attackId == 0]

    n_attack = len(attack)
    # benign / (benign + attack) = share  ->  benign = share/(1-share) * attack
    n_benign = int(round(a.benign_share / (1.0 - a.benign_share) * n_attack))
    n_benign = min(n_benign, len(benign))

    # Stratify by observer so the sample keeps the geography, and take an equal
    # share from each rather than a flat random draw over the whole pool.
    frac = n_benign / len(benign)
    rng = np.random.RandomState(a.seed)
    kept = (benign.groupby(a.observer_col, group_keys=False)
                  .apply(lambda g: g.sample(
                      n=max(1, int(round(len(g) * frac))),
                      random_state=rng.randint(0, 2**31 - 1))))

    balanced = pd.concat([attack, kept], ignore_index=True).sample(
        frac=1.0, random_state=a.seed).reset_index(drop=True)

    bal_path = f"{a.out_dir}/balanced.pkl"
    real_path = f"{a.out_dir}/realism.pkl"
    balanced.to_pickle(bal_path)
    realism.to_pickle(real_path)

    share = (balanced.label_attackId == 0).mean()
    print(f"balanced: {len(balanced)} windows, benign share {share:.3f} -> {bal_path}")
    print(f"realism : {len(realism)} windows, benign share "
          f"{(realism.label_attackId == 0).mean():.3f} -> {real_path}")
    print(f"stations: {balanced.label_txNodeId.nunique()} in balanced, "
          f"{realism.label_txNodeId.nunique()} held out, "
          f"{len(set(balanced.label_txNodeId) & set(realism.label_txNodeId))} overlapping "
          f"(must be 0)")
    print("\nbalanced set, windows per class:")
    print(balanced.label_attackId.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
