#!/usr/bin/env python3
"""
fedavg.py -- FedAvg server and client logic for CV2X-IDS.
Simulation-mode: all clients run in the same process.

Aggregation is cleanly separated so FedProx / Krum can be swapped in later.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config import (
    BATCH_SIZE,
    CLASS_ORDER,
    DROPOUT,
    FEATURES,
    LABEL_COL,
    LR,
    N_CLASSES,
    RANDOM_STATE,
    WEIGHT_DECAY,
)
from model import CV2XMLP, get_model_size_bytes, get_weights, set_weights


# ---------------------------------------------------------------------------
# Aggregation strategies (extensible)
# ---------------------------------------------------------------------------

def fedavg_aggregate(client_weights, client_sizes):
    """
    Weighted average of client model parameters, proportional to dataset size.
    """
    total = sum(client_sizes)
    n_layers = len(client_weights[0])
    aggregated = []
    for layer_idx in range(n_layers):
        weighted_sum = np.zeros_like(client_weights[0][layer_idx])
        for w, s in zip(client_weights, client_sizes):
            weighted_sum += w[layer_idx] * (s / total)
        aggregated.append(weighted_sum)
    return aggregated


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class FedAvgClient:
    def __init__(self, client_id, X, y, class_weights):
        self.client_id = client_id
        self.X = torch.from_numpy(X)
        self.y = torch.from_numpy(y)
        self.n_samples = len(y)
        self.class_weights = torch.from_numpy(class_weights)

    def train_round(self, global_weights, local_epochs, lr, batch_size, seed, dropout=DROPOUT):
        """
        Receive global weights, train locally, return updated weights.
        """
        torch.manual_seed(seed + self.client_id)

        model = CV2XMLP(dropout=dropout)
        set_weights(model, global_weights)
        model.train()

        criterion = nn.CrossEntropyLoss(weight=self.class_weights)
        optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)

        dataset = TensorDataset(self.X, self.y)
        loader = DataLoader(
            dataset, batch_size=batch_size, shuffle=True,
            generator=torch.Generator().manual_seed(seed + self.client_id),
        )

        for _ in range(local_epochs):
            for X_batch, y_batch in loader:
                optimizer.zero_grad()
                logits = model(X_batch)
                loss = criterion(logits, y_batch)
                loss.backward()
                optimizer.step()

        return get_weights(model), self.n_samples


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class FedAvgServer:
    def __init__(self, dropout=DROPOUT):
        torch.manual_seed(RANDOM_STATE)
        self.dropout = dropout
        self.global_model = CV2XMLP(dropout=dropout)
        self.model_bytes = get_model_size_bytes(self.global_model)

    def prepare_clients(self, client_dfs, scaler_mean, scaler_scale):
        """Create FedAvgClient objects from partitioned DataFrames."""
        label_to_idx = {c: i for i, c in enumerate(CLASS_ORDER)}
        clients = []

        for i, df in enumerate(client_dfs):
            X = df[FEATURES].values.astype(np.float32)
            X = (X - scaler_mean) / scaler_scale
            y = np.array([label_to_idx[l] for l in df[LABEL_COL].values], dtype=np.int64)

            # Per-client class weights
            counts = np.bincount(y, minlength=N_CLASSES).astype(np.float32)
            total = counts.sum()
            with np.errstate(divide="ignore", invalid="ignore"):
                weights = np.where(counts > 0, total / (N_CLASSES * counts), 0.0).astype(np.float32)

            clients.append(FedAvgClient(i, X, y, weights))

        return clients

    def run(
        self,
        clients,
        X_val, y_val,
        X_test, y_test,
        global_rounds,
        local_epochs,
        lr=LR,
        batch_size=BATCH_SIZE,
        eval_every=1,
        aggregate_fn=fedavg_aggregate,
    ):
        """
        Run the full FedAvg training loop.
        Returns round_metrics list and total communication bytes.
        """
        from evaluate import compute_metrics

        round_metrics = []
        total_comm_bytes = 0

        for r in range(1, global_rounds + 1):
            global_weights = get_weights(self.global_model)

            # All clients participate each round
            all_weights = []
            all_sizes = []
            for client in clients:
                w, n = client.train_round(
                    global_weights, local_epochs, lr, batch_size,
                    seed=RANDOM_STATE + r, dropout=self.dropout,
                )
                all_weights.append(w)
                all_sizes.append(n)

            # Communication cost: each client uploads + downloads model weights
            total_comm_bytes += len(clients) * 2 * self.model_bytes

            # Aggregate
            new_weights = aggregate_fn(all_weights, all_sizes)
            set_weights(self.global_model, new_weights)

            # Evaluate
            if r % eval_every == 0 or r == global_rounds:
                self.global_model.eval()
                with torch.no_grad():
                    val_logits = self.global_model(torch.from_numpy(X_val))
                    val_pred = val_logits.argmax(dim=1).numpy()
                    test_logits = self.global_model(torch.from_numpy(X_test))
                    test_pred = test_logits.argmax(dim=1).numpy()

                val_m = compute_metrics(y_val, val_pred)
                test_m = compute_metrics(y_test, test_pred)

                entry = {
                    "round": r,
                    "val_macro_f1": val_m["macro_f1"],
                    "val_mcc": val_m["mcc"],
                    "test_macro_f1": test_m["macro_f1"],
                    "test_mcc": test_m["mcc"],
                    "test_accuracy": test_m["accuracy"],
                }
                round_metrics.append(entry)

                if r % 10 == 0 or r == 1 or r == global_rounds:
                    print(f"  Round {r:3d}  "
                          f"val_f1={val_m['macro_f1']:.4f}  "
                          f"test_f1={test_m['macro_f1']:.4f}  "
                          f"test_mcc={test_m['mcc']:.4f}")

        # Final test metrics (full detail)
        self.global_model.eval()
        with torch.no_grad():
            test_logits = self.global_model(torch.from_numpy(X_test))
            test_pred = test_logits.argmax(dim=1).numpy()
        final_metrics = compute_metrics(y_test, test_pred)

        return round_metrics, final_metrics, total_comm_bytes, test_pred
