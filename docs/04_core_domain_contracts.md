# Agent 2 Core Domain Contracts

## 1. Purpose

This is the canonical, current-state reference for every immutable domain
contract Agent 2 defines as of Increment 1. It documents what Agent 2
*knows how to represent* -- not what it knows how to compute. No network
assembly, kinetic-law assignment, boundary heuristic, module partitioning,
or Antimony generation algorithm exists anywhere in this repository yet;
every type below is a structural, self-validating data contract with
reference-integrity checks only.

## 2. FullNetwork

`app.agent2.types.FullNetwork` -- the single authoritative graph of every
`CompartmentSpecification`/`SpeciesSpecification`/`ReactionSpecification`
Agent 2 assembles from an `Agent1CuratedKnowledgeViewContract`
(`app.agent2.network.assemble_full_network`, Increment 2 -- see
`docs/05_whole_network_assembly.md`). Built once, before kinetic-law
assignment or boundary assessment (full-network-first).

Fields: `network_id`, `name`, `compartments`, `species`, `reactions`,
`enzyme_associations`, `regulatory_interactions`, `kinetic_measurements`
(the latter three added in Increment 2), `organism_id`, `assumptions`,
`provenance_refs`.

Validated: compartment/species/reaction/enzyme-association/regulatory-
interaction/kinetic-measurement ids are each internally unique; every
species' `compartment_id` names a compartment present in `compartments`;
every reaction participant's `species_id` names a species present in
`species`; every reaction's `enzyme_association_ids`/
`regulatory_interaction_ids` exist among `enzyme_associations`/
`regulatory_interactions`; every enzyme association's `reaction_id` exists
among `reactions`; every regulatory interaction's `regulator_id`/
`target_id` is checked only when its type is `"reaction"`/`"compound"`
(see `docs/05_whole_network_assembly.md` §14 for why every other entity
type is left unchecked). **Never validated here**: mass balance, graph
connectivity, unit consistency, or conservation laws -- those are Agent
3's job.

`enzyme_associations`/`regulatory_interactions`/`kinetic_measurements` are
supporting data attached to the network, never structural graph elements
in their own right -- see §2A/§10 below and
`docs/05_whole_network_assembly.md` §§9-11.

## 2A. ReactionEnzymeAssociation

`app.agent2.types.ReactionEnzymeAssociation` -- one reaction-enzyme
association carried into `FullNetwork.enzyme_associations` (Increment 2).
Mirrors `CuratedReactionEnzymeAssociation` field-for-field, adding only
`association_id`: a stable id synthesized at assembly time, since the
curated handoff record itself carries none (a discovered gap -- see
`docs/05_whole_network_assembly.md` §14). Fields: `association_id`,
`reaction_id`, `protein_id`, `complex_id`, `relationship`.

## 3. CompartmentSpecification

One compartment in the full network. `source_scope`
(`CompartmentSourceScope`: `AGENT1_CURATED`/`MODELING_CONSTRUCT`) decides
what `source_entity_id` may hold: `AGENT1_CURATED` requires it,
`MODELING_CONSTRUCT` forbids it and instead requires `assumptions` to
disclose why Agent 2 needed a compartment Agent 1 never curated. No unit
is ever invented -- `volume_unit` is `None` whenever the source data
supplied none.

Fields: `compartment_id`, `name`, `source_scope`, `source_entity_id`,
`initial_volume` (`Decimal | None`), `volume_unit`, `constant`,
`assumptions`, `provenance_refs`.

## 4. SpeciesSpecification

One chemical species. Species identity always includes compartment
context: `compartment_id` is required. At most one of `initial_amount`/
`initial_concentration` may be set -- no reconciliation policy exists yet.
`constant` (value never changes) and `boundary_condition` (not consumed/
produced by reactions, but may still be set externally) are independent
SBML-style flags. `initialization_source` reuses `ParameterSource` rather
than inventing a near-duplicate vocabulary for "where did this initial
value come from."

