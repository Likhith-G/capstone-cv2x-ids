# Feature Engineering Results

## Feature Universe

Starting from 39 dataset columns, after removing metadata (5), context (4), labels (2), zero-variance (4), and correlated (7), **17 informative features** remain.

| Category | Features |
|---|---|
| timing | duration, mean_iat, min_iat, max_iat, flood_mean_iat |
| volume_rate | n_flood, flood_ratio |
| size | mean_pkt_size, std_pkt_size |
| vehicular | mean_pos_deviation, max_pos_deviation, mean_speed_deviation |
| behavioral | seq_anomaly, unique_vehicle_ids |

**Dropped (zero-variance):** bsm_std_iat, heading_change_rate, bsm_size_mean, bsm_size_std

**Dropped (correlation > 0.99):** flood_std_iat, max_speed_deviation, std_iat, n_bsm, n_pkts, msg_freq, byte_rate

## Rankings: Binary

| Rank | Feature | ANOVA F | MI Score |
|---|---|---|---|
| 1.5 | mean_iat | 11133.6 | 0.1466 |
| 1.5 | min_iat | 13312.6 | 0.1460 |
| 4.5 | pkt_rate | 5350.5 | 0.1441 |
| 5.5 | duration | 8506.0 | 0.1168 |
| 6.0 | total_bytes | 3782.5 | 0.1439 |
| 7.0 | n_flood | 5108.6 | 0.1172 |
| 7.0 | flood_ratio | 7719.8 | 0.1168 |
| 7.0 | max_iat | 8194.0 | 0.1159 |
| 8.0 | mean_pkt_size | 1576.6 | 0.1185 |
| 9.0 | flood_mean_iat | 1265.0 | 0.1199 |
| 10.0 | std_pkt_size | 3620.0 | 0.1141 |
| 12.5 | mean_speed_deviation | 1399.8 | 0.0518 |
| 12.5 | max_pos_deviation | 1278.8 | 0.0924 |
| 13.0 | mean_pos_deviation | 1259.9 | 0.0935 |
| 15.0 | unique_vehicle_ids | 1109.4 | 0.0231 |

## Rankings: Multiclass

| Rank | Feature | ANOVA F | MI Score |
|---|---|---|---|
| 4.0 | mean_iat | 543291732.6 | 0.3031 |
| 4.0 | mean_pkt_size | 1869140738.7 | 0.2629 |
| 6.0 | total_bytes | 4721711.4 | 0.3123 |
| 6.5 | pkt_rate | 12478759.6 | 0.2989 |
| 6.5 | min_iat | 2777470523608510.0 | 0.2420 |
| 7.0 | duration | 53726120.9 | 0.2503 |
| 7.0 | std_pkt_size | 18445090.1 | 0.2616 |
| 7.0 | flood_ratio | 438967761.5 | 0.2495 |
| 7.0 | flood_mean_iat | 1239183932.8 | 0.2482 |
| 8.0 | unique_vehicle_ids | 27774705236085100.0 | 0.0563 |
| 9.5 | bsm_mean_iat | 477450709241507.9 | 0.0527 |
| 10.0 | n_flood | 4164979.3 | 0.2489 |
| 12.0 | max_iat | 53246.5 | 0.2432 |
| 13.5 | max_pos_deviation | 6768.2 | 0.2096 |
| 13.5 | mean_speed_deviation | 230515.4 | 0.1180 |

## Top-k Evaluation: Binary

| k | Macro F1 | MCC | Accuracy |
|---|---|---|---|
| 3 | 0.8288 +/- 0.1104 | 0.7095 +/- 0.1743 | 0.9538 |
| 5 | 0.8288 +/- 0.1104 | 0.7095 +/- 0.1743 | 0.9538 |
| 7 | 0.8288 +/- 0.1104 | 0.7095 +/- 0.1743 | 0.9538 |
| 10 | 0.8288 +/- 0.1104 | 0.7095 +/- 0.1743 | 0.9538 |
| 11 | 0.8288 +/- 0.1104 | 0.7095 +/- 0.1743 | 0.9538 |
| 12 | 0.9152 +/- 0.0519 | 0.8467 +/- 0.0922 | 0.9723 |
| 13 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |
| 14 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |
| 15 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |
| 16 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |
| 17 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |

## Top-k Evaluation: Multiclass

| k | Macro F1 | MCC | Accuracy |
|---|---|---|---|
| 3 | 0.4424 +/- 0.0817 | 0.4012 +/- 0.0650 | 0.0585 |
| 5 | 0.4424 +/- 0.0817 | 0.4012 +/- 0.0650 | 0.0585 |
| 7 | 0.4424 +/- 0.0817 | 0.4012 +/- 0.0650 | 0.0585 |
| 10 | 0.5119 +/- 0.0831 | 0.4289 +/- 0.0539 | 0.0677 |
| 11 | 0.5119 +/- 0.0831 | 0.4289 +/- 0.0539 | 0.0677 |
| 12 | 0.5119 +/- 0.0831 | 0.4289 +/- 0.0539 | 0.0677 |
| 13 | 0.5119 +/- 0.0831 | 0.4289 +/- 0.0539 | 0.0677 |
| 14 | 0.9493 +/- 0.0620 | 0.9595 +/- 0.0518 | 0.9908 |
| 15 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |
| 16 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |
| 17 | 1.0000 +/- 0.0000 | 1.0000 +/- 0.0000 | 1.0000 |

## Selected Features: Binary (k=13)

1. `mean_iat`
2. `min_iat`
3. `pkt_rate`
4. `duration`
5. `total_bytes`
6. `n_flood`
7. `flood_ratio`
8. `max_iat`
9. `mean_pkt_size`
10. `flood_mean_iat`
11. `std_pkt_size`
12. `mean_speed_deviation`
13. `max_pos_deviation`

Macro F1: 1.0000, MCC: 1.0000

## Selected Features: Multiclass (k=15)

1. `mean_iat`
2. `mean_pkt_size`
3. `total_bytes`
4. `pkt_rate`
5. `min_iat`
6. `flood_ratio`
7. `flood_mean_iat`
8. `duration`
9. `std_pkt_size`
10. `unique_vehicle_ids`
11. `bsm_mean_iat`
12. `n_flood`
13. `max_iat`
14. `max_pos_deviation`
15. `mean_speed_deviation`

Macro F1: 1.0000, MCC: 1.0000
