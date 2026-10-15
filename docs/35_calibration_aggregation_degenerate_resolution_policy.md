# Calibration-Independence Aggregation + Degenerate Resolution Policy

## 1. Goal

Remove the remaining resolution bias in calibration-based modularization scoring (the
Module-Count / Resolution Bias Audit increment found `CALIBRATION_INDEPENDENCE`'s own
weakest-link aggregation to be monotonically non-increasing in module count, a structural bias
distinct from the raw-score-formula biases of the other criteria) and prevent a trivial
one-module decomposition from automatically winning candidate-search boundary optimization.

## 2. Pluggable calibration aggregation

`app.agent2.module_evaluation.types.CalibrationAggregationMethod` is a closed, explicit
vocabulary replacing the single, previously hard-coded `min()` policy:

- `MINIMUM` — weakest-link; the original policy, retained as an explicit, strict diagnostic
  choice.
- `WEIGHTED_MEAN` — the (optionally per-module-weighted) arithmetic mean; **the new default**.
- `LOWER_QUANTILE` — a disclosed lower quantile (deterministic nearest-rank: `index =
  ceil(quantile * n) - 1`, clamped to `[0, n - 1]`, never interpolated, never randomized).
- `FRACTION_ABOVE_THRESHOLD` — the fraction of modules whose own score is `>= threshold`.

`CalibrationAggregationPolicy` carries the method plus whichever parameter it requires
(`quantile`/`threshold`/`module_weights`) and rejects a parameter supplied for the wrong method
at construction time (never a silently-ignored value). `module_weights` defaults every
unnamed module to weight `1` — an unweighted mean when left empty.

`score_calibration_independence(module_ids, evaluations, *, policy=...)`
(`app.agent2.module_evaluation.calibration_adapter`) keeps its unavailable-evidence gate
**completely unchanged and policy-independent**: any module missing evidence makes the whole
aggregate unavailable, regardless of which method was requested — `WEIGHTED_MEAN`/
`LOWER_QUANTILE`/`FRACTION_ABOVE_THRESHOLD` could each, mathematically, ignore a missing module
and still produce a number, but none of them is permitted to (confirmed by test
`test_unavailable_evidence_gate_is_identical_across_aggregation_methods`). Only the aggregation
*formula*, once every module has available evidence, varies.

**Never hides a weak module.** `CalibrationIndependenceDetail` now also discloses
`aggregation_method`, `per_module_scores` (every evidence-bearing module's own individual
score, regardless of which one aggregate number the policy produced, and regardless of whether
the aggregate itself is available at all), and `mean_score`/`min_score`/`max_score`/
`unavailable_module_count` dispersion summary statistics.

`evaluate_modularization`/`evaluate_modularization_under_weights`/`compare_modularizations`
(`module_evaluation.evaluator`), `explore_weight_space` (`weight_space_exploration.exploration`),
and `search_candidate_modularizations` (`modularization_search.search`) each gained one new,
optional `calibration_aggregation_policy: CalibrationAggregationPolicy | None = None` parameter,
threaded straight through. Omitting `calibration_evidence` entirely — every pre-existing call
site that never supplied it — is completely unaffected either way.

## 3. Why `WEIGHTED_MEAN` is the new default, and why `MINIMUM` is not

For a fixed per-module quality distribution, `E[mean(X_1..X_n)] = E[X]` — **constant** in module
count `n` (an unbiased estimator of the per-module mean, by linearity of expectation). `E[min
(X_1..X_n)]`, by contrast, is **provably non-increasing** in `n` (a standard order-statistics
result, and the exact property the Module-Count / Resolution Bias Audit increment's own test,
`test_calibration_independence_weakest_link_aggregation_is_monotonically_non_increasing`,
confirms by direct construction: adding a module can only ever keep the running minimum the
same or lower it, never raise it).

