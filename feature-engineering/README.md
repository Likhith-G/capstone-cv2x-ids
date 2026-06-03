# Feature Engineering

**Status: In Progress**

---

## Objective

Identify the optimal feature subset from the CV2X-IDS dataset that best discriminates each attack type, using ANOVA F-score and Mutual Information. Initial pipeline development and validation was completed on the VeReMi dataset. This workstream now applies that methodology to the custom simulation dataset.

---

## Input

| File | Location |
|---|---|
| Full dataset | `../dataset-expansion/output/dataset_v3.csv` |
| Feature schema | `../dataset-expansion/output/DATASET_CARD.md` |
| Baseline importance | `../dataset-expansion/output/figures/feature_importance.png` |

---

## Constraints

- Target columns: `label_binary` (binary) and `label_attack_type` (12-class)
- Exclude context features: `true_speed_mean`, `true_speed_std`, `distance_to_gnb`, `region_id`
- Exclude zero-variance features: `bsm_std_iat`, `heading_change_rate`, `bsm_size_mean`, `bsm_size_std`, `true_speed_std`
- Account for class imbalance (88.5% benign) before computing F-scores
- Compare both ANOVA F-score and Mutual Information — report whether the two methods agree on the optimal subset

---

## Expected Output

- Ranked feature list from ANOVA F-score and Mutual Information
- Final recommended feature subset with justification
- Analysis of how the optimal subset changes between binary and 12-class targets
