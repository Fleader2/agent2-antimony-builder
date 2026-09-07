# Increment 1 — Agent 2 Architecture and Core Contracts

## Goal

> Establish the immutable domain contracts for full-network assembly,
> kinetic-law specification, parameter specification, boundary assessment,
> module decomposition, `ModelSpecification`, and Antimony output
> packaging — without implementing network assembly or Antimony
> generation yet.

This document specifies the *next* implementation increment. It is not
implemented by the repository-seeding task that created this document —
that task deliberately stopped at lightweight contract scaffolding
(`app/agent2/types.py`, `app/agent2/version.py`) plus this specification.

## Relationship to already-seeded types

The seeding task that created this repository already defined, as
lightweight contract scaffolding (not full Increment 1 behavior):

- `BoundaryLikelihood`
- `ParameterSource`
- `BoundaryAssessment`
- `ModuleBoundaryInterface`
- `ModuleSpecification`
- `ModuleDecomposition`
- `ModelSpecification`
- `Agent1CuratedKnowledgeViewContract` (and its nested `Curated*` records)

**Increment 1 must refine these types in place, not duplicate them under
new names.** If a field needs to change shape, edit the existing
dataclass and update `docs/02_agent1_handoff_contract.md`/this document
together with the code change (see `CONTRIBUTING.md`).

Increment 1 additionally introduces the types below, which do not exist
yet in any form:

- `FullNetwork`
- `CompartmentSpecification`
- `SpeciesSpecification`
- `ReactionSpecification`
- `KineticLawSpecification`
- `ParameterSpecification`
- `FullAntimonyArtifact`
- `ModuleAntimonyArtifact`
- `Agent2OutputPackage`

## Type responsibilities (contracts only — no generation logic)

