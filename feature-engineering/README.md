# Feature Engineering

> **Superseded.** This describes the v1 pipeline, submitted for OENG1167 and
> kept as the record of what was handed in. It is not the current state of the
> project, and the scores in it should not be read as deployment performance.
>
> Two measured reasons. Compared at measurement precision rather than float
> precision, the v1 dataset holds 97.8 percent duplicate feature vectors and
> 96.4 percent verbatim overlap between the training and test splits, so much
> of the test set is a copy of what the model was trained on. Duplicate and
> overlap tests run at float precision return zero on any continuous feature
> set whether or not the data is degenerate, which is why this went unseen.
> Separately, several of the selected features compare a claimed value against
> simulator ground truth, and a deployed roadside unit has only the claim.
> Together these account for the perfect scores reported below.
>
> The current pipeline is v2, in [`simulation/`](../simulation/) and
> [`analysis/`](../analysis/). It fixes both structurally rather than by
> patching: ground truth never travels over the air and the feature builder
> cannot open the transmit log, so an unobservable feature cannot enter the
> corpus by accident. Every corpus is put through eight adversarial integrity
> gates before a model is trained, which is
> [`analysis/validate_dataset.py`](../analysis/validate_dataset.py).

---

**Status: Complete**

---

## Objective

Identify optimal feature subsets from the CV2X-IDS dataset for binary and multiclass IDS classification, using ANOVA F-score and Mutual Information ranking with grouped cross-validation evaluation.

---

## Pipeline

Run the full pipeline:
```bash
python3 feature-engineering/feature_selection.py
```

Individual steps can be run with `--step {universe,rankings,discriminability,topk,select,shap,report}`.

**Dependencies:** `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `shap`

---

## Key Results

### Feature Universe

Starting from 39 dataset columns, the pipeline removes metadata (5), context (4), labels (2), zero-variance (4), and highly correlated pairs (7), leaving **17 informative features**.

Correlation filter removes perfectly redundant pairs (|r| > 0.99):
- `n_pkts` / `pkt_rate` (r=1.00) -- kept `pkt_rate`
- `n_bsm` / `bsm_mean_iat` / `msg_freq` (r=1.00) -- kept `bsm_mean_iat`
- `total_bytes` / `byte_rate` (r=1.00) -- kept `total_bytes`
- `mean_speed_deviation` / `max_speed_deviation` (r=0.999) -- kept `mean_speed_deviation`
- `std_iat` / `flood_mean_iat` / `flood_std_iat` (r>0.99) -- kept `flood_mean_iat`

### Selected Feature Subsets

**Binary IDS (k=13):** `mean_iat`, `min_iat`, `pkt_rate`, `duration`, `total_bytes`, `n_flood`, `flood_ratio`, `max_iat`, `mean_pkt_size`, `flood_mean_iat`, `std_pkt_size`, `mean_speed_deviation`, `max_pos_deviation`
- Macro F1: 1.0000, MCC: 1.0000

**Multiclass (k=15):** adds `unique_vehicle_ids` and `bsm_mean_iat` to the binary set (reordered by multiclass ranking)
- Macro F1: 1.0000, MCC: 1.0000, all 12 classes at F1=1.0

### Critical Feature Dependencies

The top-k curves reveal sharp phase transitions:
- **Binary:** k=11 to k=13 jumps from 0.83 to 1.00 F1 (vehicular features entering)
- **Multiclass:** k=13 to k=15 jumps from 0.51 to 1.00 F1 (position and speed features entering)

Per-class discriminability analysis shows each attack type depends on specific features:

| Attack | Primary Discriminator |
|---|---|
| Network floods (UDP/ICMP/SYN/HTTP) | `flood_ratio`, `n_flood`, `total_bytes`, `mean_pkt_size` |
| SlowDoS | `flood_mean_iat` (uniquely low-rate flood pattern) |
| PositionSpoof / RandomPosition | `mean_pos_deviation`, `max_pos_deviation` |
| FalseDataInjection | `mean_speed_deviation` (sole discriminator) |
| Sybil | `unique_vehicle_ids` |
| VehicularDoS | `bsm_mean_iat` / `pkt_rate` |
| Replay | `seq_anomaly` (weak), `mean_pos_deviation` (primary) |

---

## Output Artifacts

| File | Description |
|---|---|
| `output/feature_universe.json` | Final 17-feature list with categories |
| `output/rankings_binary.csv` | ANOVA + MI rankings for binary target |
| `output/rankings_multiclass.csv` | ANOVA + MI rankings for multiclass target |
| `output/rankings.json` | Combined rankings (both targets) |
| `output/per_class_discriminability.csv` | One-vs-rest ANOVA for each attack type |
| `output/topk_binary.csv` | Top-k evaluation results (binary) |
| `output/topk_multiclass.csv` | Top-k evaluation results (multiclass) |
| `output/selected_features_binary.json` | Final binary feature subset + metrics |
| `output/selected_features_multiclass.json` | Final multiclass feature subset + metrics |
| `output/RESULTS.md` | Human-readable results summary |
| `output/figures/` | Heatmap, top-k curves, SHAP plots |

---

## Handoff to Classification

The classification workstream should:
1. Load `train.csv`, `val.csv`, `test.csv` directly (do not re-split)
2. Use the 15 multiclass features from `output/selected_features_multiclass.json`
3. Use `class_weight='balanced'` to handle 88.5% benign imbalance
4. Report: Macro F1, MCC, per-class F1, per-class precision/recall, FPR
5. Evaluate on `val.csv` for tuning, final metrics on `test.csv` only
