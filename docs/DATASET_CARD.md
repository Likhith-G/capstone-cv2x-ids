# Dataset card: CV2X-IDS

Generated from `corpus.pkl` on 2026-09-06 by `analysis/make_dataset_card.py`. Every count below is read from the corpus at generation time rather than written by hand.

## What this is

A labelled intrusion detection dataset for C-V2X sidelink, generated in ns-3.42 with the 5G-LENA `nr` module at tag `v2x-1.1`. Vehicles exchange ETSI messages directly over an NR V2X Mode 2 PC5 sidelink. Each row is **one receiver's view of one claimed station over one time window**, and carries both what the message said and what the radio measured while receiving it.

**Ground truth never travels over the air.** The transmitter logs it, the receiver logs only what it received, and the two are joined offline on a message identifier. An assertion fails the build if any column named `key_*` or `label_*` reaches the feature list.

**Benign vehicles do not claim their exact position.** Each carries a receiver error drawn from the model VeReMi Extension uses. Without it the benign class has no positional variance and any displacement at all is separable in principle, which makes position falsification far easier to detect than it could ever be in deployment.

## Size

| | |
|---|---|
| windows | 1,641,002 |
| stations | 720 physical transmitters, of which 519 benign |
| claimed identities | 783, more than the transmitter count because sybil emits several per vehicle |
| classes | 11 |
| columns | 61, being 22 application layer, 28 physical and MAC, 11 keys and labels |
| seeds | 8 |

## Scenarios

Five campaigns, each varying one factor. They ship together because a detector that only works in one of them has not been shown to work.

| scenario | role | windows | vehicles | seeds |
|---|---|---|---|---|
| `highway_sparse` | benchmark | 1,641,002 | 720 | 8 |
| `highway_dense` | benchmark | 3,657,495 | 720 | 3 |
| `magnitude_sweep` | benchmark | 1,220,021 | 540 | 6 |
| `bursty_attackers` | supplementary | 792,709 | 360 | 4 |
| `offset_receivers` | supplementary | 605,481 | 270 | 3 |
| **total** | | **7,916,708** | | |

**`highway_sparse`**, what varies: nothing, this is the reference. 6 km carriageway, 90 vehicles, about 2.5 per km per lane, so the channel sits well below congestion and the decentralised congestion control barely engages. The reference scenario and the one every headline figure is measured on.

**`highway_dense`**, what varies: **density**. 2 km carriageway, 240 vehicles, about 20 per km per lane, with congestion control saturated. Any claim about behaviour under congestion has to come from here, and the transfer between this and the sparse scenario is what makes a drift evaluation possible.

**`magnitude_sweep`**, what varies: **attack magnitude coverage**. The same geometry as the reference with both position offset draws widened, so attackers span 4 to 233 m with eleven of them inside the 30 to 50 m band that the reference has only three in. Built to sample the detectability transition rather than its ends. **Shares its vehicles with the reference scenario**, see the warning below.

**`bursty_attackers`**, what varies: **attack strategy**. Attackers misbehave in bursts at a duty of about 0.2 rather than continuously. This exists to attack persistence based alerting, which a continuously lying attacker satisfies trivially, and it is the axis the VASP framework calls persistent against sporadic.

  Marked *supplementary*: under the shared partition 1 class and split combination(s) are empty, so it supports auxiliary evaluation but not headline scoring. Specifically: class 1 has no transmitter in test.

**`offset_receivers`**, what varies: **receiver placement**. Roadside units moved off the centreline to a lateral offset, which changes the conditioning of the receiver array without changing anything else. The array's weakness across the road is the mechanism behind the adversarial result, so a scenario that perturbs it is the control.

  Marked *supplementary*: under the shared partition 2 class and split combination(s) are empty, so it supports auxiliary evaluation but not headline scoring. Specifically: class 1 has no transmitter in test; class 4 has no transmitter in validation.

### A warning that matters more than it looks

**The campaigns were generated with the same random seeds, so some of them contain the same physical vehicles.** `magnitude_sweep` and `highway_sparse` are identical in this respect: at seed 1 they share 102 stations whose true positions agree to four decimal places. `offset_receivers` diverges from the reference by at most 3.3 m and `bursty_attackers` by at most 219 m, so both are close relatives rather than independent draws. Only `highway_dense`, which uses a different road length and vehicle count, is genuinely independent.

**This is why the partition is global.** It is assigned once across the union of all five scenarios, keyed on the physical transmitter, so a vehicle sits in the same partition everywhere it appears. Training on one scenario and scoring on another is therefore safe. **Do not re-partition per scenario**, and do not assume two scenarios are independent samples.

---

## Classes

Station counts, not row counts. One station produces thousands of windows, so a per class score read over rows can rest on two or three vehicles.

