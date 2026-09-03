# Paper draft

Written 3 Sep 2026. **Numbers here are copied from `RESULTS.md` and every one
of them is pinned by `analysis/verify_results.py`.** If a number in this file
disagrees with that one, this file is wrong. Do not edit a figure here without
running the verifier.

Structure follows the seven claims in `PAPER_CLAIMS.md`. Methods are in
`METHODS_DRAFT.md` and are not repeated.

---

## Title

Candidates, in order of preference:

1. **What received power can and cannot tell you about a lying vehicle**
2. Cooperative position verification on NR sidelink, and its detection floor
3. A detection floor for position falsification in C-V2X

The first is preferred because the paper's most defensible contribution is a
bound rather than a score, and a title that promises a bound is one the results
can keep.

---

## Abstract

Connected vehicles broadcast position several times a second, signed but not
verified: a station holding valid credentials can transmit a correctly signed
message whose position is false, and no signature check detects it. We generate
a labelled intrusion detection dataset on 3GPP NR sidelink (PC5 Mode 2) in
which benign vehicles carry realistic receiver positioning error, and in which
position falsification appears at three magnitudes chosen to bracket the point
where detection becomes possible rather than to sit on one side of it.

We show that a single receiver cannot detect a constant position offset at any
magnitude the dataset contains, and that pooling received power across
receivers before any decision is taken detects 90 percent of attackers
displaced 50 to 80 m and all of them above 80 m. Combining per receiver
verdicts instead of measurements recovers none of this, which makes the case
for cooperative detection an argument about information rather than about
privacy.

We then bound what that check can do. An attacker who knows the estimator lies
perpendicular to the road, where receivers strung along a carriageway are
nearly collinear and range only measurements barely constrain position, and
defeats the check entirely. Constraining the position estimate to the
carriageway removes that degree of freedom, takes localisation error from 65 m
to 18 m, and leaves an attacker that must remain on the road detectable 85
percent of the time at 100 m. The lies received power cannot see are the lies a
map rejects for nothing, and we argue the pair rather than either half.

---

## 1. Introduction

Connected vehicles broadcast their position, speed and heading several times a
second so that neighbours can act on them. Those broadcasts are signed. In the
European stack every message is wrapped in an ETSI TS 103 097 envelope and
signed with ECDSA under a pseudonym certificate, IEEE 1609.2 does the same in
North America, and a receiver checks that the certificate is valid, unexpired,
authorised for the message type and not revoked.

What no part of that establishes is whether the position inside the message is
true. The signature binds a message to a credential, and no credential can
attest to a measurement the sender itself produced. A station holding valid
credentials can therefore transmit a correctly signed message whose position is
false, and it is indistinguishable at the cryptographic layer from an honest
one. Detecting that is a plausibility problem rather than a cryptographic one,
and it is what misbehaviour detection exists to do.

The obvious plausibility check is the radio itself. A receiver measures the
power it received, and received power falls with distance, so a claim that
places a vehicle somewhere inconsistent with the power it produced should be
visible. This paper measures how far that idea goes, and finds the answer is
further than a single receiver can reach and less far than a cooperative scheme
might promise.

**What is new.** The first labelled multiclass intrusion detection dataset
generated over 3GPP NR sidelink Mode 2, combining sidelink physical and MAC
layer measurements with application layer misbehaviour in one schema. Every
vehicular 5G intrusion detection dataset located runs over the Uu uplink.

**What is more useful than what is new.** The dataset exists to support a
measurement rather than to be a contribution on its own. Position falsification
has a detection floor, that floor is set by the localisation accuracy of the
receivers that can see the vehicle, and a detector evaluated only on
VeReMi-scale offsets of 250 m is being asked an easy question.

### Contributions

1. A labelled NR sidelink misbehaviour dataset with realistic benign
   positioning error and a graded position falsification ladder.
2. The measurement that cooperative detection has to fuse measurements rather
   than verdicts, demonstrated on the magnitude band where it matters.
3. A detection floor for position falsification, located between 30 and 80 m
   and explained by the estimator's own error.
4. The best response of an attacker that knows the estimator, and the road
   constraint that closes it.
5. A federated evaluation under geometric label skew, with the cost of
   differential privacy at deployment scale.

---

## 2. Related work

### Datasets

