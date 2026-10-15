# Recursive Module Evaluation Orchestration

## 1. Goal and architecture

Lets one candidate module from Agent 2's unified modularization system
(`ModelModularization`/`ModelModule`/`ModuleMembership`/`ModulePort`) be converted into a
standalone executable Antimony submodel (the existing, unchanged
`app.agent2.antimony.generate_module_artifacts` path) and sent, via the Harness, through Agent 3
(simulation/diagnostics) then Agent 4 (calibration), producing a structured, calibration-based
module-quality result that feeds the Module Boundary Evaluation Framework's own previously
reserved `CALIBRATION_INDEPENDENCE` criterion (`docs/27_module_boundary_evaluation_framework.md`).

**Agent 2 never calls Agent 4 (or Agent 3) directly anywhere in this repository.** Routing is
always the Harness's own job (`agent-integration-harness/app/harness/module_calibration.py`):

```text
Agent 2 candidate module
  (app.agent2.module_calibration.build_module_calibration_request)
        |
        v
ModuleCalibrationRequest  -- carries module_handoff (build_module_downstream_handoff's own
        |                     already-filtered Agent2->Agent3 handoff dict for this module)
        v
Harness (app.harness.module_calibration.run_module_calibration_workflow)
        |
        +--> Agent 3 subprocess (run_agent3.py, unchanged)        -- simulation/diagnostics
        |
        +--> Agent 4 subprocess (run_agent4.py, unchanged)        -- calibration
        |
        v
ModuleCalibrationEvaluation dict
        |
        v
app.agent2.module_calibration.parse_module_calibration_evaluation
        |
        v
app.agent2.module_evaluation.calibration_adapter.score_calibration_independence
        |
        v
evaluate_modularization(..., calibration_evidence={module_id: evaluation, ...})
```

Two packages, one on each side of the Harness boundary:

- **`app.agent2.module_calibration`** (this repository): `types.py` (`ModuleCalibrationStatus`,
  `ModuleCalibrationRequest`, `ModuleCalibrationEvaluation`, and the supporting evidence types
  below), `request_builder.py` (`build_module_calibration_request`,
  `boundary_inadequate_evaluation`), `serialization.py` (plain-dict (de)serialization, the
  decoupling boundary), `errors.py`.
- **`app.harness.module_calibration`** (`agent-integration-harness`): `build_module_agent3_handoff`
  (pure passthrough of `request["module_handoff"]`), `map_calibration_result_to_module_evaluation`
  (Agent 4 `CalibrationStatus` -> `ModuleCalibrationStatus` + field derivation),
  `run_module_calibration_workflow` (the actual subprocess orchestration + persistence/replay).

Neither package imports the other's, or Agent 3's, or Agent 4's own Python package -- only the
one documented plain-dict shape is shared at each boundary, exactly like every other cross-repo
boundary in this five-agent pipeline already is.

## 2. Request contract

