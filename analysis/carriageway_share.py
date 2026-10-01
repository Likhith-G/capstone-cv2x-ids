"""How many honest claims a map check at a given carriageway half-width rejects.

A road-bounded estimator and a map check on the claim both use a half-width
around the centreline. Honest claims carry positioning error, so some benign
station-windows sit outside a narrow band even though the vehicle is in its
lane. This prints that share at several widths, per window the way the pooled
geometry averages positions, and per message.

Usage: carriageway_share.py <run-dir> seed1 seed2 ... [--widths 12 15 18]
"""
import argparse
import sys

import numpy as np
import pandas as pd

from pooled_consensus import WRAP_SPAN_M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("tags", nargs="+")
    ap.add_argument("--widths", type=float, nargs="+", default=[12, 15, 18])
    ap.add_argument("--window-ms", type=float, default=1000.0)
    a = ap.parse_args()
    print("invocation: " + " ".join(sys.argv))

    parts = []
    for t in a.tags:
        tx = pd.read_csv(f"{a.run_dir}/tx_{t}.csv", on_bad_lines="skip",
                         usecols=["txTimeMs", "claimedStationId", "trueY",
                                  "claimedX", "claimedY", "attackId"]).dropna()
        st = pd.read_csv(f"{a.run_dir}/stations_{t}.csv")
        veh = set(st.loc[st.role == "vehicle", "stationId"])
        tx = tx[tx.claimedStationId.isin(veh)].copy()
        tx["seed"] = t
        tx["window"] = (tx.txTimeMs // a.window_ms).astype(int)
        parts.append(tx)
    alltx = pd.concat(parts, ignore_index=True)
    tx = alltx[alltx.attackId == 0]

    g = tx.groupby(["seed", "claimedStationId", "window"])
    win = g[["claimedY", "trueY"]].mean()
    keep = (g.claimedX.max() - g.claimedX.min()) <= WRAP_SPAN_M
    win = win[keep]
    print(f"{len(tx):,} benign vehicle messages, {len(win):,} station-windows "
          f"({int((~keep).sum())} wrapped windows dropped), seeds {' '.join(a.tags)}")
    print(f"true lateral position, station-window mean: max |y| "
          f"{win.trueY.abs().max():.2f} m")
    print(f"claimed lateral position, station-window mean: max |y| "
          f"{win.claimedY.abs().max():.2f} m\n")
    print("  half-width   station-windows outside   messages outside")
    for w in a.widths:
        sw = float((win.claimedY.abs() > w).mean())
        ms = float((tx.claimedY.abs() > w).mean())
        print(f"  +/-{w:5.1f} m          {100 * sw:6.2f} percent        "
              f"{100 * ms:6.2f} percent")

    # The same share for every attack class. A claim off the carriageway is
    # rejected by a map check with no radio evidence, so a class whose claims
    # often leave the road is partly detectable without any of this pipeline,
    # and a radio result on it should be read against that.
    ga = alltx.groupby(["seed", "claimedStationId", "window"])
    wa = ga[["claimedY", "attackId"]].agg({"claimedY": "mean", "attackId": "first"})
    wa = wa[(ga.claimedX.max() - ga.claimedX.min()) <= WRAP_SPAN_M]
    print("\nstation-windows whose mean claimed position is off the carriageway, "
          "per class")
    print("  class   windows  " + "  ".join(f"> {w:4.1f} m" for w in a.widths))
    for c, grp in wa.groupby("attackId"):
        cells = "  ".join(f"{100 * (grp.claimedY.abs() > w).mean():7.2f}%"
                          for w in a.widths)
        print(f"  {int(c):>5d}  {len(grp):>8,}  {cells}")


if __name__ == "__main__":
    main()
