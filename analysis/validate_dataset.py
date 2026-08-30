#!/usr/bin/env python3
"""
Adversarial validation gates. These run BEFORE a dataset is frozen.

An earlier integrity suite ran 57 checks, passed all 57, and certified a
dataset in which 97.76 percent of test rows appeared verbatim in training and a
1-nearest neighbour classifier scored F1 = 1.0000. A suite that only checks what the
generator intended will always pass. These gates instead try to show the
dataset is trivial, and the run fails if any of them succeeds.

For scale: KDD'99, the canonical cautionary tale in intrusion detection, had
78 percent duplicate training records. The dataset above had 97.76 percent.

Usage: validate_dataset.py <features.csv>
"""
import argparse
import sys
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import f1_score

FAIL = []
WARN = []


def gate(name, ok, detail, warn_only=False):
    tag = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    print(f"[{tag}] {name}: {detail}")
    if not ok:
        (WARN if warn_only else FAIL).append(name)


def feature_columns(df):
    return [c for c in df.columns if c.startswith(("app_", "phy_"))]


def quantise(X):
    """Round each feature to a physically meaningful precision.

    Rounding continuous floats to six decimals makes the duplicate and overlap
    gates vacuous: they return 0.0000 whether or not the dataset is degenerate,
    because no two floats ever match. That 97.76 percent duplicate rate came
    from features that were genuinely DISCRETE, because the
    attack parameters were constants. To catch that failure again the gates
    have to compare at the resolution a measurement actually carries: 1 dB of
    received power, 1 ms of time, 1 m of distance.
    """
    Q = X.copy()
    for c in Q.columns:
        if "rsrp" in c or "sinr" in c or "tbler" in c:
            step = 1.0
        elif "iat" in c:
            step = 0.001
        elif "dist" in c or "predict" in c or "dmv" in c:
            step = 1.0
        elif "speed" in c or "ssc" in c or "accel" in c:
            step = 0.1
        elif "heading" in c:
            step = 1.0
        else:
            step = 0.01
        Q[c] = (Q[c] / step).round() * step
    return Q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--dup-max", type=float, default=0.20)
    ap.add_argument("--knn-max", type=float, default=0.97)
    ap.add_argument("--corr-max", type=float, default=0.95)
    ap.add_argument("--model-sample", type=int, default=150000,
                    help="subsample size for the nearest-neighbour gate, which "
                         "is brute force in this many dimensions")
    a = ap.parse_args()

    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    feats = feature_columns(df)
    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = df.label_attackId.astype(int)
    groups = df.label_txNodeId.astype(int)

    print(f"{len(df)} windows, {len(feats)} features, "
          f"{y.nunique()} classes, {groups.nunique()} stations\n")

    # 1. Duplicate feature vectors, whole dataset and per class.
    Q = quantise(X)
    dup = 1.0 - len(Q.drop_duplicates()) / len(Q)
    gate("1 duplicate fraction", dup <= a.dup_max,
         f"{dup:.4f} duplicate rows at measurement precision (limit {a.dup_max})")
    for c, g in Q.groupby(y):
        d = len(g.drop_duplicates())
        gate(f"1b class {c} distinct vectors", d > max(20, 0.02 * len(g)),
             f"{d} distinct of {len(g)} rows")

    # 2. Within-class coefficient of variation. A class whose features barely
    #    move is a class the model memorises rather than learns.
    for c, g in X.groupby(y):
        cv = (g.std() / g.mean().abs().replace(0, np.nan)).abs()
        n_flat = int((cv.fillna(0) < 0.01).sum())
        gate(f"2 class {c} feature variation", n_flat < len(feats) * 0.5,
             f"{n_flat}/{len(feats)} features effectively constant")

    # 3 and 4. Grouped split, then verbatim overlap and 1-NN triviality.
    #    Splitting by transmitting station is what stops the same station's
    #    windows appearing on both sides.
    if len(X) > a.model_sample:
        idx = X.sample(n=a.model_sample, random_state=0).index
        Xm, ym, gm, Qm = X.loc[idx], y.loc[idx], groups.loc[idx], Q.loc[idx]
        print(f"    (gates 3 and 4 run on a {a.model_sample} row subsample)")
    else:
        Xm, ym, gm, Qm = X, y, groups, Q
    sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    tr, te = next(sgkf.split(Xm, ym, gm))
    Xtr, Xte, ytr, yte = Xm.iloc[tr], Xm.iloc[te], ym.iloc[tr], ym.iloc[te]

    Qtr, Qte = Qm.iloc[tr], Qm.iloc[te]
    tr_set = set(map(tuple, Qtr.values))
    overlap = np.mean([tuple(r) in tr_set for r in Qte.values])
    gate("3 verbatim train/test overlap", overlap <= 0.05,
         f"{overlap:.4f} of test rows appear verbatim in training")

    knn = KNeighborsClassifier(n_neighbors=1).fit(Xtr, ytr)
    f1_knn = f1_score(yte, knn.predict(Xte), average="macro")
    gate("4 1-NN triviality", f1_knn <= a.knn_max,
         f"macro F1 {f1_knn:.4f} (a near-perfect score means the task is trivial)")

    dt = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xtr, ytr)
    f1_dt = f1_score(yte, dt.predict(Xte), average="macro")
    gate("4b depth-3 tree triviality", f1_dt <= a.knn_max,
         f"macro F1 {f1_dt:.4f}")

    # 5. Single-feature separability. No class may be readable off one column.
    worst = ("", 0.0)
    for f in feats:
        for c in sorted(y.unique()):
            if c == 0:
                continue
            pos, neg = X[f][y == c], X[f][y != c]
            if pos.std() == 0 and neg.std() == 0:
                continue
            lo, hi = pos.min(), pos.max()
            sep = float(((neg < lo) | (neg > hi)).mean())
            if sep > worst[1]:
                worst = (f"{f} vs class {c}", sep)
    gate("5 single-feature separability", worst[1] < 0.999,
         f"best single feature excludes {worst[1]:.4f} of other classes ({worst[0]})")

    # 6. Oracle freedom. No feature may track a ground-truth column.
    labels = df[[c for c in df.columns if c.startswith("label_")]].select_dtypes("number")
    worst_corr = ("", 0.0)
    for f in feats:
        for l in labels.columns:
            if X[f].std() == 0 or labels[l].std() == 0:
                continue
            r = abs(np.corrcoef(X[f], labels[l])[0, 1])
            if np.isfinite(r) and r > worst_corr[1]:
                worst_corr = (f"{f} vs {l}", r)
    gate("6 oracle freedom", worst_corr[1] < a.corr_max,
         f"max |corr| with a label column {worst_corr[1]:.4f} ({worst_corr[0]})")

    # 7. Negative-class presence. Every feature must have a real benign
    #    distribution, or it is a marker rather than a measurement.
    benign = X[y == 0]
    dead = [f for f in feats if benign[f].nunique() <= 1]
    gate("7 benign distribution present", not dead,
         f"{len(dead)} features constant on benign traffic"
         + (f": {dead[:5]}" if dead else ""))

    # 8. Class balance sanity.
    share = y.value_counts(normalize=True)
    gate("8 class balance", share.max() < 0.90,
         f"largest class {share.max():.3f}", warn_only=True)

    print()
    if FAIL:
        print(f"FAILED {len(FAIL)} gate(s): {', '.join(FAIL)}")
        sys.exit(1)
    print("all gates passed" + (f" ({len(WARN)} warning(s))" if WARN else ""))


if __name__ == "__main__":
    main()
