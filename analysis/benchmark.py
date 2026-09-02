#!/usr/bin/env python3
"""
The three-way cross-layer benchmark: application-only against PHY/MAC-only
against fused, on one dataset with one attack set and one split.

This IS contribution C2, so it is the experimental core rather than a
formality. So, Petit and Starobinski (WiSec 2019) found PHY-only beat
application-only on VeReMi position attacks (CCR 0.9376 against 0.8838) but
never built the fused model. The interesting result here is per class: which
layer catches what.

Splits are grouped by transmitting station so no station appears on both sides.
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score, classification_report, matthews_corrcoef


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--sample", type=int, default=None,
                    help="subsample rows before the comparison; the three blocks "
                         "always see the SAME rows and the SAME folds, so the "
                         "comparison stays paired")
    ap.add_argument("--trees", type=int, default=200)
    a = ap.parse_args()

    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    if "label_clean" in df.columns:
        before = len(df)
        df = df[df.label_clean == 1].reset_index(drop=True)
        if len(df) < before:
            print(f"dropped {before - len(df)} windows below the label purity floor")
    app = [c for c in df.columns if c.startswith("app_")]
    phy = [c for c in df.columns if c.startswith("phy_")]
    blocks = {"app-only": app, "phy-only": phy, "fused": app + phy}

    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0).reset_index(drop=True)
        print(f"subsampled to {len(df)} windows")
    y = df.label_attackId.astype(int)
    groups = df.label_txNodeId.astype(int)
    sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=0)
    folds = list(sgkf.split(df, y, groups))

    print(f"{len(df)} windows, {y.nunique()} classes, {groups.nunique()} stations, "
          f"{a.folds} grouped folds\n")
    # MCC is the primary aggregate metric named in the proposal, section 5.6.
    # It is the multiclass generalisation here, over every class at once, and it
    # is NOT the same quantity as the binary MCC reported per threshold in
    # evaluate_deployment.py. The two must never be compared to each other.
    print(f"{'block':10s} {'features':>8s}  {'macro F1':>18s}  {'accuracy':>8s}"
          f"  {'MCC multiclass':>18s}")

    keep = None
    classes = sorted(y.unique())
    per_class = {}
    for name, cols in blocks.items():
        X = df[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        f1s, accs, pc, mccs = [], [], [], []
        for tr, te in folds:
            clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=-1, random_state=0)
            clf.fit(X.iloc[tr], y.iloc[tr])
            p = clf.predict(X.iloc[te])
            f1s.append(f1_score(y.iloc[te], p, average="macro"))
            accs.append((p == y.iloc[te]).mean())
            mccs.append(matthews_corrcoef(y.iloc[te], p))
            pc.append(f1_score(y.iloc[te], p, average=None, labels=classes,
                               zero_division=0))
            if name == "fused" and keep is None:
                keep = (y.iloc[te], p, clf, cols)
        per_class[name] = np.mean(pc, axis=0)
        print(f"{name:10s} {len(cols):8d}  {np.mean(f1s):.4f} +/- {np.std(f1s):.4f}  "
              f"{np.mean(accs):.4f}  {np.mean(mccs):.4f} +/- {np.std(mccs):.4f}")

    # Per class for EVERY block, averaged over folds. Which layer catches what
    # is the whole of C2, and reporting it for the fused block alone on one
    # fold hides exactly the comparison the contribution rests on.
    print(f"\nper class F1, averaged over {a.folds} folds")
    print(f"{'class':>6s}  " + "  ".join(f"{b:>12s}" for b in blocks))
    for i, c in enumerate(classes):
        print(f"{c:>6d}  " + "  ".join(f"{per_class[b][i]:12.3f}" for b in blocks))

    if a.report and keep:
        yt, p, clf, cols = keep
        print("\nfused, first fold, per class:")
        print(classification_report(yt, p, digits=3, zero_division=0))
        imp = pd.Series(clf.feature_importances_, index=cols).sort_values(ascending=False)
        print("top features:")
        print(imp.head(12).to_string())


if __name__ == "__main__":
    main()
