#!/usr/bin/env python3
"""
validate_dataset.py -- Capstone: Cybersecurity for Connected Cars

Mandatory plausibility and integrity checks on the generated dataset.
All checks must PASS before the dataset is used in the report.
"""

import sys
import numpy as np
import pandas as pd


def run_checks(df):
    """Run all validation checks. Returns (passed, failed) counts."""
    checks_passed = 0
    checks_failed = 0

    def check(name, condition, detail=""):
        nonlocal checks_passed, checks_failed
        if condition:
            checks_passed += 1
            print(f"  PASS: {name}")
        else:
            checks_failed += 1
            print(f"  FAIL: {name}  {detail}")

    print("=" * 60)
    print("DATASET VALIDATION REPORT")
    print("=" * 60)

    # -- Structural checks --------------------------------------------------
    print("\n--- Structural Checks ---")
    check("Has rows", len(df) > 0, f"got {len(df)} rows")
    check("Has label_binary", "label_binary" in df.columns)
    check("Has label_attack_type", "label_attack_type" in df.columns)
    check("Binary labels valid",
          df["label_binary"].isin([0, 1]).all(),
          f"invalid values: {df['label_binary'].unique()}")

    expected_cols = [
        "bsm_mean_iat", "bsm_std_iat", "flood_mean_iat", "flood_std_iat"
    ]
    for col in expected_cols:
        check(f"Has column {col}", col in df.columns)

    # -- Scale checks -------------------------------------------------------
    print("\n--- Scale Checks ---")
    check("Dataset has > 5000 rows",
          len(df) > 5000,
          f"got {len(df)} rows (target: 10x of original 720)")

    n_scenarios = df["scenario_id"].nunique()
    check("All 12 scenarios present",
          n_scenarios == 12,
          f"got {n_scenarios} scenarios")

    n_attack_types = df["label_attack_type"].nunique()
    check("All 12 attack types present",
          n_attack_types == 12,
          f"got {n_attack_types} types: {df['label_attack_type'].unique()}")

    # Check attack sample count per class
    atk_counts = df[df["label_binary"] == 1]["label_attack_type"].value_counts()
    min_atk_count = atk_counts.min() if len(atk_counts) > 0 else 0
    check("Each attack class has >= 50 windows",
          min_atk_count >= 50,
          f"smallest attack class has {min_atk_count} windows")

    # -- Physical plausibility checks ---------------------------------------
    print("\n--- Physical Plausibility ---")

    check("mean_iat > 0 (all rows)",
          (df["mean_iat"] > 0).all(),
          f"{(df['mean_iat'] <= 0).sum()} rows with non-positive IAT")

    check("duration > 0 (all rows)",
          (df["duration"] > 0).all(),
          f"{(df['duration'] <= 0).sum()} rows with non-positive duration")

    check("n_pkts >= 10 (all rows)",
          (df["n_pkts"] >= 10).all(),
          f"min n_pkts = {df['n_pkts'].min()}")

    check("pkt_rate > 0",
          (df["pkt_rate"] > 0).all())

    check("mean_pos_deviation >= 0",
          (df["mean_pos_deviation"] >= 0).all())

    check("mean_speed_deviation >= 0",
          (df["mean_speed_deviation"] >= 0).all())

    # -- Feature range checks -----------------------------------------------
    print("\n--- Feature Range Checks ---")

    benign = df[df["label_attack_type"] == "Benign"]
    if len(benign) > 0:
        benign_msg_freq = benign["msg_freq"].mean()
        check("Benign msg_freq ~ 10 Hz",
              5 <= benign_msg_freq <= 15,
              f"got {benign_msg_freq:.2f} Hz (expected ~10 Hz)")

        benign_iat = benign["bsm_mean_iat"].mean()
        check("Benign bsm_mean_iat ~ 0.1s",
              0.05 <= benign_iat <= 0.2,
              f"got {benign_iat:.4f}s (expected ~0.1s)")

        benign_pos_dev = benign["mean_pos_deviation"].mean()
        check("Benign mean_pos_deviation ~ 0",
              benign_pos_dev < 1.0,
              f"got {benign_pos_dev:.4f}m (should be ~0 for honest UEs)")

        benign_speed_dev = benign["mean_speed_deviation"].mean()
        check("Benign mean_speed_deviation ~ 0",
              benign_speed_dev < 1.0,
              f"got {benign_speed_dev:.4f} m/s (should be ~0)")

        benign_unique_ids = benign["unique_vehicle_ids"].mean()
        check("Benign unique_vehicle_ids == 1",
              0.9 <= benign_unique_ids <= 1.1,
              f"got {benign_unique_ids:.2f} (should be 1)")

    # -- Attack-specific plausibility ---------------------------------------
    print("\n--- Attack-Specific Plausibility ---")

    for atk in ["PositionSpoof", "RandomPosition"]:
        atk_df = df[df["label_attack_type"] == atk]
        if len(atk_df) > 0:
            atk_pos_dev = atk_df["mean_pos_deviation"].mean()
            check(f"{atk} pos_deviation >> 0",
                  atk_pos_dev > 50.0,
                  f"got {atk_pos_dev:.2f}m (should be 100s of meters)")

    fdi = df[df["label_attack_type"] == "FalseDataInjection"]
    if len(fdi) > 0:
        fdi_speed_dev = fdi["mean_speed_deviation"].mean()
        check("FDI speed_deviation >> 0",
              fdi_speed_dev > 5.0,
              f"got {fdi_speed_dev:.2f} m/s (should be 10+ m/s)")

    sybil = df[df["label_attack_type"] == "Sybil"]
    if len(sybil) > 0:
        sybil_ids = sybil["unique_vehicle_ids"].mean()
        check("Sybil unique_vehicle_ids > 1",
              sybil_ids > 2.0,
              f"got {sybil_ids:.2f} (should be ~5)")

    vdos = df[df["label_attack_type"] == "VehicularDoS"]
    if len(vdos) > 0:
        vdos_freq = vdos["msg_freq"].mean()
        check("VehicularDoS msg_freq >> 10 Hz",
              vdos_freq > 100,
              f"got {vdos_freq:.2f} Hz (should be ~1000 Hz)")

    replay = df[df["label_attack_type"] == "Replay"]
    if len(replay) > 0:
        replay_seq = replay["seq_anomaly"].mean()
        check("Replay seq_anomaly > 0 (at least some windows)",
              replay_seq > 0,
              f"got mean {replay_seq:.2f} (should be > 0 after fix)")

        replay_pos = replay["mean_pos_deviation"].mean()
        check("Replay pos_deviation >> 0 (stale positions)",
              replay_pos > 10.0,
              f"got {replay_pos:.2f}m (should be 40-75m for 5s delay)")

    # Network attack flood ratio checks
    if "flood_ratio" in df.columns:
        for atk in ["UDPFlood", "ICMPFlood", "SYNFlood", "HTTPFlood", "SlowDoS"]:
            atk_df = df[df["label_attack_type"] == atk]
            if len(atk_df) > 0:
                fr = atk_df["flood_ratio"].mean()
                check(f"{atk} flood_ratio > 0",
                      fr > 0.1,
                      f"got {fr:.4f} (should be >> 0 for flood attacks)")

    # -- Label contamination check ------------------------------------------
    print("\n--- Label Contamination Check ---")

    for scenario in sorted(df["scenario_id"].unique()):
        if scenario == "S00":
            continue
        scenario_df = df[df["scenario_id"] == scenario]
        benign_in_scenario = scenario_df[scenario_df["label_binary"] == 0]
        attack_in_scenario = scenario_df[scenario_df["label_binary"] == 1]
        check(f"{scenario} has BOTH benign + attack rows",
              len(benign_in_scenario) > 0 and len(attack_in_scenario) > 0,
              f"benign={len(benign_in_scenario)}, attack={len(attack_in_scenario)}")

    # -- Attacker count check -----------------------------------------------
    print("\n--- Multi-Attacker Check ---")

    for scenario in sorted(df["scenario_id"].unique()):
        if scenario == "S00":
            continue
        scenario_df = df[df["scenario_id"] == scenario]
        atk_nodes = scenario_df[scenario_df["label_binary"] == 1]["node_id"].nunique()
        check(f"{scenario} has >= 3 attacker nodes",
              atk_nodes >= 3,
              f"got {atk_nodes} attacker nodes (expected 5)")

    # -- Summary ------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"RESULT: {checks_passed} passed, {checks_failed} failed")
    if checks_failed == 0:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED -- review above")
    print(f"{'='*60}")

    return checks_passed, checks_failed


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "output/dataset.csv"
    print(f"Loading {path}...")
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns\n")

    passed, failed = run_checks(df)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
