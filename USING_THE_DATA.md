# Using the dataset

**Start here if you want to train something on this data.** You do not need ns-3,
you do not need to regenerate anything, and you do not need the two Python
interpreters that [`REPRODUCING.md`](REPRODUCING.md) talks about. That document is
for rebuilding the dataset from the simulator. This one is for using it.

---

## How to get it, in three steps

**1. Clone the repository.** It is small, about 30 MB, and holds the scripts but
not the data.

    git clone https://github.com/Likhith-G/capstone-cv2x-ids.git
    cd capstone-cv2x-ids

**2. Ask Likhith for the dataset.** It is **not in the repository**, because it is
1.7 GB and GitHub is the wrong place for it. It arrives as a directory called
`release/`, over a shared drive. Put it wherever you like and pass its path to the
scripts below.

**3. Install what the scripts need**, if you do not already have it.

    pip3 install pandas numpy scikit-learn

That is all. **You do not need ns-3, and you do not need to reproduce anything.**
If you are wondering whether you should be following
[`REPRODUCING.md`](REPRODUCING.md), the answer is no. That document is for
rebuilding the dataset from the simulator, which takes hours across two different
Python versions and produces the same data you were handed.

Then, from the repository directory:

    python3 analysis/check_release.py /path/to/release      # confirm it arrived intact
    python3 analysis/baseline_starter.py /path/to/release   # train the baseline

If you were sent the single-scenario package, the 377 MB one holding only
`highway_sparse`, add `--subset` to the first command. Without it the check looks
for the four scenarios you were not sent and reports the bundle as incomplete.

---

## What you get

One directory, about 1.7 GB. This describes release 1.1.0.

    release/
      shards/                  five scenarios, gzipped CSV, one file per seed
        highway_sparse/        the reference scenario
        highway_dense/         2 km, 240 vehicles, congestion control saturated
        magnitude_sweep/       attack magnitudes widened to sample the transition
        bursty_attackers/      attackers who misbehave in bursts, not continuously
        offset_receivers/      roadside units moved off the centreline
      release_splits.csv       the frozen train, validation and test partition
      schema.json              every column, typed and described
      SCENARIOS.json           row counts and parameters of the five scenarios
      sample.csv               5,000 rows, to look at before committing
      DATASET_CARD.md          what every class and column means
      CHECKSUMS.sha256         every file here
      CITATION.cff             how to cite it
      PROVENANCE.txt           the generator commit that built it
      .zenodo.json             archive metadata; hidden, so copy the whole
                               directory rather than the files you can see

7,916,708 rows. Each row is **one receiver's view of one claimed station over one
one-second window**, carrying both what the messages said and what the radio
measured while receiving them.

## Check it before you use it

    python3 analysis/check_release.py path/to/release

Add `--subset` for the single-scenario package. This is the acceptance test. It
verifies the checksums, loads the shards against
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

**Or skip all of this and start from the script**, which does the load, the
partition and the protocol correctly and prints a baseline:

    python3 analysis/baseline_starter.py path/to/release

Replace `build_model()` in it with whatever you are testing and change nothing
else. The rest of this document explains what that script is doing and why.

Columns are prefixed by what they are:

| prefix | count | what it is |
|---|---|---|
| `app_` | 22 | application layer, computed from message contents |
| `phy_` | 28 | radio measurements, and residuals that set a measurement against what the claimed position predicts |
| `key_` | 5 | identifiers. **Never a feature.** |
| `label_` | 5 | ground truth. **Never a feature.** |

`label_clean` marks a window that passes the label purity threshold. It is set on
every row here because no window in this corpus is impure: every claimed identity
belongs to one transmitter and a transmitter's behaviour is fixed. The column is
kept for corpora built with an attack that sends under another station's
identity, so filter on it if you build your own.

Thirteen of the `phy_` columns take the claimed position or the application loss
rate as an input (`phy_rsrp_resid_*`, `phy_track_*`, `phy_closest_*`,
`phy_rsrp_vs_claimed`, `phy_rsrp_voiceprint_min`, `phy_loss_vs_rsrp`). They are
the physical layer check the literature uses, power against the claim, so the
`phy_` block is not a radio-only ablation. Drop those thirteen for one.

The five keys are `key_rxNodeId`, `key_claimedStationId`, `key_window`,
`key_observer_role` and `key_seed`. Release 1.0.0 had a sixth, `key_txRnti_mode`,
which named the physical radio; 1.1.0 drops it. The five labels are
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
703 / 233 / 234, which is 770 / 259 / 258 claimed identities because a sybil
vehicle claims several, with all eleven classes present in every partition and no
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
| `magnitude_sweep` | yes, for the aggregate | its position classes are drawn wider on purpose, so do not read or compare them per class; bin by realised displacement |
| `bursty_attackers` | **no** | class 1 has no transmitter in test |
| `offset_receivers` | **no** | class 1 has none in test, class 4 none in validation |

