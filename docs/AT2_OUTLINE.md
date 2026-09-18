# AT2 Final Report, outline against the rubric

**Due 18 Oct 2026. Fifty percent of OENG1168.** Built 19 Sep 2026 from
`OENG1168 - Assessment 1 - Rubric - new.pdf`, which carries all four assessment
rubrics rather than only AT1's. Criteria and point values below are quoted from
it, not inferred.

The evidence base is far larger than the report. `RESULTS.md` is 3,553 lines and
every figure in it is pinned to a generating log. **This is a selection problem,
not a discovery one**, and the rubric decides the selection.

---

## What the marks are actually for

| criterion | pts | CLOs |
|---|---|---|
| **Research and development process** | **40** | CLO2, CLO3 |
| Literature review | 20 | CLO2, CLO4 |
| Discussion and conclusion, overall reporting | 20 | CLO1, CLO3, CLO4 |
| Writing style | 10 | CLO4 |
| Format and presentation | 10 | CLO4 |

**Forty of the hundred points are the engineering process**, and its HD
descriptor names six things: problem, criteria and constraints clearly defined;
method selection justified; robust design and reproducible procedures;
validation and verification with sensitivity and quantified uncertainty;
alternatives considered with critical comparison; evidence-based
recommendations.

That descriptor is unusually well matched to this project, and the match is the
whole strategy for the report. Most student projects lose points on
*reproducible procedures*, *quantified uncertainty* and *critical comparison of
alternatives*, because most projects do not have them. This one has all three in
quantity and they are currently buried in internal documents that no marker will
ever open.

**The single largest risk is writing a report about the result instead of a
report about the process.** The result is one number. The process is the forty
points.

---

## Section plan, with the evidence named

Page budget assumes a 30 to 40 page report. Adjust proportionally if the
instructions set a different length; the ratios matter more than the totals.

### 1. Introduction and problem definition, 3 to 4 pages
*Feeds: R&D process (problem, criteria and constraints clearly defined),
Discussion (CLO1 lifecycle).*

The insider problem, stated once and concretely: every C-V2X message is signed
under ETSI TS 103 097, the signature proves the sender, and it proves nothing
about whether the content is true. Then the aim, the scope, and the constraints
that were fixed before any work: simulation rather than road measurement, and
why, which is that labelling an attack means performing it and nobody performs
position falsification on a public road.

**State the success criteria here and in measurable form**, because the rubric
asks for criteria and the Discussion criterion later asks for conclusions mapped
against them. Draw them from the four research questions.

### 2. Literature review, 5 to 6 pages
*Feeds: Literature review, 20 pts.*

The HD descriptor wants synthesis that **identifies gaps and justifies method
choices**, not a survey. Structure it as the gap argument the project actually
made, which is already written and checked:

- what exists for DSRC and ITS-G5 cross-layer detection, and why "first
  cross-layer V2X IDS" is false. `PLAN.md` section 1 has the checked wording.
- the public datasets and what each carries: VeReMi, VeReMi Extension, **VeReMi
  NextGen (IEEE VNC 2026)**, VASP, MisbehaviorX, and the four DSRC sets that
  carry RSSI. NextGen must appear; it is the current benchmark and it is three
  months old.
- prior art on position verification that bounds our claims: **Yan, Malaney,
  Nevat and Peters, IEEE TVT 63(7) 2014** for the CRLB error ellipse, and
  **Ihsan, Malaney and Yan, arXiv 1904.05610, 2019** for the estimator-aware
  attacker. Both are cited to forestall a reviewer, and citing them is what
  makes the narrower surviving claim credible.
- the standing objection that multilateration is impractical in vehicular
  networks because too few nodes are in proximity. **This project measured the
  answer**: five receivers is the identifiability floor and a real roadside unit
  region has a median of eight. Citing an objection and then answering it with
  your own measurement is exactly the "strong synthesis that identifies gaps"
  the descriptor asks for.

Source: `PLAN.md` section 1 and `docs/research/`, which holds the 24 research
reports and first-hand PDFs.

### 3. Methodology, 8 to 10 pages
*Feeds: R&D process, the 40 pts. **This is the longest section and it should
be.***

