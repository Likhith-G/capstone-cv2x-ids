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
can keep. It also sets the reader's expectation correctly for section 11, which
is the half of the paper that says what the method cannot do.

## Venue

**ACM WiSec, chosen 4 Sep 2026.** Write to a security venue. The alternatives
below are ordered, and all three want the same paper, so the structure is
settled by this decision and does not need revisiting if the first submission
fails.

**Why WiSec and not the vehicular venues.** The object of this paper is
received power on PC5 sidelink and what a nearly collinear receiver array does
to it. That is a wireless measurement result, and the contribution is a limit
and a mechanism rather than a system that performs well. Security venues take
papers whose headline is a bound; vehicular networking venues generally want a
system that works. WiSec is also where the prior result this work reproduces
and then bounds was published, so its programme committee contains the people
who know that line of work. That is an argument for and not against.

**Why not VehicleSec.** Its centre of mass is in-vehicle: CAN, ECUs, sensors,
autonomy. Its dataset artefact award went to a CAN bus dataset. This paper is a
radio and network paper and would be the odd one out. Note also that
`docs/research/reports/08_venues.txt` is stale on this point: VehicleSec has
left NDSS and is now a USENIX symposium co-located with USENIX Security, so its
deadline pattern is late February for an August event rather than late December.

### Dates

Verified against the WiSec 2026 call and the published pattern. The 2027 call
was not posted when this was written, so confirm the exact dates when it is.

| | |
|---|---|
| cycle 1 | mid November 2026, notification mid January 2027 |
| cycle 2 | early March 2027, notification mid April 2027 |
| format | 10 pages ACM sigconf excluding bibliography, 12 total; 6 page short |
| review | double blind, thoroughly anonymised |
| artefacts | optional, evaluated after acceptance, badged, and stated to count positively |

**Cycle 1 is a cheap roll and cycle 2 is the real target.** The call states
that a paper rejected in the first round may be resubmitted to the second, and
that authors may request the same reviewers by supplying a letter detailing the
revisions. A November submission therefore buys expert reviews in January and
roughly seven weeks to act on them, at no cost to the March attempt. Decide in
late October, once the capstone is submitted, whether the draft is ready enough
for November to be worth the effort. Do not rush it there; the March cycle is
the one that has to be good.

### The structural consequence

A security venue wants the adversarial section early and needs little standards
background. A vehicular networking venue is the reverse, and would want the
sidelink and congestion control detail that is currently compressed into the
dataset section. Do not write to both.

### The artefact ordering, which is irreversible if done wrong

Review is double blind and artefact evaluation happens only after acceptance.
**Do not deposit the dataset under his name, or push a public repository that
identifies the authors, before the submission is in.** The anonymised artefact
has to be a separate deposit. And nothing in `docs/` that is gitignored may go
into any release: those files name defects the team has not seen.

---

## Structure, and what it is mapped onto

Research report 21 surveyed what actually gets accepted as resource led work at
WiSec, NDSS, CCS, IEEE S&P and USENIX Security. Those venues run no separate
dataset track, so a dataset there supports a scientific argument rather than
standing alone, and the accepted papers converge on a ten part shape. This draft
is ordered onto it.

| the shape | here | budget for a 10 page core |
|---|---|---|
| problem and benchmark gap | 1, 2 | |
| security model | 3 | |
| design requirements | 4 | |
| generation methodology | 5 | 4 to 4.5 pages, sections 4 to 7 |
| label and provenance methodology | 6 | |
| characterisation and quality control | 7 | |
| benchmark task and evaluation protocol | 8 | |
| baseline results and failure analysis | 9 | 1.8 to 2.2 pages, sections 8 and 9 |
| the security insight the benchmark enables | 10, 11, 12 | the rest |
| scope, limitations, ethics, release | 13, 14 | 0.5 to 0.75 pages |

As proportions: 35 to 50 percent on generation, labels, characterisation and
quality; 15 to 25 percent on baselines; 5 to 10 percent on limitations. **A novel
detector is not required.** The single receiver unidentifiability result and the
cooperative recovery already constitute a security finding, which is what the
dataset is here to support.

Sections 4 to 7 replaced a single "Dataset" section. The requirements in 4 are
referenced by tag from 5 to 7, so a reader can check the instrument against the
question rather than taking it on trust.

---

## Where every number in this file comes from

| section | source log |
|---|---|
| 3 dataset | `campaign_gnss/logs/merge.log`, `validate.log`, `check_seed1.log` |
| 4 single receiver | `campaign_gnss/logs/benchmark.log` |
| 4 four learner families | `campaign_gnss/logs/model_independence.log` |
| 4 plausibility baseline | `campaign_gnss/logs/plausibility_baseline.log` |
| 4 cross dataset | `drift/logs/veremi_crossdataset.log` |
| 5 pooling and floor | `campaign_gnss/logs/pooled_road.log`, `offset_floor_full.log` |
| 5 the geometric bound | `campaign_gnss/logs/geometry_bound.log`, `geometry_bound_regions.log` |
| 6 adversary | `drift/logs/br_gnss_*.log` |
| 6 receiver placement | `campaign_gnss/logs/geometry_placement.log` |
| 7 drift | `drift/logs/density_gnss.log` |
| 7 federation | `campaign_gnss/logs/federated_regions*.log`, `dp_sweep.log` |
| 7 federating across the shift | `drift/logs/federated_drift_dense.log` |
| 7 operating point | `campaign_gnss/logs/persistence.log` |
| 8 calibration | `campaign_gnss/logs/calibration.log` |

---

## Abstract

Connected vehicles broadcast position several times a second, signed but not
verified: a station holding valid credentials can transmit a correctly signed
message whose position is false, and no signature check detects it. We generate
a labelled intrusion detection dataset on 3GPP NR sidelink (PC5 Mode 2) in
which benign vehicles carry realistic receiver positioning error, and in which
position falsification appears at three magnitudes chosen to bracket the point
where detection becomes possible rather than to sit on one side of it.

A single receiver cannot detect a constant position offset at any magnitude the
dataset contains, and we show it three ways that do not share a failure mode:
four learner families, the field's calibrated plausibility checks, and the
measurement model itself, which is unidentifiable at one receiver and so admits
no position estimate at any observation length.

Pooling received power across receivers before any decision is taken detects 90
percent of attackers displaced 50 to 80 m and all of them above 80 m. **The
crossing is located rather than bracketed: 50 percent detection at 47.2 m, with
a 95 percent interval of 39.3 to 57.4 m.** That figure is the paper's central
quantity, and it is a property of the problem rather than of the detector.
Combining per receiver verdicts instead of measurements recovers none of it,
which makes the case for cooperative detection an argument about information
rather than about privacy.

We then bound what that check can do. Error ellipses for received signal
strength position verification are not new, and neither are estimator aware
adversaries; what we add is the rule and its independent confirmation. The
ellipse for this receiver geometry, computed from the propagation law and its
residual with no classifier involved, points 79.3 degrees off the road axis. An
attacker given free choice of where to claim to be, searched by brute force over
72 directions with no knowledge of that bound, lies at 75 to 85 degrees and
defeats the check entirely: receivers strung along a carriageway
are nearly collinear, and range only measurements barely constrain position
across it.

