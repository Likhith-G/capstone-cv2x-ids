#!/usr/bin/env python3
"""
The EnGenius poster: its figures, its QR code, its PDF, and the checks the
course poster guide sets.

Figures are drawn at the width they print, so a point size set here is the
point size on the sheet. The guide asks for 18 to 24 pt body text read from
two to three metres, and a figure scaled by the page after it is drawn quietly
breaks that. Every number on a figure is parsed out of the same logs
make_figures.py reads.

    make_poster.py              figures, QR, PDF, checks
    make_poster.py --check      checks only, against the current poster.html

The checks render the page in headless Chrome and read back what it drew:
  - no visible text below 18 pt
  - no all-capitals token outside a short allowed list (the guide says to
    avoid acronyms)
  - every number in the visible text appears in docs/RESULTS.md or in the
    report content, both of which are pinned to run logs elsewhere
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from make_figures import RUNS, grab  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOTH = ROOT / "docs" / "booth"
FIGS = BOOTH / "figures"
POSTER = BOOTH / "poster.html"
PDF = BOOTH / "poster.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEMO = "https://likhith-g.github.io/capstone-cv2x-ids/booth/"

# The report's own text, where it exists on this machine. Every figure in it
# is pinned to a log by the report build, so a poster number found there is
# a checked number.
REPORT = (pathlib.Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
          / "Academics/Engineering Capstone Project/Part B/Assessment Task 2"
          / "generator/content")

PT = 1 / 72                      # inches per point
MM = 1 / 25.4                    # inches per millimetre
NAVY, RUST, GREY, TEAL = "#1b3a5c", "#b4532a", "#8a8f94", "#2e7d7d"

plt.rcParams.update({
    "font.family": "Arial", "font.size": 22, "axes.labelsize": 22,
    "xtick.labelsize": 20, "ytick.labelsize": 20, "legend.fontsize": 20,
    "axes.linewidth": 1.4, "xtick.major.width": 1.4, "ytick.major.width": 1.4,
    "xtick.major.size": 7, "ytick.major.size": 7, "svg.fonttype": "path",
    "axes.spines.top": False, "axes.spines.right": False,
})


def save(fig, stem):
    FIGS.mkdir(parents=True, exist_ok=True)
    # No bbox_inches="tight": that crops the canvas and the printed width
    # would no longer be the width the fonts were set for.
    fig.savefig(FIGS / f"{stem}.svg")
    plt.close(fig)
    print(f"wrote figures/{stem}.svg")


def fig_floor(w_mm, h_mm):
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
    cross = float(grab(log, r"50 percent detection at\s+([\d.]+) m", "the crossing")[0])
    lo, hi = map(float, grab(log, r"95 percent interval\s+([\d.]+) to ([\d.]+) m",
                             "the crossing interval")[0])
    p95 = float(grab(log, r"95th ([\d.]+) m", "the benign error")[0])

    fig = plt.figure(figsize=(w_mm * MM, h_mm * MM))
    ax = fig.add_axes([0.13, 0.14, 0.84, 0.83])
    ax.axvspan(1, p95, color=GREY, alpha=0.22, lw=0)
    ax.text(p95 * 1.08, 0.80, "honest cars'\nposition error\n(95 in 100\nare inside\nthe grey)",
            fontsize=19, color="#555555", va="top")
    ax.axvspan(lo, hi, color=RUST, alpha=0.16, lw=0)
    ax.axvline(cross, color=RUST, lw=2.4, ls="--")
    ax.text(cross * 1.12, 0.40,
            f"floor {cross:.1f} m\n95% interval\n{lo:.1f} to {hi:.1f} m",
            fontsize=22, color=RUST, va="top", fontweight="bold")
    ax.plot(px, py, "o-", color=NAVY, lw=4, ms=13,
            label="receivers pool their measurements")
    ax.plot(sx, sy, "s--", color="#666666", lw=3, ms=11, label="one receiver alone")
    ax.set_xscale("log")
    ax.set_xlim(5, 300)
    ax.set_xticks([5, 10, 20, 50, 100, 200])
    ax.set_xticklabels(["5", "10", "20", "50", "100", "200"])
    ax.minorticks_off()
    ax.set_xlabel("size of the lie: distance from true to claimed position (metres)")
    ax.set_ylabel("share of lying cars caught")
    ax.set_ylim(-0.05, 1.08)
    ax.legend(loc="upper left", frameon=False, borderaxespad=0.2)
    ax.grid(alpha=0.3)
    save(fig, "floor")


def fig_geometry(w_mm, h_mm):
    d = json.loads((RUNS / "campaign_gnss/booth_surface.json").read_text())
    tx, ty = d["true_position"]["x"], d["true_position"]["y"]
    rx = np.array([[r["x"] - tx, r["y"] - ty] for r in d["receivers"]])
    hw = d["road_halfwidth"]

    fig = plt.figure(figsize=(w_mm * MM, h_mm * MM))
    ax = fig.add_axes([0.07, 0.40, 0.91, 0.58])
    ax.axhspan(-hw, hw, color="0.90", zorder=0, lw=0)
    ax.axhline(0, color="0.6", lw=1.2, ls=(0, (8, 8)), zorder=1)
    ax.scatter(rx[:, 0], rx[:, 1], s=110, c=TEAL, zorder=3,
               label=f"the {len(rx)} receivers that heard it")
    ax.scatter([0], [0], s=520, marker="*", c=RUST, zorder=4,
               label="the transmitting car")
    ax.set_aspect("equal")
    ax.set_ylim(-hw * 4, hw * 4)
    ax.set_yticks([-40, 0, 40])
    ax.set_xlabel("along the road (metres); the grey band is the road, drawn to the same scale")
    ax.set_ylabel("across (m)")
    fig.legend(loc="lower center", ncol=2, frameon=False, columnspacing=3,
               borderaxespad=0.1)
    ax.grid(alpha=0.3, axis="x")
    save(fig, "geometry")
    return np.ptp(rx[:, 0]), np.ptp(rx[:, 1])


def fig_direction(w_mm, h_mm):
    angles = grab("campaign_gnss/logs/geometry_bound.log",
                  r"major axis\s+([\d.]+) deg from the road",
                  "the ellipse orientation percentiles")
    q25, q50, q75 = [float(a) for a in angles[:3]]
    rows = grab("drift/logs/br_gnss_free.log",
                r"^\s+\d+ m(?:\s+[-\d.]+){7}\s+([\d.]+)\s+[-\d.]+$",
                "the off-axis angle of the best lies")
    lo, hi = min(float(r) for r in rows), max(float(r) for r in rows)

    fig = plt.figure(figsize=(w_mm * MM, h_mm * MM))
    ax = fig.add_axes([0.02, 0.36, 0.96, 0.62])
    ax.axvspan(lo, hi, color=RUST, alpha=0.25, lw=0,
               label="where a search of 72 directions\nput the attacker's best lie")
    ax.plot([q25, q75], [1, 1], color=NAVY, lw=8, solid_capstyle="butt",
            label="weakest direction predicted from\nreceiver positions alone (middle half)")
    ax.plot([q50], [1], "o", color=NAVY, ms=22)
    ax.text(q50, 1.22, f"{q50:.1f}°", fontsize=24, color=NAVY, ha="center",
            fontweight="bold")
    ax.set_xlim(0, 92)
    ax.set_ylim(0.6, 2.9)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_xticks([0, 30, 60, 90])
    labels = ax.set_xticklabels(["0°\nalong the road", "30°", "60°",
                                 "90°\nstraight across"])
    labels[0].set_ha("left")
    labels[-1].set_ha("right")
    ax.legend(loc="upper left", frameon=False, borderaxespad=0)
    ax.grid(axis="x", alpha=0.3)
    save(fig, "direction")


def make_qr():
    import segno
    segno.make(DEMO, error="h").save(str(FIGS / "qr.svg"), scale=10, border=4,
                                    dark="#1b3a5c")
    print("wrote figures/qr.svg")


def render_pdf():
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=4000", f"--print-to-pdf={PDF}",
                    POSTER.as_uri()], check=True, capture_output=True)
    boxes = re.findall(rb"MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", PDF.read_bytes())
    if len(boxes) != 1:
        sys.exit(f"FAILED: poster.pdf has {len(boxes)} pages, expected one")
    w, h = (float(v) / 72 * 25.4 for v in boxes[0])
    if abs(w - 841) > 1 or abs(h - 1189) > 1:
        sys.exit(f"FAILED: poster.pdf is {w:.0f} x {h:.0f} mm, not A0")
    print(f"wrote poster.pdf, one page, {w:.0f} x {h:.0f} mm")


def audit():
    """Render the poster with ?audit and read back what the page measured."""
    dom = subprocess.run([CHROME, "--headless", "--disable-gpu",
                          "--virtual-time-budget=4000", "--dump-dom",
                          POSTER.as_uri() + "?audit"],
                         check=True, capture_output=True, text=True).stdout
    m = re.search(r'<pre id="audit">(.*?)</pre>', dom, re.S)
    if not m:
        sys.exit("FAILED: the poster did not write its audit block")
    import html
    return json.loads(html.unescape(m.group(1)))


# The one all-capitals word the guide's "avoid acronyms" does not reach. The
# reference list is outside the check.
ALLOWED_CAPS = {"RMIT"}


def numbers(text):
    """Numeric tokens worth checking: decimals, thousands, and integers of two
    or more digits, minus years and the poster's own figure numbers."""
    toks = set(re.findall(r"\d{1,3}(?:,\d{3})+|\d+\.\d+|\d{2,}", text))
    return {t for t in toks if not re.fullmatch(r"(19|20)\d\d", t)}


