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
| `claims` (accepted only) | Every claim in this list has already passed Agent 1's `HUMAN_ACCEPTED` review gate. | That an accepted claim is proven correct — it is evidence-supported and human-reviewed, not infallible. | A claim with no corresponding evidence is possible; check `evidence` before assuming support exists. | See `confidence_summaries`. |
| `evidence` | Each evidence record references one of the `claims` above and may carry a publication reference and quoted support text. | That every claim has evidence, or that every evidence record has a publication reference. | Represented by the absence of a matching row — never fabricated. | `quoted_support`/publication reference, when present, are the provenance. |
| `confidence_summaries` | One summary per claim, exposing Agent 1's already-computed confidence score/class and claim status verbatim. | That Agent 2 may recompute or reinterpret this value — Agent 1 is the sole authority on it. | A `None` score/class means Agent 1 recorded none — never inferred. | This *is* the provenance for "how strongly is this claim supported." |
| `provenance` | Represented via `evidence`'s own publication/quoted-support fields plus `confidence_summaries` (there is no separate top-level "provenance" field in Agent 1's actual `Agent1CuratedKnowledgeView`). | That every reaction/compound is directly evidence-linked — only claims carry evidence in Agent 1 v1. | Absence of evidence for a given claim is possible and must be preserved, not backfilled. | See `evidence`/`confidence_summaries`. |
| `limitations` | A non-empty tuple of plain-text, human-readable disclosures (e.g. regulation incompleteness, cofactor non-classification). | That this list is exhaustive of every limitation that could ever matter to Agent 2 — read it, but do not treat its absence of an item as a guarantee of completeness. | Always present, per Agent 1's own contract; represented as an empty tuple only if Agent 1 ever ships with none. | n/a |

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

None of these are required for Increment 1.
