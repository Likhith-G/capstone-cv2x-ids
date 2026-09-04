#!/usr/bin/env python3
"""
Where the detection floor comes from, derived rather than measured.

The project measures a floor: a lie has to exceed the receivers' localisation
error before it can be detected, and a single receiver never gets there. This
script asks what sets that error, from the geometry and the noise alone, with
no classifier involved.

The measurement model is the one the estimator already assumes, in
pooled_consensus._resid:

    rsrp_i = A - 10 n log10(d_i(p)) + e_i

with p the position, and A and n free. A and n being free is what makes the
pooled statistic invariant to transmit power, and it means they are nuisance
parameters: the information they absorb is information the position does not
get. The bound below profiles them out rather than assuming they are known,
which is the difference between bounding this estimator and bounding a
different one.

Two things come out of it.

**The error ellipse.** The Fisher information for position is a sum of outer
products of unit vectors from each receiver, weighted by inverse squared
distance. Receivers along a straight road point at a transmitter from nearly
the same two directions, so the sum is nearly rank deficient across the road,
and the ellipse is long in exactly the direction an estimator-aware attacker
was found to lie in.

**Why one receiver never crosses the floor.** The residual has two parts: a
per link component that persists for as long as the link does, and a per sample
component that does not. Averaging more windows from one receiver reduces the
second and not the first, so a single receiver's error stops falling while a
lie is still invisible. Pooling across receivers reduces the first, because
different links shadow independently. That is the mechanism the paper argues
physically, stated as a variance decomposition.
"""
import argparse
import numpy as np
import pandas as pd
from pooled_consensus import observer_geometry, true_positions, ROAD_HALFWIDTH

LN10 = np.log(10.0)


def fit_law(d, rsrp):
    """Least squares on rsrp = A - 10 n log10(d). Returns A, n, residuals."""
    L = 10.0 * np.log10(np.maximum(d, 1.0))
    X = np.c_[np.ones(len(L)), -L]
    beta, *_ = np.linalg.lstsq(X, rsrp, rcond=None)
    return float(beta[0]), float(beta[1]), rsrp - X @ beta


def variance_split(df, resid):
    """Split the residual into a per link part and a per sample part.

    The per link part is what a single receiver cannot average away, because it
    is the same shadow every window the link lasts. It is the quantity that
    makes a single-receiver floor exist at all.
    """
    g = pd.DataFrame({"link": df.link.values, "r": resid})
    m = g.groupby("link").r.agg(["mean", "std", "count"])
    m = m[m["count"] >= 3]
    within = float(np.sqrt(np.nanmean(m["std"].values ** 2)))
    # The spread of link means already contains the sampling error of each
    # mean, so subtract it rather than reporting the persistent component
    # inflated by the part that does average away.
    raw = float(np.var(m["mean"].values))
    bias = float(np.nanmean(m["std"].values ** 2 / m["count"].values))
    between = float(np.sqrt(max(raw - bias, 0.0)))
    return within, between, len(m)


def fisher(ox, oy, px, py, n_exp, sigma, profile=True):
    """Fisher information for position, with A and n profiled out.

    d mean_i / d p = -(10 n / ln10) * u_i / d_i, u_i the unit vector from
    receiver i to the position. Stacking those rows gives the design matrix for
    position; the nuisance columns are the derivatives with respect to A and n.
    Profiling means projecting the position columns off the nuisance columns,
    which is what the estimator does when it fits A and n freely.
    """
    dx, dy = px - ox, py - oy
    d = np.maximum(np.hypot(dx, dy), 1.0)
    k = -(10.0 * n_exp / LN10) / d
    Gp = np.c_[k * (dx / d), k * (dy / d)]          # position columns
    if profile:
        Gn = np.c_[np.ones(len(d)), -10.0 * np.log10(d)]   # dA, dn columns
        # residual of the position columns after regressing out the nuisance
        beta, *_ = np.linalg.lstsq(Gn, Gp, rcond=None)
        Gp = Gp - Gn @ beta
    return (Gp.T @ Gp) / (sigma ** 2)


