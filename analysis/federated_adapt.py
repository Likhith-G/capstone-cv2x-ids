#!/usr/bin/env python3
"""
Can a deployed federated detector be adapted to a change of traffic density?

The project brief asks for a detector that stays reliable under non-stationary
conditions and predicts how an offline model fails when they change: missed
attacks and excessive false alarms. federated_drift.py measured that failure
(RESULTS 5d): a model federated on the sparse road and deployed into congestion
loses most of what a model trained on congestion reaches, and federating across
both densities recovers none of it. That leaves the question the brief actually
asks unanswered: once conditions have changed, can the deployment catch up?

This file tests the two cheapest ways a deployment could, against the drift
experiment's own controls, on the SAME 217 held-out target clients:

  transfer          the source-density model, unadapted. Must reproduce the
                    drift log's transfer row, which is the check that the setup
                    below is the drift experiment's setup
  in-dist           trained on the target density from the start (the ceiling)
  label-free        the transfer model with its input scaling refitted on
                    UNLABELLED target-density rows. Needs no labels at all
  fine-tune k       the transfer model, then a few rounds of FedAvg on k
                    labelled target-density clients
  scratch k         the same k clients and rounds from a fresh model, the
                    control that says whether the warm start is worth anything
  label-free + fine-tune k   both

Adaptation clients are drawn from the target TRAINING clients, never the test
clients. Reported per arm: macro F1, MCC, benign F1 (the false-alarm side) and
dos_low_rate F1 (the missed-attack side), the two failures the brief names, and
the share of the transfer gap recovered, (arm - transfer) / (in-dist - transfer).
"""
import argparse
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import f1_score, matthews_corrcoef
from sklearn.preprocessing import StandardScaler
from federated import MLP, load_flat, run_method
from federated_drift import VEHICLE, load, pack_clients, to_tensors
from pooled_consensus import wilcoxon


