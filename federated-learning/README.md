# Federated Learning

**Status: Pending — starts after Classification workstream delivers model architecture**

---

## Objective

Implement a FedAvg federated learning prototype with at least 3 client nodes, each trained on a non-IID geographic partition of the dataset. Evaluate detection accuracy, convergence behavior, bandwidth overhead vs a centralized baseline, and inference latency relative to the 100ms PC5 constraint.

---

## Inputs

From Classification workstream:
- Final model architecture (PyTorch recommended for Flower compatibility)
- Recommended feature subset

From Dataset Expansion workstream:
- `../dataset-expansion/output/train.csv` — re-partitioned for FL clients using `partition_fl.py`

---

## FL Pipeline Design

Standard federated loop: server distributes global model → each client trains locally → client returns weight updates only → server aggregates with FedAvg and redistributes. No raw data leaves any client node.

**Aggregation configurations:**

| Algorithm | Scope | Semester |
|---|---|---|
| FedAvg | Core baseline | Part A |
| FedProx | Non-IID robustness | Part B |
| Krum | Byzantine resilience (stretch) | Part B |

**Tools:** Python + [Flower](https://flower.dev/) + PyTorch

---

## Non-IID Partitioning

```bash
python3 ../dataset-expansion/pipeline/partition_fl.py \
    ../dataset-expansion/output/train.csv 5 0.5 ./partitions/
```

Default: 5 clients, alpha=0.5 (moderate heterogeneity). Lower alpha = more non-IID.

---

## Evaluation Targets

- Detection accuracy, Macro F1, MCC per FL round
- Convergence curve (rounds to target accuracy)
- Bandwidth overhead vs centralized baseline
- Inference latency per sample (target: below 100ms)
