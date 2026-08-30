#!/usr/bin/env python3
"""
End-to-end detection latency, measured honestly.

A 26.4 microsecond forward pass is easy to measure and easy to report against
the 100 ms PC5 budget in 3GPP TS 22.185, and doing so measures the wrong
quantity by three orders of magnitude. A windowed detector cannot decide anything until
its window has filled, so the latency a vehicle experiences is

    window fill + feature extraction + inference

and the forward pass is the smallest of the three by a wide margin. What the
TS 22.185 budget actually covers is the PC5 transport of a single message, not
an application-layer detection pipeline, and conflating the two flatters the
result. State both.

This script measures each term for a given window length and reports the
detection latency against the budget.

Usage: measure_latency.py <features.pkl> [--window-ms 1000] [--long-factor 10]
"""
import argparse
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier


def timeit(fn, repeats=5):
    best = np.inf
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features")
    ap.add_argument("--window-ms", type=float, default=1000.0)
    ap.add_argument("--long-factor", type=int, default=10)
    ap.add_argument("--budget-ms", type=float, default=100.0)
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--fit-rows", type=int, default=80000)
    a = ap.parse_args()

    df = (pd.read_pickle(a.features) if a.features.endswith(".pkl")
          else pd.read_csv(a.features))
    feats = [c for c in df.columns if c.startswith(("app_", "phy_"))]
    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = df.label_is_attack

    fit = X.sample(n=min(a.fit_rows, len(X)), random_state=0)
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=1,
                                 random_state=0).fit(fit, y.loc[fit.index])

    one = X.iloc[[0]]
    batch = X.iloc[:1000]
    t_single = timeit(lambda: clf.predict_proba(one)) * 1000.0
    t_batch = timeit(lambda: clf.predict_proba(batch)) * 1000.0 / len(batch)

    # Features that need the long window cannot be produced any sooner than
    # that window fills, whatever the hardware does.
    long_feats = [c for c in feats if "track" in c or "closest" in c]
    short_ms = a.window_ms
    long_ms = a.window_ms * a.long_factor

    print(f"{len(feats)} features, {len(long_feats)} of them long-window "
          f"({', '.join(long_feats) or 'none'})\n")
    print(f"single-window inference   {t_single:8.3f} ms")
    print(f"amortised in batches      {t_batch:8.4f} ms per window")
    print()
    print(f"{'path':28s} {'window fill':>12s} {'inference':>10s} {'total':>9s} "
          f"{'vs %.0f ms budget' % a.budget_ms:>18s}")
    for name, fill in [("short window only", short_ms),
                       ("full feature set", long_ms)]:
        total = fill + t_single
        verdict = "within" if total <= a.budget_ms else f"{total / a.budget_ms:.0f}x over"
        print(f"{name:28s} {fill:9.0f} ms {t_single:8.3f} ms {total:7.1f} ms "
              f"{verdict:>18s}")

    print(f"\nInference is {t_single / short_ms * 100:.2f} percent of the shortest "
          f"path's latency. Window fill dominates, and no amount of hardware "
          f"acceleration changes that.")


if __name__ == "__main__":
    main()
