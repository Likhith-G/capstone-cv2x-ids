#!/usr/bin/env python3
"""
config.py -- Single source of truth for the FL workstream.
Feature contract, label contract, experiment grid, and paths.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "dataset-expansion" / "output"
FE_DIR = ROOT / "feature-engineering" / "output"
CLS_DIR = ROOT / "classification" / "output"
FL_SPEC = CLS_DIR / "model_spec_fl.json"
OUT_DIR = Path(__file__).resolve().parent / "output"
FIG_DIR = OUT_DIR / "figures"

# ---------------------------------------------------------------------------
# Feature and label contract (must match classification workstream exactly)
# ---------------------------------------------------------------------------
FEATURES = [
    "mean_iat", "mean_pkt_size", "total_bytes", "pkt_rate", "min_iat",
    "flood_ratio", "flood_mean_iat", "duration", "std_pkt_size",
    "unique_vehicle_ids", "bsm_mean_iat", "n_flood", "max_iat",
    "max_pos_deviation", "mean_speed_deviation",
]
N_FEATURES = len(FEATURES)

CLASS_ORDER = [
    "Benign", "FalseDataInjection", "HTTPFlood", "ICMPFlood",
    "PositionSpoof", "RandomPosition", "Replay", "SYNFlood",
    "SlowDoS", "Sybil", "UDPFlood", "VehicularDoS",
]
N_CLASSES = len(CLASS_ORDER)

LABEL_COL = "label_attack_type"
RANDOM_STATE = 42

# ---------------------------------------------------------------------------
# Model architecture (mirrors classification MLP -> PyTorch)
# ---------------------------------------------------------------------------
HIDDEN_LAYERS = [128, 64, 32]
ACTIVATION = "relu"

# ---------------------------------------------------------------------------
# Experiment grid
# ---------------------------------------------------------------------------
GLOBAL_ROUNDS = 50
BATCH_SIZE = 64
LR = 1e-3
WEIGHT_DECAY = 1e-3

EXPERIMENT_GRID = {
    "n_clients": [3, 5],
    "alpha": [100.0, 1.0, 0.5, 0.1],
    "local_epochs": [1, 3],
    "seeds": [42, 123, 456],
}

# Scenario-based partitioning runs separately (no alpha parameter)
SCENARIO_GRID = {
    "n_clients": [3, 5],
    "local_epochs": [1, 3],
    "seeds": [42, 123, 456],
}
