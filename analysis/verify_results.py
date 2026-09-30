#!/usr/bin/env python3
"""
Check that the numbers in RESULTS.md still match the logs that produced them.

The standing rule for this project is that every number is verified against its
generating file before it goes into a document, and that rule is what caught
the v1 defects. This automates the part of it that can be automated: each entry
below pins a string in RESULTS.md to the exact line in the run log it came
from, so a figure cannot be edited on one side alone, and a rerun that changes
a result cannot leave the document quietly stale.

Add an entry whenever a number goes into RESULTS.md. If a check fails, the
document and the log disagree and one of them is wrong.

This is a local working tool. It reads `docs/RESULTS.md` and the run logs under
`~/ns3-v2x/runs/`, neither of which is in the repository, so a fresh clone will
report every check as a missing file. That is expected.
"""
import re
import pathlib
import sys

DOC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "RESULTS.md"
RUNS = pathlib.Path.home() / "ns3-v2x" / "runs"

# label, exact string in RESULTS.md, log stem, exact string in that log
CHECKS = [
    # campaign_v3 is the corpus. Its logs live under campaign_v3/logs/.
    # 3g, the floor under four learner families rather than one
    # The magnitude ladder over all eight seeds. It replaced three stations a
    # class on seed 1, which had been carried forward as the scenario's ranges.
    ("ladder small offset",
     "| 11 pos_small_offset | uniform 4 to 25 m | **1.3 to 24.7 m** | 12.3 m | 2 of 22 |",
     "campaign_gnss/logs/magnitude_ladder",
     " 11 pos_small_offset       22     1.3     8.6    12.3    20.1    24.7  2"),
    ("ladder medium offset",
     "| 13 pos_medium_offset | uniform 50 to 80 m | **47.3 to 83.2 m** | 70.7 m | 0 of 20 |",
     "campaign_gnss/logs/magnitude_ladder",
     " 13 pos_medium_offset       20    47.3    60.1    70.7    76.4    83.2  0"),
    ("ladder constant offset",
     "| 1 pos_const_offset | box, 250 m by 30 m | **21.5 to 232.7 m** | 139.9 m | 0 of 18 |",
     "campaign_gnss/logs/magnitude_ladder",
     "  1 pos_const_offset       18    21.5    70.0   139.9   192.0   232.7  0"),
    ("ladder benign error",
     "Benign error over the same eight seeds: median 4.02 m, 95th percentile 6.12 m.",
     "campaign_gnss/logs/magnitude_ladder", "benign error: median 4.02 m, p95 6.12 m"),
    # The acceptance test on the bundle as sent. The public documents quote it,
    # and it had no log until 26 Sep.
    # 3h, the bound from geometry with no classifier involved
    # 3h5: the predicted rotation to 86 degrees, tested against the corrected
    # estimator and refuted. The off-axis column is the claim; the caught-at-5%
    # column beside it is what the correction is worth against this adversary.
    # 3h8: the replication. The two displacements that carry the claim, on the
    # two independent seed subsets, plus the 200 m cell that never moves.
    # 3h7: the correction swept in five steps, with the bound swept alongside
    # it. The controls are the two endpoints, which must reproduce the published
    # single slope and corrected columns, and the claim is the monotone gap.
    # 3h6: the attacker constraint isolated. Same campaign, same triples, same
    # estimator constraint; only --br-lateral differs. The angle column is the
    # finding and the caught-at-5% column is what the constraint is worth.
    # 3i, against the field's standard checks
    # 5d, does federating across densities recover the shift. Every pin here is
    # against the regenerated logs; the four federated_drift_* logs are
    # superseded and 5d4 says why. The pooled arms were unpinned before, which
    # is part of how a wrong number survived in 5d3, so they are pinned now.
    ("federated drift in-distribution",
     "| **trained on the target density** | 503 | 209,916 | **0.2998 +/- 0.0048** | **0.4282** |",
     "drift/logs/drift_dense_fixedsample",
     "in-dist       503 clients  209,916 rows   macro F1 0.2998 +/- 0.0048"),
    ("federated drift mixed is worse",
     "| federated across both | 1223 | 209,320 | 0.1268 +/- 0.0354 | 0.1497 |",
     "drift/logs/drift_dense_fixedsample",
     "mixed        1223 clients  209,320 rows   macro F1 0.1268 +/- 0.0354"),
    ("federated drift double data",
     "| federated across both, twice the rows | 1223 | 419,234 | 0.2285 +/- 0.0188 | 0.3438 |",
     "drift/logs/drift_dense_fixedsample",
     "mixed-2x     1223 clients  419,234 rows   macro F1 0.2285 +/- 0.0188"),
    ("federated drift transfer arm",
     "| trained on the other density | 720 | 209,555 | 0.1927 +/- 0.0314 | 0.2904 |",
     "drift/logs/drift_dense_fixedsample",
     "transfer      720 clients  209,555 rows   macro F1 0.1927 +/- 0.0314"),
    # 5d3, the pooled ceiling arms in both directions
    ("pooled mixed arm, dense target",
     "| the same mixed rows pooled into one client | 1 | 209,320 | 0.4971 +/- 0.0042 | 0.5755 |",
     "drift/logs/drift_dense_fixedsample",
     "centralised     1 clients  209,320 rows   macro F1 0.4971 +/- 0.0042"),
    ("pooled target arm, dense target",
     "| the target rows pooled into one client | 1 | 209,916 | 0.5169 +/- 0.0055 | 0.5855 |",
     "drift/logs/drift_dense_fixedsample",
     "centralised-in-dist    1 clients  209,916 rows   macro F1 0.5169 +/- 0.0055"),
    ("pooled mixed arm, sparse target",
     "| the same mixed rows pooled into one client | 1 | 208,626 | 0.5210 +/- 0.0022 | 0.6667 |",
     "drift/logs/drift_sparse_fixedsample",
     "centralised     1 clients  208,626 rows   macro F1 0.5210 +/- 0.0022"),
    ("pooled arms are stable at the gentler rate",
     "0.5181 +/- 0.0040 and 0.5284 +/- 0.0025 across ten seeds",
     "drift/logs/drift_sparse_fixedsample_lr01",
     "centralised     1 clients  208,626 rows   macro F1 0.5181 +/- 0.0040"),
    # 5d3, the exposure matched control. The ratios are derived rather than
    # printed by the campaign, so they are pinned against drift_exposure.py's
    # own output, which recomputes them from the arm lines.
    ("exposure matched, smallest ratio",
     "| sparse into dense, 0.05 | -0.1730, 15.3 sigma | -0.0198, 9.0 sigma | **-0.0265**, 11.8 sigma | **6.53 +/- 0.70** |",
     "drift/logs/drift_exposure", "ratio  6.53 +/- 0.70"),
    ("exposure matched, largest ratio",
     "| dense into sparse, 0.05 | -0.1705, 11.9 sigma | +0.0021, 0.2 sigma, collapsed seed | **-0.0056**, 4.7 sigma | **30.45 +/- 6.93** |",
     "drift/logs/drift_exposure", "ratio 30.45 +/- 6.93"),
    ("exposure matched cost, dense target",
     "**-0.0265**, 11.8 sigma",
     "drift/logs/drift_exposure",
     "pooled, EXPOSURE MATCHED  -0.0265  se 0.0022   11.8 sigma"),
    ("exposure matched cost, sparse target",
     "**-0.0056**, 4.7 sigma",
     "drift/logs/drift_exposure",
     "pooled, EXPOSURE MATCHED  -0.0056  se 0.0012    4.7 sigma"),
    ("matched arm is stable where the unmatched one was not",
     "spreads between 0.0021 and 0.0054",
     "drift/logs/drift_sparse_exposure",
     "centralised-matched    1 clients  208,626 rows   macro F1 0.5180 +/- 0.0021"),
    ("the collapsed seed is a weight blowup",
     "weight norm is **123.5 against about 52 for the nine stable seeds**",
     "drift/logs/drift_sparse_fixedsample",
     "seed 9  F1 0.4098  MCC +0.5896  predicts  6 of 11 classes   |w|   123.49"),
    # 3b2, the floor located from a campaign built to sample the transition
    # 3c2, does the cooperative architecture survive the shift
    ("pooled drift into light traffic",
     "| **into light traffic** | **pooled fused** | **0.4193 +/- 0.0204** | **0.6274 +/- 0.0121** | **-0.2081** |",
     "drift/logs/density_pooled",
     "campaign_gnss    pooled fused    0.4193 +/- 0.0204    0.6274 +/- 0.0121  -0.2081"),
    ("pooled drift into congestion",
     "| **into congestion** | **pooled fused** | **0.3063 +/- 0.0104** | **0.6711 +/- 0.0174** | **-0.3648** |",
     "drift/logs/density_pooled",
     "campaign_dense_gnss pooled fused    0.3063 +/- 0.0104    0.6711 +/- 0.0174  -0.3648"),
    # 3f2, the cross dataset test on the current benchmark
    # 3h2, the placement prediction tested against a real campaign
    ("federated drift reverse direction",
     "| **trained on the target density** | 503 | 209,228 | **0.3265 +/- 0.0177** | **0.4396** |",
     "drift/logs/drift_sparse_fixedsample",
     "in-dist       503 clients  209,228 rows   macro F1 0.3265 +/- 0.0177"),
    ("federated drift reverse mixed",
     "| federated across both | 1223 | 208,626 | 0.1560 +/- 0.0417 | 0.1906 |",
     "drift/logs/drift_sparse_fixedsample",
     "mixed        1223 clients  208,626 rows   macro F1 0.1560 +/- 0.0417"),
    # 3h3, the estimator study
    ("corpus size", "| windows | 1,641,002 |",
     "campaign_gnss/logs/merge", "merged: 1641002 windows, 720 stations, 8 seeds"),
    # The epsilon column is recomputed rather than read from the sweep, because
    # the sweep's accountant charged the wrong sensitivity. Pin both columns.
    # The p-values in section 5 are recomputed exactly from the logged per-seed
    # scores, because the logged ones came from a normal approximation.
    ("bursty attacker destroys the operating point",
     "| **5/7** | **7** | **139** | 0.540 | 0.503 |",
     "campaign_sporadic/logs/persistence",
     "   5/7                   106                  139            0.503"),
    ("bursty attacker collapses per window classification",
     "| **fused** | **0.5145** | **0.3762** |",
     "campaign_sporadic/logs/benchmark", "fused            50  0.3762"),
    ("bursty benign flag rate",
     "Benign stations flagged at 2 of 3 rise\nfrom 0.086 to 0.360.",
     "campaign_sporadic/logs/persistence",
     "   2/3                   382                  503            0.736           0.360"),
    ("collusion needs twenty receivers",
     "| a half | 20 | 13 |", None, None),
    # Drift. These live under runs/drift/logs because drift.py reads several
    # corpora at once and has no single run directory to write into.
    ("drift control with roadside units",
     "| light | **fused** | **-0.1972** | **-0.1941** |",
     "drift/logs/scenario",
     "campaign_v3      fused         0.3605 +/- 0.0083    0.5577 +/- 0.0137  -0.1972"),
    ("drift control congested",
     "| congested | **fused** | **-0.1656** | **-0.1613** |",
     "drift/logs/scenario",
     "campaign_dense   fused         0.4187 +/- 0.0004    0.5843 +/- 0.0098  -0.1656"),
    ("drift none within one run",
     "| **fused** | **0.5913** | **0.5930** | **-0.0017** | **0.7365** | **0.7219** |",
     "drift/logs/temporal",
     "fused         0.5913    0.5930    -0.0017    0.7365     0.7219"),
    ("drift prequential rises across the cut",
     "| 30 to 40 s | 11,814 | **0.5935** | **0.7378** |",
     "drift/logs/temporal", "30-40s    11,814    0.5935    0.7378"),
    # Superseded pair, kept because section 3d is a statement about the filter
    # rather than about the corpus and has not been repeated.
    ("drift baseline holds under seed grouping",
     "**0.5767 +/- 0.0181 on the congested corpus against 0.5843\nstation-grouped**",
     "drift/logs/density_seedgrouped",
     "campaign_dense   fused         0.4132 +/- 0.0265    0.5767 +/- 0.0181  -0.1634"),
    # The estimator-aware adversary. Two logs, because the constrained and
    # unconstrained versions are the whole point and quoting one without the
    # other is the misreading this section exists to prevent.
    # cross-checks kept from the other corpora
    # release 1.1.0 rewrite: sections 2, 3g, 3i, 5, 5b, 5c, 6, 6b, 7, 8, 8c
    ('2 gate count',
     'All 10 gates pass',
     'campaign_gnss/logs/validate', 'all 10 gates passed'),
    ('2 1-NN macro F1',
     '1-NN reaches a macro F1 of 0.3533',
     'campaign_gnss/logs/validate', '4 1-NN triviality: macro F1 0.3533'),
    ('2 depth-3 tree macro F1 and ceiling',
     'cannot exceed 0.727; it reaches 0.3103',
     'campaign_gnss/logs/validate', 'macro F1 0.3103 against a ceiling of 0.727 for 11 classes'),
    ('2 best single-feature separation',
     '0.0686 of other classes, `app_n_msgs` against sybil',
     'campaign_gnss/logs/validate', 'excludes 0.0686 of other classes (app_n_msgs vs class 6)'),
    ('2 oracle gate one-vs-rest AUC',
     '0.9803, `app_predict_mean` against pos_offset_random',
     'campaign_gnss/logs/validate', 'one-vs-rest AUC 0.9803 (app_predict_mean vs class 3), against 0.995'),
    ('2 dense corpus 1-NN',
     '0.3285 at the dense operating point',
     'campaign_dense_gnss/logs/validate', '4 1-NN triviality: macro F1 0.3285'),
    ('2 sporadic corpus 1-NN',
     '0.2188 on `campaign_sporadic`',
     'campaign_sporadic/logs/validate', '4 1-NN triviality: macro F1 0.2188'),
    ('2 floor corpus passes all gates',
     'also pass all 10 gates',
     'campaign_floor/logs/validate', 'all 10 gates passed'),
    ('2 offset_rsu corpus passes all gates',
     'also pass all 10 gates',
     'campaign_offset_rsu/logs/validate', 'all 10 gates passed'),
    ('2 dense corpus oracle AUC',
     'at the dense operating point, at 0.9686',
     'campaign_dense_gnss/logs/validate', 'one-vs-rest AUC 0.9686 (app_predict_mean vs class 3)'),
    ('2 no feature constant within a class',
     '0/50 in each of the',
     'campaign_gnss/logs/validate', '2 class 6 feature variation: 0/50 features effectively constant'),
    ('2 no feature constant on benign traffic',
     '| features constant on benign traffic | 0 |',
     'campaign_gnss/logs/validate', '7 benign distribution present: 0 features constant on benign traffic'),
    ('2 largest class share',
     'largest class at 0.702',
     'campaign_gnss/logs/validate', '8 class balance: largest class 0.702'),
    ('3g random forest macro F1 and MCC',
     '| random forest | **0.5068 +/- 0.0019** | 0.6438 |',
     'campaign_gnss/logs/model_independence', 'macro F1 0.5068 +/- 0.0019   MCC 0.6438'),
    ('3g hist gradient boosting macro F1 and MCC',
     '0.4945 +/- 0.0211 | 0.5871',
     'campaign_gnss/logs/model_independence', 'macro F1 0.4945 +/- 0.0211   MCC 0.5871'),
    ('3g mlp 128-64 macro F1 and MCC',
     '0.5030 +/- 0.0041 | 0.6291',
     'campaign_gnss/logs/model_independence', 'macro F1 0.5030 +/- 0.0041   MCC 0.6291'),
    ('3g logistic macro F1 and MCC',
     '0.4274 +/- 0.0056 | 0.5969',
     'campaign_gnss/logs/model_independence', 'macro F1 0.4274 +/- 0.0056   MCC 0.5969'),
    ('3g best of four on the position classes',
     '0.008 on class 11, 0.056 on class 13 and 0.158 on class 1',
     'campaign_gnss/logs/model_independence', 'class 11 0.008, class 13 0.056, class 1 0.158'),
    ('3g forest row reproduces the benchmark fused row',
     'reproduces section 3 exactly**: 0.5068 +/- 0.0019',
     'campaign_gnss/logs/benchmark', 'fused            50  0.5068 +/- 0.0019  0.8416  0.6438'),
    ('3i corpus size and stations',
     '250,000 windows from 720',
     'campaign_gnss/logs/plausibility_baseline', '250,000 windows, 720 stations, 3 folds grouped'),
    ('3i suite any-check binary F1/precision/recall/MCC',
     '| **suite, any check fires** | **0.307** | 0.652 | 0.201 | **0.246** |',
     'campaign_gnss/logs/plausibility_baseline', 'suite, any check fires        0.307      0.652    0.201    0.246'),
    ('3i learned 50-feature binary F1/precision/recall/MCC',
     '| **learned, 50 features** | **0.666** | 0.942 | 0.517 | **0.623** |',
     'campaign_gnss/logs/plausibility_baseline', 'learned, 50 features          0.666      0.942    0.517    0.623'),
    ('3i RSS claimed-distance check binary row',
     '| RSS claimed distance | 0.098 | 0.688 | 0.053 | 0.131 |',
     'campaign_gnss/logs/plausibility_baseline', 'RSS claimed distance          0.098      0.688    0.053    0.131'),
    ('3i RSS recall on constant-offset classes',
     '| RSS claimed distance | 0.057 |',
     'campaign_gnss/logs/plausibility_baseline', '  RSS claimed distance          0.057'),
    ('3i suite recall on constant-offset classes',
     '| suite, any check fires | 0.088 |',
     'campaign_gnss/logs/plausibility_baseline', '  suite                         0.088'),
    ('3i learned recall on constant-offset classes',
     '| learned, 50 features | 0.080 |',
     'campaign_gnss/logs/plausibility_baseline', '  learned                       0.080'),
    ('3i pooled mean per-station flag rate, 50 to 80 m band',
     "flags on average 0.864 of each station's windows",
     'campaign_gnss/logs/offset_floor_full', '50 to 80 m        21     1,193      0.864     0.90'),
    ('3i pooled stations caught, 50 to 80 m band',
     'catches 0.90 of those stations',
     'campaign_gnss/logs/offset_floor_full', '50 to 80 m        21     1,193      0.864     0.90'),
    ('3i pooled arm benign false flag rate',
     'false flag rate of 0.0162',
     'campaign_gnss/logs/offset_floor_full', 'benign stations 519, false flag rate 0.0162'),
    ('5 FedAvg macro F1',
     '| FedAvg | 0.2241 +/- 0.0302',
     'campaign_gnss/logs/federated', 'fedavg    macro F1 0.2241 +/- 0.0302'),
    ('5 FedAvg MCC',
     '0.3312 +/- 0.0346 | | |',
     'campaign_gnss/logs/federated', 'MCC multiclass 0.3312 +/- 0.0346'),
    ('5 FedLC macro F1',
     '**0.2480 +/- 0.0269**',
     'campaign_gnss/logs/federated', 'fedlc     macro F1 0.2480 +/- 0.0269'),
    ('5 FedLC macro F1 delta and exact p',
     'The gain is +0.0238 macro F1',
     'campaign_gnss/logs/federated', 'fedlc     delta +0.0238  p = 0.0078'),
    ('5 FedLC MCC delta and exact p',
     'and +0.0318 MCC',
     'campaign_gnss/logs/federated', 'fedlc     MCC delta +0.0318  p = 0.0078'),
    ('5 FedLC tuned tau',
     'mu 0.0001, tau 4.0, lambda 0.01',
     'campaign_gnss/logs/federated', 'tuned fedlc: tau = 4.0'),
    ('5 FedProx mu at grid edge',
     'mu 0.0001, tau 4.0',
     'campaign_gnss/logs/federated', 'tuned fedprox: mu = 0.0001 (validation macro F1 0.2675)  AT THE GRID EDGE'),
    ('5 FedProx identical to FedAvg',
     'p = 1.0000 on both aggregates',
     'campaign_gnss/logs/federated', 'fedprox   delta +0.0000  p = 1.0000'),
    ('5 FedNova macro F1 delta',
     'gains +0.0037 macro F1 at p = 0.5469',
     'campaign_gnss/logs/federated', 'fednova   delta +0.0037  p = 0.5469'),
    ('5 Panel partition total variation',
     'variation from the pooled distribution is 0.140',
     'campaign_gnss/logs/skew_rsu', 'mean total variation from the pooled distribution: 0.140'),
    ('5 Panel clients missing a class',
     '50 of 56 clients miss at least',
     'campaign_gnss/logs/skew_rsu', 'clients missing at least one class: 50 of 56'),
    ('5 All-observer total variation',
     'figures are 0.126, 654 of 816 and 313',
     'campaign_gnss/logs/skew', 'mean total variation from the pooled distribution: 0.126'),
    ('5 All-observer clients missing a class',
     'figures are 0.126, 654 of 816 and 313',
     'campaign_gnss/logs/skew', 'clients missing at least one class: 654 of 816'),
    ('5b receivers per pooled unit in a region',
     'maximum 19.**',
     'campaign_gnss/logs/pooled_regions', 'receivers per pooled unit: median 8, p10 5, p90 12, max 19'),
    ('5b region skew, total variation',
     'is 0.136 across the 96 regions',
     'campaign_gnss/logs/skew_regions', 'mean total variation from the pooled distribution: 0.136'),
    ('5b region panel FedAvg baseline',
     '| FedAvg | 0.4848 +/- 0.0045 | | | 0.5951 +/- 0.0037 | | |',
     'campaign_gnss/logs/federated_regions', 'fedavg    macro F1 0.4848 +/- 0.0045'),
    ('5b region FedLC macro F1 gain',
     '| **FedLC** | **0.5231 +/- 0.0045** | **+0.0383** | **0.0078** |',
     'campaign_gnss/logs/federated_regions', 'fedlc     delta +0.0383  p = 0.0078'),
    ('5b region FedLC MCC gain',
     '**0.6036 +/- 0.0038** | **+0.0085** | **0.0078** |',
     'campaign_gnss/logs/federated_regions', 'fedlc     MCC delta +0.0085  p = 0.0078'),
    ('5b region FedLC tau at grid edge',
     'mu 0.0001, tau 8.0, lambda 0.01',
     'campaign_gnss/logs/federated_regions', 'tuned fedlc: tau = 8.0 (validation macro F1 0.5324)  AT THE GRID EDGE'),
    ('5b region FedNova no longer differs',
     '| FedNova | 0.4832 +/- 0.0043 | -0.0016 | 0.2500 |',
     'campaign_gnss/logs/federated_regions', 'fednova   delta -0.0016  p = 0.2500'),
    ('5b region FedProto, corrected variant',
     '| FedProto | 0.4836 +/- 0.0046 | -0.0011 | 0.0156 |',
     'campaign_gnss/logs/federated_regions', 'fedproto  delta -0.0011  p = 0.0156'),
    ('5b section 5 FedNova, cross reference',
     '+0.0037 at p = 0.5469',
     'campaign_gnss/logs/federated', 'fednova   delta +0.0037  p = 0.5469'),
    ('5b pooling gain, derived 0.4848 minus single arm 0.4290',
     '**Pooling inside a region is worth 0.0558 macro F1',
     'campaign_gnss/logs/federated_regions_single', 'fedavg    macro F1 0.4290 +/- 0.0062'),
    ('5b consensus block at region scale, derived 0.4848 minus 0.4879',
     '| the consensus block, on top of pooling | -0.0031 | 2 of 8 |',
     'campaign_gnss/logs/federated_regions_nocons', 'fedavg    macro F1 0.4879 +/- 0.0065'),
    ('5b pooling stage drops road-wrap windows',
     'drops receiver and claim windows that wrap the road',
     'campaign_gnss/logs/pooled_regions', 'seed1: dropped 19 receiver-windows and 23 claim-windows that wrap the road'),
    ('5b pooled-mean arm at 39 receivers, section 3b',
     'takes macro F1 from 0.5628 to',
     'campaign_gnss/logs/pooled_road', 'pooled-mean        0.5628 +/- 0.0424'),
    ('5b block difference at 39 receivers, derived 0.6019 minus 0.5628, unte',
     '0.6019, a difference of 0.0391',
     'campaign_gnss/logs/pooled_road', 'pooled-consensus   0.6019 +/- 0.0403'),
    ('5b block importance share at 39 receivers',
     'The block holds 0.181 of total feature importance',
     'campaign_gnss/logs/pooled_road', '0.181 of total importance (proportional share would be 0.180)'),
    ('5c no-DP baseline macro F1',
     '| off | 0.4848 +/- 0.0045 |',
     'campaign_gnss/logs/dp_sweep', 'off 0.4848 +/- 0.0045'),
    ('5c no-DP baseline MCC',
     '| 0.5951 +/- 0.0037 |',
     'campaign_gnss/logs/dp_sweep', '0.5951 +/- 0.0037'),
    ('5c clipping-only cost',
     'costs 0.0410 before any noise is added',
     'campaign_gnss/logs/dp_sweep', '0.00 0.4437 +/- 0.0032   -0.0410   no noise'),
    ('5c z=0.5 row',
     '| 0.50 | 0.4372 +/- 0.0041 | -0.0475 | 245.8 |',
     'campaign_gnss/logs/dp_sweep', '0.50 0.4372 +/- 0.0041   -0.0475      245.8'),
    ('5c z=1 row',
     '| 1.00 | 0.4229 +/- 0.0060 | -0.0619 | 82.9 |',
     'campaign_gnss/logs/dp_sweep', '1.00 0.4229 +/- 0.0060   -0.0619       82.9'),
    ('5c z=1 privacy loss exceeds pooling gain',
     'loss, 0.0619, already exceeds that gain',
     'campaign_gnss/logs/dp_sweep', '1.00 0.4229 +/- 0.0060   -0.0619'),
    ('5c z=2 row',
     '| 2.00 | 0.3694 +/- 0.0109 | -0.1154 | 31.5 |',
     'campaign_gnss/logs/dp_sweep', '2.00 0.3694 +/- 0.0109   -0.1154       31.5'),
    ('5c tightest epsilon, macro F1',
     'macro F1 falls to 0.2876 from 0.4848',
     'campaign_gnss/logs/dp_sweep', '3.00 0.2876 +/- 0.0317   -0.1972       18.8'),
    ('5c tightest epsilon row, loss and epsilon',
     '| **-0.1972** | **18.8** |',
     'campaign_gnss/logs/dp_sweep', '-0.1972       18.8'),
    ('5c tightest epsilon, MCC',
     '0.5951 to 0.3316',
     'campaign_gnss/logs/dp_sweep', '18.8 0.3316 +/- 0.0342'),
    ('5c pooling gain, derived 0.4848 minus 0.4290',
     'against 0.4290 in the paired single-receiver arm',
     'campaign_gnss/logs/federated_regions_single', 'fedavg    macro F1 0.4290 +/- 0.0062'),
    ('5c privacy loss against pooling gain, derived 0.1972 / 0.0558',
     'it** (0.1972 / 0.0558)',
     'campaign_gnss/logs/dp_sweep', '3.00 0.2876 +/- 0.0317   -0.1972'),
    ('5c 5b method spread, derived 0.5231 minus 0.4832',
     '0.4832 to FedLC at 0.5231',
     'campaign_gnss/logs/federated_regions', 'fednova   macro F1 0.4832 +/- 0.0043'),
    ('5c wrapped windows dropped by the pooling stage',
     'drops receiver and claim windows that wrap the road',
     'campaign_gnss/logs/pooled_regions', 'receiver-windows and 23 claim-windows that wrap the road'),
    ('6 decisions per observer per window',
     '36 decisions per observer per window',
     'campaign_gnss/logs/deployment', 'decisions per observer per window: 36.0'),
    ('6 training set size',
     'Trained on 462568 balanced windows',
     'campaign_gnss/logs/deployment', 'trained on 462568 balanced windows (30.0% benign)'),
    ('6 held-out evaluation set',
     '300000 held-out windows at the simulated',
     'campaign_gnss/logs/deployment', '300000 held-out windows at the SIMULATED prevalence (67.1% benign), 216 unseen stations'),
    ('6 threshold 0.50 row',
     '| 0.50 | 0.3593 | 0.7729 | 0.5129 |',
     'campaign_gnss/logs/deployment', '0.50   0.3593   0.7729     0.5129'),
    ('6 alerts per hour at 0.50',
     'raises 46565 false alerts per observer per',
     'campaign_gnss/logs/deployment', '46565       0.3885           0.0213     0.0856'),
    ('6 one alert every 77 ms, derived 3600 / 46565',
     'about one every 77',
     'campaign_gnss/logs/deployment', '46565       0.3885'),
    ('6 binary MCC peak at 0.70',
     'it peaks at 0.70, 0.6106',
     'campaign_gnss/logs/deployment', '3893       0.6106           0.1564     0.2813'),
    ('6 threshold 0.90 row',
     '| 0.90 | 0.0008 | 0.4063 | 0.9958 |',
     'campaign_gnss/logs/deployment', '0.90   0.0008   0.4063     0.9958'),
    ('6 0.90 alerts and recall',
     'At 0.90 it raises 109 an hour while finding 0.4063',
     'campaign_gnss/logs/deployment', '0.4063     0.9958                          109'),
    ('6 MCC at 1 percent peaks at 0.90',
     'the five thresholds at 0.90, 0.5781',
     'campaign_gnss/logs/deployment', '109       0.5589           0.8303     0.5781'),
    ('6b held-out coverage and scale',
     '0.294 of the benign traffic',
     'campaign_gnss/logs/persistence', "held-out benign traffic is 0.294 of the population's, so episode rates are scaled by 3.40"),
    ('6b corpus size',
     '1695 station tracks in 96 regions, 545 of them attackers',
     'campaign_gnss/logs/persistence', '50830 windows, 1695 station tracks in 96 regions, 545 of them attackers'),
    ('6b 5/7 operating point',
     '| **5/7** | **5** | **11** | **0.503** | **0.004** |',
     'campaign_gnss/logs/persistence', '   5/7                     5                   11            0.503           0.004'),
    ('6b 2/3 rule',
     '| 2/3 | 132 | 295 | 0.607 | 0.095 |',
     'campaign_gnss/logs/persistence', '   2/3                   132                  295            0.607           0.095'),
    ('6b 4/5 rule',
     '| 4/5 | 11 | 25 | 0.541 | 0.010 |',
     'campaign_gnss/logs/persistence', '   4/5                    11                   25            0.541           0.010'),
    ('6b small offset class found',
     '| **11 pos_small_offset, 1 to 25 m** | 97 | **0.134** |',
     'campaign_gnss/logs/persistence', '    11       97    0.134'),
    ('6b constant offset class found',
     '| **1 pos_const_offset, 22 to 233 m** | 46 | **0.543** |',
     'campaign_gnss/logs/persistence', '     1       46    0.543'),
    ('6b speed falsify found',
     '| 5 speed_falsify | 67 | 0.672 |',
     'campaign_gnss/logs/persistence', '     5       67    0.672'),
    ('6b contact time, short tracks',
     '| 1 to 4 | 69 | 0.333 | 0.030 |',
     'campaign_gnss/logs/persistence', '            (0, 4]               69            0.333           0.030'),
    ('6b contact time, long tracks',
     '| 17 or more | 360 | 0.683 | 0.109 |',
     'campaign_gnss/logs/persistence', '         (16, 100]              360            0.683           0.109'),
    ('7 single-window inference',
     'single-window inference    3.085 ms',
     'campaign_gnss/logs/latency', 'single-window inference      3.085 ms'),
    ('7 inference share of shortest path',
     "0.31 percent of the shortest path's window fill plus inference",
     'campaign_gnss/logs/latency', 'Inference is 0.31 percent of the shortest path'),
    ('7 receivers per unit in pooling cost sample',
     'median 39 receivers per unit (6 to',
     'campaign_gnss/logs/pooling_cost', 'median 39, min 6, max 66'),
    ('7 whole consensus block cost per unit',
     '| both | **1.3367** |',
     'campaign_gnss/logs/pooling_cost', '1.3367'),
    ('7 free fit relative to inference',
     '0.43 times the inference cost',
     'campaign_gnss/logs/pooling_cost', 'the free fit alone is 0.43 times the inference cost'),
    ('7 block share of a 1000 ms window',
     '0.134 percent of a 1000 ms window',
     'campaign_gnss/logs/pooling_cost', '0.134 percent of a 1000 ms window'),
    ('7 pool_mlat_err importance rank',
     'ranks sixth of sixty one features',
     'campaign_gnss/logs/pooled_road', 'rank   6  pool_mlat_err'),
    ('7 consensus block gain at 39 receivers (derived 0.6019 minus 0.5628), ',
     'adds 0.0391 macro F1',
     'campaign_gnss/logs/pooled_road', '0.6019 +/- 0.0403'),
    ('7 consensus block gain at 39 receivers, pooled-mean component',
     '0.6019 against 0.5628',
     'campaign_gnss/logs/pooled_road', '0.5628 +/- 0.0424'),
    ('7 closed-form pool_claim_rmse separation on class 1',
     '+4.92 and -5.61 benign standard deviations',
     'campaign_gnss/logs/pool_separation_road', 'pool_claim_rmse                4.92'),
    ('7 pool_rmse_ratio separation on class 1 (needs the free fit)',
     'by +6.45',
     'campaign_gnss/logs/pool_separation_road', 'pool_rmse_ratio                6.45'),
    ('7 fused macro F1 at 1000 ms window',
     '**0.4520 +/- 0.0057**',
     'campaign_gnss/logs/benchmark_w1000', '0.4520 +/- 0.0057'),
    ('7 fused macro F1 at 200 ms window (0.0415 cost is derived 0.4520 minus',
     'costs 0.0415 fused macro F1',
     'campaign_gnss/logs/benchmark_w200', '0.4105 +/- 0.0035'),
    ('7 phy-only macro F1 at 1000 ms (44 percent gain is derived from 0.2202',
     '**0.3171 +/- 0.0211**',
     'campaign_gnss/logs/benchmark_w1000', '0.3171 +/- 0.0211'),
    ('7 phy-only macro F1 at 200 ms',
     '0.2202 +/- 0.0174',
     'campaign_gnss/logs/benchmark_w200', '0.2202 +/- 0.0174'),
    ('7 500 ms dips (derived 0.4098 minus 0.3990 and 0.4105 minus 0.3978), a',
     '0.0108 and 0.0127, are smaller',
     'campaign_gnss/logs/benchmark_w500', '0.3990 +/- 0.0143'),
    ('7 fused 500 ms fold SD compared against the dip',
     '(0.0143 and 0.0199)',
     'campaign_gnss/logs/benchmark_w500', '0.3978 +/- 0.0199'),
    ('8 BLER at the 10 to 15 dB transition',
     '0.0375 at 10 to 15',
     'campaign_gnss/logs/calibration', '193656  0.0375'),
    ('8 BLER at 5 to 10 dB',
     '0.8106 at 5 to 10',
     'campaign_gnss/logs/calibration', '284318  0.8106'),
    ('8 PRR under 50 m',
     '0.9292 under 50 m',
     'campaign_gnss/logs/calibration', '6756  0.9292'),
    ('8 PRR beyond 1 km',
     '0.0346 beyond 1 km',
     'campaign_gnss/logs/calibration', '276251  0.0346'),
    ('8 CBR on the main corpus seed 1',
     'mean 0.318, median 0.317, p95 0.397 and max 0.536',
     'campaign_gnss/logs/calibration', 'CBR estimate: mean 0.318, median 0.317, p95 0.397, max 0.536'),
    ('8 Message count and per-station rate',
     '35159 messages at a mean 6.75 Hz',
     'campaign_gnss/logs/calibration', 'messages 35159, mean rate 6.75 Hz'),
    ('8 Decoded SL-RSRP minimum',
     'spanning -129.8 to',
     'campaign_gnss/logs/calibration', 'RSRP dBm min -129.8'),
    ('8 Decoded SL-RSRP median',
     'median of -113.2',
     'campaign_gnss/logs/calibration', 'median -113.2'),
    ('8 RSRP band median beyond 1 km',
     '-122.1 beyond 1 km',
     'campaign_gnss/logs/calibration', '-122.1'),
    ('8 Path loss exponent from decoded RSRP',
     '**an exponent of 2.37**',
     'campaign_gnss/logs/calibration', 'an exponent of 2.37. Free space is 2.'),
    ('8c bundle shards load',
     'pass, 7,916,708 rows in 67s',
     'campaign_gnss/logs/check_release_bundle', '7,916,708 rows in 67s'),
    ('8c schema columns',
     'pass, 60 of 60 promised',
     'campaign_gnss/logs/check_release_bundle', '60 of 60 promised'),
    ('8c no transmitter spans partitions',
     '**pass, 0 span partitions**',
     'campaign_gnss/logs/check_release_bundle', '0 span partitions'),
    ('8c bundle baseline, reference scenario',
     '**macro F1 0.5319, MCC 0.6746**',
     'campaign_gnss/logs/check_release_bundle', 'macro F1 0.5319, MCC 0.6746'),
    ('8c three-scenario baseline and its test rows',
     'macro F1 0.5258, MCC 0.5975 on 1,300,560',
     'campaign_gnss/logs/check_release_bundle', 'scored on 1,300,560, 90s  ->  macro F1 0.5258, MCC 0.5975'),
    ('8c three-scenario F1 change',
     'as -0.0061',
     'campaign_gnss/logs/check_release_bundle', 'moves it -0.0061'),
    ('8c starter macro F1',
     'macro F1 **0.5068 +/- 0.0019**',
     'campaign_gnss/logs/baseline_starter_cv', '0.5068 +/- 0.0019'),
    ('8c starter MCC',
     '**0.6438 +/- 0.0458**',
     'campaign_gnss/logs/baseline_starter_cv', '0.6438 +/- 0.0458'),
    ('8c starter ten-class macro F1',
     '0.5575 +/- 0.0021 over the ten classes',
     'campaign_gnss/logs/baseline_starter_cv', 'the 10 with a signature  0.5575 +/- 0.0021'),
    ('8c section 3 benchmark figure',
     'the 0.5068 that',
     'campaign_gnss/logs/benchmark', 'fused            50  0.5068 +/- 0.0019'),
    ('8c manifest file count',
     '16 of 32 files',
     'campaign_gnss/logs/check_release_package', '16 of 32 files present'),
    ('8c manifest count in the table',
     'pass, 32 files',
     'campaign_gnss/logs/check_release_package', '16 of 32 files present'),
    ('8c bundler log file count',
     'prints 33',
     'campaign_gnss/logs/make_release_v110', '33 files'),
    ('8c reference package size',
     '(359M in',
     'campaign_gnss/logs/package_v110', '359M 27 Sep 14:03 cv2x-ids-1.1.0-highway_sparse.zip'),
    ('8c transmitters vs claimed identities',
     '1170 physical transmitters carrying 1287',
     'campaign_gnss/logs/release_splits_v110', '1170 physical transmitters carrying 1287 claimed identities'),
    ('3 fused macro F1 and MCC',
     '| **fused** | 50 | **0.5068 +/- 0.0019** | **0.8416** | **0.6438** |',
     'campaign_gnss/logs/benchmark', 'fused            50  0.5068 +/- 0.0019  0.8416  0.6438'),
    ('3 app-only',
     '| application-only | 22 | 0.4880 +/- 0.0042 | 0.8338 | 0.6236 |',
     'campaign_gnss/logs/benchmark', 'app-only         22  0.4880 +/- 0.0042  0.8338  0.6236'),
    ('3 phy block',
     '| phy block | 28 | 0.3363 +/- 0.0081 | 0.7831 | 0.4745 |',
     'campaign_gnss/logs/benchmark', 'phy-only         28  0.3363 +/- 0.0081  0.7831  0.4745'),
    ('3 radio-only',
     '| radio-only | 15 | 0.2495 +/- 0.0072 | 0.7587 | 0.3891 |',
     'campaign_gnss/logs/benchmark', 'radio-only       15  0.2495 +/- 0.0072  0.7587  0.3891'),
    ('3 fused ten classes',
     '**0.5575 +/- 0.0021**',
     'campaign_gnss/logs/benchmark', 'fused      0.5575 +/- 0.0021'),
    ('3 class 1 blind to app and radio alone',
     '| 1 pos_const_offset, 22 to 233 m | **0.000** | **0.135** | **0.000** | 0.145 |',
     'campaign_gnss/logs/benchmark', '     1         0.000         0.135         0.145         0.000'),
    ('3 speed negative control',
     '| 5 speed_falsify | **0.658** | **0.000** | 0.000 | 0.627 |',
     'campaign_gnss/logs/benchmark', '     5         0.658         0.000         0.627         0.000'),
    ('3 sybil union',
     '| 6 sybil | 0.854 | 0.754 | 0.694 | **0.895** |',
     'campaign_gnss/logs/benchmark', '     6         0.854         0.754         0.895         0.694'),
    ('3 medium offset',
     '| 13 pos_medium_offset, 47 to 83 m | **0.000** | 0.030 | 0.001 | 0.021 |',
     'campaign_gnss/logs/benchmark', '    13         0.000         0.030         0.021         0.001'),
    ('3 top feature phy_rsrp_count',
     '`phy_rsrp_count`, 0.0734',
     'campaign_gnss/logs/benchmark', 'phy_rsrp_count            0.073405'),
    ('3 ladder constant offset',
     '139.9 m when lying',
     'campaign_gnss/logs/magnitude_ladder', '139.9'),
    ('3 dense fused',
     '| **fused** | 50 | **0.5001 +/- 0.0161** | **0.8029** | **0.5870** |',
     'campaign_dense_gnss/logs/benchmark', 'fused            50  0.5001 +/- 0.0161  0.8029  0.5870'),
    ('3 dense class 1',
     '| 1 pos_const_offset | **0.002** | **0.212** | 0.000 | 0.212 |',
     'campaign_dense_gnss/logs/benchmark', '     1         0.002         0.212         0.212         0.000'),
    ('3 dense 1-NN',
     '1-NN at 0.3285',
     'campaign_dense_gnss/logs/validate', 'macro F1 0.3285'),
    ('3 dense ten classes',
     'fused macro\nF1 is 0.5501',
     'campaign_dense_gnss/logs/benchmark', 'fused      0.5501 +/- 0.0177'),
    ('3 selection top 15',
     '| 15 | 0.4741 +/- 0.0166 | -0.0050 |',
     'campaign_gnss/logs/feature_selection', '       15  0.4741 +/- 0.0166     -0.0050'),
    ('3 selection stability',
     '15 distinct features are ever chosen',
     'campaign_gnss/logs/feature_selection', '15 distinct features ever chosen, 0 of them in only one fold'),
    ('3b2 floor crossing',
     '> **50 percent detection at 38.9 m, 95 percent interval 34.5 to 45.5 m**',
     'campaign_floor/logs/offset_floor_located', '95 percent interval        34.5 to 45.5 m (2000 of 2000 bootstrap fits converged)'),
    ('3b2 floor point',
     '50 percent detection at 38.9 m',
     'campaign_floor/logs/offset_floor_located', '50 percent detection at     38.9 m'),
    ('3b2 seed-resampled interval',
     'whole seeds instead gives **35.3 to 44.1 m**',
     'campaign_floor/logs/offset_floor_located', '95 percent interval      35.3 to 44.1 m, width 8.8 m'),
    ('3b2 interval width',
     'an 11.1 m interval',
     'campaign_floor/logs/offset_floor_located', 'interval width             11.1 m'),
    ('3b2 band 30 to 50',
     '| **30 to 50 m** | **11** | **0.64** |',
     'campaign_floor/logs/offset_floor_located', '30 to 50 m        11       625      0.441     0.64'),
    ('3b2 pooled false flag',
     'pooled arm is **0.0113**',
     'campaign_floor/logs/offset_floor_located', 'benign stations 393, false flag rate 0.0113'),
    ('3b2 localisation',
     '18.3 m from the truth here',
     'campaign_floor/logs/pooled_road', 'estimate to TRUE position     median    18.3 m'),
    ('3b2 stations',
     '**44 position attacker stations',
     'campaign_floor/logs/offset_floor_located', 'locating the floor from all 44 stations'),
    ('4b triples',
     '**29,461 benign triples**',
     'drift/logs/br_gnss_free', '29,461 triples, 72 directions searched per displacement.'),
    ('4b free localisation',
     'is 67.2 m unconstrained',
     'drift/logs/br_gnss_free', 'free-fit localisation error on these benign triples: median 67.2 m'),
    ('4b road localisation',
     '18.3 m bounded to the carriageway',
     'drift/logs/br_gnss_roadest', 'free-fit localisation error on these benign triples: median 18.3 m'),
    ('4b free free 50 m',
     '| 50 m | **1.011** | **0.121** | **0.002** | 80 deg | +14.7 m |',
     'drift/logs/br_gnss_free', '50 m       2.838     0.281       1.011      0.121         0.002        0.676           0.406          80.0          14.7'),
    ('4b onroad 100 m',
     '| 100 m | 1.732 | **0.953** | **0.850** | 5 deg |',
     'drift/logs/br_gnss_onroad', '100 m       4.842     0.944       1.732      0.953         0.850'),
    ('4b onroad 200 m',
     '| 200 m | 2.452 | **0.975** | **0.953** | 0 deg |',
     'drift/logs/br_gnss_onroad', '200 m       6.853     0.972       2.452      0.975         0.953'),
    ('4b both 50 m',
     '| 50 m | 0.271 | **0.389** | **0.769** |',
     'drift/logs/br_gnss_both', '50 m       3.641     0.708       1.175      0.769         0.389'),
    ('4b roadest free attacker',
     'the ratio goes **below** one: 0.946 at 50 m',
     'drift/logs/br_gnss_roadest', '50 m       2.838     0.281       0.946      0.129         0.012        0.741           0.060'),
    ('4b placement 40 m',
     'across-road bound falls from 33.7 m to 26.9 m',
     'campaign_gnss/logs/geometry_placement', '40m        26.9 m       11.0 m          78.3 deg        2.43'),
    ('3b units and receivers',
     '43,360 (station, window)',
     'campaign_gnss/logs/pooled_road', '43360 pooled units, 720 stations, 11 classes'),
    ('3b median receivers',
     '**median 39 receivers per unit**',
     'campaign_gnss/logs/pooled_road', 'observers per unit: median 39, min 5, max 67'),
    ('3b benign localisation',
     '| benign | 0.0 | **18.3** | **18.9** |',
     'campaign_gnss/logs/pooled_road', 'estimate to TRUE position     median    18.3 m'),
    ('3b class 1 localisation',
     '| 1 pos_const_offset | 140.6 | **18.6** | **138.7** |',
     'campaign_gnss/logs/pooled_road', 'class 1: true offset median   140.6 m,  estimate to claim   138.7 m,  estimate to true    18.6 m'),
    ('3b unconstrained benign error',
     'benign estimates 67.3 m from the truth',
     'campaign_gnss/logs/pooled', 'estimate to TRUE position     median    67.3 m'),
    ('3b pooled-consensus',
     '| **pooled-consensus** | **0.6019 +/- 0.0403** | **+0.1258** | **0.7615** |',
     'campaign_gnss/logs/pooled_road', 'pooled-consensus   0.6019 +/- 0.0403     +0.1258    0.001953  0.7615'),
    ('3b single receiver',
     '| single receiver | 0.4760 +/- 0.0375 |',
     'campaign_gnss/logs/pooled_road', 'single             0.4760 +/- 0.0375'),
    ('3b class 1 gain',
     'Class 1 goes from 0.128 to 0.571',
     'campaign_gnss/logs/pooled_road', 'class 1: single 0.128 -> consensus 0.571 (+0.443), p=0.003906, vote 0.000, vote-soft 0.000'),
    ('3b class 13 gain',
     'class 13 from 0.027 to 0.379',
     'campaign_gnss/logs/pooled_road', 'class 13: single 0.027 -> consensus 0.379 (+0.351), p=0.001953, vote 0.000, vote-soft 0.000'),
    ('3b unconstrained F1',
     '**The unconstrained estimator reaches 0.5972 +/- 0.0443',
     'campaign_gnss/logs/pooled', 'pooled-consensus   0.5972 +/- 0.0443'),
    ('3b dense pooled-consensus',
     '| **pooled-consensus** | **0.6735 +/- 0.0350** | **+0.1638** |',
     'campaign_dense_gnss/logs/pooled_road_veh', 'pooled-consensus   0.6735 +/- 0.0350     +0.1638'),
    ('3b dense class 13',
     'class 13 goes 0.026 to 0.561',
     'campaign_dense_gnss/logs/pooled_road_veh', 'class 13: single 0.026 -> consensus 0.561 (+0.535)'),
    ('3b sparse vehicles-only',
     'pooled-consensus reaches 0.6052 +/- 0.0345',
     'campaign_gnss/logs/pooled_road_veh', 'pooled-consensus   0.6052 +/- 0.0345'),
    ('3b sweep five receivers',
     '| 5 | 0.4923 | 0.3107 | 0.1208 |',
     'campaign_gnss/logs/pooled_sweep', '5  0.4923 +/- 0.0490  0.3107 +/- 0.0548  0.1208 +/- 0.0144'),
    ('3b sweep ten receivers',
     '| 10 | 0.5279 | **0.4697** | 0.1694 |',
     'campaign_gnss/logs/pooled_sweep', '10  0.5279 +/- 0.0515  0.4697 +/- 0.0417  0.1694 +/- 0.0500'),
    ('3b ratio separation',
     'falsification at **+6.45 benign standard',
     'campaign_gnss/logs/pool_separation_road', 'pool_rmse_ratio                6.45    1.71    2.94'),
    ('3b permuted claim',
     '| **benign, claim permuted** | **9.82 dB** | **12.79** | **0.113** |',
     'campaign_gnss/logs/claim_permutation', 'benign, claim permuted              29464        9.82           12.79     0.113     1770.3 m'),
    ('3b floor crossing full corpus',
     'crosses one half at **36.3 m**, 95 percent interval 26.1 to 51.4 m',
     'campaign_gnss/logs/offset_floor_full', '95 percent interval        26.1 to 51.4 m'),
    ('3b floor pooled 50 to 80',
     '| 50 to 80 m | 21 | 0.00 | **0.90** |',
     'campaign_gnss/logs/offset_floor_full', '50 to 80 m        21     1,193      0.864     0.90'),
    ('3b debiased crossing',
     'moves the crossing to 32.2 m',
     'campaign_gnss/logs/offset_floor_debias', '50 percent detection at     32.2 m'),
    ('4 dense loud flood',
     '| rate flooding, loud (7) | 10 ms interval, 100 Hz | 0.963 |',
     'campaign_dense_gnss/logs/benchmark', '     7         0.960         0.699         0.963         0.644'),
    ('4 dense stealthy flood',
     '| rate flooding, stealthy (12) | 40 to 80 ms interval, 12.5 to 25 Hz | 0.958 |',
     'campaign_dense_gnss/logs/benchmark', '    12         0.956         0.734         0.958         0.688'),
    ('4 dense loud position',
     '| position falsification, loud (1) | 135.2 m median, 28 stations | 0.212 |',
     'campaign_dense_gnss/logs/benchmark', '     1         0.002         0.212         0.212         0.000'),
    ('4 dense loud magnitude',
     '135.2 m median, 28 stations',
     'campaign_dense_gnss/logs/magnitude_ladder', '  1 pos_const_offset       28    21.1    90.4   135.2   217.1   247.1  0'),
    ('4 dense stealthy magnitude',
     '**11.6 m** median, 26 stations',
     'campaign_dense_gnss/logs/magnitude_ladder', ' 11 pos_small_offset       26     3.3     9.2    11.6    14.8    24.7  3'),
    ('4 dense benign rate',
     'Benign CAMs in this scenario run at 1.13 Hz',
     'campaign_dense_gnss/logs/check_seed1', 'benign CAM: median 1000 ms, mean 887, 1.13 Hz'),
    ('4b class 1 none',
     '| 1 pos_const_offset | none | 0.641 | **0.915** |',
     'campaign_gnss/logs/power_evasion', '     1       none             0.641             0.915'),
    ('4b class 1 targeted',
     '| 1 | power-targeted | **0.500** | **0.915** |',
     'campaign_gnss/logs/power_evasion', '     1 power-targeted             0.500             0.915'),
    ('4b class 13',
     '**The mid-magnitude class behaves the same way**, 0.811 pooled',
     'campaign_gnss/logs/power_evasion', '    13 power-targeted             0.500             0.811'),
    ('4b sybil pooled',
     '| 6 | power-targeted | 0.500 | 0.917 |',
     'campaign_gnss/logs/power_evasion', '     6 power-targeted             0.500             0.917'),
    ('3h law intercept',
     'intercept **-38.48 dBm**',
     'campaign_gnss/logs/geometry_bound', 'intercept A              -38.48 dBm'),
    ('3h law exponent',
     'path loss exponent **2.505**',
     'campaign_gnss/logs/geometry_bound', 'path loss exponent n      2.505'),
    ('3h law residual',
     'residual **3.444 dB**',
     'campaign_gnss/logs/geometry_bound', 'residual sigma            3.444 dB'),
    ('3h persistent floor',
     '**1.171 dB persistent against 3.059 dB per',
     'campaign_gnss/logs/geometry_bound', 'per link, persists while the link lasts      1.171 dB'),
    ('3h median ambiguity',
     '| median, 612.8 m | **69.7 m** |',
     'campaign_gnss/logs/geometry_bound', '50th       612.8 m            69.7 m'),
    ('3h ellipse angle',
     '| **50th** | **35.5 m** | **7.3 m** | **79.7 deg** |',
     'campaign_gnss/logs/geometry_bound', '50th percentile   major      35.5 m   minor     7.3 m   major axis  79.7 deg from the road'),
    ('3h median radial',
     '| **free fit, median radial error** | **25.6 m** | **67.2 m** |',
     'campaign_gnss/logs/geometry_bound', 'median radial error of an efficient estimator      25.6 m'),
    ('3h road constrained',
     '| road constrained, along-road standard deviation | 8.1 m | |',
     'campaign_gnss/logs/geometry_bound', 'along the road                  8.1 m'),
    ('3h region scale',
     '| one region | 8 | 4983.4 m | 2970.5 m |',
     'campaign_gnss/logs/geometry_bound_regions', 'across the road              4983.4 m'),
    ('3h region 10 to 14',
     'region-scoped units with the same 10 to 14 receivers give 1751.8 m',
     'campaign_gnss/logs/geometry_bound_regions', '10 to 14     1451      1751.8 m'),
    ('3h placement optimum',
     '| **40 m** | **26.9 m** | 11.0 m | **2.43** |',
     'campaign_gnss/logs/geometry_placement', '40m        26.9 m       11.0 m          78.3 deg        2.43'),
    ('3h placement worse than nothing',
     '| 200 m | 36.9 m | 11.4 m | 3.23 |',
     'campaign_gnss/logs/geometry_placement', '200m        36.9 m       11.4 m          80.2 deg        3.23'),
    ('3h2 centreline across',
     '| across-road bound | 36.2 m | **28.3 m** | **-21.8 percent** |',
     'campaign_gnss/logs/geometry_bound_3seed', 'across the road                36.2 m'),
    ('3h2 offset across',
     '| across-road bound | 36.2 m | **28.3 m**',
     'campaign_offset_rsu/logs/geometry_bound', 'across the road                28.3 m'),
    ('3h2 offset anisotropy',
     '| **anisotropy** | **3.2** | **2.5** | |',
     'campaign_offset_rsu/logs/geometry_bound', 'anisotropy                      2.5'),
    ('3h2 offset radial',
     '| median radial bound | 27.3 m | 23.0 m | |',
     'campaign_offset_rsu/logs/geometry_bound', 'median radial error of an efficient estimator      23.0 m'),
    ('3h2 free centreline',
     '| free fit localisation error, measured | 68.6 m |',
     'campaign_gnss/logs/br_centreline3_free', 'median 68.6 m'),
    ('3h2 free offset',
     '| free fit localisation error, measured | 68.6 m | **70.4 m** |',
     'campaign_offset_rsu/logs/br_offset_free', 'median 70.4 m'),
    ('3h2 road offset',
     '| road constrained localisation error, measured | 17.9 m | **18.1 m** |',
     'campaign_offset_rsu/logs/br_offset_roadest', 'median 18.1 m'),
    ('3h2 br offset 50 m',
     '| best-response AUC at 50 m, free estimator | 0.124 | 0.155 |',
     'campaign_offset_rsu/logs/br_offset_free', '50 m       2.899     0.307       1.014      0.155'),
    ('3h3 misspecification near',
     '-4.31 dB under 60 m',
     'campaign_gnss/logs/estimator_study_heldout', '0 m to 60 m              -4.31 dB    4.86 dB'),
    ('3h3 misspecification mid',
     '+1.74 dB at 200 to 400 m',
     'campaign_gnss/logs/estimator_study_heldout', '200 m to 400 m           +1.74 dB    2.85 dB'),
    ('3h3 ols free',
     '| ordinary least squares, what the project uses | 67.1 m | 18.5 m |',
     'campaign_gnss/logs/estimator_study_heldout', 'ols, what the project uses          67.1 m    1.00x'),
    ('3h3 ols road',
     '| ordinary least squares, what the project uses | 67.1 m | 18.5 m |',
     'campaign_gnss/logs/estimator_study_heldout_road', 'ols, what the project uses          18.5 m    1.00x'),
    ('3h3 debiased free',
     '| calibrated mean removed | 20.2 m | 13.9 m |',
     'campaign_gnss/logs/estimator_study_heldout', 'debiased, calibrated mean           20.2 m    0.30x'),
    ('3h3 debiased road',
     '| calibrated mean removed | 20.2 m | 13.9 m |',
     'campaign_gnss/logs/estimator_study_heldout_road', 'debiased, calibrated mean           13.9 m    0.75x'),
    ('3h3 debiased weighted road',
     '| **calibrated mean removed and weighted** | **19.3 m** | **12.4 m** |',
     'campaign_gnss/logs/estimator_study_heldout_road', 'debiased and weighted               12.4 m    0.67x'),
    ('3h3 weighted road',
     '| inverse variance weights | 66.3 m | 17.6 m |',
     'campaign_gnss/logs/estimator_study_heldout_road', 'wls, inverse variance               17.6 m    0.95x'),
    ('3h3 residual after',
     'Removing the mean takes the residual on the calibration data from 3.461 dB to',
     'campaign_gnss/logs/estimator_study_heldout', 'residual on the calibration data, before removing the calibrated mean  3.461 dB'),
    ('3h3 debias both 50 m',
     'debiased estimator an on-road lie of 50 m is caught 0.504 of the time against',
     'drift/logs/br_gnss_both_debias', '50 m       3.198     0.744       1.175      0.836         0.504'),
    ('3h4 sigma corrected',
     '3.025 dB, a fall of 12.2 percent',
     'campaign_gnss/logs/geometry_bound_corrected', 'Sigma falls by 12.2 percent'),
    ('3h4 corrected radial',
     '| median radial error of an efficient estimator | 25.6 m | **34.5 m** |',
     'campaign_gnss/logs/geometry_bound_corrected', 'median radial error of an efficient estimator      34.5 m'),
    ('3h4 corrected angle',
     '| ellipse major axis, median | **79.7 deg** | **83.7 deg** |',
     'campaign_gnss/logs/geometry_bound_corrected', '50th percentile   major      47.4 m   minor    10.1 m   major axis  83.7 deg from the road'),
    ('3h4 corrected anisotropy',
     '| anisotropy | 3.1 | **3.8** |',
     'campaign_gnss/logs/geometry_bound_corrected', 'anisotropy                      3.8'),
    ('3h4 road ols tail',
     '| ordinary least squares, what the project uses | 18.5 m | 26.7 m | 45.0 m | **40.8 m** | 2.21 | 0.00% |',
     'campaign_gnss/logs/estimator_study_heldout_road', 'ols, what the project uses          18.5 m    1.00x   26.7 m   45.0 m    40.8 m     2.21      0.00%'),
    ('3h4 road debiased weighted tail',
     '| **calibrated mean removed and weighted** | **12.4 m** | 20.5 m | 30.0 m | **24.6 m** | 1.99 | 0.00% |',
     'campaign_gnss/logs/estimator_study_heldout_road', 'debiased and weighted               12.4 m    0.67x   20.5 m   30.0 m    24.6 m     1.99      0.00%'),
    ('3h4 free debiased weighted tail',
     '| **calibrated mean removed and weighted** | **19.3 m** | 36.2 m | 63.0 m | **43.9 m** | 2.28 | 0.00% |',
     'campaign_gnss/logs/estimator_study_heldout', 'debiased and weighted               19.3 m    0.29x   36.2 m   63.0 m    43.9 m     2.28      0.00%'),
    ('3h4 transfer fraction',
     'so **0.66 of the achievable gain transfers**',
     'campaign_gnss/logs/correction_transfer', 'fraction of the achievable gain that transfers    0.66'),
    ('3h4 transfer own curve',
     'against 7.2 percent for a curve fitted on that corpus',
     'campaign_gnss/logs/correction_transfer', "corrected with B's own curve          3.890     7.2 percent removed"),
    ('3h5 triples',
     '599,267 observations, 10,488 triples',
     'campaign_gnss/logs/br_centreline3_free_debias', '10,488 triples, 72 directions searched per displacement.'),
    ('3h5 25 m corrected angle',
     '| 25 m | 75 deg | **65 deg** |',
     'campaign_gnss/logs/br_centreline3_roadest_debias', '25 m       2.624     0.422       0.995      0.267         0.022        0.567           0.048          65.0'),
    ('3h5 50 m corrected',
     '| 50 m | 0.013 | **0.110** |',
     'campaign_gnss/logs/br_centreline3_roadest_debias', '50 m       2.726     0.492       1.004      0.420         0.110'),
    ('3h5 50 m single slope',
     '| 50 m | 0.013 | **0.110** |',
     'campaign_gnss/logs/br_centreline3_roadest', '50 m       2.825     0.281       0.946      0.130         0.013'),
    ('3h5 200 m corrected',
     '| 200 m | 0.241 | **0.627** |',
     'campaign_gnss/logs/br_centreline3_roadest_debias', '200 m       3.398     0.795       1.261      0.854         0.627'),
    ('3h5 debiased free tail',
     'an RMS of 245.2 m, a ratio of 10.18',
     'campaign_gnss/logs/br_centreline3_free_debias', 'median 24.1 m, 90th 97.8 m, RMS 245.2 m, RMS/median 10.18'),
    ('3h5 honest residual',
     'the honest baseline residual falls from 3.209 dB to',
     'campaign_gnss/logs/br_centreline3_roadest_debias', '0 m, honest       2.741'),
    ('3h7 scale 0 tail',
     '| 0.00 | 68.6 m | 140.5 m | 2.05 | 93.3 m | 1.36 | 79.8 deg |',
     'campaign_gnss/logs/eff_sweep_000', 'median 68.6 m, 90th 140.5 m, RMS 93.3 m, RMS/median 1.36'),
    ('3h7 scale 1 tail',
     '| 1.00 | 24.1 m | 97.8 m | 4.06 | 245.2 m | 10.18 | 83.6 deg |',
     'campaign_gnss/logs/eff_sweep_100', 'median 24.1 m, 90th 97.8 m, RMS 245.2 m, RMS/median 10.18'),
    ('3h7 scale 0.5 tail',
     '| 0.50 | 41.5 m | 123.0 m | 2.96 | 242.6 m | 5.84 | 81.3 deg |',
     'campaign_gnss/logs/eff_sweep_050', 'median 41.5 m, 90th 123.0 m, RMS 242.6 m, RMS/median 5.84'),
    ('3h7 bound scale 0',
     'its bound median axis is **79.8 deg**',
     'campaign_gnss/logs/bound_sweep_000', 'major axis  79.8 deg from the road'),
    ('3h7 bound scale 1',
     'its bound axis is **83.6 deg**',
     'campaign_gnss/logs/bound_sweep_100', 'major axis  83.6 deg from the road'),
    ('3h7 attacker 25 m scale 1',
     '| **25 m** | +4.8 | +5.5 | +11.3 | +17.3 | **+18.6** | 75 to 65 deg |',
     'campaign_gnss/logs/eff_sweep_100', '25 m       2.624     0.422       1.000      0.270         0.019        0.549           0.040          65.0'),
    ('3h7 no censoring',
     'cuts 0.00 percent at 3 km and 12 km',
     'campaign_gnss/logs/eff_sweep_100', 'RMS<3km 245.2 m (0.00% cut) RMS<12km 245.2 m (0.00% cut)'),
    ('3h8 subset b scale 1 tail',
     'RMS over median rises from 1.61 to 12.18 on',
     'campaign_gnss/logs/rep_b_eff_100', 'RMS/median 12.18'),
    ('3h8 subset b scale 0 tail',
     'RMS over median rises from 1.61',
     'campaign_gnss/logs/rep_b_eff_000', 'RMS/median 1.61'),
    ('3h8 subset c scale 1 tail',
     'from 1.82 to 11.51 on seeds 7 and 8',
     'campaign_gnss/logs/rep_c_eff_100', 'RMS/median 11.51'),
    ('3h8 subset b bound top',
     '**80.1 to 83.9** on 4 to 6',
     'campaign_gnss/logs/rep_b_bnd_100', 'major axis  83.9 deg from the road'),
    ('3h8 subset c bound bottom',
     '**79.1 to 83.6** on 7 and 8',
     'campaign_gnss/logs/rep_c_bnd_000', 'major axis  79.1 deg from the road'),
    ('3h8 subset c seeds',
     'seeds 7 and 8. Both sweeps end to',
     'campaign_gnss/logs/rep_c_eff_000', '--tags seed7 seed8 --classes'),
    ('3h6 road 50 m',
     '| 50 m | 0.013 | **0.379** |',
     'campaign_gnss/logs/ac_attacker_road', '50 m       3.640     0.707       1.177      0.768         0.379'),
    ('3h6 road 100 m',
     '| 100 m | 0.056 | **0.860** |',
     'campaign_gnss/logs/ac_attacker_road', '100 m       4.853     0.945       1.587      0.932         0.860'),
    ('3h6 free 100 m',
     '| 100 m | 0.056 | **0.860** |',
     'campaign_gnss/logs/ac_attacker_free', '100 m       2.877     0.323       0.950      0.246         0.056'),
    ('3h6 road angle 50 m',
     '| 50 m | 80 deg | **20 deg** |',
     'campaign_gnss/logs/ac_attacker_road', '0.274          20.0'),
    ('3h6 honest outside 12 m',
     '**20.66 percent of benign',
     'campaign_gnss/logs/carriageway_share', '+/- 12.0 m           20.66 percent'),
    ('3h6 honest outside 18 m',
     '6.67 percent outside 15 m and',
     'campaign_gnss/logs/carriageway_share', '+/- 18.0 m            0.00 percent'),
    ('3h6 road18 50 m',
     '| 50 m | 30 deg | **0.230** |',
     'campaign_gnss/logs/ac_attacker_road18', '50 m       3.471     0.640       1.143      0.703         0.230'),
    ('3h6 road18 localisation',
     'widens from 17.9 m to 21.0 m',
     'campaign_gnss/logs/ac_attacker_road18', 'median 21.0 m, 90th 41.8 m'),
    ('3f control',
     '| **VeReMi, FIXED position (control)** | 400,000 | 2472 | 117,807 | **0.9688 +/- 0.0018** | **0.9562** |',
     'campaign_gnss/logs/veremi_control', 'F1 0.9688 +/- 0.0018  MCC 0.9562'),
    ('3f VeReMi offset',
     '| **VeReMi, constant OFFSET** | 400,000 | 2472 | 117,807 | **0.4961 +/- 0.0093** | **0.3659** |',
     'campaign_gnss/logs/veremi_offset', 'F1 0.4961 +/- 0.0093  MCC 0.3659'),
    ('3f corpus offset',
     '| **this corpus, constant OFFSET** | 312,624 | 579 | 31,930 | **0.0539 +/- 0.0222** | **0.0816** |',
     'campaign_gnss/logs/veremi_offset', '312,624 windows   579 stations    31,930 attack rows  F1 0.0539 +/- 0.0222  MCC 0.0816'),
    ('3f range importance',
     '`app_claimed_dist_mean`, 0.365 of total importance',
     'campaign_gnss/logs/veremi_offset', 'most important: app_claimed_dist_mean 0.365'),
    ('3f VeReMi claimed distance',
     "VeReMi's offset attackers claim a **median distance of 311.4 m from the",
     'campaign_gnss/logs/veremi_offset', 'median |app_claimed_dist_mean|: benign 164.8458, attack 311.4193'),
    ('3f corpus claimed distance',
     '**On this corpus the same feature carries nothing.** Attackers claim a median',
     'campaign_gnss/logs/veremi_offset', 'median |app_claimed_dist_mean|: benign 613.5534, attack 603.2576'),
    ('3f selftest',
     'builder produced from the same log: **all seventeen match across 218,782',
     'campaign_gnss/logs/veremi_selftest', '218,782 windows compared against corpus.pkl'),
    ('3f twin guard',
     'share 28 to 48 of 4,000',
     'campaign_gnss/logs/veremi_offset', 'twin check 1 and 3: 48 of 4000 benign positions shared'),
    ('3f2 control',
     '| NextGen randomPositionOffset, self-inconsistent (control) | **0.9570 +/- 0.0075** | 0.9478 |',
     'drift/logs/nextgen_rpo', 'F1 0.9570 +/- 0.0075  MCC 0.9478'),
    ('3f2 constant offset',
     '| NextGen constantPositionOffset, self-consistent | **0.1460 +/- 0.0254** | 0.1315 |',
     'drift/logs/nextgen_cpo', 'F1 0.1460 +/- 0.0254  MCC 0.1315'),
    ('3f2 this corpus',
     '| this corpus, constant offset | **0.0397 +/- 0.0389** | 0.0684 |',
     'drift/logs/nextgen_cpo', 'F1 0.0397 +/- 0.0389  MCC 0.0684'),
    ('3f2 receptions',
     'Highway scenario 2, test split, 476',
     'drift/logs/nextgen_cpo', '44,259 receptions from 476 receivers, 476 senders'),
    ('3f2 control dmv',
     '70.1895 m against 0.4939 m',
     'drift/logs/nextgen_rpo', 'median |app_dmv_mean|: benign 0.4939, attack 70.1895'),
    ('3f2 claimed distance',
     'claim a median 166.9 m from the receiver',
     'drift/logs/nextgen_cpo', 'median |app_claimed_dist_mean|: benign 152.4080, attack 166.8938'),
    ('3c light fused',
     '| light | **fused** | **0.3173 +/- 0.0039** | **0.4977 +/- 0.0180** | **-0.1804** |',
     'drift/logs/density_gnss', 'campaign_gnss    fused         0.3173 +/- 0.0039    0.4977 +/- 0.0180  -0.1804'),
    ('3c light app',
     '| light, 2.5 veh/km/lane | app-only | 0.3259 +/- 0.0080 | 0.4712 +/- 0.0161 | **-0.1453** |',
     'drift/logs/density_gnss', 'campaign_gnss    app-only      0.3259 +/- 0.0080    0.4712 +/- 0.0161  -0.1453'),
    ('3c light phy',
     '| light | phy-only | 0.1312 +/- 0.0074 | 0.3212 +/- 0.0269 | **-0.1900** |',
     'drift/logs/density_gnss', 'campaign_gnss    phy-only      0.1312 +/- 0.0074    0.3212 +/- 0.0269  -0.1900'),
    ('3c congested fused',
     '| congested | **fused** | **0.3414 +/- 0.0199** | **0.5037 +/- 0.0138** | **-0.1624** |',
     'drift/logs/density_gnss', 'campaign_dense_gnss fused         0.3414 +/- 0.0199    0.5037 +/- 0.0138  -0.1624'),
    ('3c congested app',
     '| congested, 20.0 veh/km/lane | app-only | 0.3609 +/- 0.0209 | 0.4780 +/- 0.0114 | **-0.1171** |',
     'drift/logs/density_gnss', 'campaign_dense_gnss app-only      0.3609 +/- 0.0209    0.4780 +/- 0.0114  -0.1171'),
    ('3c light fused per class',
     '| sybil | **0.473 / 0.859** | **0.116 / 0.782** |',
     'drift/logs/density_gnss', 'campaign_gnss    fused       0.651/0.897     0.070/0.147     0.982/0.985     0.044/0.100     0.270/0.600     0.473/0.859'),
    ('3c congested fused per class',
     '| dos_low_rate | **0.117 / 0.885** | 0.831 / 0.941 |',
     'drift/logs/density_gnss', 'campaign_dense_gnss fused       0.625/0.878     0.038/0.209     0.963/0.973     0.067/0.306     0.183/0.469     0.116/0.782     0.927/0.963     0.000/0.000     0.000/0.000     0.831/0.941'),
    ('3c training rows',
     '98,023 and 99,684 training rows per arm',
     'drift/logs/density_gnss', '99,684 training rows per arm'),
]

