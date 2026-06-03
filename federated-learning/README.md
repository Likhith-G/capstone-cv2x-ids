# Federated Learning

**Status: Pending — starts after Classification workstream delivers model architecture**  
**Owner:** Likhith Lokesh Gowda (s4062973)  
**Research Question:** RQ3 — Federated aggregation under data heterogeneity

---

## Objective

Implement a FedAvg federated learning prototype with at least 3 client nodes, each trained on a non-IID geographic partition of the dataset. Evaluate detection accuracy, convergence behavior, bandwidth overhead vs a centralized baseline, and inference latency relative to the 100ms PC5 constraint.

---

## Inputs

From Classification workstream:
- Final model architecture (PyTorch recommended for Flower compatibility)
- Recommended feature subset

From Dataset Expansion workstream:
- `../dataset-expansion/output/train.csv` — will be re-partitioned for FL clients
- `../dataset-expansion/pipeline/partition_fl.py` — Dirichlet non-IID partitioner (already written)

---

## FL Pipeline Design

The pipeline follows the standard federated loop:
1. Central server distributes global model
2. Each client trains locally on its partition
3. Client returns only weight updates (no raw data)
4. Server aggregates with FedAvg and redistributes

**Aggregation configurations (scope-tiered):**

| Algorithm | Scope | Semester |
|---|---|---|
| FedAvg | Core baseline | Part A |
| FedProx | Supporting — non-IID robustness | Part B |
| Krum | Stretch — Byzantine resilience | Part B |

**Tools:** Python + [Flower](https://flower.dev/) + PyTorch

---

## Non-IID Partitioning

The `partition_fl.py` script uses Dirichlet distribution to create non-IID client datasets. Default parameters: 5 clients, alpha=0.5 (moderate heterogeneity). Lower alpha = more heterogeneous.

```bash
python3 partition_fl.py ../dataset-expansion/output/train.csv 5 0.5 ./partitions/
```

---

## Evaluation Targets

- Detection accuracy, Macro F1, MCC per FL round
- Convergence curve (rounds to reach target accuracy)
- Bandwidth overhead vs centralized baseline
- Inference latency per sample (target: below 100ms)

---

## Place your work here

Add FL training scripts, Flower server/client code, and results to this folder as the workstream progresses.