Write it as six subsections matching the six things the HD descriptor names.

**3.1 Method selection, justified.** ns-3.42 with 5G-LENA at tag `v2x-1.1`, and
why that rather than Veins, MOSAIC or SUMO alone: it is the only option that
produces native NR V2X PC5 Mode 2 sidelink with receiver-side PHY measurements.
Name the three-file patch that exposes per-SCI sidelink RSRP.

**3.2 Design.** Scenario, mobility, ETSI message triggering, the eleven attack
classes and the magnitude ladder. **The ladder is a design decision worth its own
paragraph**: non-overlapping magnitude bands turn a categorical label into an
axis, which is what makes a detection floor measurable at all.

**3.3 Reproducible procedures.** `regenerate.sh`, pinned seeds, the frozen
partition, `CHECKSUMS.sha256`, and `verify_results.py` pinning **158 figures**
to their generating logs. Say plainly that any figure in the report can be
traced to the run that produced it and that a script enforces it.

**3.4 Validation and verification, with quantified uncertainty.** Ten adversarial
integrity gates. The 1-NN score of **0.3466** as evidence the task is not
memorisable. Confidence intervals wherever they exist: the floor at 47.2 m with
a 95 percent interval of 39.3 to 57.4 m. The drift ratios reported as a range of
6.53 +/- 0.70 to 30.45 +/- 6.93 **and never averaged**, because they do not
overlap.

**3.5 Alternatives considered, critically compared.** This is the subsection most
reports cannot write and this one can, four times over:
- four learner families on identical folds, `model_independence.py`
- **seven estimator arms**, of which weighting alone made the fit worse and the
  reason is diagnostic rather than incidental, `RESULTS.md` 3h3
- five aggregation strategies across the federated panel
- six pooling arms, of which four are provably unaffected by the estimator
  change and are identical to four decimal places, which is how a real
  improvement is told from a bug

**3.6 The rebuild, and why it belongs in the methodology rather than hidden.**
The v1 pipeline reported macro F1 **1.0000** from three model families. An audit
found **96.39 percent of test rows appeared verbatim in training**, and that
16,150 benign windows collapsed to one distinct feature vector while the distance
they encoded spanned 2 m to over 8 km. The pipeline was rebuilt from the
simulator upward with a structural guarantee that ground truth cannot reach the
feature list.

**Markers reward this and reviewers do not.** It is the clearest available
evidence of engineering judgement, and the rubric's Discussion criterion asks
explicitly for transparent limitations and risks with mitigations.

### 4. Results, 6 to 8 pages
*Feeds: R&D process, Discussion.*

Four results in the order that makes them understandable, which is the order the
README already uses:

1. the application layer alone misses what the radio catches, and the reverse
2. a single receiver cannot detect a constant position offset at any magnitude
   in the corpus, across four learner families
3. pooling across receivers recovers it, down to a floor at **47.2 m**
4. the geometry predicts where an adaptive attacker will lie, **79.3 degrees**
   against 75 to 85 found by independent search

**On result 4, carry the condition, not just the number.** The pairing holds
while the estimator is near efficient, which this one is at a factor of 2.3
above its bound, and `RESULTS.md` 3h5 tested that by breaking it. A conditional
claim with a test behind it is stronger evidence of engineering judgement than
an unconditional one, and it is honest.

**Report the operating point with both figures.** Five of seven raises 7 false
alert episodes per region-hour while finding 54 percent of misbehaving stations.
Do not call it deployable. Call it the best point on this corpus and give the
comparison against two of three, which is a twelvefold reduction in false alerts
for nine points of recall.

### 5. Discussion and conclusions, 4 to 5 pages
*Feeds: Discussion and conclusion, 20 pts.*

The descriptor asks for four things and each maps to material that exists:

**Evidence to conclusion mapping.** Every conclusion tied to the section that
measured it. `PAPER_CLAIMS.md` already holds the claim-to-evidence table.

**Transparent limitations with mitigations.** `DATASET_CARD.md` has eight, each
stated rather than discovered: both radio attacks inert, light traffic, fixed
modulation and coding, one straight road with centreline units, highway only,
three classes under twenty stations, the observation unit fixed at 1000 ms, and
every measurement a simulator output never checked against a real radio.