| id | name | stations | windows | description |
|---|---|---|---|---|
| 0 | `benign` | 519 | 1,152,169 | Honest station. Carries receiver positioning error rather than claiming its exact position. |
| 1 | `pos_const_offset` | 18 | 37,312 | Position falsification at a constant offset, realised displacement 71 to 233 m. |
| 3 | `pos_offset_random` | 22 | 47,797 | Position falsification redrawn every message, so the claim is self inconsistent. |
| 4 | `pos_replay` | 15 | 36,534 | A previously transmitted position re-sent, so the claim lags the truth. |
| 5 | `speed_falsify` | 23 | 50,391 | Claimed speed inconsistent with claimed displacement. |
| 6 | `sybil` | 21 | 114,257 | One physical station transmitting under several identities. |
| 7 | `dos_rate` | 21 | 29,776 | High rate transmission, denial of service against the channel. |
| 8 | `sps_manipulation` | 18 | 37,876 | Semi persistent scheduling manipulation. INERT in this simulator, see limitations. |
| 11 | `pos_small_offset` | 22 | 46,837 | Position falsification at a constant offset, realised displacement 20 to 25 m. |
| 12 | `dos_low_rate` | 21 | 41,711 | Low rate denial of service, below the obvious volumetric signature. |
| 13 | `pos_medium_offset` | 20 | 46,342 | Position falsification at a constant offset, realised displacement 47 to 60 m. |

The three constant offset classes, 11 then 13 then 1, are **one mechanism at three magnitudes**, chosen against the benign positioning error so the set brackets the point at which detection becomes possible rather than sitting to one side of it. Their realised displacements do not overlap. Treating them as three unrelated classes loses the axis they were built to provide.

## Partitions

Frozen, shipped with the dataset, and reproducible from `analysis/make_release_splits.py`. Split **by physical transmitter**, not by claimed identity, so a sybil vehicle's several identities stay together and no vehicle appears on both sides of a boundary. Stratified so every class reaches every partition. Counts below are vehicles.

| class | train | validation | test |
|---|---|---|---|
| 0 | 493 | 164 | 164 |
| 1 | 20 | 7 | 7 |
| 3 | 23 | 8 | 8 |
| 4 | 19 | 6 | 6 |
| 5 | 22 | 7 | 7 |
| 6 | 19 | 6 | 6 |
| 7 | 25 | 8 | 8 |
| 8 | 21 | 7 | 7 |
| 11 | 21 | 7 | 7 |
| 12 | 21 | 7 | 7 |
| 13 | 19 | 6 | 7 |

Window shares: train 59.8 percent, validation 20.1 percent, test 20.0 percent.

A dependence this does not remove, stated rather than hidden: stations inside one seed share a traffic realisation, so grouping by station removes identity leakage and not scenario correlation. A seed level split would remove it, and cannot be used here because five of the eight seeds are missing at least one attack class outright.

## Schema

### Keys and provenance (6)

Identify a row. **Never features.**

| column | type | meaning |
|---|---|---|
| `key_rxNodeId` | int64 | Receiver that made this observation. |
| `key_claimedStationId` | int64 | Station identifier as claimed over the air. |
| `key_window` | int64 | Time window index. |
| `key_txRnti_mode` | int64 | Modal radio identifier seen for this station in this window. |
| `key_observer_role` | object | Whether the receiver is a vehicle or a roadside unit. |
| `key_seed` | object | Simulation seed. Eight independent realisations. |

### Labels (5)

Ground truth from the transmit log. **Never features.**

| column | type | meaning |
|---|---|---|
| `label_attackId` | int64 | Class. See the class table. |
| `label_txNodeId` | int64 | True transmitting node, from the transmit log. |
| `label_attack_purity` | float64 | Share of this window's messages that came from the labelled attacker. |
| `label_is_attack` | int64 | Binary form of label_attackId. |
| `label_clean` | int64 | Window passes the purity threshold. Filter on this before any analysis. |

### Application layer (22)

Computable from message contents alone, which is what a detector without radio access sees.

| column | type | meaning |
|---|---|---|
| `app_n_msgs` | int64 | Messages received from this station in this window. |
| `app_n_cam` | int64 | Cooperative awareness messages among them. |
| `app_n_denm` | int64 | Decentralized environmental notification messages. |
| `app_n_cpm` | int64 | Collective perception messages. |
| `app_iat_mean` | float64 | Mean inter arrival time. |
| `app_iat_std` | float64 | Standard deviation of inter arrival time. |
| `app_iat_min` | float64 | Smallest inter arrival time. |
| `app_claimed_dist_mean` | float64 | Mean distance from the receiver to the CLAIMED position. The acceptance range check. |
| `app_claimed_dist_std` | float64 | Its standard deviation. |
| `app_claimed_speed_mean` | float64 | Mean claimed speed. |
| `app_claimed_speed_std` | float64 | Its standard deviation. |
| `app_dmv_mean` | float64 | Distance moved verification: claimed displacement against claimed speed, mean. |
| `app_dmv_absmax` | float64 | The same, largest magnitude. |
| `app_ssc_mean` | float64 | Sudden speed change between consecutive claims, mean. |
| `app_ssc_absmax` | float64 | The same, largest magnitude. |
| `app_predict_mean` | float64 | Claimed position against the position predicted from the previous claim, mean. |
| `app_predict_max` | float64 | The same, largest. |
| `app_heading_mean` | float64 | Claimed heading against the heading implied by claimed displacement, mean. |
| `app_heading_max` | float64 | The same, largest. |
| `app_accel_absmax` | float64 | Largest implied acceleration between consecutive claims. |
| `app_seq_gaps` | float64 | Gaps in the claimed sequence number. |
| `app_seq_loss_rate` | float64 | Those gaps as a rate. |