Fields: `species_id`, `name`, `compartment_id`, `source_compound_id`,
`initial_amount`, `initial_concentration`, `initialization_source`,
`constant`, `boundary_condition`, `assumptions`, `provenance_refs`.

## 5. ReactionParticipantSpecification

One reactant/product/modifier of a reaction. `role` is `ParticipantRole`
(`REACTANT`/`PRODUCT`/`MODIFIER`, transcribed from Agent 1's own
`ReactionParticipantRole` vocabulary -- never imported). `stoichiometry`
is required and must be `> 0` for **every** role including `MODIFIER`,
mirroring Agent 1's own database `CHECK` constraint. Whether a modifier's
stoichiometry contributes to a kinetic-law expression is a modeling
decision deferred to kinetic-law assignment -- this type only records the
value. Multiplicity is preserved: nothing deduplicates two participants
naming the same species and role.

## 6. ReactionSpecification

One reaction. `participants` are structural inputs only -- no mass-balance
or duplicate-reaction detection. `reversible` is never inferred (`None`
means Agent 1 did not record it). `kinetic_law_id` may be unresolved
(`None`) at this stage. Requires at least one participant (a structural
completeness check, not mass-balance analysis).

Fields: `reaction_id`, `name`, `participants`, `source_reaction_id`,
`reversible`, `enzyme_association_ids`, `regulatory_interaction_ids`,
`kinetic_law_id`, `assumptions`, `provenance_refs`.

## 7. KineticLawType

```text
MASS_ACTION
MICHAELIS_MENTEN
HILL
REVERSIBLE_MASS_ACTION
CUSTOM
UNASSIGNED
```

The structural *form/category* of a rate law -- never fitted behavior.
`UNASSIGNED` is the default starting point.

## 8. KineticLawSpecification

