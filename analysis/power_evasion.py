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

With --best-response the script also answers the harder version of the
objection. A power offset cannot beat the pooled statistic because the fit
removes a constant slide analytically, so an attacker who understands the
detector would not spend its effort there. It would choose WHERE TO CLAIM TO BE
instead, picking among the positions that serve its purpose the one that leaves
the smallest pooled residual. That is the principled lower bound on how well
this check can ever do, because no attacker constrained to tell a lie of a
given size can do better, and it is measured rather than argued.
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from pooled_consensus import (observer_geometry, true_positions,
                              consensus_block, free_fit, MIN_OBS)

KEY = ["key_seed", "key_claimedStationId", "key_window"]


def fit_global_law(d, rsrp):
    """A deployment calibrates its propagation law once from traffic it has no
    reason to doubt. Fitted on benign observations against claimed distance,
    which for a benign station is the true distance."""
    L = 10.0 * np.log10(np.maximum(d, 1.0))
    A = np.c_[np.ones(len(L)), -L]
    beta, *_ = np.linalg.lstsq(A, rsrp, rcond=None)
    return float(beta[0]), float(beta[1])


def free_rmse_of(ox, oy, rsrp, road_halfwidth):
    """Residual of the best single position, constrained or not."""
    try:
        sol = free_fit(ox, oy, rsrp, road_halfwidth)
        return (float(np.sqrt(np.mean(sol.fun ** 2))),
                float(sol.x[0]), float(sol.x[1]))
    except Exception:
        return np.nan, np.nan, np.nan


def pooled_rmse(ox, oy, rsrp, cx, cy):
    """Residual of the two-parameter propagation fit given a claimed position.

    Intercept and exponent are free, which is what makes a constant transmit
    power offset invisible to this statistic and why an adaptive attacker has
    to move the claim rather than the power.
    """
    d = np.maximum(np.hypot(ox - cx, oy - cy), 1.0)
    L = 10.0 * np.log10(d)
    X = np.c_[np.ones(len(L)), -L]
    beta, *_ = np.linalg.lstsq(X, rsrp, rcond=None)
    return float(np.sqrt(np.mean((rsrp - X @ beta) ** 2)))


def best_response(ox, oy, rsrp, tx, ty, displacement, n_angles,
                  max_lateral=None):
    """The smallest pooled residual an attacker can leave while still lying by
    `displacement` metres, and the direction it lied in.

    The attacker is assumed to know the receivers' positions, the propagation
    model and the statistic, and to be free to choose any direction. Those are
    generous assumptions, deliberately: a bound is only worth reporting if the
    adversary it bounds is stronger than any real one.

    The direction is returned because the number alone does not explain
    itself. If the best lies are longitudinal, the finding is about a road
    geometry in which receivers are nearly collinear and a shift along the axis
    is close to what a different transmit power and path loss exponent would
    produce at the true position. That is a statement about the estimator, and
    it is actionable. A number is not.
    """
    ang = np.linspace(0.0, 2.0 * np.pi, n_angles, endpoint=False)
    best, best_th = np.inf, np.nan
    for th in ang:
        cx = tx + displacement * np.cos(th)
        cy = ty + displacement * np.sin(th)
        # A claim off the carriageway is rejected by a map check without any
        # radio evidence at all, so an attacker that has to remain plausible
        # cannot use those directions. Constraining the search here is what
        # separates "what received power cannot see" from "what an attacker can
        # actually get away with".
        if max_lateral is not None and abs(cy) > max_lateral:
            continue
        v = pooled_rmse(ox, oy, rsrp, cx, cy)
        if v < best:
            best, best_th = v, th
    return best, best_th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--classes", type=int, nargs="+", default=[1, 3, 4])
    ap.add_argument("--best-response", type=float, nargs="*", default=None,
                    metavar="METRES",
                    help="also measure the estimator-aware adversary at these "
                         "displacements, e.g. --best-response 25 50 100 200")
    ap.add_argument("--br-lateral", type=float, default=None, metavar="METRES",
                    help="keep the attacker's claim within this distance of "
                         "the road centreline. Without it the best response is "
                         "free to claim a position in the field beside the "
                         "road, which a map check rejects for nothing")
    ap.add_argument("--br-estimator-road", type=float, default=None,
                    metavar="METRES",
                    help="constrain the DETECTOR's position estimate to the "
                         "carriageway. Distinct from --br-lateral, which "
                         "constrains the ATTACKER. Setting both asks the "
                         "question that matters: a road-aware detector against "
                         "an attacker that must stay on the road")
    ap.add_argument("--br-triples", type=int, default=None, metavar="N",
                    help="cap the number of benign triples the best response "
                         "search runs over. The search is 72 nonlinear fits "
                         "per triple per displacement, so the full corpus is "
                         "hours; a few thousand triples already give a spread "
                         "far tighter than the effect being measured")
    ap.add_argument("--br-angles", type=int, default=72,
                    help="directions searched per displacement. The attacker "
                         "is given a fine search because the bound is supposed "
                         "to be generous to it")
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
    if a.best_response is not None:
        levels = a.best_response or [25.0, 50.0, 100.0, 200.0]
        run_best_response(df, a, levels)

    print("\nAUC 0.5 means the statistic carries no information about the class.\n"
          "Below 0.5 means the attacker now looks LESS anomalous than benign\n"
          "traffic on that statistic, which is a defeated detector, not a\n"
          "working one with the sign flipped: a threshold set to catch it would\n"
          "flag most of the benign fleet.")


