#!/usr/bin/env python3
"""
Each attack class against benign alone, from one receiver's window.

The multiclass benchmark asks a model to tell eleven classes apart at once, so a
class can score badly because it is confused with another attack rather than
because nothing separates it from honest traffic. This removes the other
attacks: for each class, a binary detector is trained on that class and benign
only, and scored by the area under the ROC curve (AUC) on held-out
transmitters. AUC needs no threshold, so no operating point is chosen on the
test data, and it does not depend on how many of each class the test set holds.

An AUC near 0.5 means the window's features carry almost no signal for that
class even with every other attack out of the way. That is the single-receiver
limit seen from a different angle than the multiclass table.

Chance is not 0.5 here, and the null control measures what it is. Class 8 is
inert in this simulator, so its stations behave exactly like benign ones, yet a
detector trained on it scores well above 0.5. Every station differs from the
others in ways that have nothing to do with attacking (its vehicle class, its
desired speed, its lane, where it sits relative to the roadside units), and a
binary detector over a handful of stations learns those traits. `--null` draws
groups of BENIGN transmitters the same size as a class, labels them as the
attack, and runs the identical protocol. A class is only separable by more than
station identity where its AUC clears that null band.

This adapts a diagnostic from the feature engineering workstream's MATLAB
pipeline to release 1.1.0: the frozen partition rather than a fresh holdout,
label_clean rather than a purity threshold, and the reference scenario alone,
because the other scenarios widen the position draws or leave classes out of a
split.

    separability.py RELEASE_DIR [--scenario highway_sparse]
"""
import argparse
import glob
import pathlib

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

