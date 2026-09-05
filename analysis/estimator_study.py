#!/usr/bin/env python3
"""
Why the position fit sits a factor of two above the bound, and what closes it.

RESULTS.md 3h2 shows the gap between the Cramer-Rao bound and the fitted
position is larger than any receiver placement is worth, so the estimator and
not the array is the binding constraint. The obvious fix was a weighted least
squares fit. Weighting only helps if the residuals are heteroscedastic, so the
first thing here is a diagnostic rather than an estimator, and it found three
faults where one was expected:

  MISSPECIFICATION  a single slope log-distance law leaves a systematic
                    residual that changes sign with range, from -2.1 dB under
                    100 m to +1.7 dB at 200 to 400 m and -2.5 dB past a
                    kilometre. No amount of weighting fixes a wrong mean.
  HETEROSCEDASTICITY  residual spread runs 2.7 dB in the middle of the range
                    and 4.8 dB close in and 8.1 dB far out.
  HEAVY TAILS       kurtosis 18, and 0.79 percent of residuals beyond three
                    sigma against the 0.27 percent a Gaussian gives.

So four estimators are compared, each fitting the same four parameters to the
same triples, and the comparison is the median distance from the fit to the
truth on benign stations, which is what RESULTS.md 4b reports:

  ols       what the project uses now
  wls       inverse variance weights from a calibration curve of residual
            spread against range, which a deployment fits once offline on
            traffic it has no reason to doubt
  huber     a robust loss, which bounds the influence of a multipath excursion
  both      weighted and robust together

The nuisance parameters stay free in every arm, because that is what makes the
statistic invariant to transmit power and giving it up would be a different
detector.
"""
import argparse
import sys

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from pooled_consensus import observer_geometry, true_positions, ROAD_HALFWIDTH

# Calibration bins for the variance curve. Wide enough that each holds tens of
# thousands of benign observations, narrow enough to follow the shape found in
# the diagnostic above.
EDGES = np.array([0, 60, 100, 200, 400, 700, 1000, 1500, 1e9])


def calibrate(d, resid):
    """Residual spread AND mean against range, from benign traffic.

    The mean matters more than the spread. A single slope log-distance law
    leaves a systematic residual that changes sign with range, and that is a
    wrong mean rather than a noisy one, so no reweighting touches it. A
    deployment can measure this curve once offline on traffic it has no reason
    to doubt, exactly as it measures the law itself, and subtracting it costs no
    free parameters.
    """
    sd = np.zeros(len(EDGES) - 1)
    mu = np.zeros(len(EDGES) - 1)
    for i in range(len(sd)):
        m = (d >= EDGES[i]) & (d < EDGES[i + 1])
        sd[i] = np.std(resid[m]) if m.sum() > 200 else np.nan
        mu[i] = np.mean(resid[m]) if m.sum() > 200 else np.nan
    med = np.nanmedian(sd)
    sd = np.maximum(np.where(np.isnan(sd), med, sd), 0.5 * med)
    mu = np.where(np.isnan(mu), 0.0, mu)
    return sd, mu


def _pick(d, curve):
    return curve[np.clip(np.digitize(d, EDGES) - 1, 0, len(curve) - 1)]


