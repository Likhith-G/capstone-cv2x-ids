#!/usr/bin/env python3
"""
significance.py -- Paired statistical significance tests for FL experiments.

Compares two groups of results that share the same (partition, C, alpha, E)
configurations but differ by algorithm or hyperparameter. Uses Wilcoxon
signed-rank test on paired F1 scores (matched by seed and partition).

Current use: E=1 vs E=3 within FedAvg (same partitions, same seeds).
Part B use:  FedAvg vs FedProx (same configs, same seeds, same partitions).
"""

import numpy as np
from scipy.stats import wilcoxon


def paired_significance(results_a, results_b, label_a="A", label_b="B", metric="macro_f1"):
    """
    Run paired Wilcoxon signed-rank tests between two matched result sets.

    Each result set is a list of dicts with keys:
      partition_type, n_clients, alpha, local_epochs, seed, final_test

    Pairs are matched on (partition_type, n_clients, alpha, seed).
    results_a and results_b must differ only in the comparison variable
    (e.g., local_epochs, or algorithm).

    Returns a list of comparison dicts, one per matched group.
    """
    def _key(r):
        return (r["partition_type"], r["n_clients"], r["alpha"], r["seed"])

    index_a = {}
    for r in results_a:
        index_a[_key(r)] = r["final_test"][metric]

    index_b = {}
    for r in results_b:
        index_b[_key(r)] = r["final_test"][metric]

    groups_a = {}
    groups_b = {}
    for key in index_a:
        config = (key[0], key[1], key[2])  # (partition, C, alpha)
        groups_a.setdefault(config, []).append((key[3], index_a[key]))

    for key in index_b:
        config = (key[0], key[1], key[2])
        groups_b.setdefault(config, []).append((key[3], index_b[key]))

    comparisons = []
    for config in sorted(groups_a.keys()):
        if config not in groups_b:
            continue

        seeds_a = {seed: val for seed, val in groups_a[config]}
        seeds_b = {seed: val for seed, val in groups_b[config]}
        common_seeds = sorted(set(seeds_a) & set(seeds_b))

        if len(common_seeds) < 3:
            continue

        vals_a = np.array([seeds_a[s] for s in common_seeds])
        vals_b = np.array([seeds_b[s] for s in common_seeds])

        diff = vals_b - vals_a
        if np.all(diff == 0):
            p_val = 1.0
        elif len(common_seeds) < 6:
            # Wilcoxon exact with n<6 has limited resolution; report but flag
            try:
                _, p_val = wilcoxon(vals_a, vals_b, alternative="two-sided")
            except ValueError:
                p_val = 1.0
        else:
            _, p_val = wilcoxon(vals_a, vals_b, alternative="two-sided")

        partition, c, alpha = config
        comparisons.append({
            "partition": partition,
            "C": c,
            "alpha": alpha if alpha is not None else "-",
            f"{label_a}_{metric}": f"{np.mean(vals_a):.4f}±{np.std(vals_a):.4f}",
            f"{label_b}_{metric}": f"{np.mean(vals_b):.4f}±{np.std(vals_b):.4f}",
            "delta": round(float(np.mean(vals_b) - np.mean(vals_a)), 4),
            "p_value": round(float(p_val), 4),
            "significant": p_val < 0.05,
            "n_seeds": len(common_seeds),
        })

    return comparisons


def compare_local_epochs(all_results, e_baseline=1, e_compare=3):
    """
    Compare E=e_baseline vs E=e_compare across all matching configs.
    This is the main Part A comparison (more local epochs = more compute,
    but does it significantly improve F1 under non-IID?).
    """
    group_a = [r for r in all_results if r["local_epochs"] == e_baseline]
    group_b = [r for r in all_results if r["local_epochs"] == e_compare]

    return paired_significance(
        group_a, group_b,
        label_a=f"E={e_baseline}", label_b=f"E={e_compare}",
        metric="macro_f1",
    )
