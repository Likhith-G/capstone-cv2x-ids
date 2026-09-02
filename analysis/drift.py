#!/usr/bin/env python3
"""
Does the detector survive conditions it was not trained on?

The supervisor's brief names non-stationarity as the aim of the project: a
detector that stays reliable as traffic conditions change. Every result up to
this point is measured inside one distribution, with grouped splits that stop a
station appearing on both sides but do nothing about the scenario itself being
the same on both sides. A model can hold a grouped split perfectly and still
fail the first time density doubles.

Two protocols, both of which reuse corpora that already exist.

  --scenarios   leave one scenario out. Train on the union of every other
                corpus, test on the held-out one, in all permutations. The
                comparison that matters is against the in-distribution score on
                the same held-out corpus, because the gap between them IS the
                cost of the shift.

  --temporal    train on the early part of a run and test on the late part of
                held-out seeds, then walk a prequential curve forward in time.
                Density and channel load drift within a single run as vehicles
                enter and leave, so this is drift without changing scenario.

Both report the three feature blocks separately. A claim that cross-layer
fusion is worth its cost is much stronger if the fused block degrades least
under shift, and would be undermined if it degraded most, so the blocks are
carried through rather than collapsed to one number.
"""
import argparse
import pathlib
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score, matthews_corrcoef

NAMES = {0: "benign", 1: "pos_const_offset", 3: "pos_offset_random",
         4: "pos_replay", 5: "speed_falsify", 6: "sybil", 7: "dos_rate",
         8: "sps_manipulation", 11: "pos_small_offset", 12: "dos_low_rate"}


def load(spec, sample, seed=0):
    """Load one `name=path` corpus, filtered and subsampled.

    Subsampling is not optional on this machine. Two of these corpora together
    are larger than memory, and the comparison needs every scenario to carry
    the same weight anyway, which an unsampled union would not give.
    """
    name, _, path = spec.partition("=")
    if not path:
        name, path = pathlib.Path(spec).parent.name, spec
    df = pd.read_pickle(path)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    if sample and len(df) > sample:
        df = df.sample(n=sample, random_state=seed)
    df = df.reset_index(drop=True)
    df["scenario"] = name
    return name, df


def blocks_of(df):
    app = [c for c in df.columns if c.startswith("app_")]
    phy = [c for c in df.columns if c.startswith("phy_")]
    return {"app-only": app, "phy-only": phy, "fused": app + phy}


def fit_score(Xtr, ytr, Xte, yte, classes, trees, jobs):
    clf = RandomForestClassifier(n_estimators=trees, n_jobs=jobs, random_state=0)
    clf.fit(Xtr, ytr)
    p = clf.predict(Xte)
    return (f1_score(yte, p, average="macro"),
            matthews_corrcoef(yte, p),
            f1_score(yte, p, average=None, labels=classes, zero_division=0))