**VeReMi and VeReMi Extension** are the reference misbehaviour datasets and are
application layer only: they carry position, speed and a received signal
strength value, and no network or MAC layer measurement. VeReMi Extension adds
realistic sensor error to benign traffic, and this work adopts its positioning
error model directly so that the benign class is comparable.

**VASP** implements 68 BSM attacks, far more than this work, and is likewise
application layer. Breadth of attack catalogue is explicitly not a contribution
claimed here.

**5G-NIDD** and **5GCID** carry 5G network layer measurements with multiclass
labels and are not vehicular.

**Melo's 5G-enabled vehicular datasets** are the closest prior work and must be
cited and differentiated explicitly. They use NS-3 with 5G-LENA over four maps
with 45 to 100 vehicles, carry delay and jitter alongside position and speed,
and are the existence proof that this direction is being pursued. They are
binary rather than multiclass, carry no application layer misbehaviour, model
V2X multicast rather than CAM semantics, and run over the Uu uplink rather than
the sidelink. A reviewer who knows this work and does not see it discussed will
assume we did not look.

### Detection

**So, Petit and Starobinski (WiSec 2019)** found physical layer features beat
application layer ones on VeReMi position attacks and did not build the fused
model. This work reproduces the ordering on C-V2X sidelink and builds the fused
model, and finds the application layer is not merely worse but blind.

**Gurjar et al. (2025)** closed the gap that federated learning had not been
validated on vehicular misbehaviour data. That claim is not available and is
not made.

### Cooperative position verification

No prior work performs cooperative multi receiver position verification on NR
sidelink, and no work measures the detection cost of exchanging verdicts rather
than measurements. Both were checked against the 2019 to 2026 literature. The
second is the sharper gap: cooperative schemes trade summary statistics,
misbehaviour reports, reputations or model parameters, and almost never pooled
raw measurements.

### Standards

ETSI TR 103 460 already recognises cooperative and consensus based misbehaviour
detection as a category, and ETSI TS 103 759's misbehaviour report can carry
the evidence this detector produces. What the standards assume is a per station
local decision with cooperation at the level of verdicts, which is precisely
the arrangement this paper measures and finds wanting.

---

## 3. Dataset

Generated with ns-3.42 and 5G-LENA at tag `v2x-1.1`, on a 6 km three lane
carriageway with 90 vehicles and 12 roadside units, over eight seeds of 60 s.
Vehicles follow an intelligent driver model and exchange ETSI CAM, DENM, CPM
and VAM messages under TS 102 687 reactive congestion control, directly over an
NR V2X Mode 2 PC5 sidelink. 1,641,002 windows, 720 stations of which 519 are
benign, eleven classes, 50 features in two blocks of 22 application layer and
28 physical and MAC layer.

The detection unit is one observer's view of one claimed station over one
second. Ground truth never crosses the air interface: the transmitter writes
what is true to one table, each receiver writes only what it received to
another, and the two are joined offline on a message identifier. An assertion
fails the run if any column named for a key or a label reaches the feature
list.

### Benign vehicles do not claim their exact position

Each carries a receiver error following the VeReMi Extension model: an initial
offset drawn uniformly within 5 m per axis, each fix mixing that with the
previous one plus noise proportional to the vehicle's own initial draw, and
occasional multipath excursions at 0.005 per second. The realised benign error
has a median of 4.00 m, a 95th percentile of 5.90 m and a maximum of 14.79 m.

This matters more than it looks. Without it the benign class has no positional
variance, so any displacement greater than zero is separable in principle and a
position attack is asked an easier question than deployment would ask it.
Adding it moved fused macro F1 from 0.5578 over ten classes to **0.5145** over
eleven, and the fall is the measurement rather than a regression.

### Position falsification is a ladder, not a class

The three constant offset classes are one mechanism at three magnitudes, and
the bands are chosen against the benign error so that the set brackets the
point where detection becomes possible rather than sitting on one side of it:

| class | realised displacement | relative to benign 95th percentile |
|---|---|---|
| small | 20.1 to 24.7 m | 3 to 4 times |
| medium | 47.3 to 60.3 m | 8 to 10 times |
| large | 70.8 to 232.7 m | 12 to 39 times |

Their realised displacements do not overlap, which is checked on the first seed
before a campaign is used, because bands that overlap cannot bracket a
threshold. The middle band is the one that matters and it was absent from every
earlier corpus of this work and, as far as we found, from the misbehaviour
datasets in general, which cluster at VeReMi's 250 m scale.

### Integrity

