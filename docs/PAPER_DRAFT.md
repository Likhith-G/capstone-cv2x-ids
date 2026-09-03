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

Full source list and the competitive analysis are in
`docs/research/NOVELTY_POSITION.md`, last checked 29 Aug 2026. **Re-check
before submission.** This is the claim the paper lives or dies on.

### Datasets

**VeReMi and VeReMi Extension** are the reference misbehaviour datasets and are
application layer only: they carry position, speed and a received signal
strength value, and no network or MAC layer measurement. VeReMi Extension adds
realistic sensor error to benign traffic, and this work adopts its positioning
error model directly so that the benign class is comparable. We also evaluate
our application layer detector on VeReMi itself, on the seventeen features both
datasets support, so that our headline negative result is not a property of our
own simulator.

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
model. They reported a correct classification rate of 0.9376 for the physical
layer against 0.8838 for the application layer on position falsification, so
the ordering is theirs and the gap is small in their setting. In ours the
application layer does not merely trail, it scores exactly zero, and the
difference is that their position attacks are VeReMi scale while ours span a
ladder down to the noise floor. This work reproduces the ordering on C-V2X sidelink and builds the fused
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

### The blindness is not a property of our simulator

We evaluate the same application layer detector on VeReMi, on the seventeen
features both datasets support, computed by definitions verified to match ours
exactly across 218,782 windows. Six of its simulations at the highest density
and attacker fraction available, roughly a thousand constant offset attackers.

[RESULT PENDING: `runs/drift/logs/veremi_crossdataset.log`. Both near zero is
the expected outcome and would say the blindness is a property of the attack
rather than of this simulator. A high score there and a low one here would say
the opposite, that something about our corpus hides a signal the application
layer can normally find, and would need explaining before anything else in this
paper is believed.]

**We used the original VeReMi rather than the Extension**, because the
Extension is distributed through a file locker requiring an interactive client.
The substitution matters and is in our favour rather than against it: the
original's benign vehicles are effectively noise free, which is the easiest
possible case for a self consistency detector, and a constant offset is self
consistent by construction so the application layer cannot see it whether or
not benign traffic carries noise.

The cross layer arm cannot be evaluated externally, because no public
misbehaviour dataset carries the radio measurements it needs. After this
comparison that is demonstrated rather than asserted.

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

## 7. Deployment: drift, federation, and the operating point

### The detector does not survive a density it was not trained on

The project brief names non stationarity as its aim, and until this measurement
nothing tested it. Every result above holds training and test in one
distribution: the grouped folds stop a station appearing on both sides, and the
scenario is identical on both sides.

Trained at one traffic density and tested at the other, on two corpora that
share the positioning error model and are both restricted to vehicle observers,
the fused detector loses **0.1543 macro F1 going to light traffic and 0.1222
going to congested**, from in distribution scores near 0.51.

**Fusion does not protect against the shift, and going to light traffic it is
the worst of the three blocks**, losing 0.1543 against 0.1468 for the
application block and 0.1422 for the radio one. Fusion buys detection at a
fixed operating point and nothing against a change of operating point.

**The cost lands on false alarms rather than misses.** Benign F1 falls from
0.902 to 0.672. A detector deployed at the wrong density does not mainly miss
attacks, it alerts on ordinary traffic, which is the failure an operator sees
first and which makes the operating point below conditional on the deployment
matching the training distribution.

**One class shows the mechanism.** Low rate denial of service scores 0.884 in
distribution and 0.114 when a model trained on congestion is tested on light
traffic, because a modest rate increase is defined against an ambient rate and
the ambient rate is exactly what changed. It holds at 0.829 in the reverse
direction, where the model has seen the quieter baseline. Sybil moves the
opposite way, conspicuous when identities are scarce and hidden when the
channel is full of them.

**Nothing drifts inside a single run.** With held out seeds on both sides of a
time cut, the fused block moves by 0.0017 across 60 s, and a prequential curve
trained once and never updated is flat across 57 s and rises across the
boundary where its training data ends. So the transfer cost belongs to the
scenario rather than to time passing, and calling it drift over time would be
wrong.

### Federation at the edge

A client is a roadside unit region: the unit plus every vehicle whose nearest
unit it is. The vehicles contribute measurements, the unit fuses them into one
pooled record per station and window, and the unit federates. Receivers per
region: median 8, tenth percentile 5, which is just above the five receiver
identifiability floor and far below the 39 of the corpus wide study.

**Pooling inside a region is worth +0.0578 macro F1 and wins on all eight
seeds.** Of that, 0.0553 comes from combining measurements at all and 0.0025
from the eleven cross receiver consistency statistics, which do not reach
significance at this receiver count. Averaging is doing nearly all the work
here. At 39 receivers the same statistics are worth 0.0334, so the claim is
that they matter where receivers are plentiful and one region is not where they
are.

