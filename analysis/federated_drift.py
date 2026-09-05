#!/usr/bin/env python3
"""
Does federated training recover what a density change costs?

The brief names non-stationarity as the aim, and RESULTS.md 3c measures the
loss: a detector trained at one traffic density and tested at the other drops
about 0.15 macro F1, and the loss lands on false alarms rather than on missed
attacks. Federation is then motivated as the way to keep learning from the
conditions a deployment actually sees.

Nothing in the project tested that. The architecture is introduced to solve a
problem and never shown to solve it, which is the first thing a reviewer will
ask about the federated panel's presence in a paper about a detection floor.

Four arms, every one of them evaluated on the SAME held-out clients of the
target corpus, and every one trained on the same number of rows:

    transfer      clients from the other density only
    in-dist       training clients from the target density only
    mixed         both, which is what a federation spanning densities has
    centralised   the mixed rows pooled into one client, the ceiling federation
                  is trying to reach without moving the data

transfer against in-dist reproduces the drift result under this model. mixed
against transfer is what federation buys. mixed against centralised is what
federation costs. Either answer is publishable; not asking is not.
"""
import argparse
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from federated import MLP, run_method

VEHICLE = "vehicle"


def load(path, tag, role, sample, rng):
    df = pd.read_pickle(path)
    if "label_clean" in df.columns:
        df = df[df.label_clean == 1]
    if role and "key_observer_role" in df.columns:
        before = len(df)
        df = df[df.key_observer_role == role]
        print(f"{tag}: kept {len(df):,} of {before:,} rows at observer role {role}")
    if sample and len(df) > sample:
        df = df.sample(n=sample, random_state=0)
    df = df.reset_index(drop=True)
    df["corpus"] = tag
    df["client"] = tag + ":" + df.key_rxNodeId.astype(str)
    return df