Constraining the position estimate to the carriageway removes that degree of
freedom, takes localisation error from 65 m to 18 m, and leaves an attacker
that must remain on the road detectable 85 percent of the time at 100 m. Moving
the receivers off the centreline instead has an optimum, is worth about a fifth
of the error, and still leaves the geometry 2.4 times weaker across the road
than along it, so the weakness cannot be placed away. The lies received power
cannot see are the lies a map rejects for nothing, and we argue the pair rather
than either half.

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

**What is new.** To the best of our knowledge, as of September 2026, the first
publicly released dataset of labelled V2X misbehaviour generated over 3GPP NR V2X
PC5 sidelink Mode 2 that co-registers standards compliant ETSI messages with
receiver observed physical and MAC layer measurements. Every vehicular 5G
intrusion detection dataset we located runs over the Uu uplink, and the public
V2X datasets that do carry a radio measurement are IEEE 802.11p rather than
C-V2X. The claim is deliberately dated and hedged: a literature search cannot
exclude an unannounced release.

**What is more useful than what is new.** The dataset exists to support a
measurement rather than to be a contribution on its own. Position falsification
has a detection floor, that floor is set by the localisation accuracy of the
receivers that can see the vehicle, and a detector evaluated only on
VeReMi-scale offsets of 250 m is being asked an easy question.

### Contributions

1. **A detection floor for position falsification, established three ways that
   do not share a failure mode**: four learner families, a calibrated
   implementation of the field's standard plausibility checks, and the
   measurement model itself, which is unidentifiable at a single receiver.
2. **The array's weak information axis, stated as an attack rule and validated
   against an independent search.** The error ellipse for the array points 79.3
   degrees off the road axis and an attacker searching 72 directions with no
   knowledge of it lies at 75 to 85. Error ellipses for position verification
   are not new, see section 2; what we add is the rule that an estimator aware
   attacker at fixed displacement should take the weakest eigenvector, and a
   measured angle agreeing with it. The bound also shows the free position fit
   is barely identifiable inside one roadside unit region, which is a controlled
   measurement of a standard geometric result rather than a new one.
3. **The measurement that cooperative detection has to fuse measurements rather
   than verdicts**, on the magnitude band where it matters: 0.019 at one
   receiver, 0.412 pooled, and exactly 0.000 for both voting schemes.
4. **The best response of an attacker that knows the estimator, and the pair of
   checks that answers it.** The road constraint takes localisation error from
   65 m to 18 m; moving the receivers instead has an optimum, is worth a fifth
   of the error, and does not remove the direction the attacker uses.
5. **A federated evaluation under geometric label skew, including the negative
   result that federating across densities does not recover what a density
   change costs**, with the cost of differential privacy at deployment scale and
   the operating point a persistence rule reaches.
6. A labelled NR sidelink misbehaviour dataset with realistic benign
   positioning error and a graded position falsification ladder, whose bands are
   chosen against that error so the set brackets the detection threshold. To the
   best of our knowledge, as of September 2026, it is the first publicly released
   dataset of labelled V2X misbehaviour generated over 3GPP NR V2X PC5 sidelink
   Mode 2 that co-registers standards compliant ETSI messages with receiver
   observed physical and MAC layer measurements, including per SCI sidelink
   reference signal received power. It is
   the instrument the results above are measured with rather than the headline,
   because application layer breadth and traffic realism are settled by VeReMi
   NextGen and neither is claimed here.

### What this paper does not claim

Stated here rather than left to a limitations section, because each is a claim
a reader might reasonably expect and would be wrong to infer.

- **That federated training recovers the drift loss.** We tested it and it does
  not. A federation spanning both densities scores below a model trained on
  either one alone, and doubling its data does not close the gap. Section 12
  reports this as a finding rather than leaving it unexamined, and it argues for
  personalisation, which we have not built.
- **That the cross layer detector catches radio layer attacks.** Both radio
  layer attacks in the dataset are inert in this simulator. The cross layer
  result is radio features catching application layer misbehaviour.
- **That the pooled architecture is robust to drift.** We measured it and it is
  less robust than the single observer detector, losing 0.21 and 0.36 macro F1
  across a density change against 0.15 and 0.12.
- **That the floor is located precisely.** It is located to an interval and
  not to a figure: 50 percent detection at 47.2 m, 95 percent interval 39.3 to
  57.4 m. Quoting the crossing without the interval would overstate it.
- **That a better estimator buys proportionate detection.** It does not. A
  calibrated correction improving the road constrained localisation median by 29
  percent moved the located floor by 10 percent and the persistence operating
  point not at all. The estimator matters where the floor is and nowhere else.
- **Any priority over cooperative position verification, error ellipses for it,
  estimator aware adversaries, or evaluation against displacement.** All four
  have prior art, named in section 2.
- **That angular spread mattering more than receiver count is a new result.** It
  is standard Fisher information and geometric dilution of precision. What is
  ours is the size of the effect in this setting.

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

**VeReMi NextGen** (Hermann, Remmers, Eisermann, Erb and Kargl, IEEE VNC 2026)
is the current state of the lineage and supersedes the Extension as the
application layer benchmark: fifteen attack types, urban and highway scenarios
from the InTAS trace, three driver profiles, and predefined training,
validation and test partitions, with attacks deliberately harder than the
Extension's. It is generated in Eclipse MOSAIC and carries application layer
message logs.

**We evaluate on it.** Section 9 reports our application layer detector on
NextGen's highway scenario, and the result reproduces there and is sharper than
on the earlier release: a self inconsistent position lie is caught at 0.9570 and
a self consistent one at 0.1460, against 0.9644 and 0.3382 on the original.

We state the relationship plainly because it decides what this paper is for.
**Attack breadth and traffic realism at the application layer are settled by
NextGen and are not contributions claimed here.** What NextGen does not carry
is any physical or medium access layer measurement, and it is not generated
over a 3GPP sidelink stack, so it cannot express the question this paper asks:
what received power at several receivers can and cannot establish about a
claimed position. Our dataset is the instrument that makes that question
measurable, not the result.

### Against the field, on the field's own axes

Built from the comparison tables that appear in published work rather than from
axes chosen here: Yakan's survey, the VeReMi Extension and DARE dataset
descriptions, and VASP's Table III, which compares on attack count, attack
strategy and attacked fields. VeReMi NextGen adds predefined splits and generator
availability, and names their absence as a limitation of everything earlier.

