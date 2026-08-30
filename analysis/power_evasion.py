#!/usr/bin/env python3
"""
Transmit power control against the received-power plausibility check.

This answers the objection that RESULTS.md lists as a limitation and that a
reviewer will raise first: RSRP is not a trustworthy witness because the
attacker chooses its transmit power, so it can simply turn the power up or down
until the received power agrees with the position it is claiming.

Against ONE receiver that objection is correct and fatal. Against several it is
not, and the reason is that the attacker has one power setting and the receivers
have different geometries. A claimed position implies a DIFFERENT required
received power at every receiver, so a single power offset cannot satisfy them
all. It can only slide every receiver's residual by the same constant.

The pooled statistics used here fit the propagation intercept per station and
window, so a constant slide is removed before the statistic is formed. The
invariance is therefore analytic, not lucky, and this script is the empirical
confirmation plus the measurement of what the same adversary does to the
single-receiver check.

Adversaries:
  none    measured received power as it is.
  power   the attacker picks the single best power offset for the lie it is
          telling, the offset that minimises its own total residual against the
          claimed geometry. This is the strongest constant-power adversary
          there is, and it is recomputed every window, which is stronger than
          any real transmitter that has to commit to a power level.

Scored as AUC of each statistic separating benign from one attack class, so no
threshold or classifier is involved and the comparison is about information.
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from pooled_consensus import observer_geometry, MIN_OBS

KEY = ["key_seed", "key_claimedStationId", "key_window"]


def fit_global_law(d, rsrp):
    """A deployment calibrates its propagation law once from traffic it has no
    reason to doubt. Fitted on benign observations against claimed distance,
    which for a benign station is the true distance."""
    L = 10.0 * np.log10(np.maximum(d, 1.0))
    A = np.c_[np.ones(len(L)), -L]
    beta, *_ = np.linalg.lstsq(A, rsrp, rcond=None)
    return float(beta[0]), float(beta[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--classes", type=int, nargs="+", default=[1, 3, 4])
    a = ap.parse_args()

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    df = df[KEY + ["key_rxNodeId", "phy_rsrp_mean", "label_attackId",
                   "label_txNodeId"]].dropna(subset=["phy_rsrp_mean"])
    obs, claim = observer_geometry(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(claim, how="inner", on=["key_seed", "key_claimedStationId", "key_window"])
    rng = np.random.default_rng(0)
    df["d_claim"] = np.hypot(df.rxX - df.claimedX, df.rxY - df.claimedY)
    print(f"{len(df)} observations")

    ben = df.label_attackId == 0
    A0, n0 = fit_global_law(df.d_claim[ben].values, df.phy_rsrp_mean[ben].values)
    print(f"global propagation law from benign traffic: "
          f"rsrp = {A0:.1f} - 10 x {n0:.2f} x log10(d)")

    rows = []
    for k, g in df.groupby(KEY, sort=False):
        if len(g) < MIN_OBS:
            continue
        d = np.maximum(g.d_claim.values, 1.0)
        L = 10.0 * np.log10(d)
        r = g.phy_rsrp_mean.values
        pred = A0 - n0 * L
        # Two constant-power adversaries. The transmitter has ONE power setting
        # and the receivers have different geometries, so it must choose whose
        # residual to fix.
        #   power-global    minimise its total residual over every receiver.
        #                   The best it can do against the population.
        #   power-targeted  zero the residual at the one receiver running the
        #                   single-receiver check, ignoring what that does
        #                   everywhere else. This defeats that receiver by
        #                   construction and is the ceiling of what power
        #                   control can achieve against it.
        i = int(rng.integers(len(r)))
        d_global = float(np.mean(pred - r))
        d_target = float(pred[i] - r[i])
        for adv, rr in (("none", r), ("power-global", r + d_global),
                        ("power-targeted", r + d_target)):
            single = abs(rr[i] - pred[i])
            # pooled: refit intercept and exponent GIVEN the claim
            X = np.c_[np.ones(len(L)), -L]
            beta, *_ = np.linalg.lstsq(X, rr, rcond=None)
            res = rr - X @ beta
            rows.append((k[0], k[1], k[2], int(g.label_attackId.iloc[0]), adv,
                         single, float(np.sqrt(np.mean(res ** 2))),
                         float(abs(beta[1] - n0)), len(g)))
    R = pd.DataFrame(rows, columns=KEY + ["label_attackId", "adversary",
                                          "single_resid", "pooled_rmse",
                                          "pooled_exp_dev", "n_obs"])
    print(f"{R.key_window.count() // 3} triples\n")

    stats = ["single_resid", "pooled_rmse", "pooled_exp_dev"]
    print(f"{'class':>6s} {'adversary':>10s}  " +
          "  ".join(f"{s:>16s}" for s in stats))
    for cls in a.classes:
        for adv in ("none", "power-global", "power-targeted"):
            sub = R[(R.adversary == adv) & (R.label_attackId.isin([0, cls]))]
            if sub.label_attackId.nunique() < 2:
                continue
            yv = (sub.label_attackId == cls).astype(int).values
            aucs = [roc_auc_score(yv, sub[s].values) for s in stats]
            print(f"{cls:>6d} {adv:>10s}  " + "  ".join(f"{v:16.3f}" for v in aucs))
    print("\nAUC 0.5 means the statistic carries no information about the class.\n"
          "Below 0.5 means the attacker now looks LESS anomalous than benign\n"
          "traffic on that statistic, which is a defeated detector, not a\n"
          "working one with the sign flipped: a threshold set to catch it would\n"
          "flag most of the benign fleet.")


if __name__ == "__main__":
    main()
