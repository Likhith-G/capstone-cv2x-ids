# Dataset Card: CV2X-IDS-V3

## Overview

| Property | Value |
|---|---|
| **Name** | CV2X-IDS-V3 |
| **Domain** | 5G C-V2X Intrusion Detection |
| **Source** | NS-3.42 with 5G-LENA NR module |
| **Total Rows** | 18,240 time-windowed feature vectors |
| **Scenarios** | 12 (1 Benign + 5 Network + 6 Vehicular) |
| **Topology** | 40 UEs, 4 gNBs, highway mobility |
| **Simulation Time** | 600s per scenario |
| **Window Size** | 30s with 15s sliding step |
| **Attackers** | 5 per scenario (nodes 0-4) |
| **RNG Seeds** | Per-scenario dynamic seeds (43-54) |
| **Generated** | 2026-05-31 |

---

## Attack Types

### Network Layer (5 types)
| Type | Mechanism | Key Signal |
|---|---|---|
| UDPFlood | 500 pps flood to MEC server | `n_flood >> 0`, `flood_ratio > 0` |
| ICMPFlood | 200 pps ICMP echo to MEC server | `n_flood >> 0`, `flood_ratio > 0` |
| SYNFlood | 400 pps TCP SYN to MEC server | `n_flood >> 0`, `flood_ratio > 0` |
| HTTPFlood | 200 pps HTTP GET to MEC server | `n_flood >> 0`, `flood_ratio > 0` |
| SlowDoS | 10 pps slow-read connections | `n_flood > 0`, lower `flood_ratio` |

### Vehicular / Application Layer (6 types)
| Type | Mechanism | Key Signal |
|---|---|---|
| PositionSpoof | BSM claims position +500m from truth | `mean_pos_deviation = 500` |
| RandomPosition | BSM claims random position each tx | `mean_pos_deviation >> 0` (variable) |
| Replay | Retransmits cached stale BSMs | `mean_pos_deviation > 0` (stale coords) |
| FalseDataInjection | BSM speed falsified by +50% | `mean_speed_deviation >> 0` |
| Sybil | One node sends BSMs with 5 fake IDs | `unique_vehicle_ids = 5` |
| VehicularDoS | BSM rate increased to 1000 Hz | `n_bsm = 30,000` vs normal `300` |

---

## Feature Set (39 columns total, 23 informative after zero-variance filter)

### Metadata (not used for classification)
`scenario_id`, `node_id`, `window_id`, `window_start`, `window_end`

### Network Traffic Features (18)
`n_pkts`, `n_bsm`, `n_flood`, `flood_ratio`, `total_bytes`, `pkt_rate`, `byte_rate`, `mean_iat`, `std_iat`, `min_iat`, `max_iat`, `bsm_mean_iat`, `bsm_std_iat`*, `flood_mean_iat`, `flood_std_iat`, `mean_pkt_size`, `std_pkt_size`, `duration`

### Vehicular / BSM Features (10)
`mean_pos_deviation`, `max_pos_deviation`, `mean_speed_deviation`, `max_speed_deviation`, `heading_change_rate`*, `seq_anomaly`, `unique_vehicle_ids`, `msg_freq`, `bsm_size_mean`*, `bsm_size_std`*

> **Note:** `bsm_size_mean` exhibits zero variance in addition to `bsm_size_std` and `heading_change_rate` — all three are filtered pre-classification.

### Context Features (4)
`true_speed_mean`, `true_speed_std`*, `distance_to_gnb`, `region_id`

### Labels (2)
`label_binary` (0 = Benign, 1 = Attack), `label_attack_type` (12 classes)

> Features marked with * have zero variance due to `ConstantVelocityMobilityModel` and are automatically filtered before classification. Zero-variance features confirmed: `bsm_std_iat`, `heading_change_rate`, `bsm_size_mean`, `bsm_size_std`, `true_speed_std`.

---

## Label Distribution

| Class | Windows | % of Dataset |
|---|---|---|
| Benign | 16,150 | 88.5% |
| UDPFlood | 190 | 1.04% |
| ICMPFlood | 190 | 1.04% |
| SYNFlood | 190 | 1.04% |
| HTTPFlood | 190 | 1.04% |
| SlowDoS | 190 | 1.04% |
| PositionSpoof | 190 | 1.04% |
| RandomPosition | 190 | 1.04% |
| Replay | 190 | 1.04% |
| FalseDataInjection | 190 | 1.04% |
| Sybil | 190 | 1.04% |
| VehicularDoS | 190 | 1.04% |
| **Total Attack** | **2,090** | **11.46%** |

