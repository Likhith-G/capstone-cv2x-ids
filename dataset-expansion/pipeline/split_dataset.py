#!/usr/bin/env python3
"""
split_dataset.py -- Capstone: Cybersecurity for Connected Cars

Performs a strict 70/15/15 train/val/test split on the dataset.

Splitting strategy:
  - The unit of splitting is the SCENARIO (S00-S11), not individual groups.
  - Each scenario contains a unique attack type, so splitting at the scenario
    level guarantees every attack type appears in every split.
  - Within each scenario, we split NODES (groups) into 70/15/15.
  - This ensures:
    1. No temporal leakage (all windows for a node stay together).
    2. All 12 attack types appear in train, val, AND test.
    3. Group-level integrity is preserved.
"""

import os
import sys
import json
import numpy as np
import pandas as pd


def main():
    input_csv = sys.argv[1] if len(sys.argv) > 1 else "output/dataset.csv"
    out_dir = os.path.dirname(input_csv)

    print(f"Loading {input_csv}...")
    df = pd.read_csv(input_csv)

    # Create group IDs
    df["group_id"] = df["scenario_id"] + "_" + df["node_id"].astype(str)

    print(f"Total rows: {len(df)}")
    print(f"Total groups: {df['group_id'].nunique()}")

    train_groups = []
    val_groups = []
    test_groups = []

    # Split within each scenario independently to guarantee attack type coverage
    for scenario in sorted(df["scenario_id"].unique()):
        sc_df = df[df["scenario_id"] == scenario]
        nodes = sorted(sc_df["node_id"].unique())
        n = len(nodes)

        # Separate attacker and benign nodes for this scenario
        node_labels = {}
        for nid in nodes:
            label = sc_df[sc_df["node_id"] == nid]["label_binary"].iloc[0]
            node_labels[nid] = label

        attacker_nodes = [nid for nid, lab in node_labels.items() if lab == 1]
        benign_nodes = [nid for nid, lab in node_labels.items() if lab == 0]

        # Shuffle with fixed seed for reproducibility
        rng = np.random.RandomState(42)
        rng.shuffle(attacker_nodes)
        rng.shuffle(benign_nodes)

        def split_list(lst, train_frac=0.7, val_frac=0.15):
            """Split a list into train/val/test preserving proportions."""
            n = len(lst)
            n_train = max(1, int(round(n * train_frac))) if n >= 3 else n
            n_val = max(1, int(round(n * val_frac))) if n >= 3 else 0
            # Ensure at least 1 in each split if we have enough items
            if n >= 3:
                n_test = n - n_train - n_val
                if n_test < 1:
                    n_train -= 1
                    n_test = 1
            else:
                n_test = 0
            return lst[:n_train], lst[n_train:n_train + n_val], lst[n_train + n_val:]

        # Split attackers and benign nodes separately to maintain label ratio
        atk_train, atk_val, atk_test = split_list(attacker_nodes)
        ben_train, ben_val, ben_test = split_list(benign_nodes)

        for nid in atk_train + ben_train:
            train_groups.append(f"{scenario}_{nid}")
        for nid in atk_val + ben_val:
            val_groups.append(f"{scenario}_{nid}")
        for nid in atk_test + ben_test:
            test_groups.append(f"{scenario}_{nid}")

    # Map groups back to rows
    train_df = df[df["group_id"].isin(train_groups)].copy()
    val_df = df[df["group_id"].isin(val_groups)].copy()
    test_df = df[df["group_id"].isin(test_groups)].copy()

    # Drop temporary column
    train_df.drop(columns=["group_id"], inplace=True)
    val_df.drop(columns=["group_id"], inplace=True)
    test_df.drop(columns=["group_id"], inplace=True)

    print("\n--- Split Results ---")
    print(f"Train: {len(train_df)} rows ({len(train_groups)} groups)")
    print(f"Val:   {len(val_df)} rows ({len(val_groups)} groups)")
    print(f"Test:  {len(test_df)} rows ({len(test_groups)} groups)")

    # Ratios
    total = len(train_df) + len(val_df) + len(test_df)
    print(f"\nTrain ratio: {len(train_df)/total*100:.1f}%")
    print(f"Val ratio:   {len(val_df)/total*100:.1f}%")
    print(f"Test ratio:  {len(test_df)/total*100:.1f}%")

    # Binary labels
    print(f"\nTrain labels: {train_df['label_binary'].value_counts().to_dict()}")
    print(f"Val labels:   {val_df['label_binary'].value_counts().to_dict()}")
    print(f"Test labels:  {test_df['label_binary'].value_counts().to_dict()}")

    # Attack type coverage check
    all_types = sorted(df["label_attack_type"].unique())
    train_types = sorted(train_df["label_attack_type"].unique())
    val_types = sorted(val_df["label_attack_type"].unique())
    test_types = sorted(test_df["label_attack_type"].unique())

    print(f"\nAttack type coverage:")
    print(f"  All:   {all_types}")
    print(f"  Train: {train_types}")
    print(f"  Val:   {val_types}")
    print(f"  Test:  {test_types}")

    missing_val = set(all_types) - set(val_types)
    missing_test = set(all_types) - set(test_types)
    if missing_val:
        print(f"  WARNING: Val missing: {missing_val}")
    if missing_test:
        print(f"  WARNING: Test missing: {missing_test}")
    if not missing_val and not missing_test:
        print(f"  PASS: All attack types in all splits")

    # Per-type counts
    print(f"\nPer-type counts:")
    print(f"  {'Type':25s} {'Train':>8} {'Val':>8} {'Test':>8}")
    print(f"  {'-'*55}")
    for t in all_types:
        tr = (train_df["label_attack_type"] == t).sum()
        va = (val_df["label_attack_type"] == t).sum()
        te = (test_df["label_attack_type"] == t).sum()
        print(f"  {t:25s} {tr:8d} {va:8d} {te:8d}")

    # Group leakage check
    train_set = set(train_groups)
    val_set = set(val_groups)
    test_set = set(test_groups)
    assert len(train_set & val_set) == 0, "Train-Val overlap!"
    assert len(train_set & test_set) == 0, "Train-Test overlap!"
    assert len(val_set & test_set) == 0, "Val-Test overlap!"
    print(f"\nGroup leakage check: PASS (zero overlap)")

    # Save
    train_path = os.path.join(out_dir, "train.csv")
    val_path = os.path.join(out_dir, "val.csv")
    test_path = os.path.join(out_dir, "test.csv")

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    meta = {
        "split_method": "per-scenario stratified node split (70/15/15)",
        "train_groups": sorted(train_groups),
        "val_groups": sorted(val_groups),
        "test_groups": sorted(test_groups),
    }
    with open(os.path.join(out_dir, "split_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nSaved {train_path}, {val_path}, {test_path}")


if __name__ == "__main__":
    main()
