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
     "| `pool_rmse_ratio` | **4.97** | 1.56 | 3.01 | -0.02 | 0.78 | 0.45 | 0.05 | 0.15 | 0.19 |",
     "campaign_v3/logs/pool_separation",
     "pool_rmse_ratio                4.97    1.56    3.01   -0.02    0.78    0.45    0.05    0.15    0.19"),
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
    ("pooled federated gain", "| pooling, against one receiver | 0.4933 | **0.5564** | **+0.0631** | 0.0078 |",
     "campaign_v3/logs/federated_regions", "fedavg    macro F1 0.5564 +/- 0.0044"),
    ("consensus block earns place", "| the consensus block, on top of pooling | 0.5455 | **0.5564** | **+0.0109** | 0.0078 |",
     "campaign_v3/logs/federated_regions_nocons", "fedavg    macro F1 0.5455 +/- 0.0149"),
    ("dp at epsilon 8.3", "| 3.00 | **0.3397 +/- 0.0250** | **-0.2174** | **8.3** |",
     "campaign_v3/logs/dp_sweep", "3.00 0.3397 +/- 0.0250   -0.2174        8.3"),
    ("persistence zero alerts", "| **0.90** | **2/3** | **0** | **0.528** |",
     "campaign_v3/logs/persistence", "2/3                     0                    0            0.528"),
    ("persistence per class class 1", "| 1 pos_const_offset | 30 | **0.300** | **0.100** |",
     "campaign_v3/logs/persistence", "     1       30    0.300"),
    ("pooling cost", "| both | **0.4076** |",
     "campaign_v3/logs/pooling_cost", "both                                               0.4076"),
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
    ("floor pooled crosses at 50 to 80 m",
     "| 50 to 80 m | 21 | 0.00 | **0.90** |",
     "campaign_gnss/logs/offset_floor",
     "          50 to 80 m        21     1,197      0.838     0.90"),
    ("floor single observer never crosses",
     "| over 150 m | 8 | 0.12 | **1.00** |",
     "campaign_gnss/logs/offset_floor",
     "          over 150 m         8     4,119      0.264     0.12"),
    ("floor below 30 m nothing works",
     "| 15 to 30 m | 10 | 0.00 | 0.00 |",
     "campaign_gnss/logs/offset_floor",
     "          15 to 30 m        10       568      0.058     0.00"),
    ("collusion needs twenty receivers",
     "| a half | 20 | 13 |", None, None),
    # Drift. These live under runs/drift/logs because drift.py reads several
    # corpora at once and has no single run directory to write into.
    ("drift fused into light traffic",
     "| light | **fused** | **0.3612 +/- 0.0026** | **0.5554 +/- 0.0213** | "
     "**-0.1941** | **0.3098** | **0.6984** |",
     "drift/logs/density",
     "campaign_v3      fused         0.3612 +/- 0.0026    0.5554 +/- 0.0213  -0.1941"),
    ("drift fused into congestion",
     "| congested | **fused** | **0.4230 +/- 0.0109** | **0.5843 +/- 0.0098** | "
     "**-0.1613** | **0.3609** | **0.6548** |",
     "drift/logs/density",
     "campaign_dense   fused         0.4230 +/- 0.0109    0.5843 +/- 0.0098  -0.1613"),
    ("drift radio degrades least",
     "| congested | phy-only | 0.2784 +/- 0.0079 | 0.3686 +/- 0.0046 | **-0.0902** |",
     "drift/logs/density",
     "campaign_dense   phy-only      0.2784 +/- 0.0079    0.3686 +/- 0.0046  -0.0902"),
    ("drift benign false alarms",
     "| benign | 0.601 / 0.911 | 0.749 / 0.892 |",
     "drift/logs/density",
     "campaign_v3      fused       0.601/0.911"),
    ("drift low rate dos collapses",
     "| dos_low_rate | **0.103 / 0.907** | 0.834 / 0.934 |",
     "drift/logs/density", "0.103/0.907"),
    ("drift sybil reverses",
     "| sybil | **0.882 / 0.962** | **0.217 / 0.886** |",
     "drift/logs/density", "0.217/0.886"),
    ("drift control with roadside units",
     "| light | **fused** | **0.3605 +/- 0.0083** | **0.5577 +/- 0.0137** | "
     "**-0.1972** | -0.1941 |",
     "drift/logs/scenario",
     "campaign_v3      fused         0.3605 +/- 0.0083    0.5577 +/- 0.0137  -0.1972"),
    ("drift control congested",
     "| congested | **fused** | **0.4187 +/- 0.0004** | **0.5843 +/- 0.0098** | "
     "**-0.1656** | -0.1613 |",
     "drift/logs/scenario",
     "campaign_dense   fused         0.4187 +/- 0.0004    0.5843 +/- 0.0098  -0.1656"),
    ("drift none within one run",
     "| **fused** | **0.5913** | **0.5930** | **-0.0017** | **0.7365** | **0.7219** |",
     "drift/logs/temporal",
     "fused         0.5913    0.5930    -0.0017    0.7365     0.7219"),
    ("drift prequential rises across the cut",
     "| 30 to 40 s | 11,814 | **0.5935** | **0.7378** |",
     "drift/logs/temporal", "30-40s    11,814    0.5935    0.7378"),
    ("drift baseline holds under seed grouping",
     "**0.5767 +/- 0.0181 on the congested corpus against 0.5843\nstation-grouped**",
     "drift/logs/density_seedgrouped",
     "campaign_dense   fused         0.4132 +/- 0.0265    0.5767 +/- 0.0181  -0.1634"),
    # The estimator-aware adversary. Two logs, because the constrained and
    # unconstrained versions are the whole point and quoting one without the
    # other is the misreading this section exists to prevent.
    ("best response defeats the check off road",
     "| 50 m | **1.011** | **0.147** | **0.003** | 80 deg | +14.9 m |",
     "drift/logs/best_response_free",
     "        50 m       2.807     0.311       1.011      0.147         0.003"),
    ("best response is lateral",
     "**The mechanism is in the off-axis column: 75 to 85 degrees, which is lateral.**",
     "drift/logs/best_response_free", "        25 m       2.875     0.340"),
    ("on road best response is caught",
     "| 100 m | 1.742 | **0.937** | **0.814** | 5 deg |",
     "drift/logs/best_response_onroad",
     "       100 m       4.875     0.909       1.742      0.937         0.814"),
    ("localisation error is the attacker budget",
     "**Free-fit localisation error on these triples is 62.6 m.**",
     "drift/logs/best_response_free",
     "free-fit localisation error on these benign triples: median 62.6 m"),
    ("road constraint cuts localisation error",
     "**Free-fit localisation error falls from 62.6 m to 17.5 m**",
     "drift/logs/best_response_onroad_roadest",
     "free-fit localisation error on these benign triples: median 17.5 m"),
    ("road constraint lifts detection at the floor",
     "| 50 m | 0.282 | **0.398** | **0.773** |",
     "drift/logs/best_response_onroad_roadest",
     "        50 m       3.658     0.693       1.176      0.773         0.398"),
    ("ratio goes below one off road",
     "0.951 at 50 m in\n`best_response_free_roadest.log`",
     "drift/logs/best_response_free_roadest",
     "        50 m       2.807     0.311       0.951      0.148         0.013"),
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
    """The claims summary must not drift from the results it summarises."""
    claims = DOC.parent / "PAPER_CLAIMS.md"
    if not claims.exists():
        return bad
    ctext, rtext = claims.read_text(), DOC.read_text()
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