def ellipse(J):
    """Semi-axes and orientation of the CRLB error ellipse, metres and degrees
    from the road axis. Returns nan when the geometry is singular."""
    try:
        C = np.linalg.inv(J)
    except np.linalg.LinAlgError:
        return np.nan, np.nan, np.nan
    w, V = np.linalg.eigh(C)
    if np.any(w <= 0):
        return np.nan, np.nan, np.nan
    major, minor = float(np.sqrt(w[1])), float(np.sqrt(w[0]))
    ang = float(np.degrees(np.arctan2(abs(V[1, 1]), abs(V[0, 1]))))
    return major, minor, ang


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--units", type=int, default=4000,
                    help="pooled units to evaluate the bound over")
    ap.add_argument("--min-obs", type=int, default=5,
                    help="five receivers is the identifiability floor: four "
                         "free parameters plus one")
    ap.add_argument("--road-halfwidth", type=float, default=ROAD_HALFWIDTH)
    a = ap.parse_args()

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1].reset_index(drop=True)
    obs, claim = observer_geometry(a.run_dir, a.tags)
    truth = true_positions(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(truth, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])
    df = df[df.phy_rsrp_mean.notna()]

    # The law is calibrated the way a deployment would calibrate it: on traffic
    # it has no reason to doubt, against the position that traffic claims, which
    # for a benign station is where it actually is.
    ben = df[df.label_attackId == 0].copy()
    ben["d"] = np.hypot(ben.rxX - ben.trueX, ben.rxY - ben.trueY)
    ben = ben[ben.d > 1.0]
    A, n_exp, resid = fit_law(ben.d.values, ben.phy_rsrp_mean.values)
    sigma = float(np.std(resid))

    ben["link"] = (ben.key_seed.astype(str) + ":" +
                   ben.key_rxNodeId.astype(str) + ":" +
                   ben.key_claimedStationId.astype(str))
    within, between, n_links = variance_split(ben, resid)

    print(f"{len(ben):,} benign observations, {n_links:,} links with 3 or more windows\n")
    print("propagation law fitted on benign traffic")
    print(f"  intercept A            {A:8.2f} dBm")
    print(f"  path loss exponent n   {n_exp:8.3f}")
    print(f"  residual sigma         {sigma:8.3f} dB\n")

    print("residual variance decomposition")
    print(f"  per link, persists while the link lasts   {between:8.3f} dB")
    print(f"  per sample, averages away within a link   {within:8.3f} dB")
    print(f"  ratio of persistent to averaging          {between / within:8.3f}")
    print("""
A single receiver watching one station for W windows reduces the per sample
part by root W and does not reduce the per link part at all, so its position
error stops falling at the persistent floor no matter how long it watches.
That is why the single-observer arm never crosses the detection floor at any
magnitude, rather than crossing it late. Receivers in different places shadow
independently, so pooling reduces the persistent part instead.
""")

    # Which sigma goes into the bound depends on what is being bounded, and
    # getting this wrong is the easiest way to produce a flattering number.
    # The pooled fit uses one window across several receivers. Different
    # receivers are different links, so their shadows are independent and each
    # measurement carries the full residual. The bound below therefore uses the
    # total sigma. The persistent component is what matters for a SINGLE
    # receiver averaging over time, and it is quoted separately for that.
    sig_eff = sigma
    print(f"the ellipse below uses the total residual, {sig_eff:.3f} dB, because "
          f"a pooled fit\nsees one window at each of several independent links. "
          f"The persistent component\n{between:.3f} dB is the floor a single "
          f"receiver averaging over time cannot go below.\n")

    g = df.groupby(["key_seed", "key_claimedStationId", "key_window"])
    keys = [k for k, v in g.size().items() if v >= a.min_obs]
    rng = np.random.default_rng(0)
    if len(keys) > a.units:
        keys = [keys[i] for i in rng.choice(len(keys), a.units, replace=False)]

    rows = []
    for k in keys:
        v = g.get_group(k)
        ox, oy = v.rxX.values, v.rxY.values
        px, py = float(v.trueX.iloc[0]), float(v.trueY.iloc[0])
        J = fisher(ox, oy, px, py, n_exp, sig_eff, profile=True)
        maj, mnr, ang = ellipse(J)
        Jk = fisher(ox, oy, px, py, n_exp, sig_eff, profile=False)
        majk, mnrk, _ = ellipse(Jk)
        # Road constrained: the across-road coordinate is known to lie in a
        # 2*halfwidth band, so the estimator cannot spend error there. The
        # bound for the remaining free coordinate is the reciprocal of the
        # along-road information on its own.
        # Marginal standard deviations of the free fit, which is what the
        # unconstrained localisation error should be compared against.
        try:
            C = np.linalg.inv(J)
            free_along = float(np.sqrt(C[0, 0]))
            free_across = float(np.sqrt(C[1, 1]))
        except np.linalg.LinAlgError:
            free_along = free_across = np.nan
        # Road constrained: the across-road coordinate is pinned to the
        # carriageway, so the along-road coordinate is estimated with the other
        # one effectively known. That is the conditional bound, not the
        # marginal one, and it is the right comparison for the constrained fit.
        road_along = float(np.sqrt(1.0 / J[0, 0])) if J[0, 0] > 0 else np.nan
        rows.append((len(v), maj, mnr, ang, majk, free_along, free_across,
                     road_along))

    r = pd.DataFrame(rows, columns=["n_obs", "major", "minor", "angle",
                                    "major_known", "free_along", "free_across",
                                    "road_along"])
    r = r.replace([np.inf, -np.inf], np.nan).dropna()
    print(f"{len(r):,} pooled units with {a.min_obs} or more receivers, "
          f"median {r.n_obs.median():.0f} receivers per unit\n")

    print("Cramer-Rao error ellipse, A and n profiled out as the estimator fits them")
    for q in (0.25, 0.5, 0.75):
        print(f"  {int(q*100):>3d}th percentile   major {r.major.quantile(q):9.1f} m"
              f"   minor {r.minor.quantile(q):7.1f} m"
              f"   major axis {r.angle.quantile(q):5.1f} deg from the road")
    print(f"\nfree fit, marginal standard deviations")
    print(f"  along the road            {r.free_along.median():9.1f} m")
    print(f"  across the road           {r.free_across.median():9.1f} m")
    print(f"  anisotropy                {r.free_across.median() / r.free_along.median():9.1f}")
    print(f"\nroad constrained, the across-road coordinate pinned to the carriageway")
    print(f"  along the road            {r.road_along.median():9.1f} m")
    print(f"  improvement over the free fit  "
          f"{r.free_across.median() / r.road_along.median():6.1f} times")
    print("""
Compare these two against the measured localisation error, 65.2 m free and
18.3 m road constrained, in RESULTS.md 4b. The bound is a lower bound on any
unbiased estimator, so the measured error should sit above it. If the ratio
between the two bounds tracks the ratio between the two measurements, the
road constraint is doing what the geometry says it should and not something
incidental.""")
    print(f"\n  same geometry with A and n KNOWN: median major "
          f"{r.major_known.median():.1f} m, so fitting the propagation law "
          f"costs a factor of\n  {r.major.median() / r.major_known.median():.1f} "
          f"in position accuracy. That is the price of invariance to transmit power.")

    # How the bound moves with the number of cooperating receivers is the
    # deployment question: a roadside unit region carries a median of eight,
    # the corpus-wide study forty, and five is the identifiability floor.
    print(f"\nthe bound against the number of cooperating receivers")
    print(f"{'receivers':>12s} {'units':>8s} {'across-road':>13s} {'along-road':>12s}"
          f" {'road-constrained':>18s}")
    bins = [(5, 6), (7, 9), (10, 14), (15, 24), (25, 44), (45, 10**6)]
    for lo, hi in bins:
        s = r[(r.n_obs >= lo) & (r.n_obs <= hi)]
        if len(s) < 20:
            continue
        lab = f"{lo} to {hi}" if hi < 10**6 else f"{lo} or more"
        print(f"{lab:>12s} {len(s):8d} {s.free_across.median():11.1f} m"
              f" {s.free_along.median():10.1f} m {s.road_along.median():16.1f} m")
    print("""
Five receivers is where the fit becomes identifiable at all, with four free
parameters, and the across-road bound there is what makes a lie in that
direction cheap. Read the eight receiver row as the deployment case: it is what
one roadside unit region actually has.""")

    print("""
Read the angle column against section 4b. The estimator-aware attacker was
measured to lie 75 to 85 degrees off the road axis, found by search over 72
directions with no knowledge of this bound. The major axis of the ellipse is
where the geometry is weakest, so the attack and the bound should point the
same way. If they do, the attack is not a quirk of that search, it is the
geometry, and the road constraint works because it removes that axis rather
than because it happens to help.
""")


if __name__ == "__main__":
    main()