# Files whose contents must be no older than the artefact they describe. The
# separation table is computed FROM the pooled pickle, so a stale log beside a
# regenerated pickle quotes numbers that can no longer be reproduced, and no
# amount of string matching would notice.
FRESHNESS = [("campaign_gnss/logs/pool_separation.log", "campaign_gnss/pooled.pkl"),
             ("campaign_gnss/logs/pool_separation_road.log", "campaign_gnss/pooled_road.pkl")]

# Numbers that appear in BOTH the claims summary and the results file. The
# claims file is the one that gets read while writing, so it is the one most
# likely to be edited in isolation and left quietly disagreeing with the
# evidence it summarises. Each entry is a string that must appear in both.
CLAIMS_CONSISTENCY = [
    "0.131",          # single receiver, class 1
    "0.590",          # pooled consensus, class 1
    "0.412",          # pooled consensus, class 13, the band that decides
    "0.019",          # and the same class to one receiver
    "18.2",           # localisation error, which sets the detection floor
    "0.0156",         # FedLC over FedAvg on MCC, the pre-specified aggregate
    "7.16",           # permutation control, benign given a false claim
    "0.905",          # pooled AUC, unchanged under every power adversary
]

# Prose files the dash ban is enforced over, as repository relative paths.
# Every document that gets written by hand belongs here. METHODS_DRAFT.md in
# particular carries the standards prose, which is copied from sources that use
# em dashes freely, so it is the file most likely to acquire one.
STYLE_FILES = ["docs/RESULTS.md", "docs/MASTER_INDEX.md", "docs/BUILD_LOG_V2.md",
               "docs/PAPER_CLAIMS.md", "docs/METHODS_DRAFT.md",
               "docs/PAPER_DRAFT.md",
               "docs/DEFECTS_V2.md", "docs/PLAN_V3.md", "docs/RUNS_MANIFEST.md",
               "README.md", "analysis/README.md", "simulation/README.md"]


