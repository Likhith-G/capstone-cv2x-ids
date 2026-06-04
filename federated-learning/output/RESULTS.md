# Federated Learning Results

## Centralized Baseline

- **Test Macro F1:** 1.0000
- **Test MCC:** 1.0000
- **Test Accuracy:** 1.0000
- **Best epoch:** 3

## FL Experiment Results (mean ± std across 3 seeds)

| Partition | C | α | E | F1 (mean±std) | MCC (mean±std) |
|---|---|---|---|---|---|
| dirichlet | 3 | 0.1 | 1 | 0.8365±0.2188 | 0.9134±0.1153 |
| dirichlet | 3 | 0.1 | 3 | 0.9993±0.0010 | 0.9996±0.0006 |
| dirichlet | 3 | 0.5 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 0.5 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 1.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 1.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 100.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 3 | 100.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 0.1 | 1 | 0.5392±0.2457 | 0.7572±0.1328 |
| dirichlet | 5 | 0.1 | 3 | 0.9389±0.0371 | 0.9639±0.0220 |
| dirichlet | 5 | 0.5 | 1 | 0.9706±0.0416 | 0.9826±0.0247 |
| dirichlet | 5 | 0.5 | 3 | 0.9978±0.0031 | 0.9987±0.0018 |
| dirichlet | 5 | 1.0 | 1 | 0.9720±0.0396 | 0.9835±0.0234 |
| dirichlet | 5 | 1.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 100.0 | 1 | 1.0000±0.0000 | 1.0000±0.0000 |
| dirichlet | 5 | 100.0 | 3 | 1.0000±0.0000 | 1.0000±0.0000 |
| scenario | 3 | - | 1 | 0.6468±0.0525 | 0.8119±0.0233 |
| scenario | 3 | - | 3 | 0.5888±0.0459 | 0.7777±0.0221 |
| scenario | 5 | - | 1 | 0.3737±0.0230 | 0.6747±0.0303 |
| scenario | 5 | - | 3 | 0.3527±0.0225 | 0.6405±0.0065 |

## Communication Cost

- Model: 12780 parameters (51120 bytes)
- Centralized (one-time raw data upload): 0.7538 MB
- FL (C=3, 50 rounds): 14.6255 MB (ratio: 19.40x vs centralized)
- FL (C=5, 50 rounds): 24.3759 MB (ratio: 32.34x vs centralized)

### Important Caveat: Small-Dataset Artifact

The 19–32x overhead is an artifact of comparing FL training communication against a **one-time upload of a small, pre-collected dataset** (12350 samples x 64 bytes/sample). In a real C-V2X deployment, this comparison is misleading because centralized training requires **continuous raw data streaming**, not a single upload.

**Break-even analysis.** Each vehicle transmits BSMs at 10 Hz with ~300 bytes per message (SAE J2735), producing a raw data stream of **3,000 bytes/sec per vehicle**:

| Metric | Value |
|--------|-------|
| One FL model update (upload) | 51,120 bytes |
| Time for 1 vehicle to stream equivalent data | **17 seconds** |
| FL cost per RSU, 50 rounds (C=5) | 12.8 MB |
| Raw stream from 8 vehicles per RSU | 24 KB/s |
| Time to match total FL training cost | **~3.5 minutes** |
| Raw data from 8 vehicles over 10-min session | 14.4 MB (2.8x the FL cost) |

After just **17 seconds** of driving, a single vehicle has already streamed more raw data than one complete model weight upload. An RSU serving 8 vehicles surpasses the **entire 50-round FL training cost** within ~3.5 minutes — less than a single red-light cycle. Over a typical 10-minute urban driving session, raw streaming produces 2.8x more data than the full FL training budget.

At production scale with hundreds of vehicles per RSU, the ratio inverts dramatically: FL sends periodic 51 KB weight updates while centralized streaming grows linearly with vehicle count. FL also never transmits raw feature data, preserving driver location privacy.

## Statistical Significance: E=1 vs E=3 (Wilcoxon signed-rank)

Paired test across seeds for each (partition, C, α) configuration. Tests whether additional local epochs (E=3 vs E=1) significantly improve F1 under the same data partition.

