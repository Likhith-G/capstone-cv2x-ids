#!/usr/bin/env python3
"""
classify.py -- Capstone: Cybersecurity for Connected Cars
Multiclass classification pipeline for CV2X-IDS dataset.

Trains and evaluates three model families on the FE-selected feature subset:
  1. Random Forest (RF)
  2. Histogram Gradient Boosting (GBC)
  3. Multi-Layer Perceptron (MLP)

Usage:
  python3 classification/classify.py                    # full pipeline
  python3 classification/classify.py --step train       # train all models
  python3 classification/classify.py --step evaluate    # evaluate on test
  python3 classification/classify.py --step compare     # comparative analysis
  python3 classification/classify.py --step report      # generate RESULTS.md
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_fscore_support,
)
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.utils.class_weight import compute_class_weight, compute_sample_weight

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "dataset-expansion" / "output"
FE_DIR = ROOT / "feature-engineering" / "output"
OUT_DIR = Path(__file__).resolve().parent / "output"
FIG_DIR = OUT_DIR / "figures"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLASS_ORDER = [
    "Benign",
    "FalseDataInjection",
    "HTTPFlood",
    "ICMPFlood",
    "PositionSpoof",
    "RandomPosition",
    "Replay",
    "SYNFlood",
    "SlowDoS",
    "Sybil",
    "UDPFlood",
    "VehicularDoS",
]

RANDOM_STATE = 42


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_features():
    with open(FE_DIR / "selected_features_multiclass.json") as f:
        spec = json.load(f)
    return spec["features"]


def load_split(name, features):
    df = pd.read_csv(DATA_DIR / f"{name}.csv")
    X = df[features].values.astype(np.float64)
    y = df["label_attack_type"].values
    groups = (
        df["scenario_id"].astype(str) + "_" + df["node_id"].astype(str)
    ).values
    return X, y, groups


def encode_labels(y_train, y_val, y_test):
    le = LabelEncoder()
    le.classes_ = np.array(CLASS_ORDER)
    return (
        le.transform(y_train),
        le.transform(y_val),
        le.transform(y_test),
        le,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def compute_metrics(y_true, y_pred, le):
    n_classes = len(le.classes_)
    labels = np.arange(n_classes)

    macro_f1 = f1_score(y_true, y_pred, average="macro", labels=labels)
    mcc = matthews_corrcoef(y_true, y_pred)

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fpr = np.zeros(n_classes)
    for i in range(n_classes):
        fp = cm[:, i].sum() - cm[i, i]
        tn = cm.sum() - cm[i, :].sum() - cm[:, i].sum() + cm[i, i]
        fpr[i] = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    per_class = {}
    for i, cls_name in enumerate(le.classes_):
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
        "accuracy": round(float(np.mean(y_true == y_pred)), 6),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
    }


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------
def build_rf(n_classes, class_weights_dict):
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=25,
        min_samples_leaf=3,
        class_weight=class_weights_dict,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )


def build_gbc():
    return HistGradientBoostingClassifier(
        max_iter=300,
        max_depth=8,
        learning_rate=0.1,
        min_samples_leaf=5,
        l2_regularization=0.01,
        random_state=RANDOM_STATE,
    )


def build_mlp():
    return MLPClassifier(
        hidden_layer_sizes=(128, 64, 32),
        activation="relu",
        solver="adam",
        alpha=1e-3,
        learning_rate="adaptive",
        learning_rate_init=1e-3,
        max_iter=500,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=20,
        random_state=RANDOM_STATE,
    )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def train_models(X_train, y_train, X_val, y_val, le, scaler):
    n_classes = len(le.classes_)
    classes = np.arange(n_classes)

    cw_array = compute_class_weight("balanced", classes=classes, y=y_train)
    class_weights_dict = {i: w for i, w in enumerate(cw_array)}
    sample_weights = compute_sample_weight("balanced", y_train)

    models = {}
    val_metrics = {}

    # --- Random Forest ---
    print("Training Random Forest...")
    rf = build_rf(n_classes, class_weights_dict)
    rf.fit(X_train, y_train)
    models["rf"] = rf
    val_metrics["rf"] = compute_metrics(y_val, rf.predict(X_val), le)
    print(f"  Val Macro F1: {val_metrics['rf']['macro_f1']:.4f}  "
          f"MCC: {val_metrics['rf']['mcc']:.4f}")

    # --- Gradient Boosting ---
    print("Training Histogram Gradient Boosting...")
    gbc = build_gbc()
    gbc.fit(X_train, y_train, sample_weight=sample_weights)
    models["gbc"] = gbc
    val_metrics["gbc"] = compute_metrics(y_val, gbc.predict(X_val), le)
    print(f"  Val Macro F1: {val_metrics['gbc']['macro_f1']:.4f}  "
          f"MCC: {val_metrics['gbc']['mcc']:.4f}")

    # --- MLP ---
    print("Training MLP...")
    X_train_s = scaler.transform(X_train)
    X_val_s = scaler.transform(X_val)
    mlp = build_mlp()
    mlp.fit(X_train_s, y_train)
    models["mlp"] = mlp
    val_metrics["mlp"] = compute_metrics(y_val, mlp.predict(X_val_s), le)
    print(f"  Val Macro F1: {val_metrics['mlp']['macro_f1']:.4f}  "
          f"MCC: {val_metrics['mlp']['mcc']:.4f}")

    return models, val_metrics


# ---------------------------------------------------------------------------
# Evaluation on test set
# ---------------------------------------------------------------------------
def evaluate_models(models, X_test, y_test, le, scaler):
    test_metrics = {}
    for name, model in models.items():
        X = scaler.transform(X_test) if name == "mlp" else X_test
        y_pred = model.predict(X)
        test_metrics[name] = compute_metrics(y_test, y_pred, le)
        print(f"  {name.upper():>4}  Macro F1: {test_metrics[name]['macro_f1']:.4f}  "
              f"MCC: {test_metrics[name]['mcc']:.4f}  "
              f"Acc: {test_metrics[name]['accuracy']:.4f}")
    return test_metrics


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------
def extract_importances(models, features, X_test, y_test, le, scaler):
    importances = {}

    if "rf" in models:
        imp = models["rf"].feature_importances_
        importances["rf"] = sorted(
            zip(features, imp.tolist()), key=lambda x: x[1], reverse=True
        )

    if "mlp" in models:
        X_s = scaler.transform(X_test)
        baseline_f1 = f1_score(
            y_test, models["mlp"].predict(X_s), average="macro"
        )
        perm_imp = []
        rng = np.random.RandomState(RANDOM_STATE)
        for i, feat in enumerate(features):
            X_perm = X_s.copy()
            X_perm[:, i] = rng.permutation(X_perm[:, i])
            perm_f1 = f1_score(
                y_test, models["mlp"].predict(X_perm), average="macro"
            )
            perm_imp.append((feat, round(baseline_f1 - perm_f1, 6)))
        importances["mlp"] = sorted(perm_imp, key=lambda x: x[1], reverse=True)

    return importances


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def plot_confusion_matrices(models, X_test, y_test, le, scaler, features):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    short_names = [c[:8] for c in le.classes_]

    for name, model in models.items():
        X = scaler.transform(X_test) if name == "mlp" else X_test
        y_pred = model.predict(X)
        cm = confusion_matrix(y_test, y_pred, labels=np.arange(len(le.classes_)))

        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
        ax.set_xticks(np.arange(len(short_names)))
        ax.set_yticks(np.arange(len(short_names)))
        ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(short_names, fontsize=8)

        thresh = cm.max() / 2.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(
                    j, i, format(cm[i, j], "d"),
                    ha="center", va="center", fontsize=7,
                    color="white" if cm[i, j] > thresh else "black",
                )

        ax.set_xlabel("Predicted")
        ax.set_ylabel("True")
        ax.set_title(f"Confusion Matrix -- {name.upper()}")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"confusion_{name}.png", dpi=150)
        plt.close(fig)

    # Feature importance bar chart (RF)
    if "rf" in models:
        imp = models["rf"].feature_importances_
        idx = np.argsort(imp)
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh(np.arange(len(features)), imp[idx])
        ax.set_yticks(np.arange(len(features)))
        ax.set_yticklabels([features[i] for i in idx], fontsize=8)
        ax.set_xlabel("Gini Importance")
        ax.set_title("Random Forest Feature Importance")
        fig.tight_layout()
        fig.savefig(FIG_DIR / f"feature_importance_rf.png", dpi=150)
        plt.close(fig)

    print(f"  Figures saved to {FIG_DIR}/")


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------
def save_comparison(val_metrics, test_metrics, importances, features):
    rows = []
    for name in ["rf", "gbc", "mlp"]:
        row = {
            "model": name.upper(),
            "val_macro_f1": val_metrics[name]["macro_f1"],
            "val_mcc": val_metrics[name]["mcc"],
            "test_macro_f1": test_metrics[name]["macro_f1"],
            "test_mcc": test_metrics[name]["mcc"],
            "test_accuracy": test_metrics[name]["accuracy"],
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "comparison.csv", index=False)

    for name in ["rf", "gbc", "mlp"]:
        with open(OUT_DIR / f"metrics_{name}.json", "w") as f:
            json.dump(
                {
                    "model": name,
                    "val": val_metrics[name],
                    "test": test_metrics[name],
                    "feature_importance": importances.get(name, []),
                },
                f,
                indent=2,
            )

    print(f"  Metrics saved to {OUT_DIR}/")


# ---------------------------------------------------------------------------
# FL model spec
# ---------------------------------------------------------------------------
def save_fl_spec(features, scaler, test_metrics):
    best_name = max(test_metrics, key=lambda k: test_metrics[k]["macro_f1"])
    spec = {
        "model_type": "MLP",
        "description": "Feed-forward neural network for FL client-side training",
        "features": features,
        "n_features": len(features),
        "preprocessing": {
            "type": "StandardScaler",
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
        },
        "architecture": {
            "input_dim": len(features),
            "hidden_layers": [128, 64, 32],
            "activation": "relu",
            "output_dim": 12,
            "output_activation": "softmax",
        },
        "training": {
            "loss": "cross_entropy_weighted",
            "optimizer": "adam",
            "learning_rate": 1e-3,
            "weight_decay": 1e-3,
            "batch_size": 64,
            "max_epochs": 100,
            "early_stopping_patience": 10,
            "class_weight": "balanced",
        },
        "label_order": CLASS_ORDER,
        "centralized_baseline": {
            "best_model": best_name.upper(),
            "test_macro_f1": test_metrics[best_name]["macro_f1"],
            "test_mcc": test_metrics[best_name]["mcc"],
        },
    }
    with open(OUT_DIR / "model_spec_fl.json", "w") as f:
        json.dump(spec, f, indent=2)
    print(f"  FL model spec saved to {OUT_DIR / 'model_spec_fl.json'}")


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(features, val_metrics, test_metrics, importances):
    lines = []
    lines.append("# Classification Results\n")
    lines.append("## Feature Subset\n")
    lines.append(f"**{len(features)} features** from feature engineering (multiclass selection, k=15):\n")
    lines.append("```")
    lines.append(", ".join(features))
    lines.append("```\n")

    lines.append("## Model Comparison\n")
    lines.append("| Model | Val Macro F1 | Val MCC | Test Macro F1 | Test MCC | Test Accuracy |")
    lines.append("|---|---|---|---|---|---|")
    for name in ["rf", "gbc", "mlp"]:
        vm = val_metrics[name]
        tm = test_metrics[name]
        lines.append(
            f"| {name.upper()} | {vm['macro_f1']:.4f} | {vm['mcc']:.4f} "
            f"| {tm['macro_f1']:.4f} | {tm['mcc']:.4f} | {tm['accuracy']:.4f} |"
        )

    lines.append("\n## Per-Class Test Metrics (Best Model)\n")
    best_name = max(test_metrics, key=lambda k: test_metrics[k]["macro_f1"])
    tm = test_metrics[best_name]
    lines.append(f"**Model: {best_name.upper()}**\n")
    lines.append("| Class | Precision | Recall | F1 | FPR | Support |")
    lines.append("|---|---|---|---|---|---|")
    for cls_name in CLASS_ORDER:
        pc = tm["per_class"][cls_name]
        lines.append(
            f"| {cls_name} | {pc['precision']:.4f} | {pc['recall']:.4f} "
            f"| {pc['f1']:.4f} | {pc['fpr']:.6f} | {pc['support']} |"
        )

    if "rf" in importances:
        lines.append("\n## Feature Importance (Random Forest Gini)\n")
        lines.append("| Rank | Feature | Importance |")
        lines.append("|---|---|---|")
        for rank, (feat, imp) in enumerate(importances["rf"], 1):
            lines.append(f"| {rank} | {feat} | {imp:.4f} |")

    if "mlp" in importances:
        lines.append("\n## Permutation Importance (MLP)\n")
        lines.append("| Rank | Feature | F1 Drop |")
        lines.append("|---|---|---|")
        for rank, (feat, drop) in enumerate(importances["mlp"], 1):
            lines.append(f"| {rank} | {feat} | {drop:.4f} |")

    lines.append("\n## FL Handoff\n")
    lines.append("The FL workstream should use the MLP architecture defined in "
                 "`output/model_spec_fl.json`:")
    lines.append("- Input: 15 features (StandardScaler parameters included)")
    lines.append("- Architecture: [128, 64, 32] hidden layers, ReLU, softmax output")
    lines.append("- Loss: class-weighted cross-entropy")
    lines.append("- Optimizer: Adam (lr=1e-3, weight_decay=1e-3)")
    lines.append("")

    report_path = OUT_DIR / "RESULTS.md"
    report_path.write_text("\n".join(lines))
    print(f"  Report saved to {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="CV2X-IDS Multiclass Classification")
    parser.add_argument(
        "--step",
        choices=["train", "evaluate", "compare", "report", "all"],
        default="all",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    features = load_features()
    print(f"Loaded {len(features)} features from FE output")
    print(f"Features: {', '.join(features)}\n")

    print("Loading data splits...")
    X_train, y_train_str, g_train = load_split("train", features)
    X_val, y_val_str, g_val = load_split("val", features)
    X_test, y_test_str, g_test = load_split("test", features)
    print(f"  Train: {X_train.shape}  Val: {X_val.shape}  Test: {X_test.shape}")

    y_train, y_val, y_test, le = encode_labels(y_train_str, y_val_str, y_test_str)
    print(f"  Classes: {list(le.classes_)}\n")

    scaler = StandardScaler()
    scaler.fit(X_train)

    run_all = args.step == "all"

    if run_all or args.step == "train":
        print("=" * 60)
        print("TRAINING")
        print("=" * 60)
        models, val_metrics = train_models(
            X_train, y_train, X_val, y_val, le, scaler
        )
    else:
        print("Skipping training (use --step train or --step all)")
        return

    if run_all or args.step == "evaluate":
        print("\n" + "=" * 60)
        print("TEST SET EVALUATION")
        print("=" * 60)
        test_metrics = evaluate_models(models, X_test, y_test, le, scaler)

    if run_all or args.step == "compare":
        print("\n" + "=" * 60)
        print("FEATURE IMPORTANCE")
        print("=" * 60)
        importances = extract_importances(
            models, features, X_test, y_test, le, scaler
        )
        for name in importances:
            print(f"\n  {name.upper()} top 5:")
            for feat, imp in importances[name][:5]:
                print(f"    {feat:>25s}  {imp:.4f}")

        print("\n" + "=" * 60)
        print("SAVING RESULTS")
        print("=" * 60)
        save_comparison(val_metrics, test_metrics, importances, features)
        save_fl_spec(features, scaler, test_metrics)

        print("\n" + "=" * 60)
        print("GENERATING FIGURES")
        print("=" * 60)
        plot_confusion_matrices(models, X_test, y_test, le, scaler, features)

    if run_all or args.step == "report":
        print("\n" + "=" * 60)
        print("GENERATING REPORT")
        print("=" * 60)
        generate_report(features, val_metrics, test_metrics, importances)

    print("\nDone.")


if __name__ == "__main__":
    main()
