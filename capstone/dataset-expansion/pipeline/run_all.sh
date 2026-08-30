#!/bin/bash
# run_all.sh -- Run all 12 simulation scenarios and build the dataset
#
# Usage:
#   cd ~/ns-allinone-3.42/ns-3.42
#   bash pipeline/run_all.sh
#
# Expected runtime: ~2-3 hours on MacBook Air M2
# Output: output/dataset.csv (~18,000 rows)

set -e

OUTPUT_DIR="output"
mkdir -p "$OUTPUT_DIR"

echo "============================================================"
echo "Dataset Expansion: Full Batch Run"
echo "  40 UEs | 4 gNBs | 600s sim | 5 attackers per scenario"
echo "============================================================"
echo ""

# Scenario definitions: ID, AttackType
SCENARIOS=(
    "S00 Benign"
    "S01 UDPFlood"
    "S02 ICMPFlood"
    "S03 SYNFlood"
    "S04 HTTPFlood"
    "S05 SlowDoS"
    "S06 PositionSpoof"
    "S07 RandomPosition"
    "S08 Replay"
    "S09 FalseDataInjection"
    "S10 Sybil"
    "S11 VehicularDoS"
)

TOTAL=${#SCENARIOS[@]}
CURRENT=0

for entry in "${SCENARIOS[@]}"; do
    read -r SCENARIO ATTACK <<< "$entry"
    CURRENT=$((CURRENT + 1))

    echo ""
    echo "------------------------------------------------------------"
    echo "[$CURRENT/$TOTAL] Running $SCENARIO ($ATTACK)..."
    echo "------------------------------------------------------------"

    START_TIME=$(date +%s)
    SEED=$((42 + CURRENT))

    ./ns3 run "scratch/simulation \
        --scenario=$SCENARIO \
        --attackType=$ATTACK \
        --numUes=40 \
        --simTime=600 \
        --numAttackers=5 \
        --seed=$SEED \
        --outputDir=$OUTPUT_DIR"

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    echo "  Completed in ${ELAPSED}s"
done

echo ""
echo "============================================================"
echo "All simulations complete. Building dataset..."
echo "============================================================"

python3 pipeline/build_dataset.py "$OUTPUT_DIR" "$OUTPUT_DIR"

echo ""
echo "============================================================"
echo "Validating dataset..."
echo "============================================================"

python3 pipeline/validate_dataset.py "$OUTPUT_DIR/dataset.csv"

echo ""
echo "============================================================"
echo "Running baseline classifier..."
echo "============================================================"

python3 pipeline/baseline_classifier.py "$OUTPUT_DIR/dataset.csv"

echo ""
echo "============================================================"
echo "Splitting dataset (Train/Val/Test)..."
echo "============================================================"

python3 pipeline/split_dataset.py "$OUTPUT_DIR/dataset.csv"

echo ""
echo "============================================================"
echo "Generating visualisations..."
echo "============================================================"

python3 pipeline/visualise.py "$OUTPUT_DIR/dataset.csv" "$OUTPUT_DIR/figures"

echo ""
echo "============================================================"
echo "Generating FL partitions (Dirichlet, 5 clients, α=0.5)..."
echo "============================================================"

python3 pipeline/partition_fl.py "$OUTPUT_DIR/dataset.csv" 5 0.5 "$OUTPUT_DIR/partitions"

echo ""
echo "============================================================"
echo "BATCH COMPLETE"
echo "  Outputs in: $OUTPUT_DIR/"
echo "  Figures in: $OUTPUT_DIR/figures/"
echo "  Partitions in: $OUTPUT_DIR/partitions/"
echo "============================================================"
