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
import pathlib
import sys

DOC = pathlib.Path(__file__).resolve().parent.parent / "docs" / "RESULTS.md"
RUNS = pathlib.Path.home() / "ns3-v2x" / "runs"

# label, exact string in RESULTS.md, log stem, exact string in that log
CHECKS = [
    # campaign_v3 is the corpus. Its logs live under campaign_v3/logs/.
    # 3g, the floor under four learner families rather than one
    ("model independence forest reproduces",
     "| random forest | **0.5145 +/- 0.0016** | 0.6635 |",
     "campaign_gnss/logs/model_independence",
     "random forest            macro F1 0.5145 +/- 0.0016   MCC 0.6635"),
    ("model independence best of four",
     "| 13 pos_medium_offset, 47 to 60 m | 0.021 | 0.025 | 0.052 | 0.000 | **0.052** |",
     "campaign_gnss/logs/model_independence",
     "class 11 0.010, class 13 0.052, class 1 0.167"),
    # 3h, the bound from geometry with no classifier involved
    ("geometry law fitted",
     "path loss exponent **2.466**, residual **3.821 dB**",
     "campaign_gnss/logs/geometry_bound", "path loss exponent n      2.466"),
    ("geometry ellipse angle",
     "| **50th** | **38.7 m** | **8.2 m** | **79.3 deg** |",
     "campaign_gnss/logs/geometry_bound",
     "major axis  79.3 deg from the road"),
    ("geometry free fit across road",
     "| free fit, across-road standard deviation | 36.4 m | |",
     "campaign_gnss/logs/geometry_bound", "across the road                36.4 m"),
    ("geometry median radial, like for like",
     "| **free fit, median radial error** | **28.0 m** | **65.2 m** |",
     "campaign_gnss/logs/geometry_bound",
     "median radial error of an efficient estimator      28.0 m"),
    ("geometry road constrained",
     "| road constrained, along-road standard deviation | 9.2 m | |",
     "campaign_gnss/logs/geometry_bound", "along the road                  9.2 m"),
    ("geometry persistent floor",
     "| median, 615 m | **83.2 m** |",
     "campaign_gnss/logs/geometry_bound", "615.3 m            83.2 m"),
    ("geometry region scale",
     "| one region | 8 | 6,211 m | 3,900 m |",
     "campaign_gnss/logs/geometry_bound_regions",
     "across the road              6211.7 m"),
    # 3i, against the field's standard checks
    ("baseline suite against learned",
     "| **learned, 50 features** | **0.682** | 0.963 | 0.532 | **0.644** |",
     "campaign_gnss/logs/plausibility_baseline",
     "learned, 50 features          0.682      0.963    0.532    0.644"),
    ("baseline suite blind to offsets",
     "| suite, any check fires | 0.040 |",
     "campaign_gnss/logs/plausibility_baseline", "suite                         0.040"),
    ("geometry placement optimum",
     "| **40 m** | **29.6 m** | 12.4 m | **2.38** |",
     "campaign_gnss/logs/geometry_placement",
     "40m        29.6 m       12.4 m          77.9 deg        2.38"),
    ("geometry placement worse than nothing",
     "| 200 m | 40.2 m | 12.8 m | 3.13 |",
     "campaign_gnss/logs/geometry_placement",
     "200m        40.2 m       12.8 m          79.7 deg        3.13"),
    ("benchmark ten live classes",
     "| **fused** | **0.5145 +/- 0.0016** | **0.5659 +/- 0.0018** |",
     "campaign_gnss/logs/benchmark", "fused      0.5659 +/- 0.0018"),
    # 5d, does federating across densities recover the shift
    ("federated drift in-distribution",
     "| **trained on the target density** | 494 | 207,338 | **0.2966 +/- 0.0046** | **0.4246** |",
     "drift/logs/federated_drift_dense",
     "in-dist       494 clients  207,338 rows   macro F1 0.2966 +/- 0.0046"),
    ("federated drift mixed is worse",
     "| federated across both | 1179 | 209,345 | 0.1305 +/- 0.0285 | 0.1685 |",
     "drift/logs/federated_drift_dense",
     "mixed        1179 clients  209,345 rows   macro F1 0.1305 +/- 0.0285"),
    ("federated drift double data",
     "| federated across both, twice the rows | 1179 | 419,253 | 0.2243 +/- 0.0116 | 0.3398 |",
     "drift/logs/federated_drift_dense",
     "mixed-2x     1179 clients  419,253 rows   macro F1 0.2243 +/- 0.0116"),
    # 3b2, the floor located from a campaign built to sample the transition
    ("floor crossing",
     "> **50 percent detection at 47.2 m, 95 percent interval 39.3 to 57.4 m**",
     "campaign_floor/logs/offset_floor_located",
     "50 percent detection at     47.2 m"),
    ("floor transition band",
     "| **30 to 50 m** | **11** | **0.36** |",
     "campaign_floor/logs/offset_floor_located",
     "30 to 50 m        11       627      0.384     0.36"),
    ("floor same operating point",
     "Benign false flag rate on the pooled arm is **0.0102**",
     "campaign_floor/logs/offset_floor_located",
     "benign stations 393, false flag rate 0.0102"),
    # 3c2, does the cooperative architecture survive the shift
    ("pooled drift into light traffic",
     "| **into light traffic** | **pooled fused** | **0.4193 +/- 0.0204** | **0.6274 +/- 0.0121** | **-0.2081** |",
     "drift/logs/density_pooled",
     "campaign_gnss    pooled fused    0.4193 +/- 0.0204    0.6274 +/- 0.0121  -0.2081"),
    ("pooled drift into congestion",
     "| **into congestion** | **pooled fused** | **0.3063 +/- 0.0104** | **0.6711 +/- 0.0174** | **-0.3648** |",
     "drift/logs/density_pooled",
     "campaign_dense_gnss pooled fused    0.3063 +/- 0.0104    0.6711 +/- 0.0174  -0.3648"),
    ("floor clustered check",
     "whole seeds instead gives **40.7 to 53.6 m**",
     "campaign_floor/logs/offset_floor_located",
     "95 percent interval      40.7 to 53.6 m"),
    ("gates 1-NN", "| 1-NN macro F1 | **0.3466** | 1.0000 |",
     "campaign_gnss/logs/validate", "1-NN triviality: macro F1 0.3466"),
    ("gates single feature",
     "| best single-feature separation | **0.0686** | perfect for 9 of 11 classes |",
     "campaign_gnss/logs/validate", "best single feature excludes 0.0686"),
    ("corpus size", "| windows | 1,641,002 |",
     "campaign_gnss/logs/merge", "merged: 1641002 windows, 720 stations, 8 seeds"),
    ("benchmark fused",
     "| **fused** | 50 | **0.5145 +/- 0.0016** | **0.8495** | **0.6635** |",
     "campaign_gnss/logs/benchmark", "fused            50  0.5145"),
    ("benchmark class 1 app blind",
     "| 1 pos_const_offset, 71 to 233 m | **0.000** | **0.156** | 0.146 |",
     "campaign_gnss/logs/benchmark", "     1         0.000         0.156         0.146"),
    ("benchmark speed negative control",
     "| 5 speed_falsify | **0.657** | **0.000** | 0.633 |",
     "campaign_gnss/logs/benchmark", "     5         0.657         0.000         0.633"),
    ("benchmark medium offset is new and blind",
     "| 13 pos_medium_offset, 47 to 60 m | **0.000** | 0.029 | 0.021 |",
     "campaign_gnss/logs/benchmark", "    13         0.000         0.029         0.021"),
    ("pooling receivers", "**median 39 receivers per unit**,\nminimum 5, maximum 67",
     "campaign_gnss/logs/pooled_road", "observers per unit: median 39, min 5, max 67"),
    ("localisation benign", "| benign | 0.0 | **18.2** | **18.9** |",
     "campaign_gnss/logs/pooled_road", "median    18.2 m"),
    ("road constraint on the corpus",
     "benign estimates 65.2 m from the truth against 18.2 m here, a factor of 3.6",
     "campaign_gnss/logs/pooled", "median    65.2 m"),
    ("localisation class 1", "| 1 pos_const_offset | 140.8 | **18.7** | **140.1** |",
     "campaign_gnss/logs/pooled_road",
     "estimate to claim   140.1 m,  estimate to true    18.7 m"),
    ("localisation class 13",
     "| 13 pos_medium_offset | 70.2 | **17.8** | **70.1** |",
     "campaign_gnss/logs/pooled_road",
     "estimate to claim    70.1 m,  estimate to true    17.8 m"),
    ("pooled-consensus arm",
     "| **pooled-consensus** | **0.6279 +/- 0.0202** | **+0.1280** | **0.7673** | "
     "**0.590** | **0.412** | **0.382** |",
     "campaign_gnss/logs/pooled_road",
     "pooled-consensus   0.6279 +/- 0.0202     +0.1280"),
    ("medium offset recovered by pooling",
     "Class 1 goes from 0.131 to 0.590, class 13 from 0.019 to 0.412",
     "campaign_gnss/logs/pooled_road",
     "class 13: single 0.019 -> consensus 0.412 (+0.393)"),
    ("single receiver arm",
     "| single receiver | 0.4999 +/- 0.0178 | | 0.6798 | 0.131 | 0.019 | 0.109 |",
     "campaign_gnss/logs/pooled_road", "single             0.4999 +/- 0.0178"),
    ("soft vote recovers nothing",
     "| vote, soft | 0.5006 +/- 0.0162 | +0.0007 | 0.7044 | **0.000** | **0.000** | 0.096 |",
     "campaign_gnss/logs/pooled_road", "vote-soft          0.5006 +/- 0.0162     +0.0007"),
    ("consensus separation",
     "`pool_rmse_ratio` reaches +6.06 benign\nstandard deviations on constant-offset falsification and +2.93 on the random\noffset",
     "campaign_gnss/logs/pool_separation_road",
     "pool_rmse_ratio                6.06    1.56    2.93"),
    ("consensus separation table",
     "| `pool_rmse_ratio` | **6.06** | 1.56 | 2.93 | 0.02 | 0.78 | 0.30 | 0.01 | 0.01 | 0.18 | **2.25** |",
     "campaign_gnss/logs/pool_separation_road",
     "pool_rmse_ratio                6.06    1.56    2.93    0.02    0.78    0.30    0.01    0.01    0.18    2.25"),
    ("permutation control",
     "| **benign, claim permuted** | **1769.0 m** | **9.90 dB** | **7.16** | **0.109** |",
     "campaign_gnss/logs/claim_permutation",
     "benign, claim permuted              29574        9.90            7.16     0.109     1769.0 m"),
    ("power evasion class 1", "| 1 | power-targeted | **0.500** | **0.905** |",
     "campaign_gnss/logs/power_evasion",
     "     1 power-targeted             0.500             0.905"),
    ("power evasion class 13 invariant",
     "| 13 | power-targeted | **0.500** | **0.784** |",
     "campaign_gnss/logs/power_evasion",
     "    13 power-targeted             0.500             0.784"),
    ("power evasion class 4", "| 4 pos_replay | none | 0.561 | 0.835 |",
     "campaign_gnss/logs/power_evasion", "4       none             0.561             0.835"),
    ("power evasion class 6", "| 6 sybil | none | 0.561 | 0.600 |",
     "campaign_gnss/logs/power_evasion", "6       none             0.561             0.600"),
    ("consensus block matters at 39 receivers",
     "takes macro F1 from 0.5945 to 0.6279**, a gain of 0.0334, thirteen times the",
     "campaign_gnss/logs/pooled_road", "pooled-mean        0.5945 +/- 0.0167"),
    ("consensus importance share",
     "The block holds 0.149 of total feature importance",
     "campaign_gnss/logs/pooled_road",
     "consensus block: 11 of 61 features, 0.149 of total importance"),
    ("privacy costs three times the architecture gain",
     "| 3.00 | **0.3063 +/- 0.0196** | **-0.1712** | **8.3** | **0.3505** |",
     "campaign_gnss/logs/dp_sweep", "3.00 0.3063 +/- 0.0196   -0.1712        8.3"),
    ("clipping alone is not free",
     "| 0.00, clipping only | 0.4434 +/- 0.0018 | **-0.0341** | no noise | 0.5750 |",
     "campaign_gnss/logs/dp_sweep", "0.00 0.4434 +/- 0.0018   -0.0341"),
    ("region pooling gain over one receiver",
     "| **pooled, with it** | **0.4775 +/- 0.0063** | **+0.0578** | **8 of 8** | **0.0078** |",
     "campaign_gnss/logs/federated_regions_single",
     "fedavg    macro F1 0.4197 +/- 0.0049"),
    ("region panel FedAvg baseline",
     "| FedAvg | 0.4775 +/- 0.0063 | | | 0.5991 | | |",
     "campaign_gnss/logs/federated_regions",
     "fedavg    macro F1 0.4775 +/- 0.0063"),
    ("consensus block no longer earns its place",
     "| the consensus block, on top of pooling | **+0.0025** | 6 of 8 | **0.1953** |",
     "campaign_gnss/logs/federated_regions_nocons",
     "fedavg    macro F1 0.4750 +/- 0.0063"),
    ("persistence no longer reaches zero",
     "| **5/7** | **10** | **7** | **0.540** | **0.008** |",
     "campaign_gnss/logs/persistence",
     "   5/7                    10                    7            0.540           0.008"),
    ("persistence 2 of 3 now alerts",
     "| 2/3 | 129 | 85 | 0.632 | 0.086 |",
     "campaign_gnss/logs/persistence",
     "   2/3                   129                   85            0.632           0.086"),
    ("persistence follows the magnitude ladder",
     "| **13 pos_medium_offset, 47 to 60 m** | 48 | **0.458** |",
     "campaign_gnss/logs/persistence", "    13       48    0.458"),
    ("pooling cost", "| both | **0.4054** |",
     "campaign_gnss/logs/pooling_cost",
     "both                                               0.4054"),
    ("federated FedAvg",
     "| FedAvg | 0.2014 +/- 0.0312 | | | 0.2964 +/- 0.0207 | | |",
     "campaign_gnss/logs/federated", "fedavg    macro F1 0.2014 +/- 0.0312"),
    ("federated FedLC splits the aggregates",
     "| **FedLC** | 0.2059 +/- 0.0340 | **+0.0044** | **0.0547** | "
     "**0.3041 +/- 0.0247** | **+0.0078** | **0.0156** |",
     "campaign_gnss/logs/federated", "fedlc     delta +0.0044  p = 0.0547"),
    ("federated FedLC significant on MCC",
     "significant on the Matthews correlation at p = 0.0156 and not on macro F1 at\np = 0.0547",
     "campaign_gnss/logs/federated",
     "fedlc     MCC delta +0.0078  p = 0.0156  significant"),
    ("federated FedNova no longer worse",
     "| FedNova | 0.2024 +/- 0.0317 | +0.0010 | 0.0679 | 0.2976 +/- 0.0214 | +0.0013 | 0.0679 |",
     "campaign_gnss/logs/federated", "fednova   delta +0.0010  p = 0.0679"),
    ("partition skew", "mean total variation from the pooled distribution 0.126",
     "campaign_gnss/logs/skew", "mean total variation from the pooled distribution: 0.126"),
    ("deployment at 0.90",
     "| 0.90 | 0.0005 | 0.471 | 0.998 | **161** | 0.6101 |",
     "campaign_gnss/logs/deployment", "0.90   0.0005   0.4706"),
    ("deployment MCC peaks at a useless threshold",
     "| 0.70 | 0.0228 | 0.562 | 0.923 | 7,316 | **0.6329** |",
     "campaign_gnss/logs/deployment", "0.70   0.0228   0.5617"),
    ("latency", "single-window inference    3.390 ms",
     "campaign_gnss/logs/latency", "single-window inference      3.390 ms"),
    ("cross dataset positive control",
     "| **VeReMi, FIXED position (control)** | 214,247 | 2,509 | 35,952 | "
     "**0.9644 +/- 0.0014** | **0.9575** |",
     "drift/logs/veremi_crossdataset",
     "VeReMi, FIXED position (control)     214,247 windows  2509 stations    "
     "35,952 attack rows  F1 0.9644 +/- 0.0014  MCC 0.9575"),
    ("cross dataset VeReMi offset partly detectable",
     "| **VeReMi, constant OFFSET** | 214,048 | 2,509 | 35,753 | "
     "**0.3382 +/- 0.0071** | **0.3149** |",
     "drift/logs/veremi_crossdataset",
     "VeReMi, constant OFFSET              214,048 windows  2509 stations    "
     "35,753 attack rows  F1 0.3382 +/- 0.0071  MCC 0.3149"),
    ("cross dataset ours near zero",
     "| **this corpus, constant OFFSET** | 195,359 | 579 | 19,934 | "
     "**0.0290 +/- 0.0194** | **0.0496** |",
     "drift/logs/veremi_crossdataset",
     "this corpus, constant OFFSET         195,359 windows   579 stations    "
     "19,934 attack rows  F1 0.0290 +/- 0.0194  MCC 0.0496"),
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
    ("floor pooled crosses at 50 to 80 m",
     "| 50 to 80 m | 21 | 0.00 | **0.90** |",
     "campaign_gnss/logs/offset_floor_full",
     "          50 to 80 m        21     1,197      0.838     0.90"),
    ("floor single observer never crosses",
     "| over 150 m | 8 | **0.00** | **1.00** |",
     "campaign_gnss/logs/offset_floor_full",
     "          over 150 m         8    16,678      0.198     0.00"),
    ("floor below 30 m nothing works",
     "| 15 to 30 m | 10 | 0.00 | 0.00 |",
     "campaign_gnss/logs/offset_floor_full",
     "          15 to 30 m        10       568      0.058     0.00"),
    ("collusion needs twenty receivers",
     "| a half | 20 | 13 |", None, None),
    ("adversary defeats the check off road",
     "| 50 m | **1.011** | **0.139** | **0.003** | 80 deg | +10.6 m |",
     "drift/logs/br_gnss_free",
     "        50 m       2.891     0.309       1.011      0.139         0.003"),
    ("adversary used the whole corpus",
     "**29,574 benign\ntriples**, the whole corpus",
     "drift/logs/br_gnss_free",
     "29,574 triples, 72 directions searched per displacement."),
    ("adversary budget is the localisation error",
     "**Free-fit localisation error is 65.2 m unconstrained and 18.3 m bounded to the\ncarriageway.**",
     "drift/logs/br_gnss_free",
     "free-fit localisation error on these benign triples: median 65.2 m"),
    ("on road adversary is caught",
     "| 100 m | 1.698 | **0.940** | **0.818** | 5 deg |",
     "drift/logs/br_gnss_onroad",
     "       100 m       4.905     0.915       1.698      0.940         0.818"),
    ("road constraint cuts localisation error",
     "**Localisation error falls from 65.2 m to 18.3 m**",
     "drift/logs/br_gnss_both",
     "free-fit localisation error on these benign triples: median 18.3 m"),
    ("road constraint lifts detection at the floor",
     "| 50 m | 0.264 | **0.380** | **0.764** |",
     "drift/logs/br_gnss_both",
     "        50 m       3.700     0.687       1.162      0.764         0.380"),
    ("ratio goes below one off road",
     "the ratio goes **below** one: 0.952 at 50 m.",
     "drift/logs/br_gnss_roadest",
     "        50 m       2.891     0.309       0.952      0.141         0.011"),
    # Drift. These live under runs/drift/logs because drift.py reads several
    # corpora at once and has no single run directory to write into.
    ("drift fused into light traffic",
     "| light | **fused** | **0.3543 +/- 0.0020** | **0.5086 +/- 0.0170** | "
     "**-0.1543** | **0.3120** | **0.6578** |",
     "drift/logs/density_gnss",
     "campaign_gnss    fused         0.3543 +/- 0.0020    0.5086 +/- 0.0170  -0.1543"),
    ("drift fused into congestion",
     "| congested | **fused** | **0.3898 +/- 0.0254** | **0.5119 +/- 0.0165** | "
     "**-0.1222** | **0.4103** | **0.5956** |",
     "drift/logs/density_gnss",
     "campaign_dense_gnss fused         0.3898 +/- 0.0254    0.5119 +/- 0.0165  -0.1222"),
    ("drift radio degrades least",
     "| congested | phy-only | 0.2724 +/- 0.0154 | 0.3442 +/- 0.0101 | **-0.0718** |",
     "drift/logs/density_gnss",
     "campaign_dense_gnss phy-only      0.2724 +/- 0.0154    0.3442 +/- 0.0101  -0.0718"),
    ("drift benign false alarms",
     "| benign | **0.672 / 0.902** | 0.823 / 0.879 |",
     "drift/logs/density_gnss",
     "campaign_gnss    fused       0.672/0.902"),
    ("drift low rate dos collapses",
     "| dos_low_rate | **0.114 / 0.884** | 0.829 / 0.942 |",
     "drift/logs/density_gnss", "0.114/0.884"),
    ("drift sybil reverses",
     "| sybil | **0.849 / 0.948** | **0.330 / 0.867** |",
     "drift/logs/density_gnss", "0.330/0.867"),
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
    ("region panel FedLC significant on both",
     "FedLC **+0.0147 at p = 0.0078**", None, None),
    ("region panel FedNova worse again",
     "FedNova **-0.0046 at p = 0.0078**", None, None),
    # Superseded pair, kept because section 3d is a statement about the filter
    # rather than about the corpus and has not been repeated.
    ("drift baseline holds under seed grouping",
     "**0.5767 +/- 0.0181 on the congested corpus against 0.5843\nstation-grouped**",
     "drift/logs/density_seedgrouped",
     "campaign_dense   fused         0.4132 +/- 0.0265    0.5767 +/- 0.0181  -0.1634"),
    # The estimator-aware adversary. Two logs, because the constrained and
    # unconstrained versions are the whole point and quoting one without the
    # other is the misreading this section exists to prevent.
    ("calibration BLER waterfall",
     "**0.0375\nat 10-15**, 0.0131 at 15-20, 0.0063 at 20-30, 0.0017 above 30",
     "campaign_gnss/logs/calibration", "(10, 15]    193656  0.0375"),
    ("calibration PRR decay",
     "0.9292 under 50 m, 0.8787 at\n150-200",
     "campaign_gnss/logs/calibration", "(0.0, 50.0]               6756  0.9292"),
    # cross-checks kept from the other corpora
    ("dense blocks", "| **fused** | 50 | **0.5859** | **0.8312** |",
     "benchmark_dense3", "fused            50  0.5859"),
    ("dense stealth position",
     "| position falsification, stealthy | **14.0 m** median error (sd 6.2) | **0.001** |",
     "benchmark_dense3", "    11         0.002         0.002         0.001"),
    ("short road pooling ceiling", "0.281 to 0.810 on class 1",
     "pooled_unweighted", "pooled-consensus   0.8039 +/- 0.0400     +0.1438"),
    ("dense CBR",
     "| 240 veh / 2000 m, `runs/campaign_dense` seed1 | 20.0 | **0.733** | 1.000 | 1.000 | **1000 ms** |",
     None, None),
]

# Files whose contents must be no older than the artefact they describe. The
# separation table is computed FROM the pooled pickle, so a stale log beside a
# regenerated pickle quotes numbers that can no longer be reproduced, and no
# amount of string matching would notice.
FRESHNESS = [("campaign_v3/logs/pool_separation.log", "campaign_v3/pooled.pkl")]

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
               "README.md", "analysis/README.md", "simulation/README.md",
               "capstone/README.md"]


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
    """Em and en dashes are banned in this project's prose.

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


def main():
    doc = DOC.read_text()
    cache, bad = {}, 0
    bad = check_style(bad)
    bad = check_claims(bad)
    bad = check_references(bad)
    bad = check_readme(bad)
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
             + len(CLAIMS_CONSISTENCY) + 2)   # reference and readme checks
    print(f"\n{total - bad}/{total} verified")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
