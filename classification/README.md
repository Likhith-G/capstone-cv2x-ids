# Multiclass Classification

**Status: In Progress**  
**Owner:** Verna Nakhla (s3945172), Ken Navarro (s4005415)  
**Research Question:** RQ2b — Multiclass classification baseline

---

## Objective

Train and evaluate multiclass classifiers on the CV2X-IDS-V3 dataset using the feature subset selected by the Feature Engineering team. Report per-class F1, MCC, and false positive rate across all 12 attack classes. The final model architecture is passed to the Federated Learning workstream.

---

## Input

From the Dataset Expansion workstream:

| File | Location | Notes |
|---|---|---|
| `train.csv` | `../dataset-expansion/output/train.csv` | 12,350 rows |
| `val.csv` | `../dataset-expansion/output/val.csv` | 2,736 rows — for hyperparameter tuning only |
| `test.csv` | `../dataset-expansion/output/test.csv` | 3,154 rows — final evaluation only |
| `split_metadata.json` | `../dataset-expansion/output/split_metadata.json` | Node-to-split mapping |

From the Feature Engineering workstream:
- Final feature subset list (to be provided by Josh + Andrew)

---

## Constraints

- **Do not re-shuffle or re-split the provided CSV files.** The split was engineered to guarantee all 12 attack types appear in every split with zero temporal leakage. Load them directly.
- Evaluate on `test.csv` only for final reported metrics. Use `val.csv` only for tuning.
- Class imbalance is 88.5% benign vs 1.04% per attack type — use class weighting, focal loss, or SMOTE in your training loop.
- Primary metrics per the proposal: Macro F1, MCC (Matthews Correlation Coefficient), per-class precision and recall, and false positive rate.

---

## Label Columns

| Column | Type | Values |
|---|---|---|
| `label_binary` | Binary | 0 = Benign, 1 = Attack |
| `label_attack_type` | 12-class | Benign, UDPFlood, ICMPFlood, SYNFlood, HTTPFlood, SlowDoS, PositionSpoof, RandomPosition, Replay, FalseDataInjection, Sybil, VehicularDoS |

---

## Expected Output

- Trained model (saved as a file in this folder — `.pkl` or `.pth`)
- Per-class classification report (precision, recall, F1, MCC)
- Confusion matrix
- Final recommended model architecture for Likhith to use in the FL workstream

---

## Place your work here

Add notebooks, scripts, model files, and results to this folder as the workstream progresses.
