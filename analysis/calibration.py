#!/usr/bin/env python3
"""
Simulation calibration curves.

The three curves a reviewer will look for in an NR sidelink study, per the
evaluation methodology in 3GPP TR 37.885:

  1. Packet reception ratio against transmitter-receiver distance
  2. Block error rate against SINR
  3. Channel occupancy against vehicle density

and a fourth that is specific to this dataset: received power against distance,
because the cross-layer features rest on it.

None of these involve the detector. They are about whether the radio layer
behaves like a radio. A dataset built on a simulator that does not produce a
physically sensible PRR curve is not worth the detection results computed from
it, and the curves are cheap to produce from the tables already written.

Usage: calibration.py <run_dir> <tag> [--max-time-ms N]
"""
import argparse
import numpy as np
import pandas as pd


def load(run_dir, tag, max_time_ms=None):
    def rd(name, tcol):
        df = pd.read_csv(f"{run_dir}/{name}_{tag}.csv", on_bad_lines="skip")
        df = df[df[tcol].notna()]
        return df[df[tcol] <= max_time_ms] if max_time_ms else df
    return (rd("tx", "txTimeMs"), rd("rx_app", "rxTimeMs"),
            rd("rx_pssch", "timeMs"), rd("rx_pscch", "timeMs"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("tag")
    ap.add_argument("--max-time-ms", type=float, default=None)
    ap.add_argument("--sample", type=int, default=400000)
    a = ap.parse_args()

    tx, rx, pssch, pscch = load(a.run_dir, a.tag, a.max_time_ms)

    # ---- 1. PRR against distance ---------------------------------------
    # For every transmitted message and every station that could have heard
    # it, did it arrive? The denominator is what makes this a PRR rather than
    # a delivery count: it counts the receivers that were in range and silent.
    stations = sorted(set(tx.txNodeId.unique()))
    pos = tx[["txNodeId", "txTimeMs", "trueX", "trueY"]].sort_values("txTimeMs")
    idx = {n: (d.txTimeMs.values, d.trueX.values, d.trueY.values)
           for n, d in pos.groupby("txNodeId")}

    def at(n, t):
        if n not in idx:
            return None
        ts, xs, ys = idx[n]
        i = min(max(np.searchsorted(ts, t), 0), len(ts) - 1)
        return xs[i], ys[i]

    got = set(zip(rx.msgUid, rx.rxNodeId))
    sample = tx.sample(n=min(a.sample // max(1, len(stations)), len(tx)), random_state=0)

    rows = []
    for uid, sender, t, sx, sy in zip(sample.msgUid, sample.txNodeId, sample.txTimeMs,
                                      sample.trueX, sample.trueY):
        for r in stations:
            if r == sender:
                continue
            p = at(r, t)
            if p is None:
                continue
            d = float(np.hypot(sx - p[0], sy - p[1]))
            rows.append((d, (uid, r) in got))
    prr = pd.DataFrame(rows, columns=["d", "ok"])
    prr["band"] = pd.cut(prr.d, [0, 50, 100, 150, 200, 300, 400, 500, 750, 1000, 1e9])
    print("1. PRR against distance")
    print(prr.groupby("band", observed=True).agg(
        pairs=("ok", "size"), prr=("ok", "mean")).round(4).to_string())

    # ---- 2. BLER against SINR ------------------------------------------
    p = pssch[(pssch.sinr > 0)].copy()
    p["sinr_db"] = 10 * np.log10(p.sinr)
    p["band"] = pd.cut(p.sinr_db, [-20, -10, -5, 0, 5, 10, 15, 20, 30, 100])
    print("\n2. Block error rate against SINR")
    print(p.groupby("band", observed=True).agg(
        n=("corrupt", "size"), bler=("corrupt", "mean"),
        mean_tbler=("tbler", "mean")).round(4).to_string())

    # ---- 3. Channel occupancy ------------------------------------------
    print("\n3. Channel occupancy as the transmitters saw it")
    print(f"   CBR estimate: mean {tx.txCbr.mean():.3f}, median {tx.txCbr.median():.3f}, "
          f"p95 {tx.txCbr.quantile(0.95):.3f}, max {tx.txCbr.max():.3f}")
    print(f"   stations {tx.txNodeId.nunique()}, "
          f"messages {len(tx)}, "
          f"mean rate {len(tx) / tx.txNodeId.nunique() / ((tx.txTimeMs.max() - tx.txTimeMs.min()) / 1000):.2f} Hz")

    # ---- 4. Received power against distance ----------------------------
    # The RSRP the patch exposes must fall with distance at roughly the rate
    # the channel model sets, or the strongest feature measures nothing
    # physical. Every decoded control channel is placed at the true distance
    # between its radio and the receiver at that instant, and the median power
    # per distance band is fitted against 10 log10(d). Corrupt receptions are
    # left out, as build_features.py leaves them out: a receiver cannot read
    # power from a channel it did not decode.
    print("\n4. SL-RSRP against distance, decoded control channels only")
    txp = pd.read_csv(f"{a.run_dir}/tx_pssch_{a.tag}.csv", usecols=["txNodeId", "rnti"])
    rnti2node = txp.groupby("rnti").txNodeId.agg(lambda s: s.mode().iloc[0])
    ok = pscch[pscch.corrupt == 0]
    ok = ok.sample(n=min(200000, len(ok)), random_state=0)
    rpos = {n: (d.rxTimeMs.values, d.rxX.values, d.rxY.values)
            for n, d in rx[["rxNodeId", "rxTimeMs", "rxX", "rxY"]]
            .sort_values("rxTimeMs").groupby("rxNodeId")}

    def rx_at(n, t):
        if n not in rpos:
            return None
        ts, xs, ys = rpos[n]
        i = min(max(np.searchsorted(ts, t), 0), len(ts) - 1)
        return xs[i], ys[i]

    pts = []
    for r, rn, t, p_ in zip(ok.rxNodeId, ok.txRnti, ok.timeMs, ok.slRsrpDbm):
        s_ = rnti2node.get(rn)
        q, w = (at(s_, t) if s_ is not None else None), rx_at(r, t)
        if q is None or w is None:
            continue
        pts.append((float(np.hypot(q[0] - w[0], q[1] - w[1])), p_))
    pw = pd.DataFrame(pts, columns=["d", "rsrp"])
    pw = pw[pw.d > 1.0]
    print(f"   {len(pw):,} decoded channels placed, of {len(ok):,} sampled; "
          f"RSRP dBm min {pw.rsrp.min():.1f}, median {pw.rsrp.median():.1f}, "
          f"max {pw.rsrp.max():.1f}")
    pw["band"] = pd.cut(pw.d, [1, 25, 50, 100, 200, 300, 500, 750, 1000, 1e9])
    tab = pw.groupby("band", observed=True).agg(
        n=("rsrp", "size"), median_dbm=("rsrp", "median"),
        p10=("rsrp", lambda s: s.quantile(0.1)),
        p90=("rsrp", lambda s: s.quantile(0.9)))
    print(tab.round(1).to_string())
    fit = pw[(pw.d >= 10) & (pw.d <= 1000)]
    if len(fit) > 100:
        X = np.c_[np.ones(len(fit)), 10 * np.log10(fit.d.values)]
        b, *_ = np.linalg.lstsq(X, fit.rsrp.values, rcond=None)
        print(f"   least squares over 10 to 1000 m: RSRP = {b[0]:.1f} "
              f"{b[1]:+.2f} x 10 log10(d), an exponent of {-b[1]:.2f}. "
              f"Free space is 2.")

if __name__ == "__main__":
    main()
