#!/usr/bin/env python3
"""
Negative control for the cross-observer consensus statistic.

That the statistic stays silent on speed_falsify and sps_manipulation is a
consistency check, not an independence test: those attackers transmit truthful
positions, so they are quiet by construction. The test that actually
discriminates is the other direction. Give a BENIGN station another station's
claimed position, from the same window so the geometry is comparable, and
recompute. If the statistic is measuring the claim against the radio geometry
and nothing else, a benign station handed a false claim must look like a
position falsifier.

If instead permuted benign stays benign, the statistic is reading something
other than the claim and the whole interpretation is wrong. This is the check a
reviewer builds if the paper does not.

The displacement introduced by permutation is reported beside the result,
because a permuted claim is usually further from the truth than the injected
attack is, and the separation has to be read against the size of the lie.
"""
import argparse
import numpy as np
import pandas as pd
from pooled_consensus import observer_geometry, MIN_OBS

KEY = ["key_seed", "key_claimedStationId", "key_window"]


def claim_stats(ox, oy, rsrp, cx, cy):
    d = np.maximum(np.hypot(ox - cx, oy - cy), 1.0)
    X = np.c_[np.ones(len(d)), -10.0 * np.log10(d)]
    beta, *_ = np.linalg.lstsq(X, rsrp, rcond=None)
    r = rsrp - X @ beta
    ss = float(np.sum((rsrp - rsrp.mean()) ** 2))
    return (float(np.sqrt(np.mean(r ** 2))),
            1.0 - float(np.sum(r ** 2)) / ss if ss > 0 else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    df = df[KEY + ["key_rxNodeId", "phy_rsrp_mean", "label_attackId"]] \
        .dropna(subset=["phy_rsrp_mean"])
    obs, claim = observer_geometry(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(claim, how="inner", on=["key_seed", "key_claimedStationId", "key_window"])

    # A permuted claim for every benign unit, drawn from another benign station
    # in the SAME seed and window so the road geometry is the same.
    units = (df.groupby(KEY)
               .agg(label=("label_attackId", "first"),
                    cx=("claimedX", "first"), cy=("claimedY", "first"))
               .reset_index())
    perm = {}
    for (seed, win), g in units[units.label == 0].groupby(["key_seed", "key_window"]):
        if len(g) < 2:
            continue
        idx = np.arange(len(g))
        shift = rng.integers(1, len(g))          # derangement: never itself
        for src, dst in zip(idx, np.roll(idx, shift)):
            perm[(seed, g.key_claimedStationId.iloc[src], win)] = (
                float(g.cx.iloc[dst]), float(g.cy.iloc[dst]))

    rows = []
    for k, g in df.groupby(KEY, sort=False):
        if len(g) < MIN_OBS:
            continue
        ox, oy, r = g.rxX.values, g.rxY.values, g.phy_rsrp_mean.values
        cx, cy = float(g.claimedX.iloc[0]), float(g.claimedY.iloc[0])
        rmse, r2 = claim_stats(ox, oy, r, cx, cy)
        rows.append((int(g.label_attackId.iloc[0]), "as transmitted", rmse, r2, 0.0))
        if k in perm:
            px, py = perm[k]
            prmse, pr2 = claim_stats(ox, oy, r, px, py)
            rows.append((int(g.label_attackId.iloc[0]), "claim permuted",
                         prmse, pr2, float(np.hypot(px - cx, py - cy))))
    R = pd.DataFrame(rows, columns=["label", "arm", "claim_rmse", "claim_r2", "moved_m"])

    ben = R[(R.label == 0) & (R.arm == "as transmitted")]
    sd, med = ben.claim_rmse.std(), ben.claim_rmse.median()
    print(f"{len(R[R.arm == 'as transmitted'])} units, "
          f"{len(ben)} benign, benign claim_rmse median {med:.2f} dB sd {sd:.2f}\n")
    print(f"{'group':34s} {'n':>6s} {'claim_rmse':>11s} {'sd from benign':>15s} "
          f"{'claim_r2':>9s} {'claim moved':>12s}")

    def line(name, sub):
        if not len(sub):
            return
        print(f"{name:34s} {len(sub):6d} {sub.claim_rmse.median():11.2f} "
              f"{(sub.claim_rmse.median() - med) / sd:15.2f} "
              f"{sub.claim_r2.median():9.3f} {sub.moved_m.median():10.1f} m")

    line("benign, as transmitted", ben)
    line("benign, claim permuted", R[(R.label == 0) & (R.arm == "claim permuted")])
    for c in sorted(R.label.unique()):
        if c:
            line(f"class {c}, as transmitted",
                 R[(R.label == c) & (R.arm == "as transmitted")])
    print("\nA benign station given someone else's claimed position must look like a\n"
          "position falsifier. If it does not, the statistic is not reading the claim.")


if __name__ == "__main__":
    main()
