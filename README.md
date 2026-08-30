# Cybersecurity for Connected Cars: Edge-Based Federated Intrusion Detection

**Course:** OENG1167 / OENG1168 Engineering Capstone Project, RMIT University
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
- RQ1: How to generate a labelled C-V2X dataset through NS-3 simulation
- RQ2: Which features best discriminate C-V2X attack types
- RQ3: How non-IID data heterogeneity affects federated convergence, and which aggregation rule holds up under it
- RQ4: Can detection meet the 100ms PC5 deadline on edge hardware

See [`docs/Project_Proposal_Assessment1.pdf`](docs/Project_Proposal_Assessment1.pdf) for the full project proposal.

### Two generations of this work

The repository holds two pipelines, and the distinction matters when reading
any result in it.

**v1**, in `dataset-expansion/`, `feature-engineering/`, `classification/` and
`federated-learning/`, is the OENG1167 submission. Vehicles uplink Basic Safety
Messages to a MEC server over a 5G Uu link, mobility is constant velocity, and
detection uses traffic and payload features with nothing from the physical or
MAC layer. It is kept intact as the record
of what was submitted. Its reported scores are not deployment performance, for
reasons given in the notice at the top of each of those directories.

**v2**, in `simulation/` and `analysis/`, is the current pipeline. The radio
link is a direct PC5 sidelink, benign traffic is a standards-compliant ETSI ITS
message mix under congestion control, mobility is car following, and features
span the physical, MAC and application layers. Ground truth never travels over
the air. Read `simulation/README.md` and `analysis/README.md` for this one.

New work goes in v2. The v1 tree is not used by any of it.

---

## Repository Structure

```
capstone-cv2x-ids/
├── docs/
│   ├── RESULTS_SECTION.md       # v1 results write-up, as submitted
│   ├── walkthrough.md           # v1 walkthrough and deliverables
│   ├── patches/                 # additive patch to 5G-LENA, required to build v2
│   └── Project_Proposal_Assessment1.pdf
│
├── simulation/                  # v2: NS-3 PC5 sidelink simulation module
│   └── cv2xids/                 # ITS messaging, DCC, car following, attacks, traces
│
├── analysis/                    # v2: cross-layer detection pipeline
│   ├── build_features.py        # windowing, application and radio features
│   ├── validate_dataset.py      # eight adversarial integrity gates
│   ├── benchmark.py             # application against radio against fused
│   ├── pooled_consensus.py      # cross-receiver position verification
│   ├── federated.py             # FedAvg, FedProx, FedNova, FedLC, FedProto, DP
│   ├── persistence_filter.py    # alert episodes and K-of-M operating points
│   └── regenerate.sh            # whole chain, one stage per log
│
├── dataset-expansion/           # v1: dataset generation
│   ├── simulation/              # NS-3 C++ source
│   ├── pipeline/                # Python scripts and shell orchestration
│   └── output/                  # generated dataset, figures, metadata
│
├── feature-engineering/         # v1: feature selection
│   └── output/                  # rankings, SHAP plots, selected features
│
├── classification/              # v1: multiclass classification
│   └── output/                  # metrics, confusion matrices, model spec
│
└── federated-learning/          # v1: federated learning and edge deployment
    └── output/                  # 60 experiments, aggregated results, figures
```

---

## Cross-layer sidelink pipeline

What v2 changes, and why each change was needed.

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

**A limit worth stating up front.** Mode 2 resource grants in 5G-LENA are data
driven, so a reserved resource is only used when there is data for it and no
attacker can hoard the channel. The two radio-layer attacks in the scenario,
sensing manipulation and resource exhaustion, therefore produce no signature.
That is a property of the simulator rather than of C-V2X, and it is why the
cross-layer argument rests on radio features catching application-layer
attacks.

See [`simulation/README.md`](simulation/README.md) for building and running the
NS-3 module, and [`analysis/README.md`](analysis/README.md) for the pipeline
and the methodology constraints it enforces.

---

## Datasets

Two corpora, one per pipeline generation. Neither raw trace set is in the
repository; both are regenerated from source.

| | v2 sidelink corpus | v1 uplink dataset |
|---|---|---|
| Radio link | NR V2X Mode 2 PC5 sidelink | 5G Uu uplink to a MEC server |
| Benign traffic | ETSI CAM, DENM, CPM and VAM under TS 102 687 congestion control | BSM at a fixed 10 Hz |
| Mobility | Intelligent Driver Model car following, three vehicle classes | constant velocity |
| Topology | 6 km, three lanes each way, 90 vehicles, 12 roadside units | 40 UEs, 4 gNBs |
| Detection unit | one observer's view of one claimed station over one window | one node over one window |
| Windows | 1,644,280 across 8 seeds | 18,240 across 12 scenarios |
| Stations | 720, of which 519 benign | 40 per scenario, 5 of them attackers |
| Classes | 10 | 12 |
| Features | 50, being 22 application and 28 physical and MAC | 24 informative of 39 columns |
| Simulator | NS-3.42 with 5G-LENA `nr` at tag `v2x-1.1` | NS-3.42 with 5G-LENA NR |
| Where it lives | regenerated into a run directory outside the repo | `dataset-expansion/output/` |

The v1 schema and per-class breakdown are in
[`dataset-expansion/output/DATASET_CARD.md`](dataset-expansion/output/DATASET_CARD.md).
Read the notice at the top of that file before quoting any figure from it.

---

## Reproducing

### v2, the current pipeline

Build the simulator module and apply the one required patch to 5G-LENA, both
covered in [`simulation/README.md`](simulation/README.md). Generate seeds, then
take the finished campaign through every analysis stage in one pass:

```bash
./analysis/regenerate.sh <run-dir> <max-time-ms> seed1 seed2 ... seed8
```

Each stage writes its own log, so a single stage can be repeated after a fix
without redoing the work before it. Run `analysis/check_campaign.py` on the
first seed before letting the rest generate; it reads only the small transmit
table and catches the misconfigurations that are expensive to find afterwards.
[`analysis/README.md`](analysis/README.md) documents every script and the
methodology constraints the pipeline enforces.

**Requirements:** NS-3.42 with 5G-LENA `nr` at tag `v2x-1.1`, built under
Python 3.12. Analysis runs on Python 3.9 with `numpy`, `pandas`,
`scikit-learn`, `scipy`, `matplotlib` and `torch`. The two interpreters are
separate and should not be mixed.

### v1, as submitted

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