NAMES = {1: "pos_const_offset", 3: "pos_offset_random", 4: "pos_replay",
         5: "speed_falsify", 6: "sybil", 7: "dos_rate", 8: "sps_manipulation",
         11: "pos_small_offset", 12: "dos_low_rate", 13: "pos_medium_offset"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("release")
    ap.add_argument("--scenario", default="highway_sparse")
    ap.add_argument("--cap", type=int, default=60000,
                    help="training rows per side per class; benign is drawn "
                         "down to the attack class's size, as a balanced "
                         "binary fit")
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--null", type=int, default=0, metavar="K",
                    help="also run K null draws per transmitter count: benign "
                         "transmitters relabelled as a pseudo attack class, "
                         "matched to each class's transmitter count in train "
                         "and in test")
    a = ap.parse_args()
    rel = pathlib.Path(a.release).expanduser()
    print(f"release: {(rel / 'PROVENANCE.txt').read_text().splitlines()[0]}")

    shards = sorted(glob.glob(str(rel / "shards" / a.scenario / "*.csv.gz")))
    df = pd.concat((pd.read_csv(f) for f in shards), ignore_index=True)
    df = df[df.label_clean == 1]
    feats = [c for c in df.columns if c.startswith(("app_", "phy_"))]
    splits = pd.read_csv(rel / "release_splits.csv")
    df = df.merge(splits[["key_seed", "key_claimedStationId", "split"]],
                  on=["key_seed", "key_claimedStationId"], how="left")
    assert df.split.notna().all(), "a row has no partition"
    print(f"{a.scenario}: {len(df):,} windows from {len(shards)} shards, "
          f"{len(feats)} features")
    tr, te = df[df.split == "train"], df[df.split == "test"]
    assert not set(tr.label_txNodeId) & set(te.label_txNodeId), \
        "a transmitter is on both sides"
    print(f"train {len(tr):,} windows, {tr.label_txNodeId.nunique()} transmitters; "
          f"test {len(te):,}, {te.label_txNodeId.nunique()}")

    def matrix(d):
        return (d[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
                .to_numpy(dtype=np.float32))

    rng = np.random.default_rng(0)
    ben_tr = tr[tr.label_attackId == 0]
    def binary_auc(fit_pos, fit_neg, test_pos, test_neg):
        n = min(len(fit_pos), len(fit_neg), a.cap)
        fit_pos = fit_pos.iloc[rng.choice(len(fit_pos), n, replace=False)]
        fit_neg = fit_neg.iloc[rng.choice(len(fit_neg), n, replace=False)]
        clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                     random_state=0)
        clf.fit(np.vstack([matrix(fit_pos), matrix(fit_neg)]),
                np.r_[np.ones(n), np.zeros(n)])
        p = clf.predict_proba(np.vstack([matrix(test_pos), matrix(test_neg)]))[:, 1]
        return roc_auc_score(np.r_[np.ones(len(test_pos)), np.zeros(len(test_neg))], p), n

    print(f"\n{'class':>20s} {'id':>3s} {'train rows':>11s} {'test attack':>12s} "
          f"{'test benign':>12s} {'AUC':>7s}  stations train/test")
    for c in sorted(NAMES, key=lambda k: NAMES[k]):
        att = tr[tr.label_attackId == c]
        n = min(len(att), a.cap)
        att = att.iloc[rng.choice(len(att), n, replace=False)]
        ben = ben_tr.iloc[rng.choice(len(ben_tr), n, replace=False)]
        fit = pd.concat([att, ben])
        clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                     random_state=0)
        clf.fit(matrix(fit), (fit.label_attackId == c).astype(int).values)
        test = te[te.label_attackId.isin([0, c])]
        p = clf.predict_proba(matrix(test))[:, 1]
        auc = roc_auc_score((test.label_attackId == c).astype(int).values, p)
        print(f"{NAMES[c]:>20s} {c:>3d} {2 * n:>11,} "
              f"{int((test.label_attackId == c).sum()):>12,} "
              f"{int((test.label_attackId == 0).sum()):>12,} {auc:>7.4f}  "
              f"{tr[tr.label_attackId == c].label_txNodeId.nunique():>3d}/"
              f"{te[te.label_attackId == c].label_txNodeId.nunique()}")
    print("\nAUC 0.5 is chance. Each row is a separate binary detector trained "
          "on that class and benign\nalone, on the frozen train split, and "
          "scored on held-out transmitters.")
    if a.null:
        # A transmitter is one physical radio across the whole run, so a
        # station is drawn whole and every window it sent goes with it.
        ben_te = te[te.label_attackId == 0]
        tx_tr = ben_tr.label_txNodeId.unique()
        tx_te = ben_te.label_txNodeId.unique()
        sizes = sorted({(tr[tr.label_attackId == c].label_txNodeId.nunique(),
                         te[te.label_attackId == c].label_txNodeId.nunique())
                        for c in NAMES})
        print(f"\nnull control: benign transmitters relabelled as a pseudo "
              f"attack, {a.null} draws per size")
        print(f"{'stations train/test':>20s} {'AUC min':>8s} {'median':>8s} "
              f"{'max':>8s}")
        for k_tr, k_te in sizes:
            aucs = []
            for _ in range(a.null):
                s_tr = set(rng.choice(tx_tr, k_tr, replace=False))
                s_te = set(rng.choice(tx_te, k_te, replace=False))
                auc, _n = binary_auc(
                    ben_tr[ben_tr.label_txNodeId.isin(s_tr)],
                    ben_tr[~ben_tr.label_txNodeId.isin(s_tr)],
                    ben_te[ben_te.label_txNodeId.isin(s_te)],
                    ben_te[~ben_te.label_txNodeId.isin(s_te)])
                aucs.append(auc)
            print(f"{f'{k_tr}/{k_te}':>20s} {min(aucs):8.4f} "
                  f"{np.median(aucs):8.4f} {max(aucs):8.4f}", flush=True)
        print("\nA class carries evidence beyond station identity only where "
              "its AUC clears the null band\nfor its own transmitter count.")
    print("SEPARABILITY DONE")


if __name__ == "__main__":
    main()
