#!/usr/bin/env python3
"""
Does attack A1 damage its neighbours, or only itself?

A1 disables the mode 2 sensing procedure on the attacker's MAC. The intended
effect is that the attacker selects resources its neighbours have reserved, so
the VICTIMS collide. Measuring corruption on the attacker's own transmissions
does not show that; it shows the attacker being unlucky. This script measures
the effect where it should appear: on benign to benign links, as a function of
the receiver's distance to the nearest attacker.

Usage: a1_victim_effect.py <run_dir> <tag>
"""
import sys
import numpy as np
import pandas as pd

def load(run_dir, tag):
    r = lambda n: pd.read_csv(f"{run_dir}/{n}_{tag}.csv")
    return r("stations"), r("tx"), r("rx_pssch"), r("tx_pssch")

def victim_effect(run_dir, tag, attack_id=8, sample=120000):
    st, tx, pssch, txp = load(run_dir, tag)
    att = set(st[st.attackId == attack_id].nodeId)
    if not att:
        return None

    rnti2node = {v: k for k, v in
                 txp.groupby("txNodeId").rnti.agg(lambda s: s.mode()[0]).items()}
    pssch["txNodeId"] = pssch.txRnti.map(rnti2node)

    pos = tx[["txNodeId", "txTimeMs", "trueX", "trueY"]].sort_values("txTimeMs")
    idx = {n: (d.txTimeMs.values, d.trueX.values, d.trueY.values)
           for n, d in pos.groupby("txNodeId")}

    def pos_at(nid, t):
        if nid not in idx:
            return None
        ts, xs, ys = idx[nid]
        i = min(max(np.searchsorted(ts, t), 0), len(ts) - 1)
        return xs[i], ys[i]

    s = pssch[(~pssch.txNodeId.isin(att)) & (~pssch.rxNodeId.isin(att))]
    s = s.dropna(subset=["txNodeId"])
    if len(s) > sample:
        s = s.sample(n=sample, random_state=0)

    att_l = sorted(att)
    def nearest(rx, t):
        p = pos_at(rx, t)
        if p is None:
            return np.nan
        best = np.inf
        for a in att_l:
            q = pos_at(a, t)
            if q is not None:
                best = min(best, float(np.hypot(p[0] - q[0], p[1] - q[1])))
        return best

    s = s.assign(dAtt=[nearest(r, t) for r, t in zip(s.rxNodeId, s.timeMs)])
    s = s.dropna(subset=["dAtt"])
    s["band"] = pd.cut(s.dAtt, [0, 50, 100, 150, 250, 10000])
    return s.groupby("band", observed=True).agg(
        n=("corrupt", "size"), corruptRate=("corrupt", "mean"),
        sinrMedian=("sinr", "median"))

if __name__ == "__main__":
    print(victim_effect(sys.argv[1], sys.argv[2]))
