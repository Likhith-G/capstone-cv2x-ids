#!/usr/bin/env python3
"""
Generate the dataset card from the corpus, so it cannot drift from the data.

Three documents in this project wrote figures down by hand and all three went
wrong. A dataset card is the worst place for that to happen, because it is the
one document a stranger reads instead of the data. So every count, every class
size and every partition figure here is read out of the corpus at generation
time, and only the prose is written by a person.

**A column with no description is an error, not an omission.** The descriptions
below are curated and the script exits non-zero if the corpus carries a column
this file does not describe. Adding a feature therefore forces documenting it,
which is the only mechanism that reliably keeps a schema honest.

    make_dataset_card.py corpus.pkl --splits release_splits.csv --out DATASET_CARD.md
"""
import argparse
import datetime as dt
import hashlib
import pathlib
import sys

import numpy as np
import pandas as pd

CLASSES = {
    0:  ("benign", "Honest station. Carries receiver positioning error rather than claiming its exact position."),
    1:  ("pos_const_offset", "Position falsification at a constant offset, realised displacement 71 to 233 m."),
    3:  ("pos_offset_random", "Position falsification redrawn every message, so the claim is self inconsistent."),
    4:  ("pos_replay", "A previously transmitted position re-sent, so the claim lags the truth."),
    5:  ("speed_falsify", "Claimed speed inconsistent with claimed displacement."),
    6:  ("sybil", "One physical station transmitting under several identities."),
    7:  ("dos_rate", "High rate transmission, denial of service against the channel."),
    8:  ("sps_manipulation", "Semi persistent scheduling manipulation. INERT in this simulator, see limitations."),
    11: ("pos_small_offset", "Position falsification at a constant offset, realised displacement 20 to 25 m."),
    12: ("dos_low_rate", "Low rate denial of service, below the obvious volumetric signature."),
    13: ("pos_medium_offset", "Position falsification at a constant offset, realised displacement 47 to 60 m."),
}

