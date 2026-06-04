#!/usr/bin/env python3
"""
fl.py -- Main entry point for the Federated Learning workstream.

Usage:
  python3 federated-learning/fl.py                      # full pipeline
  python3 federated-learning/fl.py --step centralized    # centralized baseline only
  python3 federated-learning/fl.py --step experiments    # FL experiments only
  python3 federated-learning/fl.py --step summary        # aggregate results + figures
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from config import (
    BATCH_SIZE,
    CLASS_ORDER,
    DATA_DIR,
    EXPERIMENT_GRID,
    FEATURES,
    GLOBAL_ROUNDS,
    LABEL_COL,
    LR,
    N_CLASSES,
    OUT_DIR,
    FIG_DIR,
    RANDOM_STATE,
    SCENARIO_GRID,
)


def run_centralized_baseline():
    """Step 1: Train and evaluate centralized PyTorch MLP."""
    from centralized import train_centralized
    print("=" * 70)
    print("STEP 1: CENTRALIZED PYTORCH BASELINE")
    print("=" * 70)
    model, results = train_centralized()
    f1 = results["test"]["macro_f1"]
    if f1 < 0.99:
        print(f"\n  WARNING: Centralized F1={f1:.4f} < 0.99. "
              "PyTorch model does not match sklearn baseline.")
    else:
        print(f"\n  Centralized baseline verified: test F1={f1:.4f}")
    return model, results


def run_single_experiment(
    train_df, X_val, y_val, X_test, y_test,
    scaler_mean, scaler_scale,
    n_clients, alpha, local_epochs, seed,
    partition_type="dirichlet",
):
    """Run one FL experiment configuration."""
    from fedavg import FedAvgServer
    from partition import (
        partition_by_scenario,
        partition_dirichlet,
        partition_report,
        plot_partition_heatmap,
    )
    from evaluate import plot_convergence, plot_confusion

    # Experiment directory
    if partition_type == "dirichlet":
        exp_name = f"{n_clients}c_{alpha}a_{local_epochs}e_{seed}s"
    else:
        exp_name = f"{n_clients}c_scenario_{local_epochs}e_{seed}s"
    exp_dir = OUT_DIR / "experiments" / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Experiment: {exp_name} ---")

    # Partition
    if partition_type == "dirichlet":
        client_dfs = partition_dirichlet(train_df, n_clients, alpha, seed)
    else:
        client_dfs = partition_by_scenario(train_df, n_clients, seed)

    meta = partition_report(client_dfs, exp_dir / "partition_meta.json")
    plot_partition_heatmap(meta, exp_dir / "partition_heatmap.png")

    for c in meta["clients"]:
        print(f"  Client {c['client_id']}: {c['n_samples']} samples, "
              f"entropy={c['entropy']:.2f}")

    # Run FedAvg
    server = FedAvgServer()
    clients = server.prepare_clients(client_dfs, scaler_mean, scaler_scale)

    round_metrics, final_metrics, comm_bytes, test_pred = server.run(
        clients, X_val, y_val, X_test, y_test,
        global_rounds=GLOBAL_ROUNDS,
        local_epochs=local_epochs,
        lr=LR,
        batch_size=BATCH_SIZE,
    )

    # Save round metrics
    with open(exp_dir / "round_metrics.json", "w") as f:
        json.dump(round_metrics, f, indent=2)

    # Save final metrics
    result = {
        "experiment": exp_name,
        "partition_type": partition_type,
        "n_clients": n_clients,
        "alpha": alpha if partition_type == "dirichlet" else None,
        "local_epochs": local_epochs,
        "seed": seed,
        "global_rounds": GLOBAL_ROUNDS,
        "comm_bytes": comm_bytes,
        "final_test": final_metrics,
    }
    with open(exp_dir / "final_metrics.json", "w") as f:
        json.dump(result, f, indent=2)

    # Figures
    plot_convergence(
        round_metrics, exp_dir / "convergence.png",
        title=f"FedAvg: C={n_clients}, "
              + (f"α={alpha}" if partition_type == "dirichlet" else "scenario")
              + f", E={local_epochs}, seed={seed}",
    )
    plot_confusion(
        y_test, test_pred, exp_dir / "confusion.png",
        title=f"Confusion — {exp_name}",
    )

    print(f"  Final: F1={final_metrics['macro_f1']:.4f}  "
          f"MCC={final_metrics['mcc']:.4f}  "
          f"Comm={comm_bytes / 1024:.0f} KB")

    return result


def run_all_experiments():
    """Step 2: Run the full FL experiment grid."""
    from centralized import load_scaler_params, load_split

    print("\n" + "=" * 70)
    print("STEP 2: FEDERATED LEARNING EXPERIMENTS")
    print("=" * 70)

    scaler_mean, scaler_scale = load_scaler_params()
    X_val, y_val = load_split("val", scaler_mean, scaler_scale)
    X_test, y_test = load_split("test", scaler_mean, scaler_scale)
    train_df = pd.read_csv(DATA_DIR / "train.csv")

    observed = sorted(train_df[LABEL_COL].unique())
    assert set(observed) == set(CLASS_ORDER), f"Label mismatch: {observed}"

    all_results = []
    total_start = time.time()

    # Dirichlet experiments
    n_dirichlet = (
        len(EXPERIMENT_GRID["n_clients"])
        * len(EXPERIMENT_GRID["alpha"])
        * len(EXPERIMENT_GRID["local_epochs"])
        * len(EXPERIMENT_GRID["seeds"])
    )
    # Scenario experiments
    n_scenario = (
        len(SCENARIO_GRID["n_clients"])
        * len(SCENARIO_GRID["local_epochs"])
        * len(SCENARIO_GRID["seeds"])
    )
    print(f"\nTotal experiments: {n_dirichlet} Dirichlet + {n_scenario} scenario "
          f"= {n_dirichlet + n_scenario}")

    exp_count = 0

    for n_clients in EXPERIMENT_GRID["n_clients"]:
        for alpha in EXPERIMENT_GRID["alpha"]:
            for local_epochs in EXPERIMENT_GRID["local_epochs"]:
                for seed in EXPERIMENT_GRID["seeds"]:
                    exp_count += 1
                    print(f"\n[{exp_count}/{n_dirichlet + n_scenario}]", end="")
                    result = run_single_experiment(
                        train_df, X_val, y_val, X_test, y_test,
                        scaler_mean, scaler_scale,
                        n_clients, alpha, local_epochs, seed,
                        partition_type="dirichlet",
                    )
                    all_results.append(result)

    for n_clients in SCENARIO_GRID["n_clients"]:
        for local_epochs in SCENARIO_GRID["local_epochs"]:
            for seed in SCENARIO_GRID["seeds"]:
                exp_count += 1
                print(f"\n[{exp_count}/{n_dirichlet + n_scenario}]", end="")
                result = run_single_experiment(
                    train_df, X_val, y_val, X_test, y_test,
                    scaler_mean, scaler_scale,
                    n_clients, None, local_epochs, seed,
                    partition_type="scenario",
                )
                all_results.append(result)

    elapsed = time.time() - total_start
    print(f"\n\nAll {exp_count} experiments completed in {elapsed:.0f}s")

    return all_results


def generate_summary(all_results=None):
    """Step 3: Aggregate results, generate summary tables and key figures."""
    from bandwidth import estimate_comm_cost
    from latency import profile_inference

    print("\n" + "=" * 70)
    print("STEP 3: SUMMARY AND ANALYSIS")
    print("=" * 70)

    # Load results from disk if not passed
    if all_results is None:
        all_results = []
        exp_dir = OUT_DIR / "experiments"
        for d in sorted(exp_dir.iterdir()):
            metrics_file = d / "final_metrics.json"
            if metrics_file.exists():
                with open(metrics_file) as f:
                    all_results.append(json.load(f))

    if not all_results:
        print("  No experiment results found.")
        return

    # Load centralized baseline
    cent_path = OUT_DIR / "centralized" / "metrics.json"
    cent_metrics = None
    if cent_path.exists():
        with open(cent_path) as f:
            cent_metrics = json.load(f)

    # --- Summary table ---
    rows = []
    for r in all_results:
        rows.append({
            "partition": r["partition_type"],
            "C": r["n_clients"],
            "alpha": r["alpha"] if r["alpha"] is not None else "-",
            "E": r["local_epochs"],
            "seed": r["seed"],
            "test_f1": r["final_test"]["macro_f1"],
            "test_mcc": r["final_test"]["mcc"],
            "test_acc": r["final_test"]["accuracy"],
            "comm_kb": round(r["comm_bytes"] / 1024, 1),
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "experiment_summary.csv", index=False)
    print(f"\n  Saved experiment_summary.csv ({len(df)} experiments)")

    # --- Aggregated table (mean ± std across seeds) ---
    agg_rows = []
    for partition_type in ["dirichlet", "scenario"]:
        subset = [r for r in all_results if r["partition_type"] == partition_type]
        if not subset:
            continue

        if partition_type == "dirichlet":
            group_keys = set(
                (r["n_clients"], r["alpha"], r["local_epochs"]) for r in subset
            )
            for c, a, e in sorted(group_keys):
                group = [r for r in subset
                         if r["n_clients"] == c and r["alpha"] == a
                         and r["local_epochs"] == e]
                f1s = [r["final_test"]["macro_f1"] for r in group]
                mccs = [r["final_test"]["mcc"] for r in group]
                agg_rows.append({
                    "partition": "dirichlet",
                    "C": c, "alpha": a, "E": e,
                    "f1_mean": round(np.mean(f1s), 4),
                    "f1_std": round(np.std(f1s), 4),
                    "mcc_mean": round(np.mean(mccs), 4),
                    "mcc_std": round(np.std(mccs), 4),
                    "n_seeds": len(group),
                })
        else:
            group_keys = set(
                (r["n_clients"], r["local_epochs"]) for r in subset
            )
            for c, e in sorted(group_keys):
                group = [r for r in subset
                         if r["n_clients"] == c and r["local_epochs"] == e]
                f1s = [r["final_test"]["macro_f1"] for r in group]
                mccs = [r["final_test"]["mcc"] for r in group]
                agg_rows.append({
                    "partition": "scenario",
                    "C": c, "alpha": "-", "E": e,
                    "f1_mean": round(np.mean(f1s), 4),
                    "f1_std": round(np.std(f1s), 4),
                    "mcc_mean": round(np.mean(mccs), 4),
                    "mcc_std": round(np.std(mccs), 4),
                    "n_seeds": len(group),
                })

    agg_df = pd.DataFrame(agg_rows)
    agg_df.to_csv(OUT_DIR / "aggregated_results.csv", index=False)
    print(f"  Saved aggregated_results.csv ({len(agg_df)} configurations)")

    # --- Bandwidth estimation ---
    print("\n  Communication cost analysis:")
    train_df = pd.read_csv(DATA_DIR / "train.csv")
    train_size = len(train_df)
    bw_all = {}
    for c in sorted(set(r["n_clients"] for r in all_results)):
        bw_all[c] = estimate_comm_cost(c, GLOBAL_ROUNDS, train_size)
    bw = bw_all[max(bw_all)]  # Use largest C for headline numbers
    with open(OUT_DIR / "bandwidth.json", "w") as f:
        json.dump({"configurations": {str(k): v for k, v in bw_all.items()}}, f, indent=2)
    print(f"    Model: {bw['model_params']} params = {bw['model_bytes']} bytes")
    print(f"    Centralized: {bw['centralized']['total_mb']:.4f} MB (raw data upload)")
    for c, b in sorted(bw_all.items()):
        print(f"    FL (C={c}, {GLOBAL_ROUNDS} rounds): {b['federated']['total_mb']:.4f} MB  "
              f"(ratio: {b['ratio_fl_over_centralized']:.2f}x)")

    # --- Latency profiling ---
    print("\n  Inference latency profiling:")
    latency = profile_inference()
    with open(OUT_DIR / "latency.json", "w") as f:
        json.dump(latency, f, indent=2)
    print(f"    Mean: {latency['mean_us']:.1f} μs  "
          f"P95: {latency['p95_us']:.1f} μs  "
          f"P99: {latency['p99_us']:.1f} μs  "
          f"Max: {latency['max_us']:.1f} μs")
    print(f"    Headroom: {latency['headroom_factor']:.0f}x under 100ms budget")
    print(f"    Passes 100ms: {latency['passes_100ms']}")

    # --- Key figures ---
    _plot_noniid_degradation(agg_rows, cent_metrics)
    _plot_convergence_grid(all_results)

    # --- RESULTS.md ---
    _generate_results_md(cent_metrics, agg_df, bw_all, latency)

    # --- summary.json ---
    summary = {
        "n_experiments": len(all_results),
        "centralized_test_f1": cent_metrics["test"]["macro_f1"] if cent_metrics else None,
        "bandwidth": bw,
        "latency": latency,
        "best_fl": max(all_results, key=lambda r: r["final_test"]["macro_f1"])["final_test"],
        "worst_fl": min(all_results, key=lambda r: r["final_test"]["macro_f1"])["final_test"],
    }
    with open(OUT_DIR / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  All results saved to {OUT_DIR}/")


def _plot_noniid_degradation(agg_rows, cent_metrics):
    """Plot F1 vs alpha for each C (the money plot)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    dirichlet_rows = [r for r in agg_rows if r["partition"] == "dirichlet"]
    if not dirichlet_rows:
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    for c in sorted(set(r["C"] for r in dirichlet_rows)):
        subset = [r for r in dirichlet_rows if r["C"] == c]
        # Average across local_epochs for this plot
        alpha_vals = sorted(set(r["alpha"] for r in subset))
        f1_means = []
        f1_stds = []
        for a in alpha_vals:
            group = [r for r in subset if r["alpha"] == a]
            f1s = [r["f1_mean"] for r in group]
            f1_means.append(np.mean(f1s))
            f1_stds.append(np.mean([r["f1_std"] for r in group]))

        ax.errorbar(
            alpha_vals, f1_means, yerr=f1_stds,
            marker="o", label=f"C={c}", capsize=3,
        )

    if cent_metrics:
        ax.axhline(
            y=cent_metrics["test"]["macro_f1"],
            color="k", linestyle="--", alpha=0.7, label="Centralized",
        )

    ax.set_xscale("log")
    ax.set_xlabel("Dirichlet α (log scale)")
    ax.set_ylabel("Test Macro F1")
    ax.set_title("FL Performance vs Non-IID Strength")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-0.05, 1.05)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "noniid_degradation.png", dpi=150)
    plt.close(fig)
    print("  Saved noniid_degradation.png")


