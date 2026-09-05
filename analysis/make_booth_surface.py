#!/usr/bin/env python3
"""
Compute the response surface the booth demo is a lookup over.

The booth page has no Python behind it, which invites the question "did you just
draw this?". The answer is that every number it shows came from here, and this
imports `pooled_consensus` directly, so the statistic on the screen is the
statistic in the paper rather than a re-implementation of it.

Sampling it on a grid rather than computing live is also what makes the
interaction instant. A visitor dragging a claimed position should see the verdict
move with their finger.

**What is computed.** For one representative pooled unit, the consistency ratio
at every claimed position on a grid around the truth, at several receiver counts.
The ratio is the claim's propagation residual over the best any single position
could achieve on the same measurements, which is exactly `pool_claim_rmse` over
`pool_free_rmse` in the pooled table.

**The single receiver case is not a small number, it is undefined.** The model
has four free parameters, two of position and two of propagation, and one
receiver at one geometry supplies one equation per window. There is no fit. The
demo must show that as "no evidence available at any displacement" rather than as
a poor score, because the difference between cannot and does-not-well is the
paper's first result.

    make_booth_surface.py corpus.pkl --run-dir DIR --tags seed1 ... --out surface.json
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

from pooled_consensus import observer_geometry, true_positions, free_fit
from power_evasion import pooled_rmse

ROAD_HALFWIDTH = 12.0
RECEIVER_COUNTS = [1, 5, 8, 20, 0]          # 0 means every receiver in the unit


def pick_unit(df, want=36):
    """A representative unit: plenty of receivers, mid road, benign.

    Representative rather than favourable. The receiver count is chosen near the
    corpus median for a pooled unit rather than at its maximum, so the demo shows
    what a deployment sees and not the best case in the dataset.
    """
    g = df.groupby(["key_seed", "key_claimedStationId", "key_window"])
    best, best_score = None, None
    for k, v in g:
        v = v[v.phy_rsrp_mean.notna()]
        if len(v) < 20 or int(v.label_attackId.iloc[0]) != 0:
            continue
        tx = float(v.trueX.iloc[0])
        # near the middle of the road, so the receiver geometry is not an
        # end-of-road special case
        score = abs(len(v) - want) + abs(tx - 3000.0) / 500.0
        if best_score is None or score < best_score:
            best, best_score = (k, v), score
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--along", type=float, default=250.0, help="grid half range along the road")
    ap.add_argument("--across", type=float, default=150.0, help="grid half range across it")
    ap.add_argument("--steps", type=int, default=81)
    a = ap.parse_args()

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    obs, _ = observer_geometry(a.run_dir, a.tags)
    truth = true_positions(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(truth, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])
    df = df[df.phy_rsrp_mean.notna()]

    # A calibrated decision threshold, so the demo's verdict is not a number
    # somebody chose to make the demo work. Taken over benign units at a stated
    # false positive rate, exactly as the plausibility baseline does.
    thresholds = {}
    print("calibrating the verdict threshold on benign units")
    ben_units = []
    for k, v in df.groupby(["key_seed", "key_claimedStationId", "key_window"]):
        v = v[v.phy_rsrp_mean.notna()]
        if len(v) >= 20 and int(v.label_attackId.iloc[0]) == 0:
            ben_units.append(v)
        if len(ben_units) >= 400:
            break
    for n in RECEIVER_COUNTS:
        if n and n < 5:
            continue
        ratios = []
        for v in ben_units:
            o_x, o_y = v.rxX.values, v.rxY.values
            r_ = v.phy_rsrp_mean.values
            t_x, t_y = float(v.trueX.iloc[0]), float(v.trueY.iloc[0])
            od = np.argsort(np.abs(o_x - t_x))
            o_x, o_y, r_ = o_x[od], o_y[od], r_[od]
            kk = len(o_x) if n == 0 else min(n, len(o_x))
            if kk < 5:
                continue
            try:
                s = free_fit(o_x[:kk], o_y[:kk], r_[:kk], ROAD_HALFWIDTH)
                fr = float(np.sqrt(np.mean(s.fun ** 2)))
                if fr <= 0:
                    continue
                # the honest claim IS the true position for a benign station
                ratios.append(pooled_rmse(o_x[:kk], o_y[:kk], r_[:kk], t_x, t_y) / fr)
            except Exception:
                continue
        if ratios:
            thr = float(np.quantile(ratios, 0.95))
            thresholds["all" if n == 0 else str(n)] = round(thr, 4)
            print(f"  {'all' if n == 0 else n:>3} receivers  "
                  f"{len(ratios):3d} benign units, 95th percentile ratio {thr:.3f}")
    print()

    picked = pick_unit(df)
    if picked is None:
        print("FAIL: no unit with enough receivers")
        return 1
    key, v = picked
    ox, oy = v.rxX.values, v.rxY.values
    rsrp = v.phy_rsrp_mean.values
    tx, ty = float(v.trueX.iloc[0]), float(v.trueY.iloc[0])
    print(f"unit {key}, {len(v)} receivers, true position ({tx:.0f}, {ty:.1f})")

    # Receiver order is fixed once so every arm is a nested subset of the same
    # set. Otherwise a smaller count could draw a luckier geometry and the
    # comparison would measure the draw.
    order = np.argsort(np.abs(ox - tx))
    ox, oy, rsrp = ox[order], oy[order], rsrp[order]

    dxs = np.linspace(-a.along, a.along, a.steps)
    dys = np.linspace(-a.across, a.across, a.steps)

    surfaces = {}
    for n in RECEIVER_COUNTS:
        k = len(ox) if n == 0 else min(n, len(ox))
        label = "all" if n == 0 else str(n)
        if k < 5:
            # Four free parameters need at least five independent equations.
            # Below that there is no fit, and that is the finding rather than a
            # gap in the demo.
            surfaces[label] = {"identifiable": False, "n": k, "grid": None}
            print(f"  {k:>3} receivers  NOT IDENTIFIABLE, four free parameters")
            continue
        sx, sy, sr = ox[:k], oy[:k], rsrp[:k]
        sol = free_fit(sx, sy, sr, ROAD_HALFWIDTH)
        free = float(np.sqrt(np.mean(sol.fun ** 2)))
        grid = []
        for dy in dys:
            row = []
            for dx in dxs:
                r = pooled_rmse(sx, sy, sr, tx + dx, ty + dy)
                row.append(round(r / free, 4) if free > 0 else None)
            grid.append(row)
        surfaces[label] = {"identifiable": True, "n": k,
                           "free_rmse": round(free, 4), "grid": grid}
        honest = surfaces[label]["grid"][a.steps // 2][a.steps // 2]
        print(f"  {k:>3} receivers  free rmse {free:6.3f} dB, "
              f"ratio at the truth {honest:.3f}")

    out = {
        "note": "Every value here was computed by analysis/make_booth_surface.py "
                "over the real corpus, using the same consistency statistic as "
                "the paper. The page is a lookup over this, not a mock up.",
        "unit": {"seed": str(key[0]), "station": int(key[1]),
                 "window": int(key[2]), "receivers": int(len(ox))},
        "true_position": {"x": round(tx, 2), "y": round(ty, 2)},
        "receivers": [{"x": round(float(x), 1), "y": round(float(y), 1)}
                      for x, y in zip(ox, oy)],
        "road_halfwidth": ROAD_HALFWIDTH,
        "grid": {"dx": [round(float(x), 1) for x in dxs],
                 "dy": [round(float(y), 1) for y in dys]},
        "thresholds": thresholds,
        "threshold_note":
            "The 95th percentile of the consistency ratio over benign units, so "
            "a verdict of caught means the claim looks worse than 95 percent of "
            "honest stations do. Calibrated on the data, not chosen.",
        "surfaces": surfaces,
    }
    pathlib.Path(a.out).write_text(json.dumps(out))
    kb = pathlib.Path(a.out).stat().st_size / 1024
    print(f"\n{a.steps}x{a.steps} grid, {len(surfaces)} arms -> {a.out} ({kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
