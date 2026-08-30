#!/usr/bin/env python3
"""
run_dropout_check.py -- Targeted robustness check: re-run the 2 worst FL
configurations with dropout=0.2 and compare against the original results.

Configs tested:
  1. C=5, α=0.1, E=1 (worst Dirichlet)
  2. C=5, scenario, E=1 (worst scenario-based)
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from config import (
    BATCH_SIZE, CLASS_ORDER, DATA_DIR, FEATURES,
    GLOBAL_ROUNDS, LABEL_COL, LR, N_CLASSES, OUT_DIR,
    RANDOM_STATE, SCENARIO_GRID,
)

DROPOUT = 0.2
SEEDS = [42, 123, 456]
EXPERIMENTS = [
    {"partition": "dirichlet", "n_clients": 5, "alpha": 0.1, "local_epochs": 1},
    {"partition": "scenario",  "n_clients": 5, "alpha": None, "local_epochs": 1},
]


def run():
    from centralized import load_scaler_params, load_split
    from fedavg import FedAvgServer
    from partition import (
        partition_by_scenario, partition_dirichlet,
        partition_report, plot_partition_heatmap,
    )
    from evaluate import compute_metrics, plot_convergence, plot_confusion

    scaler_mean, scaler_scale = load_scaler_params()
    X_val, y_val = load_split("val", scaler_mean, scaler_scale)
    X_test, y_test = load_split("test", scaler_mean, scaler_scale)
    train_df = pd.read_csv(DATA_DIR / "train.csv")

    dropout_dir = OUT_DIR / "dropout_check"
    dropout_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    for exp in EXPERIMENTS:
        for seed in SEEDS:
            partition_type = exp["partition"]
            n_clients = exp["n_clients"]
            alpha = exp["alpha"]
            local_epochs = exp["local_epochs"]

            if partition_type == "dirichlet":
                exp_name = f"{n_clients}c_{alpha}a_{local_epochs}e_{seed}s_drop{DROPOUT}"
            else:
                exp_name = f"{n_clients}c_scenario_{local_epochs}e_{seed}s_drop{DROPOUT}"

            exp_dir = dropout_dir / exp_name
            exp_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n--- {exp_name} ---")

            if partition_type == "dirichlet":
                client_dfs = partition_dirichlet(train_df, n_clients, alpha, seed)
            else:
                client_dfs = partition_by_scenario(train_df, n_clients, seed)

            meta = partition_report(client_dfs, exp_dir / "partition_meta.json")
            plot_partition_heatmap(meta, exp_dir / "partition_heatmap.png")

            server = FedAvgServer(dropout=DROPOUT)
            clients = server.prepare_clients(client_dfs, scaler_mean, scaler_scale)

            round_metrics, final_metrics, comm_bytes, test_pred = server.run(
                clients, X_val, y_val, X_test, y_test,
                global_rounds=GLOBAL_ROUNDS,
                local_epochs=local_epochs,
                lr=LR,
                batch_size=BATCH_SIZE,
            )

            with open(exp_dir / "round_metrics.json", "w") as f:
                json.dump(round_metrics, f, indent=2)

            result = {
                "experiment": exp_name,
                "partition_type": partition_type,
                "n_clients": n_clients,
                "alpha": alpha,
                "local_epochs": local_epochs,
                "seed": seed,
                "dropout": DROPOUT,
                "global_rounds": GLOBAL_ROUNDS,
                "comm_bytes": comm_bytes,
                "final_test": final_metrics,
            }
            with open(exp_dir / "final_metrics.json", "w") as f:
                json.dump(result, f, indent=2)

            plot_convergence(
                round_metrics, exp_dir / "convergence.png",
                title=f"FedAvg+Dropout({DROPOUT}): {exp_name}",
            )
            plot_confusion(
                y_test, test_pred, exp_dir / "confusion.png",
                title=f"Confusion — {exp_name}",
            )

            print(f"  F1={final_metrics['macro_f1']:.4f}  "
                  f"MCC={final_metrics['mcc']:.4f}")

            all_results.append(result)

    # Compare against original results
    print("\n" + "=" * 70)
    print("DROPOUT ROBUSTNESS CHECK — COMPARISON")
    print("=" * 70)

    rows = []
    for exp in EXPERIMENTS:
        partition_type = exp["partition"]
        n_clients = exp["n_clients"]
        alpha = exp["alpha"]
        local_epochs = exp["local_epochs"]

        orig_f1s = []
        drop_f1s = []
        orig_mccs = []
        drop_mccs = []

        for seed in SEEDS:
            if partition_type == "dirichlet":
                orig_name = f"{n_clients}c_{alpha}a_{local_epochs}e_{seed}s"
            else:
                orig_name = f"{n_clients}c_scenario_{local_epochs}e_{seed}s"

            orig_path = OUT_DIR / "experiments" / orig_name / "final_metrics.json"
            if orig_path.exists():
                with open(orig_path) as f:
                    orig = json.load(f)
                orig_f1s.append(orig["final_test"]["macro_f1"])
                orig_mccs.append(orig["final_test"]["mcc"])

            drop_result = [r for r in all_results
                           if r["partition_type"] == partition_type
                           and r["seed"] == seed]
            if drop_result:
                drop_f1s.append(drop_result[0]["final_test"]["macro_f1"])
                drop_mccs.append(drop_result[0]["final_test"]["mcc"])

        config_label = (f"C={n_clients}, α={alpha}, E={local_epochs}"
                        if partition_type == "dirichlet"
                        else f"C={n_clients}, scenario, E={local_epochs}")

        row = {
            "config": config_label,
            "orig_f1": f"{np.mean(orig_f1s):.4f}±{np.std(orig_f1s):.4f}",
            "drop_f1": f"{np.mean(drop_f1s):.4f}±{np.std(drop_f1s):.4f}",
            "delta_f1": f"{np.mean(drop_f1s) - np.mean(orig_f1s):+.4f}",
            "orig_mcc": f"{np.mean(orig_mccs):.4f}±{np.std(orig_mccs):.4f}",
            "drop_mcc": f"{np.mean(drop_mccs):.4f}±{np.std(drop_mccs):.4f}",
            "delta_mcc": f"{np.mean(drop_mccs) - np.mean(orig_mccs):+.4f}",
        }
        rows.append(row)

        print(f"\n  {config_label}:")
        print(f"    Original:    F1={row['orig_f1']}  MCC={row['orig_mcc']}")
        print(f"    Dropout=0.2: F1={row['drop_f1']}  MCC={row['drop_mcc']}")
        print(f"    Delta:       F1={row['delta_f1']}       MCC={row['delta_mcc']}")

    comparison_df = pd.DataFrame(rows)
    comparison_df.to_csv(dropout_dir / "comparison.csv", index=False)
    print(f"\n  Saved comparison to {dropout_dir}/comparison.csv")


if __name__ == "__main__":
    t0 = time.time()
    run()
    print(f"\nTotal time: {time.time() - t0:.0f}s")
