# Calibration Evidence Integration into Weight-Space Exploration

## 1. Goal

The Recursive Module Evaluation Orchestration increment (`docs/
31_recursive_module_evaluation_orchestration.md`) let a single `evaluate_modularization` call
score the `CALIBRATION_INDEPENDENCE` criterion from externally-obtained
`ModuleCalibrationEvaluation` evidence, but left that evidence unthreaded through the Weight-
Space Exploration and Stable Boundary Discovery framework (`docs/
30_weight_space_exploration_and_stable_boundary_discovery.md`). This increment closes that gap:
candidate modularization → module calibration evaluations → `CALIBRATION_INDEPENDENCE` score →
`evaluate_modularization` → weight-space exploration → stable-boundary discovery, end to end.

**Agent 2 still never recomputes or triggers calibration** -- every `ModuleCalibrationEvaluation`
consumed here was already obtained by routing a `ModuleCalibrationRequest` through the Harness/
Agent 3/Agent 4 (`app.agent2.module_calibration`) before calling any function in this increment.

## 2. Evidence mapping (deterministic, per modularization)

`calibration_evidence` is always keyed by `modularization_id` -> `{module_id:
ModuleCalibrationEvaluation}` wherever more than one modularization can be in scope
(`compare_modularizations`, `explore_weight_space`); `evaluate_modularization`/
`evaluate_modularization_under_weights` (single modularization) keep the simpler
`{module_id: ModuleCalibrationEvaluation}` shape from the previous increment unchanged. Each
modularization's own evidence is looked up by its own id and passed to its own
`evaluate_modularization` call alone -- never shared across different modularizations' own,
structurally distinct modules.

**Corrected aggregation policy** (`app.agent2.module_evaluation.calibration_adapter
.score_calibration_independence`): the function now takes the modularization's own *complete*
`module_ids` tuple as a required argument, not just whatever keys happened to be present in the
caller's evidence mapping. A module named in `module_ids` with **no entry at all** in the
mapping is now correctly treated identically to one with an explicitly unavailable status
(`INSUFFICIENT_DATA`/`BOUNDARY_INADEQUATE`) -- previously, a mapping that simply omitted a
module's own key was silently treated as "not asked about," which could make a partial-evidence
modularization look fully evaluated when it was not. `MODULE_CALIBRATION_POLICY_VERSION` bumped
`"module-calibration-v1"` -> `"module-calibration-v2"` for this real policy correction.

## 3. Agent 4 field exposure (sibling repository, no new algorithm)

Confirmed by direct inspection before this increment: Agent 4 already computed a local
covariance estimate (finite-difference residual Jacobian → Fisher information → pseudo-inverse)
internally, solely to threshold-check its own `HIGH_CORRELATION` identifiability finding, then
discarded it. `agent4-calibration-estimator` now exposes that identical computation as public
data (`docs/05_identifiability_diagnostics.md` §6, sibling repository):

- `ParameterEstimate.standard_error` (new field) -- `None` only when the estimate itself could
  not be computed, never fabricated.
- `CalibrationResult.parameter_correlations` (new field) -- every fitted-target pair's own local
  correlation (not only the ones above the `HIGH_CORRELATION` threshold).
- Fit quality (`objective_before`/`objective_after`, `residuals`) and convergence/status
  information (`CalibrationStatus`, `optimizer_message`, `best_start_index`,
  `all_start_objectives`) were already exposed before this increment -- unchanged.

`AGENT4_CONTRACT_VERSION` bumped `"0.1"` -> `"0.2"` (purely additive). No new calibration
algorithm: the exact same math, merely no longer thrown away.

## 4. Failure/status semantics: infrastructure vs. genuine evidence

A real design flaw in the previous increment's own Harness orchestration is fixed here: when
Agent 3's or Agent 4's own subprocess crashed or timed out (never that agent's own disclosed
calibration/simulation outcome -- both pipelines are documented to never raise for a genuine
outcome), the Harness previously mapped that straight into a disclosed
`ModuleCalibrationStatus.CALIBRATION_FAILED` result. That conflated "the harness/agent broke"
with "this module calibrates poorly" -- a real negative-evidence claim the Harness had no basis
to make. `app.harness.module_calibration.run_module_calibration_workflow` now raises
`ModuleCalibrationWorkflowError` for exactly this case (alongside the pre-existing
`INVALID_REQUEST` handling) -- never persisted as a cached result, so a retry after the
underlying infrastructure problem is fixed is free to actually re-run.
`MODULE_CALIBRATION_WORKFLOW_POLICY_VERSION` bumped accordingly (sibling repository's own
`docs/10_calibration_evidence_integration_into_weight_space_exploration.md`).

`CALIBRATION_FAILED`/`UNIDENTIFIABLE` themselves remain exactly what they always were: real,
available *negative* evidence (scored `0` by `score_calibration_independence`), never confused
with `INSUFFICIENT_DATA`/`BOUNDARY_INADEQUATE` (unavailable evidence, never a score at all).

## 5. Weight-space behavior

`CALIBRATION_INDEPENDENCE` participates exactly like every other criterion, verified by test:

