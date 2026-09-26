# Agent 1 → Agent 2 Handoff Contract

## 1. Purpose

This document defines the data-only contract Agent 2 uses to consume
Agent 1's curated biochemical knowledge. Agent 2 never imports Agent 1's
runtime package (`app.*` in `agent1-biochemical-curator`), its ORM models,
or its database session objects. The handoff is a plain, versioned,
serializable data structure — nothing more.

Agent 1's own authoritative description of this data is
`agent1-biochemical-curator/docs/23_agent1_v1_scope_and_completion.md`
(§19, §23) and the `Agent1CuratedKnowledgeView` type it defines
(`app.agent1.types.Agent1CuratedKnowledgeView` in that repository). This
document defines Agent 2's own **local, decoupled** representation of that
same data — `Agent1CuratedKnowledgeViewContract`
(`app/agent2/types.py` in this repository) — which mirrors it in shape
without depending on it in code.

## 2. Why a local, decoupled contract

Agent 2 must remain buildable, testable, and versionable independently of
Agent 1's Python environment, database, and release cadence. A local
contract type:

* lets Agent 2's tests run with no Agent 1 database or package installed;
* lets the two repositories evolve their internal representations
  independently, as long as the *data shape* named here stays compatible;
* makes exactly what Agent 2 assumes about Agent 1's output explicit and
  auditable in one place, rather than implicit in whatever Agent 1's ORM
  happens to expose.

A future integration layer (outside the scope of this increment) is
expected to translate a real Agent 1 `Agent1CuratedKnowledgeView` into
this contract's shape — most likely via serialization (e.g. JSON) rather
than an in-process Python import across repositories.

## 3. Contract version

`AGENT1_HANDOFF_VERSION` (`app/agent2/version.py`) names the version of
this contract Agent 2 was built against. A handoff payload that declares a
different `contract_version` must not be silently assumed compatible —
that reconciliation is future work (§9), not implemented in this
increment.

## 4. Conceptual field-by-field contract