def run_best_response(df, a, levels):
    """The estimator-aware adversary, measured on benign traffic.

    Benign stations are used rather than the existing attackers on purpose. An
    attacker in the corpus lied in whatever direction its parameters told it
    to, which is not the direction that would have served it best, so measuring
    the bound on those would measure their parameter draws. Taking a benign
    station and making it lie optimally isolates what the geometry allows from
    what any particular attack happened to do.
    """
    tp = true_positions(a.run_dir, a.tags)
    d = df.merge(tp, how="inner", on=KEY)
    ben = d[d.label_attackId == 0]
    print(f"\nestimator-aware best response, on {ben.key_window.count():,} "
          f"benign observations")
    print("The attacker knows the receiver positions, the propagation model "
          "and the statistic,\nand picks the direction of its lie to minimise "
          "the pooled residual. No attacker\nconstrained to lie by this much "
          "can leave a smaller residual than this.\n")

    # Two statistics, because they behave differently and only one of them is
    # what the detector uses. The raw claimed residual is what an attacker
    # would naively try to minimise. The RATIO of that residual to the best any
    # position could achieve on the same measurements is what the consensus
    # block actually carries, and the ratio cannot be pushed below one by
    # construction, since the free fit is a minimum over every position
    # including the claimed one.
    #
    # Minimising the ratio and minimising the raw residual are the same search,
    # because the free fit does not depend on the claim, so one pass gives the
    # best response for both.
    rng = np.random.default_rng(0)
    honest_rmse, honest_ratio = [], []
    rows = {lv: {"rmse": [], "ratio": [], "axis": [], "toward": [],
                 "blocked": 0}
            for lv in levels}
    free_err = []
    n_tri = 0
    groups = list(ben.groupby(KEY, sort=False))
    if a.br_triples and len(groups) > a.br_triples:
        # Sampled rather than truncated, because the groupby order follows seed
        # and window and taking a prefix would measure one seed's early traffic.
        idx = np.random.default_rng(0).choice(len(groups), a.br_triples,
                                              replace=False)
        groups = [groups[i] for i in sorted(idx)]
        print(f"capped to {len(groups):,} benign triples, sampled across the "
              f"corpus")
    for k, g in groups:
        if len(g) < MIN_OBS:
            continue
        ox, oy = g.rxX.values, g.rxY.values
        r = g.phy_rsrp_mean.values
        tx, ty = float(g.trueX.iloc[0]), float(g.trueY.iloc[0])
        blk, est = consensus_block(ox, oy, r, tx, ty, rng,
                                   road_halfwidth=a.br_estimator_road)
        free = blk["pool_free_rmse"]
        if not np.isfinite(free) or free <= 0 or not np.isfinite(est[0]):
            continue
        free_err.append(np.hypot(est[0] - tx, est[1] - ty))
        honest_rmse.append(blk["pool_claim_rmse"])
        honest_ratio.append(blk["pool_claim_rmse"] / free)
        for lv in levels:
            br, th = best_response(ox, oy, r, tx, ty, lv, a.br_angles,
                                   a.br_lateral)
            if not np.isfinite(br):
                # No direction at this displacement keeps the claim on the
                # road, so an attacker that must stay plausible cannot lie this
                # far at all. That is a result, not a gap.
                rows[lv]["blocked"] += 1
                continue
            rows[lv]["rmse"].append(br)
            rows[lv]["ratio"].append(br / free)
            # How longitudinal was the best lie? Zero degrees is straight along
            # the road, ninety is straight across it.
            rows[lv]["axis"].append(
                np.degrees(np.arcsin(min(1.0, abs(np.sin(th))))))
            # And how far did it move toward the estimator's own answer? The
            # free fit is typically tens of metres from the truth, so a lie
            # smaller than that error can be pointed at it.
            ex, ey = est
            d_true = np.hypot(ex - tx, ey - ty)
            cx, cy = tx + lv * np.cos(th), ty + lv * np.sin(th)
            rows[lv]["toward"].append(d_true - np.hypot(ex - cx, ey - cy))
        n_tri += 1
    if n_tri < 20:
        print(f"  only {n_tri} usable triples, not reporting")
        return

    hr = np.array(honest_rmse)
    hq = np.array(honest_ratio)
    fe = np.array(free_err)
    print(f"free-fit localisation error on these benign triples: median "
          f"{np.median(fe):.1f} m")
    print("That number is the budget the attacker gets to spend. A lie shorter "
          "than the\nestimator's own error can be aimed at the estimate "
          "instead of away from it.\n")
    print(f"{'displacement':>13s} {'best rmse':>11s} {'AUC rmse':>9s} "
          f"{'best ratio':>11s} {'AUC ratio':>10s} {'caught at 5%':>13s} "
          f"{'AUC 2-sided':>12s} {'caught 2-sided':>15s} "
          f"{'off-axis deg':>13s} {'toward est m':>13s}")
    print(f"{'0 m, honest':>13s} {np.median(hr):11.3f} {'':>9s} "
          f"{np.median(hq):11.3f}")
    for lv in levels:
        v = np.array(rows[lv]["rmse"])
        q = np.array(rows[lv]["ratio"])
        blocked = rows[lv]["blocked"]
        if len(v) < 20:
            print(f"{lv:11.0f} m   no on-road direction at this displacement "
                  f"for {blocked} of {n_tri} triples")
            continue
        y = np.r_[np.zeros(len(hr)), np.ones(len(v))]
        auc_r = roc_auc_score(y, np.r_[hr, v])
        auc_q = roc_auc_score(y, np.r_[hq, q])
        # Two-sided, because the ratio is only bounded below by one while the
        # claim lies inside the estimator's feasible set. Constrain the
        # estimator to the road and an off-road claim can score BELOW one: it
        # explains the measurements better than any on-road position does,
        # which is not the check failing, it is the check saying the claim is
        # not on the road. A one-sided reading throws that away.
        centre = np.median(hq)
        auc_2 = roc_auc_score(y, np.r_[np.abs(hq - centre), np.abs(q - centre)])
        lo, hi = np.quantile(hq, [0.025, 0.975])
        sep2 = float(((q < lo) | (q > hi)).mean())
        # Caught at a threshold set to the honest 95th percentile of the RATIO,
        # which is the statistic a deployment would threshold, at one false
        # alarm in twenty.
        sep = float((q > np.quantile(hq, 0.95)).mean())
        print(f"{lv:11.0f} m {np.median(v):11.3f} {auc_r:9.3f} "
              f"{np.median(q):11.3f} {auc_q:10.3f} {sep:13.3f} "
              f"{auc_2:12.3f} {sep2:15.3f} "
              f"{np.median(rows[lv]['axis']):13.1f} "
              f"{np.median(rows[lv]['toward']):13.1f}"
              + (f"   ({blocked} triples had no on-road direction)"
                 if blocked else ""))
    print(f"\n{n_tri:,} triples, {a.br_angles} directions searched per "
          f"displacement.")
    print("""
How to read this, and it is not the comfortable reading.

An AUC below 0.5 means the attacker found a claim that fits the measurements
BETTER than the honest position does. It can do that because the free fit is
tens of metres from the truth, so the true position is not the residual
minimum, and a lie shorter than that error can be aimed at the minimum. The
honest vehicle has no such freedom. The 'toward est' column is how much closer
to the estimate the best lie lands, in metres, and a positive number there is
the whole mechanism.

The ratio does NOT rescue this. It is bounded below by one, so it cannot be
driven to zero, but the honest ratio is not one either, and an attacker
standing nearer the residual minimum than the honest vehicle gets the lower
ratio of the two.

The two-sided columns score deviation from the honest ratio in EITHER
direction, against a band holding 95 percent of honest traffic. Use them
whenever the estimator is road constrained and the attacker is not, because a
ratio below one then means the claim fits better than anywhere on the road,
which is a detection rather than a miss.

The 'off-axis' column says whether the best lies are longitudinal, zero degrees
being along the road and ninety across it. Receivers strung along a straight
road are close to collinear, so a shift along the axis produces a distance
profile that a different transmit power and path loss exponent largely
reproduce at the true position. If that column is small, the finding is a
statement about this geometry rather than about received power in general, and
the remedy is a better estimator rather than a different feature.""")


if __name__ == "__main__":
    main()