| | VeReMi 2018 | VeReMi Ext. 2020 | VASP 2023 | NextGen 2026 | this work |
|---|---|---|---|---|---|
| simulator | Veins, OMNeT++, SUMO | Veins, F2MD | Veins | Eclipse MOSAIC, InTAS | ns-3, 5G-LENA |
| radio | 802.11p | 802.11p | 802.11p | 802.11p | **NR V2X PC5 sidelink** |
| misbehaviour types | 5 | 19 | 68 | 15 | **10** |
| attack strategy | persistent | persistent | persistent, sporadic | persistent | **persistent, sporadic** |
| scenario coverage | urban | urban | urban | urban, highway, 3 driver profiles | highway, 5 scenarios varying 4 factors |
| physical layer | RSSI | RSSI | none | none | **28 PHY and MAC features, incl. per-SCI RSRP** |
| benign positioning error | none | modelled | none | modelled | **modelled and quantified** |
| magnitude as an axis | no | no | no | no | **yes, three non-overlapping bands** |
| adversarial integrity gates | no | no | no | no | **yes, ten** |
| predefined splits | no | no | no | **yes** | **yes** |
| public generator | yes | yes | yes | **yes** | **yes** |

**Where we are behind, stated plainly.** Ten misbehaviour types against VASP's 68,
VeReMi Extension's 19 and NextGen's 15. Highway only, where NextGen covers urban
and highway with three driver profiles. Breadth of attack catalogue and traffic
realism are settled by that work and are not claimed here.

**Where the difference is a difference in kind rather than in degree.** The radio
row is the one that matters: this is the only entry generated over a 3GPP
sidelink, and the only one carrying receiver-observed physical and MAC layer
measurements rather than at most a single received signal strength column. The
three rows below it, a quantified benign positioning error, magnitude as an axis,
and adversarial rather than confirmatory validation, are what let a detection
floor be measured at all rather than a score be reported.

**VASP** implements 68 BSM attacks, far more than this work, and is likewise
application layer. Breadth of attack catalogue is explicitly not a contribution
claimed here.

**5G-NIDD** and **5GCID** carry 5G network layer measurements with multiclass
labels and are not vehicular.

**Cross layer intrusion detection outside V2X has already run the comparison
this paper runs inside it, and must be cited.** A 2026 study of Open RAN
(arXiv:2606.22450) evaluates application layer flow records against radio
telemetry against the two fused, which is structurally the ablation of section 9.
It is a cellular access network rather than a vehicular one, and it fuses flow
records rather than message semantics, so the comparison here remains the first
we are aware of **for vehicular misbehaviour**. The qualifier is not decoration:
without it the claim is false.

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

Cooperative position verification is not new and we do not claim it.
Leinmuller et al. introduced autonomous and cooperative position verification
sensors over neighbour tables and beacons (ACM VANET 2006, Security and
Communication Networks 2008), and the field's canonical survey (van der
Heijden, Dietzel, Leinmuller and Kargl, IEEE Communications Surveys and
Tutorials 21(1), 2019) reviews a decade of received signal strength schemes
built on the idea.

Two positions in that survey are what this paper is placed against.

**The first is a standing negative result about the method we use.** The survey
reports Yao et al. (IEEE TMC 2018) finding that one cannot directly apply RSSI
measurements, and that using a propagation model to estimate the validity of
messages through the RSSI is unlikely to give reasonable results. That is
precisely the method here, and our answer is that the claim is correct about
the observation unit and not about the method. At a single receiver we confirm
it in the strongest available form: no learner we tried detects a constant
position offset at any magnitude our dataset contains. Pooled across receivers
the same propagation model detects 90 percent of attackers displaced 50 to 80 m.
The contribution is locating the boundary between those two statements, not
proposing the statistic.

**The second is a gap the survey names and no one has measured.** Of the
witness based schemes it reviews, it observes that they do not account for
scenarios with a low number of witnesses. We measure that dependence: five
receivers is an identifiability floor set by the four free parameters of the
fit, a real roadside unit region carries a median of eight, and the cross
receiver consistency block is worth 0.0025 macro F1 at eight receivers against
0.0334 at thirty nine.

**The third is prior art on the bound itself, and it constrains what section 10
may claim.** Yan, Malaney, Nevat and Peters (IEEE TVT 63(7), 2014) construct a
Fisher information matrix for position from received signal strength, invert it
into a Cramer-Rao error ellipse, and test whether an estimate falls outside a
threshold scaled ellipse around the claimed position, choosing that threshold by
mutual information. The work is explicitly motivated by intelligent transport
systems, and the same group extends it to Rician fading (IEEE TVT 65(7), 2016).
**So this paper does not claim the first information theoretic limit for
detecting falsified vehicular positions, and must not be read as doing so.**

Ihsan, Malaney and Yan (arXiv:1904.05610, 2019) go further in the direction that
matters most here. Their attacker chooses its claimed position by minimising the
Kullback-Leibler divergence between the received power distribution expected at
the claim and the one its true position generates, subject to a minimum
displacement, and they report that the geometry of their three verifying units
makes the optimised claims cluster. They also evaluate detection at several
displacement magnitudes. **So neither an estimator aware adversary nor an
evaluation against displacement is new.**

What is left, and it is narrower than the headline those papers might suggest, is
three things. First, **non-identifiability at a single receiver**: with the
intercept and path loss exponent unknown, one receiver at one geometry cannot
estimate position at any observation length, which is a rank deficiency rather
than a large variance and is not the regime those papers analyse. Second, **the
weak axis stated as a rule and checked against an independent search**: that an
estimator aware attacker at fixed displacement should choose the eigenvector of
the smallest eigenvalue of the position information matrix follows locally from
the same geometry, but we found no source stating it as such or comparing a
predicted angle against a brute forced one. Third, **a displacement resolved
detection floor measured against a nonzero benign positioning error
distribution**; prior work imposes minimum displacement constraints on the
attacker rather than sweeping magnitude against real benign variance.

**On the receiver geometry result, we claim less than we first wrote.** That
angular spread rather than receiver count governs a position fit is standard
Fisher information and geometric dilution of precision, and vehicular cooperative
positioning already uses that quantity to weight neighbours. What we contribute
is the controlled measurement in this setting and its size: at equal receiver
count the across-road bound is 36.4 m corpus wide against 6.2 km inside a single
roadside unit region. That is an empirical consequence for misbehaviour
detection, not a new result in estimation theory.

What we did not find in the 2019 to 2026 literature is any measurement of the
detection cost of exchanging verdicts rather than measurements, and no
cooperative verification on NR sidelink. Cooperative schemes trade summary
statistics, misbehaviour reports, reputations or model parameters, and almost
never pooled raw measurements.

### Standards

ETSI TR 103 460 already recognises cooperative and consensus based misbehaviour
detection as a category, and ETSI TS 103 759's misbehaviour report can carry
the evidence this detector produces. What the standards assume is a per station
local decision with cooperation at the level of verdicts, which is precisely
the arrangement this paper measures and finds wanting.

---

## 3. Threat model

A security venue reads this before it reads any result, and the draft did not
have one. Stated as capabilities the adversary has and does not have, because
every result in the paper is conditional on this boundary.

**What the adversary is.** An *insider*. It holds a valid pseudonym certificate,
so every message it sends carries a correct ETSI TS 103 097 signature and passes
every cryptographic check a receiver can perform. This is the case the
cryptography is not built to address, and it is the whole reason misbehaviour
detection exists as a field.