The declared structural form of one reaction's rate law. `expression` is
a contract representation of the intended rate law (free-form text), not
Antimony serialization -- no parsing or generation occurs, only a
non-blank check when a law is actually assigned (`law_type is not
UNASSIGNED`). `assignment_source` reuses `ParameterSource` (a law's *type*
has the identical provenance-vs-status axis as a parameter's *value*).
Reference integrity for `parameter_ids`/`species_ids` is enforced later,
at `ModelSpecification` construction.

Fields: `kinetic_law_id`, `reaction_id`, `law_type`, `assignment_source`,
`expression`, `parameter_ids`, `species_ids`, `assumptions`,
`provenance_refs`.

## 9. ParameterSpecification

The most important contract in this increment. `value` may be `None` -- a
declared-but-uninitialized parameter is normal, not an error. `source`
(`ParameterSource`) is the sole authority on how to interpret `value`: a
`PLACEHOLDER` must never be presented as `CURATED`/`CALIBRATED`, and Agent
2 must never assign `CALIBRATED` to a value it produced itself (only
Agent 4's future feedback justifies that). `lower_bound`/`upper_bound`
must satisfy `lower_bound <= upper_bound` when both are set. Four pure,
deterministic properties (never a numeric confidence): `has_value`,
`is_placeholder`, `is_calibrated`, `is_curated`.

Fields: `parameter_id`, `name`, `source`, `value`, `unit`,
`source_reference`, `reaction_id`, `module_ids`, `lower_bound`,
`upper_bound`, `uncertainty_text`, `fixed`, `assumptions`,
`provenance_refs`.

## 10. ParameterSource

```text
CURATED
LITERATURE_DERIVED
DEFAULT
PLACEHOLDER
CALIBRATED
```

Provenance/status, never confidence. Reused by
`SpeciesSpecification.initialization_source` and
`KineticLawSpecification.assignment_source` rather than inventing
near-duplicate vocabularies.

## 11. BoundaryLikelihood

```text
VERY_LOW
LOW
MEDIUM
HIGH
VERY_HIGH
```

A qualitative heuristic judgment -- never a fabricated numeric
probability. No boundary heuristic rule set exists yet to assign one.

## 12. BoundaryParameterBasis

```text
NONE
PLACEHOLDER_ONLY
DEFAULT_ONLY
CURATED_OR_LITERATURE
CALIBRATED
MIXED
```

Whether a `BoundaryAssessment` was informed by parameter data and of what
quality -- a structural disclosure, never a numeric weight. Replaces the
seeded free-text `parameter_basis: str | None` with this closed
vocabulary.

## 13. BoundaryAssessment

One candidate module boundary's qualitative assessment. Refined in
Increment 1 with `policy_version` (which boundary-heuristic rule set, once
one exists, produced this), `kinetic_law_ids`/`parameter_ids` (what
kinetic/parameter data the assessment considered), and
`parameter_basis: BoundaryParameterBasis | None` (upgraded from a free
string). No heuristic computation exists yet -- this is the contract a
future rule set will populate.

Fields: `boundary_id`, `upstream_element_id`, `downstream_element_id`,
`likelihood`, `explanation`, `policy_version`, `shared_species_ids`,
`connecting_reaction_ids`, `supporting_reason_codes`,
`opposing_reason_codes`, `kinetic_law_ids`, `parameter_ids`,
`parameter_basis`.

## 14. ModuleBoundaryInterface

One explicit interface element required for a standalone module model.
`role` is now `ModuleInterfaceRole` (`INPUT`/`OUTPUT`/`BIDIRECTIONAL`/
`SHARED`, upgraded from a free string); `direction` remains free text (no
closed vocabulary was specified for it). Refined with `initial_value`
(`Decimal | None`) and `unit`. Structural only -- no simulation semantics.
Agent 2 never invents a boundary condition silently.

## 15. ModuleSpecification

One module: a named subset of the full network plus its boundary
interfaces. Refined with `kinetic_law_ids` and `provenance_refs`. Requires
at least one reaction (an empty module is not meaningful); every
id-bearing tuple (`reaction_ids`/`species_ids`/`parameter_ids`/
`kinetic_law_ids`) is internally unique. Always traceable to the full
model via `source_boundary_ids`. One pure property:
`has_explicit_boundary_interfaces` (`len(boundary_interfaces) > 0`) -- the
same predicate `ModuleAntimonyArtifact` uses to decide whether a
standalone variant may exist.

## 16. ModuleDecomposition

The full network's partition into modules, as of one boundary-policy
version. Refined with `created_from_network_id` (must equal the
`FullNetwork.network_id` it was built from, enforced at
`ModelSpecification` construction) and `parameter_basis_summary`
(`BoundaryParameterBasis | None`). References modules/boundaries by id --
never duplicates them. No partitioning algorithm exists in this
increment.

## 17. ModelAssumption

A structured, categorized, model-level assumption record -- distinct from
the lightweight free-text `assumptions: tuple[str, ...]` every structural
type already carries for local disclosures. `ModelSpecification` carries
both: `assumptions` for quick notes, `model_assumptions` for the
referenceable, categorized layer. Kept minimal: `assumption_id`,
`category`, `statement`, `related_entity_ids`, `source`, `reason_code` --
no free-form LLM rationale field.

## 18. ModelSpecification

The top-level, authoritative contract. Refined significantly in Increment
1: the seeded flat id-tuple fields (`compartment_ids`/`species_ids`/
`reaction_ids`/`kinetic_law_ids`/`parameter_ids`) are replaced by a real
`full_network: FullNetwork` plus `kinetic_laws`/`parameters` tuples of the
actual specification objects, enabling genuine reference-integrity
validation (§19). Also gained `model_assumptions` and `contract_version`
(defaults to `AGENT2_CONTRACT_VERSION`).

Fields: `model_id`, `name`, `full_network`, `organism_id`, `kinetic_laws`,
`parameters`, `boundary_assessments`, `module_decomposition`,
`module_specifications`, `assumptions`, `model_assumptions`,
`provenance_refs`, `contract_version`.

## 19. Reference integrity

`ModelSpecification.__post_init__` enforces, in one pass
(`_validate_model_specification_references`):

* every `kinetic_laws[].reaction_id` exists in `full_network.reactions`;
* every `kinetic_laws[].parameter_ids`/`.species_ids` exist in
  `parameters`/`full_network.species`;
* every `parameters[].reaction_id` (when set) exists in
  `full_network.reactions`;
* every `full_network.reactions[].kinetic_law_id` (when set) exists in
  `kinetic_laws`;
* every `module_specifications[].species_ids`/`.reaction_ids`/
  `.parameter_ids`/`.kinetic_law_ids`/`.source_boundary_ids` exist in the
  corresponding sets;
* every module's `boundary_interfaces[].species_id` exists in
  `full_network.species`;
* `module_decomposition.module_ids`/`.boundary_assessment_ids` (when set)
  exist among `module_specifications`/`boundary_assessments`, and
  `.created_from_network_id` equals `full_network.network_id`;
* `kinetic_laws`/`parameters`/`module_specifications`/
  `boundary_assessments` are each internally unique by id.

**Never validated here**: mass balance, graph connectivity, unit
consistency, or conservation-law analysis. Those are Agent 3's job.

## 20. FullAntimonyArtifact

The full, canonical Antimony model text -- a contract only in Increment
1. Construction is allowed (for tests and future wiring); no generator
function, no syntax validation, and no Antimony runtime dependency exists
anywhere in this repository.

Fields: `model_id`, `model_specification_id`, `antimony_text`,
`generator_version`, `assumptions`, `provenance_refs`.

## 21. ModuleAntimonyArtifact

One module's Antimony output(s) -- a contract only in Increment 1.
`antimony_view` may exist without `standalone_antimony`.
`standalone_antimony` may be present only when `boundary_interfaces` is
non-empty -- the same structural predicate as `ModuleSpecification
.has_explicit_boundary_interfaces`. No boundary condition is ever invented
to satisfy this rule.

Fields: `module_id`, `model_specification_id`, `generator_version`,
`antimony_view`, `standalone_antimony`, `boundary_interfaces`,
`assumptions`.

## 22. Agent2OutputPackage

The complete output of one Agent 2 build. `boundary_assessments`/
`module_decomposition` are convenience top-level copies and must be
identical to `model_specification`'s own -- never independently
diverging. `full_antimony.model_specification_id` must equal
`model_specification.model_id`. Every `module_artifacts` entry must
reference a module that exists in
`model_specification.module_specifications` (not every module needs an
artifact yet) and must itself carry the same `model_specification_id`.
`module_artifacts` ids are unique.

Fields: `contract_version`, `model_specification`, `full_antimony`,
`module_artifacts`, `boundary_assessments`, `module_decomposition`,
`assumptions`, `provenance_refs`.

## 23. Versioning

`AGENT2_CONTRACT_VERSION` was bumped from `"0.1"` to `"0.2"` in this
increment (`ModelSpecification`'s shape changed in a backward-incompatible
way). `AGENT1_HANDOFF_VERSION`/`BOUNDARY_POLICY_VERSION` are unchanged --
the Agent 1 handoff shape did not change, and no boundary heuristic rule
set exists yet to version. No additional version constants
(`MODEL_SPECIFICATION_VERSION`/`ANTIMONY_ARTIFACT_VERSION`) were added --
`AGENT2_CONTRACT_VERSION` already covers the shape of every contract in
this file, and a fourth near-duplicate constant would be exactly the
"complex version registry" Increment 1 instructions warn against.

**Agent 1.x Increment A** (later than the increment this file otherwise
describes) bumped `AGENT1_HANDOFF_VERSION` "1.0" -> "1.1" and added
`kinetic_measurements`/`CuratedKineticMeasurement` to
`Agent1CuratedKnowledgeViewContract` (see `docs/02_agent1_handoff_contract.md`
§4, §9) -- available input data only, not auto-converted into a
`ParameterSpecification`. `AGENT2_CONTRACT_VERSION` did not change: none of
this file's own output contracts (`FullNetwork`, `ModelSpecification`, ...)
changed shape. This does not alter Increment 2's scope below (§25).

**Increment 2** bumped `AGENT2_CONTRACT_VERSION` from `"0.2"` to `"0.3"`:
`FullNetwork` gained `enzyme_associations`/`regulatory_interactions`/
`kinetic_measurements` (each defaulting to `()`, so existing keyword-based
construction is unaffected) plus three new reference-integrity checks, and
a new domain type, `ReactionEnzymeAssociation`, was introduced (§2A).
`AGENT1_HANDOFF_VERSION`/`BOUNDARY_POLICY_VERSION` are unchanged.

**Agent 1.x Increment B** (later than the increment this file otherwise
describes) bumped `AGENT1_HANDOFF_VERSION` "1.1" -> "1.2" and added
`enzyme_states`/`enzyme_modifications`/`allosteric_interactions`/
`enzyme_state_transitions` to `Agent1CuratedKnowledgeViewContract`, plus
`enzyme_state_id` to `CuratedKineticMeasurement` (see
`docs/02_agent1_handoff_contract.md` §4B, §9) -- available input data
only. `AGENT2_CONTRACT_VERSION` did not change: none of this file's own
output contracts changed shape, and Whole-Network Assembly was not
modified to consume the new fields (`docs/05_whole_network_assembly.md`).

## 24. Scope boundaries

As of Increment 1, no behavior beyond validation, identity/reference
integrity, and the four deterministic `ParameterSpecification` properties
existed anywhere in this file's types. **Increment 2** (§25) added the
first real algorithm, whole-network assembly
(`app.agent2.network.assemble_full_network`) -- still specifically absent
from this repository: kinetic-law selection, parameter initialization
policy, boundary heuristics, module partitioning, Antimony generation, and
any Agent 3/4/5 behavior (validation, simulation, parameter fitting, model
critique). Verified structurally by `tests/agent2/test_contracts.py`'s and
`tests/agent2/test_network_assembly.py`'s AST-based import/definition
scans.

## 25. Increment 2 handoff

**Status: implemented** (`app.agent2.network`, see
`docs/05_whole_network_assembly.md` for the full contract). Increment 2
("Whole-Network Assembly") consumes `Agent1CuratedKnowledgeViewContract`
and produces a `FullNetwork` -- the first real algorithm in this
repository. It:

* maps each `CuratedCompartment` to a `CompartmentSpecification` with
  `source_scope=AGENT1_CURATED`;
* maps each `CuratedCompound` referenced by a `CuratedReactionParticipant`
  to a `SpeciesSpecification`, keyed by compound+compartment (§4) --
  deciding that a participant with no compartment reference cannot be
  assembled and must raise (`MissingCompartmentReferenceError`), since
  Agent 1 v1 permits a nullable compartment reference but
  `SpeciesSpecification.compartment_id` is required;
* maps each `CuratedReaction`/`CuratedReactionParticipant` to a
  `ReactionSpecification`/`ReactionParticipantSpecification`, mapping the
  free-string `CuratedReactionParticipant.role` onto the closed
  `ParticipantRole` enum and raising `UnknownParticipantRoleError` when it
  does not cleanly match;
* additionally attaches curated enzyme associations, regulatory
  interactions, and kinetic measurements to `FullNetwork` (§2, §2A, and
  `docs/05_whole_network_assembly.md` §§9-11) -- not originally itemized
  in this section's first draft, but required by Increment 2's own
  governing instructions and implemented alongside the mappings above;
* leaves every `kinetic_law_id`/kinetic-law-assignment/parameter concern
  entirely alone -- Increment 2's own scope ends at a valid, reference-
  consistent `FullNetwork`.

It does not implement kinetic-law assignment, parameter initialization,
boundary assessment, module decomposition, or Antimony generation.

---

> Increment 1 defines what Agent 2 knows how to represent.
>
> It does not yet decide how to assemble a network, choose kinetics,
> initialize missing parameters, assess boundaries, partition modules, or
> generate Antimony.
