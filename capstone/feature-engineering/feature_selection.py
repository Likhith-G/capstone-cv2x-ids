#!/usr/bin/env python3
"""
feature_selection.py -- Capstone: Cybersecurity for Connected Cars

Feature engineering pipeline for the CV2X-IDS dataset.
Produces ranked feature lists, top-k evaluation curves, final feature
subsets, per-class discriminability analysis, and SHAP interpretability.

Usage:
    python3 feature_selection.py                    # Run full pipeline
    python3 feature_selection.py --step universe    # Run a single step
    python3 feature_selection.py --step rankings
    python3 feature_selection.py --step discriminability
    python3 feature_selection.py --step topk
    python3 feature_selection.py --step select
    python3 feature_selection.py --step shap
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import f_classif, mutual_info_classif
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    matthews_corrcoef,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset-expansion" / "output"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
FIGURES_DIR = OUTPUT_DIR / "figures"

METADATA_COLS = ["scenario_id", "node_id", "window_id", "window_start", "window_end"]
CONTEXT_COLS = ["true_speed_mean", "true_speed_std", "distance_to_gnb", "region_id"]
LABEL_COLS = ["label_binary", "label_attack_type"]
VARIANCE_THRESHOLD = 1e-10
CORRELATION_THRESHOLD = 0.99

FEATURE_CATEGORIES = {
    "volume_rate": ["n_pkts", "n_bsm", "n_flood", "byte_rate", "total_bytes", "pkt_rate", "flood_ratio"],
    "timing": [
        "duration", "mean_iat", "std_iat", "min_iat", "max_iat",
        "bsm_mean_iat", "flood_mean_iat", "flood_std_iat",
    ],
    "size": ["mean_pkt_size", "std_pkt_size"],
    "vehicular": [
        "mean_pos_deviation", "max_pos_deviation",
        "mean_speed_deviation", "max_speed_deviation",
    ],
    "behavioral": ["seq_anomaly", "unique_vehicle_ids", "msg_freq"],
}
ANOVA_F_CAP = 1e6

K_VALUES = [3, 5, 7, 10, 11, 12, 13, 14, 15, 16]

RF_PARAMS = dict(
    n_estimators=200,
    max_depth=20,
    min_samples_leaf=5,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)

BINARY_MCC_THRESHOLD = 0.98
MULTICLASS_MCC_THRESHOLD = 0.95
PER_CLASS_F1_THRESHOLD = 0.90


plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "font.size": 10,
})


# ---------------------------------------------------------------------------
# Step 0: Feature Universe
# ---------------------------------------------------------------------------

def load_and_filter(dataset_path):
    """Load dataset, remove excluded columns, apply variance and correlation filters."""
    df = pd.read_csv(dataset_path)
    excluded = set(METADATA_COLS + CONTEXT_COLS + LABEL_COLS)
    candidates = [c for c in df.columns if c not in excluded]

    X = df[candidates].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Variance filter
    variances = np.var(X, axis=0)
    var_mask = variances >= VARIANCE_THRESHOLD
    dropped_var = [f for f, keep in zip(candidates, var_mask) if not keep]
    candidates = [f for f, keep in zip(candidates, var_mask) if keep]
    X = X[:, var_mask]

    print(f"Variance filter: dropped {len(dropped_var)} features: {dropped_var}")
    print(f"Remaining: {len(candidates)} features")

    # Correlation filter -- for |r| > threshold, keep the one with higher MI
    corr = np.corrcoef(X, rowvar=False)
    le = LabelEncoder()
    y_mc = le.fit_transform(df["label_attack_type"].values)

    mi_scores = mutual_info_classif(X, y_mc, discrete_features=False, random_state=42)
    mi_lookup = dict(zip(candidates, mi_scores))

    to_drop = set()
    n = len(candidates)
    for i in range(n):
        if candidates[i] in to_drop:
            continue
        for j in range(i + 1, n):
            if candidates[j] in to_drop:
                continue
            if abs(corr[i, j]) > CORRELATION_THRESHOLD:
                drop = candidates[j] if mi_lookup[candidates[i]] >= mi_lookup[candidates[j]] else candidates[i]
                keep = candidates[i] if drop == candidates[j] else candidates[j]
                to_drop.add(drop)
                print(f"Correlation filter: |r|={abs(corr[i,j]):.4f} between "
                      f"{candidates[i]} and {candidates[j]} -> drop {drop} (keep {keep})")

    final_features = [f for f in candidates if f not in to_drop]
    print(f"\nFinal feature universe: {len(final_features)} features")

    # Categorize
    categorized = {}
    uncategorized = []
    for f in final_features:
        placed = False
        for cat, members in FEATURE_CATEGORIES.items():
            if f in members:
                categorized.setdefault(cat, []).append(f)
                placed = True
                break
        if not placed:
            uncategorized.append(f)

    print("\nFeature categories:")
    for cat, feats in categorized.items():
        print(f"  {cat}: {feats}")
    if uncategorized:
        print(f"  uncategorized: {uncategorized}")

    config = {
        "features": final_features,
        "categories": categorized,
        "dropped_variance": dropped_var,
        "dropped_correlation": list(to_drop),
        "n_features": len(final_features),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config_path = OUTPUT_DIR / "feature_universe.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\nSaved: {config_path}")

    return config


# ---------------------------------------------------------------------------
# Step 1: Dual Feature Ranking
# ---------------------------------------------------------------------------

def compute_rankings(features):
    """Compute ANOVA F-score and MI rankings for binary and multiclass targets."""
    train = pd.read_csv(DATASET_DIR / "train.csv")
    X = train[features].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    le = LabelEncoder()
    y_bin = train["label_binary"].values
    y_mc = le.fit_transform(train["label_attack_type"].values)

    results = {}
    for target_name, y in [("binary", y_bin), ("multiclass", y_mc)]:
        print(f"\n--- Ranking: {target_name} ---")

        f_scores, _ = f_classif(X, y)
        f_scores = np.where(np.isfinite(f_scores), f_scores, 0.0)
        f_scores = np.where(np.isnan(f_scores), 0.0, f_scores)
        f_scores = np.minimum(f_scores, ANOVA_F_CAP)

        mi_scores = mutual_info_classif(
            X, y, discrete_features=False, random_state=42, n_neighbors=5
        )

        # Rank (1 = best)
        anova_ranks = len(features) - np.argsort(np.argsort(f_scores))
        mi_ranks = len(features) - np.argsort(np.argsort(mi_scores))
        combined_ranks = (anova_ranks + mi_ranks) / 2.0

        rows = []
        for i, feat in enumerate(features):
            rows.append({
                "feature": feat,
                "anova_f": float(f_scores[i]),
                "anova_rank": int(anova_ranks[i]),
                "mi_score": float(mi_scores[i]),
                "mi_rank": int(mi_ranks[i]),
                "combined_rank": float(combined_ranks[i]),
            })

        df_rank = pd.DataFrame(rows).sort_values("combined_rank")
        csv_path = OUTPUT_DIR / f"rankings_{target_name}.csv"
        df_rank.to_csv(csv_path, index=False)

        print(f"Top features ({target_name}):")
        for _, row in df_rank.head(10).iterrows():
            print(f"  {row['feature']:30s}  ANOVA_rank={int(row['anova_rank']):2d}  "
                  f"MI_rank={int(row['mi_rank']):2d}  combined={row['combined_rank']:.1f}")

        results[target_name] = df_rank

    # Save combined JSON
    rankings_json = {}
    for target_name, df_rank in results.items():
        rankings_json[target_name] = df_rank.to_dict(orient="records")

    json_path = OUTPUT_DIR / "rankings.json"
    with open(json_path, "w") as f:
        json.dump(rankings_json, f, indent=2)
    print(f"\nSaved: {json_path}")

    return results


# ---------------------------------------------------------------------------
# Step 2: Per-Class Discriminability
# ---------------------------------------------------------------------------

def per_class_analysis(features):
    """One-vs-rest ANOVA for each attack type. Produces a heatmap."""
    train = pd.read_csv(DATASET_DIR / "train.csv")
    X = train[features].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    attack_types = sorted(train["label_attack_type"].unique())
    attack_types = [a for a in attack_types if a != "Benign"]

    rows = []
    for attack in attack_types:
        y_ovr = (train["label_attack_type"] == attack).astype(int).values
        f_scores, _ = f_classif(X, y_ovr)
        f_scores = np.where(np.isfinite(f_scores), f_scores, 0.0)
        f_scores = np.where(np.isnan(f_scores), 0.0, f_scores)
        f_scores = np.minimum(f_scores, ANOVA_F_CAP)
        rows.append(dict(zip(features, f_scores)))

    df_disc = pd.DataFrame(rows, index=attack_types)

    csv_path = OUTPUT_DIR / "per_class_discriminability.csv"
    df_disc.to_csv(csv_path)

    # Normalize per row for heatmap visualization (0-1 scale)
    df_norm = df_disc.div(df_disc.max(axis=1), axis=0)

    fig, ax = plt.subplots(figsize=(max(10, len(features) * 0.55), len(attack_types) * 0.5 + 1.5))
    im = ax.imshow(df_norm.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(features)))
    ax.set_xticklabels(features, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(attack_types)))
    ax.set_yticklabels(attack_types, fontsize=9)
    ax.set_title("Per-Class Feature Discriminability (Row-Normalized ANOVA F-score)")
    fig.colorbar(im, ax=ax, shrink=0.6, label="Normalized F-score")
    plt.tight_layout()

    fig_path = FIGURES_DIR / "discriminability_heatmap.png"
    fig.savefig(fig_path)
    plt.close(fig)

    print(f"\nPer-class discriminability analysis:")
    for attack in attack_types:
        top3 = df_disc.loc[attack].nlargest(3)
        top3_str = ", ".join(f"{k} ({v:.0f})" for k, v in top3.items())
        print(f"  {attack:25s} -> {top3_str}")

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {fig_path}")

    return df_disc


# ---------------------------------------------------------------------------
# Step 3: Top-k Evaluation
# ---------------------------------------------------------------------------

def evaluate_topk(features, rankings):
    """Evaluate top-k feature subsets with grouped CV on train.csv."""
    train = pd.read_csv(DATASET_DIR / "train.csv")
    groups = train["scenario_id"].astype(str) + "_" + train["node_id"].astype(str)

    le = LabelEncoder()
    le.fit(train["label_attack_type"])
    class_names = list(le.classes_)

    results = {}

    for target_name in ["binary", "multiclass"]:
        label_col = "label_binary" if target_name == "binary" else "label_attack_type"
        y = train[label_col].values
        if target_name == "multiclass":
            y_encoded = le.transform(y)
        else:
            y_encoded = y.astype(int)

        ranked_features = rankings[target_name].sort_values("combined_rank")["feature"].tolist()
        k_list = [k for k in K_VALUES if k <= len(features)] + [len(features)]
        k_list = sorted(set(k_list))

        print(f"\n--- Top-k evaluation: {target_name} ---")
        print(f"k values: {k_list}")

        rows = []
        for k in k_list:
            selected = ranked_features[:k]
            X = train[selected].values.astype(np.float64)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

            sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)

            fold_f1, fold_mcc, fold_acc = [], [], []
            all_y_true, all_y_pred = [], []

            for train_idx, val_idx in sgkf.split(X, y_encoded, groups=groups):
                X_tr, X_va = X[train_idx], X[val_idx]
                y_tr, y_va = y_encoded[train_idx], y_encoded[val_idx]

                clf = RandomForestClassifier(**RF_PARAMS)
                clf.fit(X_tr, y_tr)
                y_pred = clf.predict(X_va)

                fold_f1.append(f1_score(y_va, y_pred, average="macro", zero_division=0))
                fold_mcc.append(matthews_corrcoef(y_va, y_pred))
                fold_acc.append(accuracy_score(y_va, y_pred))

                if target_name == "multiclass":
                    all_y_true.extend(y_va.tolist())
                    all_y_pred.extend(y_pred.tolist())

            row = {
                "k": k,
                "features_used": ", ".join(selected),
                "f1_mean": np.mean(fold_f1),
                "f1_std": np.std(fold_f1),
                "mcc_mean": np.mean(fold_mcc),
                "mcc_std": np.std(fold_mcc),
                "acc_mean": np.mean(fold_acc),
                "acc_std": np.std(fold_acc),
            }

            if target_name == "multiclass" and all_y_true:
                n_classes = len(le.classes_)
                per_class = f1_score(
                    all_y_true, all_y_pred, labels=list(range(n_classes)),
                    average=None, zero_division=0,
                )
                for i, cn in enumerate(class_names):
                    row[f"f1_{cn}"] = per_class[i]

            rows.append(row)
            print(f"  k={k:3d}  F1={np.mean(fold_f1):.4f}+/-{np.std(fold_f1):.4f}  "
                  f"MCC={np.mean(fold_mcc):.4f}+/-{np.std(fold_mcc):.4f}  "
                  f"Acc={np.mean(fold_acc):.4f}")

        df_topk = pd.DataFrame(rows)
        csv_path = OUTPUT_DIR / f"topk_{target_name}.csv"
        df_topk.to_csv(csv_path, index=False)
        results[target_name] = df_topk

    # Plot
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, target_name in zip(axes, ["binary", "multiclass"]):
        df_topk = results[target_name]
        ax.errorbar(df_topk["k"], df_topk["f1_mean"], yerr=df_topk["f1_std"],
                     marker="o", label="Macro F1", capsize=3)
        ax.errorbar(df_topk["k"], df_topk["mcc_mean"], yerr=df_topk["mcc_std"],
                     marker="s", label="MCC", capsize=3)
        ax.set_xlabel("Number of Features (k)")
        ax.set_ylabel("Score")
        ax.set_title(f"Top-k Feature Evaluation ({target_name.title()})")
        ax.legend()
        ax.set_ylim(0.5, 1.05)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig_path = FIGURES_DIR / "topk_curves.png"
    fig.savefig(fig_path)
    plt.close(fig)
    print(f"\nSaved: {fig_path}")

    return results


# ---------------------------------------------------------------------------
# Step 4: Final Subset Selection
# ---------------------------------------------------------------------------

def select_final_subsets(features, rankings, topk_results):
    """Select minimal feature subsets meeting performance thresholds."""
    selected = {}

    for target_name in ["binary", "multiclass"]:
        df_topk = topk_results[target_name]
        ranked_features = rankings[target_name].sort_values("combined_rank")["feature"].tolist()
        max_mcc = df_topk["mcc_mean"].max()

        threshold = BINARY_MCC_THRESHOLD if target_name == "binary" else MULTICLASS_MCC_THRESHOLD

        best_k = None
        for _, row in df_topk.iterrows():
            k = int(row["k"])
            mcc = row["mcc_mean"]

            if mcc < max_mcc * threshold:
                continue

            if target_name == "multiclass":
                class_f1_cols = [c for c in df_topk.columns
                                 if c.startswith("f1_") and c not in ("f1_mean", "f1_std")]
                min_class_f1 = min(row[c] for c in class_f1_cols)
                if min_class_f1 < PER_CLASS_F1_THRESHOLD:
                    continue

            best_k = k
            break

        if best_k is None:
            best_k = int(df_topk["k"].max())
            print(f"  WARNING: No k met thresholds for {target_name}, using all features")

        best_row = df_topk[df_topk["k"] == best_k].iloc[0]
        chosen_features = ranked_features[:best_k]

        result = {
            "target": target_name,
            "k": best_k,
            "features": chosen_features,
            "metrics": {
                "f1_mean": float(best_row["f1_mean"]),
                "f1_std": float(best_row["f1_std"]),
                "mcc_mean": float(best_row["mcc_mean"]),
                "mcc_std": float(best_row["mcc_std"]),
                "acc_mean": float(best_row["acc_mean"]),
            },
        }

        if target_name == "multiclass":
            class_f1_cols = [c for c in df_topk.columns
                             if c.startswith("f1_") and c not in ("f1_mean", "f1_std")]
            result["per_class_f1"] = {
                c.replace("f1_", ""): float(best_row[c]) for c in class_f1_cols
            }

        selected[target_name] = result

        json_path = OUTPUT_DIR / f"selected_features_{target_name}.json"
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"\n{target_name.title()} selection: k={best_k}")
        print(f"  Features: {chosen_features}")
        print(f"  Macro F1: {result['metrics']['f1_mean']:.4f}")
        print(f"  MCC: {result['metrics']['mcc_mean']:.4f}")

    return selected


# ---------------------------------------------------------------------------
# Step 5: SHAP Analysis
# ---------------------------------------------------------------------------

def run_shap_analysis(selected):
    """Train final model and compute SHAP values for interpretability."""
    try:
        import shap
    except ImportError:
        print("SHAP not installed. Run: pip install shap")
        return

    train = pd.read_csv(DATASET_DIR / "train.csv")
    val = pd.read_csv(DATASET_DIR / "val.csv")

    mc_features = selected["multiclass"]["features"]
    le = LabelEncoder()
    y_train = le.fit_transform(train["label_attack_type"].values)
    class_names = list(le.classes_)

    X_train = train[mc_features].values.astype(np.float64)
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)

    clf = RandomForestClassifier(**RF_PARAMS)
    clf.fit(X_train, y_train)

    # Stratified sample from val for SHAP (up to 500 rows)
    val_sample = val.groupby("label_attack_type", group_keys=False).apply(
        lambda x: x.sample(n=min(len(x), 40), random_state=42)
    )
    X_val = val_sample[mc_features].values.astype(np.float64)
    X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)

    print(f"\nComputing SHAP values on {len(X_val)} validation samples...")
    explainer = shap.TreeExplainer(clf)
    shap_values_raw = explainer.shap_values(X_val)

    # Normalize shape: ensure list-of-arrays format [class][samples, features]
    if isinstance(shap_values_raw, np.ndarray) and shap_values_raw.ndim == 3:
        # Shape (n_samples, n_features, n_classes) -> list of (n_samples, n_features)
        shap_values = [shap_values_raw[:, :, i] for i in range(shap_values_raw.shape[2])]
    elif isinstance(shap_values_raw, list):
        shap_values = shap_values_raw
    else:
        shap_values = [shap_values_raw]

    # Global summary (beeswarm)
    fig_path = FIGURES_DIR / "shap_summary.png"
    shap.summary_plot(
        shap_values, X_val, feature_names=mc_features,
        class_names=class_names, show=False, max_display=len(mc_features),
    )
    plt.tight_layout()
    plt.savefig(fig_path)
    plt.close("all")
    print(f"Saved: {fig_path}")

    # Bar plot (mean |SHAP|)
    fig_path = FIGURES_DIR / "shap_bar.png"
    shap.summary_plot(
        shap_values, X_val, feature_names=mc_features,
        class_names=class_names, plot_type="bar", show=False,
        max_display=len(mc_features),
    )
    plt.tight_layout()
    plt.savefig(fig_path)
    plt.close("all")
    print(f"Saved: {fig_path}")

    # Per-domain bar plots: network attacks vs vehicular attacks
    network_attacks = ["UDPFlood", "ICMPFlood", "SYNFlood", "HTTPFlood", "SlowDoS"]
    vehicular_attacks = ["PositionSpoof", "RandomPosition", "Replay",
                         "FalseDataInjection", "Sybil", "VehicularDoS"]

    sample_labels = val_sample["label_attack_type"].values

    for domain_name, attack_list in [("network_attacks", network_attacks),
                                      ("vehicular_attacks", vehicular_attacks)]:
        class_indices = [class_names.index(a) for a in attack_list if a in class_names]
        if not class_indices:
            continue

        domain_mask = np.isin(sample_labels, attack_list)
        if domain_mask.sum() == 0:
            continue

        domain_importance = np.zeros(len(mc_features))
        for ci in class_indices:
            domain_importance += np.abs(shap_values[ci][domain_mask]).mean(axis=0)
        domain_importance /= len(class_indices)

        sorted_idx = np.argsort(domain_importance)
        sorted_names = [mc_features[i] for i in sorted_idx]
        sorted_vals = domain_importance[sorted_idx]

        fig, ax = plt.subplots(figsize=(8, 6))
        y_pos = np.arange(len(sorted_names))
        ax.barh(y_pos, sorted_vals)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(sorted_names, fontsize=8)
        ax.set_xlabel("Mean |SHAP value|")
        ax.set_title(f"Feature Importance: {domain_name.replace('_', ' ').title()}")
        plt.tight_layout()

        fig_path = FIGURES_DIR / f"shap_{domain_name}.png"
        fig.savefig(fig_path)
        plt.close(fig)
        print(f"Saved: {fig_path}")


# ---------------------------------------------------------------------------
# Step 6: Report Generation
# ---------------------------------------------------------------------------

def generate_report(config, rankings, discriminability, topk_results, selected):
    """Generate human-readable summary as RESULTS.md."""
    lines = []
    lines.append("# Feature Engineering Results\n")

    lines.append("## Feature Universe\n")
    lines.append(f"Starting from 39 dataset columns, after removing metadata (5), "
                 f"context (4), labels (2), zero-variance ({len(config['dropped_variance'])}), "
                 f"and correlated ({len(config['dropped_correlation'])}), "
                 f"**{config['n_features']} informative features** remain.\n")

    lines.append("| Category | Features |")
    lines.append("|---|---|")
    for cat, feats in config["categories"].items():
        lines.append(f"| {cat} | {', '.join(feats)} |")
    lines.append("")

    lines.append(f"**Dropped (zero-variance):** {', '.join(config['dropped_variance'])}\n")
    lines.append(f"**Dropped (correlation > {CORRELATION_THRESHOLD}):** "
                 f"{', '.join(config['dropped_correlation'])}\n")

    for target_name in ["binary", "multiclass"]:
        lines.append(f"## Rankings: {target_name.title()}\n")
        df_rank = rankings[target_name].head(15)
        lines.append("| Rank | Feature | ANOVA F | MI Score |")
        lines.append("|---|---|---|---|")
        for _, row in df_rank.iterrows():
            anova_display = f"{min(row['anova_f'], ANOVA_F_CAP):.1f}"
            lines.append(f"| {row['combined_rank']:.1f} | {row['feature']} | "
                         f"{anova_display} | {row['mi_score']:.4f} |")
        lines.append("")

    for target_name in ["binary", "multiclass"]:
        lines.append(f"## Top-k Evaluation: {target_name.title()}\n")
        df_topk = topk_results[target_name]
        lines.append("| k | Macro F1 | MCC | Accuracy |")
        lines.append("|---|---|---|---|")
        for _, row in df_topk.iterrows():
            lines.append(f"| {int(row['k'])} | {row['f1_mean']:.4f} +/- {row['f1_std']:.4f} | "
                         f"{row['mcc_mean']:.4f} +/- {row['mcc_std']:.4f} | "
                         f"{row['acc_mean']:.4f} |")
        lines.append("")

    for target_name in ["binary", "multiclass"]:
        sel = selected[target_name]
        lines.append(f"## Selected Features: {target_name.title()} (k={sel['k']})\n")
        for i, f in enumerate(sel["features"], 1):
            lines.append(f"{i}. `{f}`")
        lines.append(f"\nMacro F1: {sel['metrics']['f1_mean']:.4f}, "
                     f"MCC: {sel['metrics']['mcc_mean']:.4f}\n")

    report_path = OUTPUT_DIR / "RESULTS.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nSaved: {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CV2X-IDS Feature Selection Pipeline")
    parser.add_argument("--step", type=str, default=None,
                        choices=["universe", "rankings", "discriminability",
                                 "topk", "select", "shap", "report"],
                        help="Run a single step (default: run all)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    dataset_path = DATASET_DIR / "dataset.csv"
    run_all = args.step is None

    # Step 0
    if run_all or args.step == "universe":
        print("=" * 70)
        print("STEP 0: Feature Universe Definition")
        print("=" * 70)
        config = load_and_filter(dataset_path)
    else:
        config = json.loads((OUTPUT_DIR / "feature_universe.json").read_text())

    features = config["features"]

    # Step 1
    if run_all or args.step == "rankings":
        print("\n" + "=" * 70)
        print("STEP 1: Dual Feature Ranking (ANOVA + MI)")
        print("=" * 70)
        rankings = compute_rankings(features)
    else:
        rankings = {}
        for target in ["binary", "multiclass"]:
            p = OUTPUT_DIR / f"rankings_{target}.csv"
            if p.exists():
                rankings[target] = pd.read_csv(p)

    # Step 2
    if run_all or args.step == "discriminability":
        print("\n" + "=" * 70)
        print("STEP 2: Per-Class Discriminability Analysis")
        print("=" * 70)
        discriminability = per_class_analysis(features)
    else:
        p = OUTPUT_DIR / "per_class_discriminability.csv"
        discriminability = pd.read_csv(p, index_col=0) if p.exists() else None

    # Step 3
    if run_all or args.step == "topk":
        print("\n" + "=" * 70)
        print("STEP 3: Top-k Feature Subset Evaluation")
        print("=" * 70)
        topk_results = evaluate_topk(features, rankings)
    else:
        topk_results = {}
        for target in ["binary", "multiclass"]:
            p = OUTPUT_DIR / f"topk_{target}.csv"
            if p.exists():
                topk_results[target] = pd.read_csv(p)

    # Step 4
    if run_all or args.step == "select":
        print("\n" + "=" * 70)
        print("STEP 4: Final Feature Subset Selection")
        print("=" * 70)
        selected = select_final_subsets(features, rankings, topk_results)
    else:
        selected = {}
        for target in ["binary", "multiclass"]:
            p = OUTPUT_DIR / f"selected_features_{target}.json"
            if p.exists():
                selected[target] = json.loads(p.read_text())

    # Step 5
    if run_all or args.step == "shap":
        print("\n" + "=" * 70)
        print("STEP 5: SHAP Interpretability Analysis")
        print("=" * 70)
        run_shap_analysis(selected)

    # Step 6
    if run_all or args.step == "report":
        print("\n" + "=" * 70)
        print("STEP 6: Report Generation")
        print("=" * 70)
        generate_report(config, rankings, discriminability, topk_results, selected)

    print("\n" + "=" * 70)
    print("Feature Engineering Pipeline Complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
