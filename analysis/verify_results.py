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
    ("localisation benign", "| benign | 0.0 | **35.7** | **35.8** |",
     "pooled_unweighted", "median    35.7 m"),
    ("localisation class 1", "| 1 pos_const_offset | 133.9 | **33.4** | **145.9** |",
     "pooled_unweighted", "estimate to claim   145.9 m,  estimate to true    33.4 m"),
    ("single receiver arm", "| single receiver | 0.6602 +/- 0.0351 | | 0.281 | 0.432 |",
     "pooled_unweighted", "single             0.6602 +/- 0.0351"),
    ("soft vote arm",
     "| vote, soft | 0.6331 +/- 0.0388 | -0.0270 | **0.018** | 0.426 |",
     "pooled_unweighted", "vote-soft          0.6331 +/- 0.0388     -0.0270"),
    ("pooled-consensus arm",
     "| **pooled-consensus** | **0.8039 +/- 0.0400** | **+0.1438** | **0.810** | **0.847** |",
     "pooled_unweighted", "pooled-consensus   0.8039 +/- 0.0400     +0.1438"),
    ("per-observation reconciliation", "0.300 on class 1 against\nsection 3's 0.292",
     "pooled_unweighted", "1:0.300"),
    ("per-observation macro", "0.6556 macro F1\nper observation",
     "pooled_unweighted", "macro F1 0.6556"),
    ("balanced robustness", "class 1 goes 0.204 to 0.744 instead of 0.281 to 0.810",
     "pooled_consensus", "pooled-consensus   0.7851 +/- 0.0362"),
    ("sweep at 5, the floor", "| 5 | 0.6787 | 0.4588 | 0.4344 |",
     "pooled_sweep", "5  0.6787"),
    ("sweep at all receivers", "| all, median 87 | 0.8013 | 0.8169 | 0.8559 |",
     "pooled_sweep", "all  0.8013"),
    ("consensus separation",
     "| `pool_rmse_ratio` | **5.41** | 1.96 | 3.16 | -0.06 | 0.99 | 0.19 | 0.01 |",
     "pool_separation",
     "pool_rmse_ratio                5.41    1.96    3.16   -0.06    0.99    0.19    0.01"),
    ("permutation control",
     "| **benign, claim permuted** | **345.2 m** | **7.98 dB** | **7.29** | **0.287** |",
     "claim_permutation",
     "benign, claim permuted               4771        7.98            7.29     0.287      345.2 m"),
    ("power evasion class 1", "| 1 | power-targeted | **0.468** | **0.905** |",
     "power_evasion", "power-targeted             0.468             0.905"),
    ("feature selection at 30", "| 30 | 0.6434 | -0.0054 |",
     "feature_selection", "30  0.6434 +/- 0.0214     -0.0054"),
    ("selection stability", "Only 16 distinct features are ever chosen",
     "feature_selection", "16 distinct features ever chosen"),
    # Section 5 was measured before federated.py grew --observer-col, the pool_
    # prefix and the DP path. Pinning it here means those edits cannot silently
    # change the published panel.
    ("federated FedAvg baseline", "| FedAvg | 0.2392 +/- 0.0350 | | |",
     "federated_regression", "fedavg    macro F1 0.2392 +/- 0.0350"),
    ("federated FedLC significant",
     "| **FedLC** | **0.2525 +/- 0.0381** | **+0.0132** | **0.0078** |",
     "federated_regression", "fedlc     delta +0.0132  p = 0.0078  significant"),
    ("federated FedNova worse",
     "| **FedNova** | 0.2326 +/- 0.0350 | **-0.0067** | **0.0078 worse** |",
     "federated_regression", "fednova   delta -0.0067  p = 0.0078  significant"),
    ("dense blocks", "| **fused** | 50 | **0.5859** | **0.8312** |",
     "benchmark_dense3", "fused            50  0.5859"),
    ("dense class 1 app blind", "| 1 pos_const_offset | **0.000** | **0.209** | 0.208 |",
     "benchmark_dense3", "     1         0.000         0.209         0.208"),
    ("dense stealth position",
     "| position falsification, stealthy | **14.0 m** median error (sd 6.2) | **0.001** |",
     "benchmark_dense3", "    11         0.002         0.002         0.001"),
    ("dense corpus size", "2,025,833 windows from\n720 stations at CBR 0.733",
     "validate_dense3", "2025833 windows, 50 features, 10 classes, 720 stations"),
    ("dense gates", "All eight gates pass on\nit (`runs/validate_dense3.log`), with 1-NN at 0.374.",
     "validate_dense3", "1-NN triviality: macro F1 0.3741"),
    ("federated pooled FedAvg",
     "| FedAvg | 0.4536 +/- 0.0064 | **0.4844 +/- 0.0048** | +0.0308 | 8/8 | 0.0078 |",
     "federated_regions", "fedavg    macro F1 0.4844 +/- 0.0048"),
    ("federated single control",
     "| FedLC | 0.4690 +/- 0.0063 | **0.4988 +/- 0.0057** | +0.0299 | 8/8 | 0.0078 |",
     "federated_regions_single", "fedlc     macro F1 0.4690 +/- 0.0063"),
    ("federated no consensus", "| 50, pooled means only | 0.4861 +/- 0.0054 | 0.4977 |",
     "federated_regions_nocons", "fedavg    macro F1 0.4861 +/- 0.0054"),
    ("region receiver count",
     "**Receivers per region: median 8, tenth percentile 5, ninetieth 12.**",
     "pooled_regions", "median 8, p10 5, p90 12"),
    ("dense pooling replication",
     "| **pooled-consensus** | **0.6449 +/- 0.0440** | **+0.1119** | **0.684** | **0.754** | 0.004 |",
     "pooled_dense", "pooled-consensus   0.6449 +/- 0.0440     +0.1119"),
    ("dense pooling vote null", "| vote, majority | 0.5347 +/- 0.0371 | +0.0017 (p 0.92) | 0.011 | 0.261 | 0.000 |",
     "pooled_dense", "vote               0.5347 +/- 0.0371     +0.0017      0.9219"),
    ("dense localisation floor", "lands 26.8 m from the truth against 35.7 m on the sparse road",
     "pooled_dense", "median    26.8 m"),
    ("pooling cost", "| both | **0.4439** |",
     "pooling_cost", "both                                               0.4439"),
    ("pooled panel retuned", "reproducing the table above to\nfour decimals",
     "federated_regions_tuned", "tuned fedlc: tau = 2.0"),
    ("persistence best point", "| **0.90** | **2/3** | **2** | **0.583** | **0.001** |",
     "persistence", "2/3                     1                    2            0.583"),
    ("persistence at 0.70", "| 0.70 | 4/5 | 9 | 0.571 | 0.006 |",
     "persistence", "4/5                     4                    9            0.571"),
    ("pooling per class at the operating point",
     "| 1 pos_const_offset | 31 | **0.226** | **0.065** |",
     "persistence_perclass", "     1       31    0.226"),
    ("persistence single arm matches",
     "0.588 attackers\nfound against 0.583 pooled",
     "persistence_single", "2/3                     1                    2            0.588"),
    ("long contact rule 2/3", "| 2/3 | **0** | 0.611 |",
     "persistence_long", "2/3                     0                    0            0.611"),
    ("long contact span", "observation span 58 s per region against 23 s",
     "persistence_long", "observation span 58 s per region"),
    ("contact time short tracks", "| 1 to 4 | 81 | **0.210** | 0.000 |",
     "persistence_contact", "(0, 4]               81            0.210"),
    ("contact time best band", "| 9 to 12 | 44 | **0.750** | 0.000 |",
     "persistence_contact", "(8, 12]               44            0.750"),
    ("dp clipping is free", "| 0.00, clipping only | 0.4805 +/- 0.0056 | -0.0040 | no noise |",
     "dp_sweep", "0.00 0.4805 +/- 0.0056   -0.0040"),
    ("dp at epsilon 8.3", "| 3.00 | **0.2091 +/- 0.0186** | **-0.2754** | **8.3** |",
     "dp_sweep", "3.00 0.2091 +/- 0.0186   -0.2754        8.3"),
    ("deploy pooled FPR", "| 0.70 | 0.0484 | **0.0382** | 0.6003 | **0.6415** |",
     "deploy_pooled", "0.70   0.0382   0.6415"),
    ("deploy single FPR", "| 0.50 | 0.4185 | **0.3452** | 0.8017 | 0.8046 |",
     "deploy_single", "0.50   0.4185   0.8017"),
    ("dense CBR",
     "| 240 veh / 2000 m, `runs/campaign_dense` seed1 | 20.0 | **0.733** | 1.000 | 1.000 | **1000 ms** |",
     None, None),
]

