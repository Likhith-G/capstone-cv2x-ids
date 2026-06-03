#!/usr/bin/env python3
"""
build_dataset.py -- Capstone: Cybersecurity for Connected Cars

Reads per-packet CSV logs from NS-3 simulation,
computes per-window features using REAL timestamps and positions,
and produces the final dataset.

Data sources:
  1. packets_S*.csv  -- per-packet event log (BSM + flood traffic)
  2. meta_S*.json    -- scenario metadata

Output:
  dataset_v3.csv  -- one row per time window per UE
"""

import os
import sys
import json
import glob
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WINDOW_SIZE = 30   # seconds
STEP_SIZE   = 15   # seconds (50% overlap)
MIN_PKTS_PER_WINDOW = 10

# gNB positions (must match simulation.cc -- 4 gNBs along highway corridor)
GNB_POSITIONS = [
    np.array([0.0, 0.0]),      # gNB-A
    np.array([400.0, 0.0]),    # gNB-B
    np.array([800.0, 0.0]),    # gNB-C
    np.array([1200.0, 0.0]),   # gNB-D
]

# ---------------------------------------------------------------------------
# Feature computation from per-packet data
# ---------------------------------------------------------------------------
def compute_window_features(pkts_df, node_id, scenario_id, window_id,
                            window_start, window_end):
    """
    Compute features for a single time window from per-packet data.
    Handles MIXED traffic windows (BSM + flood packets from same node).
    All features derived from REAL NS-3 timestamps and MobilityModel positions.
    """
    n = len(pkts_df)
    tx_times = pkts_df["tx_time"].values
    pkt_sizes = pkts_df["pkt_size"].values

    # Separate BSM and flood packets
    bsm_mask = pkts_df["pkt_type"] == "bsm"
    flood_mask = pkts_df["pkt_type"] == "flood"
    bsm_pkts = pkts_df[bsm_mask]
    flood_pkts = pkts_df[flood_mask]
    n_bsm = len(bsm_pkts)
    n_flood = len(flood_pkts)

    # -- Timing features (from ALL packets, real timestamps) ----------------
    duration = tx_times[-1] - tx_times[0]
    if duration <= 0:
        duration = 1e-6  # avoid division by zero

    iats = np.diff(tx_times)
    mean_iat = float(np.mean(iats)) if len(iats) > 0 else 0.0
    std_iat  = float(np.std(iats))  if len(iats) > 0 else 0.0
    min_iat  = float(np.min(iats))  if len(iats) > 0 else 0.0
    max_iat  = float(np.max(iats))  if len(iats) > 0 else 0.0

    # -- Separated IAT features (BSM-only and flood-only) ------------------
    bsm_mean_iat  = 0.0
    bsm_std_iat   = 0.0
    flood_mean_iat = 0.0
    flood_std_iat  = 0.0

    if n_bsm > 1:
        bsm_iats = np.diff(bsm_pkts["tx_time"].values)
        bsm_mean_iat = float(np.mean(bsm_iats))
        bsm_std_iat  = float(np.std(bsm_iats))

    if n_flood > 1:
        flood_iats = np.diff(flood_pkts["tx_time"].values)
        flood_mean_iat = float(np.mean(flood_iats))
        flood_std_iat  = float(np.std(flood_iats))

    # -- Volume features (from ALL packets) ---------------------------------
    total_bytes = int(pkt_sizes.sum())
    pkt_rate  = n / duration
    byte_rate = total_bytes / duration

    # -- Packet size stats (from ALL packets) --------------------------------
    mean_pkt_size = float(np.mean(pkt_sizes))
    std_pkt_size  = float(np.std(pkt_sizes))

    # -- Vehicular features (from BSM packets ONLY) -------------------------
    if n_bsm > 0:
        true_x  = bsm_pkts["true_x"].values
        true_y  = bsm_pkts["true_y"].values
        claimed_x = bsm_pkts["claimed_x"].values
        claimed_y = bsm_pkts["claimed_y"].values

        # Position deviation
        pos_errors = np.sqrt(
            (claimed_x - true_x)**2 + (claimed_y - true_y)**2
        )
        mean_pos_deviation = float(np.mean(pos_errors))
        max_pos_deviation  = float(np.max(pos_errors))

        # Speed deviation
        true_speed    = bsm_pkts["true_speed"].values
        claimed_speed = bsm_pkts["claimed_speed"].values
        speed_errors  = np.abs(claimed_speed - true_speed)
        mean_speed_deviation = float(np.mean(speed_errors))
        max_speed_deviation  = float(np.max(speed_errors))

        # Heading change rate (BSM only)
        headings = bsm_pkts["claimed_heading"].values
        heading_changes = np.abs(np.diff(headings))
        bsm_iat_mean = bsm_mean_iat if bsm_mean_iat > 0 else 0.1
        heading_change_rate = (
            float(np.mean(heading_changes) / bsm_iat_mean)
            if len(heading_changes) > 0
            else 0.0
        )

        # Sequence number anomaly (replay detection) -- BSM only
        seq_nums  = bsm_pkts["seq_num"].values
        seq_jumps = np.diff(seq_nums.astype(np.int64))
        seq_anomaly = int(np.any(seq_jumps < 0) or np.any(seq_jumps > 100))

        # Unique vehicle IDs (Sybil detection) -- BSM only
        unique_vehicle_ids = int(bsm_pkts["vehicle_id"].nunique())

        # BSM message frequency
        bsm_duration = bsm_pkts["tx_time"].max() - bsm_pkts["tx_time"].min()
        msg_freq = n_bsm / bsm_duration if bsm_duration > 0 else n_bsm
        bsm_size_mean = float(np.mean(bsm_pkts["pkt_size"].values))
        bsm_size_std  = float(np.std(bsm_pkts["pkt_size"].values))

        # Spatial features (from BSM true positions)
        true_speed_mean = float(np.mean(true_speed))
        true_speed_std  = float(np.std(true_speed))
        mean_true_pos = np.array([np.mean(true_x), np.mean(true_y)])
    else:
        # Flood-only window: use true position from flood packets
        mean_pos_deviation = 0.0
        max_pos_deviation  = 0.0
        mean_speed_deviation = 0.0
        max_speed_deviation  = 0.0
        heading_change_rate  = 0.0
        seq_anomaly = 0
        unique_vehicle_ids = 0
        msg_freq = 0.0
        bsm_size_mean = 0.0
        bsm_size_std  = 0.0
        true_speed_mean = float(np.mean(pkts_df["true_speed"].values))
        true_speed_std  = float(np.std(pkts_df["true_speed"].values))
        mean_true_pos = np.array([
            np.mean(pkts_df["true_x"].values),
            np.mean(pkts_df["true_y"].values)
        ])

    # -- Flood ratio (key discriminator for network attacks) ----------------
    flood_ratio = n_flood / n if n > 0 else 0.0

    # -- Distance to nearest gNB -------------------------------------------
    distances_to_gnbs = [
        np.linalg.norm(mean_true_pos - gnb) for gnb in GNB_POSITIONS
    ]
    distance_to_gnb = float(min(distances_to_gnbs))

    # Region: index of the nearest gNB
    region_id = int(np.argmin(distances_to_gnbs))

    # -- Label: attack if ANY attack packets present in window ---------------
    attack_count = int(pkts_df["label"].sum())
    label_binary = 1 if attack_count > 0 else 0

    return {
        "scenario_id":           scenario_id,
        "node_id":               int(node_id),
        "window_id":             window_id,
        "window_start":          round(window_start, 4),
        "window_end":            round(window_end, 4),
        "duration":              round(duration, 6),
        "n_pkts":                n,
        "n_bsm":                 n_bsm,
        "n_flood":               n_flood,
        "flood_ratio":           round(flood_ratio, 4),
        "total_bytes":           total_bytes,
        "pkt_rate":              round(pkt_rate, 4),
        "byte_rate":             round(byte_rate, 4),
        "mean_iat":              round(mean_iat, 8),
        "std_iat":               round(std_iat, 8),
        "min_iat":               round(min_iat, 8),
        "max_iat":               round(max_iat, 8),
        "bsm_mean_iat":          round(bsm_mean_iat, 8),
        "bsm_std_iat":           round(bsm_std_iat, 8),
        "flood_mean_iat":        round(flood_mean_iat, 8),
        "flood_std_iat":         round(flood_std_iat, 8),
        "mean_pkt_size":         round(mean_pkt_size, 2),
        "std_pkt_size":          round(std_pkt_size, 2),
        "mean_pos_deviation":    round(mean_pos_deviation, 4),
        "max_pos_deviation":     round(max_pos_deviation, 4),
        "mean_speed_deviation":  round(mean_speed_deviation, 4),
        "max_speed_deviation":   round(max_speed_deviation, 4),
        "heading_change_rate":   round(heading_change_rate, 4),
        "seq_anomaly":           seq_anomaly,
        "unique_vehicle_ids":    unique_vehicle_ids,
        "msg_freq":              round(msg_freq, 4),
        "bsm_size_mean":         round(bsm_size_mean, 2),
        "bsm_size_std":          round(bsm_size_std, 2),
        "true_speed_mean":       round(true_speed_mean, 4),
        "true_speed_std":        round(true_speed_std, 4),
        "distance_to_gnb":       round(distance_to_gnb, 2),
        "region_id":             region_id,
        "label_binary":          label_binary,
    }


