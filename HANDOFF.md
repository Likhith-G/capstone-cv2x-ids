# Handoff

Two pieces of work are open and neither of them belongs to the person who built
the pipeline. This document is what each pair needs to start: why the work
matters, what "done" looks like, what you are given, and the one rule that
decides whether your result can be believed.

Read [`USING_THE_DATA.md`](USING_THE_DATA.md) first. Everything below assumes it.

---

## Before either of you starts

You both get the same thing, and you both have to use it unchanged:

- the release bundle, 1.6 GB, five scenarios
- `release_splits.csv`, the frozen partition inside it
- `analysis/check_release.py`, the acceptance test

### Getting it

The full bundle is 1.6 GB, which is more than most ways of sending a file will
take. Two options.

**The whole thing**, 1.6 GB, over OneDrive or a shared drive. Preferred, because
it is the only form the acceptance test covers completely.

**One scenario**, if that is impractical. `highway_sparse` plus the eight small
files beside it is **358 MB** and is enough for everything in section A, because
it is the reference scenario where every published figure is measured. Copy the
`shards/highway_sparse/` directory and all eight files at the top level of the
bundle, then run the acceptance test in subset mode:

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

### Pin this before you write any code

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

| learner | macro F1 | MCC |
|---|---|---|
| random forest | 0.5145 | 0.6635 |
| hist gradient boosting | 0.5015 | 0.6081 |
| MLP 128-64 | 0.5028 | 0.6397 |
| logistic regression | 0.4160 | 0.5889 |

And on the three position classes, which is where the claim actually lives, the
best any of the four reached:

| class | best of four |
|---|---|
| position offset, 20 to 25 m | 0.010 |
| position offset, 47 to 60 m | 0.052 |
| position offset, 71 to 233 m | 0.167 |

**Those three numbers are the target.** The aggregate is almost beside the point.
Note that the four rows above come from grouped cross-validation on 250,000
windows, not from a single pass over the frozen split. Score the same way if you
want your row to sit in that table; `USING_THE_DATA.md` explains the difference
and why the acceptance test reports 0.5396 instead.
A transformer that moves the aggregate from 0.51 to 0.53 and leaves the position
classes at 0.01 has confirmed the bound. A transformer that moves the position
classes is the finding.

### The rule

**A 1-nearest-neighbour classifier scores 0.3466 on this corpus.** If your model
reports anything near 1.0, stop and find the leak. It will almost certainly be a
split that is not grouped by physical transmitter. The first version of this
project reported 1.0000 from three model families and the cause was that 96.39
percent of test rows appeared verbatim in training.

**A perfect score here is a bug report.** Treat it that way from day one and you
will save yourselves a fortnight.

### Done looks like

1. A transformer trained on the frozen partition with the pinned observation unit.
2. Its row added to the four above: MCC, macro F1, per-class F1.
3. Its three position-class scores stated explicitly against 0.010 / 0.052 / 0.167.
4. The `check_release.py` output alongside.
5. One paragraph on whether it confirms or breaks the bound, and why you think so.

### You are given

- `analysis/model_independence.py`, the harness the other four families ran in.
  Your row plugs into it.
- `analysis/validate_dataset.py`, the ten integrity gates, if you want to check
  any subset you construct.
- `analysis/benchmark.py`, which is where the 0.5145 comes from.

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

Already measured:

| | |
|---|---|
| single-window inference | 3.390 ms |
| window fill | 1000 ms |
| inference as a share of latency | **0.34 percent** |
| cooperative pooling block | 0.4054 ms |

| window | fused macro F1 |
|---|---|
| 200 ms | 0.6166 |
| 500 ms | 0.6468 |
| 1000 ms | 0.6514 |

Shortening the window from 1000 ms to 200 ms costs **0.035 macro F1 for a
fivefold latency reduction.** The radio block loses most of it, because radio
features are statistics and statistics need samples.

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
  pass alone, and is where 3.390 ms comes from.
- `analysis/measure_pooling_cost.py`, the 0.4054 ms figure.
- `analysis/benchmark.py`, for the window sweep.

### One thing that is not yours any more, and why

The plan also had you re-run feature selection on the regenerated dataset. **Do
not run it as the headline method**, and this is a finding rather than a
cancellation.

Ranking all 50 features by importance and keeping the top 15 costs only 0.0315
macro F1, which reads as a sensible trade. But of that top 15, **fourteen are
application features and exactly one is a radio feature.** The radio block earns
its place by catching attacks the application layer misses entirely, not by
containing the single strongest signal, and its contribution is spread across many
individually weak features. Importance ranking keeps the best one and discards the
other 27.

So the routine procedure would have quietly deleted the cross-layer result the
whole project rests on, while the headline metric barely moved. That is worth
reporting as a result of your workstream, because it is one: **on a dataset whose
value is distributed across a block of weak features, top-k selection destroys the
finding and the aggregate does not tell you.**

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
