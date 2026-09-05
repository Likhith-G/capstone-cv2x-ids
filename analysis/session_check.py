#!/usr/bin/env python3
"""Session check: the state that goes stale, verified rather than narrated.

Run this before every compaction and at every session close.

The reason this file exists. Three documents in this project carried a disk
figure and all three were wrong, one by a factor of twelve. A blocker sat
recorded as open for weeks because a filename was misread and nothing re-tested
it. Meanwhile every number in RESULTS.md stayed true, because verify_results.py
checks all of them against their generating logs. The difference is not care.
It is that one kind of state is machine-checked and the other is narrated.

So this script checks the project's own bookkeeping the way verify_results.py
checks its figures. Anything it can measure, STATUS.md should point at rather
than restate.

    python3 analysis/session_check.py             full check
    python3 analysis/session_check.py --quick     skip verify_results.py
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
RUNS = pathlib.Path.home() / "ns3-v2x" / "runs"
MEMORY = pathlib.Path.home() / ".claude" / "projects" / "-Users-likhithgowda" / "memory"
STATUS = REPO / "docs" / "STATUS.md"
STATUS_MAX_LINES = 120

# The git conventions were set when the rewrite began. Commits before this sit
# in a shared repository and are not worth a history rewrite.
RULES_FROM = "2026-08-01"

# Memory files this project owns. The memory directory also holds unrelated
# work, and checking those here would report failures no session on this
# project should be expected to fix.
PROJECT_MEMORY = ["project_cv2x_v2_rebuild.md", "project_capstone_partb.md",
                  "project_capstone_connected_cars.md",
                  "project_capstone_ground_truth_leakage.md",
                  "feedback_shared_scenario_merge.md",
                  "feedback_background_jobs.md", "feedback_git_commit_rules.md",
                  "feedback_writing_style.md", "feedback_read_before_overwrite.md",
                  "feedback_one_artefact_framing.md"]

# Archival memory: written before the current conventions and not rewritten by
# this workstream. The dash rule governs prose being written now, and a check
# that flags a historical record in perpetuity is a check that gets ignored.
ARCHIVAL_MEMORY = ["project_capstone_connected_cars.md",
                   "project_capstone_ground_truth_leakage.md"]

# Working documents that must stay free of em and en dashes. The naive
# grep -c with backslash-pipe alternation matches nothing and returns 0, which
# silently passed documents holding 31 dashes. Checking in Python avoids the
# whole class of shell quoting error.
DASH_DOCS = ["RESULTS.md", "PAPER_DRAFT.md", "PAPER_CLAIMS.md", "METHODS_DRAFT.md",
             "STATUS.md", "LESSONS.md", "CRITIQUE.md", "PLAN.md",
             "CAPSTONE_PLAN.md"]

# Scripts that mean work is still in flight. Compacting or handing off while one
# of these runs loses the session that knows what it was for.
#
# Derived from what is actually in analysis/ rather than hand listed. The hand
# listed version silently omitted pooled_regions.py and reported "nothing
# running" while that script was mid-run, which is worse than no check: a check
# that can be quietly incomplete gives false comfort. Deriving it means a new
# script is covered the moment it exists.
#
# Matched against the .py or .sh file being invoked, not against the whole
# command line. A bare "ns3" here matched every corpus path, since they all live
# under ns3-v2x, so a shell merely waiting on a log looked like a simulation.
BUSY = sorted(p.name for p in (REPO / "analysis").glob("*.py")
              if p.name not in ("session_check.py", "verify_results.py"))
BUSY += sorted(p.name for p in (REPO / "analysis").glob("*.sh"))

# The ns-3 simulator binary, which is not a script and is matched on its own.
SIM = "cv2x-ids-scenario"

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    return ok


def sh(cmd, cwd=None):
    """Run a shell command, return (exit code, stdout stripped)."""
    p = subprocess.run(cmd, shell=True, cwd=cwd or REPO,
                       capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip()


def check_processes():
    # pgrep -f matches the waiting shell itself, which has produced false
    # positives here before. Match on the process table with a bracketed
    # pattern so the awk invocation cannot match itself.
    running = []
    _, out = sh("ps ax -o pid=,command=")
    for line in out.splitlines():
        if "session_check" in line:
            continue
        # A waiter shell names the log it polls, and those paths contain script
        # names too, so only count a line that actually INVOKES the script:
        # the token has to be an argument in its own right, not a substring of
        # a longer path, and it has to follow an interpreter or be the command.
        toks = line.split()
        invoked = {t.rsplit("/", 1)[-1] for t in toks}
        for pat in BUSY:
            if pat in invoked and any(t.endswith(pat) for t in toks[:4]):
                running.append(f"{pat} (pid {toks[0]})")
                break
        else:
            if SIM in invoked:
                running.append(f"{SIM} (pid {toks[0]})")
    check("nothing running", not running,
          "; ".join(running[:3]) if running else "no simulation or analysis in flight")


def check_git():
    code, branch = sh("git status -sb")
    dirty = [l for l in branch.splitlines()[1:] if l.strip()]
    check("working tree clean", not dirty,
          f"{len(dirty)} modified" if dirty else "no uncommitted changes")

    _, ahead = sh("git rev-list --count @{u}..HEAD")
    check("pushed to origin", ahead == "0",
          f"{ahead} unpushed commit(s)" if ahead != "0" else "in sync with origin")

    # No AI or session trailers, ever. The harness defaults must be actively
    # stripped, so this is checked rather than trusted.
    #
    # Scoped to commits since the rewrite began. The June coursework commits
    # predate these rules and sit in a shared repository, so rewriting their
    # history to satisfy a later convention would cost more than it is worth.
    _, msgs = sh(f"git log --since={RULES_FROM} --format=%B")
    # Matched as trailers rather than as bare words. A loose match on
    # "Generated with" fired on the phrase "a corpus generated without a
    # positioning error model", which is how a check earns distrust.
    patterns = [r"(?mi)^\s*Co-Authored-By:\s*.*claude",
                r"(?mi)^\s*Claude-Session:",
                r"(?i)claude\.ai/code",
                r"(?i)Generated with \[Claude Code\]",
                r"(?i)🤖"]
    bad = [p for p in patterns if re.search(p, msgs)]
    check("no AI or session trailers", not bad,
          f"{len(bad)} pattern(s) matched" if bad else f"clean since {RULES_FROM}")

    dashes = sum(msgs.count(c) for c in ("—", "–"))
    check("no dashes in commit messages", dashes == 0,
          f"{dashes} found" if dashes else f"clean since {RULES_FROM}")


def check_verifier(quick):
    if quick:
        check("verify_results.py", True, "skipped (--quick)")
        return
    code, out = sh(f"{sys.executable} analysis/verify_results.py")
    tail = out.strip().splitlines()[-1] if out.strip() else "no output"
    m = re.search(r"(\d+)/(\d+) verified", out)
    ok = bool(m) and m.group(1) == m.group(2)
    check("verify_results.py", ok, tail)


def check_disk():
    free_gb = shutil.disk_usage("/System/Volumes/Data").free / 2**30
    dirs = [d for d in RUNS.iterdir() if d.is_dir()] if RUNS.exists() else []
    _, runs_kb = sh(f"du -sk {RUNS}") if RUNS.exists() else (1, "0")
    runs_gb = int(runs_kb.split()[0]) / 2**20 if runs_kb.split() else 0

    # Below this the machine starts swapping under a heavy job, and a 40 s
    # simulation once took 2.5 hours because of it.
    check("disk headroom", free_gb >= 10.0,
          f"{free_gb:.1f} GiB free, runs/ is {runs_gb:.0f} GB across {len(dirs)} directories"
          + ("" if free_gb >= 10.0 else "  <- reclaim before running anything heavy"))

    # Any runs/ path named in a document must exist. A missing one is silent:
    # an analysis simply reports no file rather than a wrong number.
    missing = set()
    for doc in (REPO / "docs").glob("*.md"):
        for m in re.findall(r"runs/[a-z0-9_]+(?:/[a-z0-9_]+){0,2}\.(?:log|pkl)",
                            doc.read_text(errors="ignore")):
            if not (RUNS.parent / m).exists():
                missing.add(m)
    check("no dead runs/ paths in docs", not missing,
          f"{len(missing)} missing: {sorted(missing)[:2]}" if missing else "all resolve")


def check_dashes():
    offenders = []
    for name in DASH_DOCS:
        p = REPO / "docs" / name
        if not p.exists():
            continue
        t = p.read_text(errors="ignore")
        n = t.count("—") + t.count("–")
        if n:
            offenders.append(f"{name}:{n}")
    check("no em or en dashes in working docs", not offenders,
          "; ".join(offenders) if offenders else f"{len(DASH_DOCS)} documents clean")


def check_memory():
    if not MEMORY.exists():
        check("memory directory", False, "not found")
        return
    index = (MEMORY / "MEMORY.md").read_text(errors="ignore") if (MEMORY / "MEMORY.md").exists() else ""
    files = sorted(p.name for p in MEMORY.glob("*.md") if p.name != "MEMORY.md")
    unindexed = [f for f in files if f not in index]
    check("every memory file is indexed", not unindexed,
          f"{len(unindexed)} missing from MEMORY.md: {unindexed[:3]}" if unindexed
          else f"{len(files)} files, all in MEMORY.md")

    owned = [f for f in PROJECT_MEMORY if (MEMORY / f).exists()]
    missing = [f for f in PROJECT_MEMORY if not (MEMORY / f).exists()]
    check("this project's memory files exist", not missing,
          f"missing {missing}" if missing else f"{len(owned)} files")

    live = [f for f in owned if f not in ARCHIVAL_MEMORY] + ["MEMORY.md"]
    dashes = [f for f in live
              if any(c in (MEMORY / f).read_text(errors="ignore") for c in ("—", "–"))]
    check("no dashes in live memory", not dashes,
          f"{dashes[:3]}" if dashes else f"{len(live)} live files clean")


def check_status():
    if not STATUS.exists():
        check("STATUS.md exists", False, "missing, and it is the handoff entry point")
        return
    lines = STATUS.read_text(errors="ignore").splitlines()
    check("STATUS.md within cap", len(lines) <= STATUS_MAX_LINES,
          f"{len(lines)} lines"
          + ("" if len(lines) <= STATUS_MAX_LINES
             else f", over the {STATUS_MAX_LINES} cap. Move something to LESSONS.md or the archive"))


# Figures the paper legitimately carries that RESULTS.md does not, because they
# are somebody else's published result rather than a measurement made here. Any
# other unmatched figure is a number the results file cannot back.
EXTERNAL_FIGURES = {
    "0.9376", "0.8838", "0.8788",   # So, Petit and Starobinski, WiSec 2019
    "3.42",                          # the ns-3 version string
}


def check_paper_traceable():
    """Every figure in the paper must be findable in RESULTS.md.

    `verify_results.py` pins the results file to its logs. Nothing pinned the
    paper to the results file, and a figure quoted only in the paper is one
    nobody can check. This found a fused macro F1 of 0.5578 being used for a
    before-and-after comparison against a corpus that also carried one class
    fewer, so the difference was not attributable to the change it was offered as
    evidence for.

    Rounding is allowed: a paper may quote 0.072 for a measured 0.0724.
    """
    res = (REPO / "docs" / "RESULTS.md")
    pap = (REPO / "docs" / "PAPER_DRAFT.md")
    if not (res.exists() and pap.exists()):
        return
    rtext, ptext = res.read_text(), pap.read_text()
    rnums = set(re.findall(r"\b\d+\.\d+\b", rtext))
    missing = []
    for n in sorted(set(re.findall(r"\b\d+\.\d{2,4}\b", ptext))):
        if n in rnums or n in EXTERNAL_FIGURES:
            continue
        # a rounded quotation of a longer figure in the results file
        if any(r.startswith(n) or f"{float(r):.{len(n.split('.')[1])}f}" == n
               for r in rnums if r.startswith(n.split(".")[0] + ".")):
            continue
        missing.append(n)
    check("every paper figure traces to RESULTS.md", not missing,
          f"{len(missing)} untraceable: {missing[:4]}" if missing
          else "all figures found or rounded from one")


def check_blockers():
    """Every open blocker carries a test that says when it is no longer open.

    This exists because a blocker was recorded as open for weeks on the
    strength of a claim of absence that nothing re-ran. A blocker without a
    test is an opinion.
    """
    if not STATUS.exists():
        return
    text = STATUS.read_text(errors="ignore")
    block = re.search(r"<!-- BLOCKERS -->(.*?)<!-- /BLOCKERS -->", text, re.S)
    if not block:
        check("blockers declared", False, "no BLOCKERS block in STATUS.md")
        return
    entries = [l.strip("- ").strip() for l in block.group(1).splitlines()
               if l.strip().startswith("-")]
    if not entries:
        check("open blockers", True, "none declared")
        return
    for e in entries:
        if "test:" not in e:
            check(f"blocker has a test", False, f"{e[:50]} has no test")
            continue
        name, cmd = e.split("test:", 1)
        code, out = sh(cmd.strip().strip("`"))
        # exit 0 means the blocker is resolved and STATUS.md is behind
        check(f"blocker still real: {name.strip(' |')[:38]}", code != 0,
              "RESOLVED, update STATUS.md" if code == 0 else "still blocked")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip verify_results.py, which is the slow check")
    a = ap.parse_args()

    check_processes()
    check_git()
    check_verifier(a.quick)
    check_disk()
    check_dashes()
    check_memory()
    check_status()
    check_paper_traceable()
    check_blockers()

    print()
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {name:<{width}}  {detail}")
    failed = [n for n, ok, _ in results if not ok]
    print()
    if failed:
        print(f"{len(failed)} of {len(results)} checks failed. Not ready to hand off.")
        return 1
    print(f"{len(results)}/{len(results)} checks pass. Safe to compact or hand off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
