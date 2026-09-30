#!/usr/bin/env python3
"""
Run this project's application-layer detector on VeReMi.

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
import shlex
import sys

import numpy as np
import pandas as pd

# The seventeen features computable on both datasets, and the five that are not.
EXCLUDED = ["app_n_cam", "app_n_denm", "app_n_cpm",
            "app_seq_gaps", "app_seq_loss_rate"]

# Attacker type codes of the original VeReMi, powers of two. Only the original
# release and NextGen are supported. VeReMi Extension numbers its nineteen
# attacks differently and ships in a layout this loader does not read, so a code
# outside this table stops the run rather than being relabelled.
ATTACKS_ORIGINAL = {0: "benign", 1: "const_pos", 2: "const_pos_offset",
                    4: "random_pos", 8: "random_pos_offset",
                    16: "eventual_stop"}

# ConstPosOffset ONLY. This project's small, medium and large offset classes all
# displace the claimed position by a fixed vector while leaving speed and
# heading truthful, so the claim stays self consistent and the application layer
# has nothing to test it against. VeReMi's type 2 is that attack.
#
# VeReMi's type 1, ConstPos, transmits a FIXED position instead. A vehicle that
# claims not to move while claiming a speed contradicts itself in every
# consecutive pair of messages, which is exactly what the self consistency
# features are for. Treating the two as one family conflates a self consistent
# lie with a self inconsistent one and produces a high score that says nothing
# about the claim being tested. It did: lumping them together scored 0.7203.
CONST_OFFSET = {2}

# Kept as a POSITIVE CONTROL rather than discarded. If the application layer
# detects a self inconsistent position lie and not a self consistent one, the
# blindness is specific rather than general, and that is a much stronger
# statement than either result alone.
SELF_INCONSISTENT = {1}

ATTACKS = ATTACKS_ORIGINAL


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


# VeReMi NextGen (Hermann, Remmers, Eisermann, Erb and Kargl, IEEE VNC 2026)
# is a different shape from either earlier release. One JSON array per receiver
# rather than JSON lines, every record carrying both the receiver's and the
# sender's state, and an `attacker` flag in the record itself rather than a
# separate ground truth join. `pos` is what the sender REPORTED, already
# attacked where it is an attacker, and `pos_noise` is the sensor error that
# both benign and attacking senders carry: their magnitudes are both about 4 m,
# which is how the two are told apart.
#
# The flag says only that a sender attacks, not how, so the variant is read from
# the scenario's directory name. constantPositionOffset is the comparable,
# self consistent lie; randomPositionOffset draws a new offset every message,
# contradicts the claimed speed at every step, and is the positive control.
NEXTGEN_VARIANTS = {"constantPositionOffset": 2, "randomPositionOffset": 1}


def load_nextgen(root, limit=None):
    """One NextGen scenario directory into the same schema as load_veremi."""
    root = pathlib.Path(root)
    files = sorted(p for p in root.rglob("veh_*.json") if p.is_file())
    if not files:
        raise SystemExit(f"no veh_*.json receiver logs under {root}")
    if limit:
        files = files[:limit]
    found = {v for v in NEXTGEN_VARIANTS for f in files[:1] + files[-1:]
             if v in str(f)}
    if len(found) != 1:
        raise SystemExit(f"cannot tell which NextGen variant {root} holds: its "
                         f"path names {sorted(found) or 'none'} of "
                         f"{sorted(NEXTGEN_VARIANTS)}. The attacker flag does "
                         f"not say, so the directory has to.")
    variant = found.pop()
    attack_code = NEXTGEN_VARIANTS[variant]
    print(f"NextGen variant {variant}, attackers labelled "
          f"{ATTACKS_ORIGINAL[attack_code]} ({attack_code})")
    rows = []
    for rid, path in enumerate(files):
        try:
            recs = json.load(open(path))
        except json.JSONDecodeError:
            continue
        for d in recs:
            s, r = d.get("sender"), d.get("receiver")
            if not s or not r:
                continue
            try:
                sp = [float(v) for v in s["pos"].split(",")]
                rp = [float(v) for v in r["pos"].split(",")]
                rows.append((
                    float(d["rcvTime"]) / 1e6,          # ns to ms
                    int(str(d["sender_id"]).split("_")[-1]),
                    int(d["messageID"]),
                    sp[0], sp[1], rp[0], rp[1],
                    float(s["spd"]),
                    float(s["hed"]) % 360.0,
                    attack_code if int(d.get("attacker", 0)) else 0,
                    rid,
                ))
            except (KeyError, ValueError, IndexError, TypeError):
                continue
    if not rows:
        raise SystemExit("every NextGen receiver log was empty after parsing")
    df = pd.DataFrame(rows, columns=[
        "rxTimeMs", "claimedStationId", "msgUid", "claimedX", "claimedY",
        "rxX", "rxY", "claimedSpeed", "claimedHeading", "label_attackId",
        "rxNodeId"])
    n_att = df[df.label_attackId != 0].claimedStationId.nunique()
    print(f"{len(df):,} receptions from {df.rxNodeId.nunique()} receivers, "
          f"{df.claimedStationId.nunique()} senders")
    print(f"VeReMi NextGen, {n_att} attacking senders labelled in the records "
          f"themselves rather than joined from a ground truth file")
    return df


def load_veremi(root, limit=None):
    """Every receiver log under one VeReMi simulation directory."""
    root = pathlib.Path(root)
    # A VeReMi archive nests the results directory several levels down, so
    # accept either the results directory itself or anything above it.
    if not list(root.glob("GroundTruthJSONlog*")):
        found = sorted(root.rglob("GroundTruthJSONlog*"))
        if found:
            root = found[0].parent
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

    seen = set(int(k) for k in counts.index)
    if seen - set(ATTACKS_ORIGINAL):
        raise SystemExit(f"attacker codes {sorted(seen - set(ATTACKS_ORIGINAL))} "
                         f"are not the original VeReMi's. Only the original "
                         f"release and NextGen are supported.")
    print("senders per attacker type: " +
          "  ".join(f"{ATTACKS_ORIGINAL[int(k)]}:{v}" for k, v in counts.items()))
    return df


def _angdiff(a, b):
    d = (a - b + 180.0) % 360.0 - 180.0
    return np.abs(d)


def _unwrap(d, length):
    """build_features._unwrap: a difference along the road, the short way round."""
    return d if length is None else d - length * np.round(d / length)


def residuals_and_windows(rx, window_ms=1000.0, road_length=None):
    """The seventeen transferable features, by the same definitions as
    `build_features.py`.

    The arithmetic is deliberately copied rather than imported. `build_features`
    reads this project's CSV layout and computes radio features alongside, and
    importing it would drag that in. The trade is a duplicated block that has to
    stay in step, so any change to a residual definition there has to be made
    here too, and the feature names are asserted against a corpus at the end of
    a run so a drift is caught rather than assumed absent.

    `road_length` is this project's road loop. The self test passes it so the
    two claim differences are unwrapped exactly as the feature builder does;
    VeReMi is a city map with no seam and passes nothing.
    """
    rx = rx.sort_values(["rxNodeId", "claimedStationId", "rxTimeMs"]).copy()
    g = rx.groupby(["rxNodeId", "claimedStationId"], sort=False)

    rx["claimedDist"] = np.hypot(rx.claimedX - rx.rxX, rx.claimedY - rx.rxY)
    rx["dt"] = g.rxTimeMs.diff() / 1000.0
    rx["dClaimedX"] = _unwrap(g.claimedX.diff(), road_length)
    rx["dClaimedY"] = g.claimedY.diff()
    rx["claimedMoved"] = np.hypot(rx.dClaimedX, rx.dClaimedY)

    prev_speed = g.claimedSpeed.shift()
    rx["dmv_residual"] = rx.claimedMoved - prev_speed * rx.dt
    implied_speed = rx.claimedMoved / rx.dt.replace(0, np.nan)
    rx["ssc_residual"] = implied_speed - rx.claimedSpeed

    prev_heading_rad = np.deg2rad(g.claimedHeading.shift())
    pred_x = g.claimedX.shift() + prev_speed * rx.dt * np.sin(prev_heading_rad)
    pred_y = g.claimedY.shift() + prev_speed * rx.dt * np.cos(prev_heading_rad)
    rx["predict_residual"] = np.hypot(_unwrap(rx.claimedX - pred_x, road_length),
                                      rx.claimedY - pred_y)

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
    ap.add_argument("veremi_dir", nargs="*",
                    help="one or more VeReMi simulation directories. Several "
                         "are merged, with receiver and sender identifiers "
                         "namespaced per directory so two runs cannot put "
                         "different vehicles under one identifier")
    ap.add_argument("--corpus", required=True,
                    help="this project's corpus, for the paired comparison")
    ap.add_argument("--selftest", nargs=2, metavar=("RUN_DIR", "TAG"),
                    help="skip VeReMi and instead prove the feature "
                         "definitions here match build_features.py, by "
                         "recomputing them from this project's own receive log")
    ap.add_argument("--nextgen", action="store_true",
                    help="the directories are VeReMi NextGen scenarios (one "
                         "JSON array per receiver, the attacker flag inside "
                         "each record) rather than the original or Extension "
                         "layout")
    ap.add_argument("--limit-receivers", type=int, default=None)
    ap.add_argument("--sample", type=int, default=400000)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    if a.selftest:
        raise SystemExit(selftest(a.selftest[0], a.selftest[1], a.corpus))
    if not a.veremi_dir:
        ap.error("give one or more VeReMi directories, or --selftest RUN_DIR TAG")

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.metrics import f1_score, matthews_corrcoef

    print("invocation: " + " ".join(shlex.quote(s) for s in sys.argv))
    print("VeReMi NextGen" if a.nextgen else "VeReMi")
    frames = []
    for i, d in enumerate(a.veremi_dir):
        print(f"\n[{i}] {pathlib.Path(d).resolve()}")
        f = (load_nextgen(d, a.limit_receivers) if a.nextgen
             else load_veremi(d, a.limit_receivers))
        # Namespace per simulation. Two VeReMi runs both number their vehicles
        # from zero, so merging them naively would put different vehicles under
        # one identifier and break every grouped fold, which is the same trap
        # merge_corpora.py guards against on this project's own seeds.
        f["rxNodeId"] += i * 100000
        f["claimedStationId"] += i * 100000
        f["msgUid"] += i * 10000000
        frames.append(f)
    # Two scenarios built on the same traffic trace are the same experiment
    # twice. NextGen's attack variants are all generated from one InTAS run, so
    # the same vehicle appears at the same position in every one of them, and
    # namespacing their identifiers to avoid a clash makes one vehicle look
    # like two and puts its twin on the other side of a grouped fold. That is
    # verbatim train and test overlap, and it is the same defect that
    # offset_floor.py refuses on this project's own campaigns.
    if len(frames) > 1:
        prints = []
        for f in frames:
            b = f[f.label_attackId == 0]
            prints.append(set(map(tuple, b[["claimedX", "claimedY"]]
                                  .round(2).drop_duplicates()
                                  .head(4000).to_numpy())))
        # Twins share essentially every position; distinct traces on a city map
        # share a few, because SUMO stops queued vehicles at identical stop line
        # coordinates. Measured on the original release: type 1 repetitions 0
        # and 1, distinct traces, share 37 of 4,000; type 1 and type 2 of
        # repetition 0, one trace, share 4,000 of 4,000. A fixed count of 20
        # refused the distinct pair, so the limit is half the fingerprint.
        for i in range(len(prints)):
            for j in range(i + 1, len(prints)):
                shared = prints[i] & prints[j]
                size = min(len(prints[i]), len(prints[j]))
                print(f"twin check {i} and {j}: {len(shared)} of {size} "
                      f"benign positions shared")
                if len(shared) > 0.5 * size:
                    raise SystemExit(
                        f"REFUSED: simulations {i} and {j} share "
                        f"{len(shared)} benign positions to the centimetre, so "
                        f"they are the same traffic trace with different\n"
                        f"attacks applied. Merging them and renumbering the "
                        f"vehicles would put one vehicle's twin on the other "
                        f"side of a grouped fold. Run each scenario on its own.")
    raw = pd.concat(frames, ignore_index=True)
    if len(a.veremi_dir) > 1:
        print(f"\nmerged {len(a.veremi_dir)} simulations: {len(raw):,} "
              f"receptions, {raw.claimedStationId.nunique()} senders")
    vm = residuals_and_windows(raw)
    feats = transferable(vm)

    # BOTH sides are sampled to the same budget. Sampling one and not the
    # other makes the arms differ in the amount of data as well as in the
    # dataset, which is the confound that would make any difference between
    # them unreadable. It is also faster, and the comparison does not need
    # four decimal places, it needs to know whether the score is near zero.
    if a.sample and len(vm) > a.sample:
        vm = vm.sample(n=a.sample, random_state=0).reset_index(drop=True)
    print(f"{len(vm):,} windows, {len(feats)} transferable features")

    ours = pd.read_pickle(a.corpus)
    if "label_clean" in ours.columns:
        ours = ours[ours.label_clean == 1]
    # The corpus arm gets the SAME number of windows as the VeReMi side, which
    # is the smaller when VeReMi is small, so the arms differ in dataset and
    # not in data volume.
    if len(ours) > len(vm):
        ours = ours.sample(n=len(vm), random_state=0)
    print(f"corpus sampled to {len(ours):,} windows, the VeReMi budget")
    # The observation unit differs and the reader should see by how much. A
    # 1000 ms window holds one VeReMi beacon at 1 Hz, so its spread features are
    # empty there and informative here; that favours the corpus arm.
    print(f"messages per window: VeReMi {vm.app_n_msgs.mean():.2f}, "
          f"this corpus {ours.app_n_msgs.mean():.2f}\n")
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
        f1s, mccs, imps = [], [], []
        for tr, te in sg.split(X, y, groups):
            clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=a.jobs,
                                         random_state=0)
            clf.fit(X[tr], y[tr])
            p = clf.predict(X[te])
            f1s.append(f1_score(y[te], p, average="binary", zero_division=0))
            mccs.append(matthews_corrcoef(y[te], p))
            imps.append(clf.feature_importances_)
        print(f"{name:34s} {len(sub):>9,} windows  "
              f"{int(sub.label_txNodeId.nunique()):>4} stations  "
              f"{int((sub.label_attackId != benign).sum()):>8,} attack rows  "
              f"F1 {np.mean(f1s):.4f} +/- {np.std(f1s):.4f}  "
              f"MCC {np.mean(mccs):.4f}")
        # What the model separates on, so a score can be read as range
        # plausibility or as self consistency rather than guessed at.
        imp = pd.Series(np.mean(imps, axis=0), index=feats).sort_values(
            ascending=False)
        print("    most important: " + ", ".join(
            f"{k} {v:.3f}" for k, v in imp.head(3).items()))
        att = (sub.label_attackId != benign).values
        for col in ("app_claimed_dist_mean", "app_dmv_mean"):
            vals = sub[col].abs()
            print(f"    median |{col}|: benign {vals[~att].median():.4f}, "
                  f"attack {vals[att].median():.4f}")
        return float(np.mean(f1s))

    print("position falsification against benign, application layer only, the "
          "same\nseventeen features and the same model throughout\n")

    # The positive control first, because it is what makes the negative result
    # readable. A fixed claimed position contradicts the claimed speed in every
    # consecutive pair of messages, so the self consistency features should
    # catch it. If they do not, they are broken and nothing below means
    # anything.
    #
    # Each arm runs only if its attack is in the input. VeReMi runs a trace once
    # per attack type, so a type 1 run and a type 2 run of the same repetition
    # share every benign vehicle and the twin guard above refuses them together.
    # The control and the offset are therefore separate invocations on separate
    # directories, and the corpus arm, which is the comparison for the offset,
    # runs with the offset.
    def present(classes):
        return bool(vm.label_attackId.isin(list(classes)).any())

    c = v = o = None
    if present(SELF_INCONSISTENT):
        c = run(vm, "VeReMi, RANDOM offset (control)" if a.nextgen
                else "VeReMi, FIXED position (control)", SELF_INCONSISTENT)
    if present(CONST_OFFSET):
        v = run(vm, "VeReMi, constant OFFSET", CONST_OFFSET)
        o = run(ours, "this corpus, constant OFFSET", {1, 11, 13})
    if c is None and v is None:
        raise SystemExit("neither VeReMi ConstPos (1) nor ConstPosOffset (2) "
                         "senders are in the input, so there is nothing to run")
    print("\n" + ", ".join(f"{n} {x:.4f}" for n, x in
                           [("control", c), ("VeReMi offset", v),
                            ("this corpus", o)] if x is not None))
    print("\nReading: the control shows the seventeen features can catch a "
          "self inconsistent\nposition lie on VeReMi. The offset arms ask "
          "whether a self consistent one is caught\non either dataset. This "
          "is a BINARY task over seventeen features, constant offset\n"
          "attackers against benign on the subset both datasets support, and "
          "is not the same\nnumber as the per class figure in the cross "
          "layer benchmark.")


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
    lf = pathlib.Path(run_dir) / "road_length_m"
    mine = residuals_and_windows(
        rx, road_length=float(lf.read_text()) if lf.exists() else None)

    corpus = pd.read_pickle(corpus_path).copy()
    feats = transferable(mine)
    key = ["key_rxNodeId", "key_claimedStationId", "key_window"]

    # build_corpus.py namespaces receiver identifiers per seed by adding a
    # multiple of 100000, so a single-seed corpus carries an offset the raw log
    # does not. Recover it from the data rather than hardcoding it: the
    # multiple is the seed's label today (pooled_consensus.seed_offset) and was
    # its position in the build order before 19 Sep, and corpora of both ages
    # exist.
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
