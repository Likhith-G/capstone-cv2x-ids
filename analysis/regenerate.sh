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
# Set WINDOW_STUDY=1 to also rebuild the window length comparison, which needs
# its own corpora at 200, 500 and 1000 ms and roughly doubles the run:
#   WINDOW_STUDY=1 regenerate.sh ...
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

echo "[1/9] per-seed corpora"
PARTS=()
for t in $TAGS; do
  if [[ ! -f $DIR/corpus_$t.pkl ]]; then
    $PY -u $A/build_corpus.py $DIR $t --max-time-ms $MAXT \
        -o $DIR/corpus_$t.csv > $L/corpus_$t.log 2>&1
    rm -f $DIR/corpus_$t.csv          # the pickle carries every column
  fi
  PARTS+=($DIR/corpus_$t.pkl)
done

echo "[2/9] merge"
$PY -u $A/merge_corpora.py $PARTS -o $DIR/corpus.pkl > $L/merge.log 2>&1

echo "[3/9] integrity gates"
$PY -u $A/validate_dataset.py $DIR/corpus.pkl > $L/validate.log 2>&1

echo "[4/9] calibration"
$PY -u $A/calibration.py $DIR ${TAGS[1]} > $L/calibration.log 2>&1 || true

echo "[5/9] cross-layer benchmark"
$PY -u $A/benchmark.py $DIR/corpus.pkl --report --sample 250000 --folds 3 \
    --trees 100 > $L/benchmark.log 2>&1

echo "[6/9] multi-observer pooling"
$PY -u $A/pooled_consensus.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    --folds 5 --repeats 2 --trees 100 --obs-cap 60000 --jobs 4 \
    --class-weight none --validate --out $DIR/pooled.pkl > $L/pooled.log 2>&1
$PY -u $A/pool_separation.py $DIR/pooled.pkl > $L/pool_separation.log 2>&1

# The same pooling with the position fit bounded to the carriageway. Measured
# on the corpus this replaces, that constraint cuts localisation error from
# 62.6 m to 17.5 m and lifts detection of the best-response attacker at 50 m
# from 0.282 to 0.398. Whether it also helps CLASSIFICATION is a different
# question and is not assumed: both tables are built so the comparison is
# measured rather than argued, and the unconstrained one stays the default so
# that a result already written up does not move underneath it.
$PY -u $A/pooled_consensus.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    --folds 5 --repeats 2 --trees 100 --obs-cap 60000 --jobs 4 \
    --class-weight none --validate --road-halfwidth \
    --out $DIR/pooled_road.pkl > $L/pooled_road.log 2>&1
$PY -u $A/pool_separation.py $DIR/pooled_road.pkl > $L/pool_separation_road.log 2>&1
$PY -u $A/claim_permutation.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    > $L/claim_permutation.log 2>&1
$PY -u $A/power_evasion.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    --classes 1 3 4 6 13 > $L/power_evasion.log 2>&1

echo "[7/9] federated"
$PY -u $A/check_partition_skew.py $DIR/corpus.pkl > $L/skew.log 2>&1
$PY -u $A/federated.py $DIR/corpus.pkl --observer-role rsu --seeds 8 \
    --rounds 20 --tune > $L/federated.log 2>&1 || \
$PY -u $A/federated.py $DIR/corpus.pkl --seeds 8 --rounds 20 --tune \
    > $L/federated.log 2>&1

echo "[8/9] the region pipeline, which is where the client column matters"
# A region-pooled table identifies a client by REGION. federated.py,
# make_splits.py and check_partition_skew.py all default to the per receiver
# column, which is right for every other caller and wrong for this one. Getting
# it wrong killed this pipeline three times before these lines existed, so the
# stages live here with the flag rather than in a shell history somewhere.
$PY -u $A/pooled_regions.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    --road-halfwidth --out $DIR/pooled_regions.pkl \
    > $L/pooled_regions.log 2>&1
$PY -u $A/check_partition_skew.py $DIR/pooled_regions.pkl \
    --observer-col key_region > $L/skew_regions.log 2>&1
$PY -u $A/federated.py $DIR/pooled_regions.pkl --observer-col key_region \
    --seeds 8 --rounds 20 --tune > $L/federated_regions.log 2>&1
$PY -u $A/federated.py $DIR/pooled_regions.pkl --observer-col key_region \
    --drop-consensus --seeds 8 --rounds 20 --tune \
    > $L/federated_regions_nocons.log 2>&1
$PY -u $A/federated.py $DIR/pooled_regions_single.pkl \
    --observer-col key_region --seeds 8 --rounds 20 --tune \
    > $L/federated_regions_single.log 2>&1
$PY -u $A/federated.py $DIR/pooled_regions.pkl --observer-col key_region \
    --seeds 8 --rounds 20 --dp-clip 1.0 --dp-noise 0.0 0.5 1.0 2.0 3.0 \
    > $L/dp_sweep.log 2>&1
mkdir -p $DIR/split_regions
$PY -u $A/make_splits.py $DIR/pooled_regions.pkl --observer-col key_region \
    --out-dir $DIR/split_regions > $L/splits_regions.log 2>&1
$PY -u $A/persistence_filter.py --balanced $DIR/split_regions/balanced.pkl \
    --realism $DIR/split_regions/realism.pkl > $L/persistence.log 2>&1
$PY -u $A/measure_pooling_cost.py $DIR/corpus.pkl --run-dir $DIR --tags $TAGS \
    > $L/pooling_cost.log 2>&1

echo "[9/9] deployment and latency"
mkdir -p $DIR/split
$PY -u $A/make_splits.py $DIR/corpus.pkl --out-dir $DIR/split > $L/splits.log 2>&1
$PY -u $A/evaluate_deployment.py --balanced $DIR/split/balanced.pkl \
    --realism $DIR/split/realism.pkl > $L/deployment.log 2>&1
$PY -u $A/measure_latency.py $DIR/corpus.pkl > $L/latency.log 2>&1

# Window length is a design knob, not a fixed choice, and section 7 of the
# results reports it. It needs its own corpora because the window length is a
# feature-extraction parameter rather than an analysis one. Three seeds are
# enough for a trend and eight would cost three times the build for no more
# insight. Opt in, because it roughly doubles the run.
if [[ "$WINDOW_STUDY" == "1" ]]; then
  echo "[10/10] window length study"
  WT=(${TAGS[1]} ${TAGS[2]} ${TAGS[3]})
  for w in 200 500 1000; do
    WP=()
    for t in $WT; do
      if [[ ! -f $DIR/w${w}_$t.pkl ]]; then
        $PY -u $A/build_corpus.py $DIR $t --max-time-ms $MAXT --window-ms $w \
            -o $DIR/w${w}_$t.csv > $L/w${w}_$t.log 2>&1
        rm -f $DIR/w${w}_$t.csv
      fi
      WP+=($DIR/w${w}_$t.pkl)
    done
    $PY -u $A/merge_corpora.py $WP -o $DIR/corpus_w$w.pkl > $L/merge_w$w.log 2>&1
    $PY -u $A/benchmark.py $DIR/corpus_w$w.pkl --sample 150000 --folds 3 \
        --trees 100 > $L/benchmark_w$w.log 2>&1
  done
fi

echo "DONE. logs in $L"
