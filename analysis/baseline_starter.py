#!/usr/bin/env python3
"""
Starting point for anyone training a model on the released bundle.

This exists so nobody has to rebuild the evaluation protocol from prose. Every
way of getting this wrong produces a number that looks BETTER than the truth,
never worse, so a protocol assembled by hand tends to fail silently and in the
flattering direction. Run this once unmodified to see the baseline, then replace
`build_model()` with whatever you are actually testing and change nothing else.

Two protocols, and they answer different questions:

    --protocol cv       grouped cross-validation, which is how the published
                        0.5145 was measured. Use this if you want your number to
                        sit beside the published ones.

    --protocol frozen   a single pass over the frozen partition shipped in the
                        bundle. Faster, fine for iterating, and reads a little
                        high because it scores once rather than averaging folds.

Usage:

    python3 baseline_starter.py path/to/release
    python3 baseline_starter.py path/to/release --protocol frozen
    python3 baseline_starter.py path/to/release --scenario highway_dense
"""
import argparse
import glob
import pathlib
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, matthews_corrcoef
from sklearn.model_selection import StratifiedGroupKFold

# The three constant-offset classes are one mechanism at three magnitudes and
# they are where the project's central claim lives. A model that lifts the
# aggregate and leaves these alone has not touched the interesting part.
POSITION_CLASSES = {11: "pos_small_offset, 1 to 25 m",
                    13: "pos_medium_offset, 47 to 83 m",
                    1:  "pos_const_offset, 22 to 233 m"}
BEST_OF_FOUR = {11: 0.010, 13: 0.052, 1: 0.167}

# Semi-persistent scheduling manipulation has no signature in this simulator:
# Mode 2 grants are data driven, so the attacker cannot hoard the channel. It
# scores zero in every block on every corpus. Reported, never quietly dropped.
INERT_CLASS = 8

PUBLISHED = {"macro_f1": 0.5145, "mcc": 0.6635, "one_nn": 0.3466}


def build_model():
    """Replace this, and change nothing else in the file.

    The default reproduces the published baseline's settings. Anything with
    `fit` and `predict` works: a gradient booster, an MLP, a wrapper around a
    torch model. Keep `random_state` fixed so your own reruns are comparable.
    """
    return RandomForestClassifier(n_estimators=100, n_jobs=-1, random_state=0)


def load(bundle, scenario):
    b = pathlib.Path(bundle)
    shard_dir = b / "shards" / scenario
    if not shard_dir.is_dir():
        available = sorted(d.name for d in (b / "shards").iterdir() if d.is_dir())
        sys.exit(f"no scenario '{scenario}' in {b}. present: {', '.join(available)}")
    files = sorted(glob.glob(str(shard_dir / "*.csv.gz")))
    if not files:
        sys.exit(f"{shard_dir} has no shards")
    print(f"loading {len(files)} shard(s) from {scenario}")
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)

    # Present and equal to 1 for every row in the release, because impure
    # windows were excluded when the bundle was built. Applied anyway so this
    # script stays correct against a corpus built with a different threshold.
    if "label_clean" in df.columns:
        before = len(df)
        df = df[df.label_clean == 1].reset_index(drop=True)
        if len(df) < before:
            print(f"  dropped {before - len(df):,} windows below the purity floor")

    splits = pd.read_csv(b / "release_splits.csv")
    df = df.merge(splits[["key_seed", "key_claimedStationId", "split"]],
                  on=["key_seed", "key_claimedStationId"], how="left")
    if df.split.isna().any():
        sys.exit(f"{int(df.split.isna().sum())} rows matched no partition entry. "
                 "The bundle is inconsistent; run check_release.py.")
    return df