**Logit calibration is the only aggregation rule that helps**, +0.0147 macro F1
and +0.0080 MCC, both at p = 0.0078 across eight seeds. Correcting for unequal
local work is reliably worse. The spread between best and worst rule is a fifth
of the spread between seeds, so which rule is chosen matters far less than the
fact that clients see different class mixtures.

**Privacy costs three times what the architecture gains.** Clipping alone costs
0.0341 before any noise, and at the tightest bound measured, an epsilon of 8.3,
macro F1 falls from 0.4775 to 0.3063. The obstacle is the size of the
federation rather than the method: Gaussian noise is divided by the number of
clients sampled per round and this deployment samples 33.

### The operating point

Per window alerting is unusable at every threshold: at 0.90 the detector raises
161 false alerts per observer hour. Counting alert episodes rather than
windows, and requiring a station to look wrong in K of its last M windows,
changes that.

| rule | false alert episodes per region hour | attackers found |
|---|---|---|
| 2 of 3 | 85 | 0.632 |
| 4 of 5 | 12 | 0.565 |
| **5 of 7** | **7** | **0.540** |

**Detection at the operating point follows the magnitude ladder**, 0.591 on the
largest position offset, 0.458 on the mid magnitude one and 0.125 on the
smallest, which is the detection floor of section 5 appearing outside a
controlled comparison. Everything that is not a position lie sits above 0.93.

**State the operating point as two numbers.** Stratified by contact time,
detection is 0.292 for stations in range four windows or fewer and 0.718 above
sixteen, so it is roughly 70 percent of vehicles that linger and under a third
of those passing quickly. The cost of the stricter rule is six seconds of
latency on top of one second of window fill.

---

## 8. Limitations

Eleven are listed in full in `RESULTS.md` section 9 and should not be
compressed away. Three matter enough to state in the body rather than at the
end.

**Both radio layer attacks are inert.** Mode 2 grants in 5G-LENA are data
driven, so a reserved resource is used only when there is data for it and an
attacker cannot hoard the channel. Sensing manipulation scores 0.000 in every
block on three corpora. It is not weakly detectable, it is not detectable. The
cross layer claim therefore rests on radio features catching application layer
attacks, which is still cross layer and still the point, and it should be said
plainly rather than left for a reader to work out.

**The road constraint needs a map.** Bounding the position fit to the
carriageway is what takes localisation error from 65 m to 18 m, and it is the
only part of the method depending on infrastructure data rather than on what a
receiver measures. Carriageway extent is static, so the dependency is modest,
but it is one the rest of the method does not have.

**One road geometry.** Every figure here is for receivers strung along the
length of a straight carriageway. A junction, a curve, or receivers set back
from the road would break the collinearity that makes lateral position
unobservable, and this work does not measure by how much. The lateral
degeneracy is the mechanism behind both the detection floor and the strongest
evasion, so a different geometry could move both.

---

## 9. What would come next

Not in this paper, and worth naming so the boundary is deliberate.

**Locating the floor properly.** The band that brackets it holds three attacker
stations. A campaign sampling 25 to 60 m densely would place it to within a few
metres instead of within fifty.

**Does the pooled architecture transfer?** The drift measurement is on the
single observer detector, because the cross receiver features live in a
separate table. Whether cooperative detection degrades the same way under a
density shift is unmeasured.

**Does federated training recover the drift loss?** Nothing here shows that it
does. The drift result motivates continual adaptation; it does not demonstrate
that this architecture delivers it, and the two must not be allowed to run
together.

---


## Appendix: what to check before submission

- Re-run `analysis/verify_results.py` and confirm every check passes. Every
  number in this file is pinned by it.
- Re-check the novelty claim against the literature. It was last checked 29 Aug
  2026 and it is the claim the paper lives or dies on. `NOVELTY_POSITION.md`
  has the competitive table and the closest prior work.
- Confirm section 6's figures come from the rerun across all eight seeds of the
  current corpus rather than the one seed of the superseded one they were
  first measured on.
- Confirm the persistence operating point in section 7 is the rerun figure. The
  zero false alert result from the superseded corpus must not appear anywhere.
- Confirm the VeReMi comparison states that the original release was used
  rather than the Extension, and why: the Extension is distributed through a
  file locker needing an interactive client, and the original's noise free
  benign class is the harsher test for this particular claim rather than the
  easier one.
- Check every figure and table against `RESULTS.md` rather than against this
  draft, and check the draft against the results rather than the other way
  round.
- Confirm no sentence claims federated training recovers the drift loss.
  Nothing measured that.

### The five conclusions that changed when the corpus was regenerated

Worth re-reading before writing anything from memory, because each was
confidently reported in an earlier draft of this work and each is now something
else. They are listed in `MASTER_INDEX.md` section 2. The pattern matters more
than any one of them: a number measured against a benign class with no
positional variance was measuring the absence of variance.
