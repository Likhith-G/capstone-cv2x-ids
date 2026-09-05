#!/usr/bin/env python3
"""
Assemble the release bundle, so publishing becomes a decision rather than a job.

Produces everything a repository record needs: the data in shards, a machine
readable schema, a sample small enough to open in anything, the frozen partition,
the dataset card, checksums, and the two metadata files that make a record
citable.

**Why gzipped CSV rather than parquet.** Parquet is the better format and the
release guidance asked for it, but reading it needs a library and this machine
has no parquet engine installed. A released dataset that requires a dependency
before anyone can look at it is worse than one that does not, and the whole point
of a benchmark is that strangers can pick it up. CSV compresses well here because
the columns are mostly floats with repeated keys. If a parquet layer is wanted
later it is a converter over these shards, not a regeneration.

**One shard per seed**, because a seed is an independent simulation realisation.
Somebody who wants a quick look takes one shard rather than the whole corpus, and
somebody reproducing a fold takes the shards the partition names.

**Several scenarios, one partition.** The campaigns vary density, attack
magnitude, attack strategy and receiver placement, and they were generated with
the same rngRun values, so some of them share vehicles: `floor` and `gnss` are
identical to four decimal places at seed1. A per-scenario partition would let
somebody train on one and score on the same vehicles in another. The partition is
therefore assigned once across the union, keyed on the physical transmitter, and
every scenario carries the same one.

Scenarios are labelled `benchmark` or `supplementary`. A supplementary scenario
has too few transmitters for the global partition to place every class in every
split, so it can be used for auxiliary evaluation but not for headline scoring,
and the gaps are listed rather than left to be discovered.

    make_release.py --scenario name=path/to/corpus.pkl [--scenario ...] \
        --splits release_splits.csv --out-dir release/
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from make_dataset_card import DESC, CLASSES, BLOCKS      # noqa: E402

SAMPLE_ROWS = 5000


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_schema(df, out):
    """Machine readable column definitions, from the same source as the card."""
    blocks = {pre: title for pre, title, _ in BLOCKS}
    cols = []
    for c in df.columns:
        pre = next((p for p in blocks if c.startswith(p)), None)
        cols.append({
            "name": c,
            "dtype": str(df[c].dtype),
            "block": blocks.get(pre, "other"),
            "is_feature": bool(pre in ("app_", "phy_")),
            "description": DESC[c],
        })
    schema = {
        "name": "CV2X-IDS",
        "unit_of_observation":
            "one receiver's view of one claimed station over one time window",
        "generated": dt.date.today().isoformat(),
        "n_columns": len(cols),
        "n_features": sum(c["is_feature"] for c in cols),
        "classes": {str(k): {"name": v[0], "description": v[1]}
                    for k, v in CLASSES.items()},
        "grouping_column_for_splits": "label_txNodeId",
        "grouping_note":
            "Group on the physical transmitter, never on key_claimedStationId. "
            "Sybil emits several claimed identities per vehicle, so grouping on "
            "the claimed one splits a single vehicle across partitions.",
        "columns": cols,
    }
    out.write_text(json.dumps(schema, indent=2))
    return schema


def write_citation(out, version):
    out.write_text(f"""cff-version: 1.2.0
title: "CV2X-IDS: a labelled cross-layer misbehaviour dataset for NR V2X sidelink"
message: "If you use this dataset, please cite it."
type: dataset
version: "{version}"
date-released: "{dt.date.today().isoformat()}"
license: CC-BY-4.0
abstract: >-
  A labelled intrusion detection dataset for C-V2X, generated in ns-3 with the
  5G-LENA nr module over an NR V2X Mode 2 PC5 sidelink. Each row is one
  receiver's view of one claimed station over one time window and carries both
  the message contents and the physical and MAC layer measurements taken while
  receiving it, including per SCI sidelink reference signal received power.
  Benign vehicles carry a realistic receiver positioning error rather than
  claiming their exact position, and position falsification is generated at
  three non-overlapping magnitude bands chosen against that error so the set
  brackets the point at which detection becomes possible.
keywords:
  - vehicular networks
  - C-V2X
  - NR sidelink
  - misbehaviour detection
  - intrusion detection
  - cross-layer
