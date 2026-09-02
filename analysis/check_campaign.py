#!/usr/bin/env python3
"""
Sanity check one seed of a campaign before spending hours on the rest.

A campaign takes hours and a misconfiguration is cheap to make and expensive to
discover afterwards. This reads only the small transmit table and the station
register, so it costs seconds, and it checks the things that have actually gone
wrong before:

  station roles       vehicles and roadside units both present, since a road
                      with no roadside units cannot support anything federated
  attack coverage     every class in the requested mix actually got stations.
                      Random assignment with a few stations per class does
                      leave a class empty in a given seed
  message mix         CAM dominant over CPM. A CPM trigger updated on check
                      rather than on send once made CPM the majority message
  congestion control  the benign message interval rises with the channel busy
                      ratio the transmitter measured. A flat staircase means
                      either the scenario is uncongested or the busy ratio is
                      being normalised against the wrong denominator
  attack magnitude    the injected position error is the size intended

Usage: check_campaign.py <run-dir> <tag>
"""
import argparse
import sys

import numpy as np
import pandas as pd

MSG = {1: "DENM", 2: "CAM", 14: "CPM", 16: "VAM", 20: "MCM"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("tag")
    ap.add_argument("--expect-classes", default=None,
                    help="comma separated attack ids the run was asked for")
    a = ap.parse_args()

    # Collected rather than printed and forgotten. This script is the gate in
    # front of a long analysis chain, so a condition worth warning about is a
    # condition worth a non-zero exit.
    problems = []

    tx = pd.read_csv(f"{a.run_dir}/tx_{a.tag}.csv",
                     on_bad_lines="skip").dropna(subset=["attackId"])
    st = pd.read_csv(f"{a.run_dir}/stations_{a.tag}.csv")

    print(f"roles: {st.role.value_counts().to_dict()}")
    print(f"{len(tx)} transmissions from {tx.txNodeId.nunique()} stations, "
          f"{tx.txTimeMs.min():.0f} to {tx.txTimeMs.max():.0f} ms")
    if "rsu" not in set(st.role):
        print("  WARNING: no roadside units, this run cannot support federation")

    got = set(st[st.attackId > 0].attackId.astype(int))
    counts = st[st.attackId > 0].groupby("attackId").size()
    print(f"\nattack classes with stations: {sorted(got)}")
    print(counts.to_string())
    if a.expect_classes:
        want = {int(v) for v in a.expect_classes.split(",")}
        missing = want - got
        if missing:
            print(f"  NOTE: {sorted(missing)} got no stations in this seed. "
                  f"With a few stations per class this happens; it only matters "
                  f"if the class is still empty once every seed is merged.")

    mix = tx.msgType.map(MSG).value_counts()
    print(f"\nmessage mix:\n{mix.to_string()}")
    if "CAM" in mix and mix.get("CPM", 0) > mix["CAM"]:
        print("  WARNING: CPM outnumbers CAM, check the CPM trigger")
        problems.append("CPM outnumbers CAM")

    c = tx.txCbr
    print(f"\nCBR mean {c.mean():.3f} p95 {c.quantile(.95):.3f} max {c.max():.3f}")

    t = tx[(tx.attackId == 0) & (tx.msgType == 2)].sort_values(
        ["txNodeId", "txTimeMs"]).copy()
    t["gap"] = t.groupby("txNodeId").txTimeMs.diff()
    g = t.dropna(subset=["gap"])
    print(f"benign CAM: median {g.gap.median():.0f} ms, mean {g.gap.mean():.0f}, "
          f"{1000 / g.gap.mean():.2f} Hz, {g.gap.nunique()} distinct intervals")
    if g.gap.nunique() < 4:
        print("  WARNING: too few distinct intervals, triggering may be deterministic")
        problems.append("benign CAM triggering looks deterministic")
    bins = pd.cut(g.txCbr, [0, .2, .3, .4, .5, .6, .7, 1.01])
    print("\nDCC response, benign CAM interval against measured CBR:")
    print(g.groupby(bins, observed=True).agg(
        n=("gap", "size"), median_ms=("gap", "median")).to_string())

    bands = {}
    tx["err"] = np.hypot(tx.claimedX - tx.trueX, tx.claimedY - tx.trueY)
    pos = tx[tx.attackId.isin([1, 2, 3, 4, 11, 13])]
    if len(pos):
        print("\nposition error by class (m):")
        print(pos.groupby("attackId").err.median().round(1).to_string())

    # Benign positioning error. This is the noise floor every position attack
    # has to clear, so it is checked on the first seed rather than discovered
    # after eight. The target is a median near 3 to 5 m with rare excursions to
    # 10 to 15 m, and no message at exactly zero.
    ben = tx[tx.attackId == 0]
    if len(ben):
        e = ben.err
        print(f"\nbenign positioning error over {len(ben):,} messages from "
              f"{ben.txNodeId.nunique()} stations:")
        print(f"  median {e.median():.2f} m   p95 {e.quantile(.95):.2f} m   "
              f"max {e.max():.2f} m   exactly zero: {(e < 1e-9).sum()}")
        if (e < 1e-9).all():
            print("  WARNING: every benign claim is exact. The GnssError "
                  "attribute is off and the corpus will overstate detection")
            problems.append("benign positioning error is identically zero")
        # Per station, because the error is a quasi-constant bias. A station
        # that drew an initial error near zero keeps a near-zero error for the
        # whole run, which is faithful to the model and worth seeing: if a
        # small-offset result turns out to rest on a handful of unusually well
        # positioned benign stations, this is where that shows up.
        per = ben.groupby("txNodeId").err.mean()
        print(f"  per station mean error: min {per.min():.2f} "
              f"p25 {per.quantile(.25):.2f} median {per.median():.2f} "
              f"max {per.max():.2f} m")
        print(f"  stations under 1 m of mean error: "
              f"{(per < 1.0).sum()} of {len(per)}")
        sp = (ben.claimedSpeed - ben.trueSpeed).abs()
        hd = np.degrees((ben.claimedHeading - ben.trueHeading).abs())
        print(f"  speed error median {sp.median():.4f} m/s p95 "
              f"{sp.quantile(.95):.4f}")
        print(f"  heading error median {hd.median():.3f} deg max {hd.max():.2f}")

        # The magnitude ladder, stated against the noise floor rather than in
        # absolute metres, because a displacement only means something relative
        # to the error a benign receiver already has.
        p95 = e.quantile(.95)
        for cls, label in [(11, "pos_small_offset"), (13, "pos_medium_offset"),
                           (1, "pos_const_offset")]:
            d = tx[tx.attackId == cls]
            if len(d):
                per_att = d.groupby("txNodeId").err.median()
                below = (per_att < p95).sum()
                print(f"  {label:18s} per station median offset "
                      f"{per_att.min():6.1f} to {per_att.max():6.1f} m, "
                      f"{below} of {len(per_att)} stations inside the benign "
                      f"95th percentile")
                bands[cls] = (per_att.min(), per_att.max())

        # The ladder has to separate or it is not a ladder. Overlapping bands
        # mean a magnitude comparison is comparing two mixtures of the same
        # distances, which is the defect that cost one restart of this
        # campaign, so it is now checked rather than eyeballed.
        if 11 in bands and 13 in bands and bands[11][1] > bands[13][0]:
            print(f"  WARNING: the small and medium offset bands overlap, "
                  f"{bands[11][1]:.1f} m against {bands[13][0]:.1f} m")
            problems.append("position offset magnitude bands overlap")

    if problems:
        print(f"\nFAILED with {len(problems)} problem(s):")
        for pr in problems:
            print(f"  - {pr}")
        print("Fix the campaign configuration before spending the analysis "
              "chain on it.")
        return 1
    print("\nseed check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
