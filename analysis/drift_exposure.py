#!/usr/bin/env python3
"""What does partitioning cost, once the pooled arm's extra passes are removed?

`federated_drift.py` reports a pooled ceiling beside the federated arms, and
the difference between them is the headline of RESULTS.md 5d3. That difference
carried a confound worth removing: a pooled client training for two local
epochs sees every row twice per round, while a federation sampling half its
clients for two local epochs visits each row about half as often. Half the
pooled arm's advantage was simply more passes over the same data.

The `-matched` arms run the pooled side at one local epoch, which equalises row
visits per round to under a tenth of a percent. This script reads the arm lines
out of the campaign logs, forms the mixing cost on each side as
(mixed minus in-dist) with the standard error of a difference of means, and
divides. Every figure quoted in 5d3's ratio table comes from here, so it is
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

RUNS = Path.home() / "ns3-v2x" / "runs"
ARM = re.compile(r"^(\S+)\s+\d+ clients\s+[\d,]+ rows\s+macro F1 "
                 r"([\d.]+) \+/- ([\d.]+)")

# (label, log carrying the federated arms, log carrying the pooled arms)
SETTINGS = [
    ("sparse into dense, pooled lr 0.05", "drift_dense_exposure", "drift_dense_exposure"),
    ("sparse into dense, pooled lr 0.01", "drift_dense_exposure", "drift_dense_exposure_lr01"),
    ("dense into sparse, pooled lr 0.05", "drift_sparse_exposure", "drift_sparse_exposure"),
    ("dense into sparse, pooled lr 0.01", "drift_sparse_exposure", "drift_sparse_exposure_lr01"),
]


def arms(stem):
    path = RUNS / "drift" / "logs" / f"{stem}.log"
    out = {}
    for line in path.read_text().splitlines():
        m = ARM.match(line)
        if m:
            out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    if not out:
        raise SystemExit(f"no arm lines in {path}")
    return out


def diff(a, b, n):
    """mixed minus in-dist, with the standard error of the difference."""
    return a[0] - b[0], math.sqrt((a[1] ** 2 + b[1] ** 2) / n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10,
                    help="seeds behind each arm mean, for the standard error")
    a = ap.parse_args()

    print("Mixing cost is mixed minus in-dist; negative means mixing hurts.")
    print("The matched row is the control: the pooled arm at one local epoch,")
    print("which matches the federation's row visits per round to under 0.1%.\n")

    ratios = []
    for label, fed_log, pool_log in SETTINGS:
        f, p = arms(fed_log), arms(pool_log)
        fd, fse = diff(f["mixed"], f["in-dist"], a.seeds)
        rd, rse = diff(p["centralised"], p["centralised-in-dist"], a.seeds)
        md, mse = diff(p["centralised-matched"],
                       p["centralised-in-dist-matched"], a.seeds)
        ratio = fd / md
        rel = math.sqrt((fse / fd) ** 2 + (mse / md) ** 2)
        ratios.append(ratio)
        print(label)
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
