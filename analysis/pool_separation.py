#!/usr/bin/env python3
"""
Per class separation of the cross-observer consensus statistics, in benign
standard deviations. No classifier involved, so this says what the statistics
know rather than what a model can fit.

The negative controls are the point. speed_falsify and sps_manipulation tell
the truth about position, so a consensus statistic that fires on them would be
picking up something other than the geometry it claims to measure.
"""
import argparse
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("pooled")
a = ap.parse_args()
d = pd.read_pickle(a.pooled)
pool = [c for c in d.columns if c.startswith("pool_")]
ben = d.label_attackId == 0
classes = [c for c in sorted(d.label_attackId.unique()) if c]
print(f"{len(d)} pooled units, {int(ben.sum())} benign\n")
print("median shift from benign, in benign standard deviations")
print(f"{'statistic':26s} " + "".join(f"{c:>8d}" for c in classes))
for f in pool:
    sd = d.loc[ben, f].std()
    if not sd or not np.isfinite(sd):
        continue
    b = d.loc[ben, f].median()
    print(f"{f:26s} " + "".join(
        f"{(d.loc[d.label_attackId == c, f].median() - b) / sd:8.2f}" for c in classes))
print("\nbenign medians")
print(d.loc[ben, pool].median().to_string())
