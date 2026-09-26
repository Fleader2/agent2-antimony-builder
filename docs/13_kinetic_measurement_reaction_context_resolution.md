# Kinetic-Measurement Reaction-Context Resolution

Real Integration Pilot 2 Run 2 found that all 14 real SABIO-RK kinetic
measurements Agent 1 curates for yeast fatty-acyl-CoA synthase (FAS1/FAS2,
EC 2.3.1.86) arrive with `reaction_id=None`, correctly preserved and
disclosed (`KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED`) but never
usable by kinetic-law/parameter assignment. This increment asks a
narrower question: for which of those measurements does the *source
evidence itself* deterministically establish exactly one curated
reaction?

**Core rule**: protein applicability is not reaction applicability. A
measurement is assigned a `reaction_id` only when the matching procedure
below finds exactly one compatible curated reaction. See
`app.agent2.kinetics.reaction_context` for the implementation.

## 1. What the real source data actually supplies

Live, read-only re-query of the 7 real SABIO-RK entries this pathway
already discovered (18228-18234, all `EC 2.3.1.86`, all PMID `7044669`),
via `app.connectors.sabiork.SabiorkConnector.fetch` (in
`agent1-biochemical-curator`, not modified):

* `reaction.equation` -- one free-text, **lumped, whole-cycle** equation
  per entry (e.g. `"2n NADPH + Acetyl-CoA + n Malonyl-CoA + H+ = ...
  Long-chain fatty acid + n CO2 + 2n NADP+ + n+1 Coenzyme A"`), varying
  only by which primer compound is named (Acetyl-CoA for 18228-18230;
  Propionyl-/Butanoyl-/Hexanoyl-/Octanoyl-CoA for 18231-18234
  respectively). This is a whole-pathway summary, not a single curated
  elementary reaction's equation -- Agent 1's own curated FAS1/FAS2
  reaction set (38 reactions total) is the detailed, ACP-tethered,
  KEGG-style elementary-step decomposition (loading, condensation,
  ketoreduction, dehydration, enoyl-reduction per chain length), which
  uses entirely different compound identities (`Hexanoyl-[acp]`,
  `(3R)-3-Hydroxyoctanoyl-[acyl-carrier protein]`, ...) from the free-CoA
  thioesters the SABIO-RK equation text names. No exact-identity match
  exists between the two texts at the whole-equation level.
* **Each kinetic parameter's own `species` field** (parsed as
  `SabioKineticParameter.species_label`): every `Km` in all 7 entries
  names one specific ligand, with a `"Substrate"` role -- e.g. entry
  18229's `Km` names `Malonyl-CoA`, entry 18230's names `Acetyl-CoA`,
  entry 18228's names `NADPH`. **Every `Vmax` in all 7 entries has
  `species_label=None`** -- Vmax is never reported with respect to one
  named ligand. This is the one genuinely deterministic, per-parameter
  (not per-equation) identity signal the source supplies, and it cleanly
  separates by parameter type exactly as expected: a Km/Ki is a named
  ligand's binding constant; a Vmax/kcat describes overall turnover.
* `ec_number`/`enzyme_name`/`uniprot_ids` -- confirm EC 2.3.1.86 and the
  real FAS1/FAS2 heterododecamer, but (per this increment's own explicit
  scope) are never used as reaction-discriminating evidence.
* No reaction-identifier or KEGG-reaction cross-reference field exists in
  SABIO-RK's structured payload as parsed by this connector -- only the
  free-text equation and the per-parameter species field above.

**Comparison against the curated Agent 1 FAS1/FAS2 reaction set** (Real
Integration Pilot 1 Run 8's frozen `Agent1KnowledgePackage`, 38 curated
`sce00061` reactions total, 32 catalyzed by FAS1 and/or FAS2):

* `Malonyl-CoA` is a `REACTANT` of **exactly one** curated reaction:
  `malonyl-CoA:[acyl-carrier-protein] S-malonyltransferase` (KEGG
  `R05199`-family, EC 2.3.1.39/85/86, FAS1/FAS2-catalyzed).
* `Acetyl-CoA` is a `REACTANT` of **three** curated reactions across the
  full network: `acetyl-CoA:[acyl-carrier-protein] S-acetyltransferase`
  (KEGG `R01624`, FAS1/FAS2), `acyl-CoA:malonyl-CoA C-acyltransferase
  (decarboxylating, oxoacyl- and enoyl-reducing)` (KEGG `R05190`,
  FAS1/FAS2, a lumped whole-cycle reaction whose own shape echoes the
  SABIO-RK equation more closely than any other), and `acetyl-CoA:carbon-
  dioxide ligase (ADP-forming)` (KEGG `R00742`, ACC1 -- a different
  enzyme entirely). Nothing in the source (compound identity alone)
  discriminates between these three.
