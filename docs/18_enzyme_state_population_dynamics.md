# Enzyme-State Population Dynamics and Conservation (Multi-Context Catalytic Rate Composition, Stage 2)

## 1. Objective and insertion point

Stage 1 (`docs/12_antimony_generation.md` §11a) let a reaction retain
multiple, independently-resolved catalyst-specific rate contributions and
compose them additively -- but only for protein-general or complex-general
contexts. Two or more `enzyme_state_id` contexts of the same protein
remained deliberately unresolved: nothing in the data model tracked
whether that protein's modification states could be dynamically modeled
at all, and handing the protein's one, undifferentiated total
concentration to more than one sibling state would double-count it.

Stage 2 closes that gap with one new package, `app.agent2
.enzyme_state_dynamics`, and its own public entry point,
`build_enzyme_state_dynamics`. It sits **after** network assembly,
characterization, kinetic-law assignment, and protein-level concentration
resolution -- all four packages run completely unmodified, against the
*original* network -- and **before** parameter declaration and model
assembly, which consume its output instead:

```
assemble_full_network -> characterize_full_network -> assign_kinetic_laws -> resolve_enzyme_concentrations
                                                                                        |
                                                                                        v
                                                                    build_enzyme_state_dynamics
                                                                                        |
                              +-------------------------------------------------------+
                              |                                                       |
                              v                                                       v
      declare_parameters(original assignments, original network)   merge_transition_assignments + declare_parameters(merged, augmented network)
                              |                                                       |
                              v                                                       v
                  assess_boundaries / decompose_network            assemble_model_specification(augmented network, merged assignments, ..., enzyme_state_pools=..., enzyme_state_concentrations=...)
                              |                                                       |
                              +-------------------------------------------------------+
                                                                                        v
                                                                              generate_antimony
```

`declare_parameters` runs **twice**: once against the original
assignments/network (feeding boundaries/module decomposition, which never
need to know about enzyme-state dynamics), and once against the merged
assignments/augmented network (feeding the final model). Both calls are
pure and cheap; this is simpler and safer than trying to make boundaries/
modules tolerate a partially-augmented input.

## 2. Why a protein's states are not dynamically modeled by default

A protein having two or more curated `CuratedEnzymeState` rows is **not**,
by itself, grounds for dynamic modeling -- that would be inferring a
transition merely because two states share a parent protein, which the
task's own instructions explicitly forbid. A protein's states become a
**pool** only when at least one curated `CuratedEnzymeStateTransition`
connects two of that protein's own states. A protein with two states and
zero curated transitions is left completely untouched: no species, no
reactions, no pool -- Stage 1's own `_ambiguous_state_parent_keys`
withholding in `app.agent2.parameters.builder` continues to apply exactly
as before (**existing single-state and isozyme behavior is unchanged**).

A transition whose two endpoints resolve to two *different* parent
proteins is a real data inconsistency (never a genuine modification-state
transition) and is silently excluded -- never fabricated across proteins.

Within a dynamically-modeled group, an individual state is excluded (and,
if that drops the group below two states, the whole protein is left
unmodeled) when it has no resolvable `compartment_id` -- a disclosed data
gap, never a fabricated compartment.

## 3. Species and reactions

Each modeled state becomes one `SpeciesSpecification`
(`source_enzyme_state_id` set, mutually exclusive with
`source_compound_id` -- `docs/04_core_domain_contracts.md` §4) in its own
curated compartment. Each modeled transition becomes one ordinary
`ReactionSpecification` (two participants: the *from* state as
`REACTANT`, the *to* state as `PRODUCT`, both stoichiometry 1,
`reversible=False`) plus one hand-built `KineticLawAssignment`
(`kinetic_law_type=MASS_ACTION`, `assignment_source=
DETERMINISTIC_STRUCTURAL`, reason code `KineticLawReasonCode
.ENZYME_STATE_TRANSITION_STRUCTURAL_MASS_ACTION`, all three catalytic-
context fields `None`) -- **first-order mass action is the only
mechanistic form ever assigned**, never a guessed enzymatic mechanism. A
curated, explicitly reversible interconversion is represented as **two**
separate one-way transition rows (and therefore two separate reactions),
never one `reversible=True` reaction and never an invented symmetry.

