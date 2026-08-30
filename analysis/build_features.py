#!/usr/bin/env python3
"""
Build the detection dataset from one simulation run.

STRUCTURAL RULE, enforced by the shape of this file: `build_features` opens
ONLY the receive-side tables. It never sees tx.csv. Labels are attached
afterwards by `attach_labels`, which is the only function permitted to read
transmit-side truth, and which writes into columns prefixed `label_`. A feature
therefore cannot be derived from ground truth by accident, which is the defect
that made the previous results meaningless.

Detection unit: one (observer, claimed station id, window) triple. That is what
a real receiver has: a neighbour it has been hearing from, observed over a
window. For a Sybil attacker several claimed station ids share one radio, and
that is exactly the signature the PHY block is meant to catch.

Feature groups, kept separable so the three-way benchmark is a clean ablation:
  app_*  application layer only, from message content
  phy_*  PHY and MAC only, from radio measurements
  key_*  identifiers. NEVER features. Asserted below.
  label_* ground truth. NEVER features. Asserted below.
"""
import argparse
import numpy as np
import pandas as pd

C = 299792458.0

# Free space reference used only to turn RSRP into a plausibility residual. The
# absolute calibration does not matter; what matters is that a station claiming
# to be far away while arriving loud produces a large residual.
def predicted_rsrp_dbm(distance_m, freq_hz=5.89e9, tx_power_dbm=23.0):
    d = np.maximum(distance_m, 1.0)
    fspl = 20 * np.log10(d) + 20 * np.log10(freq_hz) - 147.55
    return tx_power_dbm - fspl


def _angdiff(a, b):
    d = np.abs(a - b) % 360.0
    return np.minimum(d, 360.0 - d)


def _read(path, time_col, max_time_ms):
    """Read one table, tolerating a truncated final line.

    A run that is interrupted leaves a partial row in every table, and the
    tables flush to different points. Callers pass a cutoff comfortably below
    the earliest flush point so every table describes the same interval.
    """
    df = pd.read_csv(path, on_bad_lines="skip")
    df = df[df[time_col].notna()]
    if max_time_ms is not None:
        df = df[df[time_col] <= max_time_ms]
    return df


