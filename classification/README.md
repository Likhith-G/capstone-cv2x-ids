# Multiclass Classification

**Status: In Progress**

---

## Objective

Train and evaluate multiclass classifiers on the CV2X-IDS dataset using the feature subset from the Feature Engineering workstream. Initial model development was completed on the VeReMi dataset. This workstream now applies those architectures to the custom simulation dataset and reports per-class F1, MCC, and false positive rate across all 12 attack classes.

---

## Input

| File | Location | Notes |
|---|---|---|
| Training split | `../dataset-expansion/output/train.csv` | 12,350 rows |
| Validation split | `../dataset-expansion/output/val.csv` | 2,736 rows — tuning only |
| Test split | `../dataset-expansion/output/test.csv` | 3,154 rows — final evaluation |
| Split metadata | `../dataset-expansion/output/split_metadata.json` | Node-to-split mapping |

Feature subset list to be provided by the Feature Engineering workstream.

---

## Constraints

- **Do not re-shuffle or re-split the provided CSV files.** The split guarantees all 12 attack types appear in every partition with zero temporal leakage. Load them directly.
- Use `val.csv` for hyperparameter tuning only. Report final metrics on `test.csv`.
- Class imbalance is 88.5% benign — use class weighting, focal loss, or SMOTE.
- Primary metrics: Macro F1, MCC, per-class precision and recall, false positive rate.

---

## Label Columns

| Column | Type | Values |
|---|---|---|
| `label_binary` | Binary | 0 = Benign, 1 = Attack |
| `label_attack_type` | 12-class | Benign, UDPFlood, ICMPFlood, SYNFlood, HTTPFlood, SlowDoS, PositionSpoof, RandomPosition, Replay, FalseDataInjection, Sybil, VehicularDoS |

---

## Expected Output

- Trained model file
- Per-class classification report (precision, recall, F1, MCC)
- Confusion matrix
- Final model architecture for use in the Federated Learning workstream