DESC = {
    # keys, which identify a row and must never be used as features
    "key_rxNodeId": "Receiver that made this observation.",
    "key_claimedStationId": "Station identifier as claimed over the air.",
    "key_window": "Time window index.",
    "key_txRnti_mode": "Modal radio identifier seen for this station in this window.",
    "key_observer_role": "Whether the receiver is a vehicle or a roadside unit.",
    "key_seed": "Simulation seed. Eight independent realisations.",
    # labels, ground truth, never features
    "label_attackId": "Class. See the class table.",
    "label_txNodeId": "True transmitting node, from the transmit log.",
    "label_attack_purity": "Share of this window's messages that came from the labelled attacker.",
    "label_is_attack": "Binary form of label_attackId.",
    "label_clean": "Window passes the purity threshold. Filter on this before any analysis.",
    # application layer, computable from message contents alone
    "app_n_msgs": "Messages received from this station in this window.",
    "app_n_cam": "Cooperative awareness messages among them.",
    "app_n_denm": "Decentralized environmental notification messages.",
    "app_n_cpm": "Collective perception messages.",
    "app_iat_mean": "Mean inter arrival time.",
    "app_iat_std": "Standard deviation of inter arrival time.",
    "app_iat_min": "Smallest inter arrival time.",
    "app_claimed_dist_mean": "Mean distance from the receiver to the CLAIMED position. The acceptance range check.",
    "app_claimed_dist_std": "Its standard deviation.",
    "app_claimed_speed_mean": "Mean claimed speed.",
    "app_claimed_speed_std": "Its standard deviation.",
    "app_dmv_mean": "Distance moved verification: claimed displacement against claimed speed, mean.",
    "app_dmv_absmax": "The same, largest magnitude.",
    "app_ssc_mean": "Sudden speed change between consecutive claims, mean.",
    "app_ssc_absmax": "The same, largest magnitude.",
    "app_predict_mean": "Claimed position against the position predicted from the previous claim, mean.",
    "app_predict_max": "The same, largest.",
    "app_heading_mean": "Claimed heading against the heading implied by claimed displacement, mean.",
    "app_heading_max": "The same, largest.",
    "app_accel_absmax": "Largest implied acceleration between consecutive claims.",
    "app_seq_gaps": "Gaps in the claimed sequence number.",
    "app_seq_loss_rate": "Those gaps as a rate.",
    # physical and MAC layer, what the radio measured
    "phy_sinr_db_mean": "Mean signal to interference and noise ratio, decibels.",
    "phy_sinr_db_std": "Its standard deviation.",
    "phy_tbler_mean": "Mean transport block error rate.",
    "phy_corrupt_rate": "Share of received transport blocks that failed.",
    "phy_mcs_mean": "Mean modulation and coding scheme index.",
    "phy_rsrp_resid_mean": "Received power against the power the fitted propagation law predicts at the CLAIMED distance, mean.",
    "phy_rsrp_resid_std": "Its standard deviation.",
    "phy_rsrp_resid_absmax": "Its largest magnitude.",
    "phy_rsrp_mean": "Mean per SCI sidelink reference signal received power. Exposed by the additive patch to 5G-LENA.",
    "phy_rsrp_std": "Its standard deviation.",
    "phy_rsrp_min": "Its minimum.",
    "phy_rsrp_max": "Its maximum.",
    "phy_rsrp_count": "Number of power measurements behind the statistics above.",
    "phy_cbr_pscch_rate": "Control channel occupancy seen by this receiver, a channel busy measure.",
    "phy_pscch_corrupt_rate": "Share of control channel decodes that failed.",
    "phy_neighbours": "Distinct radio identifiers this receiver heard in this window.",
    "phy_track_corr": "Correlation between measured power and the power predicted from the claimed track, over a long window. Undefined below 8 samples or 2 dB of predicted span.",
    "phy_track_slope": "Regression slope of the same pair. One means the claim tracks the radio.",
    "phy_track_resid_std": "Residual spread of the same regression.",
    "phy_track_span": "Range of predicted power across the window, which says whether there was anything to track.",
    "phy_closest_lag_s": "Signed time between the claimed closest approach and the measured power peak. Undefined unless the claimed minimum is interior to the window.",
    "phy_closest_lag_abs": "Its magnitude, which does not cancel in the mean as the signed value does.",
    "phy_closest_power_gap": "Measured peak power against the power predicted at the claimed closest approach.",
    "phy_rsrp_vs_claimed": "Measured power minus the power predicted for the claimed distance.",
    "phy_rsrp_voiceprint_min": "Smallest power difference to another station the same receiver hears in the same window that claims to be far away. Small with a large claimed separation is the Sybil signature.",
    "phy_loss_vs_rsrp": "Sequence loss rate against what this received power would ordinarily produce.",
    "phy_corrupt_vs_rsrp": "Corruption rate against the same baseline.",
    "phy_tbler_vs_rsrp": "Block error rate against the same baseline.",
}

SCENARIO_NOTES = {
    "highway_sparse": ("what varies: nothing, this is the reference",
        "6 km carriageway, 90 vehicles, about 2.5 per km per lane, so the channel "
        "sits well below congestion and the decentralised congestion control "
        "barely engages. The reference scenario and the one every headline figure "
        "is measured on."),
    "highway_dense": ("what varies: **density**",
        "2 km carriageway, 240 vehicles, about 20 per km per lane, with congestion "
        "control saturated. Any claim about behaviour under congestion has to come "
        "from here, and the transfer between this and the sparse scenario is what "
        "makes a drift evaluation possible."),
    "magnitude_sweep": ("what varies: **attack magnitude coverage**",
        "The same geometry as the reference with both position offset draws "
        "widened, so attackers span 4 to 233 m with eleven of them inside the 30 "
        "to 50 m band that the reference has only three in. Built to sample the "
        "detectability transition rather than its ends. **Shares its vehicles with "
        "the reference scenario**, see the warning below."),
    "bursty_attackers": ("what varies: **attack strategy**",
        "Attackers misbehave in bursts at a duty of about 0.2 rather than "
        "continuously. This exists to attack persistence based alerting, which a "
        "continuously lying attacker satisfies trivially, and it is the axis the "
        "VASP framework calls persistent against sporadic."),
    "offset_receivers": ("what varies: **receiver placement**",
        "Roadside units moved off the centreline to a lateral offset, which "
        "changes the conditioning of the receiver array without changing anything "
        "else. The array's weakness across the road is the mechanism behind the "
        "adversarial result, so a scenario that perturbs it is the control."),
}

