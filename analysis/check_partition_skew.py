#!/usr/bin/env python3
"""
Does the federated partition actually have label skew?

Run this BEFORE the aggregation panel, every time. If clients all see the same
class mixture then FedAvg is already optimal, FedProx and FedLC have nothing to
correct, and the five methods will land within noise of each other. That is a
statement about the scenario, not about the methods, and reporting it as a
method comparison would be wrong.

Measured on the 1200 m highway, every one of 60 observers had between 3.06 and
3.24 effective classes and class shares agreeing to within a standard deviation
of 0.011. Skew has to be engineered into the deployment; it cannot be assumed.

Usage: check_partition_skew.py <features.csv> [--observer-col key_rxNodeId]
"""
import argparse
import sys
import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--observer-col", default="key_rxNodeId")
    ap.add_argument("--min-spread", type=float, default=0.5,
                    help="required spread in effective classes across clients, "
                         "max minus min")
    ap.add_argument("--min-tv", type=float, default=0.10,
                    help="required mean total variation between each client's "
                         "class distribution and the pooled one. This is the "
                         "load-bearing criterion")
    ap.add_argument("--min-rows", type=int, default=200)
    a = ap.parse_args()

    if a.features.endswith(".pkl"):
        df = pd.read_pickle(a.features)[[a.observer_col, "label_attackId"]]
    else:
        df = pd.read_csv(a.features, usecols=[a.observer_col, "label_attackId"])
    sizes = df.groupby(a.observer_col).size()
    keep = sizes[sizes >= a.min_rows].index
    df = df[df[a.observer_col].isin(keep)]

    p = (df.groupby(a.observer_col).label_attackId
           .value_counts(normalize=True).unstack(fill_value=0))
    print(f"{len(p)} clients, {p.shape[1]} classes\n")
    print("per-client class share:")
    print(p.describe().loc[["mean", "std", "min", "max"]].round(3).to_string())

    ent = -(p * np.log(p.replace(0, np.nan))).sum(axis=1)
    eff = np.exp(ent)
    spread = float(eff.max() - eff.min())
    missing_any = int((p == 0).any(axis=1).sum())
    missing_two = int(((p == 0).sum(axis=1) >= 2).sum())

    print(f"\neffective classes per client: mean {eff.mean():.2f}, "
          f"min {eff.min():.2f}, max {eff.max():.2f}, spread {spread:.2f}")
    print(f"clients missing at least one class: {missing_any} of {len(p)}")
    print(f"clients missing two or more classes: {missing_two}")

    # The strongest single indicator: how far apart the client distributions
    # are. Total variation from the pooled distribution, averaged over clients.
    pooled = df.label_attackId.value_counts(normalize=True).reindex(p.columns).fillna(0)
    tv = (p - pooled).abs().sum(axis=1) / 2.0
    print(f"mean total variation from the pooled distribution: {tv.mean():.3f}")

    # Total variation is the load-bearing measure and it is required. An
    # earlier version passed on EITHER criterion, and a 12 s run with 5 classes
    # and 36 observers duly passed on spread alone while its total variation
    # was 0.023, which is near-uniform. Effective-class spread is noisy on
    # small partitions: with few classes and few observers it exceeds 0.5 by
    # chance. Distance between the client distributions and the pooled one does
    # not have that failure mode.
    ok = tv.mean() >= a.min_tv and spread >= a.min_spread
    print()
    if ok:
        print("PASS: the partition carries real skew, so the panel is meaningful")
        return 0
    print(f"FAIL: partition too uniform (total variation {tv.mean():.3f} against "
          f"a floor of {a.min_tv}, effective-class spread {spread:.2f} against "
          f"{a.min_spread}). Running the aggregation panel here would compare "
          "five methods on a problem none of them is for. Lengthen the road, "
          "localise the attackers, or vary the deployment across clients, then "
          "re-check.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
