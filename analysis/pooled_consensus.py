#!/usr/bin/env python3
"""
Does pooling observations across receivers resolve position falsification?

The build log states the problem and predicts the answer. A constant position
offset is perfectly self-consistent at the application layer, and at a SINGLE
receiver it is buried in the channel: a 100 m error at 300 m range moves free
space received power by 2.5 dB against a benign shadowing spread of 4.2 dB.
Per-link shadowing is persistent, so one receiver cannot tell a position lie
from a fade. Measured fused F1 for class 1 is 0.292.

Several receivers can, and the reason is physical rather than statistical.
Shadowing is INDEPENDENT per link. A position lie is COMMON MODE: one false
position has to explain every receiver's measured power at once, and it cannot,
because the geometry it implies is wrong in a different direction for each
receiver. So the discriminator is cross-receiver agreement, and it is exactly
the quantity a single receiver does not have.

Everything used here is legitimately observable by a cooperating receiver:
its OWN position, the position the message CLAIMS, and the sidelink RSRP it
measured. No receiver reads the transmitter's true position. True positions are
loaded only by --validate, only to report how accurate the localisation is, and
they never enter the feature matrix.

Three arms on an identical set of (seed, claimed station, window) triples, the
same grouped folds and the same row count, so the comparison is paired:

  single           one randomly chosen observer's 50 features. The baseline.
  pooled-mean      those 50 features averaged across observers. The CONTROL,
                   present so that any gain from the targeted arm cannot be
                   explained by generic averaging.
  pooled-consensus pooled-mean plus the cross-observer consensus block.

The consensus block needs no propagation calibration. Both the intercept and
the path loss exponent are fitted per triple, so a global power offset or a
wrong exponent cancels, and what is left is whether ONE claimed position can
explain every observer's power under ANY single consistent propagation law.
"""
import argparse
import gc

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import wilcoxon as _wilcoxon
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score, matthews_corrcoef

def wilcoxon(a, b):
    """Wilcoxon that reports p = 1.0 when the two arms are identical rather
    than raising. Two arms scoring 0.000 on a class every fold is a real and
    reportable outcome, not an error."""
    d = np.asarray(a, float) - np.asarray(b, float)
    if not np.any(d):
        return 1.0
    return float(_wilcoxon(a, b).pvalue)


# The joint fit has four free parameters (x, y, intercept, exponent), so five
# receivers is the identifiability floor, not a tuning choice. At four the fit
# is exactly determined and its residual is identically zero; at two the
# claimed-position regression fits two parameters to two points and returns
# rmse 0 and R-squared 1 for every unit, attacker or not. Below five the
# consensus block is not a weak signal, it is undefined, and a sweep that
# reports those rows is reporting an artefact.
MIN_OBS = 5
FIT_CAP = 48         # observers used in the nonlinear fit, for runtime