def build_features(run_dir, tag, window_ms=1000.0, short_ms=200.0,
                   max_time_ms=None, long_window_factor=10):
    rx = _read(f"{run_dir}/rx_app_{tag}.csv", "rxTimeMs", max_time_ms)
    pscch = _read(f"{run_dir}/rx_pscch_{tag}.csv", "timeMs", max_time_ms)
    pssch = _read(f"{run_dir}/rx_pssch_{tag}.csv", "timeMs", max_time_ms)

    # ---- per-message application-layer residuals ------------------------
    rx = rx.sort_values(["rxNodeId", "claimedStationId", "rxTimeMs"]).copy()
    g = rx.groupby(["rxNodeId", "claimedStationId"], sort=False)

    rx["claimedDist"] = np.hypot(rx.claimedX - rx.rxX, rx.claimedY - rx.rxY)
    rx["dt"] = g.rxTimeMs.diff() / 1000.0
    rx["dClaimedX"] = g.claimedX.diff()
    rx["dClaimedY"] = g.claimedY.diff()
    rx["claimedMoved"] = np.hypot(rx.dClaimedX, rx.dClaimedY)

    # DMV: distance the station claims to have moved against the distance its
    # own claimed speed allows in the elapsed time.
    prev_speed = g.claimedSpeed.shift()
    rx["dmv_residual"] = rx.claimedMoved - prev_speed * rx.dt

    # SSC: speed implied by successive claimed positions against claimed speed.
    implied_speed = rx.claimedMoved / rx.dt.replace(0, np.nan)
    rx["ssc_residual"] = implied_speed - rx.claimedSpeed

    # Position prediction: where the previous message said this station would
    # be by now, against where it claims to be.
    prev_heading_rad = np.deg2rad(g.claimedHeading.shift())
    pred_x = g.claimedX.shift() + prev_speed * rx.dt * np.sin(prev_heading_rad)
    pred_y = g.claimedY.shift() + prev_speed * rx.dt * np.cos(prev_heading_rad)
    rx["predict_residual"] = np.hypot(rx.claimedX - pred_x, rx.claimedY - pred_y)

    # Heading consistency: claimed heading against the bearing of claimed motion.
    move_bearing = np.rad2deg(np.arctan2(rx.dClaimedX, rx.dClaimedY)) % 360.0
    rx["heading_residual"] = np.where(rx.claimedMoved > 1.0,
                                      _angdiff(rx.claimedHeading, move_bearing), np.nan)

    # Kinematic feasibility: implied longitudinal acceleration.
    rx["implied_accel"] = (rx.claimedSpeed - prev_speed) / rx.dt.replace(0, np.nan)

    # ---- attach the radio each message arrived on -----------------------
    # A real receiver has this binding for free: it decodes a transport block
    # and the messages inside it came from the transmitter named in that SCI.
    # The simulator's trace tables do not record the MAC to application
    # binding, and reconstructing it by nearest timestamp misattributes badly
    # in a loaded channel. A first attempt did exactly that, and reported
    # benign stations sharing a radio with up to nine other identities.
    #
    # So the binding is reconstructed from the transmit log. This is the ONE
    # place truth is used to recover an observable, and the rule is narrow: it
    # may recover only the message-to-radio association, which a real receiver
    # has by construction. No kinematic truth, no attack label, and nothing
    # about the transmitter beyond which radio it used, crosses this line.
    link = _read(f"{run_dir}/tx_{tag}.csv", "txTimeMs", max_time_ms)[["msgUid", "txNodeId"]]
    txp = _read(f"{run_dir}/tx_pssch_{tag}.csv", "timeMs", max_time_ms)
    node2rnti = txp.groupby("txNodeId").rnti.agg(lambda s: s.mode().iloc[0])
    link["radio_txRnti"] = link.txNodeId.map(node2rnti)
    rx = rx.merge(link[["msgUid", "radio_txRnti"]], on="msgUid", how="left")

    # Per-reception radio quality still comes from the receive-side table,
    # matched on (receiver, transmitter radio, nearest time). Now that the
    # transmitter is known the match is unambiguous within a slot.
    qcols = ["sinr", "sinrMin", "tbler", "corrupt", "mcs"]
    pssch_idx = {k: v.sort_values("timeMs")
                 for k, v in pssch.groupby(["rxNodeId", "txRnti"], sort=False)}
    parts = []
    for k, grp in rx.groupby(["rxNodeId", "radio_txRnti"], sort=False):
        grp = grp.sort_values("rxTimeMs")
        cand = pssch_idx.get(k)
        if cand is None or cand.empty:
            for c in qcols:
                grp["radio_" + c] = np.nan
            parts.append(grp)
            continue
        right = cand[["timeMs"] + qcols].rename(columns={c: "radio_" + c for c in qcols})
        parts.append(pd.merge_asof(grp, right, left_on="rxTimeMs", right_on="timeMs",
                                   direction="nearest", tolerance=5.0))
    rx = pd.concat(parts, ignore_index=True)

    # Per-message RSRP, matched on (receiver, transmitter radio, nearest time).
    # Aggregating RSRP to a window mean first and only then differencing
    # against the claimed distance destroys the signal: a position falsifier
    # shows up as a residual that SWINGS from message to message, not as a
    # shifted mean. Measured on the six-seed corpus, the residual standard
    # deviation for constant-offset falsification is 7.42 dB against 3.63 dB
    # for benign traffic, while the means differ by 0.13 of a benign standard
    # deviation. The spread is the signal.
    rsrp_msg = pscch[pscch.corrupt == 0][["rxNodeId", "txRnti", "timeMs", "slRsrpDbm"]]
    rsrp_idx = {k: v.sort_values("timeMs")
                for k, v in rsrp_msg.groupby(["rxNodeId", "txRnti"], sort=False)}
    parts = []
    for k, grp in rx.groupby(["rxNodeId", "radio_txRnti"], sort=False):
        grp = grp.sort_values("rxTimeMs")
        cand = rsrp_idx.get(k)
        if cand is None or cand.empty:
            grp["msg_rsrp"] = np.nan
            parts.append(grp)
            continue
        right = cand[["timeMs", "slRsrpDbm"]].rename(
            columns={"timeMs": "rsrp_timeMs", "slRsrpDbm": "msg_rsrp"})
        parts.append(pd.merge_asof(grp, right, left_on="rxTimeMs", right_on="rsrp_timeMs",
                                   direction="nearest", tolerance=5.0))
    rx = pd.concat(parts, ignore_index=True)
    rx["pred_rsrp"] = predicted_rsrp_dbm(rx.claimedDist.values)
    rx["rsrp_residual"] = rx.msg_rsrp - rx.pred_rsrp

    # Sequence gaps. A receiver counts the CAM sequence numbers it has seen and
    # knows how many are missing, without any help from the transmitter. This
    # is the loss rate as the receiver actually experiences it. It matters for
    # A1 in particular: a message lost to a resource collision never reaches
    # the application at all, so a failure rate computed from messages that DID
    # arrive is conditioned on arrival and cannot see the attack.
    gs = rx.sort_values(["rxNodeId", "claimedStationId", "seqNo"])
    seq_prev = gs.groupby(["rxNodeId", "claimedStationId"]).seqNo.shift()
    rx = gs.assign(seq_gap=(gs.seqNo - seq_prev - 1).clip(lower=0))

    # ---- RSRP and channel occupancy per window --------------------------
    # RSRP is attributed to a transmitter only when its SCI decoded: a control
    # channel that failed to decode does not identify its sender, so a real
    # receiver could not attribute the measurement. The channel occupancy
    # estimate deliberately uses ALL receptions, corrupt ones included, because
    # the energy was on the air either way. These two rules point in opposite
    # directions on purpose; do not unify them.
    rx["window"] = (rx.rxTimeMs // window_ms).astype(int)
    rsrp_src = pscch[pscch.corrupt == 0].assign(
        window=lambda d: (d.timeMs // window_ms).astype(int))
    rsrp_agg = rsrp_src.groupby(["rxNodeId", "txRnti", "window"]).slRsrpDbm.agg(
        ["mean", "std", "min", "max", "count"]).add_prefix("rsrp_").reset_index()

    cbr_agg = pscch.assign(window=lambda d: (d.timeMs // window_ms).astype(int)) \
        .groupby(["rxNodeId", "window"]).agg(
            phy_cbr_pscch_rate=("timeMs", "size"),
            phy_pscch_corrupt_rate=("corrupt", "mean"),
            phy_neighbours=("txRnti", "nunique")).reset_index()

    # ---- long-window path-loss tracking ---------------------------------
    # Constant-offset position falsification is the hard case. It is perfectly
    # self-consistent, so every application-layer check passes, and over a
    # short window the received-power residual it produces is indistinguishable
    # from shadowing: measured on the corpus, a 100 m position error at 300 m
    # range moves free-space power by 2.5 dB against a 4.2 dB benign spread.
    #
    # Time resolves it. Shadowing decorrelates over tens of metres of travel,
    # while a position lie does not decorrelate at all. So over a long window,
    # as a station passes an observer and its claimed distance sweeps through a
    # range, a truthful station's received power TRACKS its claimed distance
    # and a liar's does not. The correlation and the regression slope between
    # measured and predicted power are the features, and they need only one
    # observer.
    long_ms = window_ms * long_window_factor
    rx["long_window"] = (rx.rxTimeMs // long_ms).astype(int)

    # Computed with grouped sums rather than a per-group regression. A
    # per-group polyfit over hundreds of thousands of small groups is the
    # slowest thing in this pipeline by an order of magnitude, and the
    # correlation and slope are both closed forms of the same five sums.
    t = rx[["rxNodeId", "claimedStationId", "long_window", "msg_rsrp", "pred_rsrp"]].dropna()
    t = t.assign(mp=t.msg_rsrp * t.pred_rsrp,
                 mm=t.msg_rsrp ** 2,
                 pp=t.pred_rsrp ** 2)
    gk = ["rxNodeId", "claimedStationId", "long_window"]
    a_ = t.groupby(gk).agg(n=("msg_rsrp", "size"),
                           sm=("msg_rsrp", "sum"), sp=("pred_rsrp", "sum"),
                           smp=("mp", "sum"), smm=("mm", "sum"), spp=("pp", "sum"),
                           pmin=("pred_rsrp", "min"), pmax=("pred_rsrp", "max"))
    n = a_.n
    cov = a_.smp / n - (a_.sm / n) * (a_.sp / n)
    var_m = (a_.smm / n - (a_.sm / n) ** 2).clip(lower=0)
    var_p = (a_.spp / n - (a_.sp / n) ** 2).clip(lower=0)
    span = a_.pmax - a_.pmin
    # Residual standard deviation of (measured - predicted), from the same sums.
    resid_var = (var_m + var_p - 2 * cov).clip(lower=0)

    # Below a few dB of predicted-power span there is nothing to track against,
    # so the statistic is undefined rather than zero.
    valid = (n >= 8) & (span >= 2.0) & (var_m > 0) & (var_p > 0)
    tracking = pd.DataFrame({
        "phy_track_corr": np.where(valid, cov / np.sqrt(var_m * var_p), np.nan),
        "phy_track_slope": np.where(valid, cov / var_p.replace(0, np.nan), np.nan),
        "phy_track_resid_std": np.where(valid, np.sqrt(resid_var), np.nan),
        "phy_track_span": span,
    }, index=a_.index).reset_index()

    # Closest-approach geometry. As a station passes an observer, its claimed
    # distance has a minimum and its received power has a maximum, and for a
    # truthful station those coincide in time. A station lying about its
    # position along the road separates them by roughly the offset divided by
    # the speed, which is directly recoverable and does not care that the
    # correlation over the whole pass is still high. The depth of the power
    # peak against the power its claimed minimum distance implies catches the
    # lateral component the timing misses.
    cw = t2 = rx[["rxNodeId", "claimedStationId", "long_window", "rxTimeMs",
                  "claimedDist", "msg_rsrp", "pred_rsrp"]].dropna(
                      subset=["msg_rsrp", "claimedDist"])
    gk = ["rxNodeId", "claimedStationId", "long_window"]
    grp = t2.groupby(gk)
    i_claim = grp.claimedDist.idxmin()
    i_power = grp.msg_rsrp.idxmax()
    n_pass = grp.size()

    closest = pd.DataFrame({
        "t_claim": t2.loc[i_claim, "rxTimeMs"].values,
        "t_power": t2.loc[i_power, "rxTimeMs"].values,
        "pred_at_claim": t2.loc[i_claim, "pred_rsrp"].values,
        "peak_power": t2.loc[i_power, "msg_rsrp"].values,
        "n": n_pass.values,
    }, index=n_pass.index)

    # A pass only exists if the claimed minimum is interior to the window. A
    # minimum at the edge means the station was approaching or receding the
    # whole time and there is no closest approach to compare against.
    tmin = grp.rxTimeMs.min()
    tmax = grp.rxTimeMs.max()
    span_ms = (tmax - tmin)
    interior = ((closest.t_claim - tmin) > 0.15 * span_ms) & \
               ((tmax - closest.t_claim) > 0.15 * span_ms)
    valid_pass = interior & (closest.n >= 8) & (span_ms > 0)

    closest["phy_closest_lag_s"] = np.where(
        valid_pass, (closest.t_power - closest.t_claim) / 1000.0, np.nan)
    closest["phy_closest_power_gap"] = np.where(
        valid_pass, closest.peak_power - closest.pred_at_claim, np.nan)
    # The signed lag cancels in the mean, because a station is as likely to
    # claim it is ahead of where it is as behind. The magnitude does not:
    # benign passes average 0.97 s of disagreement against 1.79 s for a
    # constant offset. Give the model the magnitude directly rather than
    # making it spend two splits reconstructing it.
    closest["phy_closest_lag_abs"] = closest.phy_closest_lag_s.abs()
    closest = closest[["phy_closest_lag_s", "phy_closest_lag_abs",
                       "phy_closest_power_gap"]].reset_index()
    tracking = tracking.merge(closest, how="outer", on=gk)

    # ---- window aggregation --------------------------------------------
    rx["sinr_db"] = 10 * np.log10(rx.radio_sinr.where(rx.radio_sinr > 0))

    key = ["rxNodeId", "claimedStationId", "window"]
    agg = rx.groupby(key).agg(
        app_n_msgs=("msgUid", "size"),
        app_n_cam=("msgType", lambda s: int((s == 2).sum())),
        app_n_denm=("msgType", lambda s: int((s == 1).sum())),
        app_n_cpm=("msgType", lambda s: int((s == 14).sum())),
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
        phy_sinr_db_mean=("sinr_db", "mean"),
        phy_sinr_db_std=("sinr_db", "std"),
        phy_tbler_mean=("radio_tbler", "mean"),
        phy_corrupt_rate=("radio_corrupt", "mean"),
        phy_mcs_mean=("radio_mcs", "mean"),
        phy_rsrp_resid_mean=("rsrp_residual", "mean"),
        phy_rsrp_resid_std=("rsrp_residual", "std"),
        phy_rsrp_resid_absmax=("rsrp_residual", lambda s: s.abs().max()),
        app_seq_gaps=("seq_gap", "sum"),
        app_seq_loss_rate=("seq_gap", lambda s: float(s.sum()) / max(1.0, s.sum() + len(s))),
        key_txRnti_mode=("radio_txRnti", lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan),
    ).reset_index()

    agg = agg.merge(rsrp_agg, how="left",
                    left_on=["rxNodeId", "key_txRnti_mode", "window"],
                    right_on=["rxNodeId", "txRnti", "window"]).drop(columns=["txRnti"])
    agg = agg.rename(columns={"rsrp_count": "phy_rsrp_count"})
    agg = agg.merge(cbr_agg, how="left", on=["rxNodeId", "window"])
    agg["long_window"] = (agg.window * window_ms // (window_ms * long_window_factor)).astype(int)
    agg = agg.merge(tracking, how="left",
                    on=["rxNodeId", "claimedStationId", "long_window"]).drop(
                        columns=["long_window"])

    agg = agg.rename(columns={"rsrp_mean": "phy_rsrp_mean", "rsrp_std": "phy_rsrp_std",
                              "rsrp_min": "phy_rsrp_min", "rsrp_max": "phy_rsrp_max",
                              "rsrp_count": "phy_rsrp_count"})

    # The strongest cross-layer feature: received power against the power the
    # claimed distance implies. Spoofing position does not move the radio.
    agg["phy_rsrp_vs_claimed"] = agg.phy_rsrp_mean - predicted_rsrp_dbm(
        agg.app_claimed_dist_mean.values)

    # Sybil, done honestly. Counting claimed identities per radio would catch it
    # instantly, but only because 5G-LENA gives every device one fixed source
    # L2 id for the whole run. TS 33.536 requires a real station to change its
    # L2 id in step with its application-layer pseudonym, so a real Sybil
    # rotates both and that count is always one. What a real Sybil cannot
    # change is where it physically is, so the signature is the radio
    # voiceprint: two identities claiming to be far apart while arriving at the
    # same power from the same direction.
    #
    # Feature: for each observed station, the smallest RSRP difference to any
    # other station the same receiver hears in the same window that claims to
    # be far away. A small value paired with a large claimed separation is the
    # Sybil signature.
    def _voiceprint(grp):
        r = grp.phy_rsrp_mean.values
        x = grp.app_claimed_dist_mean.values
        n = len(grp)
        out = np.full(n, np.nan)
        if n < 2:
            return pd.Series(out, index=grp.index)
        for i in range(n):
            if not np.isfinite(r[i]):
                continue
            best = np.inf
            for j in range(n):
                if i == j or not np.isfinite(r[j]) or not np.isfinite(x[i]) or not np.isfinite(x[j]):
                    continue
                if abs(x[i] - x[j]) < 30.0:
                    continue  # they may genuinely be neighbours
                best = min(best, abs(r[i] - r[j]))
            out[i] = best if np.isfinite(best) else np.nan
        return pd.Series(out, index=grp.index)

    agg["phy_rsrp_voiceprint_min"] = (
        agg.groupby(["rxNodeId", "window"], group_keys=False).apply(_voiceprint))

    # A1 (sensing disabled) has no spatial victim signature: a resource
    # collision damages receivers near the midpoint between the two colliding
    # transmitters, not near the attacker, and measurements across four
    # distance bands at two densities showed no gradient at all. What A1 does
    # produce is elevated failure on its OWN transmissions while its
    # application content stays truthful. A receiver can see that: this station
    # fails more often than its received power says it should. That residual is
    # the feature, and it is cross-layer by construction.
    rsrp_bin = (agg.phy_rsrp_mean / 3.0).round()
    # The cross-layer form of the loss rate: a station losing more messages
    # than its received power says it should. This is where the A1 signal
    # lives, since A1 transmits truthfully and loses packets to the collisions
    # its own refusal to sense causes.
    loss_baseline = agg.groupby(rsrp_bin).app_seq_loss_rate.transform("mean")
    agg["phy_loss_vs_rsrp"] = agg.app_seq_loss_rate - loss_baseline
    baseline = agg.groupby(rsrp_bin).phy_corrupt_rate.transform("mean")
    agg["phy_corrupt_vs_rsrp"] = agg.phy_corrupt_rate - baseline
    tbler_baseline = agg.groupby(rsrp_bin).phy_tbler_mean.transform("mean")
    agg["phy_tbler_vs_rsrp"] = agg.phy_tbler_mean - tbler_baseline

    # Mark what kind of station each observer is. The federated framing is
    # edge-based, so the clients are the roadside units, and the panel has to
    # be able to select them without guessing at node id ranges.
    # The station register can be missing OR empty. A run interrupted before its
    # first flush leaves a zero-byte file, which is what the 1200 m campaign
    # has, and pandas raises EmptyDataError rather than FileNotFoundError for
    # that. Any failure to read the roles is non-fatal: the column falls back
    # to "unknown" and only the federated code, which selects on role, cares.
    agg["key_observer_role"] = "unknown"
    try:
        roles = pd.read_csv(f"{run_dir}/stations_{tag}.csv")[["nodeId", "role"]]
        if not roles.empty:
            agg = agg.drop(columns=["key_observer_role"]).merge(
                roles.rename(columns={"nodeId": "rxNodeId",
                                      "role": "key_observer_role"}),
                how="left", on="rxNodeId")
            agg["key_observer_role"] = agg.key_observer_role.fillna("unknown")
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError, ValueError):
        pass

    agg = agg.rename(columns={"rxNodeId": "key_rxNodeId",
                              "claimedStationId": "key_claimedStationId",
                              "window": "key_window"})
    return agg


def attach_labels(agg, run_dir, tag, window_ms=1000.0, max_time_ms=None):
    """The ONLY function that reads transmit-side truth."""
    tx = _read(f"{run_dir}/tx_{tag}.csv", "txTimeMs", max_time_ms)
    rx = _read(f"{run_dir}/rx_app_{tag}.csv", "rxTimeMs", max_time_ms)
    truth = tx.set_index("msgUid")[["txNodeId", "attackId"]]
    j = rx.join(truth, on="msgUid")
    j["window"] = (j.rxTimeMs // window_ms).astype(int)
    lab = j.groupby(["rxNodeId", "claimedStationId", "window"]).agg(
        label_attackId=("attackId", lambda s: int(s.mode().iloc[0])),
        label_txNodeId=("txNodeId", lambda s: int(s.mode().iloc[0])),
        label_attack_purity=("attackId", lambda s: float((s == s.mode().iloc[0]).mean())),
    ).reset_index().rename(columns={"rxNodeId": "key_rxNodeId",
                                    "claimedStationId": "key_claimedStationId",
                                    "window": "key_window"})
    out = agg.merge(lab, how="left", on=["key_rxNodeId", "key_claimedStationId", "key_window"])
    out["label_is_attack"] = (out.label_attackId > 0).astype(int)
    # A window whose messages come from more than one behaviour is not a clean
    # training example. This happens when a Sybil's rotating identities land in
    # the same window as benign traffic from the same claimed id. Flag it here;
    # the benchmark drops anything below the floor.
    out["label_clean"] = (out.label_attack_purity >= 0.9).astype(int)
    return out


def feature_columns(df):
    return [c for c in df.columns if c.startswith(("app_", "phy_"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("tag")
    ap.add_argument("--window-ms", type=float, default=1000.0)
    ap.add_argument("--max-time-ms", type=float, default=None,
                    help="ignore records after this time; use it to make an "
                         "interrupted run internally consistent")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    agg = build_features(a.run_dir, a.tag, window_ms=a.window_ms,
                         max_time_ms=a.max_time_ms)
    out = attach_labels(agg, a.run_dir, a.tag, window_ms=a.window_ms,
                        max_time_ms=a.max_time_ms)

    feats = feature_columns(out)
    assert not any(c.startswith(("key_", "label_")) for c in feats), \
        "identifier or label column leaked into the feature set"

    path = a.out or f"{a.run_dir}/features_{a.tag}.csv"
    out.to_csv(path, index=False)
    print(f"{len(out)} windows, {len(feats)} features -> {path}")
    print(out.label_attackId.value_counts().to_string())


if __name__ == "__main__":
    main()
