#!/usr/bin/env python3
"""
The field's standard plausibility checks, as an external baseline.

Every detection number in this project so far compares our own feature blocks
against each other. That shows fusion beats its own ablations and says nothing
about how the work stands against a detector a reader recognises. This
implements the checks the misbehaviour detection literature standardised on,
as catalogued by van der Heijden, Dietzel, Leinmuller and Kargl (IEEE COMST
21(1), 2019) and as implemented in the widely used detection frameworks:

    ART   acceptance range verification. A claim from further away than a
          receiver can hear is implausible.
    DMV   distance moved verification. Consecutive claimed positions must be
          reachable at the claimed speed.
    SSC   sudden speed change. Claimed speed cannot jump faster than a vehicle
          can accelerate.
    MGT   movement graph / position prediction. The next claim must be near
          where the last one predicted.
    ACC   acceleration plausibility, a physical bound on the claimed dynamics.
    RSS   received signal strength against claimed distance under the fitted
          propagation law. This is the single receiver version of the check
          this paper pools across receivers, and it belongs in the baseline
          because it is what the prior work actually proposed.

Each check is a threshold on a quantity the receiver already computes. The
thresholds are NOT guessed: each one is set on the training fold's benign
traffic at a stated per check false positive rate, so the suite is calibrated
the way a deployment would calibrate it and the comparison is not rigged by a
badly chosen constant. A station is flagged when any check fires, which is the
usual fusion in this literature.

Reported as binary detection, benign against any attack, because a rule suite
does not produce a class label and a multiclass macro F1 would not be
comparable.
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score, matthews_corrcoef, precision_score, recall_score

# check name -> (feature, direction). "hi" means large values are implausible.
CHECKS = {
    "ART acceptance range":     ("app_claimed_dist_mean", "hi"),
    "DMV distance moved":       ("app_dmv_absmax", "hi"),
    "SSC sudden speed change":  ("app_ssc_absmax", "hi"),
    "MGT position prediction":  ("app_predict_max", "hi"),
    "ACC acceleration":         ("app_accel_absmax", "hi"),
    "RSS claimed distance":     ("phy_rsrp_mean", "lo"),
}


def thresholds(train, fpr):
    """One threshold per check, set on benign training rows at the given per
    check false positive rate. Fitted on the training fold only."""
    ben = train[train.label_attackId == 0]
    out = {}
    for name, (col, side) in CHECKS.items():
        if col not in train.columns:
            continue
        v = ben[col].replace([np.inf, -np.inf], np.nan).dropna()
        if v.empty:
            continue
        out[name] = (col, side,
                     float(np.quantile(v, 1.0 - fpr) if side == "hi"
                           else np.quantile(v, fpr)))
    return out


def fire(df, th):
    """Per check boolean, and the any-check union."""
    cols = {}
    for name, (col, side, t) in th.items():
        v = df[col].replace([np.inf, -np.inf], np.nan)
        cols[name] = (v > t).fillna(False) if side == "hi" else (v < t).fillna(False)
    f = pd.DataFrame(cols, index=df.index)
    return f, f.any(axis=1)


def scores(truth, pred):
    return (f1_score(truth, pred, zero_division=0),
            precision_score(truth, pred, zero_division=0),
            recall_score(truth, pred, zero_division=0),
            matthews_corrcoef(truth, pred) if pred.any() else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--sample", type=int, default=250000)
    ap.add_argument("--fpr", type=float, default=0.01,
                    help="per check false positive rate the thresholds are set at")
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--no-learned", action="store_true",
                    help="skip the learned comparison, which is the expensive half")
    a = ap.parse_args()

    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1].reset_index(drop=True)
    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0).reset_index(drop=True)

    y = df.label_attackId.astype(int)
    ybin = (y != 0).astype(int)
    groups = df.label_txNodeId.astype(int)
    feats = [c for c in df.columns if c.startswith(("app_", "phy_"))]
    sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=0)
    folds = list(sgkf.split(df, y, groups))

    print(f"{len(df):,} windows, {groups.nunique()} stations, {a.folds} folds "
          f"grouped by transmitting station")
    print(f"thresholds set on benign training rows at a per check false positive "
          f"rate of {a.fpr}\n")

    per_check, suite, learned = {n: [] for n in CHECKS}, [], []
    pos_recall = {n: [] for n in list(CHECKS) + ["suite", "learned"]}
    position = [1, 11, 13]
    for tr, te in folds:
        train, test = df.iloc[tr], df.iloc[te]
        th = thresholds(train, a.fpr)
        f, any_fire = fire(test, th)
        t = ybin.iloc[te]
        for name in th:
            per_check[name].append(scores(t, f[name].astype(int)))
        suite.append(scores(t, any_fire.astype(int)))
        ispos = y.iloc[te].isin(position)
        for name in th:
            pos_recall[name].append(f[name][ispos].mean())
        pos_recall["suite"].append(any_fire[ispos].mean())

        if not a.no_learned:
            X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=-1,
                                         random_state=0)
            clf.fit(X.iloc[tr], ybin.iloc[tr])
            p = clf.predict(X.iloc[te])
            learned.append(scores(t, p))
            pos_recall["learned"].append(pd.Series(p, index=t.index)[ispos].mean())

    def row(name, vals):
        m = np.mean(vals, axis=0)
        print(f"{name:26s} {m[0]:8.3f} {m[1]:10.3f} {m[2]:8.3f} {m[3]:8.3f}")

    print(f"{'detector':26s} {'F1':>8s} {'precision':>10s} {'recall':>8s} {'MCC':>8s}")
    for name, vals in per_check.items():
        if vals:
            row(name, vals)
    print("-" * 64)
    row("suite, any check fires", suite)
    if learned:
        row(f"learned, {len(feats)} features", learned)

    print(f"\nrecall on the three constant-offset position classes, which is what "
          f"this paper\nis about. A check that never fires on them is blind to the "
          f"attack the pooled\nestimator recovers.")
    for name, vals in pos_recall.items():
        if vals:
            print(f"  {name:26s} {np.mean(vals):8.3f}")

    print("""
Read the RSS row against the pooled result. It is the same physical idea at one
receiver: compare the power received against the power the claimed distance
implies. The literature proposed it in that form, and at one receiver it is
what it is. The paper's claim is that the idea is sound and the observation
unit was wrong.
""")


if __name__ == "__main__":
    main()