def check_log_freshness(bad):
    """Fail any pin whose log is older than the corpus it analyses.

    A pin checks that its string is still in its log. A log the latest rerun
    did not regenerate still holds its old string, so the pin passes on a
    figure the current corpus never produced, and after a corpus rebuild that
    reads as verified when it is stale. A log under campaign_X/logs must be
    newer than campaign_X/corpus.pkl; any other log, the drift and loose ones,
    newer than the reference corpus, which every one of them reads.
    """
    ref = RUNS / "campaign_gnss" / "corpus.pkl"
    stale = []
    for stem in sorted({c[2] for c in CHECKS if c[2]}):
        log = RUNS / f"{stem}.log"
        if not log.exists():
            continue
        corpus = (RUNS / stem.split("/logs/")[0] / "corpus.pkl"
                  if stem.startswith("campaign_") and "/logs/" in stem else ref)
        if corpus.exists() and log.stat().st_mtime < corpus.stat().st_mtime:
            stale.append(stem)
    ok = not stale
    print(f"{'ok  ' if ok else 'FAIL'} log freshness: {len(stale)} pinned log(s) "
          f"older than the corpus they analyse"
          + ("" if ok else ", e.g. " + ", ".join(stale[:4])))
    return bad + (not ok)


def check_references(bad):
    """Every run log, data artefact and script the documents cite must exist.

    Documents accumulate references faster than the things they point at get
    kept, and a citation to a log that was overwritten or a script that was
    renamed is invisible until someone tries to follow it.
    """
    import re
    docs = [f for f in DOC.parent.glob("*.md")]
    text = "\n".join(f.read_text() for f in docs)
    repo = DOC.parent.parent
    bad_refs = []
    for m in sorted(set(re.findall(r"runs/[a-z0-9_]+(?:/[a-z0-9_]+){0,2}\.(?:log|pkl)", text))):
        if not (RUNS.parent / m).exists():
            bad_refs.append(m)
    for m in sorted(set(re.findall(r"analysis/[a-z_]+\.(?:py|sh)", text))):
        if not (repo / m).exists():
            bad_refs.append(m)
    ok = not bad_refs
    bad += len(bad_refs)
    if ok:
        print("ok   references: every cited log, artefact and script exists")
    else:
        for r in bad_refs:
            print(f"FAIL reference does not exist: {r}")
    return bad


