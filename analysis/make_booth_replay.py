#!/usr/bin/env python3
"""
The booth replay: one recorded minute of the reference scenario, played back
with two detectors deciding side by side about every station in every second.

The two detectors are the two halves of the pooling result. In the first, each
receiver decides alone from its own window and the receivers then vote, which
is the majority-vote arm of the pooling comparison. In the second, the
receivers pool their measurements and one decision is taken over all of them,
which is the pooled arm. Both see the same stations in the same seconds, so a
visitor watches a lie the vote never catches turn red on the pooled side.

Both detectors are trained out of fold with folds grouped by physical
transmitter, the protocol of offset_floor.py, so no station is judged by a model
that was trained on it. Nothing on the page is drawn by hand: positions come
from the transmit log, verdicts from the two detectors.

    make_booth_replay.py RUN_DIR --seed seed1

Writes the data block of docs/booth/replay.html in place, between its markers,
so the page stays one self-contained file that opens with no network.
"""
import argparse
import json
import pathlib

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold

REPO = pathlib.Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "booth" / "replay.html"
BEGIN, END = "/*REPLAY_DATA_BEGIN*/", "/*REPLAY_DATA_END*/"

# Plain names for the page, which has to avoid jargon.
NAMES = {0: "is honest", 1: "shifts its claimed position a long way",
         3: "claims a random position", 4: "lies about its speed",
         5: "replays old messages", 6: "invents extra identities",
         7: "floods the channel", 8: "floods the channel slowly",
         11: "shifts its claimed position a little", 12: "uses a random identity",
         13: "shifts its claimed position part of the way"}
POSITION = {1, 11, 13}
FRAME_MS = 200


def out_of_fold(X, y, groups, trees, jobs, predict_mask=None, sample=None):
    """Binary attack against benign flags, each row predicted by a model whose
    training folds never held its transmitter."""
    flags = np.full(len(y), -1, dtype=np.int8)
    sg = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=0)
    rng = np.random.default_rng(0)
    for k, (tr, te) in enumerate(sg.split(X, y, groups)):
        if sample and len(tr) > sample:
            tr = rng.choice(tr, sample, replace=False)
        clf = RandomForestClassifier(n_estimators=trees, n_jobs=jobs,
                                     random_state=0)
        clf.fit(X[tr], y[tr])
        if predict_mask is not None:
            te = te[predict_mask[te]]
        flags[te] = clf.predict(X[te])
        print(f"  fold {k + 1}: trained on {len(tr):,} rows, "
              f"predicted {len(te):,}", flush=True)
    return flags