**What it controls.**

| capability | how the dataset exercises it |
|---|---|
| the contents of its own messages: position, speed, heading | the seven falsification classes, including a three magnitude position ladder |
| its transmission rate and timing | the two denial of service classes, and the sporadic variant that attacks the persistence rule |
| how many identities it presents, within one physical radio | the sybil class, four claimed identities per vehicle |
| its transmit power | section 9 measures a check that this defeats outright, to chance, on every class |
| its claimed position given full knowledge of the verifier | section 11, where it knows the receivers' positions, the propagation model and the statistic, and searches 72 directions |

**What it does not control, and these are the assumptions the results rest on.**

- **Where it physically is.** It can lie about its position; it cannot be
  somewhere else. Every result in this paper is ultimately an exploitation of
  that single asymmetry.
- **Other stations' credentials.** No key compromise, no impersonation of a
  specific victim, no certificate forgery.
- **The receivers.** They are honest. RESULTS.md 6c treats colluding receivers
  separately and quantifies the cost of that assumption rather than assuming it
  away.
- **The physical channel.** No jamming, no directional or beamformed
  transmission, no signal replay at the waveform level. The pooled statistic's
  invariance to transmit power holds for isotropic antennas and would not hold
  against a transmitter that beamforms, which is stated in the limitations
  rather than hidden.

**Deliberately out of scope, and named rather than ignored.** Jamming, because a
jammer denies service rather than lying and is a different detection problem
reached through loss and interference rather than message contents, and nothing
in this feature set is aimed at it. Eavesdropping, because a passive observer
breaks confidentiality rather than integrity and a misbehaviour detector is the
wrong instrument. Both appear on the standard V2X attack taxonomy, so their
absence is a scope decision rather than an oversight.

**What the adversary is assumed to know.** Section 9 assumes nothing. Section 11
assumes everything: receiver positions, the propagation model, the statistic and
the constraint. Those are deliberately generous, because a bound is only worth
reporting if the adversary it bounds is stronger than any real one.

---

## 4. Design requirements

What the dataset had to satisfy before any of it was generated, stated as
requirements so that a reader can check the instrument against the question
rather than taking it on trust. Each one exists because a dataset that fails it
cannot answer section 3's threat model.

**R1. The radio must be real, and it must be sidelink.** The question is what
received power can establish about a claimed position, so the physical layer has
to be measured rather than modelled at the application layer, and it has to be
the link vehicles actually use. Every vehicular 5G intrusion dataset we located
runs over the cellular uplink, where the receiver is a base station rather than
another vehicle, and the geometry that makes cooperative verification possible
does not exist.

**R2. The benign class must have real positional variance.** A dataset whose
honest vehicles report their exact coordinates makes any displacement separable
in principle and asks position falsification an easier question than deployment
ever will. This is the requirement most often missed, and it is the one that
decides whether a detection floor can be observed at all.

**R3. Attack magnitude must be an axis, not a label.** A detector evaluated at a
single offset yields a score. A detector evaluated across a graded ladder that
brackets the detectability threshold yields a limit. The bands must not overlap,
or they cannot bracket anything.

**R4. No feature may be computable only with information the receiver does not
have.** Not as a review step but as a structural property of the pipeline, since
a ground truth leak is the defect most likely to survive review and most likely
to produce a headline score.

**R5. Validation must be adversarial rather than confirmatory.** A suite that
asks whether the expected signature is present passes on a degenerate dataset.
It has to ask whether the signature is the *only* difference.

**R6. Benign traffic must be a standards-compliant message mix.** If honest
vehicles send only one message type, then message type is a label, and a detector
learns the generator rather than the misbehaviour.

---

## 5. Generation

**Five scenarios, each varying one factor**, 7.9 million windows over 24 seeds.
Every result in this paper is measured on the reference scenario unless it says
otherwise; the others exist so that a detector shown to work here can be shown
not to work elsewhere, which is what sections 12 and 10 do with them.

| scenario | what varies | windows | seeds |
|---|---|---|---|
| `highway_sparse` | the reference, 2.5 veh/km/lane | 1,641,002 | 8 |
| `highway_dense` | **density**, 20 veh/km/lane, congestion control saturated | 3,657,495 | 3 |
| `magnitude_sweep` | **attack magnitude coverage**, both offset draws widened to sample the detectability transition | 1,220,021 | 6 |
| `bursty_attackers` | **attack strategy**, misbehaviour at a duty of 0.2 rather than continuous | 792,709 | 4 |
| `offset_receivers` | **receiver placement**, roadside units moved off the centreline | 605,481 | 3 |

**The scenarios are not independent samples and the release says so.** They were
generated with the same random seeds, so several contain the same physical
vehicles: `magnitude_sweep` and `highway_sparse` share 102 stations at seed 1
whose true positions agree to four decimal places. The partition is therefore
assigned once across their union and keyed on the physical transmitter, so a
vehicle sits on the same side of the boundary in every scenario and training on
one while scoring on another is safe. Only `highway_dense`, which changes road
length and vehicle count, is a genuinely independent draw, and it is the pair used
for the density transfer in section 12 for exactly that reason.

The reference scenario: ns-3.42 with the 5G-LENA `nr` module at tag `v2x-1.1`, on
a 6 km three lane carriageway with 90 vehicles and 12 roadside units, over eight
seeds of 60 s.
Vehicles follow an intelligent driver model with three vehicle classes and
exchange ETSI CAM, DENM, CPM and VAM messages under TS 102 687 reactive
congestion control, directly over an NR V2X Mode 2 PC5 sidelink (**R1**, **R6**).

Each message type is emitted from its own triggering conditions rather than on a
fixed schedule, so the message mix responds to what the vehicle is doing. Under a
constant velocity mobility model the CAM trigger degenerates to a deterministic
interval, which is one reason the mobility model is a car following one rather
than a convenience.

**One patch to the simulator, and it is what the dataset is for.** 5G-LENA
computes a per-SCI sidelink reference signal received power and never exposes it.
A three file additive patch surfaces it. Without that patch the strongest
cross-layer feature does not exist and the dataset is application layer like
every other one.

**A limit of the simulator, stated here rather than in the limitations.** Mode 2
resource grants are data driven, so a reserved resource is used only when there
is data for it and no attacker can hoard the channel. Both radio layer attacks in
the catalogue are therefore inert, which is a property of ns-3 rather than of
C-V2X, and it means the cross layer result is radio features catching
**application layer** misbehaviour.

---

## 6. Labels and provenance

**Ground truth never crosses the air interface** (**R4**). The transmitter writes
what is true to one table. Each receiver writes only what it received to another.
The two are joined offline on a message identifier, after the fact, in a step no
feature can see.

The feature builder opens only receive side tables. One function is permitted to
read the transmit log, and an assertion fails the run if any column named for a
key or a label reaches the feature list. This is a structural guarantee rather
than a review step: a feature a real receiver could not compute cannot enter the
dataset by accident.