* `NADPH` is a **`PRODUCT`, never a `REACTANT`**, of all 16 curated
  reactions it participates in (every ketoreductase/enoyl-reductase step
  is curated in the conventional oxidative KEGG direction, NADP+ ->
  NADPH) -- confirmed by direct inspection of every
  `reaction_participants` row naming it. A naive "compound appears
  somewhere" check would have wrongly suggested 14+ candidates; the
  correct, role-aware check finds zero `REACTANT` matches.
* `Propionyl-CoA`, `Butanoyl-CoA`, `Hexanoyl-CoA`, `Octanoyl-CoA` (free
  CoA-thioester forms) are **not curated compounds at all**, anywhere in
  the 53-compound curated set (only their ACP-bound forms --
  `Butyryl-[acp]`, `Hexanoyl-[acp]`, `Octanoyl-[acp]` -- are curated, and
  none is named by any SABIO-RK equation text).

## 2. Matching-result vocabulary

`app.agent2.kinetics.reaction_context.ReactionContextMatchResult`:

* `UNIQUE_MATCH` -- exactly one curated reaction is compatible; the only
  outcome that ever produces a `reaction_id` assignment.
* `MULTIPLE_COMPATIBLE` -- two or more curated reactions are compatible;
  none is chosen.
* `NO_MATCH` -- the search ran and found zero candidates (including
  because the resolved compound is not curated as a `REACTANT` of
  anything, or is not curated at all).
* `INSUFFICIENT_SOURCE_EVIDENCE` -- there is nothing to search with at
  all (no `compound_id`, or a parameter type never anchored to one named
  compound) -- distinct from `NO_MATCH`.

No existing vocabulary fit this need (`KineticLawReasonCode` classifies
*kinetic-law type* decisions, not measurement-to-reaction matching), so
this is a new, narrowly-scoped enum.

## 3. Matching evidence (deterministic only)

The sole evidence used: `CuratedKineticMeasurement.compound_id`, resolved
by **exact id equality** (never fuzzy/nearest-name matching -- and never
by name string at all, only by id) against
`FullNetwork.species[].source_compound_id`, then against which
reactions use that species (across every compartment instance) with
`ParticipantRole.REACTANT`. Explicitly never used: protein/complex/
enzyme-state identity, EC number, `ReactionEnzyme`/
`CuratedReactionEnzymeAssociation` membership, pathway membership,
nearest-name text matching, or arbitrary selection among candidates.

## 4. Parameter-type semantics

Only `KM`/`KI` are ever eligible (`_COMPOUND_ANCHORED_PARAMETER_TYPES`),
as a **hard rule**, not an incidental consequence of `VMAX`/`KCAT` never
carrying a `compound_id` in today's real data -- even a future source
populating `compound_id` on a `VMAX` row must not be treated as
reaction-discriminating (a Vmax describes overall catalytic turnover, not
one elementary step). Each measurement is resolved independently: two
measurements from the same SABIO-RK entry (its `Km` and its `Vmax`) can
and do receive different outcomes (confirmed on every one of the 7 real
entries -- see §7), and two `Km` measurements from different entries are
never assumed to share reaction applicability merely because they share a
protein context.

## 5. Integration

`resolve_kinetic_measurement_reaction_context(network)` is a pure,
read-only classification function; `apply_resolved_reaction_context
(network, resolutions)` returns a new `FullNetwork` with only
`UNIQUE_MATCH` measurements' `reaction_id` populated -- every other field,
of every measurement and every other entity, is unchanged. This is an
opt-in pre-processing step over a `FullNetwork`, applied *before*
`assign_kinetic_laws`/`declare_parameters`/`assemble_model_specification`
run; none of those three, nor
`app.agent2.model_specification.mapping.build_model_assumptions`, was
modified. A resolved measurement is consumed by the existing, unmodified
Michaelis-Menten parameter-declaration path exactly as a natively-
attributed one would be (§6, scenario 10); an unresolved measurement
continues to receive the existing `KINETIC_MEASUREMENT_REACTION_CONTEXT_
UNRESOLVED` `ModelAssumption`, unchanged (§6, scenario 11).

## 6. Test coverage

