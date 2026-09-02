#!/usr/bin/env python3
"""
Run this project's application-layer detector on VeReMi Extension.

Report 16 is explicit that deferring cross-dataset evaluation only holds "if
your method cannot reasonably be applied there". Half of this method can. The
application-layer block is computed from message contents alone and needs no
radio measurement, so it can be evaluated on somebody else's data. The
cross-layer arm genuinely cannot, and after this runs, that statement is
demonstrated rather than asserted.

The claim under test is the constant-offset blindness. On this project's corpus
the application layer scores exactly 0.000 on constant-offset position
falsification, at every magnitude. If that reproduces on an independently
generated dataset with different mobility, a different radio stack and a
different attack implementation, it is a property of the attack rather than a
quirk of this simulator, and that is the strongest available support for the
claim that only cross-layer evidence resolves it.

THE TRANSFERABLE SUBSET
-----------------------
Five of the twenty two application features cannot be computed on VeReMi and
are excluded from BOTH sides, so the comparison is like for like:

  app_n_cam, app_n_denm, app_n_cpm   VeReMi carries one message type. This
                                     project's corpus carries the ETSI mix, and
                                     a feature that is constant on one dataset
                                     and informative on the other would make
                                     the comparison meaningless.
  app_seq_gaps, app_seq_loss_rate    VeReMi's message identifier is unique
                                     across the simulation rather than a per
                                     sender sequence, so gaps in it carry no
                                     information about loss from one sender.

The remaining seventeen are computed by the same code path on both, which is
the point: a reimplementation would confound a difference in datasets with a
difference in feature definitions.

FORMAT
------
VeReMi ships one JSON-lines file per receiver, plus a ground truth file. A
reception line carries type 3 and the fields used here: rcvTime, sender,
messageID, pos, spd. A type 2 line is the receiver's own position. The ground
truth file names each sender's attacker type.

If the files do not match that shape the loader says which field is missing
rather than producing a corpus with silently empty columns.
"""
import argparse
import json
import pathlib
import re

import numpy as np
import pandas as pd

# The seventeen features computable on both datasets, and the five that are not.
EXCLUDED = ["app_n_cam", "app_n_denm", "app_n_cpm",
            "app_seq_gaps", "app_seq_loss_rate"]

# VeReMi Extension attacker type codes, from the dataset's own documentation.
# Only the position falsification families are used here; the rest are listed so
# an unexpected code is recognised rather than silently folded into benign.
ATTACKS = {0: "benign", 1: "const_pos", 2: "const_pos_offset",
           3: "random_pos", 4: "random_pos_offset", 5: "eventual_stop",
           6: "disruptive", 7: "data_replay", 8: "delayed_messages",
           9: "dos", 10: "dos_random", 11: "dos_disruptive",
           12: "grid_sybil", 13: "data_replay_sybil", 14: "dos_random_sybil",
           15: "dos_disruptive_sybil"}

# The families that displace a claimed position by a fixed vector, which is the
# behaviour this project's class 1, 11 and 13 implement.
CONST_OFFSET = {1, 2}


def _need(d, *keys):
    missing = [k for k in keys if k not in d]
    if missing:
        raise SystemExit(
            f"VeReMi record is missing {missing}. Expected a type 3 reception "
            f"line carrying rcvTime, sender, messageID, pos and spd. Got keys "
            f"{sorted(d)}. If the release you have uses different names, map "
            f"them here rather than downstream, so the feature definitions "
            f"stay identical to the ones used on this project's corpus.")


def load_ground_truth(path):
    """Sender to attacker type. Accepts the JSON-lines ground truth file."""
    truth = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            s = d.get("sender", d.get("senderPseudo"))
            a = d.get("attackerType", d.get("attacker_type"))
            if s is not None and a is not None:
                truth[int(s)] = int(a)
    if not truth:
        raise SystemExit(f"no sender to attacker mapping found in {path}")
    return truth


