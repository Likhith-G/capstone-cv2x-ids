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

**The gap the paper addresses.** [Standards establish authenticity and not
semantic correctness. See METHODS_DRAFT section 0 for the specification map;
compress to a paragraph here.]

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

[From RESULTS.md section 1. The table, the positioning error model, the
magnitude ladder, and the ten integrity gates from section 2.]

**The one framing point to make here rather than in limitations.** Benign
vehicles carry receiver error. Without it the benign class has no positional
variance, any displacement at all is separable in principle, and a position
attack is easier to detect than it could ever be in deployment. Adding it moved
fused macro F1 from 0.5578 to 0.5145 over one more class, and the fall is the
point.

---

## 4. A single receiver cannot see a position lie

[RESULTS.md section 3. The three block comparison and the per class table.]

Fused macro F1 0.5145, MCC 0.6635 over eleven classes. The application layer
scores exactly 0.000 on both constant offset classes; the radio layer scores
0.156 and 0.029. Speed falsification scores exactly 0.000 on the radio block,
which is the negative control the claim needs.

The three constant offset classes are near zero to a single observer at every
magnitude, 0.002 at 20 to 25 m, 0.021 at 47 to 60 m and 0.146 at 71 to 233 m,
monotone in displacement.

---

## 5. Pooling measurements, and the detection floor

[RESULTS.md section 3b. The localisation table, the arm comparison, the floor
curve.]

The headline pair: class 13 goes from 0.019 at one receiver to 0.412 pooled,
and both voting arms reach exactly 0.000. Schemes that exchange verdicts have
the same evidence available and recover none of it.

The floor curve is the figure the paper should lead with. A single receiver
never crosses the floor at any magnitude; pooling reaches 0.90 by 50 to 80 m
and 1.00 above. The floor sits at roughly twice the localisation error, which
is why the estimator is the thing to improve.

---

## 6. The attacker that knows the estimator

[RESULTS.md section 4b. The four cell matrix.]

This is the section that makes the paper honest rather than promotional, and it
should not be buried. Unconstrained, the check is defeated: AUC 0.147 at 50 m.
The mechanism is lateral, and the remedy is the road constraint, which takes
localisation error from 65.2 m to 18.2 m and raises detection of the on road
best response at 50 m from 0.282 to 0.398.

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