def matrix(df, cols):
    return (df[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
            .to_numpy(dtype=np.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--seed", default="seed1")
    ap.add_argument("--pooled", default="pooled_road.pkl")
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--sample", type=int, default=400000,
                    help="training rows per fold for the single receiver "
                         "detector; every row of the replayed seed is still "
                         "predicted")
    a = ap.parse_args()
    run = pathlib.Path(a.run_dir).expanduser()

    print("pooled across receivers")
    pl = pd.read_pickle(run / a.pooled)
    cols = [c for c in pl.columns if c.startswith("pm_") or c.startswith("pool_")]
    pl["flag"] = out_of_fold(matrix(pl, cols),
                             (pl.label_attackId != 0).astype(int).values,
                             pl.label_txNodeId.values, a.trees, a.jobs)
    pl = pl[pl.key_seed == a.seed]

    print("single receivers, then a majority vote")
    df = pd.read_pickle(run / "corpus.pkl")
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    df = df.reset_index(drop=True)
    feats = ([c for c in df.columns if c.startswith("app_")]
             + [c for c in df.columns if c.startswith("phy_")])
    mask = (df.key_seed == a.seed).values
    df["flag"] = out_of_fold(matrix(df, feats),
                             (df.label_attackId != 0).astype(int).values,
                             df.label_txNodeId.values, a.trees, a.jobs,
                             predict_mask=mask, sample=a.sample)
    one = df[mask]
    vote = (one.groupby(["key_claimedStationId", "key_window"])
            .agg(vote=("flag", "mean"), n_rx=("flag", "size"),
                 attack=("label_attackId", "first")).reset_index())

    print("positions from the transmit log")
    tx = pd.read_csv(run / f"tx_{a.seed}.csv",
                     usecols=["txTimeMs", "txNodeId", "claimedStationId",
                              "trueX", "trueY", "claimedX", "claimedY",
                              "attackId"], on_bad_lines="skip").dropna()
    tx["frame"] = (tx.txTimeMs // FRAME_MS).astype(int)
    tx = tx.sort_values("txTimeMs").groupby(["claimedStationId", "frame"]).last()
    tx = tx.reset_index()
    road = float((run / "road_length_m").read_text().split()[0])
    print(f"  {len(tx):,} station frames")

    t0, t1 = int(tx.frame.min()), int(tx.frame.max())
    win = {}
    for r in vote.itertuples():
        win[(r.key_claimedStationId, r.key_window)] = [round(r.vote, 3), int(r.n_rx), -1]
    for r in pl.itertuples():
        k = (r.key_claimedStationId, r.key_window)
        win.setdefault(k, [None, 0, -1])[2] = int(r.flag)

    stations = []
    for sid, g in tx.groupby("claimedStationId"):
        attack = int(g.attackId.mode().iloc[0])
        frames = {int(f): (round(x * 10), round(y * 10), round(cx * 10), round(cy * 10), int(n))
                  for f, x, y, cx, cy, n in zip(g.frame, g.trueX, g.trueY,
                                                g.claimedX, g.claimedY, g.txNodeId)}
        ws = sorted({w for (s, w) in win if s == sid})
        stations.append({
            "id": int(sid), "attack": attack,
            "frames": [[f, *frames[f]] for f in sorted(frames)],
            "windows": {int(w): win[(sid, w)] for w in ws},
            "offset": round(float(np.median(np.hypot(g.claimedX - g.trueX,
                                                     g.claimedY - g.trueY))), 1),
        })

    # Roadside units are the receivers that never move.
    rsu = pd.read_csv(run / f"rx_app_{a.seed}.csv", nrows=400000,
                      usecols=["rxNodeId", "rxX", "rxY", "rxSpeed"],
                      on_bad_lines="skip")
    rsu = (rsu.groupby("rxNodeId").agg(rxX=("rxX", "median"), rxY=("rxY", "median"),
                                       moved=("rxSpeed", "max")))
    rsu = rsu[rsu.moved == 0]

    # Tallies over the whole minute, the same quantities the page counts up.
    att = vote[vote.attack.isin(POSITION)].copy()
    att["pooled"] = [win.get((s, w), [None, 0, -1])[2]
                     for s, w in zip(att.key_claimedStationId, att.key_window)]
    att = att[att.pooled >= 0]
    ben = vote[vote.attack == 0].copy()
    ben["pooled"] = [win.get((s, w), [None, 0, -1])[2]
                     for s, w in zip(ben.key_claimedStationId, ben.key_window)]
    ben = ben[ben.pooled >= 0]

    # A majority vote is far stricter than the pooled detector: it raises a
    # fraction of the false alarms, so comparing the two at their defaults
    # flatters pooling. The vote's threshold is therefore lowered, on honest
    # seconds alone, to the smallest share of receivers at which it raises no
    # more false alarms than pooling does, and the page uses that threshold.
    pooled_false = int((ben.pooled == 1).sum())
    cands = np.unique(ben.vote.values)
    thr = next(t for t in np.r_[cands[cands > 0], 1.01]
               if int((ben.vote >= t).sum()) <= pooled_false)
    summary = {
        "seed": a.seed,
        "vote_threshold": round(float(thr), 4),
        "position_lie_seconds": int(len(att)),
        "caught_by_majority": int((att.vote > 0.5).sum()),
        "caught_by_vote": int((att.vote >= thr).sum()),
        "caught_by_pooling": int((att.pooled == 1).sum()),
        "honest_seconds": int(len(ben)),
        "honest_flagged_by_majority": int((ben.vote > 0.5).sum()),
        "honest_flagged_by_vote": int((ben.vote >= thr).sum()),
        "honest_flagged_by_pooling": pooled_false,
    }
    print(f"\nseed {a.seed}: {len(stations)} claimed stations, frames {t0} to {t1}, "
          f"road {road:.0f} m, {len(rsu)} roadside units")
    onroad = {s["id"] for s in stations
              if np.median([abs(f[4]) / 10 for f in s["frames"]]) <= 18}
    on = att.key_claimedStationId.isin(onroad)
    print(f"vote threshold matched to pooling's false alarms: a share of "
          f"{thr:.4f} of the receivers")
    print(f"position-lie station seconds with a pooled decision: "
          f"{summary['position_lie_seconds']:,}, of them on the road {int(on.sum()):,}")
    print(f"  caught by a majority vote   {summary['caught_by_majority']:,}")
    print(f"  caught by the matched vote  {summary['caught_by_vote']:,}, "
          f"on the road {int(((att.vote >= thr) & on).sum()):,}")
    print(f"  caught by pooling           {summary['caught_by_pooling']:,}, "
          f"on the road {int(((att.pooled == 1) & on).sum()):,}")
    print(f"honest station seconds with a pooled decision: {summary['honest_seconds']:,}")
    print(f"  flagged by a majority vote  {summary['honest_flagged_by_majority']:,}")
    print(f"  flagged by the matched vote {summary['honest_flagged_by_vote']:,}")
    print(f"  flagged by pooling          {summary['honest_flagged_by_pooling']:,}")

    data = {"road": road, "frame_ms": FRAME_MS, "t0": t0, "t1": t1,
            "names": {str(k): v for k, v in NAMES.items()},
            "position": sorted(POSITION),
            "rsu": [[round(x), round(y)] for x, y in zip(rsu.rxX, rsu.rxY)],
            "stations": stations, "summary": summary}
    blob = json.dumps(data, separators=(",", ":"))
    page = PAGE.read_text()
    i, j = page.index(BEGIN) + len(BEGIN), page.index(END)
    PAGE.write_text(page[:i] + "\nwindow.REPLAY = " + blob + ";\n" + page[j:])
    print(f"\nwrote {len(blob) / 1e6:.2f} MB of data into {PAGE.relative_to(REPO)}")
    print("REPLAY DONE")


if __name__ == "__main__":
    main()
