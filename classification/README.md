# Multiclass Classification

**Status: Complete**

---

## Objective

Train and evaluate centralized multiclass classifiers on the CV2X-IDS dataset using the 15-feature subset from the Feature Engineering workstream. Produce a model architecture specification for the Federated Learning workstream.

---

## Pipeline

Run the full pipeline:
```bash
python3 classification/classify.py
```

Individual steps: `--step {train,evaluate,compare,report}`.

**Dependencies:** `pandas`, `numpy`, `scikit-learn`, `matplotlib`

---

## Models Evaluated

| Model | Description | Class Imbalance Handling |
|---|---|---|
| Random Forest (RF) | 300 trees, max_depth=25 | `class_weight='balanced'` |
| Histogram Gradient Boosting (GBC) | 300 iterations, max_depth=8 | Balanced sample weights |
| Multi-Layer Perceptron (MLP) | [128, 64, 32] hidden layers, ReLU | StandardScaler + early stopping |

---

## Key Results

All three models achieve perfect classification on the held-out test set (3,154 rows):

| Model | Test Macro F1 | Test MCC | Test Accuracy |
|---|---|---|---|
| RF | 1.0000 | 1.0000 | 1.0000 |
| GBC | 1.0000 | 1.0000 | 1.0000 |
| MLP | 1.0000 | 1.0000 | 1.0000 |

All 12 classes (Benign + 11 attack types) achieve per-class F1 = 1.0 and FPR = 0.0 across all models.

The perfect scores are expected and legitimate: the NS-3 simulation generates deterministic attack signatures (fixed PPS rates, exact position offsets, precise speed multipliers) in a noise-free environment. These produce trivial decision boundaries for any competent classifier given the correct features.

### Feature Importance

RF Gini importance confirms features align with known attack mechanisms:

| Rank | Feature | Importance | Primary Role |
|---|---|---|---|
| 1 | max_pos_deviation | 0.2684 | PositionSpoof, RandomPosition, Replay |
| 2 | mean_speed_deviation | 0.1265 | FalseDataInjection (sole discriminator) |
| 3 | mean_pkt_size | 0.0767 | Network flood differentiation |
| 4 | total_bytes | 0.0660 | Network flood volume |
| 5 | unique_vehicle_ids | 0.0605 | Sybil (sole discriminator) |

---

## Output Artifacts

| File | Description |
|---|---|
| `output/metrics_rf.json` | RF val + test metrics, feature importance |
| `output/metrics_gbc.json` | GBC val + test metrics |
| `output/metrics_mlp.json` | MLP val + test metrics, permutation importance |
| `output/comparison.csv` | Side-by-side model comparison |
| `output/model_spec_fl.json` | FL model architecture + preprocessing spec |
| `output/RESULTS.md` | Human-readable results summary |
| `output/figures/` | Confusion matrices, feature importance chart |

---

## Handoff to Federated Learning

The FL workstream should:
1. Use the MLP architecture from `output/model_spec_fl.json`
2. Reimplement in PyTorch: `nn.Linear(15, 128) -> ReLU -> nn.Linear(128, 64) -> ReLU -> nn.Linear(64, 32) -> ReLU -> nn.Linear(32, 12)`
3. Apply the StandardScaler parameters from the spec (mean + scale vectors)
4. Use class-weighted cross-entropy loss
5. The centralized MLP baseline (Macro F1 = 1.0) is the upper bound for FL performance
