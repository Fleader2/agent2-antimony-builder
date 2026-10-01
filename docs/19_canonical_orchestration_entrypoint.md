# Canonical Orchestration Entrypoint and Downstream Contract (Five-Agent Workflow V1 Hardening)

## Purpose

Before this increment, every discrete Agent 2 stage function (translate, assemble, characterize,
assign kinetic laws, resolve reaction context, resolve enzyme concentrations, build enzyme-state
dynamics, declare parameters, assess boundaries, decompose modules, assemble the model
specification, generate Antimony) was independently implemented and independently tested, but
**no single piece of already-committed code chained them together end to end**. This left two
real integration debts:

1. Any real caller (the five-agent integration harness, or any future one) had to either
   hand-chain all eleven-plus stages itself — risking silently mis-implementing Agent 2's own
   orchestration — or consume an already-captured artifact instead of ever running Agent 2 live.
2. Agents 3, 4, and 5 each independently named the identical real downstream artifact shape with
   three different `contract_version` strings (`"agent2-to-agent3-v1"`,
   `"agent2-agent3-to-agent4-v1"`, `"agent2-agent4-to-agent5-v1"`), requiring the integration
   harness to re-stamp this field as a workaround.

This document records the evidence trail behind `app.agent2.pipeline.run_agent2_pipeline` (which
closes debt 1) and `app.agent2.pipeline.build_canonical_downstream_handoff` /
`AGENT2_DOWNSTREAM_CONTRACT_VERSION` (which closes debt 2).

## The canonical stage sequence, and where each piece of evidence for it comes from

```
translate_agent1_view_to_agent2(view)
        |
assemble_full_network(handoff)                                  -> network
        |
resolve_kinetic_measurement_reaction_context(network)            -> resolutions
apply_resolved_reaction_context(network, resolutions)             -> network (rebound)
        |
characterize_full_network(network)                                -> characterization
assign_kinetic_laws(characterization, network)                     -> kinetic_laws
        |
resolve_enzyme_concentrations(network)                              -> enzyme_concentrations
build_enzyme_state_dynamics(network, enzyme_concentrations)          -> dynamics
        |
   -- Pass 1 (boundaries/modules; pre-augmentation network/assignments) --
declare_parameters(kinetic_laws, network, enzyme_concentrations)      -> parameters_for_boundaries
assess_boundaries(network, characterization, kinetic_laws,
                   parameters_for_boundaries)                          -> boundaries
decompose_network(network, kinetic_laws,
                   parameters_for_boundaries, boundaries)               -> modules
        |
   -- Pass 2 (final parameters/model; augmented network/merged assignments) --
merge_transition_assignments(kinetic_laws,
                              dynamics.transition_assignments)           -> merged_kinetic_laws
declare_parameters(merged_kinetic_laws, dynamics.network,
                    enzyme_concentrations,
                    enzyme_state_concentrations=dynamics.state_concentrations)
                                                                           -> final_parameters
assemble_model_specification(dynamics.network, merged_kinetic_laws,
                              final_parameters, boundaries, modules,
                              enzyme_concentrations=enzyme_concentrations,
                              enzyme_state_pools=dynamics.pools,
                              enzyme_state_concentrations=dynamics.state_concentrations)
                                                                           -> model
        |
generate_antimony(model)                                                  -> package
        |
build_canonical_downstream_handoff(model, package)                        -> downstream dict
```

**Evidence for the base seven-stage chain** (`assemble_full_network` through
`assemble_model_specification`): `tests/agent2/test_model_specification.py`'s own
`_assemble_full` helper, used by every test in that file, already chains exactly these seven
calls in exactly this order.