Both the species and the reaction reuse existing, unmodified types and
existing, unmodified downstream machinery end-to-end (parameter
declaration's `MASS_ACTION` path, `ModelSpecification`'s reference
validation, Antimony generation's reaction/species rendering) -- no new
serialization logic was needed anywhere in this call graph. This is
deliberately distinct from the pre-existing `SIMPLE_ELEMENTARY_TRANSITION`
/`SIMPLE_REVERSIBLE_ELEMENTARY_TRANSITION` reason codes
(`app.agent2.kinetics.selector._decide_structural`), which classify an
*ordinary, already-curated* reaction (real compound participants) tagged
`ReactionClass.STATE_TRANSITION` via the normal characterization
pipeline -- this package's own reactions are synthesized fresh, with no
curated participants at all, used only when `CuratedEnzymeStateTransition
.reaction_id` names no such ordinary reaction (which is every real case
seen so far -- see §7).

Because a transition reaction's own `reaction_id` is synthetic
(`enzyme-state-transition::<transition.id>`), no curated
`CuratedKineticMeasurement` can ever match it by reaction id -- its rate
constant is therefore always `HEURISTIC_INITIALIZATION` in practice
(disclosed via the ordinary, unmodified `_declare_mass_action` path),
never presented as biochemical evidence. Linking a transition's rate
constant to curated evidence via its own optional `reaction_id` cross-
reference is a real, disclosed limitation, deferred (see §8).

## 4. Conservation and initial-concentration precedence

For a dynamically-modeled protein, each state's own initial concentration
is resolved with exactly two tiers, never a third:

1. **`MEASURED_STATE_SPECIFIC_CONCENTRATION`** -- a real, unambiguous,
   directly-curated `PROTEIN_CONCENTRATION` observation naming this exact
   state (`CuratedQuantitativeObservation.enzyme_state_id` -- a new,
   optional field on Agent 2's own mirror type, currently never populated
   by any real Agent 1 handoff; see §7). Two or more disagreeing
   observations for the same state leave it unresolved at this tier,
   never averaged or arbitrarily chosen.
2. **`POOL_CONSERVATION_DERIVED`** -- only when the parent protein's own
   total concentration (`resolve_enzyme_concentrations`'s existing,
   unmodified protein-level output) is resolved *and* exactly one sibling
   state in the modeled group is otherwise unknown: that state's value is
   the deterministic remainder (total minus every known sibling). Two or
   more unknown siblings, or an unresolved total, leave every remaining
   state unresolved -- **never an invented fraction, never an even
   split**. A remainder that would be negative (a real data
   inconsistency -- a measured state exceeding the parent's own total) is
   also left unresolved rather than emitting an impossible negative
   concentration.

Every other state is left with `initial_concentration=None`,
`initialization_source=None`, and an explicit `assumptions` entry naming
why. `ParameterSource.DERIVED_FROM_POOL_CONSERVATION` is a new provenance
rung (between `DERIVED_FROM_MACRO_KINETICS` and
`HEURISTIC_INITIALIZATION`), used only for tier 2 above.

`app.agent2.parameters.builder._enzyme_concentration_for_assignment` now
prefers a resolved state-level concentration (either tier) over Stage 1's
blanket ambiguous-sibling withholding, for that exact state's own
catalytic-context parameters -- never for a sibling, and never
overwriting the parent-level total's own, unchanged, protein-general use.

## 5. Composing simultaneously-present states

`app.agent2.antimony.generator._context_group_composability` (Stage 1)
now also recognizes a homogeneous group of two or more distinct
`enzyme_state_id` contexts as composable, but **only** when every one of
those states belongs to the identical parent protein's dynamically-
modeled pool (`ModelSpecification.enzyme_state_pools` -- never inferred
from `FullNetwork.enzyme_states` directly). Two states with no such pool,
or spanning two different proteins' pools, still resolve to
`UNRESOLVED_MULTIPLE_CONTEXTS` exactly as in Stage 1.

This is safe precisely because this package never hands the same
protein's full concentration to more than one sibling state (§4): each
contribution's own parameters already account for (or honestly withhold)
its own share, so summing the resulting rates additively is exactly as
safe as summing two isozymes' rates (§11a) -- never a claim that every
state is simultaneously, fully present at the parent's own total
abundance.

## 6. New/changed contract shapes

* `EnzymeConcentration.enzyme_state_id` (new, optional) -- `None` means
  the pre-existing protein-level total; set means one state's own share.
* `EnzymeConcentrationBasis.MEASURED_STATE_SPECIFIC_CONCENTRATION` /
  `.POOL_CONSERVATION_DERIVED` (new members, state-level only).
* `CuratedQuantitativeObservation.enzyme_state_id` (new, optional,
  forward-compatible only -- see §4/§7).
* `SpeciesSpecification.source_enzyme_state_id` (new, optional, mutually
  exclusive with `source_compound_id`).
* `ParameterSource.DERIVED_FROM_POOL_CONSERVATION` (new member).
* `EnzymeStatePool` (new type: `protein_id`, `state_ids`,
  `transition_ids`, `policy_version`, `assumptions`, `provenance_refs`).
* `ModelSpecification.enzyme_state_pools` / `.enzyme_state_concentrations`
  (new fields, both default `()`; the latter kept separate from the
  pre-existing `enzyme_concentrations` so that field's own "at most one
  per protein" invariant is undisturbed by an unrelated, state-level
  figure). Both are reference-checked in
  `_validate_model_specification_references` against
  `full_network.enzyme_states`/`.enzyme_state_transitions`.
* `KineticLawReasonCode.ENZYME_STATE_TRANSITION_STRUCTURAL_MASS_ACTION`
  (new member).
* `build_model_assumptions` gained an eleventh disclosed-incompleteness
  category: one `ModelAssumption` (category `"enzyme_state_dynamics"`,
  reason code `ENZYME_STATE_POOL_CONSERVATION_APPLIED`) per
  `EnzymeStatePool`.

Every new field defaults to its type's own "absent" value, so every
pre-existing construction of any of these types is unaffected.

## 7. Real `sce00061` evaluation

The saved fresh-pilot handoff
(`artifacts/pilots/yeast_fatty_acid_pilot2_evidence_utilization/
08_agent1_curated_knowledge_view.json`) carries **zero**
`enzyme_states`, **zero** `enzyme_state_transitions`, and zero
`quantitative_observations`/`kinetic_measurements` tagged with an enzyme
state at all (confirmed both at Stage 1 and re-confirmed here).
Running `assemble_full_network` -> `resolve_enzyme_concentrations` ->
`build_enzyme_state_dynamics` against this real handoff produces **zero**
pools, **zero** state concentrations, **zero** transition assignments, and
an augmented network byte-for-byte identical (species/reactions/
`network_id`) to the original -- a confirmed, safe no-op. This increment
is therefore validated exclusively by synthetic/regression tests
(`tests/agent2/test_enzyme_state_dynamics.py`,
`tests/agent2/test_antimony_generation.py`), including one full,
real-pipeline "synthetic phosphorylation regression"
(`test_phosphorylation_regression_end_to_end`) exercising every stage
above together.

## 8. Scope exclusions honored

No phosphorylation/dephosphorylation *biochemistry* is invented (only a
generic, disclosed first-order mass-action structural default). No
state-population fraction is ever invented (§4). No total-enzyme
conservation *equation* is emitted as a separate, explicit model
constraint -- it is enforced only insofar as species initial values are
computed consistently with it; nothing else asserts it dynamically at
simulation time (Agent 3's job, if ever needed). No new Agent 1 connector
was added -- `CuratedQuantitativeObservation.enzyme_state_id` is a purely
internal, forward-compatible mirror-type extension, populated by no real
handoff today. No Agent 4 calibration. Linking a transition's rate
constant to curated kinetic evidence via its own optional `reaction_id`
cross-reference remains unimplemented (§3) -- a real, disclosed
limitation for a future increment, not exercised by any real or synthetic
data today.

## 9. Versioning

`ENZYME_STATE_DYNAMICS_POLICY_VERSION` ("enzyme-state-dynamics-v1", new).
`ANTIMONY_GENERATION_POLICY_VERSION` "antimony-generation-v3" ->
"antimony-generation-v4" (composability extension).
`PARAMETER_DECLARATION_POLICY_VERSION` "parameter-declaration-v6" ->
"parameter-declaration-v7" (state-level concentration precedence).
`MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION` "model-specification-v9" ->
"model-specification-v10" (new fields threaded, new assumption category).
`AGENT2_CONTRACT_VERSION` "0.11" -> "0.12" (real type-shape changes, §6).
