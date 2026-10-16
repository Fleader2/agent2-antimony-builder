# Canonical Submodel Materialization for Recursive Modularization

## 1. Goal

Given a parent `ModelSpecification` + `modularization_id` + `module_id`, materialize a new,
independently valid, genuinely scoped canonical `ModelSpecification` containing only that
module's own internal reactions and their dependency closure -- never the whole parent network
carried over unchanged.

## 2. The fix this closes

`app.agent2.candidate_orchestration.round.build_submodel` (Recursive Agent-4-Assisted Candidate
Search Orchestration increment) carried `full_network`/`kinetic_laws`/`parameters` over from the
parent *unchanged* -- a disclosed, acceptable scope limit for "usable" at the time: only the
modularization itself was scoped to one module, so a cross-boundary edge to a reaction outside
the module was counted as a cut edge exactly as any other network edge leaving the current seed
was. `build_submodel` now delegates to `materialize_submodel` (`app.agent2
.submodel_materialization`) below -- its own external signature/return shape
(`tuple[ModelSpecification, str]`) is unchanged, but the submodel it returns is now genuinely
scoped.

## 3. Materialization API

```python
materialize_submodel(
    model: ModelSpecification, modularization_id: str, module_id: str, *, policy_version=...
) -> SubmodelMaterializationResult
```

Raises `SubmodelMaterializationReferenceError` for an unknown `modularization_id`/`module_id`,
or a module with zero `REACTION` memberships (nothing to materialize). Never mutates `model`.

## 4. Dependency-closure policy

Computed fresh from the module's own `REACTION` `ModuleMembership` rows and the parent's
reaction/kinetic-law/species/parameter registries -- **never** trusted from any pre-existing
`SPECIES`/`PARAMETER` `ModuleMembership` rows a candidate happens to carry. Those rows are not a
reliable closure for a search-generated candidate: `app.agent2.antimony.generator
.generate_module_artifacts` already documents (and falls back around) the fact that a
search-generated module's own `PARAMETER` memberships may be absent entirely.

Retained, deterministically, from the module's own reactions: every participating species; every
`KineticLawSpecification` whose `reaction_id` is in scope, and every parameter/species its own
`parameter_ids`/`species_ids` name; every compartment a retained species lives in; and every
*explicit enzyme species* -- a plain `SpeciesSpecification` whose `source_protein_id`/
`source_enzyme_state_id` matches a retained kinetic law's own `protein_id`/`enzyme_state_id`
(these two fields are mutually exclusive on both types, so the match is a simple either/or, never
both at once).

## 5. FullNetwork scope decision

Every `FullNetwork` field documented elsewhere in this repository as "supporting data...
never used to infer a species, a reaction, or a compartment" (`enzyme_associations`, `genes`,
`proteins`, `regulatory_interactions`, `kinetic_measurements`, `enzyme_modifications`,
`allosteric_interactions`, `enzyme_state_transitions`, `experimental_contexts`,
`quantitative_observations`, `publications`) is dropped entirely -- "do not retain unrelated
parent-network components" (task instructions §1). `enzyme_states` is the one exception: it is
*filtered*, never dropped, to just the states a retained explicit enzyme species/kinetic law
names -- required to keep `SpeciesSpecification.source_enzyme_state_id` (the field that *makes*
a retained species an explicit enzyme species) referentially valid. `ModelSpecification`'s own
`enzyme_concentrations`/`enzyme_state_pools`/`enzyme_state_concentrations` are dropped entirely:
they are provenance for *how* an enzyme species' numeric value was derived, never required for
executable semantics -- the retained species' own `initial_amount`/`initial_concentration`
already carries the resolved value `generate_antimony` actually reads.

A retained reaction's own `enzyme_association_ids`/`regulatory_interaction_ids` are stripped to
`()` (their own registries are gone) -- these name curation-provenance *links*, never executable
semantics (task instructions §6 names stoichiometry/reversibility/kinetic laws/enzyme
concentrations/parameters as the protected semantics; association/regulation links are not among
them).

## 6. Boundary semantics (§2)

Reuses `app.agent2.types.ModulePort`/`ModulePortDirection`/`ModulePortRole` verbatim -- that
type already carries every role the task names (input/output/input-output/
externally-controlled/shared-pool via the pre-existing `SHARED_POOL` role). The module's own
existing `ModulePort` rows are restamped (never re-authored) onto the new
modularization/module id. `BoundaryTreatmentRecord` (in `submodel_materialization.types`) is
only a disclosure-friendly summary of a retained port's own already-existing facts for
`SubmodelMaterializationLineage`, never a new boundary vocabulary.

## 7. Rules/events/observables: a disclosed heuristic, never real parsing