def evaluate(gvec, test, cfg):
    m = MLP(cfg["d_in"], cfg["n_classes"])
    load_flat(m, gvec)
    m.eval()
    with torch.no_grad():
        pred = m(test[0]).argmax(1).numpy()
    truth = test[1].numpy()
    return (f1_score(truth, pred, average="macro"), matthews_corrcoef(truth, pred),
            f1_score(truth, pred, average=None, labels=list(range(cfg["n_classes"])),
                     zero_division=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--source-tag", default="sparse")
    ap.add_argument("--target-tag", default="dense")
    ap.add_argument("--sample", type=int, default=300000)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=25)
    ap.add_argument("--local-epochs", type=int, default=2)
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--budgets", type=int, nargs="+", default=[10, 50],
                    help="labelled target clients available for fine-tuning")
    ap.add_argument("--ft-rounds", type=int, default=5)
    ap.add_argument("--observer-role", default=VEHICLE)
    ap.add_argument("--holdout-tx", type=float, default=None,
                    help="hold this share of the target transmitters of every "
                         "class out of the fine-tuning rows, and also score every "
                         "arm on test rows from those transmitters only, so "
                         "adaptation is judged on attackers it never saw labelled")
    ap.add_argument("--overlap-only", action="store_true",
                    help="report how many test rows come from transmitters the "
                         "fine-tuning clients hold labelled rows of, then stop")
    a = ap.parse_args()

    # From here to the packing of the in-dist arm this is federated_drift.py's
    # main, step for step, because the transfer and in-dist rows are drawn from
    # one shared RandomState and any change in the order of draws moves them.
    rng = np.random.RandomState(0)
    src = load(a.source, a.source_tag, a.observer_role, a.sample, rng)
    tgt = load(a.target, a.target_tag, a.observer_role, a.sample, rng)
    shared = sorted(set(src.label_attackId) & set(tgt.label_attackId))
    src = src[src.label_attackId.isin(shared)]
    tgt = tgt[tgt.label_attackId.isin(shared)]
    feats = [c for c in src.columns
             if c.startswith(("app_", "phy_")) and c in set(tgt.columns)]
    both = pd.concat([src, tgt], ignore_index=True)
    del src, tgt
    codes = pd.Categorical(both.label_attackId, categories=shared).codes
    tgt_obs = pd.unique(both.loc[both.corpus == a.target_tag, "client"].values)
    rng.shuffle(tgt_obs)
    cut = int(0.7 * len(tgt_obs))
    tgt_train, tgt_test = list(tgt_obs[:cut]), list(tgt_obs[cut:])
    src_obs = list(pd.unique(both.loc[both.corpus == a.source_tag, "client"].values))
    obs = both["client"].values
    X = both[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values.astype(np.float32)
    # The physical transmitter of each row, per seed. Observer-split clients
    # hear the same transmitters as the test clients, so a fine-tuned model can
    # be scored on stations it has seen labelled examples of.
    tx = (both["key_seed"].astype(str) + ":" + both["label_txNodeId"].astype(str)).values
    del both
    test_mask = np.isin(obs, tgt_test)
    test_y = torch.tensor(codes[test_mask], dtype=torch.long)

    def rows_of(keep):
        return int(np.isin(obs, list(keep)).sum())
    budget = min(rows_of(src_obs), rows_of(tgt_train))
    tr_idx = pack_clients(obs, src_obs, a.min_rows, budget, rng)
    in_idx = pack_clients(obs, tgt_train, a.min_rows, budget, rng)

    n_cls = len(shared)
    benign, lowrate = shared.index(0), shared.index(12)
    cfg = dict(d_in=len(feats), n_classes=n_cls, embed_dim=32, lr=a.lr,
               batch_size=128, local_epochs=a.local_epochs, rounds=a.rounds,
               participation=0.5, mu=0.01, tau=1.0, lam=0.1)
    print(f"{n_cls} shared classes {shared}; {len(tr_idx)} source clients, "
          f"{len(in_idx)} target training clients, {len(tgt_test)} target test "
          f"clients, {int(test_mask.sum()):,} test rows, {len(feats)} features, "
          f"{a.seeds} seeds\n")

    sc_src = StandardScaler().fit(X[np.concatenate(tr_idx)])
    sc_in = StandardScaler().fit(X[np.concatenate(in_idx)])
    # Label-free: the deployment's own unlabelled rows, which here are the
    # target training clients' features with their labels never read.
    sc_lf = sc_in
    test_src = (torch.tensor(sc_src.transform(X[test_mask]).astype(np.float32)), test_y)
    test_in = (torch.tensor(sc_in.transform(X[test_mask]).astype(np.float32)), test_y)
    test_lf = test_in

    # Adaptation clients: k of the target TRAINING clients, drawn by their own
    # generator so the draws above are untouched. Nested, so the smaller budget
    # is a subset of the larger.
    order = np.random.RandomState(1).permutation(len(in_idx))
    pick = {k: [in_idx[i] for i in order[:k]] for k in a.budgets}

    test_tx = tx[test_mask]
    test_codes = codes[test_mask]
    held = None
    if a.holdout_tx:
        # Per class, a share of the target corpus's transmitters, chosen by
        # their own generator. Their rows are removed from every fine-tuning
        # client; nothing else changes, so transfer and in-dist still reproduce.
        tgt_rows = np.isin(obs, tgt_train + tgt_test)
        cls_of = pd.Series(codes[tgt_rows]).groupby(tx[tgt_rows]).agg(
            lambda c: c.mode().iloc[0])
        hrng = np.random.RandomState(2)
        held = set()
        for c in sorted(cls_of.unique()):
            ids = sorted(cls_of.index[cls_of == c])
            held |= set(hrng.choice(ids, int(round(a.holdout_tx * len(ids))),
                                    replace=False))
        pick = {k: [i[~np.isin(tx[i], list(held))] for i in v] for k, v in pick.items()}
        pick = {k: [i for i in v if len(i)] for k, v in pick.items()}
        ho = torch.tensor(np.isin(test_tx, list(held)))
        print(f"held out {len(held)} target transmitters ({a.holdout_tx:.0%} of each "
              f"class); test rows from them: {int(ho.sum()):,}, of which "
              f"{int((torch.tensor(test_codes)[ho] == lowrate).sum()):,} low-rate DoS")
    for k in a.budgets:
        seen = set(tx[np.concatenate(pick[k])])
        hit = np.isin(test_tx, list(seen))
        lr = test_codes == lowrate
        att = test_codes != benign
        print(f"fine-tune budget {k}: {len(seen)} transmitters in the labelled rows; "
              f"test rows from those transmitters {hit.mean():.3f} of all, "
              f"{hit[att].mean():.3f} of attack rows, {hit[lr].mean():.3f} of "
              f"low-rate DoS rows ({int(lr.sum()):,} rows, "
              f"{len(set(test_tx[lr]))} transmitters, "
              f"{len(set(test_tx[lr]) - seen)} of them unseen)")
    if a.overlap_only:
        return

    res, res_ho = {}, {}

    def record(name, rows):
        res[name] = np.array(rows)

    def unseen(name, gvecs, test):
        if held is None:
            return
        t = (test[0][ho], test[1][ho])
        out = []
        for g in gvecs:
            f1, mcc, pc = evaluate(g, t, cfg)
            out.append((f1, mcc, pc[benign], pc[lowrate]))
        res_ho[name] = np.array(out)

    transfer_models = []
    rows = []
    src_clients = to_tensors(X, codes, tr_idx, sc_src, n_cls)
    for s in range(a.seeds):
        f1, mcc, d = run_method("fedavg", src_clients, test_src, cfg, s, detail=True)
        transfer_models.append(d["gvec"].clone())
        pc = d["per_class_f1"]
        rows.append((f1, mcc, pc[benign], pc[lowrate]))
    record("transfer", rows)
    unseen("transfer", transfer_models, test_src)
    del src_clients

    rows = []
    in_clients = to_tensors(X, codes, in_idx, sc_in, n_cls)
    gv = []
    for s in range(a.seeds):
        f1, mcc, d = run_method("fedavg", in_clients, test_in, cfg, s, detail=True)
        gv.append(d["gvec"])
        pc = d["per_class_f1"]
        rows.append((f1, mcc, pc[benign], pc[lowrate]))
    record("in-dist", rows)
    unseen("in-dist", gv, test_in)
    del in_clients

    rows = []
    for s in range(a.seeds):
        f1, mcc, pc = evaluate(transfer_models[s], test_lf, cfg)
        rows.append((f1, mcc, pc[benign], pc[lowrate]))
    record("label-free", rows)
    unseen("label-free", transfer_models, test_lf)

    ft = dict(cfg, rounds=a.ft_rounds)
    for k in a.budgets:
        n_rows = sum(len(i) for i in pick[k])
        for name, scaler, test, warm in (
                (f"fine-tune {k}", sc_src, test_src, True),
                (f"scratch {k}", sc_src, test_src, False),
                (f"label-free + fine-tune {k}", sc_lf, test_lf, True)):
            clients = to_tensors(X, codes, pick[k], scaler, n_cls)
            rows, gv = [], []
            for s in range(a.seeds):
                f1, mcc, d = run_method("fedavg", clients, test, ft, s, detail=True,
                                        init=transfer_models[s] if warm else None)
                gv.append(d["gvec"])
                pc = d["per_class_f1"]
                rows.append((f1, mcc, pc[benign], pc[lowrate]))
            record(name, rows)
            unseen(name, gv, test)
            res[name + " rows"] = n_rows

    t, c = res["transfer"], res["in-dist"]
    gap = c[:, 0].mean() - t[:, 0].mean()
    print(f"{'arm':28s} {'macro F1':>18s} {'MCC':>8s} {'benign F1':>10s} "
          f"{'low-rate DoS F1':>16s} {'recovered':>10s}  vs transfer")
    for name, r in res.items():
        if name.endswith(" rows"):
            continue
        rec = (r[:, 0].mean() - t[:, 0].mean()) / gap if gap else float("nan")
        if name == "transfer":
            vs = ""
        else:
            try:
                pval = wilcoxon(list(r[:, 0]), list(t[:, 0]))
                vs = (f"p = {pval:.4f}, {int((r[:, 0] > t[:, 0]).sum())} of "
                      f"{len(r)} seeds higher")
            except ValueError as e:
                vs = str(e)
        extra = f" ({res[name + ' rows']:,} labelled rows)" if name + " rows" in res else ""
        print(f"{name:28s} {r[:, 0].mean():.4f} +/- {r[:, 0].std():.4f} "
              f"{r[:, 1].mean():8.4f} {r[:, 2].mean():10.3f} {r[:, 3].mean():16.3f} "
              f"{rec:10.0%}  {vs}{extra}")
    print(f"\nthe density change costs {gap:+.4f} macro F1 under this model "
          f"(in-dist against transfer); 'recovered' is each arm's share of it.")
    print(f"fine-tuning runs {a.ft_rounds} rounds of FedAvg at participation "
          f"{cfg['participation']}, {a.local_epochs} local epochs, learning rate {a.lr}.")
    if res_ho:
        t = res_ho["transfer"]
        c = res_ho["in-dist"]
        gap = c[:, 0].mean() - t[:, 0].mean()
        print("\nscored only on test rows from the held-out transmitters, which no "
              "fine-tuning client holds a labelled row of.\nThe in-dist ceiling "
              "was trained with them, so it is not held out.")
        print(f"{'arm':28s} {'macro F1':>18s} {'MCC':>8s} {'benign F1':>10s} "
              f"{'low-rate DoS F1':>16s} {'recovered':>10s}  vs transfer")
        for name, r in res_ho.items():
            rec = (r[:, 0].mean() - t[:, 0].mean()) / gap if gap else float("nan")
            vs = ""
            if name != "transfer":
                try:
                    pval = wilcoxon(list(r[:, 0]), list(t[:, 0]))
                    vs = (f"p = {pval:.4f}, {int((r[:, 0] > t[:, 0]).sum())} of "
                          f"{len(r)} seeds higher")
                except ValueError as e:
                    vs = str(e)
            print(f"{name:28s} {r[:, 0].mean():.4f} +/- {r[:, 0].std():.4f} "
                  f"{r[:, 1].mean():8.4f} {r[:, 2].mean():10.3f} {r[:, 3].mean():16.3f} "
                  f"{rec:10.0%}  {vs}")
    print("ADAPT DONE")


if __name__ == "__main__":
    main()
