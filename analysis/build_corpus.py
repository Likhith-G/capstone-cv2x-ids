#!/usr/bin/env python3
"""
Combine several seeds into one corpus.

Seeds are independent replicates: different fleet, different attacker
assignment, different channel draws. Station ids are namespaced by seed so
that a grouped split never puts the same physical station on both sides, and
so that each attack class has enough distinct stations for grouped
cross-validation to mean anything. A single 60-vehicle run gave two to five
stations for the rarer classes, which put whole classes at zero support in a
test fold.
"""
import argparse
import pandas as pd
from build_features import build_features, attach_labels, feature_columns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("tags", nargs="+", help="e.g. seed1 seed2 seed3")
    ap.add_argument("--window-ms", type=float, default=1000.0)
    ap.add_argument("--max-time-ms", type=float, default=None)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    frames = []
    for i, tag in enumerate(a.tags):
        agg = build_features(a.run_dir, tag, window_ms=a.window_ms,
                             max_time_ms=a.max_time_ms)
        out = attach_labels(agg, a.run_dir, tag, window_ms=a.window_ms,
                            max_time_ms=a.max_time_ms)
        # Namespace the station identifiers so grouping stays honest.
        off = (i + 1) * 100000
        out["key_rxNodeId"] += off
        out["label_txNodeId"] += off
        out["key_seed"] = tag
        frames.append(out)
        print(f"{tag}: {len(out)} windows, "
              f"{out.label_txNodeId.nunique()} stations")

    df = pd.concat(frames, ignore_index=True)
    feats = feature_columns(df)
    assert not any(c.startswith(("key_", "label_")) for c in feats)
    df.to_csv(a.out, index=False)
    # Write the pickle here too, keeping EVERY column. Reading the corpus back
    # from CSV costs a minute and silently retypes the key columns, so the
    # downstream scripts use the pickle. It must therefore carry key_window and
    # key_claimedStationId: anything that reasons about one station seen by
    # several observers at the same instant needs them, and an earlier pickle
    # built by hand dropped them.
    pkl = a.out[:-4] + ".pkl" if a.out.endswith(".csv") else a.out + ".pkl"
    df.to_pickle(pkl)

    print(f"\ncorpus: {len(df)} windows, {len(feats)} features, "
          f"{df.label_txNodeId.nunique()} stations -> {a.out} and {pkl}")
    print("\nstations per class:")
    print(df.groupby("label_attackId").label_txNodeId.nunique().to_string())
    print("\nwindows per class:")
    print(df.label_attackId.value_counts().to_string())


if __name__ == "__main__":
    main()
