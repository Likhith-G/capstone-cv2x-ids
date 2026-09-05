#!/usr/bin/env python3
"""
The pooled detector inside a real federated deployment.

Section 3b shows that pooling across receivers resolves position falsification,
and that the fusion has to happen at the feature level because exchanging
verdicts recovers nothing. Section 5 runs the federated panel with one receiver
per client. Those two results describe the same system and they have not been
run together, so this does it.

A client here is a ROADSIDE UNIT REGION: the RSU plus every vehicle whose
nearest RSU it is. The vehicles contribute their own position, the position each
message claimed and the RSRP they measured, the RSU fuses them into one pooled
unit per (station, window), and the RSU is what participates in the federation.
That is the edge-based architecture this project is named for, rather than the
single-receiver clients section 5 currently uses.

The number that decides whether this is deployable is the receiver count per
region. Ninety vehicles spread over twelve regions is about seven or eight per
region plus the RSU, which sits just above the five-receiver identifiability
floor and well below the median 87 that section 3b's headline was measured
with. If the effect survives here it survives in a deployment.

Output is a pooled corpus with `key_region` as the client column, ready for
`check_partition_skew.py` and `federated.py --observer-col key_region`.
"""
import argparse
import numpy as np
import pandas as pd

from pooled_consensus import (observer_geometry, consensus_block, MIN_OBS,
                              true_positions, calibrate_mean, DEBIAS_EDGES,
                              ROAD_HALFWIDTH)

KEY = ["key_seed", "key_claimedStationId", "key_window"]