`app.agent2.types` documents `RuleSpecification.formula`/`EventSpecification.trigger_formula`/
`ObservableSpecification.formula` as opaque text, "never parsed into an AST or evaluated," and
`RuleSpecification.variable` as "deliberately never checked against FullNetwork's species/
compartment ids." `app.agent2.submodel_materialization.closure` honors that: it scans each
formula (plus a rule's `variable`, an event's `delay_formula`/`priority_formula`/assignment
variables/formulas) for identifier-shaped tokens, and retains the rule/event/observable only if
every token that happens to match a real parent-model id is within the retained closure.
A formula referencing *no* known parent id at all (a bare literal/unit symbol) is retained
vacuously -- never rejected merely because nothing resolved, mirroring `variable`'s own
established "never invent a cross-reference requirement" convention. A rule/event/observable
that fails this scan is excluded and recorded in `unresolved_dependencies` as an
`UnresolvedDependencyDisclosure` -- disclosed, never silently dropped, and never raised (this is
an optional-fidelity exclusion, not a structural failure).

Any other structural gap a retained reaction/kinetic-law genuinely cannot do without (should be
impossible given the parent's own reference-integrity validation) is left for the final,
assembled `ModelSpecification`'s own already-complete constructor validation to reject loudly --
never silently re-validated a second time by this package.

## 8. Lineage/provenance (§4)

`SubmodelMaterializationLineage` records `parent_model_id`/`parent_modularization_id`/
`parent_module_id`, the submodel's own `submodel_modularization_id`/`submodel_module_id`, every
retained id by type, `explicit_enzyme_species_ids`, `boundary_treatments`, and
`materialization_policy_version`. The submodel's own `ModelSpecification.provenance_refs` also
carries a single, additional `submodel-materialization::...` reference string -- exact
traceability back to the parent, readable without needing the full `SubmodelMaterializationResult`
in hand.

## 9. Recursive compatibility (§5)

The materialized submodel is an ordinary `ModelSpecification` with one modularization wrapping
one module (the retained closure, under the *same* `module_id` the parent used -- preserving
traceability directly). Confirmed directly against the existing, unchanged machinery:
`search_candidate_modularizations`/`run_candidate_search_round` (via `build_submodel`'s own
updated delegation), `generate_antimony`/`generate_module_artifacts` (produces a genuinely
`EXECUTABLE` standalone Antimony artifact), and `build_module_calibration_request` (the
Harness → Agent 3 → Agent 4 module-calibration entry point) all accept the materialized submodel
with no code-path change. No automatic recursive descent is implemented or triggered by this
increment (task instructions: "do not implement automatic recursive descent... in this
increment").

## 10. Tests / lint

`tests/agent2/test_submodel_materialization.py` (24 tests): exact reaction scoping; species/
parameter/compartment dependency closure; explicit-enzyme-species retention (present for the
owning module, absent for an unrelated one); unrelated parent components (and every dropped
`FullNetwork` supporting-data field) excluded; a module with zero reactions rejected; unknown
`modularization_id`/`module_id` rejected; boundary ports preserved (including the no-port case);
rules/events/observables retained only when a reference-token scan confirms in-scope (and
disclosed, never silently dropped, when not); a formula referencing no known parent id at all
retained vacuously; parent-child lineage; GENERATED/IMPORTED parent symmetry; no mutation of the
parent model; recursive-search compatibility; standalone Antimony generation; Agent 3/4
module-calibration-request compatibility; and `build_submodel`'s own updated delegation.
`tests/agent2/test_candidate_orchestration.py`'s pre-existing 21 tests (including
`test_build_submodel_is_usable_by_the_same_round_function`) pass unchanged against the new,
genuinely-scoped `build_submodel` output. Full Agent 2 suite: 1301 passed (1277 pre-existing +
24 new); lint clean (zero overlap between touched files and the repository's pre-existing,
untouched-file lint findings). Harness (101 passed, non-DB suite; real live `sce00061`
five-agent workflow unaffected -- this increment touches no code path that workflow exercises),
Workbench (88 passed), Agent 3 (37 passed), and Agent 4 (64 passed) suites all pass unchanged.

## 11. Remaining gaps before automatic hierarchical recursion

- No automatic recursive descent: nothing in this increment decides *when* to materialize a
  submodel and search it further -- that decision-loop (if ever wanted) is explicitly out of
  scope here, mirroring the Recursive Agent-4-Assisted Candidate Search Orchestration
  increment's own identical "do not automatically recurse into every accepted module yet"
  stance.
- The rule/event/observable reference scan is a disclosed, conservative heuristic (identifier
  tokens, not real parsing) -- a formula containing a coincidental identifier-shaped substring
  that is not actually a reference (unlikely in practice, since Antimony/SBML formula grammar is
  itself just arithmetic over identifiers) would be treated as a real reference; this can only
  ever make the scan more conservative about exclusion, never cause a false retention.
- `model_assumptions`/`assumptions`/`source_provenance` are carried into the submodel verbatim
  (never filtered to just the retained closure) -- they are free-form, non-reference-validated
  text, so this is a disclosed completeness/precision trade-off, not a correctness risk.
