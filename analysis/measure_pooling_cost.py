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
are two very different costs and only one of them is optional: the claimed-
position regression is closed form, and it carries most of the separation
(pool_claim_rmse reaches +5.03 benign standard deviations on class 1 against
+0.98 for pool_mlat_err). A deployment that cannot afford the nonlinear fit can
drop it and keep most of the signal.
"""
import argparse
import time
import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from pooled_consensus import observer_geometry, _resid, FIT_CAP

KEY = ["key_seed", "key_claimedStationId", "key_window"]


def closed_form(ox, oy, rsrp, cx, cy):
    d = np.maximum(np.hypot(ox - cx, oy - cy), 1.0)
    X = np.c_[np.ones(len(d)), -10.0 * np.log10(d)]
    beta, *_ = np.linalg.lstsq(X, rsrp, rcond=None)
    r = rsrp - X @ beta
    return float(np.sqrt(np.mean(r ** 2)))


def free_fit(ox, oy, rsrp):
    i0 = int(np.argmax(rsrp))
    p0 = np.array([ox[i0], oy[i0], float(np.max(rsrp)) + 20.0, 2.5])
    sol = least_squares(_resid, p0, args=(ox, oy, rsrp), method="lm", max_nfev=400)
    return float(sol.x[0]), float(sol.x[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--units", type=int, default=2000)
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    df = df[KEY + ["key_rxNodeId", "phy_rsrp_mean"]].dropna(subset=["phy_rsrp_mean"])
    obs, claim = observer_geometry(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(claim, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])

    units = []
    for _, g in df.groupby(KEY, sort=False):
        if len(g) < 5:
            continue
        units.append((g.rxX.values, g.rxY.values, g.phy_rsrp_mean.values,
                      float(g.claimedX.iloc[0]), float(g.claimedY.iloc[0])))
        if len(units) >= a.units:
            break
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
        free_fit(ox, oy, r)
    t_free = (time.perf_counter() - t0) / len(units) * 1000

    print(f"{'step':44s} {'ms per unit':>12s}")
    print(f"{'claimed-position regression, closed form':44s} {t_closed:12.4f}")
    print(f'{"free position fit, nonlinear least squares":44s} {t_free:12.4f}')
    print(f"{'both':44s} {t_closed + t_free:12.4f}")
    print(f"\nfor comparison, section 7 measures single-window inference at "
          f"2.145 ms.")
    print(f"the free fit alone is {t_free / 2.145:.1f} times the inference cost, "
          f"and {(t_closed + t_free) / 1000.0 * 100:.3f} percent of a 1000 ms "
          f"window.")
    print("\nThe closed-form regression carries most of the separation, so a "
          "deployment\nthat cannot afford the nonlinear fit can drop it and "
          "keep the cheaper half.")


if __name__ == "__main__":
    main()
