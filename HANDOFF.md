# Handoff

Two pieces of work are open and neither of them belongs to the person who built
the pipeline. This document is what each pair needs to start: why the work
matters, what "done" looks like, what you are given, and the one rule that
decides whether your result can be believed.

Read [`USING_THE_DATA.md`](USING_THE_DATA.md) first. Everything below assumes it.

---

## Before either of you starts

You both get the same thing, and you both have to use it unchanged:

- release 1.1.0 of the bundle, 1.7 GB, five scenarios
- `release_splits.csv`, the frozen partition inside it
- `analysis/check_release.py`, the acceptance test

### Getting it

The full bundle is 1.7 GB, which is more than most ways of sending a file will
take. Two options.

**The whole thing**, 1.7 GB, over OneDrive or a shared drive. Preferred, because
it is the only form the acceptance test covers completely.

**One scenario**, if that is impractical. `highway_sparse` plus the nine small
files beside it is **377 MB**, `cv2x-ids-1.1.0-highway_sparse.zip`, and is enough for everything in section A, because
it is the reference scenario where every published figure is measured. Use the
packaged zip, or copy the `shards/highway_sparse/` directory and every file at
the top level of the bundle. One of the nine, `.zenodo.json`, is hidden and a
file browser will not show it, so copy the directory from a terminal rather than
selecting files. Then run the acceptance test in subset mode:

    python3 analysis/check_release.py path/to/bundle --subset

Subset mode accepts an absent scenario and still fails on a file that is present
and does not match its checksum, because that is corruption rather than a partial
copy. It reports which scenarios are absent so nobody reads the result as
covering the whole release.

### Then verify it

    python3 analysis/check_release.py path/to/release

**Run the acceptance test once and keep its output.** Send that output with any
number you report. Two results computed on the same frozen partition can be put
beside each other; two results on partitions each of you made up cannot, and there
is no way to fix that after the fact.

The partition is keyed on the **physical transmitter**, not the claimed identity.
That distinction is not pedantry. A sybil attacker emits several claimed
identities from one car, so grouping on the claimed one splits a single vehicle
across train and test.

---

## A. The fifth learner family

**Verna Nakhla and Ken Navarro.**

### Why this is not a side project

The central claim of this project is that **a single receiver cannot detect a
constant position lie at any magnitude the dataset contains.** That claim is
currently supported two ways. The geometry says the information is not there: one
receiver at a fixed geometry gives one equation per window for four unknowns.
And four learner families were run over identical rows and folds and none of them
found it.

The claim is written down in its honest form, which is that *no learner tried on
these features at this observation unit crosses the floor*, together with the
sentence "four families is not every learner."

**A transformer is the fifth family.** If it also fails, the claim gets
meaningfully stronger, because a model with a completely different inductive bias
looked and found nothing either. If it succeeds, that is a bigger result than
anything else in the project, and it would need explaining against the geometry.
Either outcome is worth having. There is no outcome here that wastes your time.

### Start from the script, not from this description

    python3 analysis/baseline_starter.py path/to/release --protocol cv

That runs the published protocol exactly: all 50 features, grouped folds on the
physical transmitter, all eleven classes, MCC and macro F1 and per class. It
prints your three position-class scores beside the best any of the four existing
families reached, and it exits non-zero if your score is high enough to be
leakage.

**Replace `build_model()` and change nothing else in the file.** Anything with
`fit` and `predict` works. Doing it that way means the protocol cannot drift,
and your row is comparable by construction rather than by careful reading.

Run it once unmodified first. On the 1.1.0 reference package as shipped it
reproduces the benchmark's fused row exactly: **macro F1 0.5068 +/- 0.0019, MCC
0.6438**, and 0.145 on the constant offset class. If your unmodified run does not
print those, something differs in your setup, and it is worth finding before you
change the model. Release 1.0.0 printed 0.5145 here; 1.1.0 attributes received
power per claimed identity, which makes the Sybil class honestly harder, and
that is most of the difference.

### What that pins, and why each part matters

To be the fifth family your run has to be comparable to the other four:

| | |
|---|---|
| features | all 50, every `app_` and `phy_` column |
| observation unit | one receiver, one claimed station, one 1000 ms window |
| folds | grouped by `label_txNodeId`, which the frozen partition already does |
| target | `label_attackId`, all eleven classes |
| report | MCC primary, macro F1 beside it, per-class F1 underneath |

**The observation unit is the part people get wrong.** A transformer reading a
*sequence of raw messages* rather than a window of aggregate features is a
different experiment. It might well beat the floor, and if it does that would
**not** contradict the bound, because it changed what the detector is allowed to
see. That is interesting work and worth doing second. It just has to be labelled
as a different experiment before you have numbers, not after, or nobody can tell
what your result means.

