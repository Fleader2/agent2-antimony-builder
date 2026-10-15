# Module Decomposition/Modularization Reconciliation

## 1. Objective

Before this increment, Agent 2 carried **two** independent module-representation systems:

* The **old**, build-time, GENERATED-only system (`app.agent2.boundaries.assess_boundaries`
  -> `app.agent2.modules.decompose_network`): `BoundaryAssessment`, `ModuleSpecification`,
  `ModuleDecomposition`, `InterModuleBoundaryInterface`, `ModuleBoundaryInterface`, stored
  directly on `ModelSpecification` as `boundary_assessments`/`module_decomposition`/
  `module_specifications`, with a hard-enforced "exactly one `ModuleDecomposition`" rule.
* The **newer**, origin-agnostic Model Modularization layer
  (`docs/22_model_modularization.md`): `ModelModularization`/`ModelModule`/`ModuleMembership`/
  `ModulePort`, supporting zero/one/many modularizations for a model of either
  `ModelSourceType` -- but, before this increment, entirely **dormant**: nothing in
  `app.agent2.pipeline`/`app.agent2.model_specification`/`app.agent2.antimony` ever
  constructed or consumed it.

This increment makes the newer family the **one, unified, stored module-related
representation**, for a model of either source type, while reusing the old system's
algorithm and executable-submodel-generation machinery rather than discarding or duplicating
either.

```text
GENERATED ─┐
           ├─→ canonical whole-network model (ModelSpecification)
IMPORTED ──┘
                    ↓
    modularizations / model_modules / module_memberships / module_ports
    (zero, one, or many -- never required, never one marked canonical)
                    ↓
          optional, explicitly-selected modularization_id
                    ↓
    app.agent2.antimony.generate_module_artifacts(model, modularization_id)
                    ↓
          module view(s), and -- when boundary treatment is
          explicit -- a standalone executable Antimony submodel
```

## 2. What was retained, adapted, deprecated, or removed

| Old type/field | Disposition |
| --- | --- |
| `app.agent2.boundaries.assess_boundaries` | **Retained, unchanged.** Still the one heuristic boundary-evidence algorithm. |
| `app.agent2.modules.decompose_network` | **Retained, unchanged.** Still the one connected-component partitioning algorithm (docs/10). |
| `BoundaryAssessment`, `ModuleSpecification`, `ModuleDecomposition`, `InterModuleBoundaryInterface` | **Retained as types**, still produced by the two functions above as pipeline-internal intermediate artifacts (`BoundaryAssessmentSet`/`ModuleDecompositionSet`) -- exactly like `KineticLawAssignmentSet`/`ParameterDeclarationSet` already were never stored directly on `ModelSpecification` either. No longer stored on `ModelSpecification`. |
| `ModelSpecification.boundary_assessments` | **Removed.** Confirmed zero downstream consumers (`build_canonical_downstream_handoff` never exposed it). |
| `ModelSpecification.module_decomposition` / `.module_specifications` | **Removed**, replaced by `modularizations`/`model_modules`/`module_memberships`. |
| `ModuleBoundaryInterface`, `ModuleInterfaceRole` | **Removed entirely.** Never populated in production (see §5). Their entire useful content (per-species boundary treatment) now lives directly on `ModulePort` (`externally_controlled`/`initial_value`/`unit`). |
| `ModuleSpecification.boundary_interfaces` / `.has_explicit_boundary_interfaces` | **Removed** (the identically-dead fields driven by the type above). `ModuleSpecification.boundary_interface_ids` (a different, still-live concept -- a reference to `InterModuleBoundaryInterface` records) is untouched. |
| `Agent2OutputPackage.boundary_assessments` / `.module_decomposition` | **Removed**, same rationale as the `ModelSpecification` fields. |
| `Agent2OutputPackage.module_artifacts` | **Retained**, but no longer auto-populated by `generate_antimony` (§4). |
| `assemble_model_specification`'s `_require_exactly_one_decomposition` | **Removed.** `boundaries`/`modules` are now optional (default `None`); zero, one, or many decompositions are all valid. |
| `generate_antimony`'s automatic `module_artifacts` loop over `model.module_specifications` | **Removed**, replaced by the new, explicit, opt-in `generate_module_artifacts` (§4). |

