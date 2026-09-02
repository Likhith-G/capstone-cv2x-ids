# Cybersecurity for Connected Cars: Edge-Based Federated Intrusion Detection

A labelled C-V2X sidelink intrusion detection dataset and the cross-layer
detection pipeline built on it.

Connected vehicles broadcast safety messages several times a second carrying
position, speed and heading. Those messages are signed: ETSI TS 103 097 wraps
every one of them in an ECDSA signature under a pseudonym certificate, and IEEE
1609.2 does the same in North America. What the signature establishes is that
the message came from a credentialled station and was not altered in transit. It
establishes nothing about whether the position inside it is true, so a station
holding valid credentials can transmit a correctly signed message whose contents
are false and no receiver can tell from the cryptography alone. This work
generates such misbehaviour in simulation, records only what a receiver could
actually observe, and evaluates detection from the application layer, the radio
layer and the two combined.

---

## The dataset

Generated with NS-3.42 and the 5G-LENA `nr` module at tag `v2x-1.1`. Vehicles
exchange messages directly over an NR V2X Mode 2 PC5 sidelink.

| Property | Value |
|---|---|
| Road | 6 km, three lanes each way, 90 vehicles, 12 roadside units |
| Mobility | Intelligent Driver Model car following, three vehicle classes |
| Benign traffic | ETSI CAM, DENM, CPM and VAM, each from its own triggering conditions, under TS 102 687 reactive congestion control |
| Seeds | 8 |
| Windows | 1,644,280 |
| Stations | 720, of which 519 benign |
| Classes | 10, being benign and nine misbehaviour types |
| Features | 50, being 22 application layer and 28 physical and MAC layer |
| Detection unit | one observer's view of one claimed station over one time window |

**Misbehaviour types.** Constant position offset, small position offset, random
position offset, replayed position, speed falsification, sybil, high-rate denial
of service, low-rate denial of service, and sensing manipulation.

**Ground truth never travels over the air.** The transmitter logs it, the
receiver logs only what it received, and the two are joined offline on a message
identifier. `build_features.py` opens only the receive-side tables, and an
assertion fails the run if any column named `key_*` or `label_*` reaches the
feature list. A feature that a real receiver could not compute cannot enter the
dataset by accident.

**A limit worth stating up front.** Mode 2 resource grants in 5G-LENA are data
driven, so a reserved resource is only used when there is data for it and no
attacker can hoard the channel. Sensing manipulation therefore produces no
signature. That is a property of the simulator rather than of C-V2X, and it is
why the cross-layer argument rests on radio features catching application-layer
misbehaviour.

---

## Pipeline

[`simulation/`](simulation/) is the ns-3 contrib module that generates the
traces. [`analysis/`](analysis/) takes them from raw simulator tables through to
results: windowing and feature extraction, eight adversarial integrity gates,
the cross-layer benchmark, cross-receiver position verification, the federated
aggregation panel, and the deployment evaluation.

Every split is grouped by transmitting station, false positive rate is reported
at true prevalence rather than on a balanced set, and detection latency counts
the time a window takes to fill rather than the forward pass alone.

---

## Reproducing

Build the simulation module and apply the one required patch to 5G-LENA, both
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

**Requirements.** NS-3.42 with 5G-LENA `nr` at tag `v2x-1.1`, built under
Python 3.12. Analysis runs on Python 3.9 with `numpy`, `pandas`,
`scikit-learn`, `scipy`, `matplotlib` and `torch`. The two interpreters are
separate and should not be mixed.

Traces are not held in the repository. They are regenerated from source.

---

## Repository layout

```
capstone-cv2x-ids/
├── simulation/                  # ns-3 contrib module
│   └── cv2xids/                 # ITS messaging, DCC, car following, attacks, traces
│
├── analysis/                    # detection pipeline
│   ├── build_features.py        # windowing, application and radio features
│   ├── validate_dataset.py      # eight adversarial integrity gates
│   ├── benchmark.py             # application against radio against fused
│   ├── pooled_consensus.py      # cross-receiver position verification
│   ├── federated.py             # FedAvg, FedProx, FedNova, FedLC, FedProto, DP
│   ├── persistence_filter.py    # alert episodes and K-of-M operating points
│   └── regenerate.sh            # whole chain, one stage per log
│
├── docs/patches/                # additive patch to 5G-LENA, required to build
│
└── capstone/                    # earlier coursework material, archived
```

[`capstone/`](capstone/) holds the earlier RMIT coursework phase: a separate
simulation over a 5G uplink, its feature selection, classification and federated
learning workstreams, and the progress report. It is kept for reference and is
not used by anything above it. See [`capstone/README.md`](capstone/README.md).