This increment adds the concrete, deterministic demonstration of *why* that matters
(`test_mean_aggregation_can_increase_unlike_minimum_which_never_can`,
`tests/agent2/test_module_calibration.py`): adding a new, above-average module to a
`WEIGHTED_MEAN` aggregate **can raise it** — a capability `MINIMUM` structurally lacks. A
criterion that can only ever be hurt, never helped, by more modules is inherently coarse-biased
regardless of what the real evidence says; one that can move in either direction, depending on
the real evidence, is not.

`LOWER_QUANTILE`/`FRACTION_ABOVE_THRESHOLD` sit in between: a lower quantile is less sensitive
to one single worst-scoring module than `MINIMUM` (a larger quantile value moves further from
the raw minimum), but is still not fully count-invariant in general; `FRACTION_ABOVE_THRESHOLD`
is, in expectation, an unbiased estimate of "what proportion of modules are acceptable"
regardless of count, but carries higher variance at low module counts (each additional module
is a bigger swing in the fraction). Neither is proven count-unbiased the way `WEIGHTED_MEAN` is,
so neither was chosen as the default — `WEIGHTED_MEAN` is the one policy with a direct,
first-principles argument for why it carries no inherent module-count bias.

**`MINIMUM` remains fully available** (`MINIMUM_CALIBRATION_AGGREGATION_POLICY`) as an explicit,
strict diagnostic choice (task instructions §3: "keep `MINIMUM` available... but do not make it
the default") — it still answers a real, useful question ("what is this modularization's own
weakest module"), just not the question "should this modularization win a module-count-neutral
comparison."

Demonstrated concretely (`test_one_poor_module_scores_differently_under_mean_vs_minimum`): one
poor module (`UNIDENTIFIABLE`, score `0`) among two otherwise-perfect modules pulls `MINIMUM`
all the way to `0` (the weak module reported verbatim, nothing hidden), while `WEIGHTED_MEAN`
blends it to `2/3` (a real penalty, proportionate to that one module's own share of the whole).

## 4. Degenerate one-module policy

A one-module decomposition has no internal boundary left to optimize — there is nothing to cut,
nothing to declare a port across, nothing a boundary-search criterion can meaningfully improve.
`search_candidate_modularizations` gained a new, optional
`exclude_single_module_from_ranking: bool = True` parameter (default **on**):

- A candidate whose own module count is exactly `1` is still **fully evaluated** (`_evaluate`
  runs on it exactly as on any other candidate) and **fully reported** — on the new
  `CandidateModularizationSearchResult.degenerate`/`.degenerate_evaluations` fields — but is
  excluded from beam selection, the retained candidate set, and the frontier used to generate
  the next generation's proposals. It can never occupy a beam slot that would otherwise go to a
  genuine multi-module candidate, and the final weight-space/stable-boundary analysis (which
  only ever runs over `retained`) never sees it either.
- This applies uniformly, including to the seed itself: an intentionally one-module seed, with
  no override, cannot seed any exploration (there is nothing non-degenerate to build a frontier
  from) — the search terminates after generation 0 with `retained`/`evaluations` both empty and
  `weight_space_result = None` (`explore_weight_space` is never called with an empty
  modularization-id tuple), plus a disclosed warning naming the override. A one-module seed with
  `exclude_single_module_from_ranking=False` competes and explores normally (e.g.
  `SPLIT_MODULE` can still recover a multi-module candidate from it).
- Passing `exclude_single_module_from_ranking=False` reproduces the search's exact pre-existing
  behavior (a one-module candidate competes for beam slots and ranking exactly like before this
  increment) with no change whatsoever.
- Excluding the degenerate candidate never perturbs any *other* candidate's own score or beam
  position (confirmed by test `test_degenerate_exclusion_matches_prior_search_results_otherwise`)
  — it is removed from competition, not allowed to change anyone else's evaluation.

## 5. Integration

Both corrections are threaded through every existing consumer without re-deriving anything:
`evaluate_modularization` (the aggregation policy), `explore_weight_space` (held fixed across
every `(modularization_id, weight_vector)` pair), and `search_candidate_modularizations` (both
the aggregation policy, held fixed across every candidate, and the degenerate-exclusion policy,
applied uniformly to the seed and every generation). `apply_resolution_correction` (the prior
increment's null-baseline normalization, scoped to the four structural criteria) and
`exclude_single_module_from_ranking` are independent, orthogonal flags — both can be enabled
together with no special-casing required.

## 6. Scope boundary honored

No UI. No automatic recursive calibration/search — Agent 4 is still never called automatically
inside this package; only evidence the caller already has is ever consulted. No new calibration
algorithm — every aggregation method is pure arithmetic over Agent 4's own already-reported
per-module scores, never a new way of deriving one.

## 7. Tests / lint

`tests/agent2/test_module_calibration.py` (+19 tests): `CalibrationAggregationPolicy`
construction validation (missing/misplaced `quantile`/`threshold`/`module_weights`, duplicate
weight keys), every aggregation method's own deterministic arithmetic (`WEIGHTED_MEAN` with and
without explicit weights, `LOWER_QUANTILE` nearest-rank at two quantiles, `FRACTION_ABOVE_
THRESHOLD` at two thresholds), the default-is-`WEIGHTED_MEAN`/`MINIMUM`-is-opt-in distinction,
one poor module under mean vs. minimum (task instructions §6), per-module scores/dispersion
always disclosed (including when the aggregate itself is unavailable), the unavailable-evidence
gate being identical across methods, `WEIGHTED_MEAN`'s ability to rise unlike `MINIMUM`'s
inability to, and an end-to-end `evaluate_modularization` threading test. `tests/agent2/test_
resolution_audit.py`/`tests/agent2/test_weight_space_exploration.py` (2 tests updated): the
pre-existing weakest-link-monotonicity proof and the `CALIBRATION_FAILED`/`UNIDENTIFIABLE`-is-
negative-evidence test now pin `policy=MINIMUM_CALIBRATION_AGGREGATION_POLICY` explicitly, since
both specifically exercise that one method's own property, not whatever the current default
happens to be. `tests/agent2/test_modularization_search.py` (+7 tests): the exclusion default,
evaluated-but-excluded-from-ranking, the explicit override restoring prior behavior, exclusion
not perturbing other candidates, a fully-degenerate seed yielding empty/`None` outputs by
default, the override recovering exploration from a degenerate seed, and determinism. One
pre-existing test (`test_apply_resolution_correction_cannot_fix_the_degenerate_single_module_
case`) updated to look in the new `degenerate_evaluations` field, since the candidate it
inspects is now excluded from `evaluations` by the new default.

Full Agent 2 suite: 1233 passed (1207 pre-existing + 26 new/updated for this increment); lint
clean on every touched file (3 pre-existing, unrelated `UP038` findings in
`app.agent2.module_calibration.serialization`, not touched by this increment, left as-is).

## 8. Is recursive, Agent-4-assisted search now safe to enable?

Not yet, and this increment does not attempt it (explicit non-goal). What this increment does
remove is the two scoring-level obstacles that would have made an automatic search loop
*actively misleading* even if wired up: a search that could call Agent 4 on its own candidates
would previously have been structurally rewarded for proposing fewer, coarser modules (the
weakest-link bias) and could have "won" by collapsing to one trivial module with no boundary at
all. Both are now corrected at the scoring/ranking layer. What remains before recursive search
could be safely enabled is unchanged from the prior increment's own assessment: no automatic
Agent 3/Agent 4 invocation exists anywhere in this package, and building that orchestration loop
(cost/budget control over repeated real calibration runs, caching/reuse policy across near-
duplicate candidates, and a decision about how much automatic exploration a human reviewer
should see before any evidence-gathering round trip is spent) is a distinct, larger increment of
its own.