# ---------------------------------------------------------------- geometry ---
def observer_geometry(run_dir, tags, window_ms=1000.0):
    """Per (seed, observer, window) observer position, and per (seed, claimed
    station, window) the position that station claimed. Both are things a
    receiver has: where it is, and what the message said."""
    obs, claim = [], []
    for i, tag in enumerate(tags):
        off = (i + 1) * 100000
        rx = pd.read_csv(f"{run_dir}/rx_app_{tag}.csv",
                         usecols=["rxTimeMs", "rxNodeId", "claimedStationId",
                                  "claimedX", "claimedY", "rxX", "rxY"],
                         on_bad_lines="skip")
        # A run that is interrupted leaves a partial final row in every table.
        rx = rx.dropna()
        rx["key_window"] = (rx.rxTimeMs // window_ms).astype(int)
        o = (rx.groupby(["rxNodeId", "key_window"])[["rxX", "rxY"]].mean()
               .reset_index().rename(columns={"rxNodeId": "key_rxNodeId"}))
        o["key_rxNodeId"] += off
        o["key_seed"] = tag
        obs.append(o)
        c = (rx.groupby(["claimedStationId", "key_window"])[["claimedX", "claimedY"]]
               .mean().reset_index()
               .rename(columns={"claimedStationId": "key_claimedStationId"}))
        c["key_seed"] = tag
        claim.append(c)
    return pd.concat(obs, ignore_index=True), pd.concat(claim, ignore_index=True)


def true_positions(run_dir, tags, window_ms=1000.0):
    """VALIDATION ONLY. Never merged into the feature matrix."""
    out = []
    for i, tag in enumerate(tags):
        tx = pd.read_csv(f"{run_dir}/tx_{tag}.csv",
                         usecols=["txTimeMs", "claimedStationId", "trueX", "trueY"],
                         on_bad_lines="skip")
        tx = tx.dropna()
        tx["key_window"] = (tx.txTimeMs // window_ms).astype(int)
        t = (tx.groupby(["claimedStationId", "key_window"])[["trueX", "trueY"]]
               .mean().reset_index()
               .rename(columns={"claimedStationId": "key_claimedStationId"}))
        t["key_seed"] = tag
        out.append(t)
    return pd.concat(out, ignore_index=True)


# --------------------------------------------------------------- consensus ---
def _resid(p, ox, oy, rsrp):
    """rsrp_i = A - 10 n log10(dist_i). p = (x, y, A, n)."""
    d = np.maximum(np.hypot(ox - p[0], oy - p[1]), 1.0)
    return rsrp - (p[2] - 10.0 * p[3] * np.log10(d))


def consensus_block(ox, oy, rsrp, cx, cy, rng):
    """Cross-observer consensus statistics for one triple.

    Returns the localisation estimate too, so --validate can score it.
    """
    n = len(rsrp)
    if n > FIT_CAP:                       # cap the nonlinear fit for runtime
        sel = rng.choice(n, FIT_CAP, replace=False)
        fx, fy, fr = ox[sel], oy[sel], rsrp[sel]
    else:
        fx, fy, fr = ox, oy, rsrp

    # Claimed-position plausibility. Fit intercept and exponent by ordinary
    # least squares GIVEN the claim, so the claim gets the most favourable
    # propagation law available to it. What is left is geometry it cannot fix.
    dc = np.maximum(np.hypot(ox - cx, oy - cy), 1.0)
    L = 10.0 * np.log10(dc)
    A_ = np.c_[np.ones(n), -L]
    beta, *_ = np.linalg.lstsq(A_, rsrp, rcond=None)
    r_claim = rsrp - A_ @ beta
    claim_rmse = float(np.sqrt(np.mean(r_claim ** 2)))
    ss_tot = float(np.sum((rsrp - rsrp.mean()) ** 2))
    claim_r2 = 1.0 - float(np.sum(r_claim ** 2)) / ss_tot if ss_tot > 0 else 0.0

    # Free-position fit: the best any single position can do on the same data.
    i0 = int(np.argmax(fr))
    p0 = np.array([fx[i0], fy[i0], float(np.max(fr)) + 20.0, 2.5])
    try:
        sol = least_squares(_resid, p0, args=(fx, fy, fr), method="lm", max_nfev=400)
        px, py = float(sol.x[0]), float(sol.x[1])
        expo = float(sol.x[3])
        free_rmse = float(np.sqrt(np.mean(sol.fun ** 2)))
    except Exception:
        px, py, expo, free_rmse = np.nan, np.nan, np.nan, np.nan

    # Structure in the claim's residual: a lie makes near observers wrong in
    # one direction and far ones in the other, so the residual correlates with
    # range. Shadowing does not.
    corr = float(np.corrcoef(L, r_claim)[0, 1]) if n > 2 and L.std() > 0 else 0.0

    return {
        "pool_n_obs": float(n),
        "pool_obs_span": float(ox.max() - ox.min()),
        "pool_claim_rmse": claim_rmse,
        "pool_claim_r2": claim_r2,
        "pool_claim_exp": float(beta[1]),
        "pool_claim_resid_corr": corr if np.isfinite(corr) else 0.0,
        "pool_free_rmse": free_rmse,
        "pool_rmse_ratio": (claim_rmse / free_rmse) if free_rmse and free_rmse > 0 else 1.0,
        "pool_mlat_err": float(np.hypot(px - cx, py - cy)),
        "pool_mlat_dx": float(px - cx),
        "pool_mlat_exp": expo,
    }, (px, py)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", help="corpus pickle carrying key_window and key_claimedStationId")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=4)
    ap.add_argument("--trees", type=int, default=300)
    ap.add_argument("--sweep", type=int, nargs="+", default=None,
                    help="sweep the number of cooperating receivers, e.g. "
                         "2 3 5 10 20 40 0 where 0 means all of them")
    ap.add_argument("--max-obs", type=int, default=0,
                    help="pool over at most this many receivers per triple, "
                         "0 for all of them")
    ap.add_argument("--class-weight", default="balanced",
                    choices=["balanced", "none"],
                    help="section 3's benchmark uses an UNWEIGHTED forest, so "
                         "run this both ways before quoting a class 1 number "
                         "beside it")
    ap.add_argument("--jobs", type=int, default=4,
                    help="forest workers; each holds its own trees, so -1 on a "
                         "small machine is how this gets killed")
    ap.add_argument("--obs-cap", type=int, default=250000,
                    help="cap on single-observer training rows per fold, for runtime")
    ap.add_argument("--validate", action="store_true",
                    help="score the localisation against true positions")
    ap.add_argument("--out", default=None, help="write the pooled table here")
    a = ap.parse_args()
    if a.class_weight == "none":
        a.class_weight = None
    rng = np.random.default_rng(0)

    df = pd.read_pickle(a.corpus)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1].reset_index(drop=True)
    feats = [c for c in df.columns if c.startswith(("app_", "phy_"))]
    obs, claim = observer_geometry(a.run_dir, a.tags)
    df = df.merge(obs, how="inner", on=["key_seed", "key_rxNodeId", "key_window"])
    df = df.merge(claim, how="inner", on=["key_seed", "key_claimedStationId", "key_window"])
    print(f"{len(df)} observations after attaching geometry")

    key = ["key_seed", "key_claimedStationId", "key_window"]
    df = df.sort_values(key).reset_index(drop=True)

    # ---- build the arms on one identical set of triples --------------------
    def build(k_obs, seed=0):
        """Pool each triple over at most k_obs receivers. The SET OF TRIPLES is
        the same whatever k_obs is, so the sweep changes how many receivers
        cooperate and nothing else."""
        r = np.random.default_rng(seed)
        rs, rm, rc, mt = [], [], [], []
        for kk, g in df.groupby(key, sort=False):
            v = g[g.phy_rsrp_mean.notna()]
            if len(v) < MIN_OBS:
                continue
            if k_obs and len(v) > k_obs:
                v = v.iloc[r.choice(len(v), k_obs, replace=False)]
            # Every arm sees the SAME receiver set: the ones that measured a
            # sidelink RSRP for this station in this window. The single arm
            # picks one of them at random, the pooled arms use all of them.
            cx, cy = float(v.claimedX.iloc[0]), float(v.claimedY.iloc[0])
            cb, (px, py) = consensus_block(v.rxX.values, v.rxY.values,
                                           v.phy_rsrp_mean.values, cx, cy, r)
            pick = v.iloc[r.integers(len(v))]
            rs.append(pick[feats].values)
            rm.append(v[feats].mean().values)
            rc.append(cb)
            mt.append((kk[0], kk[1], kk[2], int(pick.label_attackId),
                       int(pick.label_txNodeId), cx, cy, px, py))
        return rs, rm, rc, mt

    rows_single, rows_mean, rows_cons, meta = build(a.max_obs)

    if a.sweep:
        # How many cooperating receivers does this actually need? A real
        # deployment does not get 87. The set of triples is fixed, so the only
        # thing changing is how many receivers are allowed to contribute.
        print("\nreceivers per station-window, against detection\n")
        print(f"{'receivers':>10s}  {'macro F1':>16s}  {'class 1':>16s}  "
              f"{'class 4':>16s}  {'MCC multiclass':>16s}")
        for k_obs in a.sweep:
            if k_obs and k_obs < MIN_OBS:
                print(f"{k_obs:>10}  skipped, below the {MIN_OBS} receiver "
                      f"identifiability floor")
                continue
            rs, rm, rc, mt = build(k_obs, seed=1)
            Mk = pd.DataFrame(mt, columns=["key_seed", "key_claimedStationId",
                                           "key_window", "label_attackId",
                                           "label_txNodeId", "claimedX",
                                           "claimedY", "estX", "estY"])
            Xk = pd.concat([pd.DataFrame(rm, columns=feats),
                            pd.DataFrame(rc)], axis=1)
            Xk = (Xk.replace([np.inf, -np.inf], np.nan).fillna(0.0)
                  .to_numpy(dtype=np.float32))
            yk = Mk.label_attackId.values
            gk = Mk.label_txNodeId.values
            mac, c1, c4, mcc = [], [], [], []
            for rep in range(a.repeats):
                sg = StratifiedGroupKFold(n_splits=a.folds, shuffle=True,
                                          random_state=rep)
                for tr, te in sg.split(Mk, yk, gk):
                    cl = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                                random_state=0,
                                                class_weight=a.class_weight)
                    cl.fit(Xk[tr], yk[tr])
                    pr = cl.predict(Xk[te])
                    mac.append(f1_score(yk[te], pr, average="macro"))
                    mcc.append(matthews_corrcoef(yk[te], pr))
                    lab = sorted(np.unique(yk))
                    f1c = dict(zip(lab, f1_score(yk[te], pr, average=None,
                                                 labels=lab, zero_division=0)))
                    c1.append(f1c.get(1, 0.0))
                    c4.append(f1c.get(4, 0.0))
            print(f"{k_obs if k_obs else 'all':>10}  "
                  f"{np.mean(mac):.4f} +/- {np.std(mac):.4f}  "
                  f"{np.mean(c1):.4f} +/- {np.std(c1):.4f}  "
                  f"{np.mean(c4):.4f} +/- {np.std(c4):.4f}  "
                  f"{np.mean(mcc):.4f} +/- {np.std(mcc):.4f}")
        return

    M = pd.DataFrame(meta, columns=["key_seed", "key_claimedStationId", "key_window",
                                    "label_attackId", "label_txNodeId",
                                    "claimedX", "claimedY", "estX", "estY"])
    S = pd.DataFrame(rows_single, columns=feats)
    P = pd.DataFrame(rows_mean, columns=feats)
    C = pd.DataFrame(rows_cons)
    print(f"{len(M)} pooled units, {M.label_txNodeId.nunique()} stations, "
          f"{M.label_attackId.nunique()} classes")
    print(f"observers per unit: median {C.pool_n_obs.median():.0f}, "
          f"min {C.pool_n_obs.min():.0f}, max {C.pool_n_obs.max():.0f}")

    if a.validate:
        tp = true_positions(a.run_dir, a.tags)
        V = M.merge(tp, how="left", on=["key_seed", "key_claimedStationId", "key_window"])
        err_true = np.hypot(V.estX - V.trueX, V.estY - V.trueY)
        err_claim = np.hypot(V.estX - V.claimedX, V.estY - V.claimedY)
        off_true = np.hypot(V.claimedX - V.trueX, V.claimedY - V.trueY)
        ben = V.label_attackId == 0
        print("\nlocalisation check (validation only, never a feature)")
        print(f"  benign: estimate to TRUE position     "
              f"median {err_true[ben].median():7.1f} m")
        print(f"  benign: estimate to CLAIMED position  "
              f"median {err_claim[ben].median():7.1f} m")
        for cls in sorted(V.label_attackId.unique()):
            if cls == 0:
                continue
            m = V.label_attackId == cls
            print(f"  class {cls}: true offset median {off_true[m].median():7.1f} m,"
                  f"  estimate to claim {err_claim[m].median():7.1f} m,"
                  f"  estimate to true {err_true[m].median():7.1f} m")

    arms = {"single": S, "pooled-mean": P,
            "consensus-only": C,
            "pooled-consensus": pd.concat([P, C], axis=1)}
    if a.out:
        pd.concat([M, P.add_prefix("pm_"), C], axis=1).to_pickle(a.out)
        print(f"\npooled table -> {a.out}")

    # ---- paired evaluation -------------------------------------------------
    # The single-observer arm is trained on EVERY observation from the training
    # stations, not on the one row per triple the pooled arms get. Giving it
    # the 7,647 pooled rows instead would hand pooling an eighty-fold training
    # set advantage and the comparison would measure sample size. A deployed
    # single-observer detector has the full observation stream, so it gets it.
    #
    # `vote` is the arm that decides whether the gain is really cross-observer
    # geometry. It runs the SAME single-observer model at every receiver and
    # takes a majority vote over the triple, which is decision-level pooling:
    # more evidence, no shared raw measurements, no consensus statistic. If
    # `vote` closes the gap then pooling is just averaging out noise. If it
    # does not, the gain is the geometry that only joint inference can see.
    y = M.label_attackId.values
    groups = M.label_txNodeId.values
    classes = sorted(np.unique(y))
    # float32 and an explicit del: the observation matrix is 615,460 x 50 and
    # this machine has 8 GB with a simulation usually running beside it. In
    # float64 with pandas holding a second copy, the fold loop was reaching the
    # memory limit and being killed with no traceback, which reads exactly like
    # a silent success when the output is buffered.
    Xobs = (df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            .to_numpy(dtype=np.float32))
    yobs = df.label_attackId.to_numpy()
    gobs = df.label_txNodeId.to_numpy()
    M["_tri"] = np.arange(len(M))
    obs_tri = (df[key].merge(M[key + ["_tri"]], how="left", on=key)
               ._tri.fillna(-1).astype(int).to_numpy())
    M.drop(columns="_tri", inplace=True)
    del df
    gc.collect()

    names = ["single", "vote", "vote-soft", "pooled-mean", "consensus-only",
             "pooled-consensus"]
    scores = {k: [] for k in names}
    # MCC beside macro F1, because the proposal names it the primary aggregate
    # metric. This is the multiclass generalisation, not the binary MCC that
    # evaluate_deployment.py reports per threshold, and the two are different
    # quantities that must not be compared.
    mccs = {k: [] for k in names}
    per_class = {k: {c: [] for c in classes} for k in names}
    obs_scores = []
    obs_mccs = []
    obs_per_class = {c: [] for c in classes}
    importances = []
    import time
    t0 = time.time()
    done = 0
    for rep in range(a.repeats):
        sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=rep)
        for tr, te in sgkf.split(M, y, groups):
            done += 1
            print(f"  fold {done}/{a.folds * a.repeats} "
                  f"({time.time() - t0:.0f}s elapsed)", flush=True)
            te_stations = set(groups[te])
            tr_stations = set(groups[tr])
            m_tr = np.isin(gobs, list(tr_stations))
            m_te = np.isin(gobs, list(te_stations))
            idx_tr = np.flatnonzero(m_tr)
            if a.obs_cap and len(idx_tr) > a.obs_cap:
                idx_tr = rng.choice(idx_tr, a.obs_cap, replace=False)
            clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                         random_state=0, class_weight=a.class_weight)
            clf.fit(Xobs[idx_tr], yobs[idx_tr])
            idx_te = np.flatnonzero(m_te)
            proba = clf.predict_proba(Xobs[idx_te])
            cls_of_col = clf.classes_
            pr_obs = cls_of_col[proba.argmax(1)]
            obs_scores.append(f1_score(yobs[idx_te], pr_obs, average="macro"))
            obs_mccs.append(matthews_corrcoef(yobs[idx_te], pr_obs))
            for c, sc in zip(classes, f1_score(yobs[idx_te], pr_obs, average=None,
                                               labels=classes, zero_division=0)):
                obs_per_class[c].append(sc)

            # Three ways to use the same single-receiver model on one triple.
            #   single      one receiver decides, chosen at random so that the
            #               arbitrary row order inside a triple cannot bias it.
            #   vote        every receiver decides and they take a majority.
            #   vote-soft   every receiver's class probabilities are averaged
            #               and the argmax taken. This is the STRONGEST
            #               decision-level fusion available without sharing raw
            #               measurements, and it is here so that the pooled
            #               arms are not being compared against a weak strawman:
            #               hard voting cannot return a class the base detector
            #               rarely names, soft voting can.
            tri_te = obs_tri[idx_te]
            bucket = {}
            for j, t in enumerate(tri_te):
                if t >= 0:
                    bucket.setdefault(t, []).append(j)
            order = [t for t in te if t in bucket]
            yt = y[order]
            pr_single, pr_vote, pr_soft = [], [], []
            for t in order:
                js = bucket[t]
                pr_single.append(pr_obs[js[rng.integers(len(js))]])
                pr_vote.append(np.bincount(pr_obs[js]).argmax())
                pr_soft.append(cls_of_col[proba[js].mean(0).argmax()])
            pr_single = np.array(pr_single)
            pr_vote = np.array(pr_vote)
            pr_soft = np.array(pr_soft)
            for nm, pr in (("single", pr_single), ("vote", pr_vote),
                           ("vote-soft", pr_soft)):
                scores[nm].append(f1_score(yt, pr, average="macro"))
                mccs[nm].append(matthews_corrcoef(yt, pr))
                for c, sc in zip(classes, f1_score(yt, pr, average=None,
                                                   labels=classes, zero_division=0)):
                    per_class[nm][c].append(sc)

            for name in ("pooled-mean", "consensus-only", "pooled-consensus"):
                X = arms[name]
                Xc = (X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
                      .to_numpy(dtype=np.float32))
                cl = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                            random_state=0, class_weight=a.class_weight)
                cl.fit(Xc[tr], y[tr])
                pr = cl.predict(Xc[te])
                scores[name].append(f1_score(y[te], pr, average="macro"))
                mccs[name].append(matthews_corrcoef(y[te], pr))
                for c, sc in zip(classes, f1_score(y[te], pr, average=None,
                                                   labels=classes, zero_division=0)):
                    per_class[name][c].append(sc)
                if name == "pooled-consensus":
                    importances.append(pd.Series(cl.feature_importances_,
                                                 index=X.columns))

    n_meas = a.folds * a.repeats
    print(f"\nsingle-observer model scored per OBSERVATION (the deployed unit "
          f"today): macro F1 {np.mean(obs_scores):.4f}, "
          f"MCC multiclass {np.mean(obs_mccs):.4f}")
    print("  per class, for comparison with the section 3 benchmark: " +
          "  ".join(f"{c}:{np.mean(v):.3f}" for c, v in obs_per_class.items()))
    print(f"\nmacro F1 per TRIPLE over {n_meas} paired grouped folds "
          f"({a.repeats} repeats x {a.folds} folds)\n")
    print(f"{'arm':18s} {'macro F1':>16s}  {'vs single':>10s}  {'Wilcoxon p':>10s}"
          f"  {'MCC multiclass':>18s}")
    base = np.array(scores["single"])
    mbase = np.array(mccs["single"])
    for name in names:
        v = np.array(scores[name])
        m = np.array(mccs[name])
        line = f"{name:18s} {v.mean():.4f} +/- {v.std():.4f}"
        # The MCC column is APPENDED, never inserted. verify_results.py pins
        # substrings that run from the arm name through the delta, so anything
        # placed before the delta silently breaks those checks.
        tail = f"  {m.mean():.4f} +/- {m.std():.4f}"
        if name == "single":
            print(f"{line}{' ' * 24}{tail}")
        else:
            print(f"{line}  {v.mean() - base.mean():+10.4f}  "
                  f"{wilcoxon(v, base):10.4g}{tail}")
    print(f"MCC against single, same paired folds: " +
          "  ".join(f"{n}:{np.mean(mccs[n]) - mbase.mean():+.4f}"
                    for n in names if n != "single"))

    print(f"\nper class F1\n{'class':>6s}  " +
          "  ".join(f"{k:>16s}" for k in names))
    for c in classes:
        print(f"{c:>6d}  " +
              "  ".join(f"{np.mean(per_class[k][c]):16.3f}" for k in names))

    for c in classes:
        if c == 0:
            continue
        b = np.array(per_class["single"][c])
        v = np.array(per_class["pooled-consensus"][c])
        if abs(v.mean() - b.mean()) > 0.05:
            print(f"\nclass {c}: single {b.mean():.3f} -> consensus {v.mean():.3f} "
                  f"({v.mean() - b.mean():+.3f}), p={wilcoxon(v, b):.4g}, "
                  f"vote {np.mean(per_class['vote'][c]):.3f}, "
                  f"vote-soft {np.mean(per_class['vote-soft'][c]):.3f}")

    if importances:
        imp = pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)
        print("\nten most important features in the consensus model")
        for k, v in imp.head(10).items():
            print(f"  {k:28s} {v:.4f}")
        pool_share = imp[[i for i in imp.index if i.startswith("pool_")]].sum()
        n_pool = sum(1 for i in imp.index if i.startswith("pool_"))
        print(f"  consensus block: {n_pool} of {len(imp)} features, "
              f"{pool_share:.3f} of total importance "
              f"(proportional share would be {n_pool / len(imp):.3f})")
        print("  consensus features by rank")
        ranks = {k: i + 1 for i, k in enumerate(imp.index)}
        for k in [i for i in imp.index if i.startswith("pool_")]:
            print(f"    rank {ranks[k]:3d}  {k:26s} {imp[k]:.4f}")


if __name__ == "__main__":
    main()
