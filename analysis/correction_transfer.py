#!/usr/bin/env python3
"""
Does the calibrated propagation correction generalise, or is it shrinkage?

RESULTS.md 3h4 found a corrected estimator sitting BELOW its own Cramer-Rao
bound, 20.1 m against 25.9 m, which an unbiased estimator cannot do. The bound
constrains unbiased estimators only, so an estimator tuned to the population it
is scored on can beat it and routinely does. The correction in 3h3 is calibrated
on benign traffic against the position that traffic claims, which for a benign
station is where it actually is, and is then scored on benign stations. Held out
across seeds is not held out across populations.

Two tests, and they fail in different ways so both are worth running.

**Transfer.** Calibrate the eight bin means on one corpus and apply them to
another whose link distance distribution is different, sparse against dense. A
genuine propagation correction is a function of range and transfers. Shrinkage
onto one range distribution does not.

**Confounding.** Regress each bin's residual mean on the transmitter's
along-road position. The correction claims to be a function of range alone. If a
bin's mean varies with where on the road the transmitter is, the correction is
absorbing position structure, and an objective built from it points at the answer
for a reason that has nothing to do with propagation.
"""
import argparse
import sys

import numpy as np
import pandas as pd

from pooled_consensus import observer_geometry, true_positions
from estimator_study import EDGES, calibrate, _pick
from geometry_bound import fit_law


def load(corpus, run_dir, tags):
    df = pd.read_pickle(corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    obs, _ = observer_geometry(run_dir, tags)
    truth = true_positions(run_dir, tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(truth, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])
    df = df[df.phy_rsrp_mean.notna()]
    df = df[df.label_attackId == 0].copy()
    df["d"] = np.hypot(df.rxX - df.trueX, df.rxY - df.trueY)
    return df[df.d > 1.0]


def curve_of(df):
    A, n, resid = fit_law(df.d.values, df.phy_rsrp_mean.values)
    sd, mu = calibrate(df.d.values, resid)
    return A, n, sd, mu, resid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-corpus", required=True)
    ap.add_argument("--a-run-dir", required=True)
    ap.add_argument("--a-tags", nargs="+", required=True)
    ap.add_argument("--b-corpus", required=True)
    ap.add_argument("--b-run-dir", required=True)
    ap.add_argument("--b-tags", nargs="+", required=True)
    a = ap.parse_args()

    A = load(a.a_corpus, a.a_run_dir, a.a_tags)
    B = load(a.b_corpus, a.b_run_dir, a.b_tags)
    print(f"corpus A {len(A):,} benign observations, median link {np.median(A.d):.0f} m")
    print(f"corpus B {len(B):,} benign observations, median link {np.median(B.d):.0f} m\n")

    _, _, sdA, muA, residA = curve_of(A)
    _, _, sdB, muB, residB = curve_of(B)

    print("the calibrated mean correction, per range bin, dB")
    print(f"  {'bin':>16s} {'A':>9s} {'B':>9s} {'diff':>9s}")
    for i in range(len(muA)):
        lo, hi = EDGES[i], EDGES[i + 1]
        hs = "inf" if hi > 1e8 else f"{hi:.0f}"
        print(f"  {f'{lo:.0f} to {hs}':>16s} {muA[i]:9.3f} {muB[i]:9.3f} "
              f"{muA[i] - muB[i]:9.3f}")

    # TEST 1. How much of B's residual does A's curve remove, against how much
    # B's own curve removes? A genuine range correction transfers.
    base = float(np.std(residB))
    own = float(np.std(residB - _pick(B.d.values, muB)))
    xfer = float(np.std(residB - _pick(B.d.values, muA)))
    print(f"\nTEST 1, transfer. Residual spread on corpus B, dB")
    print(f"  uncorrected                         {base:7.3f}")
    print(f"  corrected with B's own curve        {own:7.3f}   "
          f"{100*(1-own/base):5.1f} percent removed")
    print(f"  corrected with A's curve            {xfer:7.3f}   "
          f"{100*(1-xfer/base):5.1f} percent removed")
    keep = (base - xfer) / (base - own) if base > own else float("nan")
    print(f"\n  fraction of the achievable gain that transfers  {keep:6.2f}")
    print("""
  Near one means the correction is a property of range and carries across a
  different link distance distribution. Near zero, or negative, means each
  corpus is being fitted its own shrinkage and the gain in 3h3 is not a
  propagation correction at all.
""")

    # TEST 2. Is each bin's mean flat in along-road position? The correction
    # claims to be a function of range only.
    print("TEST 2, confounding. Each bin's residual mean against the "
          "transmitter's\nalong-road position, on corpus A.\n")
    print(f"  {'bin':>16s} {'n':>9s} {'slope dB/km':>13s} {'t':>8s} {'spread dB':>10s}")
    worst = 0.0
    for i in range(len(muA)):
        m = (A.d.values >= EDGES[i]) & (A.d.values < EDGES[i + 1])
        if m.sum() < 500:
            continue
        x = A.trueX.values[m] / 1000.0            # km
        r = residA[m]
        X = np.c_[np.ones(m.sum()), x]
        beta, *_ = np.linalg.lstsq(X, r, rcond=None)
        pred = X @ beta
        se = np.sqrt(np.sum((r - pred) ** 2) / (m.sum() - 2) /
                     np.sum((x - x.mean()) ** 2))
        tstat = beta[1] / se if se > 0 else np.nan
        # how much of the bin's mean the position term moves across the road
        spread = abs(beta[1]) * (x.max() - x.min())
        worst = max(worst, spread)
        lo, hi = EDGES[i], EDGES[i + 1]
        hs = "inf" if hi > 1e8 else f"{hi:.0f}"
        print(f"  {f'{lo:.0f} to {hs}':>16s} {m.sum():9,d} {beta[1]:13.3f} "
              f"{tstat:8.1f} {spread:10.3f}")
    print(f"""
  The spread column is what the position term moves the bin mean by across the
  full road, in dB. Compare it against the correction the bin applies: the
  largest here is {worst:.2f} dB against corrections of order
  {np.max(np.abs(muA)):.2f} dB. If they are comparable then the correction is
  substantially a function of where the transmitter is rather than how far away
  it is, and an objective built from it is informed about the answer.

  A large t statistic on its own means little at this sample size. The spread
  column is the one to read.
""")


if __name__ == "__main__":
    main()
