"""Why a Sybil's pooled free-fit residual is high: channels per identity.

A Sybil sends every identity from one radio at one position, so its pooled
measurements should fit a single position as well as a benign station's do.
Yet `pool_free_rmse` sits about two benign standard deviations high on the
Sybil class. The lead tested here: power is attributed per claimed identity, a
Sybil splits its control channels across its identities, so each identity's
mean power at a receiver averages fewer channels and is noisier.

Prints, from a pooled table written by pooled_consensus.py: per class, the
median free-fit residual and the median channels per receiver behind it; the
residual against channel count for benign and Sybil in matched bins; and how
much of the Sybil excess a benign fit of residual on log channel count
predicts from the Sybil's own counts.

Usage: sybil_residual.py <pooled.pkl>
"""
import sys

import numpy as np
import pandas as pd

SYBIL = 6


def main():
    path = sys.argv[1]
    print("invocation: " + " ".join(sys.argv))
    p = pd.read_pickle(path)
    p = p[p.pm_phy_rsrp_count > 0].copy()
    b = p[p.label_attackId == 0]
    s = p[p.label_attackId == SYBIL]
    med, sd = b.pool_free_rmse.median(), b.pool_free_rmse.std()
    print(f"{len(p):,} pooled units; benign free-fit residual median {med:.3f} dB, "
          f"sd {sd:.3f} dB\n")

    g = p.groupby("label_attackId").agg(
        units=("pool_free_rmse", "size"),
        free_rmse=("pool_free_rmse", "median"),
        channels=("pm_phy_rsrp_count", "median"),
        receivers=("pool_n_obs", "median"))
    print("per class, medians: free-fit residual (dB), channels per receiver "
          "per window, receivers")
    print(g.round(3).to_string(), "\n")

    bins = [0, 2.5, 4, 6, 10, np.inf]
    p["channels"] = pd.cut(p.pm_phy_rsrp_count, bins)
    t = (p[p.label_attackId.isin([0, SYBIL])]
         .groupby(["channels", "label_attackId"], observed=True)
         .pool_free_rmse.agg(["size", "median"]).unstack())
    print("free-fit residual median in matched channel bins, benign (0) "
          "against Sybil (6)")
    print(t.round(3).to_string(), "\n")

    x = np.log(b.pm_phy_rsrp_count.values)
    slope, icpt = np.polyfit(x, b.pool_free_rmse.values, 1)
    pred = icpt + slope * np.log(s.pm_phy_rsrp_count.values)
    excess = s.pool_free_rmse.median() - med
    explained = np.median(pred) - med
    print(f"benign fit: free_rmse = {icpt:.3f} {slope:+.3f} x ln(channels), "
          f"correlation {np.corrcoef(x, b.pool_free_rmse)[0, 1]:+.3f}")
    print(f"Sybil excess over the benign median: {excess:.3f} dB "
          f"({excess / sd:.2f} benign sd)")
    print(f"  predicted by the benign fit at the Sybil's own channel counts: "
          f"{explained:.3f} dB, {100 * explained / excess:.0f} percent of it")
    print(f"  left after channel count: {excess - explained:.3f} dB "
          f"({(excess - explained) / sd:.2f} benign sd)")


if __name__ == "__main__":
    main()
