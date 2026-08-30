# Cybersecurity for Connected Cars: Edge-Based Federated Intrusion Detection

**Course:** OENG1167 Engineering Capstone Project, RMIT University
**Supervisor:** A/Prof Ke (Desmond) Wang
**Research Mentor:** Mr. Kanwardeep Singh Gahlot

## Team

| Name | Student ID |
|---|---|
| Likhith Lokesh Gowda | s4062973 |
| Verna Nakhla | s3945172 |
| Joshua Wong | s3944445 |
| Ken Navarro | s4005415 |
| Andrew Ng | s4004645 |

---

## Project Overview

Connected vehicles broadcast Basic Safety Messages (BSMs) at 10 Hz carrying position, speed, and heading data. These messages are unauthenticated by design to meet 100ms latency requirements, making them vulnerable to position spoofing, replay attacks, false data injection, Sybil attacks, and DoS flooding.

This project builds a Federated Learning Intrusion Detection System (FL-IDS) where each roadside edge node trains a local detection model and shares only model weight updates, never raw GPS data, with a central aggregation server.

**Key research questions:**
- RQ1: How to generate a labelled 5G C-V2X dataset through NS-3 simulation
- RQ2: Which features best discriminate C-V2X attack types
- RQ3: How non-IID data heterogeneity affects FedAvg convergence and whether FedProx recovers performance
- RQ4: Can inference meet the 100ms PC5 deadline on edge hardware

See [`docs/Project_Proposal_Assessment1.pdf`](docs/Project_Proposal_Assessment1.pdf) for the full project proposal.

---

## Repository Structure

```
capstone-cv2x-ids/
├── docs/                        # Documentation and results
│   ├── RESULTS_SECTION.md       # Full results write-up (for Progress Report)
│   ├── walkthrough.md           # Project walkthrough and verified deliverables
│   └── Project_Proposal_Assessment1.pdf
│
├── dataset-expansion/           # RQ1: Dataset Generation
│   ├── simulation/              # NS-3 C++ source
│   ├── pipeline/                # Python scripts and shell orchestration
│   └── output/                  # Generated dataset, figures, and metadata
│
├── feature-engineering/         # RQ2a: Feature Selection
│   └── output/                  # Rankings, SHAP plots, selected features
│
├── classification/              # RQ2b: Multiclass Classification
│   └── output/                  # Metrics, confusion matrices, model spec
│
├── federated-learning/          # RQ3 + RQ4: Federated Learning + Edge Deployment
│   └── output/                  # 60 experiments, aggregated results, figures
│
├── simulation/                  # NS-3 sidelink simulation module
│   └── cv2xids/                 # ITS messaging, DCC, mobility, attacks, traces
│
└── analysis/                    # Cross-layer detection pipeline
    └── *.py                     # features, validation, benchmarks, federation
```

---

## Cross-layer sidelink pipeline

A second generation of the dataset and detection pipeline moves the radio link
from a 5G Uu uplink to a direct PC5 sidelink and adds physical and MAC layer
features alongside the application layer ones.

**What changed in the simulation.** Vehicles now talk to each other directly
over an NR V2X Mode 2 sidelink rather than uplinking to a MEC server. Benign
traffic is a real ETSI ITS message mix, with CAM, DENM, CPM and VAM generated
from their own triggering conditions to EN 302 637-2, EN 302 637-3,
TS 103 324 and TS 103 300-3, and gated by TS 102 687 reactive congestion
control. Mobility is Intelligent Driver Model car following with three vehicle
classes, which removes the fixed message period that constant velocity produces
and removes the external traffic simulator dependency. Roadside units give the
federated work a partition based on real geography.

**What changed in the data.** Ground truth never travels over the air. The
transmitter logs it, the receiver logs only what it received, and the two are
joined offline on a message identifier, so a feature that a real receiver could
not compute cannot enter the dataset. Each record is one observer's view of one
claimed station over one time window, with 22 application layer features and 28
physical and MAC layer features.

**What changed in the evaluation.** Every split is grouped by transmitting
station, the dataset is put through eight adversarial integrity gates before any
model is trained, false positive rate is reported at true prevalence rather than
on a balanced set, and detection latency counts the time the window takes to
fill rather than the forward pass alone.

See [`simulation/README.md`](simulation/README.md) for building and running the
NS-3 module, and [`analysis/README.md`](analysis/README.md) for the pipeline
and the methodology constraints it enforces.

---

## Dataset Quick Reference

The CV2X-IDS dataset is in [`dataset-expansion/output/`](dataset-expansion/output/).

| Property | Value |
|---|---|
| Total rows | 18,240 |
| Features | 24 informative (39 columns total) |
| Scenarios | 12 (1 Benign + 5 Network attacks + 6 Vehicular attacks) |
| Topology | 40 UEs, 4 gNBs, 600s per scenario |
| Simulation | NS-3.42 + 5G-LENA NR module |

See [`dataset-expansion/output/DATASET_CARD.md`](dataset-expansion/output/DATASET_CARD.md) for the full schema, feature list, and baseline results.

---

## Reproducing the Dataset

> The raw per-packet NS-3 logs (~837 MB) are excluded from this repository. They are regenerated by running the pipeline from scratch.

**Requirements:** NS-3.42 with 5G-LENA NR module installed. Python 3.9+ with `numpy`, `pandas`, `scikit-learn`, `matplotlib`.

```bash
cd ~/ns-allinone-3.42/ns-3.42

# Copy simulation source
cp path/to/dataset-expansion/simulation/simulation.cc scratch/

# Copy pipeline scripts
cp path/to/dataset-expansion/pipeline/* pipeline/

# Run full pipeline (~2-3 hours on M2)
bash pipeline/run_all.sh
```
