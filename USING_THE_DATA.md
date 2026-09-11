# Using the dataset

**Start here if you want to train something on this data.** You do not need ns-3,
you do not need to regenerate anything, and you do not need the two Python
interpreters that [`REPRODUCING.md`](REPRODUCING.md) talks about. That document is
for rebuilding the dataset from the simulator. This one is for using it.

---

## What you get

One directory, about 1.6 GB.

    release/
      shards/                  five scenarios, gzipped CSV, one file per seed
        highway_sparse/        the reference scenario
        highway_dense/         2 km, 240 vehicles, congestion control saturated
        magnitude_sweep/       attack magnitudes widened to sample the transition
        bursty_attackers/      attackers who misbehave in bursts, not continuously
        offset_receivers/      roadside units moved off the centreline
      release_splits.csv       the frozen train, validation and test partition
      schema.json              all 61 columns, typed and described
      sample.csv               5,000 rows, to look at before committing
      DATASET_CARD.md          what every class and column means
      CHECKSUMS.sha256         every file above
      CITATION.cff             how to cite it
      PROVENANCE.txt           the generator commit that built it

7,916,708 rows. Each row is **one receiver's view of one claimed station over one
one-second window**, carrying both what the messages said and what the radio
measured while receiving them.

## Check it before you use it

    python3 analysis/check_release.py path/to/release

This is the acceptance test. It verifies the checksums, loads the shards against
the schema, confirms the partition covers every row exactly once with no vehicle
on both sides of a split, and trains a small baseline on the frozen split. It
uses only files inside the bundle. **Run it once and keep the output**, then send
it along with any result you report, so anyone reading your numbers can see you
were working from an intact copy.

## Load it

    import pandas as pd, glob

    shards = glob.glob("release/shards/highway_sparse/*.csv.gz")
    df = pd.concat(pd.read_csv(f) for f in shards)

    splits = pd.read_csv("release/release_splits.csv")
    df = df.merge(splits[["key_seed", "key_claimedStationId", "split"]],
                  on=["key_seed", "key_claimedStationId"], how="left")

    train = df[df.split == "train"]
    test  = df[df.split == "test"]

Columns are prefixed by what they are:

| prefix | count | what it is |
|---|---|---|
| `app_` | 22 | application layer, computed from message contents |
| `phy_` | 28 | physical and MAC layer, measured by the receiver's radio |
| `key_` | 6 | identifiers. **Never a feature.** |
| `label_` | 5 | ground truth. **Never a feature.** |

The six keys are `key_rxNodeId`, `key_claimedStationId`, `key_window`,
`key_txRnti_mode`, `key_observer_role` and `key_seed`. The five labels are
`label_attackId`, `label_txNodeId`, `label_attack_purity`, `label_is_attack` and
`label_clean`.

Your feature matrix is every column starting `app_` or `phy_`, which is exactly
50 columns, and nothing else.
`label_attackId` is the target. If a `key_` or `label_` column reaches your
feature list, your scores are meaningless, which is not a warning so much as a
description of what happened to the first version of this project.

## The frozen partition, and why you must use it

`release_splits.csv` assigns every vehicle to train, validation or test **once,
across all five scenarios at the same time**. 1,170 physical transmitters split
770 / 259 / 258, with all eleven classes present in every partition and no
transmitter appearing in two.

Three reasons not to make your own split.

**A vehicle transmits many windows.** Split rows at random and the same vehicle
lands on both sides, so the model recognises the vehicle rather than the
misbehaviour. This is the defect that produced the first version's perfect
scores.

**A sybil attacker emits several claimed identities.** Group on the claimed
identity and one physical vehicle scatters across partitions, which reintroduces
the same leak through a different door. The partition is keyed on
`label_txNodeId`, the physical transmitter.

**The scenarios share vehicles.** They were generated from the same seeds, so
`magnitude_sweep` and `highway_sparse` contain some of the same physical cars,
agreeing to four decimal places. A per-scenario split would leak across
scenarios. The global partition is what makes training on one scenario and
scoring on another safe.

If you split it yourself, your number cannot be compared with anybody else's, and
it is probably wrong in the optimistic direction.

### Which scenario to score on