def fit(ox, oy, rsrp, sd, mu, weighted, robust, debias, road_halfwidth=None):
    """Position and propagation law together. p = (x, y, A, n)."""
    def resid(p):
        dd = np.maximum(np.hypot(ox - p[0], oy - p[1]), 1.0)
        pred = p[2] - 10.0 * p[3] * np.log10(dd)
        if debias:
            pred = pred + _pick(dd, mu)
        r = rsrp - pred
        return r / _pick(dd, sd) if weighted else r

    # Identical initialisation and solver settings to pooled_consensus.free_fit,
    # which starts at the strongest receiver rather than at the centroid. On a
    # six kilometre road the centroid can be kilometres from the transmitter and
    # a nonlinear fit started there is handicapped, so the baseline arm here has
    # to use the project's start or the comparison measures the start instead of
    # the estimator.
    i0 = int(np.argmax(rsrp))
    p0 = np.array([ox[i0], oy[i0], float(np.max(rsrp)) + 20.0, 2.5])
    lo = np.array([-np.inf, -road_halfwidth if road_halfwidth else -np.inf,
                   -np.inf, 0.5])
    hi = np.array([np.inf, road_halfwidth if road_halfwidth else np.inf,
                   np.inf, 6.0])
    p0 = np.clip(p0, lo + 1e-6, hi - 1e-6)
    try:
        s = least_squares(resid, p0, bounds=(lo, hi), method="trf",
                          loss="huber" if robust else "linear",
                          f_scale=1.5, max_nfev=400)
        return float(s.x[0]), float(s.x[1])
    except Exception:
        return np.nan, np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--triples", type=int, default=4000)
    ap.add_argument("--min-obs", type=int, default=5)
    ap.add_argument("--road-halfwidth", type=float, default=None)
    ap.add_argument("--calibrate-tags", nargs="+", default=None,
                    help="fit the calibration curve on THESE seeds and evaluate "
                         "triples from the rest. A range dependent mean offset "
                         "is a physical effect and should generalise, but eight "
                         "bins of free correction fitted and evaluated on one "
                         "corpus is the shape of an in-sample result, so the "
                         "held out number is the one to quote")
    a = ap.parse_args()

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    obs, claim = observer_geometry(a.run_dir, a.tags)
    truth = true_positions(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(claim, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])
    df = df.merge(truth, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])
    df = df[df.phy_rsrp_mean.notna() & (df.label_attackId == 0)]

    # The calibration is fitted against the CLAIMED distance, which is what a
    # deployment has. For a benign station the claim is its true position plus
    # receiver error, so this is the same argument fit_global_law already makes
    # for the propagation law itself. Using the true position here would be an
    # oracle and would make the whole comparison worthless.
    d = np.hypot(df.rxX - df.claimedX, df.rxY - df.claimedY).values
    keep = d > 1.0
    df, d = df[keep], d[keep]

    if a.calibrate_tags:
        cal = df.key_seed.isin(a.calibrate_tags).values
        if not cal.any() or cal.all():
            raise SystemExit("--calibrate-tags must name some but not all seeds")
        print(f"calibration fitted on {sorted(set(a.calibrate_tags))}, "
              f"{cal.sum():,} observations")
        print(f"triples evaluated on the remaining seeds, "
              f"{(~cal).sum():,} observations. NOTHING is fitted and evaluated "
              f"on the same seed.")
    else:
        cal = np.ones(len(d), dtype=bool)
        print("WARNING: calibration fitted and evaluated on the same corpus. "
              "Pass --calibrate-tags\nfor the held out number, which is the one "
              "to quote.")

    L = 10.0 * np.log10(d[cal])
    X = np.c_[np.ones(len(L)), -L]
    beta, *_ = np.linalg.lstsq(X, df.phy_rsrp_mean.values[cal], rcond=None)
    resid = df.phy_rsrp_mean.values[cal] - X @ beta
    sd, mu = calibrate(d[cal], resid)
    dcal_dist = d[cal]
    if a.calibrate_tags:
        df, d = df[~cal], d[~cal]
    print(f"{len(df):,} benign observations, A={beta[0]:.2f}, n={beta[1]:.3f}, "
          f"overall sigma={resid.std():.3f} dB")
    print("\ncalibrated against range on benign traffic. The mean is the "
          "misspecification\nof the single slope law and the spread is the "
          "noise around it:")
    print(f"  {'range':<22s} {'mean':>8s} {'spread':>9s}")
    for i in range(len(sd)):
        hi = "and beyond" if EDGES[i + 1] > 1e8 else f"to {EDGES[i+1]:.0f} m"
        print(f"  {str(int(EDGES[i])) + ' m ' + hi:<22s} {mu[i]:+7.2f} dB "
              f"{sd[i]:7.2f} dB")

    g = df.groupby(["key_seed", "key_claimedStationId", "key_window"])
    keys = [k for k, v in g.size().items() if v >= a.min_obs]
    rng = np.random.default_rng(0)
    if len(keys) > a.triples:
        keys = [keys[i] for i in rng.choice(len(keys), a.triples, replace=False)]
    print(f"\n{len(keys):,} benign triples with {a.min_obs} or more receivers"
          + (f", position fit bounded to +/-{a.road_halfwidth:.0f} m"
             if a.road_halfwidth else ", position fit unconstrained"))

    arms = {"ols, what the project uses":      (False, False, False),
            "wls, inverse variance":            (True, False, False),
            "huber, robust loss":               (False, True, False),
            "wls and huber":                    (True, True, False),
            "debiased, calibrated mean":        (False, False, True),
            "debiased and weighted":            (True, False, True),
            "debiased, weighted and robust":    (True, True, True)}
    err = {k: [] for k in arms}
    for k in keys:
        v = g.get_group(k)
        ox, oy = v.rxX.values, v.rxY.values
        rs = v.phy_rsrp_mean.values
        tx, ty = float(v.trueX.iloc[0]), float(v.trueY.iloc[0])
        for name, (w, r, b_) in arms.items():
            x, y = fit(ox, oy, rs, sd, mu, w, r, b_, a.road_halfwidth)
            err[name].append(np.hypot(x - tx, y - ty))

    print(f"\n{'estimator':32s} {'median error':>13s} {'against ols':>12s} "
          f"{'75th pct':>10s}")
    base = np.nanmedian(err["ols, what the project uses"])
    for name in arms:
        e = np.array(err[name], dtype=float)
        e = e[np.isfinite(e)]
        m = np.median(e)
        print(f"{name:32s} {m:11.1f} m {m / base:11.2f}x "
              f"{np.percentile(e, 75):8.1f} m")
    # What the debiasing leaves behind is the noise the bound should be computed
    # against. Quoting the original bound beside a debiased estimator compares
    # an estimator that has removed a deterministic term against a bound that
    # assumed that term was noise.
    d_cal = d if not a.calibrate_tags else None
    post = resid - _pick(dcal_dist, mu)
    print(f"\nresidual on the calibration data, before removing the calibrated "
          f"mean {resid.std():6.3f} dB")
    print(f"                                after "
          f"{'':30s}{post.std():6.3f} dB")
    print("""
The Cramer-Rao bound reported elsewhere was computed under the single slope law,
with this deterministic term absorbed into sigma as though it were noise. That
model is misspecified, so the gap it showed between the bound and the fit was
measuring model error and estimator inefficiency together. The corrected bound
is NOT this one rescaled by sigma: the range dependent offset is itself a
function of position and so contributes sensitivity as well as removing noise.
It has not been computed. Do not quote a rescaled figure as though it had.""")

    print("""
Read the ratio column. The Cramer-Rao bound for this geometry is 28.0 m as a
median radial error and the current fit reaches 65.2 m, so the room available
is a factor of about 2.3. Anything here that does not move the ratio is not
where the gap lives.
""")


if __name__ == "__main__":
    main()
