# Feature Engineering

**Status: In Progress**  
**Owner:** Joshua Wong (s3944445), Andrew Ng (s4004645)  
**Research Question:** RQ2a — Feature selection for C-V2X attack discrimination

---

## Objective

Identify the optimal feature subset from the 23 informative features in CV2X-IDS-V3 that best discriminates each C-V2X attack type. The selected feature subset is passed to the Classification workstream.

The proposal specifies two methods to compare:
1. ANOVA F-score
2. Mutual Information

---

## Input

From the Dataset Expansion workstream:

| File | Location | Notes |
|---|---|---|
| `dataset_v3.csv` | `../dataset-expansion/output/dataset_v3.csv` | Full 18,240-row dataset |
| `DATASET_CARD.md` | `../dataset-expansion/output/DATASET_CARD.md` | Feature schema |
| `feature_importance.png` | `../dataset-expansion/output/figures/feature_importance.png` | RF Gini baseline |

---

## Constraints

- Target columns: `label_binary` (binary) and `label_attack_type` (12-class)
- Do NOT include context features: `true_speed_mean`, `true_speed_std`, `distance_to_gnb`, `region_id`
- Do NOT include zero-variance features: `bsm_std_iat`, `heading_change_rate`, `bsm_size_mean`, `bsm_size_std`, `true_speed_std`
- Account for class imbalance (88.5% benign) before computing F-scores — raw ANOVA on imbalanced data will overweight majority class
- Compare both methods: report whether the optimal subset is the same under ANOVA and MI, or if they disagree on which features to include

---

## Expected Output

- Ranked feature list from both ANOVA F-score and Mutual Information
- Final recommended feature subset (with justification for the cutoff chosen)
- Analysis of whether the optimal subset changes between binary and multiclass targets
- Metrics: how much classification performance changes as features are added/removed

Pass the final feature list to Verna and Ken before they begin model training.

---

## Place your work here

Add notebooks, scripts, and results to this folder as the workstream progresses.
