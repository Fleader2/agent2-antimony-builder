# Model Modularization: a Derived Layer

## 1. Canonical model vs. modularization

The canonical whole-network model (`ModelSpecification`/`FullNetwork`) remains primary and
unchanged by this increment. A modularization is a **derived interpretation** on top of it:

```text
Canonical Model
   |
   v
ModelModularization
   +-- Modules
   +-- Membership
   +-- Module Ports
   +-- Cross-Module Connections (always computed, never stored)
```

A modularization never moves a species, reaction, parameter, rule, event, or observable out
of the canonical model -- every new type below only *references* an already-existing
canonical component id by string. Modules are never mandatory: a `ModelSpecification` with
`modularizations=()` behaves exactly as it always has.

**Relationship to the pre-existing `ModuleSpecification`/`ModuleDecomposition`** (Increment
7, "Module Decomposition"): that is a different, narrower, already-shipped system -- one
heuristic, boundary-likelihood-driven partition per model
(`ModelSpecification.module_decomposition: ModuleDecomposition | None`, a single field, never
a collection). This increment does not modify, extend, or depend on any of it. The two systems
coexist with zero conflict; nothing in `ModuleSpecification`'s own type ever forbade overlap
or multiplicity in the first place, only the *assembler*, for the *old* type, enforced exactly
one.

## 2. Schema

All new types live in `app.agent2.types`, alongside every other canonical contract type (no
second, parallel type system):

- **`ModelModularization`**: `modularization_id`, `name`, `method` (`ModularizationMethod`),
  `module_ids`, `description`, `confidence` (`BoundaryLikelihood | None` -- qualitative only,
  reusing the pre-existing vocabulary, never a fabricated numeric probability), `assumptions`,
  `provenance_refs`.
