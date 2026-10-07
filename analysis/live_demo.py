#!/usr/bin/env python3
"""
Real-time traffic classification, replayed from the released dataset.

The project brief asks for "real-time traffic classification with performance
metrics" and a working demo. This is that demo, built only from the release
bundle so anyone holding it can run it:

  1. Train the release's own baseline exactly as check_release.py does (the
     reference scenario's frozen training partition, 400,000 rows, a 60-tree
     random forest, random_state 0).
  2. Replay the frozen TEST partition in time order, one second at a time. Each
     second, every receiver decides about every station it heard in that
     window, which is what a deployed receiver does once its 1000 ms window
     fills. The decisions for that second are made in one batch and timed.
  3. Print, every second, what was decided, the alerts raised, the time it took,
     and the running scores: macro F1 and MCC over everything so far, the share
     of each attack family caught (spoofing, flooding, replay, the three the
     brief names) and the false alarm rate on honest stations.

What it is not: a live simulation. The windows were recorded by the simulator
and are replayed here, so the demo shows the detector's behaviour over time on
held-out data, and its timing is the classifier's, not the radio's. Because the
model and the test rows are the release's own, the final scores must equal the
published frozen-split baseline, which the last line checks.

    live_demo.py BUNDLE [--pace 1.0] [--every 5] [--seeds seed1,seed2]

--pace 1.0 plays in real time, one window per second; 0 plays as fast as the
classifier allows; 0.1 is ten times real time.
"""
import argparse
import json
import pathlib
import sys
import time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, matthews_corrcoef

from baseline_starter import load

PUBLISHED = (0.5319, 0.6746)   # check_release.py, reference scenario, frozen split
FAMILIES = {                   # the attacks the project brief names
    "spoofing": [1, 3, 11, 13],
    "flooding": [7, 12],
    "replay": [4],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--scenario", default="highway_sparse")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="seconds of wall time per window; 1.0 is real time")
    ap.add_argument("--every", type=int, default=1,
                    help="print every Nth second")
    ap.add_argument("--seeds", default=None,
                    help="comma separated seeds to replay; all by default, "
                         "and only all of them reproduce the published score")
    ap.add_argument("--trees", type=int, default=60)
    ap.add_argument("--sample", type=int, default=400000)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()

    b = pathlib.Path(a.bundle)
    schema = json.loads((b / "schema.json").read_text())
    feats = [c["name"] for c in schema["columns"] if c["is_feature"]]
    df = load(a.bundle, a.scenario)
    tr = df[df.split == "train"]
    te = df[df.split == "test"]
    del df
    if a.sample and len(tr) > a.sample:
        tr = tr.sample(a.sample, random_state=0)

    print(f"training the release baseline: {len(tr):,} windows, {len(feats)} "
          f"features, {a.trees} trees")
    t0 = time.time()
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                 class_weight=None, random_state=0)
    clf.fit(tr[feats].astype("float32").fillna(-999), tr.label_attackId)
    print(f"trained in {time.time() - t0:.0f} s\n")
    del tr

    if a.seeds:
        te = te[te.key_seed.isin(a.seeds.split(","))]
    te = te.sort_values(["key_seed", "key_window"], kind="stable")
    groups = list(te.groupby(["key_seed", "key_window"], sort=False))
    print(f"replaying {len(te):,} held-out windows: {te.key_seed.nunique()} drives, "
          f"{len(groups)} seconds of traffic, one batch of decisions per second\n")
    print(f"{'drive':>6s} {'t':>4s} {'decisions':>9s} {'alerts':>7s} "
          f"{'true atk':>8s} {'ms/batch':>8s} {'us/decision':>11s} "
          f"{'macro F1':>8s} {'MCC':>6s} {'spoof':>6s} {'flood':>6s} "
          f"{'replay':>6s} {'false alarm':>11s}")

    truth, pred, lat_batch, lat_each = [], [], [], []
    for i, ((seed, win), g) in enumerate(groups):
        start = time.perf_counter()
        p = clf.predict(g[feats].astype("float32").fillna(-999))
        dt = time.perf_counter() - start
        truth.append(g.label_attackId.to_numpy())
        pred.append(p)
        lat_batch.append(dt)
        lat_each.append(dt / len(g))
        if i % a.every == 0 or i == len(groups) - 1:
            yt, yp = np.concatenate(truth), np.concatenate(pred)
            caught = {}
            for fam, cls in FAMILIES.items():
                m = np.isin(yt, cls)
                caught[fam] = (yp[m] != 0).mean() if m.any() else float("nan")
            ben = yt == 0
            fa = (yp[ben] != 0).mean() if ben.any() else float("nan")
            print(f"{str(seed):>6s} {int(win):4d} {len(g):9d} {int((p != 0).sum()):7d} "
                  f"{int((g.label_attackId != 0).sum()):8d} {dt * 1e3:8.1f} "
                  f"{dt / len(g) * 1e6:11.1f} "
                  f"{f1_score(yt, yp, average='macro'):8.4f} "
                  f"{matthews_corrcoef(yt, yp):6.3f} {caught['spoofing']:6.3f} "
                  f"{caught['flooding']:6.3f} {caught['replay']:6.3f} {fa:11.4f}")
            sys.stdout.flush()
        if a.pace > 0:
            time.sleep(max(0.0, a.pace - dt))

    yt, yp = np.concatenate(truth), np.concatenate(pred)
    f1, mcc = f1_score(yt, yp, average="macro"), matthews_corrcoef(yt, yp)
    lb, le = np.array(lat_batch), np.array(lat_each)
    print(f"\n{len(yt):,} decisions over {len(groups)} seconds of traffic")
    print(f"batch latency per second of traffic: median {np.median(lb) * 1e3:.1f} ms, "
          f"95th percentile {np.percentile(lb, 95) * 1e3:.1f} ms, worst "
          f"{lb.max() * 1e3:.1f} ms, against the 1000 ms the window takes to fill")
    print(f"per decision: median {np.median(le) * 1e6:.1f} us")
    for fam, cls in FAMILIES.items():
        m = np.isin(yt, cls)
        print(f"{fam:9s} windows flagged as an attack {(yp[m] != 0).mean():.3f}, "
              f"named as the right class {(yp[m] == yt[m]).mean():.3f}")
    print(f"honest windows falsely flagged {(yp[yt == 0] != 0).mean():.4f}")
    print(f"final macro F1 {f1:.4f}, MCC {mcc:.4f}")
    if not a.seeds:
        ok = round(f1, 4) == PUBLISHED[0] and round(mcc, 4) == PUBLISHED[1]
        print(f"published frozen-split baseline: macro F1 {PUBLISHED[0]}, MCC "
              f"{PUBLISHED[1]}: {'REPRODUCED' if ok else 'NOT REPRODUCED'}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
