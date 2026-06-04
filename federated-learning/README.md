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
| 3 | 0.1 (strong) | 1 | 0.8165±0.1796 | 0.9176±0.0806 |
| 3 | 0.1 (strong) | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| 5 | 100.0 (IID) | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| 5 | 0.1 (strong) | 1 | 0.6336±0.1755 | 0.8144±0.0861 |
| 5 | 0.1 (strong) | 3 | 0.9063±0.0808 | 0.9496±0.0415 |

**Finding:** FedAvg is robust to Dirichlet non-IID for α ≥ 0.5. Strong non-IID (α=0.1) degrades performance, especially with more clients and fewer local epochs. More local epochs (E=3) partially compensates.

### Scenario-Based Partitioning (natural non-IID)

| C | E | Macro F1 | MCC |
|---|---|----------|-----|
| 3 | 1 | 0.5578±0.0929 | 0.7562±0.0535 |
| 3 | 3 | 0.5073±0.0709 | 0.7294±0.0464 |
| 5 | 1 | 0.3951±0.1144 | 0.6682±0.0759 |
| 5 | 3 | 0.3430±0.1016 | 0.6362±0.0438 |

**Finding:** Scenario-based partitioning creates extreme non-IID where clients never see certain attack types. FedAvg cannot overcome this — motivates FedProx for Part B.

### Communication Cost
- Model: 12,780 params = 51 KB per exchange
- Centralized (raw data): 0.75 MB
- FL (5 clients, 50 rounds): 24.38 MB
- **Privacy benefit:** FL never transmits raw feature data

### Inference Latency
- Mean: 27.7 μs per sample (single-core CPU)
- P99: 30.8 μs
- **3,614x headroom** under the 100ms PC5 constraint

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
| `output/summary.json` | Machine-readable summary |
| `output/RESULTS.md` | Human-readable results |
| `output/figures/noniid_degradation.png` | F1 vs α (money plot) |
| `output/figures/convergence_grid.png` | Convergence subplot grid |

---

## Extension Points for Part B

**FedProx:** Change `FedAvgClient.train_round` to add proximal term `μ/2 * ||w - w_global||²` to the loss. Aggregation stays identical.

**Krum:** Swap `fedavg_aggregate` for a selection-based scheme in `FedAvgServer.run(aggregate_fn=krum_aggregate)`.

Both require only localized changes — the modular design keeps training, aggregation, and evaluation cleanly separated.
