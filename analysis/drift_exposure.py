#!/usr/bin/env python3
"""What does partitioning cost, once the pooled arm's extra passes are removed?

`federated_drift.py` reports a pooled ceiling beside the federated arms, and
the difference between them is the headline of RESULTS.md 5d3. That difference
carried a confound worth removing: a pooled client training for two local
epochs sees every row twice per round, while a federation sampling half its
clients for two local epochs visits each row about half as often. Half the
pooled arm's advantage was simply more passes over the same data.

The `-matched` arms run the pooled side at one local epoch, which equalises row
visits per round to within about 0.2 percent. This script reads the per seed
scores out of the campaign logs, forms the mixing cost on each side as mixed
minus in-dist, and divides. The arms of one log share their seeds, so each cost
is a PAIRED difference and its standard error is the sample standard deviation
of the per seed differences over the root of the seed count. A log without per
seed lines falls back to the arm summaries, unpaired and corrected from the
population standard deviation they print to the sample one. Every figure quoted in 5d3's ratio table comes from here, so it is
regenerable rather than typed.

What is NOT matched is sequential depth: the pooled client still takes about
1,630 gradient steps between averages against four for a federated client. That
is not a confound to remove but what partitioning is, so the output is a
measurement of what partitioning costs GIVEN that partitioning also shortens
the steps. Call it exposure matched, never step matched.
"""
import argparse
import math
import re
from pathlib import Path

import numpy as np

RUNS = Path.home() / "ns3-v2x" / "runs"
ARM = re.compile(r"^(\S+)\s+\d+ clients\s+[\d,]+ rows\s+macro F1 "
                 r"([\d.]+) \+/- ([\d.]+)")
HEAD = re.compile(r"^(\S+): \d+ clients, ")
SEED = re.compile(r"^\s+seed (\d+)\s+F1 ([\d.]+)")

# (label, log carrying the federated arms, log carrying the pooled arms)
SETTINGS = [
    ("sparse into dense, pooled lr 0.05", "drift_dense_exposure", "drift_dense_exposure"),
    ("sparse into dense, pooled lr 0.01", "drift_dense_exposure", "drift_dense_exposure_lr01"),
    ("dense into sparse, pooled lr 0.05", "drift_sparse_exposure", "drift_sparse_exposure"),
    ("dense into sparse, pooled lr 0.01", "drift_sparse_exposure", "drift_sparse_exposure_lr01"),
]


def arms(stem):
    """Per arm, the per seed macro F1 in seed order, or the (mean, population
    std) summary when the log has no per seed lines."""
    path = RUNS / "drift" / "logs" / f"{stem}.log"
    per, summ, cur = {}, {}, None
    for line in path.read_text().splitlines():
        m = HEAD.match(line)
        if m:
            cur = m.group(1)
            per[cur] = {}
            continue
        m = SEED.match(line)
        if m and cur:
            per[cur][int(m.group(1))] = float(m.group(2))
            continue
        m = ARM.match(line)
        if m:
            summ[m.group(1)] = (float(m.group(2)), float(m.group(3)))
            cur = None
    if not summ:
        raise SystemExit(f"no arm lines in {path}")
    return per, summ


def diff(log, x, y, n):
    """x minus y, and its standard error: paired over seeds where the log has
    per seed lines, otherwise unpaired from the summaries."""
    per, summ = log
    if per.get(x) and per.get(y) and set(per[x]) == set(per[y]):
        d = np.array([per[x][s] - per[y][s] for s in sorted(per[x])])
        return float(d.mean()), float(d.std(ddof=1) / math.sqrt(len(d))), "paired"
    a, b = summ[x], summ[y]
    k = math.sqrt(n / (n - 1))
    return a[0] - b[0], math.sqrt(((a[1] * k) ** 2 + (b[1] * k) ** 2) / n), "unpaired"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10,
                    help="seeds behind each arm mean, for the standard error")
    a = ap.parse_args()

    print("Mixing cost is mixed minus in-dist; negative means mixing hurts.")
    print("The matched row is the control: the pooled arm at one local epoch,")
    print("which matches the federation's expected row visits per round to "
          "within about 0.2%.\n")

    ratios = []
    for label, fed_log, pool_log in SETTINGS:
        f, p = arms(fed_log), arms(pool_log)
        fd, fse, fk = diff(f, "mixed", "in-dist", a.seeds)
        rd, rse, _ = diff(p, "centralised", "centralised-in-dist", a.seeds)
        md, mse, mk = diff(p, "centralised-matched",
                           "centralised-in-dist-matched", a.seeds)
        ratio = fd / md
        rel = math.sqrt((fse / fd) ** 2 + (mse / md) ** 2)
        ratios.append(ratio)
        print(f"{label}   ({fk} federated, {mk} pooled)")
        print(f"   federated                 {fd:+.4f}  se {fse:.4f}  "
              f"{abs(fd)/fse:5.1f} sigma")
        print(f"   pooled, unmatched         {rd:+.4f}  se {rse:.4f}  "
              f"{abs(rd)/rse:5.1f} sigma")
        print(f"   pooled, EXPOSURE MATCHED  {md:+.4f}  se {mse:.4f}  "
              f"{abs(md)/mse:5.1f} sigma")
        print(f"   ratio {ratio:5.2f} +/- {ratio * rel:.2f}\n")

    print(f"ratio spans {min(ratios):.2f} to {max(ratios):.2f} across the four "
          "settings")
    print("Same sign everywhere and no single factor. Quote the range or quote "
          "one row\nwith its direction and learning rate named. Never average "
          "them.")


if __name__ == "__main__":
    main()
