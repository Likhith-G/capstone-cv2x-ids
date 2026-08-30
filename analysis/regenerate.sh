#!/bin/zsh
# Take a finished campaign through every analysis, in order, into one place.
#
# Each stage writes its own log. Nothing here is interactive and nothing
# depends on a stage that has not finished, so a stage can be re-run alone
# after a fix without redoing the ones before it.
#
# Usage: regenerate.sh <run-dir> <max-time-ms> <seed tags...>
#   regenerate.sh ~/ns3-v2x/runs/campaign_v3 59000 seed1 seed2 ... seed8
#
# Corpora are built ONE SEED AT A TIME and then merged. Several large seeds in
# one process runs out of memory on an 8 GB machine, and building them
# separately gives every seed the same station id offset, which merge_corpora
# corrects and asserts.
set -e
DIR=$1; MAXT=$2; shift 2; TAGS=($@)
PY=/usr/bin/python3
A=$(cd "$(dirname $0)" && pwd)
L=$DIR/logs; mkdir -p $L

echo "[1/8] per-seed corpora"
PARTS=()
for t in $TAGS; do
  if [[ ! -f $DIR/corpus_$t.pkl ]]; then
    $PY -u $A/build_corpus.py $DIR $t --max-time-ms $MAXT \
        -o $DIR/corpus_$t.csv > $L/corpus_$t.log 2>&1
    rm -f $DIR/corpus_$t.csv          # the pickle carries every column
  fi
  PARTS+=($DIR/corpus_$t.pkl)
done

echo "[2/8] merge"
$PY -u $A/merge_corpora.py $PARTS -o $DIR/corpus.pkl > $L/merge.log 2>&1

echo "[3/8] integrity gates"
$PY -u $A/validate_dataset.py $DIR/corpus.pkl > $L/validate.log 2>&1

echo "[4/8] calibration"
$PY -u $A/calibration.py $DIR ${TAGS[1]} > $L/calibration.log 2>&1 || true

echo "[5/8] cross-layer benchmark"
$PY -u $A/benchmark.py $DIR/corpus.pkl --report --sample 250000 --folds 3 \
    --trees 100 > $L/benchmark.log 2>&1

echo "[6/8] multi-observer pooling"
$PY -u $A/pooled_consensus.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    --folds 5 --repeats 2 --trees 100 --obs-cap 60000 --jobs 4 \
    --class-weight none --validate --out $DIR/pooled.pkl > $L/pooled.log 2>&1
$PY -u $A/pool_separation.py $DIR/pooled.pkl > $L/pool_separation.log 2>&1
$PY -u $A/claim_permutation.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    > $L/claim_permutation.log 2>&1
$PY -u $A/power_evasion.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    --classes 1 3 4 6 > $L/power_evasion.log 2>&1

echo "[7/8] federated"
$PY -u $A/check_partition_skew.py $DIR/corpus.pkl > $L/skew.log 2>&1
$PY -u $A/federated.py $DIR/corpus.pkl --observer-role rsu --seeds 8 \
    --rounds 20 --tune > $L/federated.log 2>&1 || \
$PY -u $A/federated.py $DIR/corpus.pkl --seeds 8 --rounds 20 --tune \
    > $L/federated.log 2>&1

echo "[8/8] deployment and latency"
mkdir -p $DIR/split
$PY -u $A/make_splits.py $DIR/corpus.pkl --out-dir $DIR/split > $L/splits.log 2>&1
$PY -u $A/evaluate_deployment.py --balanced $DIR/split/balanced.pkl \
    --realism $DIR/split/realism.pkl > $L/deployment.log 2>&1
$PY -u $A/measure_latency.py $DIR/corpus.pkl > $L/latency.log 2>&1

echo "DONE. logs in $L"