def matrices(df):
    """The feature matrix, the target, and the grouping key.

    `key_*` and `label_*` columns are identifiers and ground truth. A deployed
    receiver has none of them. If one reaches the feature matrix the score stops
    describing detection and starts describing the simulator.
    """
    # app then phy, in that order, exactly as benchmark.py builds its fused
    # block. A random forest samples features per split, so column order changes
    # its trees and a reordered matrix cannot reproduce the published figure.
    feats = ([c for c in df.columns if c.startswith("app_")] +
             [c for c in df.columns if c.startswith("phy_")])
    X = df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    # A prefix cannot smuggle ground truth in, but a column can: a feature that
    # equals a label on every row is the label, whatever it is called.
    labels = [c for c in df.columns if c.startswith("label_")
              and pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 1]
    copies = [(f, l) for l in labels for f in feats
              if (X[f].to_numpy() == df[l].to_numpy()).all()]
    if copies:
        sys.exit(f"feature columns identical to a label: {copies}")
    return X, df.label_attackId.astype(int), df.label_txNodeId.astype(int), feats


def fold_scores(y_true, y_pred, classes):
    """The metrics for one fold, computed exactly as benchmark.py computes them.

    Macro F1 takes the labels present in the fold, as benchmark.py does, rather
    than a fixed list; the published figures are means of these over folds, not
    a score of pooled predictions, and the two are different statistics.
    """
    live = [c for c in classes if c != INERT_CLASS]
    return {
        "macro": f1_score(y_true, y_pred, average="macro"),
        "mcc": matthews_corrcoef(y_true, y_pred),
        "live": f1_score(y_true, y_pred, average="macro", labels=live, zero_division=0),
        "per": f1_score(y_true, y_pred, average=None, labels=classes, zero_division=0),
    }


def report(folds, classes, elapsed, comparable, scenario):
    agg = lambda k: (float(np.mean([f[k] for f in folds])), float(np.std([f[k] for f in folds])))
    (macro, macro_sd), (mcc, mcc_sd), (live, live_sd) = agg("macro"), agg("mcc"), agg("live")
    per = dict(zip(classes, np.mean([f["per"] for f in folds], axis=0)))
    n_live = len([c for c in classes if c != INERT_CLASS])
    note = "" if comparable else "  not comparable, see below"
    print(f"\n  macro F1, all {len(classes)} classes   {macro:.4f} +/- {macro_sd:.4f}"
          f"      (published {PUBLISHED['macro_f1']:.4f}){note}")
    print(f"  macro F1, the {n_live} with a signature  {live:.4f} +/- {live_sd:.4f}")
    print(f"  MCC                          {mcc:.4f} +/- {mcc_sd:.4f}"
          f"      (published {PUBLISHED['mcc']:.4f}){note}")
    print(f"  wall clock                   {elapsed:.0f}s")

    print("\n  per class F1")
    for c in classes:
        tag = "  <- inert by construction" if c == INERT_CLASS else ""
        print(f"    class {c:<3d} {per[c]:.4f}{tag}")

    # The best-of-four column was measured on highway_sparse. On any other
    # scenario the classes are drawn differently (magnitude_sweep widens both
    # offset draws on purpose), so a comparison there would announce a finding
    # that is only a different ladder.
    if scenario != "highway_sparse":
        print(f"\n  Position classes not compared: the best-of-four column was "
              f"measured on\n  highway_sparse, and {scenario} draws its offsets "
              f"differently. Bin by realised\n  displacement instead if magnitude "
              f"matters to your result.")
        return macro
    print("\n  the position classes, which is where the claim lives")
    print(f"    {'class':<32s} {'yours':>7s} {'best of four':>13s}")
    for c, name in POSITION_CLASSES.items():
        print(f"    {name:<32s} {per.get(c, float('nan')):>7.3f} "
              f"{BEST_OF_FOUR[c]:>13.3f}")

    # The best-of-four column was measured under grouped cross-validation. A
    # single pass over the frozen split reads high, by roughly a tenth on the
    # largest position class, so comparing the two columns there would announce
    # a finding that is only the optimism of scoring once instead of averaging
    # folds. An alarm that fires on a protocol difference is an alarm nobody
    # reads by the third time.
    if not comparable:
        print("\n  Not comparable to that column. It was measured under grouped\n"
              "  cross-validation and this was one pass over the frozen split,\n"
              "  which reads high. Re-run with --protocol cv before concluding\n"
              "  anything from the difference.")
    elif any(np.isnan(per.get(c, np.nan)) for c in POSITION_CLASSES):
        print("\n  A position class is missing from this sample, so there is no\n"
              "  verdict. Use a larger --sample.")
    elif macro < PUBLISHED["one_nn"]:
        # Below what a 1-nearest-neighbour classifier reaches, a model is
        # broken and its per class scores support no conclusion.
        print(f"\n  Macro F1 is below the 1-nearest-neighbour floor of "
              f"{PUBLISHED['one_nn']}, so the\n  model is not working and failing to "
              f"move a position class says nothing.")
    elif [c for c in POSITION_CLASSES if per.get(c, 0) > BEST_OF_FOUR[c] + 0.05]:
        print("\n  You moved a position class under the comparable protocol.\n"
              "  That is the finding, not the aggregate. Check the split before\n"
              "  believing it, then write it up.")
    else:
        print("\n  No position class moved. That is the expected result and is\n"
              "  consistent with the bound; failing to beat a baseline is\n"
              "  evidence, not proof.")
    return macro