- Weight `0` disables its contribution (`evaluated_weight_fraction`/`overall_score` identical to
  omitting the criterion entirely, even though it still appears in `criterion_scores` with
  `available=True`, `weighted_contribution=None`).
- A positive weight uses available evidence, and can **change which candidate ranks higher**
  (§6 below) -- the exact mechanism `compare_modularizations`/`explore_weight_space` already use
  for every other criterion.
- Unavailable evidence reduces `evaluated_weight_fraction` honestly (the pre-existing
  weighted-sum-without-renormalization policy, unchanged).
- Every criterion score, including `CALIBRATION_INDEPENDENCE`'s own `CalibrationIndependenceDetail`
  (which module had evidence, which was missing, each one's own status), remains fully
  inspectable on every `ModularizationEvaluation` this increment produces.

`evaluate_modularization_under_weights`, `compare_modularizations`, and `explore_weight_space`
all gained the optional `calibration_evidence` parameter; `select_high_scoring_solutions`/
`compute_boundary_stability`/`compute_co_membership_stability`/`compute_modularization_recurrence`
(stability analysis) needed **no code change at all** -- confirmed by inspection, they already
operate generically on `ModularizationEvaluation.overall_score`/`.criterion_scores` without
referencing any specific criterion, so a `CALIBRATION_INDEPENDENCE`-influenced `overall_score`
flows through them exactly like any other. Omitting `calibration_evidence` anywhere reproduces
every function's exact pre-existing behavior with zero change.

## 6. Example ranking change caused by calibration evidence

Reuses `tests/agent2/test_weight_space_exploration.py`'s own `_two_candidate_model()` fixture
(chain `A→B→C→D→E`; `"topo"` = {topoA={r1,r2}, topoB={r3,r4}}, `"ec"` = {ecA={r1,r3},
ecB={r2,r4}}). Under `TOPOLOGICAL_SEPARATION` alone, `"topo"` (score 2/3) beats `"ec"` (score 0).
Supplying calibration evidence where `"ec"`'s own two modules are both `CALIBRATION_SUPPORTED`
(min score 1) and `"topo"`'s own modules include one `CALIBRATION_FAILED` (min score 0), then
weighting `CALIBRATION_INDEPENDENCE` alone, **reverses that ranking**: `"ec"` (score 1) now beats
`"topo"` (score 0) -- a real ranking change driven entirely by calibration evidence, never by
re-deriving anything from the network itself (`test_calibration_evidence_changes_candidate_ranking`).

## 7. Provenance/replay handling

`ModuleCalibrationEvaluation.evaluation_id`/`.request_id`/`.correlation_id`/`.run_id`/
`.provenance_refs` (unchanged from the previous increment) already trace one piece of
calibration evidence back to the exact Agent 4 run that produced it
(`agent4-report::<report_id>`, `agent3-report::<report_id>`) -- this increment adds no new
identifier of its own, since calibration evidence is consumed as an opaque, already-fully-
provenanced object at every layer (`calibration_adapter`, `evaluate_modularization`,
`explore_weight_space`). `app.harness.module_calibration.run_module_calibration_workflow`'s own
`run_id`-keyed persistence/replay (unchanged) is the mechanism that makes a given evaluation's
own evidence reproducibly re-fetchable without re-running Agent 3/Agent 4.

## 8. Tests / lint

`tests/agent2/test_weight_space_exploration.py` (+10 tests):
ranking-change-by-calibration-evidence, weight-zero-reproduces-prior-results, multi-weight-
vector exploration with calibration, unavailable-evidence-handled-honestly (including the
no-entry-at-all case), `CALIBRATION_FAILED`/`UNIDENTIFIABLE` as negative evidence, stable-
boundary analysis over calibration-weighted solutions, no-regression-when-omitted.
`tests/agent2/test_module_calibration.py` (+1 test, signature update to the rest): the
module-ids-aware weakest-link fix. Full Agent 2 suite 1151 passed; lint clean.

Cross-repo: `agent4-calibration-estimator` +4 tests (standard-error/correlation exposure,
precomputed-estimate equivalence), 64 passed, lint clean.
`agent-integration-harness` +2 tests (infrastructure-failure-raises,
standard-error/correlation passthrough with pair re-sorting), 83 passed (including the real
live-DB `sce00061` workflow and the real Agent3→Agent4 subprocess round trip), lint clean.
Workbench suite unaffected (88 passed, no code touched).

## 9. Remaining gaps before Candidate Modularization Search

- **Parameters requiring external/context information**: still no Agent 4 output field for
  this signal (unchanged gap from the previous increment).
- **Cross-replicate parameter stability**: `ParameterStabilitySummary` remains fully designed
  but unorchestrated -- no change in this increment.
- **Weight-space exploration still does not decide which modules need evidence**: a caller
  must still supply a complete `calibration_evidence` mapping (or accept the honest
  `unavailable` outcome for an incomplete one); no automatic recursion/search was added, by
  design (task instructions' own explicit non-goal).
- **Stability/co-membership measures do not themselves distinguish *why* a boundary is stable**
  (topology, EC class, or calibration evidence) -- they report frequencies over whichever
  criteria happened to be weighted, exactly as before; attributing stability to one specific
  criterion's own influence remains a future increment's own job, if ever needed.
