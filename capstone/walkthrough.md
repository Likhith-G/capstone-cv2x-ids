# Project Walkthrough — CV2X-IDS

## Overview

This document walks through all four workstreams of the CV2X-IDS project, summarising what was built, the key outputs, and verified results for each.

---

## 1. Dataset Generation (`dataset-expansion/`)

### What Was Built
An NS-3 simulation pipeline that generates a labelled 5G C-V2X intrusion detection dataset. The simulation models a highway corridor with 40 vehicles, 4 gNBs, and 12 attack scenarios (5 network-layer, 6 vehicular-layer, 1 benign baseline). Raw per-packet logs are aggregated into 30-second time-windowed feature vectors.

### Key Outputs
| File | Description |
|------|-------------|
| `output/dataset.csv` | 18,240 rows, 39 columns |
| `output/train.csv` / `val.csv` / `test.csv` | 70/15/15 stratified split (grouped by scenario + node) |
| `output/DATASET_CARD.md` | Full schema, baselines, known limitations |
| `output/figures/` | Label distribution, feature importance, split distribution, confusion matrix |

### Verification
- All 57 internal integrity checks pass (zero NaN/Inf, all 12 types in all splits, no group leakage)
- Per-scenario random seeds prevent node identity fingerprinting (`true_speed_mean`-only F1 = 0.497)
- Dual-layer ablation: network-only F1 = 0.84, vehicular-only F1 = 0.83, combined F1 = 1.00

---

## 2. Feature Engineering (`feature-engineering/`)

### What Was Built
A feature selection pipeline that narrows 39 raw columns down to 15 optimal features for multiclass classification. Uses ANOVA F-scores, Mutual Information, and Borda count ranking, with top-k sweep evaluation under StratifiedGroupKFold.

### Key Outputs
| File | Description |
|------|-------------|
| `output/selected_features_multiclass.json` | Final 15-feature subset |
| `output/rankings_multiclass.csv` | Combined ANOVA + MI rankings |
| `output/per_class_discriminability.csv` | One-vs-rest ANOVA for each attack type |
| `output/figures/shap_network_attacks.png` | SHAP values for network attack features |
| `output/figures/shap_vehicular_attacks.png` | SHAP values for vehicular attack features |
| `output/figures/topk_curves.png` | F1 vs number of features |

### Verification
- Feature reduction path: 39 → 24 (remove metadata/labels/zero-variance/context) → 17 (correlation filter at 0.99) → 15 (Borda-ranked top-k)
- k=15 achieves perfect multiclass F1; k=13 drops to 0.51 (missing vehicular discriminators)
- Each attack type maps to specific features: flood attacks → `flood_ratio`/`n_flood`, position attacks → `mean_pos_deviation`, FDI → `mean_speed_deviation`, Sybil → `unique_vehicle_ids`

---

## 3. Classification (`classification/`)

### What Was Built
Three centralized classifiers (Random Forest, Gradient Boosting, MLP) trained on the 15-feature subset. The MLP architecture and preprocessing parameters are exported to `model_spec_fl.json` for the federated learning workstream.

### Key Outputs
| File | Description |
|------|-------------|
| `output/model_spec_fl.json` | MLP architecture + StandardScaler params (contract for FL) |
| `output/comparison.csv` | Side-by-side model comparison |
| `output/metrics_*.json` | Per-model val + test metrics |
| `output/figures/confusion_*.png` | Confusion matrices for all 3 models |

### Verification
- All three models achieve test Macro F1 = 1.0000, MCC = 1.0000 on the held-out test set (3,154 rows)
- All 12 classes at per-class F1 = 1.0 and FPR = 0.0
- Perfect scores are legitimate given deterministic NS-3 attack signatures (documented as known limitation)

---

## 4. Federated Learning (`federated-learning/`)

### What Was Built
A custom FedAvg implementation (no framework dependency) with 60 experiments across two partitioning strategies, two client counts, four non-IID levels, two local epoch settings, and three random seeds. Includes edge deployment analysis (latency profiling, model complexity sweep, communication overhead).