def leakage_alarm(macro):
    """A near-perfect score on this dataset is a bug report.

    The first version of this project reported 1.0000 from three separate model
    families, and the cause was that 96.39 percent of its test rows appeared
    verbatim in training. A 1-nearest-neighbour classifier reaches only 0.3466
    here, which is the evidence that the task is not memorisable.
    """
    if macro < 0.90:
        return 0
    print("\n" + "!" * 70)
    print(f"  macro F1 {macro:.4f}. STOP.")
    print("  Nothing on this dataset legitimately scores this high. This is")
    print("  almost certainly leakage, not a result. The usual causes:")
    print("    - a split that is not grouped by label_txNodeId")
    print("    - a key_ or label_ column left in the feature matrix")
    print("    - rows shuffled before splitting, so one vehicle lands on both sides")
    print("  A 1-NN classifier reaches 0.3466 here. Treat this as a bug report.")
    print("!" * 70)
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", help="the release directory")
    ap.add_argument("--scenario", default="highway_sparse",
                    help="highway_sparse, highway_dense and magnitude_sweep can "
                         "carry a headline score. The other two have empty class "
                         "and split combinations and cannot")
    ap.add_argument("--protocol", choices=["cv", "frozen"], default="cv",
                    help="cv matches the published protocol, frozen is faster")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--sample", type=int, default=250000,
                    help="rows to subsample, matching the published run. 0 uses "
                         "everything and is much slower")
    a = ap.parse_args()

    df = load(a.bundle, a.scenario)
    if a.sample and len(df) > a.sample:
        df = df.sample(n=a.sample, random_state=0).reset_index(drop=True)
        print(f"  subsampled to {len(df):,} windows, random_state=0")

    X, y, groups, feats = matrices(df)
    classes = sorted(y.unique())
    print(f"  {len(df):,} windows, {len(feats)} features, {len(classes)} classes, "
          f"{groups.nunique()} physical transmitters")

    t0 = time.time()
    if a.protocol == "cv":
        print(f"\ngrouped cross-validation, {a.folds} folds, grouped on "
              f"label_txNodeId")
        sgkf = StratifiedGroupKFold(n_splits=a.folds, shuffle=True,
                                    random_state=0)
        scores = []
        for i, (tr, te) in enumerate(sgkf.split(X, y, groups), 1):
            model = build_model()
            model.fit(X.iloc[tr], y.iloc[tr])
            scores.append(fold_scores(y.iloc[te], model.predict(X.iloc[te]), classes))
            print(f"  fold {i} done")
    else:
        print("\nfrozen partition from the bundle, train against test")
        tr = df.split == "train"
        te = df.split == "test"
        print(f"  train {int(tr.sum()):,} rows, test {int(te.sum()):,} rows")
        model = build_model()
        model.fit(X[tr], y[tr])
        scores = [fold_scores(y[te], model.predict(X[te]), classes)]

    macro = report(scores, classes, time.time() - t0,
                   comparable=(a.protocol == "cv"), scenario=a.scenario)
    sys.exit(leakage_alarm(macro))


if __name__ == "__main__":
    main()
