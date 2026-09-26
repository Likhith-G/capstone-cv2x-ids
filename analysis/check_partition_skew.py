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

The gate has to measure the partition the panel trains on. federated.py drops
impure windows, samples, restricts to one observer role and trains on seventy
percent of the observers; --observer-role, --sample and --training-clients
reproduce those steps in the same order and with the same seeds. Without them
the gate measures every observer in the corpus, which is a different partition.

Usage: check_partition_skew.py <features.csv> [--observer-col key_rxNodeId]
       [--observer-role rsu --sample 200000 --training-clients]
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
    ap.add_argument("--observer-role", default=None,
                    help="as federated.py: keep only observers of this role")
    ap.add_argument("--sample", type=int, default=None,
                    help="as federated.py: sample this many rows, same seed")
    ap.add_argument("--training-clients", action="store_true",
                    help="measure only the seventy percent of observers "
                         "federated.py makes training clients")
    a = ap.parse_args()

    cols = [a.observer_col, "label_attackId", "label_clean", "key_observer_role"]
    if a.features.endswith(".pkl"):
        df = pd.read_pickle(a.features)
        df = df[[c for c in cols if c in df.columns]]
    else:
        df = pd.read_csv(a.features, usecols=lambda c: c in cols)
    # The same steps as federated.py, in the same order, so the gate sees the
    # rows the panel sees.
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0)
    if a.observer_role:
        if "key_observer_role" not in df.columns:
            sys.exit("--observer-role given but the table has no key_observer_role")
        df = df[df.key_observer_role == a.observer_role]
    if a.training_clients:
        uniq = pd.unique(df[a.observer_col].values)
        np.random.RandomState(0).shuffle(uniq)
        df = df[df[a.observer_col].isin(set(uniq[:int(0.7 * len(uniq))]))]
    print(f"partition: role {a.observer_role or 'any'}, sample "
          f"{a.sample or 'none'}, "
          f"{'training clients only' if a.training_clients else 'every observer'}")
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