---

## Train / Val / Test Splits

Split at the **group level** (`scenario_id` + `node_id`) with per-scenario stratification to guarantee all 12 attack types appear in every split.

| Split | Rows | Groups | Benign | Attack | Ratio |
|---|---|---|---|---|---|
| Train | 12,350 | 325 | 11,096 | 1,254 | 67.7% |
| Val | 2,736 | 72 | 2,318 | 418 | 15.0% |
| Test | 3,154 | 83 | 2,736 | 418 | 17.3% |

**No group appears in more than one split.** This prevents temporal leakage from overlapping windows.

---

## Baseline Results (Random Forest, StratifiedGroupKFold, 5-fold)

### Binary Classification (Benign vs Attack)
| Config | Features | F1 (macro) | Accuracy |
|---|---|---|---|
| Full (no context) | 23 | 1.0000 | 1.0000 |
| Network only | 15 | 0.8405 | 0.9479 |
| Vehicular only | 7 | 0.8308 | 0.9479 |
| No position features | 21 | 0.9201 | 0.9688 |
| No speed features | 21 | 0.9718 | 0.9896 |

### Multiclass Classification (12-class)
| Config | Features | F1 (macro) | Accuracy |
|---|---|---|---|
| Full (no context) | 23 | 1.0000 | 1.0000 |

### Leakage Validation
| Test | F1 | Expected | Status |
|---|---|---|---|
| `true_speed_mean` alone | 0.4968 | ~0.50 | PASS (no leakage) |
| Context features only | 0.7112 | ~0.50 | Moderate (documented) |

> Context features have moderate predictive power (F1=0.71) because `region_id` still correlates with node location. These features are excluded from the classifier's feature set.

---

## Known Limitations

1. **ConstantVelocityMobilityModel:** All vehicles travel in straight lines at constant speed. Features like `heading_change_rate` and `true_speed_std` are always zero. A SUMO-based simulation would produce more realistic mobility patterns.
2. **Perfect F1 Scores:** The simulation produces mathematically pristine attack signals (e.g., floods at fixed rates, position offsets at exact distances). Real-world attacks would be noisier and harder to detect.
3. **Replay `seq_anomaly`:** Only 2.6% of Replay windows trigger the sequence anomaly detector. Replay is instead detected via `mean_pos_deviation` (stale positional data). The `seq_anomaly` feature needs a more sensitive detection algorithm for future versions.
4. **Class Imbalance:** 88.5% Benign vs 1% per attack type. Federated learning experiments should use stratified sampling or class weighting.

---

## File Manifest

| File | Description | Size |
|---|---|---|
| `dataset_v3.csv` | Full dataset (all 18,240 windows) | 3.3 MB |
| `train.csv` | Training split (12,350 rows) | 2.3 MB |
| `val.csv` | Validation split (2,736 rows) | 494 KB |
| `test.csv` | Test split (3,154 rows) | 493 KB |
| `split_metadata.json` | Group-to-split mapping | 7 KB |
| `packets_S00.csv` - `packets_S11.csv` | Raw per-packet logs | ~840 MB total |
| `figures/label_distribution.png` | Label distribution bar chart | -- |
| `figures/feature_importance.png` | RF feature importance (top 15) | -- |
| `figures/split_distribution.png` | Train/Val/Test per-type breakdown | -- |
| `figures/confusion_matrix.png` | Multiclass confusion matrix | -- |

---

## Pipeline Scripts

| Script | Purpose |
|---|---|
| `simulation.cc` | NS-3 C++ simulation with all 11 attack implementations |
| `run_all.sh` | Orchestrates 12 scenario runs + dataset build + validation + split |
| `build_dataset.py` | Converts raw packet CSVs to time-windowed feature vectors |
| `validate_dataset.py` | 57-check integrity validation suite |
| `baseline_classifier.py` | RF baseline with ablation study and grouped CV |
| `split_dataset.py` | Per-scenario stratified group-level 70/15/15 splitter |

---

## Reproducibility

```bash
cd ~/ns-allinone-3.42/ns-3.42
bash v3_pipeline/run_all.sh
```

Seeds are deterministic (43-54 per scenario). Output is fully reproducible on the same NS-3 build.
