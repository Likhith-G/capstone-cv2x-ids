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

**Note:** On this small simulation dataset, one-time centralized upload is cheaper in bytes. In a real C-V2X deployment where vehicles continuously stream BSMs at 10 Hz, FL dramatically reduces ongoing communication compared to streaming raw traffic. FL also never transmits raw feature data (privacy).

## Inference Latency

- Mean: 27.4 μs
- P95: 29.3 μs
- P99: 30.9 μs
- Max: 40.3 μs
- **Headroom:** 3648x under 100ms PC5 budget
- **Passes 100ms constraint:** Yes
