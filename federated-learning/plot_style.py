#!/usr/bin/env python3
"""
plot_style.py -- Publication-quality matplotlib configuration for CV2X-IDS.

Usage:
    from plot_style import apply_style, COLORS, COL_WIDTH, FULL_WIDTH
    apply_style()
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COL_WIDTH = 3.5   # single-column figure width (inches)
FULL_WIDTH = 7.0  # double-column / full-width figure width (inches)
DPI = 300

COLORS = {
    "fedavg_c3": "#66c2a5",
    "fedavg_c5": "#fc8d62",
    "fedprox_c3": "#8da0cb",
    "fedprox_c5": "#e78ac3",
    "centralized": "#333333",
    "highlight": "#e41a1c",
    "muted": "#999999",
}

PALETTE = ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3"]


def apply_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.framealpha": 0.8,
        "legend.edgecolor": "0.8",
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
        "axes.grid": True,
        "grid.alpha": 0.2,
        "grid.linewidth": 0.5,
        "axes.linewidth": 0.8,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "lines.linewidth": 1.5,
        "lines.markersize": 5,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })
