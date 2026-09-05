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
    validate_dataset.py corpus.pkl                        # ten adversarial gates
    make_splits.py corpus.pkl --out-dir DIR               # balanced + realism
    benchmark.py corpus.pkl --report --sample 250000      # app / phy / fused
    check_partition_skew.py corpus.pkl                    # BEFORE any federated run
    federated.py corpus.pkl --seeds 8 --rounds 20 --tune
    pooled_regions.py corpus.pkl --run-dir DIR --tags ... --road-halfwidth
    federated.py pooled_regions.pkl --observer-col key_region --tune

**A region-pooled table identifies a client by `key_region`, not by receiver.**
`federated.py`, `make_splits.py` and `check_partition_skew.py` all default to
the per receiver column, which is right for every other caller and wrong for
this one. Getting it wrong killed the analysis chain three times before
`regenerate.sh` carried these stages, and the default is deliberately unchanged
because a table sniffing default would hide the distinction rather than remove
it.

`drift.py` sits outside that sequence because it reads several finished corpora
at once rather than one:

    drift.py --scenarios light=A/corpus.pkl dense=B/corpus.pkl --sample 150000
    drift.py --temporal A/corpus.pkl --cut 0.5 --bins 6

`offset_floor.py` is the same shape: it reads the corpus and the transmit logs
together, because the displacement each attacker realised is in the logs and
the detection outcome is in the corpus.

    offset_floor.py corpus.pkl --run-dir DIR --tags seed1 ... --pooled pooled.pkl

It also fits detection against log displacement across every station, which
locates the crossing with an interval instead of bracketing it between two
bands. That fit needs stations well below and well above the crossing as well as
inside it, and no single campaign has all three, so `--save-stations` writes a
run's per station table and `--locate-with` borrows another run's for the locate
step only. Borrowed stations never enter the banded table, and the borrow is
refused outright if the two runs sit more than a percentage point apart on their
benign false flag rate, because per station flag rates measured at different
operating points are not the same quantity.

    offset_floor.py MAIN/corpus.pkl --run-dir MAIN --tags ... \
        --save-stations /tmp/floor_stations.csv --corpus-tag main
    offset_floor.py FLOOR/corpus.pkl --run-dir FLOOR --tags ... \
        --locate-with /tmp/floor_stations.csv --corpus-tag floor

Borrowing compares two separately trained detectors, which only works if they
settled at the same operating point. Two corpora whose attackers sit at
different magnitudes will not, because one of them poses a harder position
problem. `--extra-corpus` is the stronger form: it trains and scores ONE
detector over both corpora, so the per station flag rates are the same quantity
by construction rather than by a check. It prefixes the second corpus's seed
tags and pushes its node identifiers clear of the first, because
`build_corpus.py` namespaces by seed position and both corpora reuse the same
identifiers, so a naive concatenation would put two physical stations under one
id and break every grouped fold. It asserts that afterwards.

    offset_floor.py MAIN/corpus.pkl --run-dir MAIN --tags seed1 ... \
        --extra-corpus FLOOR/corpus.pkl --extra-run-dir FLOOR \
        --extra-tags seed1 ... --extra-prefix floor

`geometry_bound.py` takes no classifier and simulates no attack. It fits the
propagation law on benign traffic, splits the residual into the part that
persists for the life of a link and the part that averages away, and computes
the Cramer-Rao bound on position with the intercept and exponent profiled out,
because the estimator fits them freely and the information they absorb is
information the position does not get. `--regions` scopes each pooled unit to
one roadside unit region, which is the deployment case and gives a very
different answer from corpus-wide pooling.

    geometry_bound.py corpus.pkl --run-dir DIR --tags seed1 ... [--regions]

`estimator_study.py` diagnoses the position fit before trying to improve it.
Weighting only helps if the residuals are heteroscedastic, and the diagnostic
found three faults rather than one: a single slope law leaves a mean that
changes sign with range, the spread varies with range, and the tails are heavy.
A wrong mean is not fixed by reweighting, and removing a calibrated mean is what
actually works. `--calibrate-tags` fits the curve on some seeds and evaluates
triples from the rest, which is the number to quote; without it the curve is
fitted and evaluated on the same corpus and the script says so.

    estimator_study.py corpus.pkl --run-dir DIR --tags seed1 ... \
        --calibrate-tags seed1 seed2 seed3 seed4 [--road-halfwidth 12]

`make_figures.py` renders to `docs/figures/` as PDF and PNG. It parses the logs
rather than recomputing from the corpus, because a figure recomputed
independently is how a plot comes to disagree with the table beside it, and a
parser that finds nothing exits with an error rather than drawing an empty axis.

    make_figures.py [--only placement direction calibration]

`federated_drift.py` answers the question the federated panel exists to answer.
Four arms on identical held-out clients of the target corpus and an identical
training row budget: trained on the other density, trained on the target
density, federated across both, and federated across both with twice the rows so
that breadth and volume can be read apart.

    federated_drift.py --source A/corpus.pkl --target B/corpus.pkl

`model_independence.py` runs the fused block under four learner families over
the same rows and folds, and reports the best score any of them reached per
class. The random forest runs first with the settings `benchmark.py` uses, so
its row is a reproduction check before any other row is believed.

    model_independence.py corpus.pkl --sample 250000 --folds 3

`plausibility_baseline.py` implements the standard misbehaviour checks, ART,
DMV, SSC, MGT, acceleration and a received-signal-strength range check, each
thresholded on the training fold's benign traffic at a stated false positive
rate rather than at a chosen constant.

    plausibility_baseline.py corpus.pkl --fpr 0.01

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
| `model_independence.py` | is the detection floor a property of the problem, or of the random forest |
| `geometry_bound.py` | what the receiver geometry and the noise allow, derived, with no classifier |
| `plausibility_baseline.py` | how the work stands against the field's standard checks rather than its own ablations |
| `federated_drift.py` | does federating across two densities recover what the density change costs |
| `make_figures.py` | the paper's figures, parsed out of the logs so they cannot drift from the tables |
| `estimator_study.py` | why the position fit misses, and which of weighting, robustness or a calibrated mean closes it |
| `correction_transfer.py` | whether the calibrated propagation correction is a property of range or shrinkage onto one corpus: calibrate on A, apply to B, and check each bin's mean is flat in along-road position |
| `make_release_splits.py` | the frozen train, validation and test partition shipped with the dataset, so another group can compare against these numbers. Grouped on the PHYSICAL TRANSMITTER, because sybil emits four claimed identities per vehicle and grouping on the claimed one splits a vehicle across partitions. Stratified, because five of eight seeds are missing an attack class and a seed level split would ship an unscoreable partition. `--audit` prints that coverage table |
| `check_release.py` | consumes the release bundle the way a stranger would, using only files inside it: checksums, shards against the schema, the partition covering every row once with no transmitter in two partitions, and a baseline trained and scored on the frozen split. A release nobody has consumed is a release that probably does not work |
| `make_booth_surface.py` | the response surface the EnGenius booth page is a lookup over. Imports `pooled_consensus` directly, so the statistic a visitor sees is the statistic in the paper rather than a re-implementation, and sampling it on a grid is what makes the interaction instant |
| `make_release.py` | assembles the publishable bundle: one gzipped CSV shard per seed, a machine readable schema, a 5,000 row sample, the frozen partition, the card, checksums, a citation file and the record metadata. Gzipped CSV rather than parquet because reading parquet needs a library and a benchmark nobody can open without a dependency is a worse benchmark |
| `make_dataset_card.py` | the dataset card, generated from the corpus so its counts cannot drift. Exits non-zero if any column has no curated description, so adding a feature forces documenting it |
| `verify_results.py` | every reported number still matches the log that produced it |
| `session_check.py` | the project's own bookkeeping: nothing running, git clean and untrailered, disk headroom, no dead paths, memory indexed, every declared blocker still real |
| `regenerate.sh` | takes a finished campaign through every stage above, in order, each to its own log |

`verify_results.py` checks the figures. `session_check.py` checks everything
around them, and exists because the state that is narrated rather than measured
is the state that drifts: three documents here carried a disk figure and all
three were wrong. Run it before handing off or compacting.

    python3 analysis/session_check.py            # full, includes verify_results.py
    python3 analysis/session_check.py --quick    # skip the slow figure check

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
