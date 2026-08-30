# Dataset Expansion — CV2X-IDS

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

## What Was Built

A simulation-based intrusion detection dataset for 5G C-V2X networks, generated using NS-3.42 with the 5G-LENA NR module. The dataset covers 12 attack scenarios (11 attack types + 1 benign baseline) across a highway corridor simulation.

| Property | Value |
|---|---|
| Total rows | 18,240 time-windowed feature vectors |
| Columns | 39 (24 informative after zero-variance and context exclusion) |
| Scenarios | 12 (S00 Benign, S01–S05 Network, S06–S11 Vehicular) |
| Topology | 40 UEs, 4 gNBs, 5 attackers per scenario |
| Simulation time | 600 seconds per scenario |
| Window size | 30 seconds, 15-second sliding step |
| Seeds | Dynamic per-scenario (43–54) |

---

## Attack Types

### Network Layer (S01–S05)
| Scenario | Attack | Rate | Pkt Size |
|---|---|---|---|
| S01 | UDP Flood | 500 pps | 1024 B |
| S02 | ICMP Flood | 200 pps | 64 B |
| S03 | SYN Flood | 400 pps (avg) | 64 B |
| S04 | HTTP Flood | 200 pps | 1460 B |
| S05 | Slow DoS | 4 pps (avg) | 64 B |

### Vehicular / Application Layer (S06–S11)
| Scenario | Attack | Mechanism |
|---|---|---|
| S06 | Position Spoof | BSM claims +500m offset from truth |
| S07 | Random Position | BSM claims random coordinates each cycle |
| S08 | Replay | Retransmits 5s-old cached BSMs |
| S09 | False Data Injection | BSM speed field inflated by a factor of 2.5-4.0x |
| S10 | Sybil | One node cycles through 5 fake vehicle IDs |
| S11 | Vehicular DoS | BSM rate elevated to 1000 Hz |

---

## Directory Contents

```
dataset-expansion/
├── simulation/
│   └── simulation.cc         # NS-3 C++ application (849 lines)
│
├── pipeline/
│   ├── run_all.sh            # Master orchestration script
│   ├── build_dataset.py      # Packet CSV → windowed features
│   ├── validate_dataset.py   # 57-check integrity suite
│   ├── baseline_classifier.py # Random Forest ablation (StratifiedGroupKFold)
│   ├── split_dataset.py      # Per-scenario stratified 70/15/15 splitter
│   ├── visualise.py          # 4 publication figures
│   └── partition_fl.py       # Dirichlet non-IID FL partitioner
│
└── output/
    ├── DATASET_CARD.md       # Full schema, baselines, known limitations
    ├── dataset.csv           # Full dataset (18,240 rows)
    ├── train.csv             # 12,350 rows (67.7%)
    ├── val.csv               # 2,736 rows (15.0%)
    ├── test.csv              # 3,154 rows (17.3%)
    ├── split_metadata.json   # Node-to-split mapping
    ├── flowmon_S*.xml        # NS-3 FlowMonitor outputs (reference)
    ├── meta_S*.json          # Per-scenario metadata
    └── figures/              # label_distribution, feature_importance,
                              # split_distribution, confusion_matrix
```

> **Note:** Raw per-packet logs (`packets_S*.csv`, ~837 MB total) are excluded from this repository — three individual files exceed GitHub's 100 MB file limit. Run `bash pipeline/run_all.sh` to regenerate them (requires NS-3.42 + 5G-LENA, ~2–3 hours).

---

## Baseline Results

Evaluated with Random Forest (200 estimators), `StratifiedGroupKFold(n_splits=5)` grouped by `(scenario_id, node_id)`.

| Configuration | Features | Macro F1 | Accuracy |
|---|---|---|---|
| Full (no context) | 24 | 1.0000 | 1.0000 |
| Network features only | 17 | 0.8405 | 0.9479 |
| Vehicular features only | 7 | 0.8308 | 0.9479 |
| No position features | 22 | 0.9201 | 0.9688 |
| No speed features | 22 | 0.9718 | 0.9896 |
| Multiclass (12 classes) | 24 | 1.0000 | 1.0000 |

The perfect F1 is legitimate in this simulation context: deterministic attack signals create clean decision boundaries. The ablation study demonstrates that both feature domains (network and vehicular) are required for full coverage.