def check_script_count(bad):
    """The README says how many scripts analysis/ holds. Count them.

    Same drift as the figure count, which sat twenty out of date. A number in the
    README that is maintained by remembering to update it is a number that will
    be wrong, and this one moves every time a script is added.
    """
    here = pathlib.Path(__file__).resolve().parent
    n = len(list(here.glob("*.py"))) + len(list(here.glob("*.sh")))
    readme = here.parent / "README.md"
    want = f"{n} scripts"
    if want not in readme.read_text():
        print(f"FAIL script count              <- analysis/ holds {n} scripts "
              f"and README.md does not say so")
        return bad + 1
    print(f"ok   script count: analysis/ holds {n} scripts")
    return bad


def check_no_tool_urls(bad):
    """Nothing published may point at the URL of a tool that helped build it.

    The poster's QR code once pointed at a session-scoped URL from an assistant
    that had helped draft it. On an A0 sheet that is printed weeks ahead, a link
    that belongs to a tool rather than to the project is a dead link by the time
    anyone scans it, and it cannot be fixed on the day. The project's own domains
    are the only acceptable destinations.
    """
    import subprocess
    root = pathlib.Path(__file__).resolve().parent.parent
    banned = ("claude.ai", "chat.openai.com", "chatgpt.com",
              "gemini.google.com", "copilot.microsoft.com")
    try:
        tracked = subprocess.run(["git", "ls-files"], cwd=root, check=True,
                                 capture_output=True, text=True).stdout.split()
    except Exception as e:
        print(f"FAIL no tool URLs published    <- git ls-files failed: {e}")
        return bad + 1
    hits = []
    for f in tracked:
        if f == "analysis/verify_results.py":
            continue          # this file names them in order to forbid them
        try:
            text = (root / f).read_text()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for host in banned:
            if host in text:
                hits.append(f"{f} points at {host}")
    for h in hits:
        print(f"FAIL no tool URLs published    <- {h}")
    if hits:
        return bad + 1
    print(f"ok   no tool URLs published: {len(tracked)} tracked files clean")
    return bad