Ten gates run before any model is trained, two of them once per class, and all
pass: duplicate fraction 0.0000 and verbatim train and test overlap 0.0000 at
measurement precision rather than float precision, 1-NN macro F1 0.3466, a
depth three tree at 0.3288, best single feature separability 0.0686, and
maximum absolute correlation with a label column 0.2717.

Comparisons are made at measurement precision, rounding to one decibel, one
millisecond and one metre. At float precision no two continuous features ever
match, so duplicate and overlap tests return zero whether or not the dataset is
degenerate, which makes them worse than useless because they read as
reassuring.

**The one framing point to make here rather than in limitations.** Benign
vehicles carry receiver error. Without it the benign class has no positional
variance, any displacement at all is separable in principle, and a position
attack is easier to detect than it could ever be in deployment. Adding it moved
fused macro F1 from 0.5578 to 0.5145 over one more class, and the fall is the
point.

---

## 4. A single receiver cannot see a position lie

250,000 windows sampled from the corpus, three folds grouped by transmitting
station so no station appears on both sides, 100 trees.

| block | features | macro F1 | MCC |
|---|---|---|---|
| application only | 22 | 0.4878 | 0.6222 |
| radio only | 28 | 0.3554 | 0.5275 |
| **fused** | 50 | **0.5145** | **0.6635** |

**The application layer scores exactly 0.000 on both constant offset classes.**
A constant offset is perfectly self consistent: position, speed and heading all
agree with each other, every application layer plausibility check passes, and
there is nothing to find. Only the radio knows better, and it reaches 0.156 and
0.029. This is the ordering So, Petit and Starobinski report on DSRC,
reproduced on C-V2X sidelink, and here the application layer is not merely
worse, it is blind.

**Speed falsification scores exactly 0.000 on the radio block**, which is the
negative control the claim needs. Received power carries no information about a
claimed speed, and a feature set that found some would be leaking.

**Sybil is the clearest union effect**, 0.852 from the application layer, 0.915
from the radio, 0.959 fused. Each block holds evidence the other lacks.

The three constant offset classes are near zero to a single observer at every
magnitude, 0.002 at 20 to 25 m, 0.021 at 47 to 60 m and 0.146 at 71 to 233 m,
monotone in displacement. **A single receiver cannot resolve a position lie at
any magnitude this dataset contains**, and the ordering is what makes magnitude
an axis rather than a label.

---

## 5. Pooling measurements, and the detection floor

Shadowing is independent per link. A false position is common mode, because one
claimed position must explain every receiver's measured power at once and
cannot, since the geometry it implies is wrong in a different direction at each
receiver. Each receiver contributes only what it already has: its own position,
the position the message claimed, and the power it measured.

43,548 pooled units, median 39 receivers per unit. Fitting a position and a
propagation law jointly, under a road constraint, puts the estimate **18.2 m
from the truth on benign traffic and 18.7 m on the attacker**, so nothing about
the attacker makes it easier to locate. The whole of the difference appears
against the claim, 18.9 m against 140.1 m.

| arm | macro F1 | large offset | mid offset |
|---|---|---|---|
| single receiver | 0.4999 | 0.131 | 0.019 |
| majority vote | 0.4981 | **0.000** | **0.000** |
| soft vote | 0.5006 | **0.000** | **0.000** |
| **pooled** | **0.6279** | **0.590** | **0.412** |

**The mid magnitude class is the sharpest result here.** A displacement of 47
to 60 m is invisible to one receiver at 0.019 and two fifths recovered by
pooling at **0.412**, and both voting arms recover exactly nothing. Running the
same detector at every receiver and combining verdicts has the same evidence
available and does not recover it, because the discriminating quantity is a
relation between measurements rather than a property of any one of them. Soft
voting is what makes this safe to claim: hard voting can never return a class
the base model rarely names, so its zero alone would prove nothing.

### The floor, in metres

Every constant offset attacker placed on one displacement scale, detection
measured per station, benign false flag rate near 0.01:

| displacement | stations | single observer | pooled |
|---|---|---|---|
| 6 to 15 m | 11 | 0.00 | 0.00 |
| 15 to 30 m | 10 | 0.00 | 0.00 |
| 30 to 50 m | 3 | 0.00 | 0.33 |
| 50 to 80 m | 21 | 0.00 | **0.90** |
| 80 to 150 m | 5 | 0.00 | **1.00** |
| over 150 m | 8 | 0.00 | **1.00** |

