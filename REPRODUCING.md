# Reproducing

Everything here was measured on the machine that produced the results rather than
estimated, so the runtimes are what you should actually expect on comparable
hardware, not a best case.

## Two interpreters, and they must not be mixed

This is the single most common way to lose an hour here.

| | version | used for |
|---|---|---|
| ns-3 build | Python **3.12** | building the simulator. The waf wrapper does not work under 3.14 |
| analysis | Python **3.9** | everything in `analysis/` |

**Use an absolute interpreter path in any script you queue or background.** A
background shell on macOS commonly resolves a bare `python3` to a Homebrew build
that has none of the analysis packages, while an interactive shell resolves it to
the system one. A three stage job here died at every stage on exactly that, and
the wrapper still exited zero because each stage's failure went to its own log.

## Versions this was run with

Analysis, Python 3.9.6:

    numpy       2.0.2
    pandas      2.3.3
    scikit-learn 1.6.1
    scipy       1.13.1
    matplotlib  3.9.4
    torch       2.8.0

Simulation, Python 3.12.14:

    ns-3        ns-3-dev-v2x-v1.1   (CTTC fork, not vanilla ns-3.42)
    5G-LENA nr  v2x-1.1

`contrib/nr` additionally needs the three file additive patch at
`docs/patches/nr-sl-rsrp-trace.patch`. It exposes the per SCI sidelink RSRP that
5G-LENA computes internally and never surfaces. **Without it the strongest
feature in the dataset does not exist.** Make no other change to `nr`.

## Hardware the timings below were measured on

Apple M2, 8 cores, **8 GB RAM**, macOS 27.

The memory figure matters more than the core count. Two concurrent heavy jobs
made this machine swap 5 GB and turned a 40 second simulation into 2.5 hours.
**Run one heavy job at a time.** Disk matters too: keep at least 10 GB free, since
a single 60 second seed produces about 750 MB of raw tables and a 101 MB corpus.

## One command

    ./analysis/regenerate.sh <run-dir> <max-time-ms> seed1 seed2 ... seed8

Each stage writes its own log, so a single stage can be repeated after a fix
without redoing the work before it.

Run `analysis/check_campaign.py` on the first seed **before** letting the rest
generate. It reads only the small transmit table, costs seconds, and catches the
misconfigurations that are expensive to find after eight seeds: that the benign
positioning error is present, and that the position attack magnitudes do not
overlap.

## What each stage costs

Measured on the eight seed, 6 km, 90 vehicle configuration, 1,641,002 windows.

| stage | wall clock |
|---|---|
| corpus build and integrity gates | tens of minutes |
| corpus-wide pooling, full protocol (10 folds, 300 trees) | about 2.5 hours |
| corpus-wide pooling, table only (2 folds, 30 trees) | about 5 minutes |
| region pooling, full protocol | about 45 minutes |
| detection floor, `offset_floor.py` with 2,000 bootstrap fits | about 8 minutes |
| geometry bound, `geometry_bound.py` | under 1 minute |
| estimator study, 5,000 triples over 7 arms | about 9 minutes free, 2 minutes road constrained |
| correction transfer, two corpora | about 6 minutes |
| operating point, `persistence_filter.py` | seconds |

The gap between the two pooling rows is worth knowing: the expensive part is the
classification protocol, not building the table. If you only need the pooled
table, drop the folds and the trees and it is a twentieth of the cost.

## Checking the result

    python3 analysis/verify_results.py     # every reported figure against its log
    python3 analysis/session_check.py      # the bookkeeping around those figures

The first pins every number in the results document to the exact line of the log
that produced it and must report no failures. The second checks the state that
tends to go stale rather than the numbers: whether anything is still running, the
working tree, disk headroom, whether any path named in a document still exists.

Traces are not held in this repository. They are regenerated from source.
