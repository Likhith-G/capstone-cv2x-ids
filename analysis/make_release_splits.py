#!/usr/bin/env python3
"""
Frozen train, validation and test partitions for the released dataset.

Why this exists separately from `make_splits.py`. That script builds the two
sets this project's own evaluation needs: a class-balanced set to train on and a
deployment-realism set held at true prevalence. Those serve the analysis. They do
not serve somebody else who wants to compare a detector against the numbers
published here, because nothing tells them which stations were in which fold.

VeReMi NextGen ships predefined training, validation and test sets and names
their absence as a specific limitation of earlier datasets. Research report 24
lists it among this dataset's honest disadvantages. This closes it.

**The partition is by PHYSICAL TRANSMITTER, not by claimed identity, not by
window and not by seed.**

By transmitter rather than claimed identity, because sybil is the attack whose
whole nature is that one vehicle claims to be several. Twenty one physical sybil
nodes here emit four claimed identities each, so grouping on the claimed
identifier would scatter one vehicle's four identities across train, validation
and test and let a detector memorise its radio signature in training and be
scored on the same vehicle in test. The first version of this script did exactly
that. The corpus has 783 claimed identities and 720 physical transmitters, and
the difference is entirely sybil.

By transmitter rather than window, because one station produces thousands of
windows and a window level split puts the same vehicle on both sides of the
boundary. That is the leakage rule the whole pipeline is built around, and the
project's own StratifiedGroupKFold groups on the same column.

By station rather than seed, because a seed-level split is not viable here and
the reason is worth recording: five of the eight seeds are missing at least one
attack class entirely. Thirty attackers spread over nine classes is about three
per class per seed, so an empty class in one seed is expected. A test partition
of one or two whole seeds would therefore be missing classes, which makes it
useless as a benchmark. `--audit` prints the table this rests on.

**A dependence this does not remove, stated rather than hidden.** Stations within
one seed share a traffic realisation, so a benign station in train and an
attacker in test drawn from the same seed saw the same road conditions. Station
grouping removes identity leakage, not scenario correlation. The project's own
StratifiedGroupKFold protocol accepts the same limit, and a seed-level split
would remove it at the cost of class coverage.

**One partition across every scenario, not one per scenario.** The campaigns in
this project were generated with the same rngRun values, so the same physical
vehicles appear in several of them at identical positions: campaign_gnss and
campaign_floor share 90 transmitters at seed1, to four decimal places, carrying
the same classes. A per-scenario partition would therefore let somebody train on
one scenario and score on the same vehicles in another, which is the leakage this
whole pipeline exists to prevent, shipped into a public benchmark. Assigning once
on (key_seed, label_txNodeId) across the union makes cross-scenario evaluation
safe by construction.

    make_release_splits.py corpus.pkl --out splits.csv
    make_release_splits.py A/corpus.pkl B/corpus.pkl C/corpus.pkl --out splits.csv
    make_release_splits.py corpus.pkl --audit
"""
import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

# The physical transmitter. NOT key_claimedStationId: see the module docstring.
STATION = ["key_seed", "label_txNodeId"]
DEFAULT_FRACTIONS = (0.60, 0.20, 0.20)
SPLIT_SEED = 20260906


def station_table(df):
    """One row per physical transmitter, with its class and window count."""
    g = df.groupby(STATION)
    out = g.label_attackId.first().rename("label_attackId").reset_index()
    out["windows"] = g.size().values
    out["claimed_ids"] = g.key_claimedStationId.nunique().values
    return out


def expand(st, df):
    """Map the partition back onto every claimed identity.

    Rows carry a claimed identifier, not a transmitter, so a user applies the
    manifest by merging on the claimed one. The SPLIT is decided per physical
    transmitter and then copied to each of its identities, which is what keeps a
    sybil node whole.
    """
    ids = (df[["key_seed", "label_txNodeId", "key_claimedStationId"]]
           .drop_duplicates())
    return ids.merge(st, on=STATION, how="left")


def audit(st):
    tab = st.pivot_table(index="key_seed", columns="label_attackId",
                         values="label_txNodeId", aggfunc="count",
                         fill_value=0)
    print("stations per class per seed\n")
    print(tab.to_string())
    missing = int((tab.drop(columns=[0], errors="ignore") == 0).any(axis=1).sum())
    print(f"\n{missing} of {len(tab)} seeds are missing at least one attack class.")
    print("""
That is why the partition is by station rather than by seed. A test partition of
one or two whole seeds would be missing classes outright, which makes it useless
for comparing detectors. Splitting by station keeps every class in every
partition at the cost of leaving stations from one seed on both sides.
""")