def check(a):
    bad = 0
    small = [s for s in a["sizes"] if s["pt"] < 18 - 1e-6]
    for s in small[:10]:
        print(f"FAIL text below 18 pt ({s['pt']:.1f} pt): {s['text'][:60]!r}")
    bad += bool(small)
    if not small:
        print(f"ok   smallest visible text {min(s['pt'] for s in a['sizes']):.1f} pt")

    if a["overflow"]:
        print(f"FAIL content runs past the sheet: {a['used']} px of {a['height']}")
        bad += 1
    else:
        print(f"ok   fits the sheet ({a['used']} of {a['height']} px)")

    body = a["text"]
    # The reference list is checked by the report build, not here.
    prose = body.split("References", 1)[0]
    caps = sorted({w for w in re.findall(r"\b[A-Z][A-Z0-9-]{1,}\b", prose)
                   if w not in ALLOWED_CAPS})
    if caps:
        print(f"FAIL acronyms on the poster: {', '.join(caps)}")
        bad += 1
    else:
        print("ok   no acronyms outside the allowed list")

    # Both sources are private working files; on a machine with neither the
    # number check cannot run, and says so rather than passing.
    results = ROOT / "docs/RESULTS.md"
    sources = results.read_text() if results.exists() else ""
    if not sources and not REPORT.exists():
        print("FAIL no pinned source on this machine to check numbers against")
        return bad + 1
    if REPORT.exists():
        sources += "".join(p.read_text() for p in REPORT.glob("*.md"))
    else:
        print("note report content not on this machine; checking the results log only")
    missing = sorted(t for t in numbers(prose) if t not in sources)
    for t in missing:
        print(f"FAIL number not found in RESULTS.md or the report: {t}")
    bad += bool(missing)
    if not missing:
        print(f"ok   {len(numbers(prose))} numbers on the poster all found in pinned sources")

    if re.search("[–—]", body):
        print("FAIL a dash on the poster")
        bad += 1
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not args.check:
        fig_floor(460, 250)
        fig_geometry(785, 95)
        fig_direction(420, 120)
        make_qr()
        render_pdf()
    bad = check(audit())
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