# ---------------------------------------------------------------------------
# Time-window slicing
# ---------------------------------------------------------------------------
def slice_into_windows(pkts_df, node_id, scenario_id,
                       window_size=WINDOW_SIZE, step=STEP_SIZE):
    """
    Slice a node's packet stream into overlapping time windows.
    Includes ALL packet types (BSM + flood) from that node.
    """
    t_start = pkts_df["tx_time"].min()
    t_end   = pkts_df["tx_time"].max()

    windows = []
    w = 0
    t0 = t_start

    while t0 + window_size <= t_end:
        t1 = t0 + window_size
        mask = (pkts_df["tx_time"] >= t0) & (pkts_df["tx_time"] < t1)
        window_pkts = pkts_df.loc[mask]

        if len(window_pkts) >= MIN_PKTS_PER_WINDOW:
            features = compute_window_features(
                window_pkts, node_id, scenario_id, w, t0, t1
            )
            windows.append(features)

        t0 += step
        w += 1

    return windows


# ---------------------------------------------------------------------------
# Assign attack type labels
# ---------------------------------------------------------------------------
SCENARIO_ATTACK_MAP = {
    "S00": "Benign",
    "S01": "UDPFlood",
    "S02": "ICMPFlood",
    "S03": "SYNFlood",
    "S04": "HTTPFlood",
    "S05": "SlowDoS",
    "S06": "PositionSpoof",
    "S07": "RandomPosition",
    "S08": "Replay",
    "S09": "FalseDataInjection",
    "S10": "Sybil",
    "S11": "VehicularDoS",
}


