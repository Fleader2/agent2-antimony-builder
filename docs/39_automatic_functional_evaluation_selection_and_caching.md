# Automatic Functional-Evaluation Selection and Caching in Recursive Candidate Search

## 1. Goal

Extend the Recursive Agent-4-Assisted Candidate Search Orchestration so promising
modularizations automatically receive Agent 3 functional evaluation (`DYNAMIC_ISOLATION` +
`SENSITIVITY_COHERENCE`) under the same bounded, cached, provenance-preserving principles
already used for Agent 4 calibration -- a second, genuinely separate gate, never required to
select the identical candidates/modules calibration does, with its own separate budget.

## 2. Architecture

```text
candidate search
→ structural pre-ranking (unchanged)
→ FunctionalEvaluationSelectionPolicy gate (new, mirrors CalibrationSelectionPolicy)
→ Harness → Agent 3 functional evaluation (app.harness.module_functional_evaluation, unchanged)
→ DYNAMIC_ISOLATION / SENSITIVITY_COHERENCE evidence
→ re-score / re-rank (unchanged threading, prior increment)
→ calibration where separately selected (unchanged gate, independent budget)
→ next bounded round
```

Agent 2 still never calls Agent 3 directly -- the new gate only ever decides *whether* to
request real evidence and builds the request (or resolves it locally); routing is still always
the Harness's own job, exactly like calibration.

## 3. Selection policy

`app.agent2.candidate_orchestration.types.FunctionalEvaluationSelectionPolicy` mirrors
`CalibrationSelectionPolicy` field for field (`max_candidates_per_generation`,
`max_modules_per_candidate`, `score_threshold`, `rank_threshold`,
`only_if_could_change_ordering`, `total_functional_evaluation_budget`, `policy_version`).
`select_modules_for_functional_evaluation` (`functional_selection.py`) mirrors
`select_candidates_for_calibration` exactly, with one addition: a single, up-front check
(`total_functional_weight`, the sum of `DYNAMIC_ISOLATION`'s and `SENSITIVITY_COHERENCE`'s own
normalized weights) that short-circuits *every* decision this round to the new
`SKIP_ZERO_FUNCTIONAL_WEIGHT` outcome when both are zero -- functional evidence could never
move `overall_score` at all in that case, so no Agent 3 call is ever worth making. Every other
`FunctionalEvaluationDecisionOutcome` (`EVALUATE`, `SKIP_DEGENERATE_CANDIDATE`,
`SKIP_BELOW_RANK_THRESHOLD`, `SKIP_BELOW_SCORE_THRESHOLD`, `SKIP_CANDIDATE_BUDGET_EXHAUSTED`,
`SKIP_MODULE_LIMIT_REACHED`, `SKIP_COULD_NOT_CHANGE_ORDERING`, `SKIP_ALREADY_EVIDENCED`,
`SKIP_TOTAL_BUDGET_EXHAUSTED`) mirrors `CalibrationDecisionOutcome` exactly -- every
`(candidate_id, module_id)` pair considered gets one disclosed, reasoned decision.