def clean(df, cols):
    return (df[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            .to_numpy(dtype=np.float32))


def cross_scenario(a):
    frames = {}
    for spec in a.scenarios:
        name, df = load(spec, a.sample)
        frames[name] = df
        print(f"{name:16s} {len(df):>9,} windows  "
              f"{df.label_txNodeId.nunique():>4} stations  "
              f"classes {sorted(df.label_attackId.unique())}")

    # Every scenario must be scored on the same label set or the macro average
    # is over different things in different arms and the comparison is void.
    # The intersection is used rather than the union because a class absent from
    # a training corpus cannot be predicted and would enter the macro average as
    # a guaranteed zero, which reads as drift and is not.
    sets = [set(df.label_attackId.unique()) for df in frames.values()]
    classes = sorted(set.intersection(*sets))
    dropped = sorted(set.union(*sets) - set(classes))
    print(f"\nclass set: {len(classes)} shared classes "
          f"{[NAMES.get(c, c) for c in classes]}")
    if dropped:
        print(f"dropped, not present in every scenario: "
              f"{[NAMES.get(c, c) for c in dropped]}")
    for k in frames:
        frames[k] = frames[k][frames[k].label_attackId.isin(classes)].reset_index(drop=True)

    blocks = blocks_of(next(iter(frames.values())))
    print(f"\nleave-one-scenario-out, paired. For each grouped fold of the "
          f"held-out corpus,\ntwo models are scored on the SAME test rows: one "
          f"trained on the rest of that\ncorpus, one trained on the other "
          f"scenarios. The training sets are drawn to the\nsame size, so the "
          f"only difference between the arms is where the rows came from.\n")
    print(f"{'held out':16s} {'block':10s} {'transfer F1':>18s} "
          f"{'in-dist F1':>18s} {'drop':>8s} {'transfer MCC':>18s} "
          f"{'in-dist MCC':>18s}")

    per_class_rows = []
    for held in frames:
        te = frames[held]
        union = pd.concat([frames[k] for k in frames if k != held],
                          ignore_index=True)
        yte = te.label_attackId.values
        gte = te.label_txNodeId.values
        yun = union.label_attackId.values
        sg = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=0)
        splits = list(sg.split(te, yte, gte))
        for bname, cols in blocks.items():
            t0 = time.time()
            Xte, Xun = clean(te, cols), clean(union, cols)
            f1_t, f1_i, mcc_t, mcc_i, pc_t, pc_i = [], [], [], [], [], []
            for k, (itr, ite) in enumerate(splits):
                rng = np.random.default_rng(k)
                # Matched training size. Without this the transfer arm trains on
                # the whole of every other corpus while the in-distribution arm
                # trains on a fraction of one, and the difference between them
                # reads as drift when it is mostly sample size.
                n = min(len(itr), len(Xun))
                pick = rng.choice(len(Xun), n, replace=False)
                a1 = fit_score(Xun[pick], yun[pick], Xte[ite], yte[ite],
                               classes, a.trees, a.jobs)
                a2 = fit_score(Xte[itr], yte[itr], Xte[ite], yte[ite],
                               classes, a.trees, a.jobs)
                f1_t.append(a1[0]); mcc_t.append(a1[1]); pc_t.append(a1[2])
                f1_i.append(a2[0]); mcc_i.append(a2[1]); pc_i.append(a2[2])
            print(f"{held:16s} {bname:10s} "
                  f"{np.mean(f1_t):9.4f} +/- {np.std(f1_t):.4f} "
                  f"{np.mean(f1_i):9.4f} +/- {np.std(f1_i):.4f} "
                  f"{np.mean(f1_t) - np.mean(f1_i):+8.4f} "
                  f"{np.mean(mcc_t):9.4f} +/- {np.std(mcc_t):.4f} "
                  f"{np.mean(mcc_i):9.4f} +/- {np.std(mcc_i):.4f}"
                  f"   ({time.time() - t0:.0f}s, {n:,} training rows per arm)",
                  flush=True)
            per_class_rows.append((held, bname, np.mean(pc_t, axis=0),
                                   np.mean(pc_i, axis=0)))

    print(f"\nper class, transfer against in-distribution, F1, averaged over "
          f"{a.folds} folds")
    print(f"{'held out':16s} {'block':10s} " +
          "  ".join(f"{NAMES.get(c, c)[:14]:>14s}" for c in classes))
    for held, bname, pc_t, pc_i in per_class_rows:
        print(f"{held:16s} {bname:10s} " +
              "  ".join(f"{x:6.3f}/{i:<7.3f}" for x, i in zip(pc_t, pc_i)))
    print("\nEach cell is transfer / in-distribution on the same held-out rows.")