def check_geometry_span(bad):
    """The README quotes the receiver array's span. Recompute it from the source.

    Every other figure in the README is pinned to a run log. This one is not,
    because it is computed inside `make_figures.py` and printed onto the figure
    rather than written to a log. A number in the most-read document in the
    repository that nothing checks is exactly the drift this file exists to stop,
    so it is recomputed here from the same file the figure is drawn from.
    """
    import json
    src = pathlib.Path.home() / "ns3-v2x/runs/campaign_gnss/booth_surface.json"
    readme = pathlib.Path(__file__).resolve().parent.parent / "README.md"
    if not src.exists():
        print("ok   geometry span: source absent, not checked")
        return bad
    d = json.loads(src.read_text())
    tx, ty = d["true_position"]["x"], d["true_position"]["y"]
    xs = [r["x"] - tx for r in d["receivers"]]
    ys = [r["y"] - ty for r in d["receivers"]]
    along, across = max(xs) - min(xs), max(ys) - min(ys)
    want = f"{along:,.0f} m along the road and {across:.0f} m across it"
    if want not in readme.read_text():
        print(f"FAIL geometry span             <- README.md does not say "
              f"'{want}'")
        return bad + 1
    print(f"ok   geometry span: {want}")
    return bad


def check_public_refs(bad):
    """No published document may cite a document that is not published.

    Most of this project's writing is deliberately unpublished: the results, the
    defect analysis, the plans. That is fine until a file a stranger CAN open
    cites one they cannot, at which point the repository is quietly full of dead
    references that every check here passes, because the files exist on this
    machine. The reader is the one who finds out.
    """
    import subprocess
    root = pathlib.Path(__file__).resolve().parent.parent
    try:
        tracked = set(subprocess.run(["git", "ls-files"], cwd=root, check=True,
                                     capture_output=True, text=True
                                     ).stdout.split())
    except Exception as e:
        print(f"FAIL public references        <- git ls-files failed: {e}")
        return bad + 1
    docs = sorted(f for f in tracked if f.endswith(".md"))
    names = {pathlib.PurePath(f).name: f for f in tracked}
    problems = []
    for d in docs:
        text = (root / d).read_text()
        for m in re.finditer(r"[A-Za-z0-9_./-]*[A-Za-z0-9_-]+\.(?:md|py|csv|cff|json)",
                             text):
            ref = m.group(0)
            base = pathlib.PurePath(ref).name
            # a reference resolves if the path is tracked, or the bare filename
            # names a tracked file, or nothing by that name exists here at all
            # (an external work, a file inside the published data bundle)
            if ref in tracked or base in names:
                continue
            if not (root / ref).exists() and not list(root.rglob(base)):
                continue
            problems.append(f"{d} cites {ref}, which is not published")
    for pr in problems:
        print(f"FAIL public references        <- {pr}")
    if problems:
        return bad + 1
    print(f"ok   public references: {len(docs)} published documents cite "
          f"nothing unpublished")
    return bad


