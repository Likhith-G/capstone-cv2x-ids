#!/usr/bin/env python3
"""
Which classes does the baseline confuse with which? (REVIEW_FIX_PLAN 15.1, X4.)

The supervisor's expected outcomes for multiclass classification (10 Apr
slides) name a confusion matrix and "which classes are difficult to
distinguish". This is the release's own baseline, trained exactly as
check_release.py trains it (reference scenario, frozen partition, 400,000
training rows sampled with random_state 0, a 60-tree forest, the schema's 50
features), so its macro F1 must reproduce the published 0.5319 before the
matrix is read.

Prints the row-normalised confusion matrix (each row is a true class and sums
to one) and per-class precision, recall and F1.

Usage: confusion_matrix.py path/to/release [--trees 60] [--jobs 3]
"""
import argparse
import glob
import json
import pathlib

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (confusion_matrix, f1_score, matthews_corrcoef,
                             precision_recall_fscore_support)

NAMES = {0: "benign", 1: "pos_const_offset", 3: "pos_offset_random", 4: "pos_replay",
         5: "speed_falsify", 6: "sybil", 7: "dos_rate", 8: "sps_manipulation",
         11: "pos_small_offset", 12: "dos_low_rate", 13: "pos_medium_offset"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--scenario", default="highway_sparse")
    ap.add_argument("--sample", type=int, default=400000)
    ap.add_argument("--trees", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()

    b = pathlib.Path(a.bundle)
    schema = json.loads((b / "schema.json").read_text())
    feats = [c["name"] for c in schema["columns"] if c["is_feature"]]
    files = sorted(glob.glob(str(b / "shards" / a.scenario / "*.csv.gz")))
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    sp = pd.read_csv(b / "release_splits.csv").drop_duplicates(["key_seed", "label_txNodeId"])
    lut = dict(zip(sp.key_seed.astype(str) + "|" + sp.label_txNodeId.astype(str), sp.split))
    df["split"] = (df.key_seed.astype(str) + "|" + df.label_txNodeId.astype(str)).map(lut)
    if df.split.isna().any():
        raise SystemExit("rows without a partition; run check_release.py")

    tr, te = df[df.split == "train"], df[df.split == "test"]
    if a.sample and len(tr) > a.sample:
        tr = tr.sample(a.sample, random_state=0)
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                 class_weight=None, random_state=0)
    clf.fit(tr[feats].astype("float32").fillna(-999), tr.label_attackId)
    pred = clf.predict(te[feats].astype("float32").fillna(-999))
    y = te.label_attackId.values
    print(f"{a.scenario}: trained on {len(tr):,}, scored on {len(te):,} test windows; "
          f"macro F1 {f1_score(y, pred, average='macro'):.4f}, "
          f"MCC {matthews_corrcoef(y, pred):.4f} (published 0.5319, 0.6746)\n")

    classes = sorted(np.unique(y))
    cm = confusion_matrix(y, pred, labels=classes, normalize="true")
    names = [NAMES.get(c, str(c)) for c in classes]
    print("row-normalised confusion matrix, rows true class, columns predicted class")
    print("| true \\ predicted | " + " | ".join(f"{c}" for c in classes) + " |")
    print("|---|" + "---|" * len(classes))
    for c, n, row in zip(classes, names, cm):
        print(f"| {c} {n} | " + " | ".join(f"{v:.3f}" for v in row) + " |")

    p, r, f, s = precision_recall_fscore_support(y, pred, labels=classes, zero_division=0)
    print("\n| class | test windows | precision | recall | F1 | most often predicted as, other than itself |")
    print("|---|---|---|---|---|---|")
    for i, (c, n) in enumerate(zip(classes, names)):
        off = cm[i].copy()
        off[i] = -1
        j = int(off.argmax())
        print(f"| {c} {n} | {int(s[i]):,} | {p[i]:.3f} | {r[i]:.3f} | {f[i]:.3f} | "
              f"{names[j]} ({cm[i, j]:.3f}) |")
    print("\nCONFUSION DONE")


if __name__ == "__main__":
    main()
