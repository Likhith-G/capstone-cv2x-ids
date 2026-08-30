#!/usr/bin/env python3
"""
Combine per-seed corpora that were built separately.

`build_corpus.py` namespaces station identifiers by the seed's position in the
tag list it was given, so building six seeds in one call is what normally keeps
a grouped split honest. A dense campaign cannot be built that way on this
machine: one 240-vehicle seed is already several gigabytes of tables and three
in one process runs out of memory or wall clock. Each seed is therefore built
alone, which gives every one of them the SAME offset of 100000, and merging
them naively would put three different physical stations under one identifier
and quietly break every grouped fold.

This applies the offset the combined build would have applied, and asserts
afterwards that no identifier is shared between seeds.
"""
import argparse
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+", help="per-seed corpus pickles, in order")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    frames = []
    for i, path in enumerate(a.parts):
        d = pd.read_pickle(path)
        d["key_rxNodeId"] += i * 100000
        d["label_txNodeId"] += i * 100000
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