def check_selfcount(total, bad):
    """The root README quotes how many figures this script checks. Keep it true.

    That number is a credential: it tells a reader the results were pinned to
    their logs rather than transcribed. It went stale once, sitting at 134 while
    the real total was 146, which is exactly the kind of drift the rest of this
    file exists to catch. A count nobody checks is a count that rots.
    """
    import re
    readme = pathlib.Path(__file__).resolve().parent.parent / "README.md"
    if not readme.exists():
        print("FAIL readme figure count       <- README.md not found")
        return bad + 1
    m = re.search(r"which checks (\d+) figures", readme.read_text())
    if m is None:
        print("FAIL readme figure count       <- no 'which checks N figures' "
              "sentence in README.md")
        return bad + 1
    claimed = int(m.group(1))
    if claimed != total:
        print(f"FAIL readme figure count       <- README.md says {claimed}, "
              f"this script runs {total}")
        return bad + 1
    print(f"ok   readme figure count: README.md says {claimed}")
    return bad


def check_readme(bad):
    """Every script in analysis/ must appear in its README, and vice versa.

    A script that nobody documents is a script nobody finds, and a README row
    for something that has been renamed sends a reader looking for a file that
    is not there.
    """
    here = pathlib.Path(__file__).resolve().parent
    readme = here / "README.md"
    if not readme.exists():
        return bad
    text = readme.read_text()
    problems = []
    for f in sorted(list(here.glob("*.py")) + list(here.glob("*.sh"))):
        if f"`{f.name}`" not in text:
            problems.append(f"{f.name} is not documented in analysis/README.md")
    import re
    for name in sorted(set(re.findall(r"`([a-z_]+\.(?:py|sh))`", text))):
        if not (here / name).exists():
            problems.append(f"analysis/README.md documents {name}, which does not exist")
    bad += len(problems)
    if problems:
        for pr in problems:
            print(f"FAIL {pr}")
    else:
        print("ok   readme: every script documented, every documented script present")
    return bad