| Type | Responsibility |
|---|---|
| `FullNetwork` | The single authoritative graph assembled from an `Agent1CuratedKnowledgeViewContract`: every compartment, species, and reaction Agent 2 will ever reason about for this model. Built once, before kinetic-law assignment. |
| `CompartmentSpecification` | One compartment in the full network, referencing its Agent 1 provenance id. |
| `SpeciesSpecification` | One chemical species in the full network (derived from a curated compound's participation in at least one reaction), referencing its Agent 1 provenance id and compartment. |
| `ReactionSpecification` | One reaction in the full network: its participants (with role and stoichiometry), reversibility, and enzyme association(s), referencing Agent 1 provenance. |
| `KineticLawSpecification` | The declared mathematical form of one reaction's rate law (e.g. mass-action, Michaelis-Menten) and which `ParameterSpecification`s it references. Declares structure only — never a fitted value. |
| `ParameterSpecification` | One parameter: its id, the kinetic law it belongs to, its `ParameterSource`, its initial value (with unit), and provenance references. |
| `BoundaryAssessment` *(refine)* | Unchanged responsibility; Increment 1 must connect it concretely to real `FullNetwork` element ids rather than opaque placeholder strings. |
| `ModuleBoundaryInterface` *(refine)* | Unchanged responsibility. |
| `ModuleSpecification` *(refine)* | Unchanged responsibility; Increment 1 must connect its id fields to real `FullNetwork` element ids. |
| `ModuleDecomposition` *(refine)* | Unchanged responsibility. |
| `ModelSpecification` *(refine)* | Extended to reference a `FullNetwork` and the concrete `KineticLawSpecification`/`ParameterSpecification` sets, not just bare id tuples. |
| `FullAntimonyArtifact` | The generated full Antimony text plus metadata identifying the `ModelSpecification` it was generated from and when. No generation logic in Increment 1 — this type exists so later increments have somewhere to put the result. |
| `ModuleAntimonyArtifact` | The generated Antimony text for one module — a *view* or a *standalone* variant (§ "Full vs. module output semantics" below) — plus metadata identifying its `ModuleSpecification` and which variant it is. |
| `Agent2OutputPackage` | The complete output of one Agent 2 build: a `ModelSpecification`, its `FullAntimonyArtifact`, and every module's `ModuleAntimonyArtifact` (§ "Agent2OutputPackage structure" below). |

## `Agent2OutputPackage` structure

```text
Agent2OutputPackage
    full_model_specification
    full_antimony
    boundary_assessments
    module_decomposition
    modules[]
        module_specification
        antimony_view
        standalone_antimony
        boundary_interfaces
        assumptions
```

No actual Antimony generation is implemented in Increment 1 — this
structure defines where a later increment's generated output will live.

## Full vs. module output semantics

* **Full Antimony Model** — the canonical representation of the complete
  model. Authoritative: every module output must remain traceable to it.
* **Module Antimony View** — a subset view of the full model. Not
  necessarily independently simulatable.
* **Standalone Module Antimony** — independently simulatable *only* if
  explicit boundary interfaces/assumptions exist for that module
  (`ModuleSpecification.boundary_interfaces`). No silent boundary
  conditions: if a module's interfaces are not fully explicit, Increment 1
  onward must not fabricate one just to produce a standalone artifact for
  it — `standalone_antimony` is `None` for that module instead.

## Parameter feedback architecture (future Agent 4 integration)

Agent 4 may eventually return, for a previously-declared parameter:

- a calibrated value,
- an uncertainty/confidence interval,
- sensitivity information,
- identifiability information,
- a characteristic timescale,
- correlations with other parameters.

Agent 2 may use this feedback to:

- update a `ParameterSpecification`'s `source` to `CALIBRATED` and its
  initial value to the calibrated one,
- rerun boundary assessment in light of the new parameter information,
- produce a revised `ModuleDecomposition`.

**Agent 2 must not perform the fitting itself.** No Increment 1 type or
function accepts experimental time-series data or produces a fitted
value — that entry point does not exist until Agent 4 defines its own
handoff contract back to Agent 2, which is out of scope for Increment 1.

## Boundary heuristic extensibility (future policy, not implemented here)

Increment 1 does not implement any boundary-assessment heuristic — it
only defines the `BoundaryAssessment` contract a future rule set will
populate. When such a rule set is built (a later increment), it is
expected to be a composable set of signals such as:

- a compartment transition,
- a transport step,
- a branch/convergence point in the network,
- a regulatory discontinuity,
- a kinetic-law discontinuity,
- a parameter-scale discontinuity,
- a timescale separation,
- currency-metabolite behavior (e.g. ATP/ADP, NAD+/NADH),
- a pathway/function transition.

**No single signal is automatically decisive** unless a future, explicitly
versioned policy marks it as a hard boundary. Every signal only
contributes to a qualitative `BoundaryLikelihood`, never a bypass of
heuristic judgment.

## Validation rules

* Every contract type validates its own required fields at construction
  (non-empty ids/names, correct enum member types, `Decimal` — never
  `float` — for numeric values) — the same discipline already established
  in the seeded types.
* `FullNetwork`/`ModelSpecification` construction must reject a reference
  to an element id that does not exist elsewhere in the same structure
  (e.g. a `ReactionSpecification` naming a compartment id not present in
  `FullNetwork.compartments`) — a referential-integrity check, not a
  scientific judgment.
* No type introduced in Increment 1 may silently coerce a missing value
  into a fabricated default — a missing kinetic parameter is a
  `PLACEHOLDER`/`DEFAULT` `ParameterSpecification`, never an invented
  numeric value presented as `CURATED`/`LITERATURE_DERIVED`.

## Versioning

* `AGENT2_CONTRACT_VERSION` (`app/agent2/version.py`) must be bumped when
  Increment 1 changes the shape of any contract type in a
  backward-incompatible way.
* `BOUNDARY_POLICY_VERSION` stays `"boundary-v1"` through Increment 1
  (no heuristic rule set exists yet to version); it will bump when a real
  boundary-assessment rule set is introduced.
* `AGENT1_HANDOFF_VERSION` only changes if the Agent 1 handoff contract
  itself changes shape (a cross-repository concern, coordinated via
  `docs/02_agent1_handoff_contract.md`).

## Scope exclusions

Increment 1 must not implement: whole-network assembly logic (only the
`FullNetwork` contract, not the algorithm that populates it from an
`Agent1CuratedKnowledgeViewContract`), kinetic-law assignment logic,
parameter initialization logic, boundary-assessment heuristics, module
decomposition logic, Antimony generation of any kind, Tellurium/COPASI
execution, parameter estimation/calibration, or model criticism. All of
these remain contracts (types with fields) until a later increment's own
specification authorizes implementing the algorithm behind them.

## Tests required

* Construction and validation-failure tests for every new type
  (`FullNetwork`, `CompartmentSpecification`, `SpeciesSpecification`,
  `ReactionSpecification`, `KineticLawSpecification`,
  `ParameterSpecification`, `FullAntimonyArtifact`,
  `ModuleAntimonyArtifact`, `Agent2OutputPackage`), mirroring
  `tests/agent2/test_contracts.py`'s existing style for the seeded types.
* Referential-integrity validation-failure tests (§ "Validation rules").
* An `Agent2OutputPackage` construction test demonstrating the full
  `full_model_specification` / `full_antimony` / `modules[]` shape.
* Continued scope-safety tests: no Tellurium/COPASI/`libsbml`/`antimony`
  import, no Agent 1 runtime import, no simulation/parameter-fitting/
  model-critic implementation, no Antimony-generation *service* module
  (only the `FullAntimonyArtifact`/`ModuleAntimonyArtifact` *data*
  contracts).

## Not implemented in this specification

This document is a specification for the next increment. It does not
itself implement any of the types or logic it describes beyond what the
repository-seeding task already created (see "Relationship to
already-seeded types" above).