def load_receiver(path, truth, receiver_id):
    """One receiver's log into per-reception rows in this project's schema."""
    own, rows = None, []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            t = d.get("type")
            if t == 2:                      # the receiver's own position
                own = d.get("pos")
                continue
            if t != 3:
                continue
            _need(d, "rcvTime", "sender", "messageID", "pos", "spd")
            if own is None:
                # A reception before the receiver has logged its own position
                # cannot have a claimed distance computed, and dropping it is
                # better than imputing a receiver position.
                continue
            sx, sy = float(d["spd"][0]), float(d["spd"][1])
            rows.append((
                float(d["rcvTime"]) * 1000.0,
                int(d["sender"]),
                int(d["messageID"]),
                float(d["pos"][0]), float(d["pos"][1]),
                float(own[0]), float(own[1]),
                float(np.hypot(sx, sy)),
                float(np.degrees(np.arctan2(sx, sy)) % 360.0),
                int(truth.get(int(d["sender"]), 0)),
            ))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=[
        "rxTimeMs", "claimedStationId", "msgUid", "claimedX", "claimedY",
        "rxX", "rxY", "claimedSpeed", "claimedHeading", "label_attackId"])
    df["rxNodeId"] = receiver_id
    return df


def load_veremi(root, limit=None):
    """Every receiver log under one VeReMi simulation directory."""
    root = pathlib.Path(root)
    gt = sorted(root.glob("GroundTruthJSONlog*"))
    if not gt:
        raise SystemExit(
            f"no GroundTruthJSONlog file under {root}. A VeReMi release ships "
            f"one per simulation alongside the per-receiver JSONlog files.")
    truth = load_ground_truth(gt[0])
    logs = sorted(p for p in root.glob("JSONlog-*") if p.is_file())
    if limit:
        logs = logs[:limit]
    if not logs:
        raise SystemExit(f"no JSONlog-* receiver files under {root}")
    out = []
    for i, p in enumerate(logs):
        m = re.search(r"JSONlog-(\d+)", p.name)
        rid = int(m.group(1)) if m else i
        d = load_receiver(p, truth, rid)
        if d is not None:
            out.append(d)
    if not out:
        raise SystemExit("every receiver log was empty after parsing")
    df = pd.concat(out, ignore_index=True)
    print(f"{len(df):,} receptions from {df.rxNodeId.nunique()} receivers, "
          f"{df.claimedStationId.nunique()} senders")
    counts = df.groupby("label_attackId").claimedStationId.nunique()
    print("senders per attacker type: " +
          "  ".join(f"{ATTACKS.get(int(k), k)}:{v}" for k, v in counts.items()))
    return df


def _angdiff(a, b):
    d = (a - b + 180.0) % 360.0 - 180.0
    return np.abs(d)


