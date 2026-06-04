#!/usr/bin/env python3
"""
centralized.py -- Centralized PyTorch training baseline.
Verifies PyTorch MLP matches sklearn classification results (F1=1.0)
before FL experiments begin.
"""

import json

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config import (
    CLASS_ORDER,
    DATA_DIR,
    FEATURES,
    FL_SPEC,
    LABEL_COL,
    N_CLASSES,
    OUT_DIR,
    RANDOM_STATE,
)
from evaluate import compute_metrics
from model import CV2XMLP


def load_scaler_params():
    """Load StandardScaler mean/scale from the classification FL spec."""
    with open(FL_SPEC) as f:
        spec = json.load(f)
    mean = np.array(spec["preprocessing"]["mean"], dtype=np.float32)
    scale = np.array(spec["preprocessing"]["scale"], dtype=np.float32)
    return mean, scale


def load_split(name, scaler_mean, scaler_scale):
    """Load a CSV split and return scaled features + integer labels."""
    df = pd.read_csv(DATA_DIR / f"{name}.csv")

    observed = sorted(df[LABEL_COL].unique())
    assert set(observed) <= set(CLASS_ORDER), (
        f"Unknown labels: {set(observed) - set(CLASS_ORDER)}"
    )

    X = df[FEATURES].values.astype(np.float32)
    X = (X - scaler_mean) / scaler_scale

    label_to_idx = {c: i for i, c in enumerate(CLASS_ORDER)}
    y = np.array([label_to_idx[l] for l in df[LABEL_COL].values], dtype=np.int64)

    return X, y


def compute_class_weights(y_train):
    """Compute balanced class weights inversely proportional to frequency."""
    counts = np.bincount(y_train, minlength=N_CLASSES).astype(np.float32)
    total = counts.sum()
    weights = total / (N_CLASSES * counts)
    weights[counts == 0] = 0.0
    return weights


def train_centralized(
    lr=1e-3,
    weight_decay=1e-3,
    batch_size=64,
    max_epochs=100,
    patience=10,
):
    """
    Train centralized PyTorch MLP on train.csv, early stop on val.csv,
    evaluate on test.csv. Returns metrics dict.
    """
    torch.manual_seed(RANDOM_STATE)
    np.random.seed(RANDOM_STATE)

    scaler_mean, scaler_scale = load_scaler_params()

    print("Loading data splits...")
    X_train, y_train = load_split("train", scaler_mean, scaler_scale)
    X_val, y_val = load_split("val", scaler_mean, scaler_scale)
    X_test, y_test = load_split("test", scaler_mean, scaler_scale)
    print(f"  Train: {X_train.shape}  Val: {X_val.shape}  Test: {X_test.shape}")

    # Class-weighted loss
    class_weights = compute_class_weights(y_train)
    print(f"  Class weights: min={class_weights.min():.2f} max={class_weights.max():.2f}")

    train_ds = TensorDataset(
        torch.from_numpy(X_train), torch.from_numpy(y_train)
    )
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True,
        generator=torch.Generator().manual_seed(RANDOM_STATE),
    )

    model = CV2XMLP()
    criterion = nn.CrossEntropyLoss(weight=torch.from_numpy(class_weights))
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)

    best_val_f1 = -1.0
    best_weights = None
    patience_counter = 0

    print(f"\nTraining centralized MLP (max {max_epochs} epochs, patience={patience})...")
    for epoch in range(max_epochs):
        model.train()
        epoch_loss = 0.0
        n_batches = 0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            logits = model(X_batch)
            loss = criterion(logits, y_batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1

        # Validation
        model.eval()
        with torch.no_grad():
            val_logits = model(torch.from_numpy(X_val))
            val_pred = val_logits.argmax(dim=1).numpy()
        val_metrics = compute_metrics(y_val, val_pred)

        avg_loss = epoch_loss / n_batches
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1:3d}  loss={avg_loss:.4f}  "
                  f"val_f1={val_metrics['macro_f1']:.4f}  val_mcc={val_metrics['mcc']:.4f}")

        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            best_weights = [p.detach().cpu().clone() for p in model.parameters()]
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"  Early stopping at epoch {epoch+1}")
                break

    # Restore best weights
    with torch.no_grad():
        for p, w in zip(model.parameters(), best_weights):
            p.copy_(w)

    # Final evaluation on test
    model.eval()
    with torch.no_grad():
        test_logits = model(torch.from_numpy(X_test))
        test_pred = test_logits.argmax(dim=1).numpy()
    test_metrics = compute_metrics(y_test, test_pred)

    print(f"\nCentralized test results:")
    print(f"  Macro F1: {test_metrics['macro_f1']:.4f}")
    print(f"  MCC:      {test_metrics['mcc']:.4f}")
    print(f"  Accuracy: {test_metrics['accuracy']:.4f}")

    # Save results
    out_dir = OUT_DIR / "centralized"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "model": "centralized_mlp",
        "best_epoch": epoch + 1 - patience_counter,
        "val_macro_f1": round(best_val_f1, 6),
        "test": test_metrics,
    }
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(results, f, indent=2)

    # Save model weights
    torch.save(model.state_dict(), out_dir / "model.pt")
    print(f"  Saved to {out_dir}/")

    return model, results


if __name__ == "__main__":
    train_centralized()