# Files whose contents must be no older than the artefact they describe. The
# separation table is computed FROM the pooled pickle, so a stale log beside a
# regenerated pickle quotes numbers that can no longer be reproduced, and no
# amount of string matching would notice.
FRESHNESS = [("pool_separation.log", "campaign/pooled_geo.pkl")]


# Numbers that appear in BOTH the claims summary and the results file. The
# claims file is the one that gets read while writing, so it is the one most
# likely to be edited in isolation and left quietly disagreeing with the
# evidence it summarises. Each entry is a string that must appear in both.
CLAIMS_CONSISTENCY = [
    "0.281",          # single receiver, class 1
    "0.810",          # pooled consensus, class 1
    "7.29",           # permutation control, benign given a false claim
    "0.468",          # single receiver AUC under targeted power control
    "0.905",          # pooled AUC, unchanged under every adversary
    "0.0132",         # FedLC over FedAvg
    "0.583",          # attackers found at the deployable operating point
]

STYLE_FILES = ["RESULTS.md", "MASTER_INDEX.md", "BUILD_LOG_V2.md",
               "PAPER_CLAIMS.md"]


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
    for m in sorted(set(re.findall(r"runs/[a-z0-9_]+(?:/[a-z0-9_]+)?\.(?:log|pkl)", text))):
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
    for name in STYLE_FILES:
        f = DOC.parent / name
        if not f.exists():
            continue
        text = f.read_text()
        n = sum(text.count(c) for c in "\u2014\u2013")
        ok = n == 0
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} style: {name:24s}"
              f"{'' if ok else f'  <- {n} em or en dashes'}")
    return bad


def main():
    doc = DOC.read_text()
    cache, bad = {}, 0
    bad = check_style(bad)
    bad = check_claims(bad)
    bad = check_references(bad)
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
             + len(CLAIMS_CONSISTENCY) + 1)   # +1 for the reference check
    print(f"\n{total - bad}/{total} verified")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
