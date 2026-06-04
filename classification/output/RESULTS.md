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

## Per-Class Test Metrics (Best Model)

**Model: RF**

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
| 2 | duration | 0.1471 |
| 3 | bsm_mean_iat | 0.1379 |
| 4 | n_flood | 0.1138 |
| 5 | flood_mean_iat | 0.1117 |
| 6 | std_pkt_size | 0.1080 |
| 7 | mean_speed_deviation | 0.0911 |
| 8 | unique_vehicle_ids | 0.0845 |
| 9 | min_iat | 0.0623 |
| 10 | flood_ratio | 0.0615 |
| 11 | max_iat | 0.0099 |
| 12 | mean_iat | 0.0066 |
| 13 | mean_pkt_size | 0.0055 |
| 14 | total_bytes | 0.0022 |
| 15 | pkt_rate | 0.0022 |

## FL Handoff

The FL workstream should use the MLP architecture defined in `output/model_spec_fl.json`:
- Input: 15 features (StandardScaler parameters included)
- Architecture: [128, 64, 32] hidden layers, ReLU, softmax output
- Loss: class-weighted cross-entropy
- Optimizer: Adam (lr=1e-3, weight_decay=1e-3)
