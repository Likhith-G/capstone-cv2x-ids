#!/usr/bin/env python3
"""
partition.py -- Client partitioning for federated learning.
Two strategies:
  1. Dirichlet-based (synthetic non-IID, controlled by alpha)
  2. Scenario-based (natural non-IID, realistic RSU deployment)
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import CLASS_ORDER, LABEL_COL


def partition_dirichlet(train_df, n_clients, alpha, seed=42):
    """
    Partition train_df into n_clients subsets using Dirichlet distribution.
    Lower alpha = more heterogeneous (more non-IID).

    Enforces minimum 1 sample per class per client when possible.
    """
    rng = np.random.default_rng(seed)
    labels = train_df[LABEL_COL].values
    unique_labels = sorted(set(labels))
    assert set(unique_labels) == set(CLASS_ORDER)

    client_indices = [[] for _ in range(n_clients)]

    for cls in unique_labels:
        cls_idx = np.where(labels == cls)[0]
        rng.shuffle(cls_idx)

        proportions = rng.dirichlet([alpha] * n_clients)
        counts = (proportions * len(cls_idx)).astype(int)

        # Enforce minimum 1 per client if enough samples
        if len(cls_idx) >= n_clients:
            for i in range(n_clients):
                if counts[i] == 0:
                    # Steal from the largest
                    donor = np.argmax(counts)
                    counts[donor] -= 1
                    counts[i] = 1

        # Fix rounding
        counts[-1] = len(cls_idx) - counts[:-1].sum()

        splits = np.split(cls_idx, np.cumsum(counts[:-1]))
        for i in range(n_clients):
            client_indices[i].extend(splits[i].tolist())

    # Shuffle within each client
    for idx_list in client_indices:
        rng.shuffle(idx_list)

    client_dfs = [train_df.iloc[idx].reset_index(drop=True) for idx in client_indices]
    return client_dfs


def partition_by_scenario(train_df, n_clients, seed=42):
    """
    Assign entire scenarios to clients, simulating RSU geographic partitions.
    Each client gets a block of scenarios, so some clients may never see
    certain attack types.
    """
    rng = np.random.default_rng(seed)
    scenarios = sorted(train_df["scenario_id"].unique())
    rng.shuffle(scenarios)

    # Round-robin assignment
    client_scenarios = [[] for _ in range(n_clients)]
    for i, s in enumerate(scenarios):
        client_scenarios[i % n_clients].append(s)

    client_dfs = []
    for s_list in client_scenarios:
        subset = train_df[train_df["scenario_id"].isin(s_list)].reset_index(drop=True)
        client_dfs.append(subset)

    return client_dfs


def partition_report(client_dfs, output_path=None):
    """
    Generate per-client label distribution diagnostics.
    Returns metadata dict and optionally saves to JSON.
    """
    meta = {"n_clients": len(client_dfs), "clients": []}

    for i, df in enumerate(client_dfs):
        counts = df[LABEL_COL].value_counts()
        total = len(df)
        props = {cls: 0.0 for cls in CLASS_ORDER}
        cls_counts = {cls: 0 for cls in CLASS_ORDER}
        for cls in CLASS_ORDER:
            c = int(counts.get(cls, 0))
            cls_counts[cls] = c
            props[cls] = round(c / total, 6) if total > 0 else 0.0

        # Shannon entropy
        p = np.array([props[cls] for cls in CLASS_ORDER])
        p = p[p > 0]
        entropy = float(-np.sum(p * np.log2(p))) if len(p) > 0 else 0.0

        meta["clients"].append({
            "client_id": i,
            "n_samples": total,
            "label_counts": cls_counts,
            "label_proportions": props,
            "entropy": round(entropy, 4),
        })

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(meta, f, indent=2)

    return meta


def plot_partition_heatmap(meta, output_path):
    """Plot a heatmap of label proportions across clients."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_clients = meta["n_clients"]
    matrix = np.zeros((n_clients, len(CLASS_ORDER)))
    for i, c in enumerate(meta["clients"]):
        for j, cls in enumerate(CLASS_ORDER):
            matrix[i, j] = c["label_proportions"][cls]

    fig, ax = plt.subplots(figsize=(12, max(3, n_clients * 0.8)))
    im = ax.imshow(matrix, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(CLASS_ORDER)))
    ax.set_xticklabels([c[:10] for c in CLASS_ORDER], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n_clients))
    ax.set_yticklabels([f"Client {i}" for i in range(n_clients)])
    ax.set_xlabel("Class")
    ax.set_ylabel("Client")

    for i in range(n_clients):
        for j in range(len(CLASS_ORDER)):
            v = matrix[i, j]
            if v > 0.01:
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                        color="white" if v > 0.4 else "black")

    fig.colorbar(im, ax=ax, label="Proportion")
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
