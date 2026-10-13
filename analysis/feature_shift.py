#!/usr/bin/env python3
"""
Which features move when only the radio changes? (RESULTS 5m.)

Two corpora that share their vehicles and attacks and differ in one setting,
here transmit power. For honest rows only, so attacks cannot drive it, each
feature's mean shift in units of its standard deviation in the first corpus,
largest first. Shows which features carry a shift before any model sees it.

Usage: feature_shift.py A/pooled_regions.pkl B/pooled_regions.pkl [--seeds seed1 ...]
"""
import argparse

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--seeds", nargs="+", default=["seed1", "seed2", "seed3", "seed4"])
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    fr = []
    for p in (a.a, a.b):
        d = pd.read_pickle(p)
        d = d[(d.label_attackId == 0) & d.key_seed.isin(a.seeds)]
        fr.append(d)
    feats = [c for c in fr[0].columns if c.startswith(("app_", "phy_", "pool_")) and c in fr[1].columns]
    A = fr[0][feats].replace([np.inf, -np.inf], np.nan)
    B = fr[1][feats].replace([np.inf, -np.inf], np.nan)
    sd = A.std().replace(0, np.nan)
    shift = ((B.mean() - A.mean()) / sd).abs().sort_values(ascending=False)
    print(f"honest rows: {len(A):,} in {a.a}, {len(B):,} in {a.b}; {len(feats)} features")
    print(f"mean shift in standard deviations of the first corpus, largest {a.top}:")
    for f, v in shift.head(a.top).items():
        print(f"  {f:28s} {v:6.2f}")
    print(f"median over all features {shift.median():.2f}")
    print("FEATURE SHIFT DONE")


if __name__ == "__main__":
    main()
