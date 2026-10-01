#!/usr/bin/env python3
"""
Combine per-seed corpora that were built separately.

Station identifiers repeat across seeds, so every corpus namespaces them into a
per-seed block of 100000. A dense campaign cannot be built in one call on this
machine: one 240-vehicle seed is already several gigabytes of tables. Each seed
is therefore built alone and merged here, and the merge has to leave every seed
in the block that `pooled_consensus.seed_offset` gives it, because every script
that re-derives geometry joins on that block.

The block used to be positional. A seed built alone always landed at 100000 and
this script added its index. Since 19 Sep the builder keys the block on the seed
label itself, so a lone seed K already sits at K x 100000, and adding the index
on top put seed K at (2K - 1) x 100000. Nothing failed: the identifiers stayed
unique, and every later geometry join silently kept seed 1 alone.

So this no longer adds anything. It reads the block each part is in, whichever
rule built it, and moves the part to the block its seed label calls for. Parts
built before and after the change merge alike. It also refuses two parts
carrying the same seed label, because the likeliest way to get one is to merge
the same seed from two campaigns, and campaigns share their vehicles seed by
seed (see the dataset card): renumbering them apart would put one physical
vehicle on both sides of a grouped fold.
"""
import argparse
import pandas as pd
from pooled_consensus import seed_offset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+", help="per-seed corpus pickles, in order")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    frames, tags = [], []
    for i, path in enumerate(a.parts):
        d = pd.read_pickle(path)
        seeds = d.key_seed.unique()
        assert len(seeds) == 1, f"{path} holds {len(seeds)} seeds; merge one seed per part"
        tag = seeds[0]
        assert tag not in tags, (
            f"{path} repeats seed {tag}. Two parts with one seed label are almost "
            f"always the same seed from two campaigns, which share their vehicles, "
            f"so they must never be merged into one grouped corpus")
        tags.append(tag)
        blocks = set((d.key_rxNodeId // 100000).unique()) | set((d.label_txNodeId // 100000).unique())
        assert len(blocks) == 1, f"{path} spans id blocks {sorted(blocks)}; cannot rebase it"
        shift = seed_offset(tag, i) - blocks.pop() * 100000
        d["key_rxNodeId"] += shift
        d["label_txNodeId"] += shift
        frames.append(d)
        print(f"{path}: {len(d)} windows, {d.label_txNodeId.nunique()} stations, "
              f"seed tag {d.key_seed.iloc[0]}")

    seen = {}
    for d in frames:
        tag = d.key_seed.iloc[0]
        ids = set(d.label_txNodeId.unique())
        for other, prev in seen.items():
            clash = ids & prev
            assert not clash, (f"{tag} and {other} share {len(clash)} station ids; "
                               "the grouped split would be invalid")
        seen[tag] = ids

    df = pd.concat(frames, ignore_index=True)
    df.to_pickle(a.out)
    print(f"\nmerged: {len(df)} windows, {df.label_txNodeId.nunique()} stations, "
          f"{df.key_seed.nunique()} seeds -> {a.out}")
    print("\nstations per class:")
    print(df.groupby("label_attackId").label_txNodeId.nunique().to_string())
    print("\nwindows per class:")
    print(df.label_attackId.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
