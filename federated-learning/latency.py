#!/usr/bin/env python3
"""
latency.py -- Inference latency profiling against the 100ms PC5 constraint.
"""

import time

import numpy as np
import torch

from config import N_FEATURES, RANDOM_STATE
from model import CV2XMLP


def profile_inference(model=None, n_warmup=200, n_timed=2000):
    """
    Profile single-sample CPU inference latency.
    Returns dict with timing statistics in microseconds.
    """
    if model is None:
        from config import OUT_DIR
        weights_path = OUT_DIR / "centralized" / "model.pt"
        model = CV2XMLP()
        if weights_path.exists():
            model.load_state_dict(torch.load(weights_path, weights_only=True))
        # Falls back to random weights if no checkpoint exists

    model.eval()
    torch.set_num_threads(1)  # Simulate single-core edge device

    rng = np.random.RandomState(RANDOM_STATE)
    sample = torch.from_numpy(
        rng.randn(1, N_FEATURES).astype(np.float32)
    )

    # Warmup
    with torch.no_grad():
        for _ in range(n_warmup):
            model(sample)

    # Timed runs
    latencies_us = []
    with torch.no_grad():
        for _ in range(n_timed):
            start = time.perf_counter()
            model(sample)
            elapsed = (time.perf_counter() - start) * 1e6  # microseconds
            latencies_us.append(elapsed)

    latencies = np.array(latencies_us)
    pc5_budget_us = 100_000  # 100ms in microseconds

    results = {
        "n_timed": n_timed,
        "threads": 1,
        "mean_us": round(float(latencies.mean()), 2),
        "median_us": round(float(np.median(latencies)), 2),
        "p95_us": round(float(np.percentile(latencies, 95)), 2),
        "p99_us": round(float(np.percentile(latencies, 99)), 2),
        "max_us": round(float(latencies.max()), 2),
        "pc5_budget_us": pc5_budget_us,
        "headroom_factor": round(pc5_budget_us / latencies.mean(), 1),
        "passes_100ms": bool(latencies.max() < pc5_budget_us),
    }
    return results