**Ethics and safety.** Do not skip this; the descriptor names it and it is cheap.
The dataset is synthetic, so no personal data and no vehicle telemetry from real
drivers. The reason it is synthetic is itself an ethics finding: collecting real
labelled misbehaviour would mean transmitting false safety messages on a public
road. Note dual use honestly, since an attack generator is also an attack recipe,
and note that the release is CC BY 4.0 with the generator GPL-2.0-only.

**Recommendations, specific and prioritised.** Not "future work should explore".
Name them: the fifth learner family with the protocol pinned, the window length
trade with the measured cost of shortening, the raw layer release that would let
others vary the observation unit.

### 6. Reflection on process and teamwork, 2 to 3 pages
*Feeds: Discussion (CLO1 lifecycle), and it is where **D7** gets resolved in
writing.*

The committed AT1 task register no longer describes the project. Of twelve tasks
not Likhith's, two are dead, one is actively harmful, one is unreachable, four
are done and four are open. **A report that silently diverges from its own
committed plan looks like drift; a report that names the divergence and explains
each decision looks like project management**, which is CLO1 and CLO3.

Write it as a table: committed task, what happened, why, what replaced it. The
replacement register is drafted already.

**This section cannot be written alone.** It needs the D7 conversation to have
happened, which is why that conversation is the first item on the schedule below
rather than the last.

---

## Schedule, four weeks

| week | work | why then |
|---|---|---|
| **19 to 25 Sep** | **D7 conversation with the team.** Confirm the report structure with A/Prof Ke Wang and Mr Gahlot. Draft sections 1 and 2 | Section 6 is blocked on D7 and the literature review is the section least dependent on anything else |
| 26 Sep to 2 Oct | Section 3, methodology. Longest section, highest weight | Forty points. It should get the most time and the freshest attention |
| 3 to 9 Oct | Sections 4 and 5, results and discussion. **AT4 is due 11 Oct**, so keep the journal current through this week rather than reconstructing it | AT4 is 10 percent and its journal criterion is 30 of that |
| 10 to 14 Oct | Section 6, full assembly, figures, references, symbol and unit pass | Format and presentation is 10 points and is pure diligence |
| 15 to 17 Oct | Read-through against each rubric descriptor in turn. Turnitin check | See below |
| **18 Oct** | **Submit** | |
| 19 to 22 Oct | AT3 deck against its own rubric. Poster is built | AT3 is 30 percent and its poster criterion is already satisfied |

**Turnitin sees the Part A submission.** AT2 covers overlapping ground, so every
shared passage has to be written fresh rather than adapted. Budget for it rather
than discovering it on 17 October.

---

## The pre-submission pass

Read the report once per criterion, looking only for that criterion. Five passes,
about half a day, and it is the cheapest marks in the assessment.

1. **R&D process.** Can a marker find, by heading, where constraints are defined,
   where the method is justified, where uncertainty is quantified, and where
   alternatives are compared? If any of the four needs hunting, add a heading.
2. **Literature review.** Does every cited source do work, and does the section
   end by justifying a method choice rather than summarising?
3. **Discussion.** Is every conclusion traceable to a numbered result? Are ethics
   and safety present? Are recommendations specific enough to act on?
4. **Writing style.** Technical terms accurate, visuals referenced in the text
   rather than floating.
5. **Format.** Every figure numbered and captioned, every symbol defined at first
   use, every equation numbered and cross-referenced, every axis labelled.

---

## What to take from where

| need | source |
|---|---|
| any figure | `RESULTS.md`, **never memory and never earlier prose** |
| what Part A got wrong | `PARTA_CORRECTIONS.md`, eleven entries, three of which strengthen the project |
| claim to evidence mapping | `PAPER_CLAIMS.md` |
| limitations | `DATASET_CARD.md`, eight of them |
| the gap argument and citations | `PLAN.md` section 1, `docs/research/` |
| what the rebuild found | `DEFECTS_V2.md`, `DEFECT_SCOPE.md` |
| method lessons worth a reflection | `LESSONS.md` |
| what is still weak | `CRITIQUE_2.md` |