Nothing was left as dead, unreachable parallel infrastructure: every old type that remains
is either still genuinely used by its own unchanged algorithm, or was removed outright.

## 3. The adapter: `app.agent2.modularization.modularizations_from_decomposition_set`

Converts a `ModuleDecompositionSet` (the heuristic algorithm's own, unchanged output) into a
`ModularizationBundle` (`modularizations`, `model_modules`, `module_memberships`,
`module_ports` -- ready to spread directly onto `ModelSpecification`'s own fields of the same
names):

* One `ModelModularization` per `ModuleDecomposition`, `method=ModularizationMethod
  .TOPOLOGICAL` (connected-components-after-removing-boundary-edges is fundamentally a
  topological/connectivity method -- never a *new* automatic-discovery algorithm: the
  discovery already existed, this only reshapes its already-decided output, per task §8's own
  "do not implement automatic module discovery" reading as "do not implement a new one").
* One `ModelModule` + a `ModuleMembership` row per reaction/species/parameter, per
  `ModuleSpecification`.
* One `ModulePort` pair (OUTPUT on the upstream module, INPUT on the downstream module) per
  shared species of each `InterModuleBoundaryInterface`.

**Module ids are qualified by their own owning `modularization_id`**
(`f"{modularization_id}::{raw_module_id}"`), never the bare `module_NNN` the heuristic
algorithm names internally. `ModelSpecification.model_modules[].module_id` must be globally
unique across the *entire* model (never merely unique per modularization) -- two independent
decompositions of the identical network legitimately produce the identical bare id (both
naming their first module `"module_001"`), a real, expected collision once more than one
decomposition/modularization can coexist on one `ModelSpecification` at all (which, before
this increment, was structurally impossible: exactly one was always enforced).

`assemble_model_specification(network, kinetic_laws, parameters, boundaries=None,
modules=None, ...)`: when `modules` is supplied (`boundaries` is required together with it),
its own decompositions are converted via the adapter and merged into the result; when both
are omitted, the resulting `ModelSpecification` simply carries no modularization at all --
exactly as valid, never an error. The real pipeline (`app.agent2.pipeline
.run_agent2_pipeline`) continues to compute and pass real `boundaries`/`modules` for every
build, so production behavior is unchanged: a GENERATED build still gets exactly one
TOPOLOGICAL modularization automatically, by default.

## 4. Standalone submodel / module-view generation: one explicit, opt-in entry point

`app.agent2.antimony.generate_module_artifacts(model, modularization_id, module_ids=None)`
replaces the old, implicit "one `ModuleAntimonyArtifact` per `model.module_specifications`
entry, generated automatically by every call to `generate_antimony`." It:

* Requires `modularization_id` to name a real entry in `model.modularizations` (raises
  `AntimonyReferenceError` otherwise) -- task §5's own "if executable submodels are
  requested, require an explicit selected modularization id."
* Reuses `generate_antimony`'s own rendering machinery (`_build_rendering_context`,
  `_generate_module_artifact`, `_render_standalone_module`) unchanged in substance, refactored
  to take membership/port-derived inputs (reaction/species/parameter ids, `ModulePort` rows)
  rather than a `ModuleSpecification` object directly -- task §3's own "reuse old logic...
  do not duplicate it into a second exporter," satisfied literally: there is exactly one
  module-artifact-rendering code path, used by both the GENERATED-heuristic-derived and any
  user-defined/imported modularization.
* Works identically for a `GENERATED` or an `IMPORTED` model: every reaction/species/
  parameter id a module's own `ModuleMembership` rows name, and every `ModulePort`'s own
  boundary treatment, comes from `model.module_memberships`/`.module_ports` alone, never
  anything origin-specific.

