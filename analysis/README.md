# Analysis pipeline

Everything from raw simulator tables to the results. Python 3.9 with pandas,
scikit-learn, scipy and torch. This is separate from the ns-3 build, which
needs Python 3.12; do not mix the two.

## The rule the whole pipeline is built around

`build_features.py` opens only the receive-side tables. `attach_labels()` is
the only function permitted to read the transmit log, and an assertion fails
the run if any column named `key_*` or `label_*` reaches the feature list. A
feature that a real receiver could not compute cannot enter the dataset by
accident, which is a structural guarantee rather than a review step.

The one narrow exception is the radio-to-message binding, which is
reconstructed from the transmit log because a nearest-time join misattributes
badly under load. It recovers an observable a real receiver has by
construction: which radio sent the message it just decoded.

## Order of operations

    build_corpus.py DIR seed1 seed2 ... -o corpus.csv     # writes .csv and .pkl
    merge_corpora.py part1.pkl part2.pkl -o corpus.pkl    # if seeds built separately
    validate_dataset.py corpus.pkl                        # eight adversarial gates
    make_splits.py corpus.pkl --out-dir DIR               # balanced + realism
    benchmark.py corpus.pkl --report --sample 250000      # app / phy / fused
    check_partition_skew.py corpus.pkl                    # BEFORE any federated run
    federated.py corpus.pkl --seeds 8 --rounds 20 --tune

`drift.py` sits outside that sequence because it reads several finished corpora
at once rather than one:

    drift.py --scenarios light=A/corpus.pkl dense=B/corpus.pkl --sample 150000
    drift.py --temporal A/corpus.pkl --cut 0.5 --bins 6

`offset_floor.py` is the same shape: it reads the corpus and the transmit logs
together, because the displacement each attacker realised is in the logs and
the detection outcome is in the corpus.

    offset_floor.py corpus.pkl --run-dir DIR --tags seed1 ... --pooled pooled.pkl

`veremi_bridge.py` runs this project's application-layer detector on VeReMi
Extension, on the seventeen features computable from both datasets. Prove the
feature definitions still match before trusting a comparison, because the
arithmetic is duplicated from `build_features.py` rather than imported:

    veremi_bridge.py --selftest RUN_DIR seed1 --corpus RUN_DIR/corpus_seed1.pkl
    veremi_bridge.py /path/to/veremi/sim --corpus corpus.pkl

Both arms of the scenario comparison are trained on the same number of rows and
scored on the same test rows, because otherwise the difference between them is
mostly training set size rather than the shift being measured.

`merge_corpora.py` exists because building several large seeds in one process
runs out of memory, and building them separately gives every seed the same
station-id offset. It reapplies the offset a combined build would have applied
and asserts that no identifier is shared between seeds, because a naive
concatenation would put different physical stations under one id and silently
invalidate every grouped fold.

## What each script is for

| script | question it answers |
|---|---|
| `build_features.py` | windowing and feature extraction, 22 application and 28 radio features |
| `build_corpus.py` | combine seeds, namespace station ids so grouped splits stay honest |
| `merge_corpora.py` | combine seeds built in separate processes |
| `validate_dataset.py` | is this dataset trivially separable, duplicated, or leaking labels |
| `make_splits.py` | balanced training set and a realism set at true prevalence, holding out whole stations |
| `benchmark.py` | do application and radio features catch different attacks |
| `feature_selection.py` | how many features are needed, selected inside the folds |
| `pooled_consensus.py` | does pooling observations across receivers resolve position falsification |
| `pool_separation.py` | what the cross-receiver statistics know, per class, without a classifier |
| `claim_permutation.py` | independence control: does a benign station given a false claim look like an attacker |
| `power_evasion.py` | can transmit power control, or a chosen claim, defeat the received-power check |
| `pooled_regions.py` | pooled units per roadside unit region, the federated deployment version |
| `measure_pooling_cost.py` | what forming the cross-receiver statistics costs |
| `check_partition_skew.py` | is the federated partition actually skewed, or is the panel meaningless |
| `federated.py` | FedAvg, FedProx, FedNova, FedLC, FedProto, and DP-FedAvg |
| `evaluate_deployment.py` | false positive rate at true prevalence and alerts per hour |
| `persistence_filter.py` | alert episodes and K-of-M rules, the deployable operating point |
| `calibration.py` | PRR, BLER and channel occupancy against TR 37.885 |
| `measure_latency.py` | end to end detection latency, window fill included |
| `a1_victim_effect.py` | does sensing manipulation damage its neighbours |
| `check_campaign.py` | is one seed of a campaign configured correctly, before hours are spent on the rest |
| `drift.py` | does the detector survive a scenario or a period it was not trained on |
| `offset_floor.py` | how far must a vehicle lie before anyone can tell, against the benign error |
| `veremi_bridge.py` | does the application layer's blindness to constant offsets reproduce on somebody else's dataset |
| `verify_results.py` | every reported number still matches the log that produced it |
| `regenerate.sh` | takes a finished campaign through every stage above, in order, each to its own log |

Once a campaign has finished, `regenerate.sh` runs the whole sequence in one
pass and writes each stage to its own log, so a single stage can be repeated
after a fix without redoing the work before it.

    ./analysis/regenerate.sh <run-dir> <max-time-ms> seed1 seed2 ... seed8
    WINDOW_STUDY=1 ./analysis/regenerate.sh ...   # also rebuild the window comparison

Run `check_campaign.py` on the first seed of any new campaign before letting
the rest of it generate. It reads only the small transmit table, so it costs
seconds, and it catches the misconfigurations that are expensive to find
afterwards: a road with no roadside units, an attack class that drew no
stations, a message mix where CPM has overtaken CAM, congestion control that is
not responding, and injected position errors of the wrong size.

## Methodology notes that are easy to get wrong

**Group every split by transmitting station.** Windows from one station are not
independent, so a random split puts the same vehicle on both sides and the
score means nothing.

**Compare at measurement precision, not float precision.** Duplicate and
overlap tests on continuous features are vacuous otherwise, because no two
floats ever match. `validate_dataset.py` quantises to 1 dB, 1 ms and 1 m.

**Count distinct stations, never rows or tracks, before believing a per-class
number.** One station produces thousands of windows and many tracks, so a class
can look well supported and rest on two vehicles.

**Six seeds minimum for a paired Wilcoxon, eight preferred.** The two-sided
test floors at 2/2^n, so at five seeds a method winning on every single seed
still cannot reach p < 0.05.

**Report per class, and run the arm that should show no effect.** Four results
in this project reversed when properly controlled. An aggregate improvement is
not evidence until the control that should not improve has been run.

**Select features inside the training fold.** Ranking on the whole corpus and
then reporting cross-validated scores on the survivors is a selection leak.