def _plot_convergence_grid(all_results):
    """Subplot grid: convergence curves for key configurations."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    # Pick seed=42, E=1 for the grid
    dirichlet = [r for r in all_results
                 if r["partition_type"] == "dirichlet"
                 and r["seed"] == 42 and r["local_epochs"] == 1]

    if not dirichlet:
        return

    clients_list = sorted(set(r["n_clients"] for r in dirichlet))
    alphas = sorted(set(r["alpha"] for r in dirichlet))

    fig, axes = plt.subplots(
        len(alphas), len(clients_list),
        figsize=(5 * len(clients_list), 3.5 * len(alphas)),
        squeeze=False,
    )

    for i, alpha in enumerate(alphas):
        for j, c in enumerate(clients_list):
            ax = axes[i][j]
            match = [r for r in dirichlet
                     if r["n_clients"] == c and r["alpha"] == alpha]
            if match:
                exp_dir = OUT_DIR / "experiments" / match[0]["experiment"]
                rm_path = exp_dir / "round_metrics.json"
                if rm_path.exists():
                    with open(rm_path) as f:
                        rm = json.load(f)
                    rounds = [m["round"] for m in rm]
                    f1s = [m["test_macro_f1"] for m in rm]
                    ax.plot(rounds, f1s, "b-", linewidth=1.5)

            ax.set_ylim(-0.05, 1.05)
            ax.set_title(f"C={c}, α={alpha}", fontsize=10)
            ax.grid(True, alpha=0.3)
            if i == len(alphas) - 1:
                ax.set_xlabel("Round")
            if j == 0:
                ax.set_ylabel("Test F1")

    fig.suptitle("FedAvg Convergence (E=1, seed=42)", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "convergence_grid.png", dpi=150)
    plt.close(fig)
    print("  Saved convergence_grid.png")


def _generate_results_md(cent_metrics, agg_df, bw_all, latency):
    """Generate human-readable RESULTS.md."""
    lines = ["# Federated Learning Results\n"]

    lines.append("## Centralized Baseline\n")
    if cent_metrics:
        t = cent_metrics["test"]
        lines.append(f"- **Test Macro F1:** {t['macro_f1']:.4f}")
        lines.append(f"- **Test MCC:** {t['mcc']:.4f}")
        lines.append(f"- **Test Accuracy:** {t['accuracy']:.4f}")
        lines.append(f"- **Best epoch:** {cent_metrics['best_epoch']}")
    lines.append("")

    lines.append("## FL Experiment Results (mean ± std across 3 seeds)\n")
    lines.append("| Partition | C | α | E | F1 (mean±std) | MCC (mean±std) |")
    lines.append("|---|---|---|---|---|---|")
    for _, row in agg_df.iterrows():
        lines.append(
            f"| {row['partition']} | {row['C']} | {row['alpha']} | {row['E']} "
            f"| {row['f1_mean']:.4f}±{row['f1_std']:.4f} "
            f"| {row['mcc_mean']:.4f}±{row['mcc_std']:.4f} |"
        )
    lines.append("")

    bw = bw_all[max(bw_all)]
    lines.append("## Communication Cost\n")
    lines.append(f"- Model: {bw['model_params']} parameters ({bw['model_bytes']} bytes)")
    lines.append(f"- Centralized (one-time raw data upload): {bw['centralized']['total_mb']:.4f} MB")
    for c in sorted(bw_all):
        b = bw_all[c]
        lines.append(f"- FL (C={c}, {GLOBAL_ROUNDS} rounds): "
                      f"{b['federated']['total_mb']:.4f} MB "
                      f"(ratio: {b['ratio_fl_over_centralized']:.2f}x vs centralized)")
    lines.append("")
    lines.append("**Note:** On this small simulation dataset, one-time centralized upload "
                 "is cheaper in bytes. In a real C-V2X deployment where vehicles continuously "
                 "stream BSMs at 10 Hz, FL dramatically reduces ongoing communication compared "
                 "to streaming raw traffic. FL also never transmits raw feature data (privacy).")
    lines.append("")

    lines.append("## Inference Latency\n")
    lines.append(f"- Mean: {latency['mean_us']:.1f} μs")
    lines.append(f"- P95: {latency['p95_us']:.1f} μs")
    lines.append(f"- P99: {latency['p99_us']:.1f} μs")
    lines.append(f"- Max: {latency['max_us']:.1f} μs")
    lines.append(f"- **Headroom:** {latency['headroom_factor']:.0f}x under 100ms PC5 budget")
    lines.append(f"- **Passes 100ms constraint:** {'Yes' if latency['passes_100ms'] else 'No'}")
    lines.append("")

    (OUT_DIR / "RESULTS.md").write_text("\n".join(lines))
    print("  Saved RESULTS.md")


def main():
    parser = argparse.ArgumentParser(description="CV2X-IDS Federated Learning Pipeline")
    parser.add_argument(
        "--step",
        choices=["centralized", "experiments", "summary", "all"],
        default="all",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    run_all = args.step == "all"
    all_results = None

    if run_all or args.step == "centralized":
        run_centralized_baseline()

    if run_all or args.step == "experiments":
        all_results = run_all_experiments()

    if run_all or args.step == "summary":
        generate_summary(all_results)

    print("\nDone.")


if __name__ == "__main__":
    main()