**Standalone-eligibility rule** (task §6's "module" vs. "standalone submodel" distinction):
a module is eligible for a real, `EXECUTABLE` standalone Antimony submodel only when at least
one of its own `ModulePort` rows has `externally_controlled=True` -- the single, unified
successor to the old `ModuleBoundaryInterface`/`has_explicit_boundary_interfaces` predicate.
A module with no such port still gets an ordinary `VIEW_ONLY` `antimony_view` (never an
error, never a fabricated boundary condition). `ModulePort.externally_controlled`/
`.initial_value`/`.unit` absorb the entire useful content of the removed
`ModuleBoundaryInterface` directly onto the port record itself, so a module interface and its
own boundary-condition treatment are one record, never two parallel ones -- an ordinary
cross-module port (used only by `derive_cross_module_connections`) simply leaves
`externally_controlled=False` (the default), a purely descriptive fact never eligible to seed
a `const <species>;` declaration on its own.

Module/standalone generation never duplicates canonical species or reactions: both
`generate_antimony` (whole-network) and `generate_module_artifacts` (per-module) read
`model.full_network`/`.kinetic_laws`/`.parameters` by reference only, and neither mutates
`model` (confirmed directly by test).

## 5. Why standalone submodel generation had never actually run in production before this

`decompose_network` never populated `ModuleSpecification.boundary_interfaces` (the old field)
-- nothing in this repository's real pipeline ever constructed a `ModuleBoundaryInterface`.
The old "standalone executable module model" capability existed only in hand-crafted unit
tests; every real build's own module artifacts were always `VIEW_ONLY`. This increment does
not change that default (the heuristic-derived `TOPOLOGICAL` modularization still never sets
`externally_controlled=True` on any port automatically -- it has no basis to decide which
boundary species should be clamped, so it correctly discloses nothing rather than guessing);
it makes the capability real and reachable for a *caller* who supplies explicit boundary
treatment (a `USER_DEFINED`/`IMPORTED` modularization, or a future algorithmic one), for
either model origin.

## 6. Generated/imported symmetry

`apply`-style attachment of modularization data is a plain `ModelSpecification` field
assignment (`modularizations`/`model_modules`/`module_memberships`/`module_ports`), performed
identically by `assemble_model_specification` (GENERATED path, when `boundaries`/`modules`
are supplied) and by a caller directly via `dataclasses.replace` on the result of
`app.agent2.antimony_import.import_antimony` (IMPORTED path) -- no origin-specific branch
exists anywhere in `ModelSpecification.__post_init__`'s own validation of these four fields,
`generate_module_artifacts`, or the adapter. Verified directly by test
(`tests/agent2/test_modularization.py
::test_same_user_defined_modularization_works_identically_for_generated_and_imported_models`,
`::test_standalone_submodel_export_works_for_an_imported_model_with_explicit_boundary_port`):
the identical `ModelModularization`/`ModelModule`/`ModuleMembership` bundle produces
structurally equivalent module views for a GENERATED and an IMPORTED model built from the
same reaction/species shape, and a real `EXECUTABLE` standalone submodel is produced from an
IMPORTED model exactly as from a GENERATED one, given the identical explicit-boundary-port
input.

## 7. Multiple alternative modularizations

Never special-cased: `assemble_model_specification` converts every decomposition in
`modules.decompositions` (zero, one, or many) into its own, independent, equally-unranked
`ModelModularization` (never one marked more authoritative, no `is_primary`/`rank` field
anywhere in the schema -- unchanged from docs/22 §5). A caller may also attach several
independently-constructed `USER_DEFINED`/`IMPORTED` modularizations alongside the
heuristic-derived one via the identical `dataclasses.replace`/concatenation pattern. Verified
by test (`tests/agent2/test_model_specification.py
::test_multiple_decompositions_each_become_their_own_modularization`,
`tests/agent2/test_modularization.py::test_multiple_alternative_modularizations_coexist`).

## 8. One intentional, cosmetic Antimony-text difference

`ModelSpecification.model_id` changed from `f"model::{network.network_id}::
{decomposition.decomposition_id}"` to `f"model::{network.network_id}"` -- the canonical
model's own id can no longer depend on a decomposition that may not even exist (zero,
one, or many may now be present). This is the *only* difference in the generated whole-network
Antimony text for the real yeast lipid-biosynthesis regression (confirmed by direct byte
diff): the top-level `model <name>()` declaration line is shorter; every compartment,
species, reaction, parameter, and kinetic-law line is byte-identical. No module-artifact
output is affected (none was ever auto-generated for any real build before this increment
either, per §5).

## 9. Contract/version changes

