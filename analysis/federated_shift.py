#!/usr/bin/env python3
"""
Does the federated detector survive a change of radio quality or of attacker
strategy, and can it be adapted? (REVIEW_FIX_PLAN 15.1, X2 and X3.)

The brief names four things that change under a deployed detector: traffic
patterns and density, radio quality, and attacker strategy. RESULTS 5j tests
density. This file tests the other two on the deployment's own client
structure, roadside unit regions, with the same arms as 5j:

  transfer        FedAvg on the source corpus's region clients, deployed
                  unchanged into the target corpus
  in-dist         FedAvg on the target corpus's region clients (the ceiling)
  mixed           FedAvg over both corpora's clients at the same row budget
  label-free      the transfer model with its input scaling refitted on the
                  target clients' unlabelled rows
  fine-tune k     the transfer model, then ft-rounds of FedAvg on k labelled
                  target clients
  label-free + fine-tune k
  scratch k       the same k clients and rounds from a fresh model (control)

THE SPLIT. The target corpora rerun the reference scenario's seeds, so they
contain the same physical vehicles (stations_seed*.csv identical). A split by
observer, or a hold-out drawn inside the target alone, would let the source
model train on vehicles that are scored in the target. So both corpora use the
frozen release partition: every arm trains on rows of TRAINING transmitters
only, and every arm is scored on target rows of TEST transmitters only. No arm
has seen a test vehicle labelled, in either corpus.

Scored per window (macro F1, MCC, benign F1) and per track: a track is one
claimed identity in one region over the run, and it raises an alert when the
detector calls 2 of 3 consecutive windows an attack. Tracks found (attack) and
tracks flagged (benign) are reported per arm.
"""
import argparse

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, matthews_corrcoef
from sklearn.preprocessing import StandardScaler

from federated import MLP, load_flat, run_method
from pooled_consensus import wilcoxon


def load(path, tag, obs_col):
    df = pd.read_pickle(path)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    df = df.reset_index(drop=True)
    df["corpus"] = tag
    df["client"] = tag + ":" + df[obs_col].astype(str)
    return df


def predict(gvec, X, cfg):
    m = MLP(cfg["d_in"], cfg["n_classes"])
    load_flat(m, gvec)
    m.eval()
    with torch.no_grad():
        return m(X).argmax(1).numpy()


