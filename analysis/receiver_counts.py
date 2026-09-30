"""How many receivers a colluding attacker would have to control.

Reads a pooled table written by pooled_consensus.py and prints the distribution
of receivers per pooled unit, the share of thin units, and how many colluders a
given share of a unit's receivers takes at the median and at the 10th
percentile unit.

Usage: receiver_counts.py <pooled.pkl>
"""
import math
import sys

import numpy as np
import pandas as pd


def main():
    path = sys.argv[1]
    print("invocation: " + " ".join(sys.argv))
    n = pd.read_pickle(path)["pool_n_obs"].to_numpy()
    print(f"{len(n):,} pooled units in {path}\n")
    print("receivers per pooled unit")
    for q, name in [(50, "median"), (25, "25th percentile"),
                    (10, "10th percentile")]:
        print(f"  {name:<18s} {np.percentile(n, q):6.0f}")
    print(f"  {'minimum':<18s} {n.min():6.0f}")
    print(f"  {'maximum':<18s} {n.max():6.0f}\n")
    for k in (20, 10):
        print(f"  units with fewer than {k} receivers: "
              f"{100 * (n < k).mean():.1f} percent")
    print(f"  units with 10 or fewer receivers: {100 * (n <= 10).mean():.1f} percent\n")
    med, p10 = np.percentile(n, 50), np.percentile(n, 10)
    print("colluders needed to hold a share of a unit's receivers")
    print("  share        median unit   10th percentile unit")
    for share, name in [(1 / 2, "a half"), (1 / 3, "a third"), (1 / 4, "a quarter")]:
        print(f"  {name:<12s} {math.ceil(share * med):>10d}   {math.ceil(share * p10):>10d}")


if __name__ == "__main__":
    main()