**One narrow exception, named because it is the only one.** The binding between a
decoded radio measurement and the message it carried is reconstructed from the
transmit log, because a nearest-time join misattributes badly under load. That
recovers an observable a real receiver has by construction, namely which radio
sent the message it just decoded, rather than leaking one it does not.

Every row also carries provenance columns, the seed, the receiver, the claimed
station, the window and the true transmitter, kept as metadata for grouping and
audit and never as features.

---

## 7. Characterisation and quality control

1,641,002 windows, 720 physical transmitters of which 519 are benign, eleven
classes, 50 features in two blocks of 22 application layer and 28 physical and
MAC layer. The detection unit is one observer's view of one claimed station over
one time window.

### Benign vehicles do not claim their exact position

Each carries a receiver error following the VeReMi Extension model: an initial
offset drawn uniformly within 5 m per axis, each fix mixing that with the
previous one plus noise proportional to the vehicle's own initial draw, and
occasional multipath excursions at 0.005 per second. The realised benign error
has a median of 4.00 m, a 95th percentile of 5.90 m and a maximum of 14.79 m
(**R2**).

Without it the benign class has no positional variance, so any displacement
greater than zero is separable in principle and a position attack is asked an
easier question than deployment would ask it. The argument is from construction
rather than from a before and after score, and deliberately so: an earlier corpus
without the error model scored higher, but it also carried one class fewer, so
the difference between the two numbers is not attributable to the error model
alone and must not be presented as though it were.

### Position falsification is a ladder, not a class

The three constant offset classes are one mechanism at three magnitudes, and the
bands are chosen against the benign error so the set brackets the point where
detection becomes possible rather than sitting on one side of it (**R3**):

| class | realised displacement | relative to benign 95th percentile |
|---|---|---|
| small | 20.1 to 24.7 m | 3 to 4 times |
| medium | 47.3 to 60.3 m | 8 to 10 times |
| large | 70.8 to 232.7 m | 12 to 39 times |

Their realised displacements do not overlap, which is checked on the first seed
before a campaign is used, because bands that overlap cannot bracket a threshold.
The middle band is the one that matters and it was absent from every earlier
corpus of this work and, as far as we found, from the misbehaviour datasets in
general, which cluster at VeReMi's 250 m scale.

### The integrity gates are adversarial, not confirmatory

Ten gates run before any model is trained, two of them once per class, and all
pass (**R5**): duplicate fraction 0.0000 and verbatim train and test overlap
0.0000, 1-NN macro F1 **0.3466**, a depth three tree at 0.3288, best single
feature separability 0.0686, and maximum absolute correlation with a label column
0.2717.

The 1-NN figure is the one to read. A dataset that a nearest neighbour can solve
has been memorised rather than learned, and the earlier pipeline this work
replaces scored 1.000 on exactly that test while passing all 57 of its own
integrity checks, because every one of them asked whether the expected signature
was present and none asked whether it was the only difference.

**Comparisons are made at measurement precision**, rounding to one decibel, one
millisecond and one metre. At float precision no two continuous features ever
match, so duplicate and overlap tests return zero whether or not the dataset is
degenerate, which makes them worse than useless because they read as reassuring.

---

## 8. Benchmark task and evaluation protocol

What a reader has to reproduce to compare against these numbers. Report 21 found
that accepted resource led papers state this explicitly and the draft did not.

**The task.** Eleven class classification of one receiver's view of one claimed
station over one time window. Binary detection is reported alongside but is not
the task: a detector that flags a station without saying what it is leaves an
operator with nothing to act on, and the classes differ enormously in
detectability, which a binary score hides.

**The partition.** Frozen and shipped, `release_splits.csv`. Grouped by
**physical transmitter**, not by claimed identity: sybil is one vehicle claiming
to be several, so grouping on the claimed identifier scatters one vehicle across
partitions and lets a detector be scored on a vehicle it trained on. 720
transmitters split 60, 20, 20 with stratification by class, so every class
reaches every partition. Window shares land at 60.0, 20.1 and 19.9 percent.

**What must be reported, and why each.**

| metric | why it is required |
|---|---|
| macro F1 **and** the Matthews correlation | the two disagree here, and reporting one hides the disagreement. The federated panel's only near significant result is significant on one and not the other |
| per class scores **with station counts** | one station produces thousands of windows, so a per class score over rows can rest on two or three vehicles. Three classes have fewer than twenty stations |
| false positive rate at **true prevalence** | not on the balanced set. Real traffic is overwhelmingly benign and a balanced set's precision says nothing about deployment |
| detection latency including **window fill** | not the forward pass alone. A decision cannot arrive before the window it needs has finished |

**Baselines a comparison must beat, and they are not trivial.** A 1-NN
classifier, which scores 0.3466 here and is the check that the task is not being
won by memorisation. The application only and radio only single layer blocks,
which are the ablation that makes a cross layer claim mean anything. And a
calibrated implementation of the field's standard plausibility checks, thresholded
on benign traffic at a stated false positive rate rather than at a chosen
constant.

**What must not be done.** Do not split by window, do not group by claimed
identity, do not report a per class score without its station count, and do not
merge the three constant offset classes with anything that reads a class label as
a magnitude: they are one mechanism at three magnitudes and their bands do not
overlap by construction.

---

## 9. A single receiver cannot see a position lie

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

Reported over all eleven classes the fused score is 0.5145. One of the eleven,
sensing manipulation, has no signature in this simulator at all, because Mode 2
grants are data driven and an attacker cannot hoard the channel, so it scores
0.000 in every block on every corpus we generated. Over the ten classes that
carry a signature the fused score is **0.5659**. We report the eleven class
figure as primary so that nothing is hidden, and the ten class figure because it
is what the detector achieves on the classes the simulator can express. The
exclusion is mechanistic and was established before these scores existed.

### The blindness is not a property of the classifier

A bound evidenced by one model's failure is a statement about that model. We
therefore repeat the comparison under four learner families that fail in
different ways: a linear model, a boosted tree ensemble, a bagged tree ensemble
and a network. Same rows, same folds, same features.

| class | best of four learners |
|---|---|
| 20 to 25 m | 0.010 |
| 47 to 60 m | 0.052 |
| 71 to 233 m | 0.167 |

The random forest reproduces the table above exactly, which is what makes the
other three comparable to it, and it is the best of the four overall, so nothing
here rests on an unlucky choice of model.

We also compare against the plausibility checks the field standardised on:
acceptance range, distance moved, sudden speed change, position prediction,
acceleration, and a received signal strength check against the claimed distance.
Each threshold is set on the training fold's benign traffic at a 1 percent false
positive rate rather than at a chosen constant. The suite reaches an F1 of 0.252
against 0.682 for the cross layer detector, and **recalls 0.040 of constant
offset attackers against the learned detector's 0.076**. The floor is not an
artefact of learning: a hand built rule set calibrated on the same data does no
better.

The single receiver signal strength check on its own, which is the form the
prior work proposed, recalls 0.010 of them and has a negative correlation
coefficient.