def tracks(frame, pred, benign, k=2, m=3):
    """Share of attack tracks with an alert and of benign tracks with one, where
    an alert is k of the last m windows called an attack."""
    f = frame.assign(alarm=(pred != benign).astype(int))
    f = f.sort_values(["track", "key_window"])
    roll = f.groupby("track").alarm.transform(lambda s: s.rolling(m, min_periods=m).sum())
    hit = (roll >= k).groupby(f.track).any()
    is_att = f.groupby("track").is_attack.first()
    return float(hit[is_att].mean()), float(hit[~is_att].mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--split-file", required=True)
    ap.add_argument("--source-tag", default="reference")
    ap.add_argument("--target-tag", required=True)
    ap.add_argument("--observer-col", default="key_region")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=200)
    ap.add_argument("--local-epochs", type=int, default=2)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--budgets", type=int, nargs="+", default=[10])
    ap.add_argument("--ft-rounds", type=int, default=5)
    ap.add_argument("--drop-prefix", nargs="+", default=[],
                    help="leave out every feature starting with one of these, to "
                         "test which features carry a shift")
    a = ap.parse_args()

    src = load(a.source, a.source_tag, a.observer_col)
    tgt = load(a.target, a.target_tag, a.observer_col)
    shared = sorted(set(src.label_attackId) & set(tgt.label_attackId))
    src = src[src.label_attackId.isin(shared)]
    tgt = tgt[tgt.label_attackId.isin(shared)]
    feats = [c for c in src.columns
             if c.startswith(("app_", "phy_", "pool_")) and c in set(tgt.columns)]
    if a.drop_prefix:
        gone = [c for c in feats if c.startswith(tuple(a.drop_prefix))]
        feats = [c for c in feats if c not in gone]
        print(f"left out {len(gone)} features: {gone}")
    both = pd.concat([src, tgt], ignore_index=True)
    del src, tgt

    sp = pd.read_csv(a.split_file).drop_duplicates(["key_seed", "label_txNodeId"])
    part = both[["key_seed", "label_txNodeId"]].merge(
        sp[["key_seed", "label_txNodeId", "split"]], how="left",
        on=["key_seed", "label_txNodeId"]).split.values
    if pd.isna(part).any():
        raise SystemExit(f"{int(pd.isna(part).sum())} rows have no split")
    codes = pd.Categorical(both.label_attackId, categories=shared).codes
    X = both[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values.astype(np.float32)
    is_src = (both.corpus == a.source_tag).values
    is_tgt = ~is_src
    train = part == "train"
    test_mask = is_tgt & (part == "test")
    obs = both.client.values

    def clients_of(mask):
        out = []
        for o in pd.unique(obs[mask]):
            idx = np.flatnonzero(mask & (obs == o))
            if len(idx) >= a.min_rows:
                out.append(idx)
        return out

    src_idx = clients_of(is_src & train)
    tgt_idx = clients_of(is_tgt & train)
    n_src = sum(len(i) for i in src_idx)
    n_tgt = sum(len(i) for i in tgt_idx)
    budget = min(n_src, n_tgt)
    rng = np.random.RandomState(0)

    def thin(idx_lists, cap):
        total = sum(len(i) for i in idx_lists)
        if total <= cap:
            return idx_lists
        f = cap / total
        return [rng.choice(i, max(20, int(len(i) * f)), replace=False) for i in idx_lists]

    tr_idx = thin(src_idx, budget)
    in_idx = thin(tgt_idx, budget)
    mix_idx = thin(src_idx + tgt_idx, budget)

    n_cls = len(shared)
    benign = shared.index(0)
    cfg = dict(d_in=len(feats), n_classes=n_cls, embed_dim=32, lr=0.05,
               batch_size=128, local_epochs=a.local_epochs, rounds=a.rounds,
               participation=0.5, mu=0.01, tau=1.0, lam=0.1)
    test_frame = pd.DataFrame({
        "track": both.loc[test_mask, a.observer_col].astype(str).values + ":"
                 + both.loc[test_mask, "key_claimedStationId"].astype(str).values,
        "key_window": both.loc[test_mask, "key_window"].values,
        "is_attack": codes[test_mask] != benign})
    test_y = codes[test_mask]
    print(f"{n_cls} shared classes {shared}; {len(feats)} features")
    print(f"source {a.source_tag}: {len(src_idx)} region clients, {n_src:,} training rows; "
          f"target {a.target_tag}: {len(tgt_idx)} region clients, {n_tgt:,} training rows")
    print(f"row budget per arm {budget:,}; {int(test_mask.sum()):,} target test rows from "
          f"{len(set(both.loc[test_mask, 'label_txNodeId'].astype(str) + ':' + both.loc[test_mask, 'key_seed'].astype(str)))} "
          f"test transmitters, {test_frame.track.nunique()} tracks; frozen split, so no arm "
          f"trains on a test vehicle\n", flush=True)

    def pack(idx_lists, scaler):
        out = []
        for idx in idx_lists:
            xi = torch.tensor(scaler.transform(X[idx]).astype(np.float32))
            yi = torch.tensor(codes[idx], dtype=torch.long)
            out.append((xi, yi, torch.bincount(yi, minlength=n_cls)))
        return out

    def test_with(scaler):
        return (torch.tensor(scaler.transform(X[test_mask]).astype(np.float32)),
                torch.tensor(test_y, dtype=torch.long))

    sc_src = StandardScaler().fit(X[np.concatenate(tr_idx)])
    sc_in = StandardScaler().fit(X[np.concatenate(in_idx)])
    sc_mix = StandardScaler().fit(X[np.concatenate(mix_idx)])
    # Label-free: the target clients' own rows, labels never read.
    sc_lf = sc_in
    res, models = {}, {}

    def score(name, gvec, test, rows):
        pred = predict(gvec, test[0], cfg)
        f1 = f1_score(test_y, pred, average="macro")
        mcc = matthews_corrcoef(test_y, pred)
        pc = f1_score(test_y, pred, average=None, labels=list(range(n_cls)), zero_division=0)
        found, flagged = tracks(test_frame, pred, benign)
        rows.append((f1, mcc, pc[benign], found, flagged))

    for name, idx, sc in (("transfer", tr_idx, sc_src), ("in-dist", in_idx, sc_in),
                          ("mixed", mix_idx, sc_mix)):
        cl = pack(idx, sc)
        test = test_with(sc)
        rows, gv = [], []
        for s in range(a.seeds):
            _, _, d = run_method("fedavg", cl, test, cfg, s, detail=True)
            gv.append(d["gvec"].clone())
            score(name, d["gvec"], test, rows)
        res[name], models[name] = np.array(rows), gv
        print(f"{name:26s} done, {len(cl)} clients, {sum(len(c[0]) for c in cl):,} rows", flush=True)
        del cl

    rows = []
    test_lf = test_with(sc_lf)
    for s in range(a.seeds):
        score("label-free", models["transfer"][s], test_lf, rows)
    res["label-free"] = np.array(rows)

    order = np.random.RandomState(1).permutation(len(tgt_idx))
    ft = dict(cfg, rounds=a.ft_rounds)
    for k in a.budgets:
        pick = [tgt_idx[i] for i in order[:k]]
        n_rows = sum(len(i) for i in pick)
        for name, sc, warm in ((f"fine-tune {k}", sc_src, True),
                               (f"scratch {k}", sc_src, False),
                               (f"label-free + fine-tune {k}", sc_lf, True)):
            cl = pack(pick, sc)
            test = test_with(sc)
            rows = []
            for s in range(a.seeds):
                _, _, d = run_method("fedavg", cl, test, ft, s, detail=True,
                                     init=models["transfer"][s] if warm else None)
                score(name, d["gvec"], test, rows)
            res[name] = np.array(rows)
            res[name + " rows"] = n_rows

    t, c = res["transfer"], res["in-dist"]
    gap = c[:, 0].mean() - t[:, 0].mean()
    print(f"\n{'arm':28s} {'macro F1':>18s} {'MCC':>8s} {'benign F1':>10s} "
          f"{'found':>7s} {'flagged':>8s} {'recovered':>10s}  vs transfer")
    for name, r in res.items():
        if name.endswith(" rows"):
            continue
        rec = (r[:, 0].mean() - t[:, 0].mean()) / gap if gap else float("nan")
        vs = ""
        if name != "transfer":
            pval = wilcoxon(list(r[:, 0]), list(t[:, 0]))
            vs = f"p = {pval:.4f}, {int((r[:, 0] > t[:, 0]).sum())} of {len(r)} seeds higher"
        extra = f" ({res[name + ' rows']:,} labelled rows)" if name + " rows" in res else ""
        print(f"{name:28s} {r[:, 0].mean():.4f} +/- {r[:, 0].std():.4f} {r[:, 1].mean():8.4f} "
              f"{r[:, 2].mean():10.3f} {r[:, 3].mean():7.3f} {r[:, 4].mean():8.3f} "
              f"{rec:10.0%}  {vs}{extra}")
    print(f"\nthe shift costs {gap:+.4f} macro F1 (in-dist against transfer); 'recovered' "
          f"is each arm's share of it. found and flagged: share of attack and benign "
          f"tracks raising an alert at 2 of 3 windows.")
    print("SHIFT DONE")


if __name__ == "__main__":
    main()