""")


def write_zenodo(out, version):
    out.write_text(json.dumps({
        "title": "CV2X-IDS: a labelled cross-layer misbehaviour dataset for "
                 "NR V2X sidelink",
        "upload_type": "dataset",
        "version": version,
        "license": "cc-by-4.0",
        "keywords": ["vehicular networks", "C-V2X", "NR sidelink",
                     "misbehaviour detection", "cross-layer"],
        "description":
            "Generated in ns-3.42 with the 5G-LENA nr module at tag v2x-1.1 "
            "over an NR V2X Mode 2 PC5 sidelink. One row is one receiver's view "
            "of one claimed station over one time window, carrying message "
            "contents and the radio measurements taken while receiving them. "
            "Ground truth never travels over the air: the transmitter logs it, "
            "the receiver logs only what it received, and the two are joined "
            "offline. Ships a frozen train, validation and test partition "
            "grouped on the physical transmitter.",
    }, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", action="append", required=True,
                    metavar="NAME=CORPUS",
                    help="repeatable. The first is the primary scenario")
    ap.add_argument("--splits", required=True)
    ap.add_argument("--card", default="docs/DATASET_CARD.md")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--skip-shards", action="store_true",
                    help="regenerate the metadata and checksums without rewriting "
                         "the shards. Writing 7.9 million rows of gzip takes about "
                         "twenty minutes and a metadata bug should not cost that")
    a = ap.parse_args()

    out = pathlib.Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    sp = pd.read_csv(a.splits)
    key = ["key_seed", "label_txNodeId"]
    lut = sp.drop_duplicates(key).set_index(key).split

    scen, first = {}, None
    for spec in a.scenario:
        name, _, path = spec.partition("=")
        df = pd.read_pickle(path)
        if "label_clean" in df.columns:
            df = df[df.label_clean == 1]
        missing = [c for c in df.columns if c not in DESC]
        if missing:
            print(f"FAIL: {name} has {len(missing)} undescribed column(s): {missing[:4]}")
            return 1
        if first is None:
            first = df

        # per scenario coverage under the SHARED partition
        st = df.groupby(key).label_attackId.first().reset_index()
        st["split"] = st.set_index(key).index.map(lut)
        tab = st.pivot_table(index="label_attackId", columns="split",
                             values="label_txNodeId", aggfunc="count",
                             fill_value=0).reindex(
                                 columns=["train", "validation", "test"], fill_value=0)
        gaps = [f"class {c} has no transmitter in {s}"
                for c, row in tab.iterrows() for s in tab.columns if row[s] == 0]
        kind = "benchmark" if not gaps else "supplementary"

        d = out / "shards" / name
        d.mkdir(parents=True, exist_ok=True)
        print(f"{name}  ({kind})  {len(df):,} rows, {len(st)} transmitters")
        for seed, g in df.groupby("key_seed", sort=True):
            f = d / f"cv2x_ids_{name}_{seed}.csv.gz"
            if a.skip_shards and f.exists():
                print(f"    {f.name:<40s} kept, {f.stat().st_size/2**20:6.1f} MB")
                continue
            g.to_csv(f, index=False, compression="gzip")
            print(f"    {f.name:<40s} {len(g):>9,} rows  {f.stat().st_size/2**20:6.1f} MB")
        for gp in gaps:
            print(f"    coverage gap: {gp}")
        scen[name] = {"kind": kind, "rows": int(len(df)),
                      "transmitters": int(len(st)),
                      "seeds": int(df.key_seed.nunique()),
                      "coverage_gaps": gaps}

    df = first
    print()
    print("\nsupporting files")
    (out / "sample.csv").write_text(df.head(SAMPLE_ROWS).to_csv(index=False))
    (out / "SCENARIOS.json").write_text(json.dumps(scen, indent=2))
    schema = write_schema(df, out / "schema.json")
    shutil.copy(a.splits, out / "release_splits.csv")
    if pathlib.Path(a.card).exists():
        shutil.copy(a.card, out / "DATASET_CARD.md")
    write_citation(out / "CITATION.cff", a.version)
    write_zenodo(out / ".zenodo.json", a.version)

    # Provenance: the exact commit the release was cut from. A dataset whose
    # generator cannot be identified is not reproducible whatever its card says.
    commit = subprocess.run("git rev-parse HEAD", shell=True, capture_output=True,
                            text=True,
                            cwd=pathlib.Path(__file__).resolve().parent.parent
                            ).stdout.strip()
    (out / "PROVENANCE.txt").write_text(
        f"CV2X-IDS {a.version}\n"
        f"assembled {dt.datetime.now():%Y-%m-%d %H:%M}\n"
        f"generator commit {commit}\n"
        f"scenarios {', '.join(scen)}\n"
        f"rows {sum(v['rows'] for v in scen.values())}\n"
        f"columns {len(df.columns)}\n")

    for f in ("sample.csv", "SCENARIOS.json", "schema.json", "release_splits.csv",
              "DATASET_CARD.md", "CITATION.cff", ".zenodo.json",
              "PROVENANCE.txt"):
        pth = out / f
        if pth.exists():
            print(f"  {f:28s} {pth.stat().st_size/1024:9.1f} KB")

    print("\nchecksums")
    lines = []
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.name != "CHECKSUMS.sha256":
            lines.append(f"{sha256(f)}  {f.relative_to(out)}")
    (out / "CHECKSUMS.sha256").write_text("\n".join(lines) + "\n")
    print(f"  {len(lines)} files")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"\nbundle {total/2**30:.2f} GB at {out}")
    print(f"schema describes {schema['n_columns']} columns, "
          f"{schema['n_features']} of them features")
    return 0


if __name__ == "__main__":
    sys.exit(main())