def assign_attack_labels(df):
    """
    Assign label_attack_type based on scenario + label_binary.
    Benign rows in attack scenarios are still labelled 'Benign'.
    """
    labels = []
    for _, row in df.iterrows():
        if row["label_binary"] == 0:
            labels.append("Benign")
        else:
            labels.append(
                SCENARIO_ATTACK_MAP.get(row["scenario_id"], "Unknown")
            )
    df["label_attack_type"] = labels
    return df


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    input_dir  = sys.argv[1] if len(sys.argv) > 1 else "v3_output"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "v3_output"

    packet_files = sorted(glob.glob(os.path.join(input_dir, "packets_S*.csv")))
    if not packet_files:
        print(f"ERROR: No packet CSV files found in {input_dir}/")
        sys.exit(1)

    print(f"Found {len(packet_files)} scenario files in {input_dir}/")

    all_windows = []

    for pf in packet_files:
        # Extract scenario ID from filename (packets_S00.csv -> S00)
        basename = Path(pf).stem           # packets_S00
        scenario_id = basename.split("_")[1]  # S00

        print(f"\nProcessing {scenario_id} ({pf})...")

        # ---- Load per-packet data -----------------------------------------
        df = pd.read_csv(pf)
        n_bsm = (df["pkt_type"] == "bsm").sum()
        n_flood = (df["pkt_type"] == "flood").sum()
        print(f"  Loaded {len(df)} packets ({n_bsm} BSM, {n_flood} flood)")

        # Process each node separately
        node_ids = sorted(df["node_id"].unique())
        for nid in node_ids:
            node_pkts = df[df["node_id"] == nid].sort_values("tx_time")
            windows = slice_into_windows(node_pkts, nid, scenario_id)
            all_windows.extend(windows)
            if windows:
                n_atk = sum(1 for w in windows if w["label_binary"] == 1)
                n_fl = sum(w["n_flood"] for w in windows)
                print(f"    Node {nid}: {len(windows)} windows "
                      f"({n_atk} attack, {len(windows)-n_atk} benign"
                      f"{f', {n_fl} flood pkts' if n_fl > 0 else ''})")

    # ---- Assemble final dataset -------------------------------------------
    if not all_windows:
        print("ERROR: No windows generated. Check packet CSV files.")
        sys.exit(1)

    dataset = pd.DataFrame(all_windows)
    dataset = assign_attack_labels(dataset)

    # Sort for reproducibility
    dataset = dataset.sort_values(
        ["scenario_id", "node_id", "window_id"]
    ).reset_index(drop=True)

    # Save
    output_path = os.path.join(output_dir, "dataset_v3.csv")
    dataset.to_csv(output_path, index=False)

    print(f"\n{'='*60}")
    print(f"Dataset saved: {output_path}")
    print(f"Total rows:    {len(dataset)}")
    print(f"Features:      {len(dataset.columns)}")
    print(f"\nClass distribution:")
    print(dataset["label_attack_type"].value_counts().to_string())
    print(f"\nBinary distribution:")
    print(dataset["label_binary"].value_counts().to_string())
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