def pack_clients(X, codes, obs, keep, min_rows, cap, rng):
    """One client per observer in `keep`, with a per-arm row budget."""
    out = []
    for o in keep:
        m = obs == o
        if m.sum() < min_rows:
            continue
        idx = np.flatnonzero(m)
        out.append(idx)
    if not out:
        return []
    total = sum(len(i) for i in out)
    if cap and total > cap:
        # Thin every client by the same fraction, so the arm's row budget is
        # met without changing how many clients it has or how skewed they are.
        frac = cap / total
        out = [rng.choice(i, max(20, int(len(i) * frac)), replace=False) for i in out]
    packed = []
    for idx in out:
        xi = torch.tensor(X[idx])
        yi = torch.tensor(codes[idx], dtype=torch.long)
        packed.append((xi, yi, torch.bincount(yi, minlength=int(codes.max()) + 1)))
    return packed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="corpus the model starts from")
    ap.add_argument("--target", required=True, help="corpus it is deployed into")
    ap.add_argument("--source-tag", default="sparse")
    ap.add_argument("--target-tag", default="dense")
    ap.add_argument("--sample", type=int, default=150000)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=25)
    ap.add_argument("--local-epochs", type=int, default=2)
    ap.add_argument("--method", default="fedavg")
    ap.add_argument("--min-rows", type=int, default=200)
    ap.add_argument("--observer-role", default=VEHICLE)
    a = ap.parse_args()

    rng = np.random.RandomState(0)
    src = load(a.source, a.source_tag, a.observer_role, a.sample, rng)
    tgt = load(a.target, a.target_tag, a.observer_role, a.sample, rng)

    shared = sorted(set(src.label_attackId) & set(tgt.label_attackId))
    src = src[src.label_attackId.isin(shared)]
    tgt = tgt[tgt.label_attackId.isin(shared)]
    print(f"\n{len(shared)} shared classes {shared}")

    feats = [c for c in src.columns
             if c.startswith(("app_", "phy_")) and c in set(tgt.columns)]
    both = pd.concat([src, tgt], ignore_index=True)
    codes = pd.Categorical(both.label_attackId, categories=shared).codes

    # The target corpus's observers split into training and test clients. The
    # test clients are held out of every arm, so all four are scored on rows no
    # arm has trained on and on the same rows as each other.
    tgt_obs = pd.unique(both.loc[both.corpus == a.target_tag, "client"].values)
    rng.shuffle(tgt_obs)
    cut = int(0.7 * len(tgt_obs))
    tgt_train, tgt_test = set(tgt_obs[:cut]), set(tgt_obs[cut:])
    src_obs = list(pd.unique(both.loc[both.corpus == a.source_tag, "client"].values))

    obs = both["client"].values
    X = both[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values.astype(np.float32)
    # The scaler sees training rows only, from both corpora, which is what a
    # federation spanning densities would have.
    fit_mask = np.isin(obs, list(tgt_train) + src_obs)
    X = StandardScaler().fit(X[fit_mask]).transform(X).astype(np.float32)

    test_mask = np.isin(obs, list(tgt_test))
    test = (torch.tensor(X[test_mask]),
            torch.tensor(codes[test_mask], dtype=torch.long))
    print(f"{len(src_obs)} source clients, {len(tgt_train)} target training "
          f"clients, {len(tgt_test)} target test clients, "
          f"{test_mask.sum():,} test rows, {len(feats)} features\n")

    # Every arm gets the same training row budget, so a difference between
    # arms is where the rows came from and not how many there were.
    def rows_of(keep):
        return int(np.isin(obs, list(keep)).sum())
    budget = min(rows_of(src_obs), rows_of(tgt_train))
    print(f"row budget per arm: {budget:,} "
          f"(source has {rows_of(src_obs):,}, target training has "
          f"{rows_of(tgt_train):,})\n")

    # Every arm trains on the SAME number of rows, mixed included. Letting the
    # mixed arm keep both corpora at full budget would give it twice the data
    # and confound breadth with volume, which is the mistake the drift
    # comparison in 3c was rebuilt to avoid. The extra-data case is reported
    # separately as mixed-2x, so the two effects can be read apart.
    # The centralised arm pools the SAME mixed rows into a single client, which
    # makes federated averaging equivalent to training on the pooled data. It is
    # the ceiling federation is trying to reach without moving the data, and it
    # is what separates two very different explanations of a poor mixed result:
    # that rows from the other density do not help, or that they would help and
    # federation cannot exploit them. This file's own docstring called that the
    # point and the arm was never in the dict.
    arms = {
        "transfer": (src_obs, 1, False),
        "in-dist": (list(tgt_train), 1, False),
        "mixed": (src_obs + list(tgt_train), 1, False),
        "mixed-2x": (src_obs + list(tgt_train), 2, False),
        "centralised": (src_obs + list(tgt_train), 1, True),
        # The control the ceiling needs. Without it, centralised-mixed can only
        # be compared against a FEDERATED in-dist arm, which conflates two
        # different things: whether mixing distributions helps, and whether
        # partitioning hurts. This arm is in-dist rows pooled the same way, so
        # the four form a two by two and each question has its own pair.
        "centralised-in-dist": (list(tgt_train), 1, True),
    }
    # Same configuration as federated.py's panel, so this arm is the same
    # learner the aggregation comparison uses and the two are readable together.
    cfg = dict(d_in=len(feats), n_classes=len(shared), embed_dim=32, lr=0.05,
               batch_size=128, local_epochs=a.local_epochs, rounds=a.rounds,
               participation=0.5, mu=0.01, tau=1.0, lam=0.1)

    results = {}
    for name, (keep, mult, pool) in arms.items():
        cap = budget * mult
        clients = pack_clients(X, codes, obs, keep, a.min_rows, cap, rng)
        if not clients:
            print(f"{name}: no clients with {a.min_rows} rows, skipped")
            continue
        if pool:
            # One client holding every row the mixed arm has. Same rows, same
            # budget, no partitioning. pack_clients returns (x, y, class counts),
            # so the counts are recomputed over the pooled labels rather than
            # summed, which would be the same here but is not obviously so.
            xs = torch.cat([c[0] for c in clients])
            ys = torch.cat([c[1] for c in clients])
            clients = [(xs, ys, torch.bincount(ys, minlength=len(shared)))]
        n_rows = sum(len(c[0]) for c in clients)
        f1s, mccs = [], []
        for s in range(a.seeds):
            f1, mcc = run_method(a.method, clients, test, cfg, s)
            f1s.append(f1)
            mccs.append(mcc)
        results[name] = (np.mean(f1s), np.std(f1s), np.mean(mccs), np.std(mccs))
        print(f"{name:12s} {len(clients):4d} clients {n_rows:8,} rows   "
              f"macro F1 {np.mean(f1s):.4f} +/- {np.std(f1s):.4f}   "
              f"MCC {np.mean(mccs):.4f} +/- {np.std(mccs):.4f}")

    if "mixed" in results and "centralised" in results:
        gap = results["centralised"][0] - results["mixed"][0]
        print(f"\ncentralised against mixed, the SAME rows pooled into one "
              f"client: {gap:+.4f}")
        if "centralised-in-dist" in results:
            mix = results["centralised"][0] - results["centralised-in-dist"][0]
            fed = results["mixed"][0] - results["in-dist"][0]
            print(f"does MIXING help, both arms pooled:        {mix:+.4f}")
            print(f"does MIXING help, both arms federated:     {fed:+.4f}")
            print("Read those two together. They ask the same question at the "
                  "same budget,\nonce with the rows pooled and once with them "
                  "partitioned across clients.")
        print("""
This is the row that says whose failure it is. Both arms hold the same training
rows from both densities; the centralised one holds them in a single client, so
averaging over one model is training on the pooled data.

**It is a ceiling rather than a step-matched control, and the difference matters
when reading it.** The pooled client sees every row in every round where the
federation samples half its clients, so centralised gets more optimisation as
well as no partitioning. That makes it an upper bound on what federation could
reach, which is the useful thing here, and not a clean measurement of what
partitioning alone costs.

If centralised beats mixed, the rows from the other density carry usable signal
and federation is failing to exploit it, which argues for personalisation rather
than for abandoning the breadth. If centralised is no better even as a ceiling,
the rows genuinely do not transfer and no aggregation method was going to help.
""")

    if "transfer" in results and "in-dist" in results:
        gap = results["in-dist"][0] - results["transfer"][0]
        print(f"\nthe cost of the density change under this model: "
              f"{gap:+.4f} macro F1")
        if "mixed" in results:
            rec = results["mixed"][0] - results["transfer"][0]
            frac = rec / gap if gap else float("nan")
            print(f"what a federation spanning both densities recovers: "
                  f"{rec:+.4f}, which is {frac:.0%} of it")
            over = results["mixed"][0] - results["in-dist"][0]
            print(f"mixed against training on the target density alone: {over:+.4f}")
    if "mixed-2x" in results and "mixed" in results:
        print(f"and with twice the rows rather than the same number: "
              f"{results['mixed-2x'][0] - results['mixed'][0]:+.4f} on top of mixed")
    print("""
Read the mixed row against both of the others. Against transfer it says whether
federating across densities is worth anything at all. Against in-dist it says
whether a federation that spans two distributions pays for the breadth, because
a single model serving both is not free even when it beats the transfer case.
The clients are the same observers throughout and the test rows never move, so
what differs between arms is which distribution the training rows came from.
""")


if __name__ == "__main__":
    main()