def check_claims(bad):
    """The claims summary must not drift from the results it summarises.

    The paper draft is checked against the same tokens, because it is the file
    that gets read while writing and therefore the one most likely to acquire a
    remembered number instead of a measured one.
    """
    claims = DOC.parent / "PAPER_CLAIMS.md"
    draft = DOC.parent / "PAPER_DRAFT.md"
    if not claims.exists():
        return bad
    ctext, rtext = claims.read_text(), DOC.read_text()
    if draft.exists():
        dtext = draft.read_text()
        for token in ["0.5145", "0.412", "0.0578", "18.2"]:
            ok = token in dtext and token in rtext
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} draft agrees on {token:8s}"
                  f"{'' if ok else '  <- missing from PAPER_DRAFT.md'}")
    for token in CLAIMS_CONSISTENCY:
        ok = token in ctext and token in rtext
        bad += not ok
        where = ("missing from PAPER_CLAIMS.md" if token not in ctext
                 else "missing from RESULTS.md")
        print(f"{'ok  ' if ok else 'FAIL'} claims agree on {token:8s}"
              f"{'' if ok else '  <- ' + where}")
    return bad


def check_style(bad):
    r"""Em and en dashes are banned in this project's prose.

    This is automated because the shell one-liner used to check it by hand,
    `grep -c $'\u2014\|\u2013'`, matches nothing at all and reported a clean
    zero for files that were full of them. A check that cannot fail is worse
    than no check.
    """
    repo = DOC.parent.parent
    for name in STYLE_FILES:
        f = repo / name
        if not f.exists():
            continue
        text = f.read_text()
        n = sum(text.count(c) for c in "\u2014\u2013")
        ok = n == 0
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} style: {name:26s}"
              f"{'' if ok else f'  <- {n} em or en dashes'}")
    return bad