Do the comparable run first. It is the one that slots into the existing table.

### What you are trying to beat

**The four family rows below were measured on release 1.0.0 and are being rerun
on 1.1.0; this table will be replaced when they land.** The random forest on
1.1.0 is macro F1 0.5068, MCC 0.6438, and the other three move with it. Compare
your transformer against the 1.1.0 rows, not these.

| learner | macro F1 | MCC |
|---|---|---|
| random forest | 0.5145 | 0.6635 |
| hist gradient boosting | 0.5015 | 0.6081 |
| MLP 128-64 | 0.5028 | 0.6397 |
| logistic regression | 0.4160 | 0.5889 |

And on the three position classes, which is where the claim actually lives, the
best any of the four reached, also on 1.0.0 until the rerun lands:

| class | best of four |
|---|---|
| position offset, 1 to 25 m, median 12 m | 0.010 |
| position offset, 47 to 83 m, median 71 m | 0.052 |
| position offset, 22 to 233 m, median 140 m | 0.167 |

**Those three numbers are the target.** The aggregate is almost beside the point.
Note that the four rows above come from grouped cross-validation on 250,000
windows, not from a single pass over the frozen split. Score the same way if you
want your row to sit in that table; `USING_THE_DATA.md` explains the difference
and why the acceptance test reports 0.5319 on 1.1.0 instead.
A transformer that moves the aggregate from 0.51 to 0.53 and leaves the position
classes at 0.01 has confirmed the bound. A transformer that moves the position
classes is the finding.

### The rule

**A 1-nearest-neighbour classifier scores 0.3533 on this corpus**, release 1.1.0. If your model
reports anything near 1.0, stop and find the leak. It will almost certainly be a
split that is not grouped by physical transmitter. The first version of this
project reported 1.0000 from three model families and the cause was that 96.39
percent of test rows appeared verbatim in training.

**A perfect score here is a bug report.** Treat it that way from day one and you
will save yourselves a fortnight.

### Done looks like

1. A transformer scored with `baseline_starter.py --protocol cv` at the pinned
   observation unit, which is the protocol the four rows above used. The frozen
   partition is for iterating; it reads high and does not sit in that table.
2. Its row added to the four above: MCC, macro F1, per-class F1.
3. Its three position-class scores stated explicitly against 0.010 / 0.052 / 0.167.
4. The `check_release.py` output alongside.
5. One paragraph on whether it confirms or breaks the bound, and why you think so.

### You are given

- `analysis/baseline_starter.py`, **the thing to start from.** The protocol is
  already correct in it.
- `analysis/model_independence.py`, the record of how the other four rows were
  produced. It is not a plug-in: it reads a merged corpus file the bundle does not
  ship and needs scikit-learn estimators. Use the starter for your row; it runs
  the same protocol on the bundle as shipped.
- `analysis/validate_dataset.py`, the ten integrity gates, if you want to check
  any subset you construct.
- `analysis/benchmark.py`, which is where the 0.5068 comes from. It now has a
  fourth arm, radio measurements alone, which scores exactly zero on the constant
  offset class.

---

## B. What window can the application tolerate

**Andrew Ng and Joshua Wong, with Likhith.**

### Why the old question was the wrong question

The plan asked whether inference can meet a 100 ms deadline on edge hardware, and
recorded 26.4 microseconds as a preliminary yes, roughly 3,789 times inside
budget.

Two things are wrong with that and the second one is worse.

**The quantities are not comparable.** The 100 ms in 3GPP TS 22.185 covers PC5
transport of a single message. It is not a budget for an application-layer
detection pipeline.

**A windowed detector cannot decide anything until its window is full.** The
pipeline that reported 26.4 microseconds used a 30 second window with a 15 second
step, so a decision arrived every fifteen seconds at best. Against a 100 ms
deadline that is 150 times over budget. The report claimed the deadline was met by
a factor of 3,789 while describing a pipeline two orders of magnitude slower than
it, and both numbers sat in the same document.

This is not a reason to be embarrassed. It is a reason the replacement question
is better.

### The question that replaces it

**What window length does the application tolerate, and what does shortening it
cost?**

That is a real engineering trade with real numbers on both sides, and it is yours.

Already measured, on release 1.1.0:

| | |
|---|---|
| single-window inference | 3.085 ms |
| window fill | 1000 ms |
| inference as a share of fill plus inference | **0.31 percent** |
| cooperative pooling block, the road bounded fit | 1.34 ms per unit |