| Field | Agent 2 may assume | Agent 2 must not assume | Missing information | Confidence/provenance |
|---|---|---|---|---|
| `contract_version` | A non-empty version string is always present. | That every version is compatible with `AGENT1_HANDOFF_VERSION` — version reconciliation is not implemented yet. | Never missing — required. | n/a |
| `organism_id` | Present when the handoff is scoped to one organism. | That every payload is organism-scoped — a whole-database payload may carry `None`. | Represented as `None`, never a fabricated id. | n/a |
| `compartments` | Zero or more entries; each has a stable id. | That every species/reaction references a compartment present in this list — Agent 1 v1 allows nullable compartment references. | An empty tuple, never omitted. | n/a |
| `compounds` | Zero or more entries; each has a stable id and a name. | That a compound is chemically unique, or that two compounds are guaranteed distinct just because their names differ (Agent 1 does not merge/dedupe by name). | Empty tuple if none. | n/a |
| `reactions` | Zero or more entries; each has a stable id. | That every reaction is complete, reversible/irreversible information is present, or that stoichiometry is guaranteed self-consistent (Agent 2 must check this itself, minimally, before assembly). | Empty tuple if none. | n/a |
| `reaction_participants` | Each participant names a reaction, a compound, a role, and a stoichiometry. | That role (`REACTANT`/`PRODUCT`/`MODIFIER`) distinguishes a cofactor from a non-cofactor — Agent 1 v1 does not classify cofactors separately (§6). | Empty tuple if none. | n/a |
| `reaction_enzyme_associations` | Each association names a reaction and (a protein or complex) that catalyzes it. | That every reaction has an associated enzyme — some may have none. | Empty tuple if none. | n/a |
| `regulatory_interactions` | Zero or more entries, each with a regulator, a target, and an effect. | That this list is complete or even present for a well-regulated network — Agent 1 v1's regulation pipeline is schema-ready, not curated end-to-end (§6). | Empty tuple if none — never treated as "no regulation exists," only "no regulation is currently curated." | n/a |
| `kinetic_measurements` (Agent 1.x Increment A) | Zero or more `CuratedKineticMeasurement` entries, each with a parameter type, an as-reported value/unit, and (when resolved) a reaction/protein/organism/publication reference. | That this list covers every reaction, that it is auto-converted into a `ParameterSpecification`, or that `normalized_value`/`normalized_unit` are ever populated (Agent 1 has no unit-conversion framework yet). | Empty tuple if none for this scope — never "no kinetic data exists," only "none is currently curated for this scope." | `source`/`source_id` name which connector-ingested source produced it; `confidence_score`/`confidence_class` are exposed verbatim, never recomputed by Agent 2. |
| `CuratedKineticMeasurement.protein_ids` ("Unresolved Kinetic Evidence Disclosure" increment) | The complete, deterministically-ordered set of every protein this measurement is applicable to — always a superset of the legacy `protein_id` (next row). May legitimately contain more than one entry (confirmed live: yeast's real FAS1/FAS2 heterodimer, sharing one EC number, both independently discovering the identical external SABIO-RK record). | That protein applicability is evidence of reaction applicability — it is never used to infer, narrow, or default a measurement's `reaction_id`. That exactly one entry means that protein is somehow "preferred" — every entry is equally applicable evidence. | An empty tuple means no protein context was ever resolved — a distinct fact from `reaction_id` being unresolved (§4C). | Same as `kinetic_measurements` above. |
| `CuratedKineticMeasurement.protein_id` | The first protein context established for this measurement — kept unmodified for backward compatibility with the single-protein-context case. | **That this is authoritative for protein applicability** — it is a legacy convenience field only; `protein_ids` is authoritative (see `app.agent2.types.CuratedKineticMeasurement`'s own docstring). | `None` when ambiguous (2+ protein contexts) or unresolved. | Same as `kinetic_measurements` above. |
| `claims` (accepted only) | Every claim in this list has already passed Agent 1's `HUMAN_ACCEPTED` review gate. | That an accepted claim is proven correct — it is evidence-supported and human-reviewed, not infallible. | A claim with no corresponding evidence is possible; check `evidence` before assuming support exists. | See `confidence_summaries`. |
| `evidence` | Each evidence record references one of the `claims` above and may carry a publication reference and quoted support text. | That every claim has evidence, or that every evidence record has a publication reference. | Represented by the absence of a matching row — never fabricated. | `quoted_support`/publication reference, when present, are the provenance. |
| `confidence_summaries` | One summary per claim, exposing Agent 1's already-computed confidence score/class and claim status verbatim. | That Agent 2 may recompute or reinterpret this value — Agent 1 is the sole authority on it. | A `None` score/class means Agent 1 recorded none — never inferred. | This *is* the provenance for "how strongly is this claim supported." |
| `provenance` | Represented via `evidence`'s own publication/quoted-support fields plus `confidence_summaries` (there is no separate top-level "provenance" field in Agent 1's actual `Agent1CuratedKnowledgeView`). | That every reaction/compound is directly evidence-linked — only claims carry evidence in Agent 1 v1. | Absence of evidence for a given claim is possible and must be preserved, not backfilled. | See `evidence`/`confidence_summaries`. |
| `limitations` | A non-empty tuple of plain-text, human-readable disclosures (e.g. regulation incompleteness, cofactor non-classification). | That this list is exhaustive of every limitation that could ever matter to Agent 2 — read it, but do not treat its absence of an item as a guarantee of completeness. | Always present, per Agent 1's own contract; represented as an empty tuple only if Agent 1 ever ships with none. | n/a |

## 4B. Enzyme regulatory states (Agent 1.x Increment B)

| Field | Agent 2 may assume | Agent 2 must not assume | Missing information | Confidence/provenance |
|---|---|---|---|---|
| `enzyme_states` | Zero or more `CuratedEnzymeState` entries, each naming exactly one of `protein_id`/`complex_id` and a `state_type` (`BASE`/`MODIFIED`/`ALLOSTERICALLY_BOUND`/`OTHER`). | That a state's `id` bears any relationship to the protein/complex it names, or that this list is exhaustive of every biologically real state — only curated ones appear. | Empty tuple if none for this scope. | `source`/`source_id`, when present, name the connector-ingested source. |
| `enzyme_modifications` | Each entry names an `enzyme_state_id` and a `modification_type` (`PHOSPHORYLATION`/`ACETYLATION`/`CYSTEINYLATION`/`UBIQUITINATION`/`METHYLATION`/`OTHER`); `residue`/`residue_position`/`stoichiometry` are present only when the source reported them. | That every state has a modification, or that residue/position is ever inferred when absent. | Empty tuple if none. | n/a |
| `allosteric_interactions` | Each entry names an `enzyme_state_id`, a resolved `ligand_compound_id`, and a qualitative `effect` (`ACTIVATOR`/`INHIBITOR`/`MODULATOR`/`UNKNOWN`). | That `effect` implies a specific numeric kinetic consequence — the quantitative effect, if curated, is a separate, state-specific `CuratedKineticMeasurement` sharing the same `enzyme_state_id`, never this record itself. | Empty tuple if none. | n/a |
| `enzyme_state_transitions` | Each entry names a `from_state_id`, `to_state_id`, and `transition_type` (`MODIFICATION`/`DEMODIFICATION`/`LIGAND_BINDING`/`LIGAND_RELEASE`/`OTHER`); `reaction_id` is present only when Agent 1's own reaction-curation pipeline already resolves it. | That every transition names a reaction, or that Agent 1 ever invents one. | Empty tuple if none. | n/a |
| `CuratedKineticMeasurement.enzyme_state_id` | `None` unless the measurement was specifically reported for one defined state. | That a state-specific measurement applies to the parent protein/complex generally, or to any other state of it. | `None` means not state-specific, or not yet resolved to one. | Same as `kinetic_measurements` above. |

## 4C. Unresolved kinetic evidence disclosure ("Unresolved Kinetic Evidence Disclosure" increment)

Motivated by Real Integration Pilot 2 Run 2: 14 real SABIO-RK kinetic
measurements survived the Agent 1 handoff and Agent 2's own assembly
completely intact, correctly excluded from reaction-specific kinetic-law
assignment (none had a resolved `reaction_id`) — but that exclusion was
invisible in the final `ModelSpecification`, indistinguishable from "no
kinetic evidence exists at all."

**Agent 2 distinguishes absence of kinetic evidence from kinetic evidence
that exists but cannot yet be assigned to a specific reaction.** The
former produces nothing — `kinetic_measurements` is simply empty, or every
entry already has a resolved `reaction_id`. The latter — a
`CuratedKineticMeasurement` present in the handoff with `reaction_id is
None` — now produces exactly one `ModelAssumption` (`app.agent2.types
.ModelAssumption`, `category="kinetics"`) per such measurement, with
`reason_code="KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"` and
`related_entity_ids` naming the measurement's own id and every one of its
`protein_ids`, in `ModelSpecification.model_assumptions`
(`app.agent2.model_specification.mapping.build_model_assumptions`).

**Protein applicability is not sufficient evidence of reaction
applicability.** A measurement's `protein_ids` being resolved (even to
exactly one protein) never causes, and must never be read as implying,
that its `reaction_id` should be inferred from that protein's own
`ReactionEnzyme` associations. The disclosure above makes an
already-true exclusion visible to a reviewer; it never reverses it, and
it never causes a real-valued parameter to be generated from the
measurement it describes. This remains true regardless of how many
reactions the named protein(s) catalyze.

