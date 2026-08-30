#!/usr/bin/env python3
"""
visualise.py -- Capstone: Cybersecurity for Connected Cars (v3)

Generates 4 analysis charts from dataset.csv:
1. Feature correlation heatmap
2. Class distribution bar chart
3. Feature importance (from RF)
4. t-SNE 2D projection by attack type
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.manifold import TSNE

warnings.filterwarnings("ignore")

METADATA_COLS = {"scenario_id", "node_id", "window_id", "window_start", "window_end"}
CONTEXT_COLS = {"true_speed_mean", "true_speed_std", "distance_to_gnb", "region_id"}
LABEL_COLS = {"label_binary", "label_attack_type"}
EXCLUDED_COLS = METADATA_COLS | CONTEXT_COLS | LABEL_COLS


def _load_features():
    """Load feature list from feature_universe.json if available, else derive from dataset columns."""
    fe_universe = Path(__file__).resolve().parent.parent.parent / "feature-engineering" / "output" / "feature_universe.json"
    if fe_universe.exists():
        with open(fe_universe) as f:
            return json.load(f)["features"]
    return None


FEATURES = _load_features()


def _get_features(df):
    """Return model features available in the dataframe."""
    if FEATURES is not None:
        return [f for f in FEATURES if f in df.columns]
    return [c for c in df.columns if c not in EXCLUDED_COLS]


def plot_correlation_heatmap(df, output_dir):
    """Feature correlation heatmap."""
    available = _get_features(df)
    corr = df[available].corr()

    fig, ax = plt.subplots(figsize=(14, 12))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(available)))
    ax.set_yticks(range(len(available)))
    ax.set_xticklabels(available, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(available, fontsize=7)
    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("Feature Correlation Matrix", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/chart_correlation.png", dpi=150)
    plt.close()
    print("  Saved chart_correlation.png")


def plot_class_distribution(df, output_dir):
    """Class distribution bar chart."""
    counts = df["label_attack_type"].value_counts().sort_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Multi-class
    colors = plt.cm.tab20(np.linspace(0, 1, len(counts)))
    bars = ax1.barh(range(len(counts)), counts.values, color=colors)
    ax1.set_yticks(range(len(counts)))
    ax1.set_yticklabels(counts.index, fontsize=9)
    ax1.set_xlabel("Number of Windows")
    ax1.set_title("Class Distribution (Multi-class)")
    for bar, val in zip(bars, counts.values):
        ax1.text(val + 5, bar.get_y() + bar.get_height()/2,
                 str(val), va="center", fontsize=8)

    # Binary
    binary_counts = df["label_binary"].value_counts().sort_index()
    labels = ["Benign", "Attack"]
    ax2.bar(labels, binary_counts.values, color=["#2196F3", "#F44336"])
    ax2.set_ylabel("Number of Windows")
    ax2.set_title("Class Distribution (Binary)")
    for i, val in enumerate(binary_counts.values):
        ax2.text(i, val + 5, str(val), ha="center", fontsize=10)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/chart_distribution.png", dpi=150)
    plt.close()
    print("  Saved chart_distribution.png")


def plot_feature_importance(df, output_dir):
    """Random Forest feature importance."""
    available = _get_features(df)
    X = df[available].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    le = LabelEncoder()
    y = le.fit_transform(df["label_attack_type"].values)

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=20, min_samples_leaf=5,
        random_state=42, n_jobs=-1
    )
    clf.fit(X, y)

    importances = clf.feature_importances_
    sorted_idx = np.argsort(importances)

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(range(len(sorted_idx)), importances[sorted_idx], color="#4CAF50")
    ax.set_yticks(range(len(sorted_idx)))
    ax.set_yticklabels(np.array(available)[sorted_idx], fontsize=8)
    ax.set_xlabel("Importance")
    ax.set_title("Random Forest Feature Importance (Multi-class)")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/chart_importance.png", dpi=150)
    plt.close()
    print("  Saved chart_importance.png")


def plot_tsne(df, output_dir):
    """t-SNE 2D projection colored by attack type."""
    available = _get_features(df)
    X = df[available].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Sample if too large
    max_samples = 2000
    if len(X) > max_samples:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(X), max_samples, replace=False)
        X = X[idx]
        labels = df["label_attack_type"].values[idx]
    else:
        labels = df["label_attack_type"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    tsne = TSNE(n_components=2, perplexity=30, random_state=42, n_iter=1000)
    X_2d = tsne.fit_transform(X_scaled)

    unique_labels = sorted(set(labels))
    colors = plt.cm.tab20(np.linspace(0, 1, len(unique_labels)))

    fig, ax = plt.subplots(figsize=(10, 8))
    for i, label in enumerate(unique_labels):
        mask = labels == label
        ax.scatter(X_2d[mask, 0], X_2d[mask, 1],
                   c=[colors[i]], label=label, s=15, alpha=0.7)
    ax.legend(fontsize=8, loc="best", markerscale=2)
    ax.set_title("t-SNE Projection by Attack Type")
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    plt.tight_layout()
    plt.savefig(f"{output_dir}/chart_tsne.png", dpi=150)
    plt.close()
    print("  Saved chart_tsne.png")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "output/dataset.csv"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"

    print(f"Loading {path}...")
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} rows\n")

    print("Generating charts...")
    plot_correlation_heatmap(df, output_dir)
    plot_class_distribution(df, output_dir)
    plot_feature_importance(df, output_dir)
    plot_tsne(df, output_dir)
    print("\nAll charts saved.")


if __name__ == "__main__":
    main()
