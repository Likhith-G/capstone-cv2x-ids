#!/usr/bin/env python3
"""
complexity.py -- Model complexity sweep: find the smallest MLP that achieves
F1=1.0 on the CV2X-IDS dataset, to justify the edge deployment model size.

Architectures tested:
  [32]              — minimal single-layer
  [64, 32]          — shallow two-layer
  [128, 64, 32]     — current production architecture
  [256, 128, 64, 32] — deeper reference

Usage:
  python3 federated-learning/complexity.py
"""

import json
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config import (
    CLASS_ORDER, DATA_DIR, FEATURES, FL_SPEC, LABEL_COL,
    N_CLASSES, N_FEATURES, OUT_DIR, RANDOM_STATE,
)
from evaluate import compute_metrics
from latency import profile_inference
from model import CV2XMLP, get_model_size_bytes, get_n_params

ARCHITECTURES = [
    [32],
    [64, 32],
    [128, 64, 32],
    [256, 128, 64, 32],
]


def _load_data():
    with open(FL_SPEC) as f:
        spec = json.load(f)
    mean = np.array(spec["preprocessing"]["mean"], dtype=np.float32)
    scale = np.array(spec["preprocessing"]["scale"], dtype=np.float32)

    splits = {}
    for name in ("train", "val", "test"):
        df = pd.read_csv(DATA_DIR / f"{name}.csv")
        X = (df[FEATURES].values.astype(np.float32) - mean) / scale
        label_to_idx = {c: i for i, c in enumerate(CLASS_ORDER)}
        y = np.array([label_to_idx[l] for l in df[LABEL_COL].values], dtype=np.int64)
        splits[name] = (X, y)
    return splits


def _train_one(hidden_layers, splits, lr=1e-3, weight_decay=1e-3,
               batch_size=64, max_epochs=100, patience=10):
    torch.manual_seed(RANDOM_STATE)
    np.random.seed(RANDOM_STATE)

    X_train, y_train = splits["train"]
    X_val, y_val = splits["val"]
    X_test, y_test = splits["test"]

    counts = np.bincount(y_train, minlength=N_CLASSES).astype(np.float32)
    total = counts.sum()
    class_weights = total / (N_CLASSES * counts)
    class_weights[counts == 0] = 0.0

    model = CV2XMLP(hidden_layers=hidden_layers)
    criterion = nn.CrossEntropyLoss(weight=torch.from_numpy(class_weights))
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max_epochs)

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                        generator=torch.Generator().manual_seed(RANDOM_STATE))

    best_val_f1 = -1.0
    best_weights = None
    patience_counter = 0
    best_epoch = 0

    for epoch in range(max_epochs):
        model.train()
        for X_batch, y_batch in loader:
            optimizer.zero_grad()
            loss = criterion(model(X_batch), y_batch)
            loss.backward()
            optimizer.step()
        scheduler.step()

        model.eval()
        with torch.no_grad():
            val_pred = model(torch.from_numpy(X_val)).argmax(dim=1).numpy()
        val_f1 = compute_metrics(y_val, val_pred)["macro_f1"]

        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            best_weights = [p.detach().cpu().clone() for p in model.parameters()]
            patience_counter = 0
            best_epoch = epoch + 1
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    with torch.no_grad():
        for p, w in zip(model.parameters(), best_weights):
            p.copy_(w)

    model.eval()
    with torch.no_grad():
        test_pred = model(torch.from_numpy(X_test)).argmax(dim=1).numpy()
    test_metrics = compute_metrics(y_test, test_pred)

    latency = profile_inference(model=model, n_warmup=100, n_timed=1000)

    return model, {
        "hidden_layers": hidden_layers,
        "architecture": f"15→{'→'.join(str(h) for h in hidden_layers)}→12",
        "n_params": get_n_params(model),
        "size_bytes": get_model_size_bytes(model),
        "size_kb": round(get_model_size_bytes(model) / 1024, 2),
        "best_epoch": best_epoch,
        "test_f1": test_metrics["macro_f1"],
        "test_mcc": test_metrics["mcc"],
        "test_accuracy": test_metrics["accuracy"],
        "latency_mean_us": latency["mean_us"],
        "latency_p99_us": latency["p99_us"],
    }


def run_sweep():
    print("=" * 60)
    print("MODEL COMPLEXITY SWEEP")
    print("=" * 60)

    splits = _load_data()
    results = []

    for arch in ARCHITECTURES:
        label = f"[{', '.join(str(h) for h in arch)}]"
        print(f"\n--- Architecture: {label} ---")
        _, row = _train_one(arch, splits)
        results.append(row)
        print(f"  Params: {row['n_params']:,}  Size: {row['size_kb']} KB  "
              f"F1: {row['test_f1']:.4f}  Latency: {row['latency_mean_us']:.1f} μs")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "complexity.json", "w") as f:
        json.dump(results, f, indent=2)

    df = pd.DataFrame(results)
    df.to_csv(OUT_DIR / "complexity.csv", index=False)

    print(f"\n{'Architecture':<30} {'Params':>8} {'Size':>8} {'F1':>8} {'Latency':>10}")
    print("-" * 70)
    for r in results:
        print(f"{r['architecture']:<30} {r['n_params']:>8,} {r['size_kb']:>7.1f}K "
              f"{r['test_f1']:>7.4f} {r['latency_mean_us']:>8.1f} μs")

    smallest_perfect = next((r for r in results if r["test_f1"] >= 0.9999), None)
    if smallest_perfect:
        print(f"\nSmallest model achieving F1=1.0: {smallest_perfect['architecture']}")
        print(f"  {smallest_perfect['n_params']:,} params, "
              f"{smallest_perfect['size_kb']} KB, "
              f"{smallest_perfect['latency_mean_us']:.1f} μs")

    print(f"\nSaved to {OUT_DIR}/complexity.json and complexity.csv")
    return results


if __name__ == "__main__":
    run_sweep()
