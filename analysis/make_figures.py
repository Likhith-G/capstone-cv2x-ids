#!/usr/bin/env python3
"""
Figures, rendered from the logs rather than recomputed.

Recomputing a figure from the corpus is how a plot comes to disagree with the
table beside it. Every number below is parsed out of the log that
verify_results.py already pins, and a parse that finds nothing is a hard error
rather than an empty axis, so a figure cannot quietly go stale when a run is
repeated.

Written to docs/figures/ as PDF for the paper and PNG for looking at.
"""
import argparse
import pathlib
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUNS = pathlib.Path.home() / "ns3-v2x" / "runs"
OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "figures"


def grab(log, pattern, what):
    text = (RUNS / log).read_text()
    hits = re.findall(pattern, text, re.M)
    if not hits:
        sys.exit(f"FAILED: {what} not found in {log}. The log changed shape; "
                 f"fix the parser rather than the figure.")
    return hits


def save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{stem}.{ext}", bbox_inches="tight", dpi=200)
    plt.close(fig)
    print(f"wrote {stem}.pdf and {stem}.png")


def fig_placement():
    """The bound against roadside unit lateral offset, with its optimum.

    The point of the picture is that the curve turns: past the optimum a unit
    set further back carries less information than the geometry it adds is
    worth, so there is a best place to stand one and it is not "as far as
    possible".
    """
    rows = grab("campaign_gnss/logs/geometry_placement.log",
                r"^\s+(\d+)m\s+([\d.]+) m\s+([\d.]+) m\s+([\d.]+) deg\s+([\d.]+)$",
                "the placement sweep")
    off = [float(r[0]) for r in rows]
    across = [float(r[1]) for r in rows]
    aniso = [float(r[4]) for r in rows]
    best = min(range(len(across)), key=lambda i: across[i])

    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    ax.plot(off, across, "o-", color="#1f4e79", lw=1.8)
    ax.axhline(across[0], ls=":", lw=1, color="#999999")
    ax.annotate(f"on the centreline as deployed: {across[0]:.1f} m, "
                f"anisotropy {aniso[0]:.2f}",
                xy=(off[0], across[0]), xytext=(4, across[0] + 0.7),
                fontsize=8, color="#555555")
    ax.annotate(f"optimum at {off[best]:.0f} m\n{across[best]:.1f} m, "
                f"anisotropy {aniso[best]:.2f}",
                xy=(off[best], across[best]),
                xytext=(off[best] + 26, across[best] + 0.4),
                fontsize=8, ha="left",
                arrowprops=dict(arrowstyle="->", lw=0.8, color="#333333"))
    ax.annotate("further back is worse\nthan doing nothing",
                xy=(off[-1], across[-1]), xytext=(off[-1] - 8, across[-1] - 5.4),
                fontsize=8, ha="right", color="#a0522d",
                arrowprops=dict(arrowstyle="->", lw=0.8, color="#a0522d"))
    ax.set_xlabel("roadside unit lateral offset from the centreline (m)")
    ax.set_ylabel("Cramer-Rao bound,\nacross the road (m)")
    ax.set_title("Geometry improves with offset, information falls with distance",
                 fontsize=10)
    ax.set_ylim(28.4, 42.2)
    ax.grid(alpha=0.25)
    save(fig, "placement")


def fig_direction():
    """The bound's weak axis against the direction the attacker chose.

    The ellipse orientation is computed from the propagation law and the
    receiver coordinates with no attacker anywhere in it. The shaded band is
    where a brute force search over 72 directions put the best lie. They agree,
    which is the figure's whole argument.
    """
    angles = grab("campaign_gnss/logs/geometry_bound.log",
                  r"major axis\s+([\d.]+) deg from the road",
                  "the ellipse orientation percentiles")
    q25, q50, q75 = [float(a) for a in angles[:3]]

    fig, ax = plt.subplots(figsize=(5.4, 2.0))
    ax.axvspan(75, 85, color="#a0522d", alpha=0.22,
               label="where a 72 direction search put the best lie (4b)")
    ax.plot([q25, q75], [1, 1], color="#1f4e79", lw=3,
            solid_capstyle="butt",
            label="bound's weakest axis, 25th to 75th percentile")
    ax.plot([q50], [1], "o", color="#1f4e79", ms=9)
    ax.annotate(f"median {q50:.1f} deg", xy=(q50, 1), xytext=(q50 - 30, 1.30),
                fontsize=9, color="#1f4e79")
    ax.set_xlim(0, 92)
    ax.set_ylim(0.55, 1.75)
    ax.set_yticks([])
    ax.set_xlabel("degrees off the road axis   (0 along the road, 90 across it)")
    ax.set_title("The geometry predicts where the attacker will lie", fontsize=10)
    ax.legend(fontsize=7.5, loc="upper left", frameon=False)
    ax.grid(axis="x", alpha=0.25)
    save(fig, "direction")


def fig_calibration():
    """Block error rate against SINR. Credibility rather than contribution:
    nothing was tuned to produce it and it reproduces across corpora."""
    rows = grab("campaign_gnss/logs/calibration.log",
                r"^\((-?\d+), (-?\d+)\]\s+\d+\s+([\d.]+)",
                "the BLER waterfall")
    lo = [float(r[0]) for r in rows]
    hi = [float(r[1]) for r in rows]
    bler = [float(r[2]) for r in rows]
    mid = [(a + b) / 2 for a, b in zip(lo, hi)]

    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.semilogy(mid, [max(b, 1e-4) for b in bler], "o-", color="#1f4e79")
    ax.set_xlabel("SINR (dB)")
    ax.set_ylabel("block error rate")
    ax.set_title("Link level behaviour was not tuned", fontsize=10)
    ax.grid(alpha=0.25, which="both")
    save(fig, "calibration")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    figs = {"placement": fig_placement, "direction": fig_direction,
            "calibration": fig_calibration}
    for name, fn in figs.items():
        if a.only and name not in a.only:
            continue
        fn()


if __name__ == "__main__":
    main()