**Score on `highway_sparse`.** It is the reference, and every published figure in
this project is measured on it.

`highway_dense` and `magnitude_sweep` are also benchmark scenarios and can carry
a headline number. The other two cannot, and the reason is worth knowing before
you waste a day on a confusing result:

| scenario | usable for a headline score | why not |
|---|---|---|
| `highway_sparse` | yes | |
| `highway_dense` | yes | |
| `magnitude_sweep` | yes | |
| `bursty_attackers` | **no** | class 1 has no transmitter in test |
| `offset_receivers` | **no** | class 1 has none in test, class 4 none in validation |

Under the global partition those two have empty class and split combinations, so
a macro F1 computed on them averages in a class that could not be scored. They
support auxiliary evaluation, such as asking whether a detector trained elsewhere
survives a bursty attacker, and they are genuinely useful for that. They just
cannot produce a number you put beside 0.5145.

## What to report

| | |
|---|---|
| **Primary metric** | Matthews correlation coefficient, over all eleven classes |
| **Report beside it** | macro F1, over all eleven classes |
| **Also give** | per-class F1, because the aggregate hides where the work is |
| **Splits** | grouped by `label_txNodeId`, which the frozen partition already does |
| **False positives** | at true prevalence, not on a balanced set |

MCC was chosen as primary before any of these numbers existed, because it uses
all four cells of the confusion matrix and stays meaningful when one class holds
most of the data. Report both aggregates. They sometimes disagree, and a
disagreement is information rather than an inconvenience.

## What to beat

Measured on the reference scenario, 250,000 windows, three folds grouped by
transmitting station.

| block | features | macro F1 | MCC |
|---|---|---|---|
| application only | 22 | 0.4878 | 0.6222 |
| radio only | 28 | 0.3554 | 0.5275 |
| **both** | **50** | **0.5145** | **0.6635** |

Across the ten classes that have a physical signature rather than all eleven,
fused macro F1 is 0.5659. The eleventh class, sensing manipulation, scores zero in
every block on every corpus, because resource grants in this simulator are data
driven and an attacker cannot hoard the channel, so it has no signature to find.

Four learner families have been run over identical rows and folds: a random
forest, gradient boosting, an MLP and logistic regression. The spread between the
top three is about 0.013 macro F1, so nothing here rests on a lucky model choice.

## The rule that matters most

**A 1-nearest-neighbour classifier scores 0.3466 on this corpus.**

That number is the evidence the task is not being won by memorisation. It is also
your alarm. If your model reports a macro F1 near 1.0, you have not solved the
task; you have reintroduced leakage, and the most likely cause is a split that is
not grouped by physical transmitter. The first version of this project scored
1.0000 with three separate model families, and the reason was that 96.39 percent
of its test rows appeared verbatim in training.

Treat a perfect score as a bug report. It is the single most useful thing this
project learned.

## Things that will surprise you

**The scores look low.** They are honest. Benign vehicles carry a realistic
positioning error, median 4.00 m, so a claimed position is checked against a
benign class that actually varies. Remove that and any displacement becomes
separable in principle, which makes position falsification far easier to detect
than it could ever be on a road.

**Position attacks are nearly undetectable from one receiver.** On the three
constant-offset classes the best score any of the four learner families reached
is 0.010, 0.052 and 0.167. This is not a bug and it is not a weak model. One
receiver at a fixed geometry supplies one equation per window for four unknowns,
two of position and two of propagation, so the information is not there. Pooling
across receivers is what recovers it, down to a floor at 47.2 m of displacement.

**Some classes are easy and some are impossible.** Denial of service and random
position offset sit near 0.98. Replay sits near 0.12. The aggregate is an average
over a very uneven problem, which is why per-class numbers are asked for above.

## If you need something that is not here

The raw simulator tables are not in the bundle and not in this repository. They
are regenerated from source, and [`REPRODUCING.md`](REPRODUCING.md) covers how.
[`analysis/README.md`](analysis/README.md) documents every script in the
pipeline. [`docs/DATASET_CARD.md`](docs/DATASET_CARD.md) describes every class,
every column, and the limitations, and it is generated from the corpus rather
than written by hand, so its counts cannot drift from the data.