Under the global partition those two have empty class and split combinations, so
a macro F1 computed on them averages in a class that could not be scored. They
support auxiliary evaluation, such as asking whether a detector trained elsewhere
survives a bursty attacker, and they are genuinely useful for that. They just
cannot produce a number you put beside 0.5068.

## What to report

| | |
|---|---|
| **Primary metric** | Matthews correlation coefficient, over all eleven classes |
| **Report beside it** | macro F1, over all eleven classes |
| **Also give** | per-class F1, because the aggregate hides where the work is |
| **Splits** | grouped by `label_txNodeId`, which the frozen partition already does |
| **False positives** | on unbalanced data, and precision at a stated deployment prevalence; the corpus's own attack share of about a third is far above a road's |

MCC was chosen as primary before any of these numbers existed, because it uses
all four cells of the confusion matrix and stays meaningful when one class holds
most of the data. Report both aggregates. They sometimes disagree, and a
disagreement is information rather than an inconvenience.

## What to beat

Measured on the reference scenario of release 1.1.0, 250,000 windows, three folds
grouped by transmitting station.

| block | features | macro F1 | MCC |
|---|---|---|---|
| application only | 22 | 0.4880 | 0.6236 |
| `phy_` block | 28 | 0.3363 | 0.4745 |
| radio measurements alone | 15 | 0.2495 | 0.3891 |
| **both** | **50** | **0.5068** | **0.6438** |

The radio measurements alone, the `phy_` block without the thirteen columns that
use the claim, score exactly zero on the constant offset class; the `phy_`
block's 0.135 there comes entirely from setting power against the claim. Across
the ten classes that have a physical signature rather than all eleven, fused
macro F1 is 0.5575. The eleventh class, sensing manipulation, scores zero in
every block on every corpus, because resource grants in this simulator are data
driven and an attacker cannot hoard the channel, so it has no signature to find.

Four learner families have been run over identical rows and folds: a random
forest, gradient boosting, an MLP and logistic regression. On release 1.0.0 the
spread between the top three was about 0.013 macro F1, so nothing rested on a
lucky model choice; the comparison is being rerun on 1.1.0.

**You will see a slightly different number and that is expected.** The acceptance
test trains a small forest on the frozen split using only what is in the bundle,
and reaches **macro F1 0.5319, MCC 0.6746** on the reference scenario. The
published 0.5068 comes from a stricter protocol: 250,000 windows under three
grouped cross-validation folds rather than a single train-and-score on the frozen
partition. Both are correct measurements of different protocols, and the gap
between them is the ordinary optimism of scoring once rather than averaging folds.

If you want to compare directly against 0.5068, use grouped cross-validation. If
you want a fast number to iterate on, the frozen split is fine, and 0.5319 is what
a baseline gets there.

## The rule that matters most

**A 1-nearest-neighbour classifier scores 0.3533 on this corpus.**

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
positioning error, median 4.02 m, so a claimed position is checked against a
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
position offset sit between 0.91 and 0.99. Replay sits near 0.11. The aggregate is an average
over a very uneven problem, which is why per-class numbers are asked for above.

**Received power is attributed per claimed identity.** The simulator gives each
radio one fixed link-layer identifier where a real station rotates it with its
pseudonym, so release 1.0.0 pooled power per radio and every identity of a Sybil
carried identical `phy_rsrp_*` values, which made the class easier than on a
road. Release 1.1.0 gives each decoded control channel to the claimed identity
whose message is nearest in time, as a receiver seeing each pseudonym as its own
source would, and Sybil falls from 0.959 fused to 0.895. The split is inferred
from timing rather than measured; limitation 9 in the dataset card has the detail.

**The class label is not a magnitude.** The constant offset class is drawn from a
box and overlaps the other two position classes, and the small offset class
realises lies of 1 to 25 m. If magnitude matters to your argument, bin by
realised displacement.

## If you need something that is not here

The raw simulator tables are not in the bundle and not in this repository. They
are regenerated from source, and [`REPRODUCING.md`](REPRODUCING.md) covers how.
[`analysis/README.md`](analysis/README.md) documents every script in the
pipeline. [`docs/DATASET_CARD.md`](docs/DATASET_CARD.md) describes every class,
every column, and the limitations, and it is generated from the corpus rather
than written by hand, so its counts cannot drift from the data.
