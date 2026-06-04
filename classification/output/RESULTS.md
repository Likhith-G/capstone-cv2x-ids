# Classification Results

## Feature Subset

**15 features** from feature engineering (multiclass selection, k=15):

```
mean_iat, mean_pkt_size, total_bytes, pkt_rate, min_iat, flood_ratio, flood_mean_iat, duration, std_pkt_size, unique_vehicle_ids, bsm_mean_iat, n_flood, max_iat, max_pos_deviation, mean_speed_deviation
```

## Model Comparison

| Model | Val Macro F1 | Val MCC | Test Macro F1 | Test MCC | Test Accuracy |
|---|---|---|---|---|---|
| RF | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| GBC | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| MLP | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Per-Class Test Metrics

**Model: MLP** (FL candidate; RF and GBC achieve identical metrics)

| Class | Precision | Recall | F1 | FPR | Support |
|---|---|---|---|---|---|
| Benign | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 2736 |
| FalseDataInjection | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| HTTPFlood | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| ICMPFlood | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| PositionSpoof | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| RandomPosition | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| Replay | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| SYNFlood | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| SlowDoS | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| Sybil | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| UDPFlood | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |
| VehicularDoS | 1.0000 | 1.0000 | 1.0000 | 0.000000 | 38 |

## Feature Importance (Random Forest Gini)

| Rank | Feature | Importance |
|---|---|---|
| 1 | max_pos_deviation | 0.2684 |
| 2 | mean_speed_deviation | 0.1265 |
| 3 | mean_pkt_size | 0.0767 |
| 4 | total_bytes | 0.0660 |
| 5 | unique_vehicle_ids | 0.0605 |
| 6 | std_pkt_size | 0.0596 |
| 7 | flood_mean_iat | 0.0562 |
| 8 | pkt_rate | 0.0538 |
| 9 | flood_ratio | 0.0506 |
| 10 | duration | 0.0490 |
| 11 | n_flood | 0.0486 |
| 12 | mean_iat | 0.0407 |
| 13 | min_iat | 0.0153 |
| 14 | bsm_mean_iat | 0.0147 |
| 15 | max_iat | 0.0134 |

## Permutation Importance (MLP)

| Rank | Feature | F1 Drop |
|---|---|---|
| 1 | max_pos_deviation | 0.2565 |
| 2 | n_flood | 0.2339 |
| 3 | duration | 0.1684 |
| 4 | total_bytes | 0.1337 |
| 5 | bsm_mean_iat | 0.1131 |
| 6 | flood_mean_iat | 0.1117 |
| 7 | mean_pkt_size | 0.1095 |
| 8 | std_pkt_size | 0.1057 |
| 9 | flood_ratio | 0.0913 |
| 10 | mean_speed_deviation | 0.0900 |
| 11 | unique_vehicle_ids | 0.0845 |
| 12 | max_iat | 0.0694 |
| 13 | min_iat | 0.0623 |
| 14 | pkt_rate | 0.0252 |
| 15 | mean_iat | 0.0066 |

## FL Handoff

The FL workstream should use the MLP architecture defined in `output/model_spec_fl.json`:
- Input: 15 features (StandardScaler parameters included)
- Architecture: [128, 64, 32] hidden layers, ReLU, softmax output
- Loss: class-weighted cross-entropy
- Optimizer: Adam (lr=1e-3, weight_decay=1e-3)