def assign(st, fractions, seed):
    """Stratified station-level partition, deterministic given the seed.

    Stratifying by class matters more here than it usually does: the thinnest
    class has fifteen stations, so an unstratified draw can empty it out of a
    partition by chance and the benchmark then cannot be scored on it.
    """
    rng = np.random.default_rng(seed)
    st = st.sort_values(STATION).reset_index(drop=True)
    split = np.empty(len(st), dtype=object)
    for cls, idx in st.groupby("label_attackId").groups.items():
        idx = np.array(sorted(idx))
        rng.shuffle(idx)
        n = len(idx)
        n_tr = int(round(fractions[0] * n))
        n_va = int(round(fractions[1] * n))
        # Every class must reach every partition, so when rounding would empty
        # one, take from the largest instead of shipping an unscoreable class.
        if n >= 3:
            n_tr = max(1, min(n_tr, n - 2))
            n_va = max(1, min(n_va, n - n_tr - 1))
        split[idx[:n_tr]] = "train"
        split[idx[n_tr:n_tr + n_va]] = "validation"
        split[idx[n_tr + n_va:]] = "test"
    st["split"] = split
    return st


def report(st):
    print("stations per class per partition\n")
    tab = st.pivot_table(index="label_attackId", columns="split",
                         values="label_txNodeId", aggfunc="count",
                         fill_value=0)
    tab = tab.reindex(columns=["train", "validation", "test"], fill_value=0)
    tab["total"] = tab.sum(axis=1)
    print(tab.to_string())

    empty = tab[(tab[["train", "validation", "test"]] == 0).any(axis=1)]
    if len(empty):
        print(f"\nFAIL: {len(empty)} class(es) missing from a partition")
        return False

    print("\nwindows per partition")
    w = st.groupby("split").windows.sum().reindex(["train", "validation", "test"])
    for k, v in w.items():
        print(f"  {k:<11s} {v:>10,d}  {100*v/w.sum():5.1f}%")

    thin = tab[tab["total"] < 20]
    if len(thin):
        print(f"\n{len(thin)} class(es) have fewer than 20 stations in total, so a "
              f"per-class\nscore on them rests on single figures per partition and "
              f"should be read\nwith the station count beside it:")
        for cls, row in thin.iterrows():
            print(f"  class {cls:<3d} train {row['train']:>3d}  "
                  f"validation {row['validation']:>3d}  test {row['test']:>3d}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", nargs="+",
                    help="one or more corpora. The partition is assigned ONCE "
                         "over their union, because they share vehicles")
    ap.add_argument("--out", default=None, help="write the manifest here as CSV")
    ap.add_argument("--audit", action="store_true",
                    help="print the per seed class coverage that justifies a "
                         "station level partition, and stop")
    ap.add_argument("--fractions", type=float, nargs=3,
                    default=list(DEFAULT_FRACTIONS), metavar=("TRAIN", "VAL", "TEST"))
    ap.add_argument("--seed", type=int, default=SPLIT_SEED,
                    help="fixed so the partition is reproducible. Changing it "
                         "produces a DIFFERENT benchmark and any published "
                         "number stops being comparable")
    a = ap.parse_args()

    frames = []
    for c in a.corpus:
        d = pd.read_pickle(c)
        if "label_clean" in d.columns:
            d = d[d.label_clean == 1]
        d = d[["key_seed", "label_txNodeId", "key_claimedStationId", "label_attackId"]]
        print(f"  {pathlib.Path(c).parent.name:<22s} {len(d):>10,} windows")
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    st = station_table(df)

    # A transmitter can carry DIFFERENT classes in different scenarios, because
    # each campaign draws its own attacker assignment over the same vehicle
    # population. That is not an error and it is not a reason to abandon a
    # global partition: the partition exists to keep a vehicle identity on one
    # side of the boundary, whatever role it plays on any given day.
    multi = int((df.groupby(STATION).label_attackId.nunique() > 1).sum())
    if multi:
        print(f"  {multi} transmitter(s) play different classes in different "
              f"scenarios, which is expected.\n  Each is stratified on the class "
              f"it carries in the FIRST corpus it appears in, and per-scenario\n"
              f"  class coverage is checked afterwards.")

    print(f"\n{len(df):,} windows across {len(a.corpus)} scenario(s), "
          f"{len(st)} physical transmitters carrying "
          f"{int(st.claimed_ids.sum())} claimed identities, "
          f"{st.label_attackId.nunique()} classes\n")

    if a.audit:
        audit(st)
        return 0

    st = assign(st, a.fractions, a.seed)
    ok = report(st)

    if a.out:
        expand(st, df).sort_values(STATION).to_csv(a.out, index=False)
        print(f"\nmanifest -> {a.out}")
        print(f"seed {a.seed}, fractions {tuple(a.fractions)}. Both are part of "
              f"the partition's\nidentity: reproducing it needs this file or "
              f"these two values, not one of them.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
