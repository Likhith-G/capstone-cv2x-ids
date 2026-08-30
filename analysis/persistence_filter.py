#!/usr/bin/env python3
"""
Alerting on persistence rather than on every window.

Section 6 reports the alert rate per window and it is the worst practical
number in the project: even at threshold 0.90 a receiver raises hundreds of
false alerts an hour, and at 0.70 it raises thousands. That figure assumes the
detector must commit on every window independently, which no operator would
ask of it.

Misbehaviour persists. A vehicle running a position falsification attack is
still running it a second later, while a false positive is a momentary
coincidence of channel and traffic. So requiring the same claimed station to
look wrong in K of the last M windows should cut false alerts sharply and cost
little recall, and how much of each is an empirical question worth answering
because it decides whether any of this is deployable.

Two things are counted the way an operator would count them rather than the way
a classifier report would.

  Alert EPISODES, not alert windows. An alert is a rising edge: the rule starts
  firing for a station and stays armed until it stops. A station that looks bad
  for thirty consecutive windows is one alert, not thirty.

  Attackers DETECTED, not attack windows recalled. Catching a misbehaving
  vehicle once is catching it. Recall over windows understates a detector that
  fires late and overstates one that fires at random.
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

TRACK = ["key_region", "key_claimedStationId"]


def episodes(fired):
    """Rising edges in a boolean sequence."""
    f = np.asarray(fired, dtype=bool)
    if not f.any():
        return 0
    return int(f[0]) + int((f[1:] & ~f[:-1]).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--balanced", required=True)
    ap.add_argument("--realism", required=True)
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--window-ms", type=float, default=1000.0)
    ap.add_argument("--rules", default="1/1,2/3,3/5,4/5,5/7",
                    help="comma separated K/M persistence rules")
    ap.add_argument("--stratify-rule", default="2/3",
                    help="rule used for the contact-time breakdown")
    ap.add_argument("--trees", type=int, default=150)
    a = ap.parse_args()

    load = lambda x: pd.read_pickle(x) if x.endswith(".pkl") else pd.read_csv(x)
    tr, te = load(a.balanced), load(a.realism)
    feats = [c for c in tr.columns if c.startswith(("app_", "phy_", "pool_"))]
    te = te[~te.label_txNodeId.isin(set(tr.label_txNodeId.unique()))]
    if te.empty:
        raise SystemExit("realism set shares every station with the balanced set")

    X = lambda d: d[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    clf = RandomForestClassifier(n_estimators=a.trees, n_jobs=4, random_state=0)
    clf.fit(X(tr), tr.label_is_attack)
    te = te.copy()
    te["p"] = clf.predict_proba(X(te))[:, 1]
    te["hit"] = (te.p >= a.threshold).astype(int)
    te = te.sort_values(TRACK + ["key_window"])

    tracks = te.groupby(TRACK)
    n_tracks = tracks.ngroups
    attack_track = tracks.label_is_attack.max()
    span_s = ((te.key_window.max() - te.key_window.min() + 1)
              * a.window_ms / 1000.0)
    n_regions = te.key_region.nunique()
    print(f"{len(te)} windows, {n_tracks} station tracks in "
          f"{n_regions} regions, {int(attack_track.sum())} of them attackers")
    print(f"decision threshold {a.threshold}, observation span {span_s:.0f} s "
          f"per region\n")

    print(f"{'rule':>6s} {'false alert episodes':>21s} {'per region per hour':>20s} "
          f"{'attackers found':>16s} {'benign flagged':>15s}")
    for rule in a.rules.split(","):
        k, m = (int(v) for v in rule.split("/"))
        fired_any, eps_by_track = {}, {}
        for key, g in tracks:
            h = g.hit.values
            if m > 1:
                roll = pd.Series(h).rolling(m, min_periods=1).sum().values
            else:
                roll = h
            f = roll >= k
            eps_by_track[key] = episodes(f)
            fired_any[key] = bool(f.any())
        ep = pd.Series(eps_by_track)
        fa = pd.Series(fired_any)
        benign = ~attack_track.astype(bool)
        false_ep = int(ep[benign.values].sum())
        per_region_hour = false_ep / n_regions / (span_s / 3600.0)
        found = fa[attack_track.astype(bool).values].mean()
        flagged = fa[benign.values].mean()
        print(f"{rule:>6s} {false_ep:21d} {per_region_hour:20.0f} "
              f"{found:16.3f} {flagged:15.3f}")

    # Does contact time explain the recall? Each region only observes for a
    # short span here, and a rule that needs several windows cannot fire on a
    # station that is only in range for a few. Stratifying the tracks by their
    # own length answers this from the data in hand rather than needing a
    # longer simulation, and it says whether the recall reported above is a
    # property of the detector or of the observation window.
    k, m = (int(v) for v in a.stratify_rule.split("/"))
    rows = []
    for key, g in tracks:
        h = g.hit.values
        roll = (pd.Series(h).rolling(m, min_periods=1).sum().values if m > 1 else h)
        rows.append((len(h), bool((roll >= k).any()), int(g.label_is_attack.max())))
    T = pd.DataFrame(rows, columns=["length", "fired", "attack"])
    bins = pd.cut(T.length, [0, 4, 8, 12, 16, 100])
    print(f"\ncontact time against detection, rule {a.stratify_rule}")
    print(f"{'windows in range':>18s} {'attacker tracks':>16s} "
          f"{'attackers found':>16s} {'benign flagged':>15s}")
    for b, g in T.groupby(bins, observed=True):
        att, ben = g[g.attack == 1], g[g.attack == 0]
        if not len(att):
            continue
        print(f"{str(b):>18s} {len(att):16d} {att.fired.mean():16.3f} "
              f"{ben.fired.mean() if len(ben) else float('nan'):15.3f}")

    # Per class, at the chosen rule. The binary operating point is dominated by
    # whichever attacks are easy, so a detector can look identical to another
    # one at the fleet level while missing an entirely different set of
    # vehicles. Which attackers get found is the question the alert rate hides.
    per = []
    for key, g in tracks:
        h = g.hit.values
        roll = (pd.Series(h).rolling(m, min_periods=1).sum().values if m > 1 else h)
        per.append((int(g.label_attackId.max()), bool((roll >= k).any())))
    P = pd.DataFrame(per, columns=["cls", "fired"])
    print(f"\nattackers found per class, rule {a.stratify_rule}")
    print(f"{'class':>6s} {'tracks':>8s} {'found':>8s}")
    for c, g in P[P.cls != 0].groupby("cls"):
        print(f"{c:>6d} {len(g):8d} {g.fired.mean():8.3f}")
    ben = P[P.cls == 0]
    print(f"{'benign':>6s} {len(ben):8d} {ben.fired.mean():8.3f}")

    print("\nA rule of K/M fires when K of the last M windows are positive.\n"
          "1/1 is the per-window detector section 6 reports, counted as\n"
          "episodes rather than windows, which is already a large reduction\n"
          "because consecutive false positives on one station are one alert.")


if __name__ == "__main__":
    main()