### Key Outputs
| File | Description |
|------|-------------|
| `output/aggregated_results.csv` | Mean±std across seeds for 20 configurations |
| `output/experiment_summary.csv` | All 60 individual experiment results |
| `output/bandwidth.json` | FL vs centralized communication costs |
| `output/latency.json` | Inference latency profiling (2000 forward passes) |
| `output/complexity.csv` | Model size sweep results |
| `output/figures/noniid_degradation.png` | F1 vs non-IID severity |
| `output/figures/convergence_grid.png` | Convergence curves across configurations |
| `output/figures/latency_histogram.png` | Inference latency distribution |

### Verification — Dirichlet Partitioning
- IID (α=100): F1 = 1.00 — matches centralized baseline perfectly
- Mild non-IID (α≥0.5): F1 = 0.97 to 1.00 depending on client count, so FedAvg holds up
- Strong non-IID (α=0.1, C=5, E=1): F1 = 0.54 — significant degradation
- Strong non-IID (α=0.1, C=5, E=3): F1 = 0.94 — extra local epochs partially recover

### Verification — Scenario-Based Partitioning
- F1 ranges from 0.35 to 0.65 across all configurations
- More local epochs make it worse (clients overfit to their own scenarios)
- FedAvg fundamentally cannot overcome complete class gaps — motivates FedProx for Part B

### Verification — Edge Deployment
- Mean inference: 26.4 μs, worst-case: 41.6 μs → 3,789x headroom under 100ms PC5 constraint
- Minimum viable model: 908 params (3.6 KB) at [15→32→12] still achieves perfect F1
- FL communication break-even: a single vehicle streaming raw BSMs exceeds one FL model upload in 17 seconds

### Additional Analysis
- Dropout regularisation: mixed results (helps scenario-based, hurts Dirichlet) — confirms targeted approaches like FedProx are needed
- Statistical significance: Wilcoxon tests with 3 seeds yield minimum p=0.25; Part B will use ≥6 seeds

---

## Deliverable Summary

| Workstream | RQ | Status | Key Metric |
|---|---|---|---|
| Dataset Generation | RQ1 | Complete | 18,240 rows, 12 scenarios, all integrity checks pass |
| Feature Engineering | RQ2a | Complete | 39 → 15 features, multiclass F1 = 1.00 |
| Classification | RQ2b | Complete | All 3 models at F1 = 1.00, MLP spec exported for FL |
| Federated Learning | RQ3 | Complete | 60 experiments, non-IID degradation characterised |
| Edge Deployment | RQ4 | Complete | 26.4 μs inference, 3,789x headroom |

---

## Where these priorities went

This section originally closed with three priorities for the next phase. All
three were revised once the detection pipeline in [`analysis/`](../analysis/)
was built, so what stands here is the correction to that plan.

1. **FedProx was run and does nothing.** It sits in a panel of five aggregation
   rules alongside FedAvg, FedNova, FedLC and FedProto, plus DP-FedAvg for the
   privacy cost. On geometric label skew its difference from FedAvg is within
   noise. See [`analysis/federated.py`](../analysis/federated.py).
2. **Krum was not run.** The threat model is misbehaving vehicles observed over
   the air rather than malicious federated clients, so Byzantine-resilient
   aggregation answers a question the data does not pose. It stays open.
3. **Hardware profiling was dropped deliberately.** Measured end to end, the
   time a detection window takes to fill dominates the forward pass by three
   orders of magnitude, so accelerating inference optimises a fraction of a
   percent of total detection latency. The argument does not need a board.

The partitioning strategy changed too. This phase used a Dirichlet parameter to
manufacture non-IID data. It is now a property of the deployment: roadside units
along a 6 km road see different vehicles, so most observers never see at least
one attack class. [`analysis/check_partition_skew.py`](../analysis/check_partition_skew.py)
measures it, and it should be run before any aggregation panel, because on a
short road every observer hears every vehicle and the comparison is meaningless.
