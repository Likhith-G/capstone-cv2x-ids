#!/usr/bin/env python3
"""
What pooling would put on the air, worked out from the run rather than measured.

The pooled detector needs every receiver's measurements of a station in one
place each second. Nothing in the simulation sends them anywhere: the pooled
table is assembled offline. This counts what sending them would cost, from
quantities the run fixes, and sets it beside the safety traffic the same
stations already carry, so the report can say how large the missing link is
without claiming to have simulated it.

Two report sizes bracket the cost. The full report carries the receiver's 50
window features, which is what the pooled detector as measured consumes. The
minimal report carries only what the consensus block needs, one received power
and the receiver's position. Both add the three identifiers a report needs.

    sharing_cost.py RUN_DIR --tags seed1 ... seed8
"""
import argparse
import pathlib

import numpy as np
import pandas as pd

# Fixed by the scenario source, not measured.
ITS_HEADER = 75     # its-message-header.cc, GetSerializedSize
ITS_PAYLOAD = 200   # its-station-app.cc, PacketSize default
FLOAT = 4           # one float32 value
IDS = 3 * 4         # receiver, claimed station and window, 32 bits each
POSITION = 2 * FLOAT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--pooled", default="pooled_road.pkl")
    ap.add_argument("--regions", default="pooled_regions.pkl")
    a = ap.parse_args()
    run = pathlib.Path(a.run_dir).expanduser()

    msgs = windows = 0
    cbr, rx = [], []
    for tag in a.tags:
        tx = pd.read_csv(run / f"tx_{tag}.csv", usecols=["txTimeMs", "txCbr"],
                         on_bad_lines="skip").dropna()
        msgs += len(tx)
        windows += (tx.txTimeMs // 1000).nunique()
        cbr.append(tx.txCbr.mean())
        st = pd.read_csv(run / f"stations_{tag}.csv")
        rx.append(len(st))
    pl = pd.read_pickle(run / a.pooled)
    feats = [c for c in pl.columns if c.startswith("pm_")]
    reports = float(pl.pool_n_obs.sum())
    rg = pd.read_pickle(run / a.regions)
    per = rg.groupby(["key_seed", "key_claimedStationId", "key_window"]).size()

    print(f"{len(a.tags)} seeds, {windows} one-second windows in all")
    print(f"receivers per seed: median {np.median(rx):.0f} "
          f"(vehicles and roadside units)")
    print(f"safety messages: {msgs:,}, {msgs / windows:.0f} a second on the "
          f"road, {ITS_HEADER + ITS_PAYLOAD} bytes each")
    safety = msgs / windows * (ITS_HEADER + ITS_PAYLOAD) * 8 / 1e6
    print(f"  safety traffic {safety:.2f} Mbit/s; mean channel busy ratio per "
          f"seed {min(cbr):.3f} to {max(cbr):.3f}")
    rate = reports / windows
    print(f"\nreports the pooled table consumed: {reports:,.0f}, "
          f"{rate:,.0f} a second on the road, "
          f"{rate / np.median(rx):.1f} per receiver a second")

    full = len(feats) * FLOAT + POSITION + IDS
    minimal = FLOAT + POSITION + IDS
    for name, size in (("full report", full), ("minimal report", minimal)):
        mbit = rate * size * 8 / 1e6
        print(f"  {name}: {size} bytes, {mbit:.2f} Mbit/s on the road, "
              f"{mbit / safety:.2f} times the safety traffic")
    print(f"  the full report carries the {len(feats)} pooled feature means; "
          f"the minimal one only received power and position")

    print(f"\nregions that heard a station in one window: median {per.median():.0f}, "
          f"max {per.max()}")
    print("  pooling inside a region needs one hop, receiver to its roadside "
          "unit. Pooling\n  across the road, as the reported floor does, also "
          "needs every region's reports\n  for a station gathered in one "
          "place, over a link the scenario does not model.")
    print("\nNothing here is simulated. The sizes assume float32 values and "
          "no protocol\noverhead, so they are a lower bound on the bytes.")
    print("SHARING DONE")


if __name__ == "__main__":
    main()
