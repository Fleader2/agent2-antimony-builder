# Functional Modularity Criteria from Agents 3 and 4

## 1. Goal

Extend module evaluation beyond structural criteria by activating the two remaining reserved,
Agent-3-backed criteria -- `DYNAMIC_ISOLATION` and `SENSITIVITY_COHERENCE` -- from real
simulation/perturbation evidence, while retaining the existing `CALIBRATION_INDEPENDENCE`
exactly as it already works. The canonical model and modularization representation are
unchanged throughout.

## 2. Request/result contracts

New `app.agent2.module_functional_evaluation` package, mirroring `app.agent2.module_calibration`
structurally (request builder / types / serialization / errors) but for Agent 3 rather than
Agent 4:

- `ModuleFunctionalEvaluationRequest` carries the **whole**, unfiltered canonical
  Agent2->Agent3 handoff (`build_canonical_downstream_handoff`, unchanged) -- deliberately
  **not** the module's own filtered standalone artifact. Dynamic isolation and sensitivity
  coherence are properties of how a module behaves *relative to its surrounding context*,
  which only exists in a whole-network simulation; `CALIBRATION_INDEPENDENCE` is different --
  it legitimately evaluates one module fully isolated, which is why that criterion's own
  request (`ModuleCalibrationRequest`) correctly *does* use the filtered standalone artifact.
- A deterministic battery of `PerturbationTargetSpec`s, each tagged `is_internal` by Agent 2's
  own module-membership knowledge (never resolved by Agent 3, which stays module-agnostic) --
  the first `MIN_INTERNAL_TARGETS`/`MIN_EXTERNAL_TARGETS`-or-more parameters (sorted by id)
  whose own reaction belongs to the candidate module, and the first several whose reaction does
  not.
- `ModuleFunctionalEvaluationResult` carries one `PerturbationEffectRecord` per requested
  target: Agent 3's own real `simulation_status`/`remained_numerically_stable` plus a
  **per-species** relative-change profile -- never collapsed to one scalar.

## 3. Agent 3 metrics reused/exposed