## 5. General assumptions Agent 2 may make

* Every id is a stable, opaque identifier (a UUID or string) — Agent 2
  does not need to know how Agent 1 generated it.
* Data received through this contract already passed Agent 1's own
  normalization and (for `claims`/`evidence`) review workflow — Agent 2
  does not re-normalize entity names or re-derive curation state.
* Numeric values (stoichiometry, confidence scores) are exact — Agent 2
  never assumes rounding has already occurred, and must not round further
  without a documented reason.

## 6. General assumptions Agent 2 must NOT make

* That regulation is complete (§4, `regulatory_interactions`).
* That cofactors are distinguishable from other reaction participants
  (§4, `reaction_participants`) — a cofactor is an ordinary compound
  participating via an ordinary `ReactionParticipant` role.
* That MetaCyc/BioCyc-sourced data exists — those connectors are not
  implemented in Agent 1 v1; their absence is not an error condition.
* That every kinetic value Agent 2 will eventually need (rate constants,
  Michaelis constants, ...) is present in the handoff — even with
  `kinetic_measurements` now available (Agent 1.x Increment A, §4, §9),
  Agent 1's `KineticMeasurement` data may be sparse or entirely absent for
  a given reaction, and no field here is auto-converted into a
  `ParameterSpecification`. Agent 2's own parameter declaration/
  initialization step (`docs/01_agent2_architecture.md` §9) must handle
  the sparse/absent/not-yet-mapped case by declaring a
  `PLACEHOLDER`/`DEFAULT` parameter, never by fabricating a plausible
  value.