### Physical and MAC layer (28)

What the radio measured. This block is what no other public V2X misbehaviour dataset carries.

| column | type | meaning |
|---|---|---|
| `phy_sinr_db_mean` | float64 | Mean signal to interference and noise ratio, decibels. |
| `phy_sinr_db_std` | float64 | Its standard deviation. |
| `phy_tbler_mean` | float64 | Mean transport block error rate. |
| `phy_corrupt_rate` | float64 | Share of received transport blocks that failed. |
| `phy_mcs_mean` | float64 | Mean modulation and coding scheme index. |
| `phy_rsrp_resid_mean` | float64 | Received power against the power the fitted propagation law predicts at the CLAIMED distance, mean. |
| `phy_rsrp_resid_std` | float64 | Its standard deviation. |
| `phy_rsrp_resid_absmax` | float64 | Its largest magnitude. |
| `phy_rsrp_mean` | float64 | Mean per SCI sidelink reference signal received power. Exposed by the additive patch to 5G-LENA. |
| `phy_rsrp_std` | float64 | Its standard deviation. |
| `phy_rsrp_min` | float64 | Its minimum. |
| `phy_rsrp_max` | float64 | Its maximum. |
| `phy_rsrp_count` | float64 | Number of power measurements behind the statistics above. |
| `phy_cbr_pscch_rate` | float64 | Control channel occupancy seen by this receiver, a channel busy measure. |
| `phy_pscch_corrupt_rate` | float64 | Share of control channel decodes that failed. |
| `phy_neighbours` | float64 | Distinct radio identifiers this receiver heard in this window. |
| `phy_track_corr` | float64 | Correlation between measured power and the power predicted from the claimed track, over a long window. Undefined below 8 samples or 2 dB of predicted span. |
| `phy_track_slope` | float64 | Regression slope of the same pair. One means the claim tracks the radio. |
| `phy_track_resid_std` | float64 | Residual spread of the same regression. |
| `phy_track_span` | float64 | Range of predicted power across the window, which says whether there was anything to track. |
| `phy_closest_lag_s` | float64 | Signed time between the claimed closest approach and the measured power peak. Undefined unless the claimed minimum is interior to the window. |
| `phy_closest_lag_abs` | float64 | Its magnitude, which does not cancel in the mean as the signed value does. |
| `phy_closest_power_gap` | float64 | Measured peak power against the power predicted at the claimed closest approach. |
| `phy_rsrp_vs_claimed` | float64 | Measured power minus the power predicted for the claimed distance. |
| `phy_rsrp_voiceprint_min` | float64 | Smallest power difference to another station the same receiver hears in the same window that claims to be far away. Small with a large claimed separation is the Sybil signature. |
| `phy_loss_vs_rsrp` | float64 | Sequence loss rate against what this received power would ordinarily produce. |
| `phy_corrupt_vs_rsrp` | float64 | Corruption rate against the same baseline. |
| `phy_tbler_vs_rsrp` | float64 | Block error rate against the same baseline. |

## Known limitations

Stated here rather than left for a user to discover.

1. **Both radio layer attacks are inert.** Mode 2 grants in 5G-LENA are data driven, so a reserved resource is used only when there is data for it and an attacker cannot hoard the channel. `sps_manipulation` is not weakly detectable, it is not detectable, and resource exhaustion is indistinguishable from a benign station at the same reservation interval. The cross layer argument therefore rests on radio features catching **application layer** attacks.
2. **The main corpus is light traffic**, about 2.5 vehicles per km per lane, and its congestion control barely engages. That is the price of the 6 km road the federated partition requires. A matched dense corpus covers the congested point and any claim about congestion must come from it.
3. **Fixed modulation and coding**, no link adaptation, and an EESM link to system PHY abstraction rather than a full PHY. Both are simulator limits.
4. **The receiver geometry is one straight road** with the roadside units on its centreline. Receivers along a straight road are close to collinear, which is the weakest realistic geometry for position verification and is measured rather than assumed. No junction or curve is covered.
5. **Highway only.** No urban scenario, one car following model, and the aggregate simulated time is short next to the benchmarks this sits beside.
6. **Three classes have fewer than twenty stations**, so a per class score on them rests on single figures per partition and must be read with the station count beside it.

## Licence

The data is intended for **CC BY 4.0**. The generator is an ns-3 contrib module and is **GPL-2.0-only**, because ns-3 and 5G-LENA are. See `LICENSES.md` in the code repository.