### The blindness is not a property of our simulator

We evaluate the same application layer detector on VeReMi, on the seventeen
features both datasets support, computed by definitions verified to match ours
exactly across 218,782 windows. Six of its simulations at the highest density
and attacker fraction available, roughly a thousand constant offset attackers.

Binary, constant offset attackers against benign. **This is not the same task
as the eleven class table above**, which is one class of eleven over twenty two
features and reads exactly 0.000, so a small positive here does not contradict
the zero there.

| arm | F1 | MCC |
|---|---|---|
| VeReMi, FIXED position (control) | **0.9644** | 0.9575 |
| VeReMi, constant OFFSET | **0.3382** | 0.3149 |
| this corpus, constant OFFSET | **0.0290** | 0.0496 |

Repeated on **VeReMi NextGen**, the current release of that lineage, on its
highway scenario with 476 receivers and 95 attacking senders:

| arm | F1 | MCC |
|---|---|---|
| NextGen, self inconsistent position lie (control) | **0.9570** | 0.9478 |
| NextGen, self consistent constant offset | **0.1460** | 0.1315 |
| this corpus, constant offset | **0.0352** | 0.0535 |

**The ordering is not a property of one dataset generation.** The control works
on both, the self consistent lie is missed on both, and the gap is wider on the
current benchmark than on the old one, a factor of 6.6 against 2.9. A detector
evaluated on NextGen that reports one aggregate over its position attacks is
averaging a lie the application layer can see with one it cannot.

**The control works**, so the seventeen features are capable and the low
numbers are not a broken feature set.

**The middle row was not expected and produced a sharper claim than the one
under test.** VeReMi's offset attackers are partly detectable, and chasing why
shows it is not self consistency doing it: the distance-moved-against-speed
residual has a median of 0.072 m on benign senders and 0.061 m on offset
attackers, indistinguishable. The separation comes from range plausibility.
`app_claimed_dist_mean` is the single most important feature at 0.303, and
VeReMi's attackers claim a median 315.5 m from the receiver against 172.6 m for
benign. They are caught for claiming to be somewhere a vehicle in range would
not be, not for contradicting themselves.

**So there are two thresholds and only one of them is self consistency.** A
constant offset becomes visible at the application layer once it is large
enough to make the claimed position implausible for a vehicle in radio range,
which is a far coarser test. Our ladder sits below that threshold on a 6 km
road; VeReMi's single large offset sits above it.

**This is a methodological point about the field's default benchmark**, and it
belongs in the paper as one. A detector evaluated only at VeReMi scale offsets
earns partial credit from range plausibility and can appear to be performing
self consistency checking when it is not.

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

## 10. Pooling measurements, and the detection floor

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

**The floor sits at roughly twice the localisation error, and the estimator
moves it sublinearly.** RESULTS.md 6b2b: a 29 percent better estimator moved the
crossing by 10 percent and the persistence operating point not at all, so this
paragraph must not promise that a better estimator buys proportionate detection.

**The floor sits at roughly twice the localisation error.** Estimates land
18.2 m from the truth, detection begins between 30 and 50 m and is complete by
80 m. A lie has to exceed the estimator's own uncertainty before there is
anything to see, which is why the estimator moves this line and better features
do not.

**We locate it on a second campaign built to sample the transition.** The bands
above rest on three attacker stations where it matters; the second corpus widens
both offset draws so that 44 attackers span 4 to 233 m with eleven in the 30 to
50 m band, at the same benign false alarm rate. Fitting detection against log
displacement across every station rather than binning gives **50 percent
detection at 47.2 m, with a 95 percent interval of 39.3 to 57.4 m**, and the
band that used to hold one station now holds eleven and reads 0.36. The crossing
falls where the bands say it should. We quote the crossing with its interval,
because a crossing alone would overstate what 44 stations can settle.

### Why a single receiver is not merely bad at this

The measurement model has four free parameters, two of position and two of
propagation, and the propagation pair is free precisely so that the statistic is
invariant to transmit power. One receiver supplies one equation per window with
the same geometry every time, so **a single receiver cannot estimate position
under this model at any observation length.** It can only test whether the power
it received is consistent with the range the claim implies, and that test has a
floor of its own.

Splitting the residual of the fitted propagation law on 1,151,960 benign
observations gives 1.358 dB that persists for as long as a link lasts and
3.830 dB that averages away within one. Watching longer removes the second and
never the first, so the range check keeps a distance ambiguity proportional to
range: 39 m at the first quartile of link distances and **83 m at the median.**

That predicts the ordering of the single receiver scores. Two of the three
offset classes sit entirely below the median ambiguity and only the largest
carries mass above it, and those are the classes scoring 0.002, 0.021 and 0.146.
The bound says which of them could have been detected at all, and the
measurement agrees.

### What the geometry allows

Computing the Cramer Rao bound on position from the same law, with the
propagation parameters eliminated as nuisance because the estimator fits them
freely, which is the equivalent or efficient Fisher information (the Schur
complement of the nuisance block, Shen and Win) rather than a profile
likelihood, puts
a floor under any unbiased estimator on this receiver array. The measured
localisation error sits above it by a factor of 2.3, 65.2 m median radial
against 28.0 m, so the fit is within about a factor of two of what the geometry
allows and its error is not an artefact of the fitting method.

**And the bound is strongly anisotropic**: 36.4 m across the road against 12.3 m
along it, a ratio of three, which is section 11.

**The scale at which receivers cooperate matters more than how many of them
there are.** Pooling corpus wide over a median of 39 receivers gives the 36.4 m
above. The same computation scoped to one roadside unit region, which is the
deployment this paper proposes for federation, gives 6.2 km, because eight
receivers clustered around one unit barely identify four parameters. Units with
10 to 14 receivers give 72.8 m spread over kilometres and 2,148.8 m clustered in
a region: **the same count, a factor of thirty in the bound.** Any claim about
cooperative position verification has to state the receiver geometry it assumes,
and a corpus wide pooling gain is not what one region delivers.

---

## 11. The attacker that knows the estimator

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
leaves a consistency ratio of 1.011 against 1.124 for an honest claim, an AUC
of **0.139**, and three lies in a thousand caught at a five percent false alarm
rate. An AUC below one half means the attacker looks less anomalous than an
honest vehicle, which it manages because the free fit sits tens of metres from
the truth, so the true position is not the residual minimum and a short lie can
be aimed at the minimum instead of away from it. An honest vehicle has no
equivalent freedom.

**The direction explains it, and the geometry predicted it.** The best lies are
75 to 85 degrees off the road axis, which is sideways, found by searching 72
directions at each displacement with no model of why one should win. The
Cramer Rao ellipse of section 10, computed from the propagation law and its
residual with no attacker and no classifier anywhere in it, has its major axis
at **79.3 degrees** from the road. Receivers strung along a straight road are
nearly collinear, range only measurements barely constrain position
perpendicular to a collinear array, and displacing a claim across the road
changes every receiver's distance by almost nothing.

