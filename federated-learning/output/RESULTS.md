# Federated Learning Results

## Centralized Baseline

- **Test Macro F1:** 1.0000
- **Test MCC:** 1.0000
- **Test Accuracy:** 1.0000
- **Best epoch:** 3

## FL Experiment Results (mean ± std across 3 seeds)

| Partition | C | α | E | F1 (mean±std) | MCC (mean±std) |
|---|---|---|---|---|---|
| dirichlet | 3 | 0.1 | 1 | 0.8165±0.1796 | 0.9176±0.0806 |
| dirichlet | 3 | 0.1 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 0.5 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 0.5 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 1.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 1.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 100.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 100.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 0.1 | 1 | 0.6336±0.1755 | 0.8144±0.0861 |
| dirichlet | 5 | 0.1 | 3 | 0.9063±0.0808 | 0.9496±0.0415 |
| dirichlet | 5 | 0.5 | 1 | 0.9720±0.0396 | 0.9835±0.0234 |
| dirichlet | 5 | 0.5 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 1.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 1.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 100.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 100.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| scenario | 3 | - | 1 | 0.5578±0.0929 | 0.7562±0.0535 |
| scenario | 3 | - | 3 | 0.5073±0.0709 | 0.7294±0.0464 |
| scenario | 5 | - | 1 | 0.3951±0.1144 | 0.6682±0.0759 |
| scenario | 5 | - | 3 | 0.3430±0.1016 | 0.6362±0.0438 |

## Communication Cost

- Model: 12780 parameters (51120 bytes)
- Centralized (one-time raw data upload): 0.7538 MB
- FL (C=3, 50 rounds): 14.6255 MB (ratio: 19.40x vs centralized)
- FL (C=5, 50 rounds): 24.3759 MB (ratio: 32.34x vs centralized)

### Important Caveat: Small-Dataset Artifact

The 19–32x overhead is an artifact of comparing FL training communication against a **one-time upload of a small, pre-collected dataset** (12,350 samples × 64 bytes = 0.75 MB). In a real C-V2X deployment, this comparison is misleading because centralized training requires **continuous raw data streaming**, not a single upload.

**Break-even analysis.** Each vehicle transmits BSMs at 10 Hz with ~300 bytes per message (SAE J2735), producing a raw data stream of **3,000 bytes/sec per vehicle**:

| Metric | Value |
|--------|-------|
| One FL model update (upload) | 51,120 bytes |
| Time for 1 vehicle to stream equivalent data | **17 seconds** |
| FL cost per RSU, 50 rounds (C=5) | 5.1 MB |
| Raw stream from 8 vehicles per RSU | 24 KB/s |
| Time to match total FL training cost | **~3.5 minutes** |
| Raw data from 8 vehicles over 10-min session | 14.4 MB (2.8x the FL cost) |

After just **17 seconds** of driving, a single vehicle has already streamed more raw data than one complete model weight upload. An RSU serving 8 vehicles surpasses the **entire 50-round FL training cost** within ~3.5 minutes — less than a single red-light cycle. Over a typical 10-minute urban driving session, raw streaming produces 2.8x more data than the full FL training budget.

At production scale with hundreds of vehicles per RSU, the ratio inverts dramatically: FL sends periodic 51 KB weight updates while centralized streaming grows linearly with vehicle count. FL also never transmits raw feature data, preserving driver location privacy.

## Inference Latency

- Mean: 27.4 μs
- P95: 29.3 μs
- P99: 30.9 μs
- Max: 40.3 μs
- **Headroom:** 3648x under 100ms PC5 budget
- **Passes 100ms constraint:** Yes