No new simulation algorithm. `app.agent3.pipeline.run_agent3_pipeline` already accepted an
explicit `perturbation_specs` override; the Harness's new, focused runner
(`run_agent3_functional_evaluation.py`) calls it unchanged. The *only* real Agent 3-side change
is one new, additive field, `PerturbationResult.relative_change_by_species` -- the exact
per-species values `max_relative_change_in_final_state` was already computing internally
(`app.agent3.perturbation.run_perturbation`'s own `diffs` dict) and discarding down to one
`max()`. Confirmed by test that the new field's own `max()` equals the pre-existing scalar
exactly. `AGENT3_CONTRACT_VERSION` bumped `"0.1"` -> `"0.2"`.

## 4. Dynamic-isolation formula

For one module, given its own usable internal-target and external-target perturbation effects:

- `internal_to_internal` = mean relative change, over internal species, from internal-target
  perturbations ("effect of internal perturbations on internal outputs").
- `external_to_internal` = mean relative change, over external species, from internal-target
  perturbations ("spillover effects outside the module").
- `internal_to_external` = mean relative change, over internal species, from external-target
  perturbations ("dependence of module outputs on external variables").
- `boundary_capture_fraction` = (mean response of declared boundary species to external
  perturbations) / (that same quantity plus the mean response of non-boundary internal
  species) -- "whether declared boundary inputs/outputs capture most cross-module influence."
  Only computed when the module has at least one declared `ModulePort`; omitted (never
  fabricated) otherwise.

Two ratios are then formed, each normalized against the module's own internal responsiveness
(so the measure is relative, not an absolute magnitude that would otherwise depend on how hard
each target happens to be perturbed): `spillover_ratio = external_to_internal /
internal_to_internal`, `external_dependence_ratio = internal_to_external / internal_to_internal`
(a zero denominator with a zero numerator is trivially ratio `0`; a zero denominator with a
nonzero numerator is reported as a large, finite sentinel, never an unhandled division). The
final `[0, 1]` score is the mean of `1 / (1 + spillover_ratio)`, `1 / (1 +
external_dependence_ratio)`, and `boundary_capture_fraction` (when available).

Validated directly (test, and an ad hoc check during development): a synthetic "isolated"
module (internal perturbations barely reach external species, external perturbations barely
reach internal species, boundary species absorb what little does cross) scores **~0.97**; a
synthetic "coupled" module (internal perturbations spill heavily, external perturbations
heavily move non-boundary internal species) scores **~0.40** -- a clear, correctly-directed
separation.

## 5. Sensitivity-coherence formula

Deliberately a *different* question from dynamic isolation's magnitude question: does the
module's own internal-target perturbations' *shape* of response (which species move, in what
relative proportion) look similar to each other (`within_module_coherence` -- mean pairwise
cosine similarity among internal-target profiles, projected onto the module's own internal
species), and does that internal shape look genuinely *different* from an external target's own
shape (`across_boundary_coherence` -- mean cosine similarity between every internal/external
profile pair, projected onto every species either perturbation battery actually measured).
`score = within_module_coherence * (1 - across_boundary_coherence)` -- naturally bounded in
`[0, 1]` (every component is a non-negative relative-change magnitude, so cosine similarity
itself is always in `[0, 1]`, never negative), and rewards a module only when it is *both*
internally coherent *and* distinct from its neighbors; either condition failing drags the score
down. Needs at least two usable internal-target perturbations (a "similarity between profiles"
requires at least two profiles) and at least one external one; unavailable otherwise.

Validated directly: the identical "isolated" fixture above scores **~0.95** here; the "coupled"
fixture scores **~0.13** -- confirming the two criteria, while derived from identical evidence,
measure genuinely different things and both correctly separate the two synthetic cases.

## 6. Failure/unavailable-evidence semantics

- `FunctionalEvaluationStatus.UNSUPPORTED_ANALYSIS` -- the whole network has no eligible
  executable artifact at all; decided locally, no Harness round trip.
- `FunctionalEvaluationStatus.INSUFFICIENT_TARGETS` -- fewer than `MIN_INTERNAL_TARGETS`/
  `MIN_EXTERNAL_TARGETS` perturbation targets exist for this module; decided locally.
- `FunctionalEvaluationStatus.EVALUATED` -- real, available evidence, whether it discloses
  strong or genuinely poor isolation/coherence (a low score is data, never hidden).
- An Agent 3 subprocess crash/timeout raises `ModuleFunctionalEvaluationWorkflowError`
  (`app.harness.module_functional_evaluation`) -- never cached, never mapped into any of the
  three statuses above. An individual perturbation that itself failed/went unstable is
  disclosed on its own `PerturbationEffectRecord` (`simulation_status`/
  `remained_numerically_stable`) and simply excluded from the aggregate computation, never
  silently treated as a zero effect.
- `score_dynamic_isolation`/`score_sensitivity_coherence` (`functional_adapter.py`) use the
  identical weakest-link-across-modules gate as `score_calibration_independence`: any module of
  a modularization lacking usable evidence makes the whole criterion `available=False` for that
  modularization, never a fabricated partial score.

## 7. Weight-space/search integration

`functional_evaluation_evidence` threads through `evaluate_modularization`,
`evaluate_modularization_under_weights`, `compare_modularizations`, `explore_weight_space`,
`search_candidate_modularizations`, and `run_candidate_search_round` -- the identical
content-addressed-lookup convention `calibration_evidence` already established (keyed by a
module's own content key, so evidence recurs automatically across generations/candidates
sharing identical module content). Weight `0` disables both criteria exactly like every other
criterion; omitting `functional_evaluation_evidence` entirely reproduces every pre-existing call
site's behavior with no change whatsoever (confirmed by test). One real Agent 3 round trip's own
`ModuleFunctionalEvaluationResult` serves *both* `DYNAMIC_ISOLATION` and `SENSITIVITY_COHERENCE`
-- never two separate requests for the identical evidence.

The recursive Agent-4-assisted search orchestration (`app.agent2.candidate_orchestration
.run_candidate_search_round`) accepts and threads `functional_evaluation_evidence` straight
through unchanged. It does **not** yet gain an automatic functional-evaluation selection/caching
loop analogous to `CalibrationSelectionPolicy` -- a disclosed scope limit (§10), not an
oversight: a caller already holding functional evidence gets it scored correctly everywhere,
but this package does not yet decide on its own which candidates' modules are worth a new Agent
3 round trip.

## 8. Example candidate-ranking change

`test_functional_criteria_change_candidate_ranking` (`tests/agent2/test_module_functional
_evaluation.py`): the identical modularization, scored under a weights vector naming only
`DYNAMIC_ISOLATION`/`SENSITIVITY_COHERENCE`, produces a materially higher `overall_score` when
fed the "isolated" functional evidence than the "coupled" evidence for the same two modules --
confirming real evidence, not just structure, now drives ranking once a caller supplies it.

## 9. Recursive-readiness behavior

`build_module_functional_evaluation_request`/`select_functional_evaluation_targets` read only
`model.full_network`/`.module_memberships`/`.module_ports`/`.parameters` -- no origin-specific
branch, and no assumption that `model` is "the whole canonical model." Confirmed by test against
a hand-built submodel `ModelSpecification` (mirroring the established recursive-module-
evaluation fixture convention elsewhere in this codebase): the identical function call works
unchanged. Never triggered automatically.

## 10. Full cross-repo tests/lint and remaining gaps

**Tests**: Agent 2 +23 (22 new in `tests/agent2/test_module_functional_evaluation.py` --
request construction, serialization round trips, both scoring formulas directly, availability
gating, `evaluate_modularization` integration, GENERATED/IMPORTED symmetry, recursive-submodel
compatibility, no-mutation; +1 new threading test in `tests/agent2/test_modularization_search
.py`). Agent 3 +1 (`test_relative_change_by_species_is_consistent_with_the_max_scalar`).
Harness +6 (`tests/harness/test_module_functional_evaluation.py`: one real, full round trip
against a genuine three-species chain confirming genuine per-species propagation and a genuine
near-zero cross-reaction effect, persistence replay, infrastructure-failure-never-cached, plus
three unit tests for the mapping policy). Full Agent 2 suite: 1277 passed (1254 pre-existing +
23 new). Full Agent 3 suite: 37 passed (36 + 1). Full Harness suite: 101 passed (95 + 6). Lint
clean on every file this increment touched in all three repos (confirmed by direct diff against
each lint run's own flagged-file list; every remaining finding is pre-existing and in a file
this increment never touched).

**A real production bug was found and fixed in this same increment**: `ModularizationCriterion
Score.__post_init__`'s own `.detail` type gate was a closed `if`/`elif`/`else` chain that would
have rejected the two new detail types outright with a `TypeError` the moment either criterion
was ever scored with real evidence -- caught immediately by this increment's own integration
test, extended (never bypassed) to recognize `DynamicIsolationDetail`/`SensitivityCoherenceDetail`.

**Remaining gaps before hierarchical recursive modularization**:

- No automatic functional-evaluation selection/caching loop in the recursive search
  orchestration (§7) -- the evidence channel exists and is correctly scored everywhere, but
  nothing yet decides on its own to go get new Agent 3 evidence the way `CalibrationSelection
  Policy` already does for Agent 4.
- Species-initial-concentration perturbation targets are out of scope for this increment --
  only `PARAMETER` targets are selected (a disclosed, deliberate V1 scope limit, not an
  oversight).
- `DYNAMIC_ISOLATION`/`SENSITIVITY_COHERENCE` do not yet have a pluggable cross-module
  aggregation policy analogous to `CalibrationAggregationPolicy` -- both use a fixed, equal-
  weighted mean across a modularization's own modules (a disclosed, deliberate scope cut; the
  module-count-bias reasoning that motivated `CalibrationAggregationPolicy` likely applies here
  too and would be a reasonable follow-up).
- Recursing into a submodel still inherits `build_submodel`'s own pre-existing, disclosed
  network-truncation limitation (a cross-boundary edge is still counted as external even when
  the "boundary" is only the recursion's own, not a real biological one).
- No hierarchical/nested recursive modularization yet (explicitly out of scope for this
  increment, and for the prior Recursive Agent-4-Assisted Candidate Search Orchestration
  increment too) -- both this increment's own evidence channel and the existing calibration
  one would need to be threaded consistently through whatever orchestration drives that in the
  future.