We emphasise the agreement because of what it rules out. The evasion is not a
weakness of our estimator, our feature set or our search: it is a property of
where the receivers stand, and any range based cooperative check on this array
has the same hole in the same direction.

### Standing the receivers somewhere else does not close it

Every roadside unit in our campaign is on the road centreline. That is a real
deployment pattern and it is also the worst case for geometric diversity, so
the obvious question is whether the result is an artefact of the placement.

Recomputing the bound with the units moved to alternating lateral offsets, on
identical pooled units, gives an optimum near 40 m, about three times the
carriageway half width: the across road bound falls from 36.8 m to 29.6 m and
the anisotropy from 2.99 to 2.38. Past the optimum the placement is worse than
doing nothing, and at 200 m it is worse than the centreline, because the
information a receiver carries falls as the inverse square of its distance while
the geometry it adds does not keep up.

**We then generated that deployment and measured it**, on the same three traffic
realisations so that placement is the only difference. The prediction holds: the
across road bound falls 19.1 percent against a predicted 19.6, and the
anisotropy lands at 2.4 against a predicted 2.38. Recomputing the bound under a
hypothetical placement therefore predicts what a campaign delivers, which means
placements can be compared without generating each one.

**And the estimator collects none of it.** Measured localisation error is 65.3 m
on the centreline and 66.6 m at forty metres, unchanged within seed variation,
and the best lie is still eighty degrees off axis. The fit sits a factor of two
above the bound in both placements, so its own inefficiency rather than the array
geometry is what limits it, and improving a floor it was never touching changes
nothing.

So placement is a genuine design parameter with a derived rule, worth about a
fifth of the error in principle and nothing in practice with this estimator.
**It is not a cure**, and the complementary claim below is structural rather
than a repair for a badly placed array. It also says where the remaining
headroom is: the gap between the bound and the fit is a factor of two and the
gap between placements is a fifth, so a better estimator is worth more than a
better array.

**We looked, and the gap is a misspecified propagation model rather than an
inefficient fit.** The residual of the single slope law has a mean that changes
sign with range, from minus two decibels within a hundred metres to plus one and
a half at two to four hundred and minus two and a half beyond a kilometre.
Removing that mean, calibrated offline against claimed distances on traffic a
receiver has no reason to doubt and costing no free parameters, takes the road
constrained localisation error from 18.1 m to 12.8 m, held out across seeds.
Inverse variance weighting on its own makes it worse, because down weighting a
receiver for its noise discards the receivers closest in and those carry the
most position information. **The numbers in this paper describe the
uncalibrated single slope fit, which is also what the RSS checks in the
literature assume**, and a measured thirty percent of the localisation error is
recoverable by a calibration step a deployment can already perform.

**Such a claim is in the field beside the carriageway.** A map check rejects it
at no cost and with no radio evidence at all. Held within 12 m of the
centreline, the attacker is forced longitudinal, the off axis angle falls to
zero as displacement grows, and it is caught **82 percent of the time at 100 m
and 94 percent at 200 m**.

**Constraining the estimator closes the same gap from the other side.** A
vehicle is on the carriageway or it is not a vehicle, so the position fit is
bounded to the road as a hard constraint rather than a prior. Localisation
error falls from **65.2 m to 18.3 m**, a factor of 3.6, and detection of the on
road best response at 50 m rises from 0.264 to 0.380.

**The pair is the contribution.** The lies received power cannot see are the
lies a map rejects for free, and the lies that survive a map check are the
longitudinal ones received power sees best. Neither statement is available
without the other, and presenting the received power check alone invites a
reviewer to find the lateral hole.

*Rerun and confirmed across all eight seeds of the current corpus in four
configurations, on all 29,574 benign triples, which is about nine times the
support behind the measurement it replaces. Every figure is within 0.02 of that
measurement and the off axis angles are identical to the degree.*

**The estimator has since been improved, and this section is where it earns
most.** The propagation law leaves a systematic residual that changes sign with
range; removing a calibrated mean, fitted offline on honest traffic and frozen,
costs no per unit parameters. Localisation on these triples falls **18.3 m to
14.0 m**, the honest consistency ratio tightens from 1.032 to 1.021, and
detection of the on road best response at 50 m rises **0.380 to 0.499**, with
100 m rising 0.843 to 0.903. A tighter honest distribution leaves a lie less room
to hide inside it. **The evasion direction does not move**: the off axis angles
read 35, 15, 5 and 0 degrees against 35, 20, 5 and 0, so the geometry still
decides where an attacker lies and the correction only makes the check tighter.
The full accounting for the change, including where it buys nothing, is in
RESULTS.md 6b2c.

---

## 12. Deployment: drift, federation, and the operating point

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

**The cooperative architecture is more fragile than the single receiver one,
not less.** Everything above measures the single observer detector, because the
cross receiver features live in a separate table. Repeating the comparison on
pooled tables built over vehicle receivers only, so that the presence of
roadside units is not varying alongside density, the pooled fused block loses
**0.2081 going to light traffic and 0.3648 going to congested**, against 0.1543
and 0.1222 for the single observer detector. It is worth more in distribution,
0.63 and 0.67 against roughly 0.51, and it pays more of that back under the
shift.

The mechanism is not a confound to remove. A pooled unit has a median of 34
cooperating receivers on the light corpus and 136 on the congested one, and the
cross receiver statistics are computed over those receivers. For a cooperative
scheme, how many receivers hear you is what traffic density means.

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
are. Section 10's bound says why rather than leaving it as an observation: the
across road localisation bound is 36 m at corpus scale and 6.2 km inside one
region, because eight receivers clustered around one unit barely identify four
parameters. The consistency statistics are worth little in a region because
there is little information in a region to be had.

**Logit calibration is the only aggregation rule that helps**, +0.0147 macro F1
and +0.0080 MCC, both at p = 0.0078 across eight seeds. Correcting for unequal
local work is reliably worse. The spread between best and worst rule is a fifth
of the spread between seeds, so which rule is chosen matters far less than the
fact that clients see different class mixtures.

**Federating across the shift does not repair it, and we measured that rather
than assuming either way.** Federation is introduced above as the answer to
non-stationarity, so the obvious test is whether a federation spanning both
densities recovers what the density change costs. On identical held out clients
and an identical row budget it does not: 0.1305 macro F1 against 0.1774 for a
model trained on the wrong density alone and 0.2966 for one trained on the
right one. Given twice the rows it reaches 0.2243, still below a single density
model trained on half as much data. **Twice as much data from the wrong
distribution loses to half as much from the right one.** A single global model
pulled between two distributions serves neither, so non stationarity argues for
continual and local adaptation and against the one global model this
architecture produces. Personalisation is what the result asks for and we have
not built it.

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
smallest, which is the detection floor of section 10 appearing outside a
controlled comparison. Everything that is not a position lie sits above 0.93.