**A single receiver never crosses the floor at any magnitude, not once.** Its
per window flag rate does climb with displacement, from 0.008 to 0.198, so it
is not blind; it never becomes confident often enough for a station to be
flagged in most of its windows.

**The floor sits at roughly twice the localisation error.** Estimates land
18.2 m from the truth, detection begins between 30 and 50 m and is complete by
80 m. A lie has to exceed the estimator's own uncertainty before there is
anything to see, which is why the estimator moves this line and better features
do not. Its existence is solid; its location is known only to within 30 to
80 m, because the bracketing band holds three attacker stations.

---

## 6. The attacker that knows the estimator

Transmit power cannot beat the pooled check, because the fit removes a constant
power offset analytically: a single power setting slides every receiver's
residual by the same amount and the two parameter fit absorbs it. Measured, a
targeted power adversary reduces the single receiver check to exactly chance,
AUC 0.500 on every class, while the pooled statistic is unchanged to three
decimals at 0.905.

So an attacker who understood the detector would not spend its effort there. It
would choose **where to claim to be**, taking among the positions that serve
its purpose the one leaving the smallest pooled residual. That is the bound
worth having.

**Unconstrained, the check is defeated.** At 50 m of displacement the best lie
leaves a consistency ratio of 1.011 against 1.128 for an honest claim, an AUC
of **0.147**, and three lies in a thousand caught at a five percent false alarm
rate. An AUC below one half means the attacker looks less anomalous than an
honest vehicle, which it manages because the free fit sits tens of metres from
the truth, so the true position is not the residual minimum and a short lie can
be aimed at the minimum instead of away from it. An honest vehicle has no
equivalent freedom.

**The direction explains it.** The best lies are 75 to 85 degrees off the road
axis, which is sideways. Receivers strung along a straight road are nearly
collinear, and range only measurements barely constrain position perpendicular
to a collinear array, so displacing a claim across the road changes every
receiver's distance by almost nothing. That one direction carries most of the
localisation error.

**Such a claim is in the field beside the carriageway.** A map check rejects it
at no cost and with no radio evidence at all. Held within 12 m of the
centreline, the attacker is forced longitudinal, the off axis angle falls to
zero as displacement grows, and it is caught **81 percent of the time at 100 m
and 92 percent at 200 m**.

**Constraining the estimator closes the same gap from the other side.** A
vehicle is on the carriageway or it is not a vehicle, so the position fit is
bounded to the road as a hard constraint rather than a prior. Localisation
error falls from **65.2 m to 18.2 m**, a factor of 3.6, and detection of the on
road best response at 50 m rises from 0.282 to 0.398.

**The pair is the contribution.** The lies received power cannot see are the
lies a map rejects for free, and the lies that survive a map check are the
longitudinal ones received power sees best. Neither statement is available
without the other, and presenting the received power check alone invites a
reviewer to find the lateral hole.

*Caveat to carry: these figures are one seed of an earlier corpus and are being
rerun. The mechanism is geometric and survives; the numbers are provisional.*

---

## 7. Federation, drift, and the operating point

[RESULTS.md sections 3c, 5, 5b, 5c, 6, 6b.]

Three findings, in order of how much they change what a reader believes.

**A density the detector has not seen costs a third of its macro F1**, and
fusion does not protect against it. That is the non stationarity result and it
is what motivates continual adaptation.

**Pooling inside a roadside unit region is worth 0.0578 macro F1 on all eight
seeds**, and 0.0553 of that comes from combining measurements at all rather
than from the consistency statistics, which do not reach significance at eight
receivers.

**The deployable operating point is 7 false alert episodes per region hour at
54 percent of attackers found**, under a 5 of 7 persistence rule costing six
seconds of latency.

Privacy costs three times what the architecture gains, and the reason is the
size of the federation rather than the method.

---

## 8. Limitations

[RESULTS.md section 9, eleven items. Do not compress. The detection floor, the
map dependency and the inert radio layer attacks are the three that matter.]

---

## 9. What to check before submission

- Re-run `analysis/verify_results.py` and confirm every check passes.
- Re-check the novelty claim against the literature; it was last checked 29 Aug
  2026 and it is the claim the paper lives or dies on.
- Confirm section 4b has been rerun across seeds on the current corpus. It is
  one seed of the superseded corpus as of this draft.
- Confirm the VeReMi cross dataset result exists, or state plainly that the
  application layer arm was not evaluated on external data and why.