* That an `ExperimentRecommendation`/`ExperimentExecution`/
  `ExperimentResult` chain existing for a `KnowledgeGap` means that gap is
  resolved — Agent 1 v1 never auto-resolves a gap from an experiment
  result, and Agent 2 must not either.

## 7. Preserving uncertainty

Agent 2 must carry forward, not collapse, every uncertainty already
present in the handoff: a missing regulatory interaction is not "no
regulation," a `PLACEHOLDER` parameter is not "a measured value," and a
`LOW`/`VERY_LOW` boundary likelihood is not "no boundary." Agent 2 must
never silently invent missing knowledge to make a model "complete" —
an incomplete `ModelSpecification` with explicit gaps is always preferred
to a fabricated one.

## 8. What this contract explicitly excludes

No Antimony, no SBML, no ODEs, no kinetic model objects, no simulation
results, and no model-validation output ever appear in the Agent 1
handoff — those are exclusively Agent 2/3/4 outputs, never something
Agent 1 produces or Agent 2 receives from Agent 1.

## 9. Deferred / future work

* Formal version-compatibility reconciliation between
  `Agent1CuratedKnowledgeViewContract.contract_version` and
  `AGENT1_HANDOFF_VERSION` (§3).
* A concrete serialization/transport mechanism (JSON schema, file format,
  or service boundary) for moving data from the Agent 1 repository into
  this one. This increment defines only the in-memory shape.
* Any translation layer that reads a real Agent 1 export and produces an
  `Agent1CuratedKnowledgeViewContract` instance.
* **Kinetic measurements -- closed in Agent 1.x Increment A.** Increment 1
  (Step 21) had confirmed Agent 1's real `Agent1CuratedKnowledgeView`
  carried no kinetic-measurement field at all. Agent 1.x Increment A
  closed this gap: `AGENT1_HANDOFF_VERSION` was bumped "1.0" -> "1.1", and
  `Agent1CuratedKnowledgeViewContract.kinetic_measurements` /
  `CuratedKineticMeasurement` (`app/agent2/types.py`) now mirror Agent 1's
  own `kinetic_measurements`/`CuratedKineticMeasurement`
  (`app.agent1.types` in the Agent 1 repository) exactly. **This is
  available input data only** -- nothing in this repository converts a
  `CuratedKineticMeasurement` into a `ParameterSpecification`; that mapping
  decision (which measurement satisfies which kinetic law's which
  parameter, for which module) remains unimplemented Agent 2 behavior, out
  of scope for this note and for Increment 2's own scope as originally
  defined. Until that mapping is implemented, every
  `ParameterSpecification` Agent 2 declares still has no curated numeric
  source and must use `ParameterSource.DEFAULT`/`PLACEHOLDER` -- never a
  fabricated `CURATED` value merely because a matching
  `CuratedKineticMeasurement` exists.
* **Enzyme regulatory states (Agent 1.x Increment B).**
  `AGENT1_HANDOFF_VERSION` was bumped "1.1" -> "1.2".
  `enzyme_states`/`enzyme_modifications`/`allosteric_interactions`/
  `enzyme_state_transitions` (§4B) and `CuratedKineticMeasurement.enzyme_state_id`
  now mirror Agent 1's identically-named fields exactly. Available as
  input data only -- nothing in this repository maps a `CuratedEnzymeState`
  onto a model species, and Whole-Network Assembly (Increment 2) was not
  modified to consume these fields. Agent 2's future Reaction
  Characterization stage will consume these state distinctions (a state
  may become a distinct model species with its own kinetic-law
  applicability and parameters) -- not implemented here.

None of these are required for Increment 1.
