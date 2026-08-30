#!/usr/bin/env python3
"""
evaluate.py -- Metrics computation and result aggregation for FL experiments.
"""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
)

from config import CLASS_ORDER, N_CLASSES


def compute_metrics(y_true, y_pred):
    """Compute macro F1, MCC, accuracy, per-class metrics, and confusion matrix."""
    labels = np.arange(N_CLASSES)

    macro_f1 = f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0)
    mcc = matthews_corrcoef(y_true, y_pred)
    accuracy = float(np.mean(y_true == y_pred))

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fpr = np.zeros(N_CLASSES)
    for i in range(N_CLASSES):
        fp = cm[:, i].sum() - cm[i, i]
        tn = cm.sum() - cm[i, :].sum() - cm[:, i].sum() + cm[i, i]
        fpr[i] = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    per_class = {}
    for i, cls_name in enumerate(CLASS_ORDER):
        per_class[cls_name] = {
            "precision": round(float(precision[i]), 6),
            "recall": round(float(recall[i]), 6),
            "f1": round(float(f1[i]), 6),
            "fpr": round(float(fpr[i]), 6),
            "support": int(support[i]),
        }

    return {
        "macro_f1": round(float(macro_f1), 6),
        "mcc": round(float(mcc), 6),
        "accuracy": round(float(accuracy), 6),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
    }


def plot_convergence(round_metrics, output_path, title="FedAvg Convergence"):
    """Plot macro F1 and MCC vs round."""
    from plot_style import apply_style, COLORS, FULL_WIDTH
    import matplotlib.pyplot as plt

    apply_style()

    rounds = [m["round"] for m in round_metrics]
    f1s = [m["test_macro_f1"] for m in round_metrics]
    mccs = [m["test_mcc"] for m in round_metrics]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FULL_WIDTH, 2.8))

    ax1.plot(rounds, f1s, color=COLORS["fedavg_c3"], marker="o", markersize=2)
    ax1.set_xlabel("Global Round")
    ax1.set_ylabel("Macro F1")
    ax1.set_title("Macro F1")
    ax1.set_ylim(-0.05, 1.05)

    ax2.plot(rounds, mccs, color=COLORS["fedavg_c5"], marker="o", markersize=2)
    ax2.set_xlabel("Global Round")
    ax2.set_ylabel("MCC")
    ax2.set_title("MCC")
    ax2.set_ylim(-0.05, 1.05)

    fig.suptitle(title, y=1.02)
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)


def plot_confusion(y_true, y_pred, output_path, title="Confusion Matrix"):
    """Plot a 12x12 confusion matrix."""
    from plot_style import apply_style, FULL_WIDTH
    import matplotlib.pyplot as plt

    apply_style()
    plt.rcParams["axes.spines.top"] = True
    plt.rcParams["axes.spines.right"] = True

    labels = np.arange(N_CLASSES)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    short_names = [c[:10] for c in CLASS_ORDER]

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 5.5))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    ax.set_xticks(range(N_CLASSES))
    ax.set_yticks(range(N_CLASSES))
    ax.set_xticklabels(short_names, rotation=45, ha="right")
    ax.set_yticklabels(short_names)

    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, format(cm[i, j], "d"), ha="center", va="center",
                    fontsize=6, color="white" if cm[i, j] > thresh else "black")

    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
