#!/usr/bin/env python3
"""
The position offset magnitude ladder, measured over every seed of a campaign.

The dataset card, the README and the baseline starter describe the three
constant offset classes as rungs of realised displacement that do not overlap.
Those ranges were measured by check_campaign.py on seed 1 only, three stations a
class, and check_campaign's overlap gate compares only the small and medium
rungs. This measures the same per station statistic over every seed and reports
all three pairs, so the published ranges can be read from a log rather than
carried forward from one seed.

The statistic is check_campaign's: the median displacement among a station's
LYING messages, where a message counts as lying if its claimed position is
further from its true position than the largest benign error seen anywhere in
the campaign. Nothing honest exceeds that, so the median is of lies only and a
sporadic attacker is measured by what it does when it lies.

Class 1 is drawn from a uniform box, x in [-250, 250] m and y in [-30, 30] m, so
its magnitude has no lower bound by construction. Classes 11 and 13 are drawn
from normalised bands. The script says which pairs overlap and which stations
of any class sit inside the benign error, and it does not fail on class 1,
because a box draw overlapping the bands is a property of the design rather
than a defect of the run.

Usage: magnitude_ladder.py <run-dir> seed1 seed2 ...
"""
import argparse
import datetime
import shlex
import sys

import numpy as np
import pandas as pd

LADDER = [(11, "pos_small_offset"), (13, "pos_medium_offset"), (1, "pos_const_offset")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("tags", nargs="+")
    a = ap.parse_args()
    print("invocation: " + " ".join(shlex.quote(s) for s in sys.argv))
    print(f"run at {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")

    frames = []
    for tag in a.tags:
        tx = pd.read_csv(f"{a.run_dir}/tx_{tag}.csv", on_bad_lines="skip",
                         usecols=["txNodeId", "attackId", "trueX", "trueY",
                                  "claimedX", "claimedY"]).dropna()
        tx["seed"] = tag
        frames.append(tx)
    tx = pd.concat(frames, ignore_index=True)
    tx["err"] = np.hypot(tx.claimedX - tx.trueX, tx.claimedY - tx.trueY)

    ben = tx[tx.attackId == 0].err
    if ben.empty:
        sys.exit("no benign messages; cannot set the lying threshold")
    floor, p95 = float(ben.max()), float(ben.quantile(0.95))
    print(f"{len(a.tags)} seeds, {len(tx):,} messages")
    print(f"benign error: median {ben.median():.2f} m, p95 {p95:.2f} m, "
          f"max {floor:.2f} m. A message counts as lying above {floor:.2f} m.\n")

    bands, per = {}, {}
    print(f"{'class':20s} {'stations':>8s} {'lied':>5s} {'min':>7s} {'p25':>7s} "
          f"{'median':>7s} {'p75':>7s} {'max':>7s}")
    for cls, name in LADDER:
        allc = tx[tx.attackId == cls]
        lying = allc[allc.err > floor]
        if lying.empty:
            print(f"{cls:>3d} {name:16s} {allc.groupby(['seed', 'txNodeId']).ngroups:8d}"
                  f"     0   no lying message")
            continue
        s = lying.groupby(["seed", "txNodeId"]).err.median()
        per[cls] = s
        n_all = allc.groupby(["seed", "txNodeId"]).ngroups
        bands[cls] = (float(s.min()), float(s.max()))
        print(f"{cls:>3d} {name:16s} {n_all:8d} {len(s):5d} {s.min():7.1f} "
              f"{s.quantile(.25):7.1f} {s.median():7.1f} {s.quantile(.75):7.1f} "
              f"{s.max():7.1f}")

    print("\noverlap between rungs, by realised per station median when lying:")
    for i, (c1, n1) in enumerate(LADDER):
        for c2, n2 in LADDER[i + 1:]:
            if c1 not in bands or c2 not in bands:
                continue
            lo1, hi1 = bands[c1]
            lo2, hi2 = bands[c2]
            over = max(lo1, lo2) <= min(hi1, hi2)
            print(f"  {n1:18s} {lo1:6.1f} to {hi1:6.1f} m   {n2:18s} "
                  f"{lo2:6.1f} to {hi2:6.1f} m   "
                  f"{'OVERLAP' if over else 'separate'}")

    # A station whose lies are the size of honest error cannot be told apart by
    # position at any receiver count, and its class score should be read that way.
    print(f"\nposition attackers whose median lie is inside the benign p95 "
          f"({p95:.2f} m): ", end="")
    inside = [(c, k) for c, s in per.items() for k, v in s.items() if v <= p95]
    print(len(inside) if not inside else
          ", ".join(f"class {c} {k[0]} node {k[1]}" for c, k in inside))

    # The lying-conditioned statistic is right for a sporadic attacker and wrong
    # for a rung whose size is close to the benign maximum: a small-offset station
    # whose lie is under that maximum never counts as lying and drops out of the
    # table above entirely. A continuous attacker lies in every message, so for a
    # continuous campaign the median over ALL of a station's messages is the
    # measure, and it keeps every station.
    print("\nper station median over ALL messages, the measure for a campaign whose "
          "attackers lie continuously:")
    print(f"{'class':20s} {'stations':>8s} {'min':>7s} {'p25':>7s} {'median':>7s} "
          f"{'p75':>7s} {'max':>7s}  inside benign p95")
    allmed = {}
    for cls, name in LADDER:
        s = tx[tx.attackId == cls].groupby(["seed", "txNodeId"]).err.median()
        if s.empty:
            continue
        allmed[cls] = s
        print(f"{cls:>3d} {name:16s} {len(s):8d} {s.min():7.1f} {s.quantile(.25):7.1f} "
              f"{s.median():7.1f} {s.quantile(.75):7.1f} {s.max():7.1f}  "
              f"{int((s <= p95).sum())}")
    for i, (c1, n1) in enumerate(LADDER):
        for c2, n2 in LADDER[i + 1:]:
            if c1 in allmed and c2 in allmed:
                a1, a2 = allmed[c1], allmed[c2]
                over = max(a1.min(), a2.min()) <= min(a1.max(), a2.max())
                print(f"  {n1:18s} {a1.min():6.1f} to {a1.max():6.1f} m   {n2:18s} "
                      f"{a2.min():6.1f} to {a2.max():6.1f} m   "
                      f"{'OVERLAP' if over else 'separate'}")

    if 1 in per:
        s = per[1]
        print(f"\nclass 1 is a uniform box draw with no lower bound: "
              f"{int((s < 71).sum())} of {len(s)} stations lie by less than 71 m, "
              f"{int((s < 30).sum())} by less than 30 m.")


if __name__ == "__main__":
    main()