* `AGENT2_CONTRACT_VERSION` `"0.14"` -> `"0.15"`.
* `MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION` `"model-specification-v12"` ->
  `"model-specification-v13"`.
* `ANTIMONY_GENERATION_POLICY_VERSION` `"antimony-generation-v6"` ->
  `"antimony-generation-v7"`.
* New `MODULARIZATION_POLICY_VERSION = "modularization-v1"` (the adapter's own conversion
  policy version -- never the modularization schema's own version, which has none, per
  docs/22).
* `AGENT2_DOWNSTREAM_CONTRACT_VERSION` **unchanged** -- confirmed zero downstream (Agent
  3/4/5, harness, Workbench) consumers of any removed or changed field; see §2's own table.
  `app.agent2.pipeline.build_canonical_downstream_handoff` was not modified by this
  increment.

## 10. Scope boundary honored

No automatic module discovery was *newly* implemented (the existing heuristic algorithm was
reused, not reinvented). No sensitivity-based, calibration-driven, or dynamic-behavior-based
modularization. No UI. No new Agent 3/4 logic (the downstream contract is unaffected). No
regulatory mechanism. This increment is representation + reconciliation + executable-submodel
derivation only, exactly as scoped.

## 11. Known limitations / future work

* The heuristic `TOPOLOGICAL` modularization never sets `ModulePort.externally_controlled`,
  so it never produces a real standalone submodel on its own (§5) -- a future increment could
  teach it to propose explicit boundary treatment for its own selected cuts, but doing so
  requires a real policy decision (what value to clamp a cut boundary species at) squarely
  outside this increment's own "representation + reconciliation" scope.
* A future `FUNCTIONAL`/`DYNAMIC`/`SENSITIVITY_BASED`/`HYBRID` automatic-discovery
  modularization method needs no interface change at all -- it only needs to construct a
  `ModelModularization`/`ModelModule`/`ModuleMembership`/`ModulePort` set using the identical
  types and validation this increment (and the prior Model Modularization increment) already
  ship, exactly as docs/22 §7 already anticipated.
* `generate_module_artifacts`'s own module-level render never includes `model.rules`/
  `.events`/`.observables` (only the whole-network `generate_antimony` render does) -- a
  disclosed, pre-existing gap inherited unchanged from the old `_generate_module_artifact`,
  relevant only to an IMPORTED model's own module-level view, not fixed by this increment.
* Recursive/nested modularization (a module containing sub-modularizations of its own) is not
  implemented or anticipated by this schema -- genuinely out of scope, not merely deferred.

## 12. Testing

* `tests/agent2/test_model_specification.py`/`test_model_specification_scope.py`: zero/one/
  many decompositions all accepted; module/membership/port content preserved verbatim through
  the adapter; candidate-boundary and selected-boundary-interface disclosure preserved in the
  unified representation.
* `tests/agent2/test_antimony_generation.py`: module view containment, multiple modules, no
  source/sink-reaction invention, `VIEW_ONLY`-without-boundary-treatment, standalone
  generation when boundary treatment is explicit and resolved, standalone withheld when
  kinetics/catalytic composition are unresolved, standalone never fabricates a boundary
  value, byte-identical determinism, no mutation of the input model.
* `tests/agent2/test_modularization.py` (pre-existing, unaffected by this increment, plus two
  new tests): GENERATED-with-no-modularization, IMPORTED-with-no-modularization, shared/
  overlapping membership, no duplication of canonical entities, no regression to whole-network
  Antimony export, downstream handoff unchanged, multiple alternative modularizations, **and**
  (new) the identical user-defined modularization bundle applied to both a GENERATED and an
  IMPORTED model, and a real standalone submodel export from an IMPORTED model.
* Real yeast lipid-biosynthesis regression: `run_agent2_pipeline` produces 26 modules across
  one TOPOLOGICAL modularization, 265 memberships, 0 ports (no `HIGH`/`VERY_HIGH` boundary
  evidence exists yet in this organism's real curated data), all `VIEW_ONLY` -- `EXECUTABLE`
  readiness and whole-network Antimony text otherwise unaffected (§8).
* Full cross-repo validation: Agent 2's own suite, the harness's real live-DB yeast workflow,
  and the Workbench's own suite all re-run clean after this increment (§ completion report).