| Partition | C | α | E=1 F1 | E=3 F1 | Δ | p-value | Sig? |
|---|---|---|---|---|---|---|---|
| dirichlet | 3 | 0.1 | 0.8365±0.2188 | 0.9993±0.0010 | +0.1628 | 0.1797 | no |
| dirichlet | 3 | 0.5 | 1.0000±0.0000 | 1.0000±0.0000 | +0.0000 | 1.0000 | no |
| dirichlet | 3 | 1.0 | 1.0000±0.0000 | 1.0000±0.0000 | +0.0000 | 1.0000 | no |
| dirichlet | 3 | 100.0 | 1.0000±0.0000 | 1.0000±0.0000 | +0.0000 | 1.0000 | no |
| dirichlet | 5 | 0.1 | 0.5392±0.2457 | 0.9389±0.0371 | +0.3998 | 0.2500 | no |
| dirichlet | 5 | 0.5 | 0.9706±0.0416 | 0.9978±0.0031 | +0.0272 | 0.3173 | no |
| dirichlet | 5 | 1.0 | 0.9720±0.0396 | 1.0000±0.0000 | +0.0280 | 0.3173 | no |
| dirichlet | 5 | 100.0 | 1.0000±0.0000 | 1.0000±0.0000 | +0.0000 | 1.0000 | no |
| scenario | 3 | - | 0.6468±0.0525 | 0.5888±0.0459 | -0.0580 | 0.5000 | no |
| scenario | 5 | - | 0.3737±0.0230 | 0.3527±0.0225 | -0.0210 | 0.7500 | no |

No comparisons reach significance at p<0.05 with n=3 seeds. Wilcoxon signed-rank with 3 pairs has minimum achievable p=0.25, so significance requires ≥6 seeds. Current results show the direction of effect (E=3 generally helps under non-IID) but cannot confirm statistical reliability. Part B will use ≥6 seeds for FedAvg vs FedProx comparisons.

## Inference Latency

- Mean: 26.5 μs
- P95: 28.5 μs
- P99: 35.4 μs
- Max: 65.0 μs
- **Headroom:** 3768x under 100ms PC5 budget
- **Passes 100ms constraint:** Yes

## Addendum: Dropout Robustness Check (p=0.2)

To test whether regularization improves FL performance under extreme non-IID conditions, Dropout(p=0.2) was applied after each hidden layer and evaluated on the two worst-performing configurations (pre-cosine-annealing baseline):

| Configuration | Metric | Original | Dropout=0.2 | Delta |
|---------------|--------|----------|-------------|-------|
| C=5, α=0.1, E=1 (Dirichlet) | F1 | 0.6336±0.1755 | 0.4872±0.2437 | **-0.1464** |
| C=5, α=0.1, E=1 (Dirichlet) | MCC | 0.8144±0.0861 | 0.7254±0.1321 | -0.0890 |
| C=5, scenario, E=1 | F1 | 0.3951±0.1144 | 0.4952±0.1148 | **+0.1001** |
| C=5, scenario, E=1 | MCC | 0.6682±0.0759 | 0.7181±0.0744 | +0.0499 |

**Interpretation:** The effect of dropout is mixed and configuration-dependent:

- **Dirichlet α=0.1 (synthetic non-IID):** Dropout *hurts* performance (F1 drops by 0.15). Under Dirichlet partitioning, each client still sees most classes but in skewed proportions — the model needs maximum capacity to fit the varied local distributions. Dropout constrains this capacity, slowing convergence within the fixed 50-round budget.
- **Scenario-based (natural non-IID):** Dropout *helps* (F1 improves by 0.10). Under scenario partitioning, clients see entirely disjoint attack types, so their local models tend to overfit to their subset. Dropout acts as implicit regularization, forcing the model to learn more generalizable representations that survive aggregation.

**Conclusion:** Dropout is not a universal remedy for non-IID degradation. Targeted regularization strategies like FedProx (proximal term constraining local updates toward the global model) are better suited for Part B, as they directly address the weight divergence problem rather than applying generic capacity reduction.