`ModuleCalibrationRequest` identifies, per the task's own requirement list: `parent_model_id`
(the parent canonical model), `modularization_id`/`module_id`, `module_handoff` (the standalone
module artifact -- **not** a bare Antimony string, but the identical, already-filtered
Agent2->Agent3 handoff dict `app.agent2.pipeline.build_module_downstream_handoff` produces for
this one module: its own `antimony_text`, filtered `species`/`reactions`/`kinetic_laws`/
`parameters`, and `antimony_symbol_map` -- so a real calibration target can actually be resolved
against it by Agent 4's own eligibility/bounds logic, not just compiled and simulated),
`boundary_ports` (boundary inputs/outputs, from the module's own `ModulePort` rows),
`calibration_dataset_references` (opaque pointers -- Agent 2 never owns dataset content), and
`correlation_id`/`run_id`.

`build_module_calibration_request(model, modularization_id, module_id, *, correlation_id,
run_id, ...)` is the sole producer: it calls `generate_module_artifacts` (unchanged) to obtain
the module's own `ModuleAntimonyArtifact`, raises `ModuleCalibrationReferenceError` when that
module has no eligible standalone artifact (`standalone_antimony is None`), and otherwise calls
`build_module_downstream_handoff` (new, `app.agent2.pipeline` -- §6) to assemble `module_handoff`.
Works identically for a `GENERATED` or `IMPORTED` `model`, and identically when `model` is itself
a previously-derived module/submodel re-assembled as its own `ModelSpecification` (§5).

## 3. Result contract

`ModuleCalibrationEvaluation` carries, where available: `fit_quality` (`FitQualitySummary` --
objective before/after, residual sums), `identifiability_findings`
(`IdentifiabilityFindingSummary`, a direct projection of Agent 4's own findings),
`parameter_uncertainty` (`ParameterUncertaintyEstimate` -- `fitted_value` always populated,
`standard_error` always `None`: Agent 4 computes a covariance matrix internally for its own
`HIGH_CORRELATION` finding but does not expose per-parameter standard errors as public data
today -- disclosed as unavailable, never fabricated, see §5), `parameter_correlations` (always
empty today -- same reason), `boundary_sensitivity_findings` (`BoundarySensitivityFinding`, a
direct projection of Agent 4's `BOUND_HIT`/`LOW_SENSITIVITY` identifiability-finding categories
-- the closest existing Agent 4 signal to "sensitivity to boundary conditions"),
`parameters_requiring_external_context` (always empty today -- no Agent 4 output field exists
for this, §5), `parameter_stability` (always empty today -- requires multiple calibration
datasets/replicate runs, not implemented in this increment, §5/§8), plus `warnings`/
`provenance_refs`.

`ModuleCalibrationStatus`: `CALIBRATION_SUPPORTED`, `CALIBRATION_FAILED`, `INSUFFICIENT_DATA`,
`UNIDENTIFIABLE`, `BOUNDARY_INADEQUATE`. **`INSUFFICIENT_DATA` and `BOUNDARY_INADEQUATE` both
mean unavailable evidence, never a bad module score** -- `ModuleCalibrationEvaluation`'s own
`__post_init__` enforces this structurally: every evidence field must be empty/`None` for
either status, never partially populated. `CALIBRATION_FAILED`/`UNIDENTIFIABLE` are the
opposite: real, available *negative* evidence (the fit was attempted and did not succeed, or
did succeed but could not pin the module's own parameters down standalone) -- these may
legitimately carry partial findings, and do count as evidence for scoring (§4).

`BOUNDARY_INADEQUATE` is unique: it is decided entirely **locally**, before any Harness round
trip (`boundary_inadequate_evaluation`) -- a module with no eligible standalone artifact can
never be usefully routed at all, so no request is ever built or sent for it.

## 4. Module evaluation integration (the adapter)

`app.agent2.module_evaluation.calibration_adapter.score_calibration_independence(evaluations:
Mapping[module_id, ModuleCalibrationEvaluation]) -> CriterionResult` is the "clean adapter"
(task instructions §4) converting externally-obtained calibration evidence into the
`CALIBRATION_INDEPENDENCE` criterion:

- **Weakest-link aggregation**: `available=True` only when *every* supplied module's own
  evidence is itself available; one module's `INSUFFICIENT_DATA`/`BOUNDARY_INADEQUATE` makes the
  whole aggregate unavailable, never a partial average silently dropping an unevidenced module.
- When available, `raw_score` is the **minimum** per-module contribution -- a modularization's
  own calibration independence is only as trustworthy as its least-evidenced module.
- A module's own contribution: `CALIBRATION_FAILED`/`UNIDENTIFIABLE` score `0` (real, available
  negative evidence); `CALIBRATION_SUPPORTED` starts at `1` and deducts a disclosed,
  deterministic penalty per identifiability-finding severity (`CRITICAL` -0.5, `ERROR` -0.3,
  `WARNING` -0.1, floored at `0`) -- pure arithmetic over findings Agent 4 already reported,
  never a new calibration algorithm (task instructions §6).
- `CalibrationIndependenceDetail` (the one other disclosed exception to
  `ModularizationCriterionScore.detail`'s otherwise generic, criterion-agnostic shape, alongside
  `TopologySeparationDetail`) names exactly which modules had evidence, which did not, and each
  evidence-bearing module's own status -- never silently collapsed into one number.

`evaluate_modularization` gained one new, optional `calibration_evidence` parameter
(`Mapping[module_id, ModuleCalibrationEvaluation] | None = None`). Only when supplied is
`CALIBRATION_INDEPENDENCE` computed and added to `criterion_scores` at all -- omitting it (the
default) reproduces this function's exact pre-existing behavior with zero change, and that
previously-reserved criterion simply does not appear, exactly as before this increment. This is
deliberately **not** wired into the synchronous per-criterion dispatch loop every other
criterion shares (`IMPLEMENTED_CRITERIA`) -- calibration evidence is expensive, external, and
obtained out of band (a Harness round trip), never computed inline from `FullNetwork`/
`ModuleMembership` alone the way every other criterion already is.

## 5. Agent 3/Agent 4 reuse (no code changes to either)

Confirmed by direct inspection before implementing: **zero code changes to Agent 3 or Agent
4.** Agent 3's own `parse_agent2_handoff` already treats every field beyond `antimony_text`/
`model_id`/`network_id`/`antimony_generator_version`/`readiness`/`contract_version` as optional
(defaulting to empty tuples) -- a module's own `module_handoff` is already a valid Agent2->Agent3
handoff by construction, simulated exactly like any whole model. Agent 4 already has essentially
everything needed for the "did the fit work and is it trustworthy" half of a calibration-based
module-quality result: a closed `CalibrationStatus` enum, residual-based fit-quality metrics, and
local practical-identifiability findings (`BOUND_HIT`/`LOW_SENSITIVITY`/`HIGH_CORRELATION`/
`DEGENERATE_OBJECTIVE`/`INSUFFICIENT_OBSERVATIONS`) with severities.

What Agent 4 genuinely does not expose as public data today (confirmed, not guessed): per-
parameter uncertainty/standard error (the covariance matrix is computed internally only to
threshold-check `HIGH_CORRELATION`, never surfaced), a structured correlation matrix (only a
threshold-triggered finding), an explicit "needs external context" flag, and any cross-run/
cross-context parameter-stability mechanism (`run_agent4_pipeline` is single-run and stateless
by design). None of these gaps are closed by adding new calibration algorithms inside Agent 4
(explicitly out of scope, task instructions §6) -- they are disclosed as genuinely unavailable
(`None`/empty, never fabricated) in `ModuleCalibrationEvaluation`, and noted as remaining gaps
(§8) for a future increment that would need to *expose* existing Agent 4 internals, or add a
*new*, explicitly-scoped Harness-side multi-run comparison for stability specifically.

## 6. `build_module_downstream_handoff` (`app.agent2.pipeline`)

Mirrors `build_canonical_downstream_handoff` (the existing whole-model Agent2->Agent3 handoff
builder) exactly, reusing its own private per-entity dict helpers unchanged, but filtered to one
module's own `ModuleMembership` rows: `species`/`reactions`/`kinetic_laws`/`parameters` restricted
to the module's own component ids (a filtered kinetic law's own `parameter_ids` are additionally
unioned in, even when a parameter carries no explicit `ModuleMembership` row of its own);
`compartments` restricted to those the filtered species actually reference; `model_assumptions`
restricted to those whose own `related_entity_ids` names at least one included id.
`antimony_symbol_map` is passed through **unfiltered** (the whole model's own canonical-id ->
Antimony-symbol mapping is a harmless superset; a downstream consumer only ever looks up ids it
actually needs). Raises `ValueError` if called for a module whose `standalone_antimony` is
`None` -- the identical precondition `build_module_calibration_request` itself already enforces.

## 7. Recursive readiness (not implemented, but not precluded)

Nothing in `build_module_calibration_request`'s own signature, or in `app.harness
.module_calibration`'s own request/result dict shapes, assumes "the whole canonical model" --
each takes an ordinary `ModelSpecification`/plain dict. Verified directly by test
(`test_recursive_readiness_module_rebuilt_as_its_own_model_specification`): a module's own
filtered network, re-assembled as its own standalone `ModelSpecification` with a trivial
single-module modularization wrapping the entire (now standalone) network, builds a request
through the identical, unchanged code path. No automatic recursion/search is implemented (task
instructions §5 explicitly: "just ensure there is no whole-model-only assumption") -- a future
increment recursing into one selected module only needs to build that scoped sub-
`ModelSpecification` the identical way this increment's own recursive-readiness test already
does by hand.

## 8. Scope boundary honored

No candidate boundary search, no automatic module splitting/merging, no UI, no Agent 5
experimental design, no new calibration algorithms inside Agent 4 (confirmed: this increment
adds zero lines to either `agent3-simulation-diagnostics` or `agent4-calibration-estimator`).

## 9. Remaining gaps before Candidate Modularization Search

- **Parameter uncertainty/correlation matrix**: the underlying math already exists inside Agent
  4 (Fisher-information-based covariance, used only for its own `HIGH_CORRELATION` threshold
  check) but is not exposed as structured output -- a small, additive Agent 4 increment (expose,
  never recompute) would upgrade `parameter_uncertainty`/`parameter_correlations` from "always
  disclosed-unavailable" to "available where Agent 4's own fit converged."
- **Parameters requiring external/context information**: no Agent 4 output field exists for
  this signal at all today; would need new, explicitly-scoped Agent 4 design work (out of this
  increment's scope) before this package could surface it as anything but empty.
- **Stability across replicate/context conditions**: `ParameterStabilitySummary` is fully
  designed and validated (requires `compared_run_count >= 2`) but never populated by this
  increment's own orchestration -- a future increment could have the Harness call Agent 4 once
  per `CalibrationDatasetReference` a caller supplies and diff fitted values itself (pure
  arithmetic over results Agent 4 already produced, not a new calibration algorithm), but that
  multi-run orchestration is not implemented here.
- **`EVALUATED_WEIGHT_FRACTION` across multiple modules of one modularization**: this increment's
  own adapter aggregates evidence for CALIBRATION_INDEPENDENCE with a weakest-link policy across
  whichever modules a caller supplies evidence for; it does not itself decide *which* modules of
  a modularization need evaluating, or orchestrate requests for all of them -- that remains a
  caller/future-increment responsibility, consistent with "no automatic recursion/search."
- **Weight-space exploration integration**: `app.agent2.weight_space_exploration` does not yet
  thread `calibration_evidence` through `evaluate_modularization_under_weights`/
  `compare_modularizations` -- only the single-evaluation `evaluate_modularization` entry point
  gained the new parameter. A future increment wiring calibration evidence into weight-space
  exploration needs to decide how evidence (expensive, obtained once) is held fixed across many
  weight vectors, which this increment deliberately leaves unresolved rather than guessing.

## 10. Tests / lint

`tests/agent2/test_module_calibration.py` (this repository, 25 tests): request building
(eligible/ineligible modules, non-`ModelSpecification` input), `boundary_inadequate_evaluation`,
serialize/parse round trips for every status, rejection of evidence alongside an unavailable
status, `score_calibration_independence` (empty mapping, weakest-link unavailability, min
aggregation, zero-score failure/unidentifiable statuses, deterministic severity penalty),
`evaluate_modularization` integration (omitted by default, included + weight-share-honest when
supplied, never fabricated when unavailable), `build_module_downstream_handoff` (minimal valid
shape, raises for an ineligible artifact), GENERATED/IMPORTED symmetry, recursive readiness.
1143 tests pass across the full Agent 2 suite; lint clean.

`tests/harness/test_module_calibration_workflow.py` (`agent-integration-harness`, 11 tests,
including one real, full subprocess round trip through Agent 3's then Agent 4's own real
pipelines recovering a true decay-rate parameter within 5% from precomputed analytic
observations, plus a persistence/replay test proving a second call with the identical `run_id`
never re-invokes either agent): status-mapping unit tests for every
`ModuleCalibrationStatus`/Agent 4 `CalibrationStatus` pairing, `INVALID_REQUEST` raising rather
than being disclosed, boundary-sensitivity-finding category filtering, handoff passthrough.
