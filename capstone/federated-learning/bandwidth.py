#!/usr/bin/env python3
"""
bandwidth.py -- Communication cost estimation: FL vs centralized.
"""

import numpy as np

from config import FEATURES, N_FEATURES
from model import CV2XMLP, get_model_size_bytes, get_n_params


def estimate_comm_cost(n_clients, n_rounds, train_size):
    """
    Compare communication cost of centralized vs FL training.
    Returns a dict with byte counts and ratios.
    """
    model = CV2XMLP()
    n_params = get_n_params(model)
    model_bytes = get_model_size_bytes(model)

    # Centralized: ship all raw training data once
    # Each sample: N_FEATURES floats (4 bytes each) + 1 label (4 bytes)
    bytes_per_sample = (N_FEATURES + 1) * 4
    centralized_bytes = train_size * bytes_per_sample

    # FL: each round, each client downloads global model + uploads local model
    fl_bytes_per_round = n_clients * 2 * model_bytes
    fl_total_bytes = n_rounds * fl_bytes_per_round

    # Scaled projection: production scenario
    # 1000 vehicles, 10Hz BSMs, 30s windows -> ~333 windows/min per vehicle
    prod_vehicles = 1000
    prod_windows_per_min = 333
    prod_data_per_min = prod_vehicles * prod_windows_per_min * bytes_per_sample
    prod_fl_per_min = 0  # FL only sends model updates per round, not per window

    return {
        "model_params": n_params,
        "model_bytes": model_bytes,
        "centralized": {
            "total_bytes": centralized_bytes,
            "total_mb": round(centralized_bytes / (1024 * 1024), 4),
            "description": f"{train_size} samples x {bytes_per_sample} bytes/sample",
        },
        "federated": {
            "bytes_per_round": fl_bytes_per_round,
            "total_bytes": fl_total_bytes,
            "total_mb": round(fl_total_bytes / (1024 * 1024), 4),
            "description": f"{n_rounds} rounds x {n_clients} clients x 2 x {model_bytes} bytes",
        },
        "ratio_fl_over_centralized": round(fl_total_bytes / centralized_bytes, 4)
            if centralized_bytes > 0 else float("inf"),
        "production_projection": {
            "raw_data_mb_per_min": round(prod_data_per_min / (1024 * 1024), 2),
            "fl_update_kb_per_round": round(fl_bytes_per_round / 1024, 2),
            "note": "At production scale (1000 vehicles), FL sends ~50KB/round vs MB/min of raw data",
        },
    }