**State the operating point as two numbers.** Stratified by contact time,
detection is 0.292 for stations in range four windows or fewer and 0.718 above
sixteen, so it is roughly 70 percent of vehicles that linger and under a third
of those passing quickly. The cost of the stricter rule is six seconds of
latency on top of one second of window fill.

### And it does not survive a bursty attacker

An attacker active a fifth of the time, in exponential bursts, keeping its
label throughout. At the same 5 of 7 rule, false alert episodes rise from **7
to 139 per region-hour** while detection falls slightly, and per window
classification collapses from 0.5145 to **0.3762** fused. The operating point
above is gone.

**Two effects are mixed and only one of them is evasion.** The attacker is
quiet in four windows out of five, so a rule needing several recent windows has
fewer to work with. And four out of five attack labelled windows contain no
attack, so the classifier is trained to call ordinary driving an attack, which
is what takes benign stations flagged from 0.086 to 0.360. Station level
labelling is what a deployment has, because a misbehaviour report names a
station and not a window, so this is the realistic case. Separating the two
needs a per window labelled variant, which the transmit log supports and which
is not done.

---

## 13. Limitations

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
length of a straight carriageway. Setting the roadside units back from the road
is measured, in section 11, and is worth about a fifth of the localisation bound
before the inverse square loss of distance overtakes the geometric gain. That
measurement is a recomputation of the bound on the same pooled units rather
than a fresh campaign, so it captures the geometric effect and not the change in
what a relocated unit would hear. A junction or a curve would break the
collinearity far more thoroughly than any lateral offset can, and that is not
measured at all. The lateral degeneracy is the mechanism behind both the
detection floor and the strongest evasion, so a different road could move both.

---

## 14. Ethics, and availability

The tenth section of the outline accepted resource led security papers converge
on, and the draft had neither half of it.

**Ethics.** Every attack in this dataset is simulated. Nothing was transmitted on
a real channel, no vehicle was interfered with, and no human subject or personal
datum is involved. That is not incidental: it is the answer to the obvious
objection that real C-V2X traces now exist and this work simulates anyway. They
do exist, and they carry no labelled misbehaviour, because labelling an attack
requires carrying it out and nobody carries out position falsification on a
public road. Simulation is what makes the labels possible, and the cost of that
choice is stated in the limitations rather than argued away.

The dual use question is worth answering directly. The attacks here are already
described in the public literature and in the standards that specify the checks
against them; nothing in this dataset teaches an adversary a technique it does
not have. What it provides is a common instrument for measuring detection, which
is the side of the exchange that currently lacks one.

**Availability.** Three linked records, so most users take only the benchmark
while the provenance layer stays complete:

| record | contents |
|---|---|
| derived benchmark corpus | windowed features, the frozen partition, schema, codebook, dataset card, checksums and a small sample |
| raw simulation layer | the compressed simulator tables, partitioned by seed and run, with a manifest |
| generator artefact | the ns-3 scenario, the 5G-LENA patch, the extraction pipeline, the verifier and the baseline configurations |

The data is **CC BY 4.0**. The generator is an ns-3 contrib module and links
against ns-3, so it is **GPL-2.0-only**, which is an obligation rather than a
choice. The version specific identifier goes in the paper because it freezes
exactly what these results used; the concept identifier goes in the
documentation.

**Reproducibility.** Every figure reported is pinned to the line of the log that
produced it by a checker that ships with the code and must report no failures,
and the environment, the seeds and the measured per stage runtimes are
documented. That checker is offered as an artefact evaluation credential rather
than as a courtesy.

---

## 15. What would come next

Not in this paper, and worth naming so the boundary is deliberate. The first
two are cheap and the last two are not.

**Narrowing the floor further.** It is located to an 18 m interval from 44
attacker stations. Halving that again needs roughly four times as many, which is
several more campaigns, and the campaigns have to use seeds no existing one uses
because two runs sharing a scenario cannot be pooled. That is more simulation
than the result is worth, and the interval is already narrow enough to say the
floor sits near the middle of the fifty metre bracket it replaced rather than at
either end.

**The reverse direction of the federated test**, congested into sparse. One
direction is measured and the symmetric claim is not, which is cheap to close
and would change no conclusion.

**Personalisation, which is what our own negative result asks for.** Section 12
shows a federation spanning two densities doing worse than a model trained on
either, so the one global model this architecture produces is the wrong shape
for the non stationarity that motivates it. What the result points at is per
region or per density models with shared structure, which the federated
literature calls personalisation and which needs a continual learning loop that
does not exist here. That is the follow up paper rather than a missing section
of this one.

**A geometry that is not a straight road.** The lateral degeneracy behind both
the detection floor and the strongest evasion is a property of receivers strung
along a line. Moving them off the centreline is measured in section 11 and is
worth a fifth of the error, which is not enough to remove it. A junction or a
curve would break the collinearity far more thoroughly, and measuring by how
much would say whether the floor reported here is a property of the method or of
this road. That needs a road network rather than a straight carriageway, so it
is a new campaign and a new scenario rather than a parameter.

---


## Appendix: what to check before submission

- Re-run `analysis/verify_results.py` and confirm every check passes. Every
  number in this file is pinned by it.
- Re-check the novelty claim against the literature. The dataset and detection
  positioning was last checked 29 Aug 2026 and the cooperative position
  verification prior art on 5 Sep 2026. It is the claim the paper lives or dies
  on. `NOVELTY_POSITION.md` has the competitive table and the closest prior
  work, and `PAPER_CLAIMS.md` has the two standing positions from the field's
  survey that this paper is placed against.
- Confirm VeReMi NextGen is cited and differentiated. It is the current state of
  that lineage, it settles application layer breadth, and a reviewer from that
  group will be reading.
- Confirm section 11's figures come from the rerun across all eight seeds of the
  current corpus rather than the one seed of the superseded one they were
  first measured on.
- Confirm the persistence operating point in section 12 is the rerun figure. The
  zero false alert result from the superseded corpus must not appear anywhere.
- Confirm the VeReMi comparison states that the original release was used
  rather than the Extension, and why: the Extension is distributed through a
  file locker needing an interactive client, and the original's noise free
  benign class is the harsher test for this particular claim rather than the
  easier one.
- Check every figure and table against `RESULTS.md` rather than against this
  draft, and check the draft against the results rather than the other way
  round.
- Confirm no sentence claims federated training recovers the drift loss. It was
  measured and it does not, so the risk now runs the other way: check that the
  negative result is stated where a reader expects the recovery claim, not
  buried.
- Confirm every claim about the detection floor names all three lines of
  evidence, or none. Quoting only the learner families invites the objection
  that a different model might do better, which the geometry answers.
- Confirm nothing says the effect of moving the receivers is unmeasured. It is
  measured; what remains unmeasured is a junction or a curve.

### The five conclusions that changed when the corpus was regenerated

Worth re-reading before writing anything from memory, because each was
confidently reported in an earlier draft of this work and each is now something
else. They are listed in `RESULTS.md`, each in the section it belongs to. The pattern matters more
than any one of them: a number measured against a benign class with no
positional variance was measuring the absence of variance.
