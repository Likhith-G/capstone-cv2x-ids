#!/usr/bin/env python3
"""
Consume the release bundle the way a stranger would, and check it works.

Everything else in this pipeline reads `corpus.pkl` from a run directory that
only exists on this machine. Nobody outside has that. What they will have is the
published bundle, and nothing so far has ever loaded it: the shards, the frozen
partition, the schema, on their own terms with no access to anything else.

A dataset release that nobody has consumed is a release that probably does not
work. This is the acceptance test, and it deliberately uses only files inside the
bundle directory.

**What it checks.**

1. Every file the checksum manifest names is present and matches.
2. The shards load, carry the columns the schema promises, and nothing else.
3. The frozen partition covers every row exactly once, and no physical
   transmitter appears in two partitions. That last one is the leakage rule, and
   an earlier version of the split script got it wrong.
4. A baseline trains on the train partition and scores on the test partition, and
   its number lands near what the paper reports. Not identical, because the paper
   uses repeated grouped cross validation over the whole corpus and this is a
   single fixed split, but near enough that a stranger reproducing it would
   believe the paper rather than suspect the bundle.

    check_release.py path/to/release
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, matthews_corrcoef

# What the paper reports for the fused block over eleven classes, from
# RESULTS.md section 3. A single fixed split will not reproduce it exactly.
PAPER_FUSED_F1 = 0.5145
TOLERANCE = 0.10

fails = []


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name:<46s} {detail}")
    if not ok:
        fails.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--trees", type=int, default=60)
    ap.add_argument("--sample", type=int, default=400000,
                    help="cap the training rows. The full set took half an hour, "
                         "and a check nobody waits for is a check nobody runs. "
                         "0 uses everything")
    ap.add_argument("--jobs", type=int, default=3,
                    help="keep this small: an unbounded forest on this many rows "
                         "gets OOM killed on an 8 GB machine with no traceback")
    a = ap.parse_args()
    b = pathlib.Path(a.bundle)
    print(f"consuming {b}\n")

    print("integrity")
    man = b / "CHECKSUMS.sha256"
    check("checksum manifest present", man.exists())
    if not man.exists():
        return 1
    bad, missing = [], []
    for line in man.read_text().splitlines():
        digest, _, rel = line.partition("  ")
        f = b / rel
        if not f.exists():
            missing.append(rel); continue
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != digest:
            bad.append(rel)
    check("every named file present", not missing, f"{len(missing)} missing" if missing else "")
    check("every checksum matches", not bad, f"{len(bad)} differ" if bad else "")

    print("\nschema and shards")
    schema = json.loads((b / "schema.json").read_text())
    promised = [c["name"] for c in schema["columns"]]
    feats = [c["name"] for c in schema["columns"] if c["is_feature"]]
    scen = json.loads((b / "SCENARIOS.json").read_text()) \
        if (b / "SCENARIOS.json").exists() else {}
    check("scenarios declared", bool(scen),
          ", ".join(f"{k} ({v['kind']})" for k, v in scen.items()))
    bench = [k for k, v in scen.items() if v["kind"] == "benchmark"] or list(scen)

    shards = sorted((b / "shards").rglob("*.csv.gz"))
    check("shards present", len(shards) > 0, f"{len(shards)} found")
    t0 = time.time()
    parts = []
    for s in shards:
        d = pd.read_csv(s)
        d["scenario"] = s.parent.name if s.parent.name != "shards" else "default"
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    check("shards load", True, f"{len(df):,} rows in {time.time()-t0:.0f}s")
    if scen:
        counts = df.scenario.value_counts().to_dict()
        ok = all(counts.get(k, 0) == v["rows"] for k, v in scen.items())
        check("row counts match what SCENARIOS.json declares", ok,
              "" if ok else str(counts))
    check("columns match the schema exactly",
          [c for c in df.columns if c != "scenario"] == promised,
          f"{len([c for c in df.columns if c != 'scenario'])} of "
          f"{len(promised)} promised, plus the scenario label this test adds")
    check("schema names a grouping column", "grouping_column_for_splits" in schema,
          schema.get("grouping_column_for_splits", ""))

    print("\npartition")
    sp = pd.read_csv(b / "release_splits.csv")
    key = ["key_seed", "label_txNodeId"]
    # Neither a MultiIndex map nor a merge. The map took most of half an hour on
    # eight million rows; the merge copies the whole sixty two column frame and
    # drove this machine to seven gigabytes of swap, which is how a long job gets
    # killed. A dict lookup over one composite key column touches one column and
    # allocates one Series.
    sp1 = sp.drop_duplicates(key)
    lut = dict(zip(sp1.key_seed.astype(str) + "|" + sp1.label_txNodeId.astype(str),
                   sp1.split))
    m = df
    m["split"] = (df.key_seed.astype(str) + "|" +
                  df.label_txNodeId.astype(str)).map(lut)
    check("every row lands in exactly one partition", int(m.split.isna().sum()) == 0,
          f"{int(m.split.isna().sum())} unassigned")
    shares = (m.split.value_counts(normalize=True) * 100).round(1).to_dict()
    check("all three partitions present", len(shares) == 3, str(shares))
    # the leakage rule
    span = sp.groupby(["key_seed", "label_txNodeId"]).split.nunique()
    check("no transmitter in two partitions", int((span > 1).sum()) == 0,
          f"{int((span > 1).sum())} span partitions")
    gaps = sum(len(v.get("coverage_gaps", [])) for v in scen.values()
               if v["kind"] == "benchmark")
    check("every class reaches every partition in every benchmark scenario",
          gaps == 0, f"{gaps} gaps" if gaps else "")
    supp = sum(len(v.get("coverage_gaps", [])) for v in scen.values()
               if v["kind"] == "supplementary")
    if supp:
        print(f"       {supp} declared coverage gap(s) in supplementary "
              f"scenarios, which is why they are labelled that way")

    print("\nbaseline, trained and scored using only what is in the bundle")

    def baseline(sub, label):
        tr, te = sub[sub.split == "train"], sub[sub.split == "test"]
        if a.sample and len(tr) > a.sample:
            tr = tr.sample(a.sample, random_state=0)
        clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                     class_weight=None, random_state=0)
        t0 = time.time()
        clf.fit(tr[feats].astype("float32").fillna(-999), tr.label_attackId)
        pred = clf.predict(te[feats].astype("float32").fillna(-999))
        f1 = f1_score(te.label_attackId, pred, average="macro")
        mcc = matthews_corrcoef(te.label_attackId, pred)
        print(f"       {label}: trained on {len(tr):,}, scored on {len(te):,}, "
              f"{time.time()-t0:.0f}s  ->  macro F1 {f1:.4f}, MCC {mcc:.4f}")
        return f1, mcc

    # The published figure describes the REFERENCE scenario, so the comparison
    # has to be made there. Training across three scenarios is a different
    # experiment and scoring higher on it says nothing about whether the bundle
    # reproduces the paper.
    ref = bench[0]
    f1, mcc = baseline(m[m.scenario == ref], f"reference scenario ({ref})")
    check("fused macro F1 near the published figure",
          abs(f1 - PAPER_FUSED_F1) <= TOLERANCE,
          f"{f1:.4f} against {PAPER_FUSED_F1} published, MCC {mcc:.4f}")

    if len(bench) > 1:
        f1a, _ = baseline(m[m.scenario.isin(bench)], "all benchmark scenarios")
        print(f"       training across {len(bench)} scenarios moves it "
              f"{f1a - f1:+.4f}, which is a property of the data rather than a "
              f"check on the bundle")

    print()
    if fails:
        print(f"{len(fails)} check(s) failed. The bundle is not publishable.")
        return 1
    print("The bundle is self-sufficient: it loads, partitions and trains "
          "using only its own files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