def check_doc_commands(bad):
    """Every command a published document tells a stranger to run must exist.

    The reproducibility instructions have never been executed by the audience
    they address, so the only thing standing between them and a dead command is
    that nobody renamed a script. Somebody will. This does not prove the
    instructions work; it proves they still point at something, which is the
    half that can be checked from here.
    """
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    docs = ("REPRODUCING.md", "USING_THE_DATA.md", "HANDOFF.md", "README.md")
    missing, seen = [], 0
    for name in docs:
        f = root / name
        if not f.exists():
            missing.append(f"{name} is referenced by this check and does not exist")
            continue
        for c in re.findall(r"^\s{4}(?:python3?\s+|\./)(\S+\.(?:py|sh))", f.read_text(), re.M):
            seen += 1
            stem = pathlib.PurePath(c).name
            if not ((root / c).exists() or (root / "analysis" / stem).exists()):
                missing.append(f"{name} runs {c}, which does not exist")
    for m in missing:
        print(f"FAIL doc commands            <- {m}")
    if not missing:
        print(f"ok   doc commands             {seen} documented commands all resolve")
    return bad + len(missing)


# The AT2 methodology pack transcribes about thirty figures out of RESULTS.md,
# the dataset card and the README so a writer does not have to look each one up.
# That makes it the one document in the project where a stale number can live:
# it is gitignored, so the published-reference check never sees it, and nothing
# pins what it quotes. The figure count alone moved four times in one session.
# Each pair below is (the string as the pack writes it, the file it came from).
PACK_FIGURES = [
    # (what the pack says, what the source says, the source). The two differ
    # where the source words it differently; prose wraps, so both sides are
    # compared with whitespace collapsed.
    ("0.3466", "0.3466", "README.md"),
    ("0.5145", "0.5145", "README.md"),
    ("0.5659", "0.5659", "README.md"),
    ("4.02 m", "4.02 m", "README.md"),
    ("96.39 percent", "96.39 percent", "README.md"),
    ("16,150", "16,150", "README.md"),
    ("2,414", "2,414", "README.md"),
    ("720 physical transmitters", "720 physical transmitters", "docs/DATASET_CARD.md"),
    ("783 claimed identities", "| 783,", "docs/DATASET_CARD.md"),
    ("61 columns", "| 61, being 22 application layer", "docs/DATASET_CARD.md"),
    ("47.2 m", "47.2 m", "docs/RESULTS.md"),
    ("39.3 to 57.4 m", "39.3 to 57.4 m", "docs/RESULTS.md"),
    ("0.5145 +/- 0.0016", "0.5145 +/- 0.0016", "docs/RESULTS.md"),
    ("6.53 +/- 0.70", "6.53 +/- 0.70", "docs/RESULTS.md"),
    ("30.45 +/- 6.93", "30.45 +/- 6.93", "docs/RESULTS.md"),
]


def _flat(s):
    return re.sub(r"\s+", " ", s)


def check_pack(bad):
    """Every figure the AT2 pack transcribes must still say that in its source."""
    root = pathlib.Path(__file__).resolve().parent.parent
    targets = [root / "docs" / n for n in
               ("AT2_SECTION3_PACK.md", "AT2_METHODOLOGY_DRAFT.md")]
    present = [f for f in targets if f.exists()]
    if not present:
        print("ok   AT2 pack                  not present, nothing to check")
        return bad
    # A figure need only appear in one of the AT2 documents; both restate
    # numbers out of the same sources, and the draft quotes a subset.
    text = " ".join(_flat(f.read_text()) for f in present)
    cache, problems, checked = {}, [], 0
    for mine, theirs, src in PACK_FIGURES:
        if _flat(mine) not in text:
            problems.append(f"no AT2 document quotes {mine!r}; drop it from PACK_FIGURES")
            continue
        if src not in cache:
            f = root / src
            cache[src] = _flat(f.read_text()) if f.exists() else None
        body = cache[src]
        if body is None:
            problems.append(f"{src} is missing, so {mine!r} cannot be checked")
        elif _flat(theirs) not in body:
            problems.append(f"AT2 quotes {mine!r} but {src} no longer says {theirs!r}")
        else:
            checked += 1
    for m in problems:
        print(f"FAIL AT2 pack                 <- {m}")
    if not problems:
        print(f"ok   AT2 documents            {checked} transcribed figures match their sources, "
              f"across {len(present)} document(s)")
    return bad + len(problems)


def main():
    doc = DOC.read_text()
    cache, bad = {}, 0
    bad = check_style(bad)
    bad = check_claims(bad)
    bad = check_references(bad)
    bad = check_readme(bad)
    bad = check_log_freshness(bad)
    for log_name, artefact in FRESHNESS:
        lg, ar = RUNS / log_name, RUNS / artefact
        if lg.exists() and ar.exists():
            ok = lg.stat().st_mtime >= ar.stat().st_mtime
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} freshness: {log_name:26s}"
                  f"{'' if ok else f'  <- older than {artefact}, regenerate it'}")
    for label, in_doc, stem, in_log in CHECKS:
        if stem is None:                       # doc-only entry, no log to pin
            ok = in_doc in doc
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {label:26s}"
                  f"{'' if ok else '  <- missing from RESULTS.md'}")
            continue
        if stem not in cache:
            path = RUNS / f"{stem}.log"
            cache[stem] = path.read_text() if path.exists() else None
        log = cache[stem]
        d = in_doc in doc
        l = (in_log in log) if log is not None else False
        ok = d and l
        bad += not ok
        why = "" if ok else ("  <- missing from RESULTS.md" if not d else
                             f"  <- missing from runs/{stem}.log"
                             if log is not None else
                             f"  <- runs/{stem}.log not found")
        print(f"{'ok  ' if ok else 'FAIL'} {label:26s}{why}")
    total = (len(CHECKS) + len(FRESHNESS) + len(STYLE_FILES)
             + len(CLAIMS_CONSISTENCY) + 8)   # refs, readme, freshness, count, public, span, urls, scripts
    bad = check_script_count(bad)
    bad = check_no_tool_urls(bad)
    bad = check_geometry_span(bad)
    bad = check_public_refs(bad)
    bad = check_doc_commands(bad)
    bad = check_pack(bad)
    bad = check_selfcount(total, bad)
    print(f"\n{total - bad}/{total} verified")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
