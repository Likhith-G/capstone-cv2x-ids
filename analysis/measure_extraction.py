#!/usr/bin/env python3
"""
How long feature extraction takes, the term measure_latency.py leaves out.

measure_latency.py times window fill and inference and says plainly that
feature extraction is not timed, so its total is a lower bound. This times the
missing term with the pipeline's own code: build_features.build_features, the
function every release row came from, run on one seed's receive tables.

Reading the CSV tables is file input, not extraction, and a deployed receiver
holds its messages in memory, so the tables are read once beforehand and the
timed call is handed the parsed copies. What is timed is everything after that:
the per-message residuals, the window aggregation, the radio statistics and the
long-window tracking features.

The pipeline is vectorised over a whole run, so the figure is an amortised cost
per record (one receiver's view of one station over one window) and per
receiver-window (everything one receiver computes for one window). A streaming
implementation on a vehicle would batch differently; the amortised figure is
the honest measurement available without writing one.

    measure_extraction.py RUN_DIR --tag seed1 [--repeats 3]
"""
import argparse
import time

import numpy as np

import build_features as bf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--tag", default="seed1")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--window-ms", type=float, default=1000.0)
    a = ap.parse_args()

    real_read = bf._read
    cache = {}

    def cached_read(path, time_col, max_time_ms, usecols=None):
        key = (path, time_col, max_time_ms, tuple(usecols) if usecols else None)
        if key not in cache:
            cache[key] = real_read(path, time_col, max_time_ms, usecols)
        return cache[key].copy()

    bf._read = cached_read
    t = time.perf_counter()
    agg = bf.build_features(a.run_dir, a.tag, window_ms=a.window_ms)
    first = time.perf_counter() - t
    print(f"{a.run_dir} {a.tag}: first call, reading included, {first:.1f} s")

    times = []
    for _ in range(a.repeats):
        t = time.perf_counter()
        agg = bf.build_features(a.run_dir, a.tag, window_ms=a.window_ms)
        times.append(time.perf_counter() - t)
    best = min(times)
    msgs = sum(len(v) for k, v in cache.items() if "rx_app" in k[0])
    rw = agg.groupby(["key_rxNodeId", "key_window"]).ngroups
    print(f"messages received {msgs:,}; records {len(agg):,}; "
          f"receiver-windows {rw:,}")
    print(f"extraction, tables already in memory: best of {a.repeats} "
          f"{best:.2f} s (all runs {', '.join(f'{x:.2f}' for x in times)})")
    print(f"  per record           {1e3 * best / len(agg):8.4f} ms")
    print(f"  per receiver-window  {1e3 * best / rw:8.3f} ms")
    print(f"  per message          {1e6 * best / msgs:8.2f} us")
    print(f"  against the {a.window_ms:.0f} ms window: "
          f"{100 * (best / rw) / (a.window_ms / 1e3):.3f} percent per receiver")
    print("EXTRACTION DONE")


if __name__ == "__main__":
    main()
