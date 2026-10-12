#!/usr/bin/env python3
"""
Does federation save bandwidth? Part A's argument, measured.

Part A argued that federating avoids streaming raw traffic to a server. The
two costs scale differently. Central training needs every region's pooled
records uploaded once: that cost grows with how much traffic the training set
covers. Federated training sends model updates: that cost grows with the number
of rounds and the model size, and not at all with the data. So there is a
break-even training set, measured here in minutes of traffic per region.

Both sides are counted from the panel's own clients:
  raw side       each region's pooled records, every feature as float32, per
                 minute of simulated traffic (one seed is one minute)
  federated side the MLP's weights as float32, down and up once per round a
                 client is sampled; sampled every round at most, half the
                 rounds on average at the panel's participation of 0.5;
                 secure aggregation sends the upload as int64 plus one 32 byte
                 public key per other sampled client

Sizes are lower bounds on both sides: no protocol overhead, no compression,
labels not counted (federated training needs them locally as well).

Usage: fed_bandwidth.py pooled_regions.pkl --observer-col key_region
       [--rounds 200] [--participation 0.5] [--seconds-per-seed 60]
"""
import argparse

import numpy as np
import pandas as pd

from federated import MLP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--observer-col", default="key_region")
    ap.add_argument("--rounds", type=int, default=200)
    ap.add_argument("--participation", type=float, default=0.5)
    ap.add_argument("--seconds-per-seed", type=float, default=60.0)
    a = ap.parse_args()

    df = pd.read_pickle(a.features)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    feats = [c for c in df.columns if c.startswith(("app_", "phy_", "pool_"))]
    n_classes = df.label_attackId.nunique()
    rows = df.groupby(["key_seed", a.observer_col]).size()
    clients = len(rows)
    minutes = a.seconds_per_seed / 60.0

    raw_per_min = rows / minutes * len(feats) * 4
    med_raw = float(raw_per_min.median())
    print(f"{clients} region clients, {len(feats)} features, {n_classes} classes")
    print(f"pooled records per region per minute of traffic: median "
          f"{rows.median() / minutes:,.0f}, 10th percentile "
          f"{rows.quantile(0.1) / minutes:,.0f}, 90th {rows.quantile(0.9) / minutes:,.0f}")
    print(f"raw upload per region per minute of traffic: median {med_raw / 1e6:.3f} MB "
          f"(10th percentile {raw_per_min.quantile(0.1) / 1e6:.3f}, 90th "
          f"{raw_per_min.quantile(0.9) / 1e6:.3f})")

    w = sum(p.numel() for p in MLP(len(feats), n_classes).parameters())
    per_round = 2 * 4 * w                      # download and upload, float32
    sampled = max(1, int(a.participation * clients))
    per_round_sa = 4 * w + 8 * w + 32 * (sampled - 1)
    fed_max = a.rounds * per_round
    fed_mean = a.rounds * a.participation * per_round
    sa_max = a.rounds * per_round_sa
    print(f"\nmodel: {w} weights; per round a sampled client moves "
          f"{per_round:,} bytes, {per_round_sa:,} under secure aggregation "
          f"({sampled} sampled)")
    print(f"federated training, {a.rounds} rounds: {fed_max / 1e6:.2f} MB if sampled "
          f"every round, {fed_mean / 1e6:.2f} MB on average, "
          f"{sa_max / 1e6:.2f} MB under secure aggregation if sampled every round")

    print(f"\nbreak-even training set, minutes of traffic per region at the median "
          f"region (federated cheaper above it):")
    print(f"  plain, sampled every round        {fed_max / med_raw:6.1f} min")
    print(f"  plain, average participation      {fed_mean / med_raw:6.1f} min")
    print(f"  secure aggregation, every round   {sa_max / med_raw:6.1f} min")
    print(f"\nthe panel's own training set is {minutes:.0f} minute(s) of traffic per "
          f"region, so on it central upload is the cheaper of the two by a factor "
          f"of {fed_mean / med_raw / minutes:.1f} at average participation")
    print("\nSizes are lower bounds: float32, no protocol overhead, no compression,"
          "\nlabels not counted. Key agreement is counted as one 32 byte key per peer.")


if __name__ == "__main__":
    main()