Feature extraction is not timed, so the latency total is a lower bound and the
inference share an upper bound. The pooling block costs about 0.43 times the
inference, which is still 0.13 percent of a 1000 ms window.

| window | fused macro F1, mean +/- fold spread |
|---|---|
| 200 ms | 0.4105 +/- 0.0035 |
| 500 ms | 0.3978 +/- 0.0199 |
| 1000 ms | 0.4520 +/- 0.0057 |

Each point is its own corpus rebuilt at that window length from the reference
scenario's first three seeds, benchmarked on 150,000 windows under three grouped
folds, so the 1000 ms point is not the headline 0.5068, which uses all eight
seeds. **Shortening the window from 1000 to 200 ms costs 0.042 fused macro F1**,
about seven times the fold spread, so on this corpus it is a measured trade
rather than a direction. The 500 ms point sits below the 200 ms one, but its
spread is three to six times theirs; treat the curve as two well measured ends until
more seeds say otherwise.

### One constraint, so you do not lose a week to it

**You cannot extend the window sweep from the release bundle.** Every row in the
bundle is already windowed at 1000 ms. Changing the window length means
rebuilding the corpus from the raw simulator tables with
`build_corpus.py --window-ms`, and those tables are 36 GB, are not distributed,
and live only on the machine that generated them.

So the three points at 200, 500 and 1000 ms are the curve you have. If you want
more points on it, that is a request to Likhith rather than something you can
run, and each new window length costs a corpus rebuild across six seeds plus a
benchmark, so ask for the ones you actually need rather than a sweep.

What you *can* do from the bundle is everything on the hardware side, which is
the part that is yours: the export, the board, the measurement, and the argument
that follows from it.

### What the hardware work actually proves

Measure inference on the ARM board and show it **stays negligible against window
fill**. That is the honest answer, and it is a clean result rather than a
disappointing one: it says no amount of hardware acceleration changes the timing
of this class of detector, because the window dominates by more than two orders
of magnitude, and therefore the design lever is the window and not the silicon.

Do not present the board measurement as "we met the deadline." Present it as the
measurement that shows where the deadline actually lives.

### Done looks like

1. The model exported and running on the board.
2. Inference latency measured there, with its spread, not just a mean.
3. That number placed against 1000 ms window fill and stated as a percentage.
4. A recommendation: which window length, and what it costs, for a stated use.
5. The communication and compute cost comparison across aggregation methods,
   which has never been run against the current panel.

### You are given

- `analysis/measure_latency.py`, which counts window fill rather than the forward
  pass alone, and is where 3.085 ms comes from.
- `analysis/measure_pooling_cost.py`, the 1.34 ms figure.
- `analysis/benchmark.py`, for the window sweep.

### One thing that is not yours any more, and why

The plan also had you re-run feature selection on the regenerated dataset. **Do
not run it as the headline method**, and this is a finding rather than a
cancellation.

**Measured on release 1.1.0**, `campaign_gnss/logs/feature_selection.log`, 150,000
windows under five grouped folds. Ranking all 50 features by importance and
keeping the top 15 costs only 0.0050 macro F1, which reads as a free trade. But
of that top 15, chosen identically in all five folds, **fourteen are application
features and exactly one is a radio feature**, `phy_rsrp_count`, which is the
per identity message rate rather than a radio versus claim check. The radio
block earns its place by catching attacks the application layer misses entirely,
not by containing the single strongest signal, and its contribution is spread
across many individually weak features. Importance ranking keeps the best one and
discards the other 27.

So the routine procedure would quietly delete the cross-layer result the project
rests on while the headline metric barely moved. On the superseded August corpus
the one radio feature it kept was the Sybil voiceprint, whose strength was partly
the power pooling artefact that 1.1.0 removed; the conclusion survived the fix.
What is still worth doing, if you want it, is scoring the selected set per
class. The benchmark's radio-only arm scores zero on the constant offset class,
so the selected set is expected to lose that class too, but that has not been
run.

If a selection step is kept at all, report the block composition beside it, never
a count alone.

---

## Questions that will come up

**Do we need to run the simulator?** No. Neither of these needs ns-3.

**Can we use a different metric?** Report MCC and macro F1 both. Add anything else
you like on top.

**Our result contradicts the existing numbers.** Good, say so. Send the
`check_release.py` output and the exact split you used, and it gets checked
properly. Every number in this project is pinned to the log that produced it, and
several earlier conclusions were withdrawn when the evidence moved.

**How much does it matter if we miss the date?** Both of these strengthen the work
rather than hold it up. Nothing downstream is blocked on either.