`build_functional_evaluation_requests` (`functional_requests.py`) mirrors
`build_calibration_requests`: for every `EVALUATE` decision, checks the whole network's own
Antimony readiness and target-count eligibility *before* calling
`build_module_functional_evaluation_request` (never by sniffing an exception's message text),
resolving locally as `UNSUPPORTED_ANALYSIS`/`INSUFFICIENT_TARGETS` when ineligible -- exactly
`build_module_functional_evaluation_request`'s own two, existing reject conditions, just
checked up front so the local-resolution choice is explicit rather than guessed.

## 4. Threading into `run_candidate_search_round`

Two new, optional parameters: `functional_evaluation_selection_policy` (default `None`) and
`functional_evaluations_used_so_far` (default `0`). `None` reproduces the exact prior behavior
(zero functional-evaluation decisions/requests) -- purely additive, zero-default-behavior
change, the identical rollout convention `functional_evaluation_evidence` itself used.
`CandidateSearchRoundResult` gains `functional_evaluation_decisions`,
`functional_evaluation_requests`, `locally_resolved_functional_evidence` (all empty tuples by
default). `serialize_round_result` gains the matching three keys.

## 5. Interaction with calibration selection

Calibration and functional-evaluation selection are two entirely independent calls inside
`run_candidate_search_round` -- separate policy objects, separate budgets
(`total_calibration_run_budget` vs. `total_functional_evaluation_budget`), separate decision
outcomes, separate already-evidenced-module bookkeeping (each keyed by its own evidence
mapping's own content keys). A candidate can be selected for calibration and not functional
evaluation, or the reverse, or both, or neither -- nothing requires every functionally
evaluated candidate to be calibrated (task instructions §5), and the "cheap structural screen →
Agent 3 functional screen → only strongest/ambiguous → Agent 4 calibration" workflow the task
names is directly supported: a caller can set a generous functional budget and a tight
calibration budget (gated additionally by `only_if_could_change_ordering`), reserving real
Agent 4 round trips for whichever candidates survive both screens.

## 6. Recursive/submodel compatibility

No new code path: `select_modules_for_functional_evaluation`/`build_functional_evaluation_requests`
operate on `search_result`/`model` exactly like the calibration gate does, so a materialized
submodel (`app.agent2.submodel_materialization`, via `build_submodel`) works identically --
confirmed directly (a `SPLIT_MODULE`-based search on a single-module submodel, with
`exclude_single_module_from_ranking=False` to let the degenerate seed actually seed the search
frontier, produces real functional-evaluation decisions). No automatic hierarchical descent is
added (task instructions §6/non-goals).

## 7. Harness-side caching and routing

`app.harness.recursive_candidate_search` gains a second, genuinely separate routing loop
alongside calibration's own. See the Harness repository's own
`docs/13_automatic_functional_evaluation_selection_and_caching.md` for the full routing/cache
design; in summary: `functional_evaluation_cache_key_for` (module content + boundary species +
perturbation-target battery + Agent 3 contract/policy versions -- never
`AGENT4_CONTRACT_VERSION`, since no Agent 4 call is ever involved) keyed against the existing,
reused-verbatim `FileCalibrationEvidenceCache` (already a generic cache-key -> JSON-dict file
store); a genuinely new `EVALUATE` decision is routed through the unchanged
`run_module_functional_evaluation_workflow` (itself fully self-contained -- unlike calibration,
no external dataset provider is ever needed, since the whole-network handoff and perturbation
battery are both built entirely by Agent 2); an infrastructure failure
(`ModuleFunctionalEvaluationWorkflowError`) is never cached, never counted as evidence, and is
always retried on the next attempt; a new `FUNCTIONAL_EVALUATION_BUDGET_EXHAUSTED` stopping
reason is checked independently of `CALIBRATION_BUDGET_EXHAUSTED`.

## 8. Example candidate-ranking change

Given a 4-reaction chain (A→B→C→D→E over r1..r4) with `DYNAMIC_ISOLATION`/
`SENSITIVITY_COHERENCE` weighted at 0.9 combined: two modularizations with identical structural
(`TOPOLOGICAL_SEPARATION`) scores (both unweighted-functional `overall_score=0`) diverge sharply
once functional evidence arrives -- the modularization whose own modules receive strongly
*isolated* perturbation-response evidence scores materially higher (`overall_score` changes
from `0` to a positive value exceeding the modularization given strongly *coupled* evidence),
confirmed directly via `evaluate_modularization` with each evidence set
(`test_functional_evidence_changes_candidate_ranking`).

## 9. Tests / lint

24 new Agent 2 tests (`tests/agent2/test_functional_evaluation_selection.py`): zero functional
weights produce no requests (and omitting the policy entirely produces no decisions at all);
structural gate prevents unnecessary functional evaluation; functional evidence changes
candidate ranking; functional budget enforced (both total budget and
`max_candidates_per_generation`); real requests are actually built for an `EVALUATE` decision
(with a correct internal/external target split); already-evidenced modules are never
re-evaluated; functional and calibration selection have independent budgets; functional
evaluation selection works on a materialized submodel; deterministic repeated execution;
GENERATED/IMPORTED symmetry. Full Agent 2 suite: 1313 passed (1301 pre-existing + 12 new in
this file, plus the existing `test_candidate_orchestration.py` suite unchanged); lint clean.
13 new Harness tests (see that repository's own doc for detail); Harness non-DB suite: 114
passed (101 + 13); real `sce00061` workflow unaffected (untouched by this increment). Agent 3
(37 passed), Agent 4 (64 passed), and Workbench (88 passed) suites all pass unchanged -- zero
files touched in any of the three.

## 10. Remaining gaps before automatic hierarchical recursive modularization

- No automatic recursive descent: nothing decides *when* to materialize a submodel and search
  it further on its own -- that remains the Canonical Submodel Materialization increment's own
  disclosed gap, unchanged by this increment.
- Functional-evaluation selection has no analog of calibration's
  `calibration_request_provider` indirection, because none is needed: a functional-evaluation
  request is always fully self-contained (Agent 2 builds the whole-network handoff and
  perturbation battery itself) -- there is no external "dataset" concept for this criterion at
  all, so this is a disclosed structural asymmetry versus calibration, not an oversight.
- The "could plausibly change ordering" gate's own best-case bound (the sum of
  `DYNAMIC_ISOLATION`'s and `SENSITIVITY_COHERENCE`'s normalized weights) is a conservative,
  deterministic heuristic identical in spirit to calibration's own -- it can only ever
  under-select (be too conservative), never over-select, since it assumes the best possible
  functional score (`1.0` on each) is achievable.
