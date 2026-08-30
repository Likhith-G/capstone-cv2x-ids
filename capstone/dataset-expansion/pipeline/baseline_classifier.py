#!/usr/bin/env python3
"""
baseline_classifier.py -- Capstone: Cybersecurity for Connected Cars

Random Forest baseline on the generated dataset with ablation study
to demonstrate that classification does NOT rely on fabricated features.
"""

import sys
import warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    classification_report, f1_score, accuracy_score, confusion_matrix
)

warnings.filterwarnings("ignore")

# Feature groups for ablation
NETWORK_FEATURES = [
    "n_pkts", "n_bsm", "n_flood",
    "pkt_rate", "byte_rate", "total_bytes", "duration",
    "mean_iat", "std_iat", "min_iat", "max_iat",
    "bsm_mean_iat", "bsm_std_iat", "flood_mean_iat", "flood_std_iat",
    "mean_pkt_size", "std_pkt_size",
    "flood_ratio",
]

VEHICULAR_FEATURES = [
    "mean_pos_deviation", "max_pos_deviation",
    "mean_speed_deviation", "max_speed_deviation",
    "heading_change_rate", "seq_anomaly", "unique_vehicle_ids",
    "msg_freq", "bsm_size_mean", "bsm_size_std",
]

CONTEXT_FEATURES = [
    "region_id",
]

# Note: true_speed_mean, true_speed_std, and distance_to_gnb are omitted from ALL_FEATURES
# because in a deterministic simulation, they act as proxies for node identity.

ALL_FEATURES = NETWORK_FEATURES + VEHICULAR_FEATURES + CONTEXT_FEATURES

# Ablation configurations
ABLATION_CONFIGS = {
    "full":         ALL_FEATURES,
    "network_only": NETWORK_FEATURES,
    "vehicular_only": VEHICULAR_FEATURES,
    "no_context":   NETWORK_FEATURES + VEHICULAR_FEATURES,
    "no_pos":       [f for f in ALL_FEATURES if "pos" not in f],
    "no_speed":     [f for f in ALL_FEATURES if "speed" not in f.lower() or f.startswith("true")],
}


def run_experiment(df, features, label_col, name, n_splits=5):
    """
    Run stratified K-fold RF classification.
    Returns dict of mean metrics.
    """
    available = [f for f in features if f in df.columns]
    if not available:
        print(f"  WARNING: No features available for {name}")
        return None

    X = df[available].values.astype(np.float64)
    y = df[label_col].values

    # Handle NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Variance filter: drop features with variance < 1e-10
    variances = np.var(X, axis=0)
    valid_idx = variances >= 1e-10
    dropped_feats = [f for f, v in zip(available, valid_idx) if not v]
    if dropped_feats:
        print(f"  [Filter] Dropped {len(dropped_feats)} zero-variance features: {', '.join(dropped_feats)}")
    
    available = [f for f, v in zip(available, valid_idx) if v]
    X = X[:, valid_idx]
    
    if X.shape[1] == 0:
        print(f"  WARNING: No features remaining after variance filter for {name}")
        return None

    le = LabelEncoder()
    y_encoded = le.fit_transform(y)

    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
    groups = df["scenario_id"].astype(str) + "_" + df["node_id"].astype(str)
    
    f1_scores = []
    acc_scores = []
    reports = []

    for fold, (train_idx, test_idx) in enumerate(sgkf.split(X, y_encoded, groups=groups)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y_encoded[train_idx], y_encoded[test_idx]

        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=20,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)

        f1 = f1_score(y_test, y_pred, average="macro")
        acc = accuracy_score(y_test, y_pred)
        f1_scores.append(f1)
        acc_scores.append(acc)

        if fold == 0:
            reports.append(classification_report(
                y_test, y_pred,
                labels=np.arange(len(le.classes_)),
                target_names=[str(c) for c in le.classes_],
                zero_division=0
            ))

    # Feature importance (from last fold)
    importances = clf.feature_importances_
    feat_imp = sorted(
        zip(available, importances),
        key=lambda x: x[1], reverse=True
    )

    return {
        "name":       name,
        "features":   len(available),
        "f1_mean":    np.mean(f1_scores),
        "f1_std":     np.std(f1_scores),
        "acc_mean":   np.mean(acc_scores),
        "acc_std":    np.std(acc_scores),
        "top_feats":  feat_imp[:5],
        "report":     reports[0] if reports else "",
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "output/dataset.csv"
    print(f"Loading {path}...")
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} rows\n")

    print("=" * 70)
    print("BINARY CLASSIFICATION (Benign vs Attack)")
    print("=" * 70)

    binary_results = []
    for config_name, features in ABLATION_CONFIGS.items():
        print(f"\n--- Config: {config_name} ---")
        result = run_experiment(df, features, "label_binary", config_name)
        if result:
            binary_results.append(result)
            print(f"  F1 (macro): {result['f1_mean']:.4f} +/- {result['f1_std']:.4f}")
            print(f"  Accuracy:   {result['acc_mean']:.4f} +/- {result['acc_std']:.4f}")
            print(f"  Top features: {', '.join(f[0] for f in result['top_feats'])}")

    print("\n" + "=" * 70)
    print("MULTI-CLASS CLASSIFICATION (by attack type)")
    print("=" * 70)

    multiclass_result = run_experiment(
        df, ALL_FEATURES, "label_attack_type", "multiclass_full"
    )
    if multiclass_result:
        print(f"\n  F1 (macro): {multiclass_result['f1_mean']:.4f} +/- {multiclass_result['f1_std']:.4f}")
        print(f"  Accuracy:   {multiclass_result['acc_mean']:.4f} +/- {multiclass_result['acc_std']:.4f}")
        print(f"\n  Classification Report (fold 0):")
        print(multiclass_result["report"])

    # -- Ablation summary table -------------------------------------------
    print("\n" + "=" * 70)
    print("ABLATION SUMMARY")
    print("=" * 70)
    print(f"{'Config':<20} {'Features':>8}  {'F1':>12}  {'Accuracy':>12}")
    print("-" * 60)
    for r in binary_results:
        print(f"{r['name']:<20} {r['features']:>8}  "
              f"{r['f1_mean']:.4f}+/-{r['f1_std']:.4f}  "
              f"{r['acc_mean']:.4f}+/-{r['acc_std']:.4f}")

    # -- F1 = 1.0 warning --------------------------------------------------
    if binary_results and binary_results[0]["f1_mean"] >= 0.999:
        print("\n  WARNING: F1 = 1.0 detected. Possible issues:")
        print("  - Feature leakage? Check feature importance.")
        print("  - Data leakage? Verify no label information in features.")
        top_feat_name = binary_results[0]["top_feats"][0][0]
        top_feat_imp = binary_results[0]["top_feats"][0][1]
        print(f"  - Top feature: {top_feat_name} (imp={top_feat_imp:.4f})")
        if top_feat_imp > 0.5:
            print(f"    Single feature dominates -- check if this is a proxy for the label.")


if __name__ == "__main__":
    main()
