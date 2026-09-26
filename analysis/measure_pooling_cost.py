#!/usr/bin/env python3
"""
What the pooled detector costs to run.

Forming the consensus block means fitting a position and a propagation law per
station per window, a four-parameter nonlinear least squares over every
cooperating receiver. That is the one part of the pipeline with a cost that
looks like it should matter, and the honest thing is to measure it rather than
assume either way.

It is cheap. The whole block costs less than the inference it feeds. This
script was written expecting the opposite and the measurement says otherwise,
which is the reason to run it.

Measured here on the real receiver geometry rather than synthetic points,
because the cost depends on how many receivers there are and how well
conditioned they leave the fit.

The claimed-position statistics are separated from the free fit because they
are two very different costs: the claimed-position regression is closed form,
the free fit is a nonlinear least squares. The free fit timed here is the one
the pipeline runs, pooled_consensus.free_fit bounded to the carriageway, which
is several times slower than the unbounded fit this script used to time.
Whether a deployment could drop it is a question about separation, answered in
RESULTS.md, not here.

Units are drawn at random across every seed; a prefix of the grouped table
would time one seed's early traffic.
"""
import argparse
import re
import shlex
import sys
import time
import numpy as np
import pandas as pd

from pooled_consensus import observer_geometry, free_fit, FIT_CAP, ROAD_HALFWIDTH
from pooled_consensus import require_every_seed

KEY = ["key_seed", "key_claimedStationId", "key_window"]


def closed_form(ox, oy, rsrp, cx, cy):
    d = np.maximum(np.hypot(ox - cx, oy - cy), 1.0)
    X = np.c_[np.ones(len(d)), -10.0 * np.log10(d)]
    beta, *_ = np.linalg.lstsq(X, rsrp, rcond=None)
    r = rsrp - X @ beta
    return float(np.sqrt(np.mean(r ** 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--units", type=int, default=2000)
    ap.add_argument("--latency-log", required=True,
                    help="measure_latency.py's log on the same corpus; the "
                         "single-window inference cost is read from it")
    a = ap.parse_args()
    print("invocation: " + " ".join(shlex.quote(s) for s in sys.argv) + "\n")
    m = re.search(r"single-window inference\s+([\d.]+) ms",
                  open(a.latency_log).read())
    if not m:
        sys.exit(f"no single-window inference line in {a.latency_log}")
    inference_ms = float(m.group(1))
    rng = np.random.default_rng(0)

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    df = df[KEY + ["key_rxNodeId", "phy_rsrp_mean"]].dropna(subset=["phy_rsrp_mean"])
    obs, claim = observer_geometry(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    require_every_seed(df, a.tags, "measure_pooling_cost")
    df = df.merge(claim, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])

    grouped = df.groupby(KEY, sort=False)
    size = grouped.size()
    eligible = size[size >= 5].index
    pick = rng.choice(len(eligible), min(a.units, len(eligible)), replace=False)
    units = []
    for i in sorted(pick):
        g = grouped.get_group(eligible[i])
        units.append((g.rxX.values, g.rxY.values, g.phy_rsrp_mean.values,
                      float(g.claimedX.iloc[0]), float(g.claimedY.iloc[0])))
    n = np.array([len(u[2]) for u in units])
    print(f"{len(units)} units, receivers per unit: median {np.median(n):.0f}, "
          f"min {n.min()}, max {n.max()}\n")

    t0 = time.perf_counter()
    for ox, oy, r, cx, cy in units:
        closed_form(ox, oy, r, cx, cy)
    t_closed = (time.perf_counter() - t0) / len(units) * 1000

    t0 = time.perf_counter()
    for ox, oy, r, _, _ in units:
        if len(r) > FIT_CAP:
            sel = rng.choice(len(r), FIT_CAP, replace=False)
            ox, oy, r = ox[sel], oy[sel], r[sel]
        free_fit(ox, oy, r, ROAD_HALFWIDTH)
    t_free = (time.perf_counter() - t0) / len(units) * 1000

    print(f"{'step':44s} {'ms per unit':>12s}")
    print(f"{'claimed-position regression, closed form':44s} {t_closed:12.4f}")
    print(f'{"free position fit, bounded to the road":44s} {t_free:12.4f}')
    print(f"{'both':44s} {t_closed + t_free:12.4f}")
    print(f"\nsingle-window inference on this corpus, from {a.latency_log}: "
          f"{inference_ms} ms")
    print(f"the free fit alone is {t_free / inference_ms:.2f} times the "
          f"inference cost, and the whole block is "
          f"{(t_closed + t_free) / 1000.0 * 100:.3f} percent of a 1000 ms window.")


if __name__ == "__main__":
    main()
