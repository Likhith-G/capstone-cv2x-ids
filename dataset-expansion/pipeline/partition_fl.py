#!/usr/bin/env python3
"""
partition_fl.py -- Capstone: Cybersecurity for Connected Cars (v3)

Creates non-IID Federated Learning partitions using Dirichlet distribution.
Each partition represents one FL client (edge RSU).
"""

import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path


def dirichlet_partition(labels, n_clients, alpha=0.5, seed=42):
    """
    Split label indices into n_clients groups using Dirichlet distribution.
    Lower alpha = more heterogeneous (more non-IID).

    Returns: list of n_clients index arrays.
    """
    rng = np.random.default_rng(seed)
    unique_labels = np.unique(labels)
    n_classes = len(unique_labels)

    client_indices = [[] for _ in range(n_clients)]

    for c in unique_labels:
        class_mask = np.where(labels == c)[0]
        rng.shuffle(class_mask)

        # Sample proportions from Dir(alpha)
        proportions = rng.dirichlet([alpha] * n_clients)
        # Convert proportions to actual counts
        proportions = (proportions * len(class_mask)).astype(int)
        # Fix rounding so total matches
        proportions[-1] = len(class_mask) - proportions[:-1].sum()

        splits = np.split(class_mask, np.cumsum(proportions[:-1]))
        for i in range(n_clients):
            client_indices[i].extend(splits[i].tolist())

    # Shuffle within each client
    for i in range(n_clients):
        rng.shuffle(client_indices[i])

    return client_indices


def main():
    path       = sys.argv[1] if len(sys.argv) > 1 else "v3_output/dataset_v3.csv"
    n_clients  = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    alpha      = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    output_dir = sys.argv[4] if len(sys.argv) > 4 else "v3_output"

    print(f"Loading {path}...")
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} rows")
    print(f"Clients: {n_clients}, Alpha: {alpha}\n")

    labels = df["label_attack_type"].values
    client_indices = dirichlet_partition(labels, n_clients, alpha)

    print(f"{'Client':>8} {'Rows':>8}  Label Distribution")
    print("-" * 60)

    partition_meta = {"n_clients": n_clients, "alpha": alpha, "clients": []}

    for i, indices in enumerate(client_indices):
        client_df = df.iloc[indices]
        dist = client_df["label_attack_type"].value_counts().to_dict()

        # Save partition
        out_path = Path(output_dir) / f"client_{i}.csv"
        client_df.to_csv(out_path, index=False)

        print(f"  {i:>5}  {len(indices):>8}  {dist}")

        partition_meta["clients"].append({
            "client_id": i,
            "n_rows": len(indices),
            "distribution": dist,
        })

    # Save partition metadata
    meta_path = Path(output_dir) / "partition_meta.json"
    with open(meta_path, "w") as f:
        json.dump(partition_meta, f, indent=2)

    # Verify non-IID: compute label entropy per client
    print(f"\n--- Non-IID Verification ---")
    entropies = []
    for indices in client_indices:
        client_labels = labels[indices]
        _, counts = np.unique(client_labels, return_counts=True)
        probs = counts / counts.sum()
        entropy = -np.sum(probs * np.log2(probs + 1e-12))
        entropies.append(entropy)

    max_entropy = np.log2(len(np.unique(labels)))
    print(f"Label entropy per client: {[f'{e:.2f}' for e in entropies]}")
    print(f"Max possible entropy:     {max_entropy:.2f}")
    print(f"Mean entropy:             {np.mean(entropies):.2f} "
          f"({'non-IID' if np.mean(entropies) < max_entropy * 0.8 else 'nearly IID'})")


if __name__ == "__main__":
    main()