- **`ModelModule`**: `module_id`, `name`, `description`, `biological_function`,
  `display_order`, `assumptions`, `provenance_refs`. Carries no back-reference to its owning
  modularization (mirrors `ModuleSpecification`'s own identical "parent names child, child
  names nothing back" convention).
- **`ModuleMembership`**: `membership_id`, `modularization_id`, `module_id`, `component_type`
  (`ModuleComponentType`: `SPECIES`/`REACTION`/`PARAMETER`/`RULE`/`EVENT`/`OBSERVABLE`),
  `component_id`, `role`, `notes`, `confidence`, `provenance_refs`.
- **`ModulePort`**: `port_id`, `modularization_id`, `module_id`, `species_id`, `direction`
  (`ModulePortDirection`: `INPUT`/`OUTPUT`/`INPUT_OUTPUT` -- a new, separate enum from the
  pre-existing `ModuleInterfaceRole`, so the two module systems' vocabularies evolve
  independently), `role` (`ModulePortRole`: `SIGNAL`/`SUBSTRATE`/`PRODUCT`/`REGULATOR`/
  `SHARED_POOL`/`EXTERNAL_INPUT`/`REPORTER`), `assumptions`, `provenance_refs`.

`ModelSpecification` gains four new, flat, additive tuple fields: `modularizations`,
`model_modules`, `module_memberships`, `module_ports` -- the same flat-collection-at-the-top-
level pattern `module_specifications`/`boundary_assessments` already use, not a nested
structure.

`ModularizationMethod` is a closed, seven-value enum: `USER_DEFINED`/`IMPORTED` (both
constructible by this increment's own code) plus `TOPOLOGICAL`/`FUNCTIONAL`/`DYNAMIC`/
`SENSITIVITY_BASED`/`HYBRID` (reserved vocabulary for a future algorithmic increment -- see §7).

## 3. Canonical-component reference strategy

Every reference is a plain string id, validated against the real registry
`ModuleComponentType` names (`spec.full_network.species`/`.reactions`,
`spec.parameters`/`.rules`/`.events`/`.observables`) by `_validate_model_specification_references`
(the identical function, and the identical `_require_known`/`_require_unique` helpers, every
other `ModelSpecification` field has always been checked by). No new validation mechanism was
introduced. Three additional consistency checks specific to this layer:

1. Every `ModelModularization.module_ids` entry must name a real `ModelModule`.
2. Every `ModuleMembership`/`ModulePort`'s `(modularization_id, module_id)` pair must both
   exist *and* be mutually consistent -- the named module must actually appear in that
   modularization's own `module_ids` (not merely exist somewhere else).
3. A `ModuleMembership.component_id` is checked against exactly the one registry its own
   `component_type` names -- a `REACTION` membership is never validated against the species
   registry, etc.

Any violation raises `ValueError` at construction time, identically to every other
`ModelSpecification` reference-integrity check.

## 4. Shared / cross-module species and ports

A canonical species may be the `component_id` of any number of `ModuleMembership` rows, and
the `species_id` of any number of `ModulePort` rows, across different modules of the same
modularization or across entirely different modularizations. It remains exactly one
`SpeciesSpecification` row in `FullNetwork.species` throughout -- confirmed directly by test
(`test_one_species_shared_across_modules_remains_one_canonical_object`).

Cross-module connections are **always derived, never stored**:
`app.agent2.modularization.derive_cross_module_connections(modularization, ports)` finds every
pair of ports, in different modules of the same modularization, naming the identical
`species_id`, where one port's direction allows it to act upstream (`OUTPUT`/`INPUT_OUTPUT`)
and the other downstream (`INPUT`/`INPUT_OUTPUT`). Two `INPUT_OUTPUT` ports on the same species
correctly derive connections in both directions. Deterministic, order-independent, and pure --
it reads `ModulePort` rows a caller already declared and never infers a module boundary on its
own.

## 5. Multiple alternative modularizations

`ModelSpecification.modularizations` is a plain tuple; nothing ranks, orders, or marks one
modularization as more authoritative than another (no `is_primary`/`rank`/`is_canonical`
field exists anywhere in this schema -- confirmed by test). A user-defined split, an imported
one, and a future topology-derived one may all coexist on the identical canonical model
simultaneously, each with its own independent set of modules/memberships/ports, identified
only by their own distinct `modularization_id`.

## 6. Imported / user-defined construction

`USER_DEFINED` and `IMPORTED` are the only two methods this increment's own code constructs.
**Antimony comments are not parsed into module structure in this increment.** The task's own
escape clause is used deliberately: "If module metadata is exported, do so only as clearly
non-semantic annotations/comments; otherwise keep it Agent 2-internal for now." No existing,
deterministic Antimony module-comment convention exists to parse non-speculatively (the
representative fixture's own `// module: ...` comments from the Antimony Import increment are
free text with no agreed grammar), and inventing one risks exactly the "infer module structure
from arbitrary free-text comments" the task explicitly forbids. `ModularizationMethod.IMPORTED`
remains available today for a caller that obtained modularization metadata from an external
source *by its own means* (e.g. a future Workbench integration supplying already-structured
data) and constructs a `ModelModularization` directly -- the identical, simple constructor API
`USER_DEFINED` already uses.

## 7. Automatic discovery boundary

This increment implements no clustering, sensitivity analysis, dynamic-behavior-based
decomposition, or calibration-driven discovery. `TOPOLOGICAL`/`FUNCTIONAL`/`DYNAMIC`/
`SENSITIVITY_BASED`/`HYBRID` are reserved enum values with no producer anywhere in this
codebase today -- a future increment implementing one of these methods only needs to construct
a `ModelModularization`/`ModelModule`/`ModuleMembership`/`ModulePort` set using the identical
types and validation this increment already ships; no interface change is anticipated.

## 8. Antimony and downstream-handoff compatibility

**The canonical model continues to round-trip through Antimony exactly as before.** Module
metadata is not serialized into Antimony text at all in this increment (see §6) -- confirmed
directly: `generate_antimony` on a modularized model produces byte-identical text to the
identical model with no modularization at all
(`test_antimony_round_trip_is_unaffected_by_modularization_metadata`).
`build_canonical_downstream_handoff` is similarly untouched and unaware these new fields
exist -- confirmed identical handoff output with and without modularization metadata present.
Agents 3-5 require no changes and no awareness of this increment at all.