`tests/agent2/test_reaction_context.py` (17 tests) covers all 12 required
scenarios: unique match; multiple compatible; no match (compound absent
entirely, and compound curated but never as a `REACTANT`); insufficient
evidence (missing `compound_id`); protein/EC context alone never
substituting for compound evidence; substrate-specific `Km` resolving
while every other field is preserved; `Vmax` never resolved even with a
uniquely-matching `compound_id` present (the hard rule from §4); no
arbitrary reaction chosen among multiple compatible candidates;
order-independence; a resolved measurement reaching real parameter
declaration; an unresolved measurement still producing its disclosure
assumption after a resolution pass; and `apply_resolved_reaction_context`
never altering any field but `reaction_id`. Five further tests cover the
vocabulary/type's own construction invariants.

## 7. Real-data validation (read-only, not persisted)

Ran against the real, frozen Pilot 1 Run 8 `Agent1CuratedKnowledgeView`
(14 real measurements), in two passes:

**Pass A -- current production translation, unmodified** (Pilot 2 Run
2's own `build_handoff`, `compound_id = substrate_id`, always `None` for
real data): all 14 measurements resolve to `INSUFFICIENT_SOURCE_EVIDENCE`
-- correct given today's actual data, and the expected, honest outcome
given the gap identified in §8.

**Pass B -- demonstration only** (`compound_id` populated from this
increment's own live SABIO-RK `species_label` inspection, §1 -- not
current production behavior; no translation layer commits this):

| SABIO-RK entry | parameter | protein context | resolved compound | candidates | result | matched reaction |
|---|---|---|---|---|---|---|
| 18228 | Km | FAS1+FAS2 | NADPH | 0 | `NO_MATCH` | -- |
| 18228 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |
| 18229 | Km | FAS1+FAS2 | Malonyl-CoA | 1 | **`UNIQUE_MATCH`** | `11ad95b7-...` (malonyl-CoA:[acp] S-malonyltransferase) |
| 18229 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |
| 18230 | Km | FAS1+FAS2 | Acetyl-CoA | 3 | `MULTIPLE_COMPATIBLE` | -- |
| 18230 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |
| 18231 | Km | FAS1+FAS2 | Propionyl-CoA (uncurated) | 0 | `NO_MATCH` | -- |
| 18231 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |
| 18232 | Km | FAS1+FAS2 | Butanoyl-CoA (uncurated) | 0 | `NO_MATCH` | -- |
| 18232 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |
| 18233 | Km | FAS1+FAS2 | Hexanoyl-CoA (uncurated) | 0 | `NO_MATCH` | -- |
| 18233 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |
| 18234 | Km | FAS1+FAS2 | Octanoyl-CoA (uncurated) | 0 | `NO_MATCH` | -- |
| 18234 | Vmax | FAS1+FAS2 | (none) | -- | `INSUFFICIENT_SOURCE_EVIDENCE` | -- |

Exactly 1 of 14 real measurements (18229's `Km`) would reach
`UNIQUE_MATCH` if the source evidence already documented in §1 were
carried through the handoff -- with exact supporting evidence: `Malonyl-
CoA` (`compound_id=0c578a96-0bcc-4f6d-9fad-ce6d1e5835f2`) is a `REACTANT`
of exactly one curated reaction. No measurement was ever assigned via
protein identity, EC number, or arbitrary selection -- `MULTIPLE_
COMPATIBLE` (18230) correctly declines to choose among three candidates
even though one (`R05190`) is qualitatively the closest equation-shape
match, because compound identity alone does not discriminate it from the
other two.

## 8. Agent 1 -> Agent 2 Translation Layer (separate, independent follow-up)

No committed Agent1-to-Agent2 translation layer exists in either
repository (confirmed again this increment: `agent2-antimony-builder`'s
own `git log` shows no such module; Pilot 2 Run 1/Run 2 both used an
uncommitted scratchpad script). This increment's Pass A/Pass B split
above makes the concrete stakes of that gap visible: the matching logic
in `app.agent2.kinetics.reaction_context` is real, tested, and correct,
but it can only ever resolve real measurements once something -- Agent 1
itself, or a committed translation layer sitting between the two
repositories -- populates `CuratedKineticMeasurement.compound_id` from
the evidence already available in SABIO-RK's own `species_label` field.
Building that translation layer is out of scope here (reaction-context
resolution was fully testable without it, via the fixtures in §6 and the
demonstration in §7) and is recorded as its own, separate follow-up task:
**"Agent 1 -> Agent 2 Translation Layer."**
