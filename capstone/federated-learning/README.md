# Federated Learning

**Status: Complete**

---

## Objective

Implement a FedAvg-based federated learning prototype on the CV2X-IDS dataset, comparing federated training against a centralized baseline across varying non-IID conditions.

---

## Pipeline

Run the full pipeline (centralized baseline + 60 FL experiments + summary):
```bash
python3 federated-learning/fl.py
```

Individual steps:
```bash
python3 federated-learning/fl.py --step centralized   # PyTorch centralized baseline
python3 federated-learning/fl.py --step experiments    # All FL experiment grid
python3 federated-learning/fl.py --step summary        # Aggregate results + figures
```

**Dependencies:** `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `torch`

---

## Architecture

- **Model:** MLP [15 → 128 → ReLU → 64 → ReLU → 32 → ReLU → 12] (12,780 params, ~51 KB)
- **Preprocessing:** StandardScaler (mean/scale from classification workstream)
- **Loss:** Class-weighted cross-entropy
- **Optimizer:** Adam (lr=1e-3, weight_decay=1e-3)

Same architecture for centralized baseline and all FL experiments.

---

## Experiment Grid

**Dirichlet partitioning** (48 experiments):
- Clients C ∈ {3, 5}
- Non-IID α ∈ {100.0 (IID), 1.0 (mild), 0.5 (moderate), 0.1 (strong)}
- Local epochs E ∈ {1, 3}
- Seeds: {42, 123, 456}

**Scenario-based partitioning** (12 experiments):
- Assigns entire scenarios to clients (realistic RSU deployment)
- Clients C ∈ {3, 5}, E ∈ {1, 3}, Seeds: {42, 123, 456}

All experiments: 50 global rounds, FedAvg aggregation, all clients participate each round.

---

## Key Results

### Centralized Baseline
| Metric | Value |
|--------|-------|
| Test Macro F1 | 1.0000 |
| Test MCC | 1.0000 |
| Convergence | Epoch 3 |

### Dirichlet Partitioning (mean ± std across 3 seeds)

| C | α | E | Macro F1 | MCC |
|---|---|---|----------|-----|
| 3 | 100.0 (IID) | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| 3 | 0.1 (strong) | 1 | 0.8365±0.2188 | 0.9134±0.1153 |
| 3 | 0.1 (strong) | 3 | 0.9993±0.0010 | 0.9996±0.0006 |
| 5 | 100.0 (IID) | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| 5 | 0.1 (strong) | 1 | 0.5392±0.2457 | 0.7572±0.1328 |
| 5 | 0.1 (strong) | 3 | 0.9389±0.0371 | 0.9639±0.0220 |

**Finding:** FedAvg is robust to Dirichlet non-IID for α ≥ 0.5. Strong non-IID (α=0.1) degrades performance, especially with more clients and fewer local epochs. More local epochs (E=3) partially compensates.

### Scenario-Based Partitioning (natural non-IID)

| C | E | Macro F1 | MCC |
|---|---|----------|-----|
| 3 | 1 | 0.6468±0.0525 | 0.8119±0.0233 |
| 3 | 3 | 0.5888±0.0459 | 0.7777±0.0221 |
| 5 | 1 | 0.3737±0.0230 | 0.6747±0.0303 |
| 5 | 3 | 0.3527±0.0225 | 0.6405±0.0065 |

**Finding:** Scenario-based partitioning creates extreme non-IID where clients never see certain attack types. This is more severe than most practical deployments and is used to stress-test FedAvg. FedAvg cannot overcome it — motivates FedProx for Part B.

### Communication Cost
- Model: 12,780 params = 51 KB per exchange
- Centralized (one-time raw data upload): 0.75 MB
- FL (C=3, 50 rounds): 14.63 MB | FL (C=5, 50 rounds): 24.38 MB

On this small simulation dataset, one-time centralized upload is cheaper in bytes. In a real C-V2X deployment where vehicles continuously stream BSMs at 10 Hz, FL dramatically reduces ongoing communication compared to streaming raw traffic. FL also never transmits raw feature data (**privacy**).

### Inference Latency
- Mean: 26.4 μs per sample (single-core CPU)
- P99: 29.3 μs
- Max: 41.6 μs
- **3,789x headroom** under the 100ms PC5 constraint

---

## Module Structure

| File | Description |
|------|-------------|
| `fl.py` | Main entry point — orchestrates full pipeline |
| `config.py` | Feature/label contract, experiment grid, paths |
| `model.py` | PyTorch MLP definition + weight get/set utilities |
| `partition.py` | Dirichlet + scenario-based client partitioning |
| `centralized.py` | Centralized PyTorch training baseline |
| `fedavg.py` | FedAvg server + client logic (extensible aggregation) |
| `evaluate.py` | Metrics computation + plotting |
| `bandwidth.py` | Communication cost estimation |
| `latency.py` | Inference latency profiling |
| `complexity.py` | Model size sweep (params vs F1) |
| `significance.py` | Wilcoxon signed-rank tests (E=1 vs E=3) |
| `plot_style.py` | Consistent figure styling across all plots |
| `run_dropout_check.py` | Dropout regularisation experiments |

---

## Output Artifacts

| Path | Description |
|------|-------------|
| `output/centralized/metrics.json` | Centralized baseline metrics |
| `output/centralized/model.pt` | Centralized model weights |
| `output/experiments/*/` | Per-experiment results (60 configs) |
| `output/experiment_summary.csv` | All 60 experiments in one table |
| `output/aggregated_results.csv` | Mean±std across seeds (20 configs) |
| `output/bandwidth.json` | Communication cost analysis |
| `output/latency.json` | Inference latency profiling |
| `output/complexity.csv` | Model size sweep results |
| `output/complexity.json` | Complexity analysis summary |
| `output/significance_e1_vs_e3.csv` | Statistical significance tests |
| `output/dropout_check/` | Dropout regularisation experiment results |
| `output/summary.json` | Machine-readable summary |
| `output/RESULTS.md` | Human-readable results |
| `output/figures/noniid_degradation.png` | F1 vs non-IID severity |
| `output/figures/convergence_grid.png` | Convergence subplot grid |
| `output/figures/latency_histogram.png` | Inference latency distribution |

---

## Where this went next

The extensions planned here were superseded rather than added to this codebase.
The federated work now lives in
[`analysis/federated.py`](../../analysis/federated.py) and differs in three ways
that matter:

**Five aggregation rules, not two.** FedAvg, FedProx, FedNova, FedLC and
FedProto, compared by paired Wilcoxon across eight seeds, plus DP-FedAvg to
price the privacy guarantee. FedProx is in the panel and its difference from
FedAvg is within noise, so the head-to-head planned here has an answer.

**Eight seeds, not three.** A two-sided Wilcoxon signed-rank test floors at
2/2^n, so with three seeds the smallest reachable p-value is 0.25 and no result
can be significant whatever the numbers. Six is the minimum and eight is
preferable. That is why none of the tests in this workstream reach
significance, and it is a property of the test rather than of the effects.

**Skew from geography, not from a Dirichlet parameter.** Clients are roadside
units at fixed points on a 6 km road, so label skew is a consequence of which
vehicles pass which unit. Run
[`analysis/check_partition_skew.py`](../../analysis/check_partition_skew.py)
before any panel: on a short road every observer hears every vehicle, the
partition is near uniform, and an aggregation comparison on it means nothing.