def temporal(a):
    name, df = load(a.temporal, a.sample)
    classes = sorted(df.label_attackId.unique())
    blocks = blocks_of(df)
    seeds = sorted(df.key_seed.unique())
    t_lo, t_hi = df.key_window.min(), df.key_window.max()
    cut = t_lo + (t_hi - t_lo) * a.cut
    print(f"{name}: {len(df):,} windows, seeds {seeds}, "
          f"time {t_lo:.0f} to {t_hi:.0f} s, split at {cut:.0f} s")

    # Seeds are held out as well as time. Splitting on time alone leaves the
    # same stations on both sides at different moments, which measures how well
    # a model remembers a vehicle rather than how well it survives a later
    # period.
    if len(seeds) >= 2:
        n_hold = max(1, len(seeds) // 3)
        te_seeds = seeds[-n_hold:]
        tr_seeds = [s for s in seeds if s not in te_seeds]
    else:
        # One seed is not enough to hold any out, so the split degrades to time
        # alone. Say so, because a time-only split leaves the same stations on
        # both sides and measures partly how well a model remembers a vehicle.
        print("only one seed present: splitting on time alone, so the same "
              "stations appear\non both sides and the result is an upper bound")
        te_seeds, tr_seeds = seeds, seeds
    tr = df[(df.key_seed.isin(tr_seeds)) & (df.key_window < cut)]
    te = df[(df.key_seed.isin(te_seeds)) & (df.key_window >= cut)]
    same = df[(df.key_seed.isin(te_seeds)) & (df.key_window < cut)]
    print(f"train {len(tr):,} windows, seeds {tr_seeds}, before {cut:.0f} s")
    print(f"test  {len(te):,} windows, seeds {te_seeds}, from {cut:.0f} s")
    print(f"control {len(same):,} windows, the SAME held-out seeds BEFORE the "
          f"cut, which isolates the time shift from the seed shift\n")

    # With one seed the control rows ARE the training rows, so the column is a
    # training fit and cannot be read as an in-distribution reference. Label it
    # for what it is rather than letting a 0.99 be quoted as a control.
    degenerate = set(tr_seeds) == set(te_seeds)
    ctrl = "TRAIN FIT" if degenerate else "early F1"
    if degenerate:
        print("the control column below is the TRAINING data refit, not a "
              "control: with one\nseed there are no held-out stations to score "
              "before the cut\n")
    print(f"{'block':10s} {'late F1':>9s} {ctrl:>9s} {'time cost':>10s} "
          f"{'late MCC':>9s} {'early MCC':>10s}")
    for bname, cols in blocks.items():
        Xtr, ytr = clean(tr, cols), tr.label_attackId.values
        f1_l, mcc_l, _ = fit_score(Xtr, ytr, clean(te, cols),
                                   te.label_attackId.values, classes,
                                   a.trees, a.jobs)
        f1_e, mcc_e, _ = fit_score(Xtr, ytr, clean(same, cols),
                                   same.label_attackId.values, classes,
                                   a.trees, a.jobs)
        print(f"{bname:10s} {f1_l:9.4f} {f1_e:9.4f} {f1_l - f1_e:+10.4f} "
              f"{mcc_l:9.4f} {mcc_e:10.4f}", flush=True)

    # Prequential curve on the fused block. Train once on the early period,
    # then score each later time bin in turn without retraining. A model that
    # is going stale shows a downward trend here; a flat line says the drift
    # inside one run is not the drift that matters.
    cols = blocks["fused"]
    Xtr, ytr = clean(tr, cols), tr.label_attackId.values
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs, random_state=0)
    clf.fit(Xtr, ytr)
    ho = df[df.key_seed.isin(te_seeds)]
    edges = np.linspace(t_lo, t_hi, a.bins + 1)
    print(f"\nprequential, fused block, trained once on the early period and "
          f"never updated")
    print(f"{'window':>16s} {'rows':>9s} {'macro F1':>9s} {'MCC':>9s}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = ho[(ho.key_window >= lo) & (ho.key_window < hi)]
        if len(b) < 200 or b.label_attackId.nunique() < 2:
            print(f"{f'{lo:.0f}-{hi:.0f}s':>16s} {len(b):>9,}   too few rows or "
                  f"classes to score")
            continue
        p = clf.predict(clean(b, cols))
        yb = b.label_attackId.values
        print(f"{f'{lo:.0f}-{hi:.0f}s':>16s} {len(b):>9,} "
              f"{f1_score(yb, p, average='macro'):9.4f} "
              f"{matthews_corrcoef(yb, p):9.4f}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", nargs="+",
                    help="corpora as name=path, two or more")
    ap.add_argument("--temporal", help="one corpus path, for the time split")
    ap.add_argument("--sample", type=int, default=150000,
                    help="rows kept per corpus; every scenario gets the same "
                         "budget so none dominates the union")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--cut", type=float, default=0.5,
                    help="fraction of the run used for training, temporal mode")
    ap.add_argument("--bins", type=int, default=6)
    a = ap.parse_args()
    if a.scenarios:
        cross_scenario(a)
    elif a.temporal:
        temporal(a)
    else:
        ap.error("give --scenarios or --temporal")


if __name__ == "__main__":
    main()