def residuals_and_windows(rx, window_ms=1000.0):
    """The seventeen transferable features, by the same definitions as
    `build_features.py`.

    The arithmetic is deliberately copied rather than imported. `build_features`
    reads this project's CSV layout and computes radio features alongside, and
    importing it would drag that in. The trade is a duplicated block that has to
    stay in step, so any change to a residual definition there has to be made
    here too, and the feature names are asserted against a corpus at the end of
    a run so a drift is caught rather than assumed absent.
    """
    rx = rx.sort_values(["rxNodeId", "claimedStationId", "rxTimeMs"]).copy()
    g = rx.groupby(["rxNodeId", "claimedStationId"], sort=False)

    rx["claimedDist"] = np.hypot(rx.claimedX - rx.rxX, rx.claimedY - rx.rxY)
    rx["dt"] = g.rxTimeMs.diff() / 1000.0
    rx["dClaimedX"] = g.claimedX.diff()
    rx["dClaimedY"] = g.claimedY.diff()
    rx["claimedMoved"] = np.hypot(rx.dClaimedX, rx.dClaimedY)

    prev_speed = g.claimedSpeed.shift()
    rx["dmv_residual"] = rx.claimedMoved - prev_speed * rx.dt
    implied_speed = rx.claimedMoved / rx.dt.replace(0, np.nan)
    rx["ssc_residual"] = implied_speed - rx.claimedSpeed

    prev_heading_rad = np.deg2rad(g.claimedHeading.shift())
    pred_x = g.claimedX.shift() + prev_speed * rx.dt * np.sin(prev_heading_rad)
    pred_y = g.claimedY.shift() + prev_speed * rx.dt * np.cos(prev_heading_rad)
    rx["predict_residual"] = np.hypot(rx.claimedX - pred_x, rx.claimedY - pred_y)

    move_bearing = np.rad2deg(np.arctan2(rx.dClaimedX, rx.dClaimedY)) % 360.0
    rx["heading_residual"] = np.where(rx.claimedMoved > 1.0,
                                      _angdiff(rx.claimedHeading, move_bearing),
                                      np.nan)
    rx["implied_accel"] = (rx.claimedSpeed - prev_speed) / rx.dt.replace(0, np.nan)

    rx["window"] = (rx.rxTimeMs // window_ms).astype(int)
    key = ["rxNodeId", "claimedStationId", "window"]
    agg = rx.groupby(key).agg(
        app_n_msgs=("msgUid", "size"),
        app_iat_mean=("dt", "mean"),
        app_iat_std=("dt", "std"),
        app_iat_min=("dt", "min"),
        app_claimed_dist_mean=("claimedDist", "mean"),
        app_claimed_dist_std=("claimedDist", "std"),
        app_claimed_speed_mean=("claimedSpeed", "mean"),
        app_claimed_speed_std=("claimedSpeed", "std"),
        app_dmv_mean=("dmv_residual", "mean"),
        app_dmv_absmax=("dmv_residual", lambda s: s.abs().max()),
        app_ssc_mean=("ssc_residual", "mean"),
        app_ssc_absmax=("ssc_residual", lambda s: s.abs().max()),
        app_predict_mean=("predict_residual", "mean"),
        app_predict_max=("predict_residual", "max"),
        app_heading_mean=("heading_residual", "mean"),
        app_heading_max=("heading_residual", "max"),
        app_accel_absmax=("implied_accel", lambda s: s.abs().max()),
        label_attackId=("label_attackId", "first"),
    ).reset_index()
    agg = agg.rename(columns={"rxNodeId": "key_rxNodeId",
                              "claimedStationId": "key_claimedStationId",
                              "window": "key_window"})
    agg["label_txNodeId"] = agg.key_claimedStationId
    return agg


def transferable(df):
    """The feature columns present on both datasets."""
    return [c for c in df.columns
            if c.startswith("app_") and c not in EXCLUDED]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("veremi_dir", nargs="?",
                    help="one VeReMi simulation directory")
    ap.add_argument("--corpus", required=True,
                    help="this project's corpus, for the paired comparison")
    ap.add_argument("--selftest", nargs=2, metavar=("RUN_DIR", "TAG"),
                    help="skip VeReMi and instead prove the feature "
                         "definitions here match build_features.py, by "
                         "recomputing them from this project's own receive log")
    ap.add_argument("--limit-receivers", type=int, default=None)
    ap.add_argument("--sample", type=int, default=400000)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    if a.selftest:
        raise SystemExit(selftest(a.selftest[0], a.selftest[1], a.corpus))
    if not a.veremi_dir:
        ap.error("give a VeReMi directory, or --selftest RUN_DIR TAG")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.metrics import f1_score, matthews_corrcoef

    print("VeReMi Extension")
    vm = residuals_and_windows(load_veremi(a.veremi_dir, a.limit_receivers))
    feats = transferable(vm)
    print(f"{len(vm):,} windows, {len(feats)} transferable features\n")

    ours = pd.read_pickle(a.corpus)
    if "label_clean" in ours.columns:
        ours = ours[ours.label_clean == 1]
    if a.sample and len(ours) > a.sample:
        ours = ours.sample(n=a.sample, random_state=0)
    missing = [c for c in feats if c not in ours.columns]
    if missing:
        raise SystemExit(
            f"{missing} are not in this project's corpus, so the feature "
            f"definitions have drifted apart and the comparison would be "
            f"between two different detectors. Fix the definitions before "
            f"reading any number below.")

    def run(df, name, offset_classes, benign=0):
        X = (df[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
             .to_numpy(dtype=np.float32))
        keep = df.label_attackId.isin(list(offset_classes) + [benign]).values
        X, sub = X[keep], df[keep]
        y = (sub.label_attackId != benign).astype(int).values
        groups = sub.label_txNodeId.values
        sg = StratifiedGroupKFold(n_splits=a.folds, shuffle=True, random_state=0)
        f1s, mccs = [], []
        for tr, te in sg.split(X, y, groups):
            clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                         random_state=0)
            clf.fit(X[tr], y[tr])
            p = clf.predict(X[te])
            f1s.append(f1_score(y[te], p, average="binary", zero_division=0))
            mccs.append(matthews_corrcoef(y[te], p))
        print(f"{name:34s} {len(sub):>9,} windows  "
              f"{int(sub.label_txNodeId.nunique()):>4} stations  "
              f"F1 {np.mean(f1s):.4f} +/- {np.std(f1s):.4f}  "
              f"MCC {np.mean(mccs):.4f}")
        return float(np.mean(f1s))

    print("constant-offset position falsification against benign, application "
          "layer only,\nthe same seventeen features and the same model on "
          "both datasets\n")
    v = run(vm, "VeReMi Extension", CONST_OFFSET)
    o = run(ours, "this project's corpus", {1, 11, 13})
    print(f"\nBoth near zero is the result. It says the application layer "
          f"cannot see a constant\nposition offset, on two independently "
          f"generated datasets with different mobility,\ndifferent radio "
          f"stacks and different attack implementations, which makes it a "
          f"property\nof the attack rather than of this simulator.")
    print(f"A high score on VeReMi and a low one here would mean the opposite, "
          f"that something\nabout this corpus is hiding a signal the "
          f"application layer can normally find.")
    print(f"\nVeReMi {v:.4f}, this corpus {o:.4f}")


def selftest(run_dir, tag, corpus_path, tol=1e-6):
    """Prove the duplicated arithmetic matches `build_features.py`.

    The transferable features are recomputed here from this project's own raw
    receive log, in the VeReMi-shaped schema, and compared against the corpus
    that `build_features.py` produced from the same log. If the two agree, a
    VeReMi score computed by this file is comparable to a corpus score computed
    by that one. If they do not, the cross-dataset comparison is between two
    different detectors and no number from it means anything.

    Run it whenever either residual definition is touched.
    """
    rx = pd.read_csv(f"{run_dir}/rx_app_{tag}.csv")
    rx = rx.rename(columns={})[[
        "msgUid", "rxTimeMs", "rxNodeId", "claimedStationId", "claimedX",
        "claimedY", "claimedSpeed", "claimedHeading", "rxX", "rxY"]].copy()
    rx["label_attackId"] = 0
    mine = residuals_and_windows(rx)

    corpus = pd.read_pickle(corpus_path).copy()
    feats = transferable(mine)
    key = ["key_rxNodeId", "key_claimedStationId", "key_window"]

    # build_corpus.py namespaces receiver identifiers per seed by adding a
    # multiple of 100000, so a single-seed corpus carries an offset the raw log
    # does not. Recover it from the data rather than hardcoding it, because the
    # multiple depends on the seed's position in the build order.
    off = int(corpus.key_rxNodeId.min()) - int(mine.key_rxNodeId.min())
    off = int(round(off / 100000.0)) * 100000
    if off:
        print(f"corpus receiver identifiers carry a namespacing offset of "
              f"{off:,}; removing it to compare")
        corpus["key_rxNodeId"] -= off
    j = mine.merge(corpus[key + feats], on=key, suffixes=("_new", "_old"))
    if j.empty:
        raise SystemExit("no overlapping windows, so nothing was compared")

    print(f"{len(j):,} windows compared against {pathlib.Path(corpus_path).name}\n")
    bad = 0
    for c in feats:
        a_, b_ = j[f"{c}_new"], j[f"{c}_old"]
        both_nan = a_.isna() & b_.isna()
        d = (a_ - b_).abs()
        worst = float(d[~both_nan].max()) if (~both_nan).any() else 0.0
        mism = int(((d > tol) & ~both_nan).sum()) + int((a_.isna() ^ b_.isna()).sum())
        bad += mism > 0
        print(f"  {'ok  ' if mism == 0 else 'FAIL'} {c:26s} "
              f"max |difference| {worst:.3e}"
              + ("" if mism == 0 else f"   <- {mism:,} windows disagree"))
    if bad:
        print(f"\n{bad} feature(s) do not match. The cross-dataset comparison "
              f"is invalid until they do.")
        return 1
    print(f"\nall {len(feats)} transferable features match to {tol:g}")
    return 0


if __name__ == "__main__":
    main()