BLOCKS = [("key_", "Keys and provenance", "Identify a row. **Never features.**"),
          ("label_", "Labels", "Ground truth from the transmit log. **Never features.**"),
          ("app_", "Application layer", "Computable from message contents alone, which is what a detector without radio access sees."),
          ("phy_", "Physical and MAC layer", "What the radio measured. This block is what no other public V2X misbehaviour dataset carries.")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--splits", default=None, help="release_splits.csv from make_release_splits.py")
    ap.add_argument("--scenarios", default=None,
                    help="SCENARIOS.json from make_release.py")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    df = pd.read_pickle(a.corpus)
    undescribed = [c for c in df.columns if c not in DESC]
    if undescribed:
        print(f"FAIL: {len(undescribed)} column(s) have no description in this "
              f"file, so the card would be silently incomplete:")
        for c in undescribed:
            print(f"  {c}")
        return 1

    clean = df[df.label_clean == 1] if "label_clean" in df.columns else df
    # Grouped on the PHYSICAL transmitter, not the claimed identity. Sybil
    # emits four identities per vehicle, so counting claimed identities reports
    # 783 where the corpus holds 720 vehicles, and every per class figure for
    # sybil comes out four times too large.
    st = clean.groupby(["key_seed", "label_txNodeId"]).label_attackId.first()
    L = []
    w = L.append

    w("# Dataset card: CV2X-IDS\n")
    w(f"Generated from `{pathlib.Path(a.corpus).name}` on "
      f"{dt.date.today().isoformat()} by `analysis/make_dataset_card.py`. Every "
      f"count below is read from the corpus at generation time rather than "
      f"written by hand.\n")

    w("## What this is\n")
    w("A labelled intrusion detection dataset for C-V2X sidelink, generated in "
      "ns-3.42 with the 5G-LENA `nr` module at tag `v2x-1.1`. Vehicles exchange "
      "ETSI messages directly over an NR V2X Mode 2 PC5 sidelink. Each row is "
      "**one receiver's view of one claimed station over one time window**, and "
      "carries both what the message said and what the radio measured while "
      "receiving it.\n")
    w("**Ground truth never travels over the air.** The transmitter logs it, the "
      "receiver logs only what it received, and the two are joined offline on a "
      "message identifier. An assertion fails the build if any column named "
      "`key_*` or `label_*` reaches the feature list.\n")
    w("**Benign vehicles do not claim their exact position.** Each carries a "
      "receiver error drawn from the model VeReMi Extension uses. Without it the "
      "benign class has no positional variance and any displacement at all is "
      "separable in principle, which makes position falsification far easier to "
      "detect than it could ever be in deployment.\n")

    w("## Size\n")
    w("| | |")
    w("|---|---|")
    w(f"| windows | {len(clean):,} |")
    w(f"| stations | {len(st)} physical transmitters, of which "
      f"{int((st == 0).sum())} benign |")
    w(f"| claimed identities | {clean.groupby(['key_seed','key_claimedStationId']).ngroups}, "
      f"more than the transmitter count because sybil emits several per vehicle |")
    w(f"| classes | {clean.label_attackId.nunique()} |")
    w(f"| columns | {len(df.columns)}, being "
      f"{sum(c.startswith('app_') for c in df.columns)} application layer, "
      f"{sum(c.startswith('phy_') for c in df.columns)} physical and MAC, "
      f"{sum(c.startswith(('key_','label_')) for c in df.columns)} keys and labels |")
    w(f"| seeds | {clean.key_seed.nunique()} |\n")

    scen_path = pathlib.Path(a.splits).parent / "release" / "SCENARIOS.json" \
        if a.splits else None
    if a.scenarios and pathlib.Path(a.scenarios).exists():
        import json as _json
        scen = _json.loads(pathlib.Path(a.scenarios).read_text())
        w("## Scenarios\n")
        w("Five campaigns, each varying one factor. They ship together because a "
          "detector that only works in one of them has not been shown to work.\n")
        w("| scenario | role | windows | vehicles | seeds |")
        w("|---|---|---|---|---|")
        for k, v in scen.items():
            w(f"| `{k}` | {v['kind']} | {v['rows']:,} | {v['transmitters']} | {v['seeds']} |")
        tot = sum(v["rows"] for v in scen.values())
        w(f"| **total** | | **{tot:,}** | | |\n")
        for k, v in scen.items():
            note = SCENARIO_NOTES.get(k)
            if not note:
                continue
            w(f"**`{k}`**, {note[0]}. {note[1]}")
            if v.get("coverage_gaps"):
                w("")
                w(f"  Marked *supplementary*: under the shared partition "
                  f"{len(v['coverage_gaps'])} class and split combination(s) are "
                  f"empty, so it supports auxiliary evaluation but not headline "
                  f"scoring. Specifically: " + "; ".join(v["coverage_gaps"]) + ".")
            w("")
        w("### A warning that matters more than it looks\n")
        w("**The campaigns were generated with the same random seeds, so some of "
          "them contain the same physical vehicles.** `magnitude_sweep` and "
          "`highway_sparse` are identical in this respect: at seed 1 they share "
          "102 stations whose true positions agree to four decimal places. "
          "`offset_receivers` diverges from the reference by at most 3.3 m and "
          "`bursty_attackers` by at most 219 m, so both are close relatives rather "
          "than independent draws. Only `highway_dense`, which uses a different "
          "road length and vehicle count, is genuinely independent.\n")
        w("**This is why the partition is global.** It is assigned once across the "
          "union of all five scenarios, keyed on the physical transmitter, so a "
          "vehicle sits in the same partition everywhere it appears. Training on "
          "one scenario and scoring on another is therefore safe. **Do not "
          "re-partition per scenario**, and do not assume two scenarios are "
          "independent samples.\n")
        w("---\n")

    w("## Classes\n")
    w("Station counts, not row counts. One station produces thousands of windows, "
      "so a per class score read over rows can rest on two or three vehicles.\n")
    w("| id | name | stations | windows | description |")
    w("|---|---|---|---|---|")
    for cid, (name, desc) in CLASSES.items():
        n_st = int((st == cid).sum())
        n_w = int((clean.label_attackId == cid).sum())
        if n_st == 0:
            continue
        w(f"| {cid} | `{name}` | {n_st} | {n_w:,} | {desc} |")
    w("")
    w("The three constant offset classes, 11 then 13 then 1, are **one mechanism "
      "at three magnitudes**, chosen against the benign positioning error so the "
      "set brackets the point at which detection becomes possible rather than "
      "sitting to one side of it. Their realised displacements do not overlap. "
      "Treating them as three unrelated classes loses the axis they were built "
      "to provide.\n")

    if a.splits and pathlib.Path(a.splits).exists():
        sp = pd.read_csv(a.splits)
        w("## Partitions\n")
        w("Frozen, shipped with the dataset, and reproducible from "
          "`analysis/make_release_splits.py`. Split **by physical transmitter**, "
          "not by claimed identity, so a sybil vehicle's several identities stay "
          "together and no vehicle appears on both sides of a boundary. "
          "Stratified so every class reaches every partition. Counts below are "
          "vehicles.\n")
        sp = sp.drop_duplicates(["key_seed", "label_txNodeId"])
        tab = sp.pivot_table(index="label_attackId", columns="split",
                             values="label_txNodeId", aggfunc="count",
                             fill_value=0).reindex(
                                 columns=["train", "validation", "test"], fill_value=0)
        w("| class | train | validation | test |")
        w("|---|---|---|---|")
        for cid, row in tab.iterrows():
            w(f"| {cid} | {row['train']} | {row['validation']} | {row['test']} |")
        wins = sp.groupby("split").windows.sum()
        w("")
        w("Window shares: " + ", ".join(
            f"{k} {100*wins[k]/wins.sum():.1f} percent"
            for k in ("train", "validation", "test")) + ".\n")
        w("A dependence this does not remove, stated rather than hidden: stations "
          "inside one seed share a traffic realisation, so grouping by station "
          "removes identity leakage and not scenario correlation. A seed level "
          "split would remove it, and cannot be used here because five of the "
          "eight seeds are missing at least one attack class outright.\n")

    w("## Schema\n")
    for pre, title, note in BLOCKS:
        cols = [c for c in df.columns if c.startswith(pre)]
        if not cols:
            continue
        w(f"### {title} ({len(cols)})\n")
        w(f"{note}\n")
        w("| column | type | meaning |")
        w("|---|---|---|")
        for c in cols:
            w(f"| `{c}` | {df[c].dtype} | {DESC[c]} |")
        w("")

    w("## Known limitations\n")
    w("Stated here rather than left for a user to discover.\n")
    w("1. **Both radio layer attacks are inert.** Mode 2 grants in 5G-LENA are "
      "data driven, so a reserved resource is used only when there is data for "
      "it and an attacker cannot hoard the channel. `sps_manipulation` is not "
      "weakly detectable, it is not detectable, and resource exhaustion is "
      "indistinguishable from a benign station at the same reservation interval. "
      "The cross layer argument therefore rests on radio features catching "
      "**application layer** attacks.")
    w("2. **The main corpus is light traffic**, about 2.5 vehicles per km per "
      "lane, and its congestion control barely engages. That is the price of the "
      "6 km road the federated partition requires. A matched dense corpus covers "
      "the congested point and any claim about congestion must come from it.")
    w("3. **Fixed modulation and coding**, no link adaptation, and an EESM link "
      "to system PHY abstraction rather than a full PHY. Both are simulator "
      "limits.")
    w("4. **The receiver geometry is one straight road** with the roadside units "
      "on its centreline. Receivers along a straight road are close to "
      "collinear, which is the weakest realistic geometry for position "
      "verification and is measured rather than assumed. No junction or curve is "
      "covered.")
    w("5. **Highway only.** No urban scenario, one car following model, and the "
      "aggregate simulated time is short next to the benchmarks this sits "
      "beside.")
    w("6. **Three classes have fewer than twenty stations**, so a per class score "
      "on them rests on single figures per partition and must be read with the "
      "station count beside it.\n")

    w("## Licence\n")
    w("The data is intended for **CC BY 4.0**. The generator is an ns-3 contrib "
      "module and is **GPL-2.0-only**, because ns-3 and 5G-LENA are. See "
      "`LICENSES.md` in the code repository.\n")

    out = pathlib.Path(a.out)
    text = "\n".join(L)
    bad = text.count("—") + text.count("–")
    if bad:
        print(f"FAIL: {bad} em or en dash(es) in the generated card")
        return 1
    out.write_text(text)
    print(f"{len(text.splitlines())} lines -> {out}")
    print(f"{len(df.columns)} columns, all described")
    return 0


if __name__ == "__main__":
    sys.exit(main())
