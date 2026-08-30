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
    bins = pd.cut(g.txCbr, [0, .2, .3, .4, .5, .6, .7, 1.01])
    print("\nDCC response, benign CAM interval against measured CBR:")
    print(g.groupby(bins, observed=True).agg(
        n=("gap", "size"), median_ms=("gap", "median")).to_string())

    tx["err"] = np.hypot(tx.claimedX - tx.trueX, tx.claimedY - tx.trueY)
    pos = tx[tx.attackId.isin([1, 2, 3, 4, 11])]
    if len(pos):
        print("\nposition error by class (m):")
        print(pos.groupby("attackId").err.median().round(1).to_string())


if __name__ == "__main__":
    main()