**Evidence for reaction-context resolution's placement**: `tests/agent2/test_reaction_context.py`
calls `resolve_kinetic_measurement_reaction_context`/`apply_resolved_reaction_context`
immediately after `assemble_full_network`, and threads the *resolved* network — never the
original — through every subsequent stage (`characterize_full_network`, `assign_kinetic_laws`,
`declare_parameters`, `assess_boundaries`, `decompose_network`, `assemble_model_specification`).
Both functions are unconditionally safe to call (confirmed by reading their own implementations):
`resolve_kinetic_measurement_reaction_context` only considers measurements with
`reaction_id is None` and returns an empty tuple when there is nothing to resolve;
`apply_resolved_reaction_context` is a no-op pass-through for any non-`UNIQUE_MATCH` resolution.

**Evidence for the two-pass enzyme-state-dynamics wiring**:
`tests/agent2/test_enzyme_state_dynamics.py::test_phosphorylation_regression_end_to_end` is the
one existing test performing a complete, real, upstream-to-downstream run including this
increment, and its own comment makes the two-pass design explicit: *"Parameters computed twice,
once against the original network/assignments (for boundaries/modules -- unaffected by this
increment), once against the merged/augmented pair (for the final model) -- mirrors this
package's own documented two-pass wiring."* `app.agent2.enzyme_state_dynamics.builder
.EnzymeStateDynamicsResult`'s own docstring independently confirms the same contract: *"pass
this [``dynamics.network``], never the original, to `declare_parameters`/
`assemble_model_specification`/`generate_antimony`."* When a network has no enzyme states at
all (the real `sce00061` model's own case), `dynamics.pools`/`.transition_assignments` are empty
and `dynamics.network` is structurally equivalent to the input network — the two-pass pattern
degrades gracefully to an extra, harmless `declare_parameters` call, never a behavior change.

## What is deliberately NOT a separate orchestration-level call

The task's own framing additionally named "catalytic contexts," "evidence consolidation/
prioritization," "substrate-specific parameterization," "macro→micro reconstruction," and
"heuristic initialization" as pipeline stages. Investigation (reading
`app.agent2.kinetics.evidence_consolidation`, `app.agent2.parameters.reconstruction`, and
`app.agent2.parameters.heuristic_defaults`, and their own test files) confirmed these are not
separate top-level functions a caller invokes — they are internal algorithmic steps **inside**
`assign_kinetic_laws`/`declare_parameters` themselves, triggered automatically by the nature of
the input evidence (e.g. multiple measurements for the same concept get consolidated; a missing
value falls back to a heuristic default). `run_agent2_pipeline` calls `assign_kinetic_laws`/
`declare_parameters` exactly as every other stage's own test suite already does, and trusts
their own already-tested internal behavior — never re-implementing or second-guessing it.

## The canonical downstream contract (`agent2-downstream-v1`)

`build_canonical_downstream_handoff(model, package)` serializes `ModelSpecification` +
`Agent2OutputPackage` into the one plain dict shape Agents 3, 4, and 5 already parse (confirmed
field-for-field identical to what each of those three repositories' own handoff parsers already
expect, so no change was required to any of their own parsing logic — only to the single
`contract_version` string each one checks for):

```
contract_version                 "agent2-downstream-v1" (AGENT2_DOWNSTREAM_CONTRACT_VERSION)
model_id, network_id             from ModelSpecification / FullNetwork
antimony_text, antimony_generator_version, readiness,
unresolved_reaction_ids, unresolved_kinetic_law_ids
                                  from FullAntimonyArtifact
compartments[], species[], reactions[]
                                  from FullNetwork (species[].initialization_source included)
kinetic_laws[]                   from ModelSpecification.kinetic_laws
parameters[]                     from ModelSpecification.parameters (lower_bound/upper_bound/
                                  fixed/provenance_refs included)
model_assumptions[]              from ModelSpecification.model_assumptions
```

This single name replaces the three previously-divergent per-consumer names. See each
downstream repository's own migration notes (`docs/02_*_contract.md` in
`agent3-simulation-diagnostics`, `agent4-calibration-estimator`,
`agent5-validation-experimental-design`) for the consumer side of this change.
