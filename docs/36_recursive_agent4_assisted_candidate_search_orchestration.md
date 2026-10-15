# Recursive Agent-4-Assisted Candidate Search Orchestration (Agent 2's own half)

## 1. Goal

Give the Harness everything it needs to close the modularization loop -- generate candidates,
score them structurally, decide which modules are worth a real Agent 3/Agent 4 round trip, and
build that request -- without Agent 2 ever calling Agent 3 or Agent 4 itself, and without this
package ever deciding how many rounds to run or when to stop. The full cross-repo architecture,
the recursive-loop driver, the cross-round calibration-evidence cache, and the stopping rules
all live in the Harness (`agent-integration-harness/docs/
11_recursive_agent4_assisted_candidate_search_orchestration.md`); this document covers only
`app.agent2.candidate_orchestration`, the new package the Harness drives one round at a time.

## 2. Two-stage evaluation, for free

`run_candidate_search_round` calls `search_candidate_modularizations` entirely unchanged.
Whatever `calibration_evidence` already exists (empty on round 1) is all `evaluate_
modularization` ever sees -- when `CALIBRATION_INDEPENDENCE` has no evidence yet, it is simply
unavailable, so a not-yet-calibrated candidate's own `overall_score` is already driven entirely
by the four cheap structural criteria. "Inexpensive criteria first" is therefore not special
logic in this package at all -- it is exactly what the existing scoring framework already does
the moment evidence happens to be missing.

## 3. The calibration-selection gate

`CalibrationSelectionPolicy` names every limit the task requires, each independently
configurable and independently disclosed in the resulting `CalibrationDecision.reason`:

- `max_candidates_per_generation` -- counts *candidates* that received at least one
  `CALIBRATE` decision, never a partial cutoff mid-candidate.
- `max_modules_per_candidate` -- per-candidate module cap.
- `score_threshold`/`rank_threshold` -- a candidate's own current `overall_score`/rank, by the
  identical descending-score ordering `search.py`'s own beam selection already uses.
- `only_if_could_change_ordering` -- see §4.
- `total_calibration_run_budget` -- enforced against the caller-supplied `calibration_runs_
  used_so_far` (the Harness's own running total across every round; this package holds no
  state of its own between calls).

A module already named by `calibration_evidence` (by its own content-addressed key -- see
`app.agent2.modularization_search.identity`) is never recalibrated, regardless of what that
evidence disclosed: a real negative or unavailable outcome is still a real, already-spent
attempt, never silently retried. A degenerate (one-module) candidate's own modules are *never*
selected, since by default they are already excluded from ranking entirely -- they can never
win regardless of evidence (task instructions §8); this gate still catches one explicitly even
when a caller passes `exclude_single_module_from_ranking=False` (confirmed by test).

## 4. "Could plausibly change ordering"

`could_change_ordering` is a deterministic, first-principles rule: a candidate's own best
possible score, after gaining evidence it does not yet have, is `current_score + remaining_
calibration_weight` (`CALIBRATION_INDEPENDENCE`'s own raw score is bounded in `[0, 1]`, and its
current contribution, while unavailable, is zero). Calibrating a candidate can only plausibly
change its own ranking against an immediate neighbor if that neighbor's own current score is
within `remaining_calibration_weight` of it -- otherwise even the best case could never cross
that neighbor. When the weights vector gives `CALIBRATION_INDEPENDENCE` zero weight,
`remaining_calibration_weight` is zero, so this rule *never* selects anything (confirmed by
test) -- a weights vector that does not care about calibration at all never wastes a real round
trip trying to move a score calibration cannot possibly influence.

## 5. Request construction / local resolution

`build_calibration_requests` attaches each selected candidate's own bundle to the model
(`attach_bundle`, never mutating it) and calls the existing, unchanged `build_module_
calibration_request`. When a module has no eligible standalone artifact (no genuinely
`externally_controlled` `ModulePort` -- never one `ADD_BOUNDARY` itself declares, which is
deliberately scoring-only), the existing `ModuleCalibrationReferenceError` is caught and
`boundary_inadequate_evaluation` is called directly instead -- a disclosed `BOUNDARY_INADEQUATE`
resolved with zero Harness round trips, exactly like the Recursive Module Evaluation
Orchestration increment's own established pattern.

## 6. Recursive readiness

`build_submodel` wraps one already-decomposed module as its own, standalone
`ModelSpecification` -- `full_network`/`kinetic_laws`/`parameters` carried over unchanged from
the parent model (mirroring the recursive-module-evaluation fixture convention already
established elsewhere in this codebase), only the modularization itself scoped to that one
module. `run_candidate_search_round` works on it with zero code-path change. A disclosed scope
limit: a cross-boundary edge to a reaction *outside* the submodel is still counted as a cut edge
by `TOPOLOGICAL_SEPARATION`, since the network itself is not truncated -- acceptable for
"usable," not a fully network-scoped recursive algorithm. Never triggered automatically; a
caller (the Harness) must explicitly name the module to recurse into.

## 7. The subprocess boundary's own narrow contract

`serialize_round_result` is deliberately narrow (never a full dump of every internal
`ModularizationEvaluation` field) -- exactly what the Harness's own recursive-loop driver and a
human-facing provenance report need: every retained/degenerate candidate's own structural
scores and lineage, every calibration decision with its own reason, every already-built
`ModuleCalibrationRequest`, and every locally-resolved `BOUNDARY_INADEQUATE` evaluation. Every
module reference in that dict carries its own content key as an explicit, literal `[[component
_type, component_id], ...]` list (`content_key`) -- never reconstructed by parsing a `module_id`
string, which, while itself content-addressed, is not guaranteed safely reversible if a
component id ever contained this codebase's own id-joining characters. A caller echoes that
list back unchanged as the next round's own `calibration_evidence` key. `app.agent2.module_
calibration.serialization` gained one new, additive function, `serialize_module_calibration_
evaluation` (the exact inverse of the already-existing `parse_module_calibration_evaluation`),
so a locally-resolved evidence record crosses the subprocess boundary in the identical shape a
real Harness-routed result already uses.

## 8. Scope boundary honored

No UI. No automatic recursion into every accepted module. No new Agent 3/Agent 4 algorithms --
every criterion/aggregation/request-construction function reused here is entirely unchanged.
Agent 2 still never imports, and never calls, Agent 3's or Agent 4's own code, or the Harness's.

## 9. Tests / lint

`tests/agent2/test_candidate_orchestration.py` (21 tests): the structural pre-filter preventing
unnecessary calibration, every budget/limit independently enforced, already-evidenced modules
skipped, degenerate candidates excluded both upstream (never even gated) and as a defense-in-
depth safety net under the override, `could_change_ordering`'s own zero-weight/gap/unavailable-
score cases, `BOUNDARY_INADEQUATE` resolved locally versus a real request built once a genuine
boundary exists, calibration evidence reversing candidate ranking across two round calls,
recursive submodel invocation (and its own reference-error case), GENERATED/IMPORTED symmetry,
no canonical-model mutation, deterministic repeated execution, and the serialized round
result's own JSON-shape and content-key round-trip correctness. Full Agent 2 suite: 1254 passed
(1233 pre-existing + 21 new); lint clean on every touched file.