def rsu_positions(run_dir, tags, obs):
    """Where each seed's roadside units are. RSUs are static, so one position
    per (seed, node) taken from any window it appears in."""
    out = []
    for i, tag in enumerate(tags):
        st = pd.read_csv(f"{run_dir}/stations_{tag}.csv")
        ids = set(st[st.role == "rsu"].nodeId.astype(int) + (i + 1) * 100000)
        sub = obs[(obs.key_seed == tag) & (obs.key_rxNodeId.isin(ids))]
        p = sub.groupby("key_rxNodeId")[["rxX", "rxY"]].mean().reset_index()
        p["key_seed"] = tag
        p["region"] = np.arange(len(p))
        out.append(p)
    return pd.concat(out, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--road-halfwidth", type=float, default=None,
                    nargs="?", const=ROAD_HALFWIDTH, metavar="METRES",
                    help="constrain the position fit to the carriageway, the "
                         "same way pooled_consensus.py does. The region "
                         "pipeline feeds the federated panel, the privacy "
                         "sweep and the operating point, so it has to use the "
                         "same estimator as the pooling section or those "
                         "sections describe a different detector")
    ap.add_argument("--debias", action="store_true",
                    help="apply the calibrated mean correction of RESULTS.md "
                         "3h3 to the propagation law, in both the free fit and "
                         "the claim fit. Off by default so the published tables "
                         "keep their meaning. The correction is calibrated here "
                         "on benign traffic in this run, against the position "
                         "that traffic claims, which for a benign station is "
                         "where it actually is")
    a = ap.parse_args()
    rng = np.random.default_rng(0)

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    feats = [c for c in df.columns if c.startswith(("app_", "phy_"))]
    obs, claim = observer_geometry(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(claim, how="inner",
                  on=["key_seed", "key_claimedStationId", "key_window"])
    print(f"{len(df)} observations after attaching geometry")

    # Assign every receiver, RSU and vehicle alike, to its nearest RSU.
    rsu = rsu_positions(a.run_dir, a.tags, obs)
    print(f"{len(rsu)} roadside units across {len(a.tags)} seeds")
    df["region"] = -1
    for tag, g in rsu.groupby("key_seed"):
        m = df.key_seed == tag
        if not m.any():
            continue
        d = np.hypot(df.loc[m, "rxX"].values[:, None] - g.rxX.values[None, :],
                     df.loc[m, "rxY"].values[:, None] - g.rxY.values[None, :])
        df.loc[m, "region"] = g.region.values[d.argmin(axis=1)]
    df["key_region"] = df.key_seed.astype(str) + "_r" + df.region.astype(str)

    mu = None
    if a.debias:
        # Calibrated on benign traffic only, against its own claimed position,
        # which is what a deployment can actually do offline.
        truth = true_positions(a.run_dir, a.tags)
        b = df[df.label_attackId == 0].merge(
            truth, how="inner",
            on=["key_seed", "key_claimedStationId", "key_window"])
        b = b[b.phy_rsrp_mean.notna()]
        d = np.hypot(b.rxX - b.trueX, b.rxY - b.trueY).values
        keep = d > 1.0
        d, r = d[keep], b.phy_rsrp_mean.values[keep]
        L = 10.0 * np.log10(d)
        X = np.c_[np.ones(len(L)), -L]
        beta, *_ = np.linalg.lstsq(X, r, rcond=None)
        mu = calibrate_mean(d, r - X @ beta)
        print(f"calibrated mean correction on {len(d):,} benign observations")
        for i in range(len(mu)):
            hi = DEBIAS_EDGES[i + 1]
            hs = "inf" if hi > 1e8 else f"{hi:.0f}"
            print(f"  {DEBIAS_EDGES[i]:>6.0f} to {hs:<6s} {mu[i]:+7.3f} dB")
        print()

    rows, single, meta = [], [], []
    for k, v in df.groupby(KEY + ["key_region"], sort=False):
        v = v[v.phy_rsrp_mean.notna()]
        if len(v) < MIN_OBS:
            continue
        cx, cy = float(v.claimedX.iloc[0]), float(v.claimedY.iloc[0])
        cb, _ = consensus_block(v.rxX.values, v.rxY.values,
                                v.phy_rsrp_mean.values, cx, cy, rng,
                                road_halfwidth=a.road_halfwidth, mu=mu)
        rows.append(np.concatenate([v[feats].mean().values,
                                    [cb[c] for c in sorted(cb)]]))
        # One receiver from the SAME region and unit, so a paired comparison
        # against the pooled row is available without a second pass.
        single.append(v[feats].iloc[rng.integers(len(v))].values)
        meta.append((k[0], k[1], k[2], k[3], int(v.label_attackId.iloc[0]),
                     int(v.label_txNodeId.iloc[0]), len(v)))

    cols = feats + sorted(consensus_block(np.zeros(6), np.zeros(6), np.zeros(6),
                                          0.0, 0.0, rng,
                                          road_halfwidth=a.road_halfwidth)[0])
    X = pd.DataFrame(rows, columns=cols)
    M = pd.DataFrame(meta, columns=KEY + ["key_region", "label_attackId",
                                          "label_txNodeId", "n_recv"])
    out = pd.concat([M, X], axis=1)
    out["label_clean"] = 1
    out["label_is_attack"] = (out.label_attackId != 0).astype(int)
    out.to_pickle(a.out)
    S = pd.concat([M, pd.DataFrame(single, columns=feats)], axis=1)
    S["label_clean"] = 1
    S["label_is_attack"] = (S.label_attackId != 0).astype(int)
    single_path = a.out.replace(".pkl", "_single.pkl")
    S.to_pickle(single_path)
    print(f"paired single-receiver arm -> {single_path}")

    print(f"\n{len(out)} pooled units, {out.key_region.nunique()} regions, "
          f"{out.label_txNodeId.nunique()} stations, "
          f"{out.label_attackId.nunique()} classes -> {a.out}")
    print(f"receivers per pooled unit: median {out.n_recv.median():.0f}, "
          f"p10 {out.n_recv.quantile(.1):.0f}, p90 {out.n_recv.quantile(.9):.0f}, "
          f"max {out.n_recv.max():.0f}")
    per = out.groupby("key_region").size()
    print(f"units per region: median {per.median():.0f}, min {per.min()}, "
          f"max {per.max()}")
    print("\nwindows per class:")
    print(out.label_attackId.value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
