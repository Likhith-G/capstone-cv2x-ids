#!/usr/bin/env python3
"""
How far does a vehicle have to lie before anyone can tell?

The three position falsification classes are the same mechanism at different
magnitudes: a constant displacement of the claimed position, drawn from a small
band, a middle band, or a large one. Reporting them as three classes with three
F1 scores throws away the thing they were built to measure, which is the
displacement at which detection becomes possible at all.

This treats magnitude as the axis instead of the label. Every station running a
constant-offset attack is placed on one scale by the displacement it actually
realised, detection is measured per station, and the benign positioning error
is drawn on the same scale, because a displacement only means something
relative to the error an honest receiver already carries.

The result is a detection floor: the point below which a claim is
indistinguishable from a bad GNSS fix, which no detector can cross and which
therefore belongs in the paper as a property of the problem rather than as a
weakness of this detector.

With --pooled, the same curve is computed on the cross-receiver table, which
answers whether pooling moves the floor or only improves detection above it.
"""
import argparse
import pathlib

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold

# The constant-offset ladder. Every one of these displaces the claimed position
# by a fixed vector and differs only in how far.
LADDER = {11: "small", 13: "medium", 1: "large"}


def station_offsets(run_dir, tags):
    """Realised displacement per station, and the benign error distribution.

    Taken from the transmit log rather than from the drawn parameter, because
    what matters is the displacement a receiver could in principle observe, and
    that includes the positioning error the attacker's own receiver contributes.
    """
    rows, benign = [], []
    for tag in tags:
        tx = pd.read_csv(f"{run_dir}/tx_{tag}.csv",
                         usecols=["claimedStationId", "attackId",
                                  "trueX", "trueY", "claimedX", "claimedY"],
                         on_bad_lines="skip").dropna()
        tx["offset"] = np.hypot(tx.claimedX - tx.trueX, tx.claimedY - tx.trueY)
        g = (tx.groupby(["claimedStationId", "attackId"]).offset
               .median().reset_index()
               .rename(columns={"claimedStationId": "key_claimedStationId"}))
        g["key_seed"] = tag
        rows.append(g)
        benign.append(tx.loc[tx.attackId == 0, "offset"])
    return pd.concat(rows, ignore_index=True), pd.concat(benign, ignore_index=True)


def scenario_fingerprint(run_dir, tags):
    """A hash of where the benign vehicles actually were.

    Two campaigns run with the same rngRun share their entire scenario: the
    same vehicles start in the same places and the same nodes are assigned the
    same attack classes. Merging two such campaigns and renumbering their
    stations does not make them independent, it makes one physical vehicle look
    like two, and a fold grouped by station then puts a vehicle's own twin on
    the other side of the split. That is verbatim train/test overlap wearing a
    different identifier, which is the exact failure the integrity gates exist
    to catch.
    """
    import hashlib
    out = {}
    for tag in tags:
        tx = pd.read_csv(f"{run_dir}/tx_{tag}.csv",
                         usecols=["claimedStationId", "attackId", "trueX", "trueY"],
                         on_bad_lines="skip").dropna()
        b = (tx[tx.attackId == 0].groupby("claimedStationId")[["trueX", "trueY"]]
             .first().round(2).sort_index())
        out[tag] = hashlib.sha1(b.to_csv().encode()).hexdigest()[:12]
    return out


def per_station_detection(df, feats, folds, trees, jobs):
    """Fraction of each station's windows flagged as misbehaving.

    Binary, attack against benign, because the question is whether the station
    is caught at all rather than whether its attack is named correctly. Naming
    is a harder problem and would confound the floor with class confusion
    between three attacks that differ only in magnitude.
    """
    X = (df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
         .to_numpy(dtype=np.float32))
    y = (df.label_attackId != 0).astype(int).values
    groups = df.label_txNodeId.values
    pred = np.zeros(len(df), dtype=int)
    sg = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=0)
    for tr, te in sg.split(X, y, groups):
        clf = RandomForestClassifier(n_estimators=trees, n_jobs=jobs,
                                     random_state=0)
        clf.fit(X[tr], y[tr])
        pred[te] = clf.predict(X[te])
    out = df[["key_seed", "key_claimedStationId", "label_attackId"]].copy()
    out["flagged"] = pred
    return (out.groupby(["key_seed", "key_claimedStationId", "label_attackId"])
            .flagged.agg(["mean", "size"]).reset_index()
            .rename(columns={"mean": "flag_rate", "size": "windows"}))


def curve(det, offsets, floor95, label, edges, min_stations,
          save_to=None, borrow=None, corpus_tag=None):
    det = det.merge(offsets[["key_seed", "key_claimedStationId", "offset"]],
                    how="left", on=["key_seed", "key_claimedStationId"])
    ben = det[det.label_attackId == 0]
    att = det[det.label_attackId.isin(LADDER)].dropna(subset=["offset"])

    print(f"\n{label}")
    print(f"  benign stations {len(ben)}, false flag rate "
          f"{ben.flag_rate.mean():.4f}")
    print(f"  constant-offset stations {len(att)} across "
          f"{sorted(int(c) for c in att.label_attackId.unique())}")
    print(f"\n  {'displacement':>18s} {'stations':>9s} {'windows':>9s} "
          f"{'flag rate':>10s} {'caught':>8s}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = att[(att.offset >= lo) & (att.offset < hi)]
        band = f"{lo:.0f} to {hi:.0f} m" if np.isfinite(hi) else f"over {lo:.0f} m"
        if len(b) < min_stations:
            print(f"  {band:>18s} {len(b):>9d} {'':>9s} "
                  f"{'too few stations':>19s}")
            continue
        # A station counts as caught if most of its windows are flagged. The
        # per-window rate is reported beside it because a station flagged in a
        # third of its windows is not undetected, it is intermittently detected,
        # and an operator watching over time would see it.
        caught = (b.flag_rate > 0.5).mean()
        print(f"  {band:>18s} {len(b):>9d} {int(b.windows.sum()):>9,} "
              f"{b.flag_rate.mean():>10.3f} {caught:>8.2f}")
    print(f"\n  benign positioning error on the same scale: median "
          f"{floor95[0]:.2f} m, 95th {floor95[1]:.2f} m, max {floor95[2]:.2f} m")

    keep = att[["offset", "flag_rate"]].copy()
    keep["arm"] = label
    keep["corpus"] = corpus_tag or "this run"
    keep["benign_flag_rate"] = ben.flag_rate.mean()
    if save_to:
        path = pathlib.Path(save_to)
        prev = pd.read_csv(path) if path.exists() else None
        pd.concat([prev, keep] if prev is not None else [keep],
                  ignore_index=True).to_csv(path, index=False)
        print(f"  station table appended to {path}")

    pooled_in = keep
    if borrow is not None and len(borrow):
        b = borrow[borrow.arm == label]
        if len(b):
            gap = abs(b.benign_flag_rate.mean() - ben.flag_rate.mean())
            print(f"\n  borrowing {len(b)} stations from "
                  f"{', '.join(sorted(b.corpus.unique()))} for the locate step")
            print(f"    benign false flag rate here {ben.flag_rate.mean():.4f}, "
                  f"there {b.benign_flag_rate.mean():.4f}, difference {gap:.4f}")
            if gap > 0.01:
                print("    REFUSED: the two runs are not at the same operating "
                      "point, so their\n    per station flag rates are not "
                      "comparable and pooling them would mix two\n    "
                      "thresholds. Locate on this run alone.")
            else:
                pooled_in = pd.concat([keep, b], ignore_index=True)
    locate(pooled_in, label)


def locate(att, label, n_boot=2000, seed=0):
    """Where the floor actually is, from every station rather than from bins.

    The banded table above throws each station into one of six buckets and then
    reports a proportion, so a band holding three stations reports a proportion
    of three and the floor can only be bracketed. Fitting detection against log
    displacement uses every station at the displacement it actually had, and the
    crossing point comes with an interval instead of a bracket.

    Logistic in log displacement, because detection is a threshold in a ratio
    rather than in metres: the relevant quantity is how far the lie exceeds the
    localisation error, and that error scales with range.
    """
    d = att.dropna(subset=["offset"])
    d = d[d.offset > 0]
    if len(d) < 12:
        print("  too few stations to locate the floor")
        return
    x = np.log(d.offset.values)
    y = (d.flag_rate.values > 0.5).astype(float)
    if y.sum() < 3 or (1 - y).sum() < 3:
        print("  detection is all one way across every station, "
              "so no crossing can be located")
        return

    def fit(xi, yi):
        # Two parameter logistic by Newton steps, which is enough for one
        # covariate and avoids a dependency the rest of the pipeline lacks.
        b = np.zeros(2)
        X = np.c_[np.ones(len(xi)), xi]
        for _ in range(60):
            p_ = 1.0 / (1.0 + np.exp(-np.clip(X @ b, -60, 60)))
            W = np.clip(p_ * (1 - p_), 1e-6, None)
            try:
                step = np.linalg.solve((X * W[:, None]).T @ X, X.T @ (yi - p_))
            except np.linalg.LinAlgError:
                return None
            b = b + step
            if np.max(np.abs(step)) < 1e-8:
                break
        return b

    b = fit(x, y)
    if b is None or b[1] <= 0:
        print("  the fit did not converge to an increasing curve, "
              "so no crossing is reported")
        return
    cross = float(np.exp(-b[0] / b[1]))

    rng = np.random.default_rng(seed)

    def bootstrap(index_sets):
        out = []
        for _ in range(n_boot):
            if index_sets is None:
                i = rng.integers(0, len(x), len(x))
            else:
                pick = rng.integers(0, len(index_sets), len(index_sets))
                i = np.concatenate([index_sets[k] for k in pick])
            bb = fit(x[i], y[i])
            if bb is not None and bb[1] > 0:
                out.append(np.exp(-bb[0] / bb[1]))
        return np.array([v for v in out if np.isfinite(v) and 0 < v < 1e4])

    boots = bootstrap(None)

    # Stations inside one seed share a scenario and a detector fold, so they
    # are not independent draws and resampling them one at a time understates
    # the interval. Resampling whole seeds respects that. With a handful of
    # seeds it is coarse, so both are reported and the wider one is the one to
    # quote.
    clusters = None
    if "key_seed" in d.columns and d.key_seed.nunique() > 2:
        pos = np.arange(len(d))
        clusters = [pos[(d.key_seed == s).values] for s in d.key_seed.unique()]
        clusters = [c for c in clusters if len(c)]

    print(f"\n  locating the floor from all {len(d)} stations rather than from bands")
    print(f"    50 percent detection at {cross:8.1f} m")
    if len(boots) > 100:
        lo, hi = np.percentile(boots, [2.5, 97.5])
        print(f"    95 percent interval    {lo:8.1f} to {hi:.1f} m "
              f"({len(boots)} of {n_boot} bootstrap fits converged)")
        print(f"    interval width         {hi - lo:8.1f} m")
        if clusters is not None:
            cb = bootstrap(clusters)
            if len(cb) > 100:
                clo, chi = np.percentile(cb, [2.5, 97.5])
                wider = "the clustered one" if (chi - clo) > (hi - lo) else \
                        "the station one"
                print(f"    resampling whole seeds instead of stations, "
                      f"{len(clusters)} seeds:")
                print(f"      95 percent interval  {clo:8.1f} to {chi:.1f} m, "
                      f"width {chi - clo:.1f} m")
                print(f"      quote {wider}, because stations inside a seed "
                      f"share a scenario and a fold")
    else:
        print(f"    too few bootstrap fits converged ({len(boots)}) for an "
              f"interval, so quote the point estimate as indicative only")
    print("    The crossing is where half the stations at that displacement are "
          "caught in most\n    of their windows. It is not the same quantity as "
          "a band's proportion and it\n    should be reported instead of one, "
          "not beside it.")
    # The estimator was checked against simulated data with a known crossing,
    # log-uniform displacements over 5 to 250 m and a slope of 4 in log space,
    # which it recovered inside its interval. At that slope the interval ran to
    # roughly 28 m at 30 stations and 23 m at 100. Those widths depend on the
    # slope and on how the displacements are spread, so they are a comment here
    # rather than a figure printed into the log as though it were measured.
    print("    Quote the crossing WITH its interval. The interval is wide "
          "unless there are\n    stations well below and well above the "
          "crossing as well as inside it, so check\n    the displacement "
          "spread before reading the point estimate as located.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--pooled", help="pooled table, to compare the two floors")
    ap.add_argument("--sample", type=int, default=400000)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--min-stations", type=int, default=3)
    ap.add_argument("--save-stations", default=None,
                    help="append this run's per station offsets and flag rates "
                         "to a csv, so a later run can borrow them")
    ap.add_argument("--locate-with", default=None,
                    help="a csv written by --save-stations on another corpus. "
                         "Its stations join the locate step only, never the "
                         "banded table, and only when both runs sit at the same "
                         "benign false flag rate. This is how the floor campaign "
                         "and the main corpus are combined: one supplies density "
                         "through the transition, the other the anchors at both "
                         "ends that fix the slope")
    ap.add_argument("--corpus-tag", default=None,
                    help="name recorded beside this run's stations")
    ap.add_argument("--extra-corpus", default=None,
                    help="a second corpus to TRAIN AND SCORE TOGETHER with the "
                         "first, rather than to borrow scored stations from. "
                         "One detector over both sets means the per station flag "
                         "rates are the same quantity by construction, which "
                         "--locate-with can only approximate. Use this when the "
                         "two corpora differ in attacker magnitude distribution, "
                         "because separately trained detectors then settle at "
                         "different operating points and their flag rates stop "
                         "being comparable")
    ap.add_argument("--extra-run-dir", default=None)
    ap.add_argument("--extra-tags", nargs="+", default=None)
    ap.add_argument("--extra-pooled", default=None,
                    help="the second corpus's pooled table, bumped and prefixed "
                         "the same way as its corpus so the pooled arm covers "
                         "both. Without it the pooled arm sees only the first "
                         "corpus, which is the arm the crossing actually lives "
                         "in, so the locate step would be run on the wrong set")
    ap.add_argument("--extra-prefix", default="x",
                    help="seed tags of the extra corpus are prefixed with this, "
                         "and its node identifiers are pushed clear of the "
                         "first corpus, so a grouped fold cannot put the same "
                         "physical station on both sides")
    a = ap.parse_args()
    borrow = pd.read_csv(a.locate_with) if a.locate_with else None

    offsets, benign_err = station_offsets(a.run_dir, a.tags)
    extra_offsets = None
    if a.extra_corpus:
        if not (a.extra_run_dir and a.extra_tags):
            raise SystemExit("--extra-corpus needs --extra-run-dir and --extra-tags")
        fa = scenario_fingerprint(a.run_dir, a.tags)
        fb = scenario_fingerprint(a.extra_run_dir, a.extra_tags)
        shared_scenes = set(fa.values()) & set(fb.values())
        if shared_scenes:
            raise SystemExit(
                f"REFUSED: the two corpora share {len(shared_scenes)} scenario "
                f"realisation(s).\nThe same benign vehicles start in the same "
                f"places in both, because the campaigns\nwere run with the same "
                f"rngRun values. Renumbering the stations would make one\n"
                f"physical vehicle look like two and put its twin on the other "
                f"side of a grouped\nfold, which is verbatim train/test overlap. "
                f"Either run the second campaign with\nrngRun values the first "
                f"does not use, or analyse it on its own.")
        extra_offsets, extra_benign = station_offsets(a.extra_run_dir, a.extra_tags)
        extra_offsets["key_seed"] = a.extra_prefix + "_" + extra_offsets.key_seed
        offsets = pd.concat([offsets, extra_offsets], ignore_index=True)
        benign_err = pd.concat([benign_err, extra_benign], ignore_index=True)
    floor = (benign_err.median(), benign_err.quantile(0.95), benign_err.max())

    # The benign 95th percentile is a bin edge, because it is the boundary the
    # whole analysis is about. On a corpus generated without a positioning
    # error model that value is exactly zero, which would make a zero-width
    # first bin, so the edges are deduplicated and the run says so plainly
    # rather than printing an empty row.
    if floor[1] <= 0.0:
        print("WARNING: benign positioning error is exactly zero in this "
              "corpus, so there is\nno noise floor to measure a detection "
              "floor against. The bands below are absolute\ndistances and the "
              "result understates how hard small displacements really are.")
    edges = sorted({0.0, float(floor[1]), 15.0, 30.0, 50.0, 80.0, 150.0})
    edges.append(np.inf)

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    if a.extra_corpus:
        ex = pd.read_pickle(a.extra_corpus)
        if "label_clean" in ex.columns:
            ex = ex[ex.label_clean == 1]
        # Push the second corpus clear of the first. build_corpus.py namespaces
        # by seed POSITION, so both corpora reuse the same identifiers and a
        # naive concatenation would put two different physical stations under
        # one id and quietly break every grouped fold.
        bump = int(max(df.key_rxNodeId.max(), df.label_txNodeId.max())) + 1_000_000
        ex["key_rxNodeId"] += bump
        ex["label_txNodeId"] += bump
        ex["key_seed"] = a.extra_prefix + "_" + ex.key_seed.astype(str)
        shared = [c for c in df.columns if c in ex.columns]
        assert not set(df.label_txNodeId) & set(ex.label_txNodeId), \
            "identifiers still collide after the bump"
        print(f"training over both corpora: {len(df):,} + {len(ex):,} windows, "
              f"{len(shared)} shared columns, second corpus seeds prefixed "
              f"'{a.extra_prefix}_'")
        df = pd.concat([df[shared], ex[shared]], ignore_index=True)
    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0)
    df = df.reset_index(drop=True)
    app = [c for c in df.columns if c.startswith("app_")]
    phy = [c for c in df.columns if c.startswith("phy_")]
    print(f"{len(df):,} windows, {df.label_txNodeId.nunique()} stations, "
          f"{len(app)} application and {len(phy)} radio features")

    for name, feats in [("application layer only", app),
                        ("radio layer only", phy),
                        ("fused", app + phy)]:
        det = per_station_detection(df, feats, a.folds, a.trees, a.jobs)
        curve(det, offsets, floor,
              f"single observer, {name}", edges, a.min_stations,
              a.save_stations, borrow, a.corpus_tag)

    if a.pooled:
        pl = pd.read_pickle(a.pooled)
        if a.extra_pooled:
            xp = pd.read_pickle(a.extra_pooled)
            bump = int(max(pl.label_txNodeId.max(), xp.label_txNodeId.max())) + 1_000_000
            xp = xp.copy()
            xp["label_txNodeId"] += bump
            xp["key_seed"] = a.extra_prefix + "_" + xp.key_seed.astype(str)
            shared = [c for c in pl.columns if c in xp.columns]
            assert not set(pl.label_txNodeId) & set(xp.label_txNodeId), \
                "pooled identifiers still collide after the bump"
            print(f"\npooled arm over both corpora: {len(pl):,} + {len(xp):,} units")
            pl = pd.concat([pl[shared], xp[shared]], ignore_index=True)
        cols = [c for c in pl.columns
                if c.startswith("pm_") or c.startswith("pool_")]
        det = per_station_detection(pl, cols, a.folds, a.trees, a.jobs)
        curve(det, offsets, floor,
              "pooled across receivers, all features", edges, a.min_stations,
              a.save_stations, borrow, a.corpus_tag)
        print("\nThe pooled rows are (station, window) units rather than "
              "(observer, station, window),\nso its window counts are smaller "
              "by the number of receivers per unit. The flag\nrates are "
              "comparable; the window counts are not.")


if __name__ == "__main__":
    main()
