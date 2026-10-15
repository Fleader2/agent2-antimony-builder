# Weight-Space Exploration and Stable Boundary Discovery

## 1. Goal and architecture

Builds directly on the existing, unchanged Module Boundary Evaluation Framework
(`docs/27_module_boundary_evaluation_framework.md`) -- `ModelModularization`,
`evaluate_modularization`, `evaluate_modularization_under_weights`, `TopologyFilteringPolicy`,
`CriteriaWeights`. New package `app.agent2.weight_space_exploration` (`types.py`,
`sampling.py`, `stability.py`, `exploration.py`, `errors.py`) systematically explores
combinations of modularization-criterion weights and identifies module boundaries/
modularizations that remain stable across reasonable weighting assumptions. Nothing here
alters canonical model semantics: every type is a derived, on-demand analysis result, never
stored on `ModelSpecification`, exactly like `ModularizationEvaluation` itself already is.

```text
ModelSpecification + candidate modularization_ids
          |
          v
WeightGridSpec --(sampling.generate_weight_vectors)--> CriteriaWeights, ...
          |
          v
explore_weight_space(model, modularization_ids, weight_vectors, high_scoring_policy)
          |
          +--> evaluate_modularization(model, mid, weights)  -- one call per (mid, weights) pair
          |
          +--> select_high_scoring_solutions(evaluations, high_scoring_policy)
          |
          +--> compute_boundary_stability / compute_co_membership_stability /
               compute_modularization_recurrence (over the high-scoring subset)
          |
          v
WeightSpaceExplorationResult
```

## 2. Why module structure, not weight choice, drives stability

A single `ModelModularization` has one fixed module/membership/port structure -- re-scoring
it under a different `CriteriaWeights` vector never changes which reaction or species belongs
to which module, only the resulting `overall_score`. "Which boundaries are stable across
weight space" therefore means: across every `(modularization, weight-vector)` pair whose own
score was high enough to be selected, how often does a given reaction-adjacency edge end up
cut, or a given component pair end up co-membered? A modularization that scores well under
many different weight vectors contributes its own fixed structure to that tally once per
high-scoring weight vector it was evaluated under -- naturally weighting a robustly-favored
modularization's own boundaries more heavily than one favored only under a narrow sliver of
weight space. Several structurally distinct candidate modularizations may also be explored
together, so genuinely different boundary hypotheses -- not just different weightings of the
identical one -- can be compared for robustness.

## 3. Weight-space exploration API

- **`WeightRange(criterion, levels)`**: one criterion's own explicit, deterministic candidate
  raw weight levels (e.g. `(Decimal("0"), Decimal("1"), Decimal("2"))`). `0` is a legitimate
  level -- it means "disabled" for that one generated vector, exactly `CriteriaWeights`'s own
  existing rule.
- **`WeightGridSpec(ranges, max_combinations=None)`**: one `WeightRange` per criterion to
  vary -- the task's own "user-supplied weight grids/ranges."
- **`generate_weight_vectors(spec)`** (`.sampling`): the cartesian product of every
  `WeightRange`'s own levels, in deterministic order, always excluding the all-zero
  combination. When the product exceeds `max_combinations`, it is deterministically
  down-sampled to exactly that many vectors via evenly-spaced index selection
  (`_evenly_spaced_indices`) -- never a random subset, never merely the first `N`.
- **`uniform_weight_grid(criteria, steps=3, max_combinations=None)`**: a convenience
  constructor for the common case -- every named criterion varied over the identical `steps`
  integer levels `0, 1, ..., steps - 1` (the task's own "deterministic simplex/grid
  sampling"). A caller needing non-uniform or asymmetric ranges builds a `WeightGridSpec`
  directly instead.

## 4. High-scoring-solution policy

**`HighScoringSolutionPolicy(method, value)`** (task instructions §5) -- a closed,
deterministic, fully-inspectable policy, never a hidden default:

- `TOP_N`: the `value` best-scoring, available evaluations (ties broken by `evaluation_id`,
  ascending).
- `PERCENTILE`: the best `value` fraction (`0 < value <= 1`) of available evaluations, by
  score (`ceil(value * count)`, never truncated down to zero).
- `WITHIN_DELTA_OF_BEST`: every available evaluation within `value` of the single best
  available score.

An evaluation with `overall_score is None` (no available evidence at all, `docs/27` §5) is
never eligible under any method -- excluded before ranking, never treated as the worst
possible score. `select_high_scoring_solutions` returns `()` (never an error) when no
evaluation has an available score at all.

## 5. Boundary and co-membership stability

- **`BoundaryStability(reaction_id_a, reaction_id_b, shared_species_ids, cut_frequency,
  high_scoring_solution_count)`**: `cut_frequency = cut_count / applicable_count` across the
  high-scoring set, where "applicable" means both reactions were covered by some module of
  that solution's own modularization. An edge whose two reactions are stably *internal*
  across every high-scoring solution scores `0` (never reported as "unstable" merely because
  it is stably *not* a boundary).
- **`ComponentCoMembershipStability(component_type, component_id_a, component_id_b,
  co_membership_frequency, high_scoring_solution_count)`**: the more general counterpart --
  meaningful for species (not only reaction-adjacency edges), and directly comparable
  *across different module counts*, since a component's own canonical id is identical
  regardless of how many total modules its own modularization happens to define ("stability
  across module counts where meaningful," task §4). Candidate pairs are restricted to those
  that co-occur within some one module of some one high-scoring modularization at least once
  -- never every possible pair in the network.
- **`ModularizationRecurrence(modularization_id, module_count, evaluated_count,
  high_scoring_count, recurrence_frequency)`**: what fraction of the weight vectors this
  modularization was evaluated under actually placed it among the high-scoring solutions --
  "modularization recurrence/similarity" (task §4).
- **`ModuleCountStabilityGroup(module_count, ...)`**: boundary/co-membership stability
  computed *within* one specific module count alone -- "stability within a given module
  count" (task §4), a strict subset of the overall high-scoring set.
- **Ambiguous boundaries/co-memberships**: `WeightSpaceExplorationResult.ambiguous_boundaries`/
  `.ambiguous_co_memberships` are the subset whose own frequency falls strictly inside
  `(ambiguous_band_low, ambiguous_band_high)` (default `(0.25, 0.75)`, both configurable on
  `explore_weight_space`) -- "unresolved/ambiguous boundaries" (task §6). Nothing here forces
  an unstable solution into a single consensus (task §4): every measure is reported as a
  frequency, never collapsed into one "the" answer.

## 6. Example results (hand-verified fixture, `tests/agent2/test_weight_space_exploration.py`)

A 4-reaction chain `A -> B -> C -> D -> E` with two conflicting candidate modularizations --
`"topo"` (respects network adjacency: `TOPOLOGICAL_SEPARATION = 2/3`, `EC_CLASS_COHERENCE =
0.5`) and `"ec"` (respects curated EC-number classes: `TOPOLOGICAL_SEPARATION = 0.0`,
`EC_CLASS_COHERENCE = 1.0`). Weighting `TOPOLOGICAL_SEPARATION` alone favors `"topo"`;
weighting `EC_CLASS_COHERENCE` alone favors `"ec"` -- directly confirming "different weight
regimes favor different solutions." Under an equal-weight vector with both candidates
selected as high-scoring (`WITHIN_DELTA_OF_BEST`, generous delta): the `r2<->r3` edge, cut by
*both* candidates, reports `cut_frequency = 1` (fully stable); `r1<->r2` and `r3<->r4`,
disagreed on by the two candidates, report `cut_frequency = 0.5` (correctly flagged
ambiguous). Exploring the identical single modularization under many distinct weight vectors
always yields `cut_frequency` exactly `0` or `1` for every edge -- a single, fixed structure
can never itself be internally ambiguous; genuine ambiguity requires genuinely different
candidate structures to disagree.

## 7. Module-count handling

`explore_weight_space` never assumes one module count is preferred (task §3): every
evaluation, across every modularization and module count actually supplied, is preserved in
`.evaluations` (which already carries `.modularization_id`/`.module_count`/`.overall_score`
per entry -- never duplicated as separate top-level fields), and `.by_module_count` reports
stability separately per distinct module count actually explored, alongside the combined,
overall `.boundary_stability`/`.co_membership_stability` measures. Verified by test with
three candidates of module counts `2`, `2`, and `4`.

## 8. Recursive readiness (not implemented)

Nothing in `explore_weight_space`'s own signature assumes "the whole canonical model" -- it
takes an ordinary `ModelSpecification` and a tuple of `modularization_id`s exactly like
`compare_modularizations` already does. A future increment recursing into one selected module
(to discover hierarchical submodules) only needs to build a scoped sub-`ModelSpecification`/
sub-`ModelModularization` set the identical way the existing Scoped-Build Support increment
already builds a scoped `FullNetwork` -- no interface change is anticipated.
`WeightSpaceExplorationResult`'s own `evaluations`/`boundary_stability`/
`co_membership_stability` are already a clean, directly-comparable, serializable snapshot a
future recursive increment can collect and compare across many nested explorations without
any new type.

## 9. Scope boundary honored

No UI/sliders (the API is already structured for a future Workbench UI to drive directly).
No recursion. No simulation, calibration, or new Agent 3/4 behavior. No sophisticated
clustering of solutions -- stability is reported as plain frequencies, never automatically
clustered or reduced to a single consensus.

## 10. Tests / lint

`tests/agent2/test_weight_space_exploration.py`: deterministic weight-grid generation
(count, determinism, capping, explicit user-supplied ranges, all-zero-only rejection);
different weight regimes favoring different candidate modularizations; a boundary cut by
every high-scoring candidate reported fully stable; a boundary disagreed on by high-scoring
candidates reported ambiguous; a single candidate's own boundaries are always fully resolved
(never ambiguous) regardless of how many weight vectors are explored; module-count
preservation across three candidates of counts 2/2/4; `topology_filtering` integration (a
spurious, uncurated-name adjacency diluting the score until explicitly filtered); unavailable-
criterion handling (a weight vector naming only an unavailable criterion yields an empty
high-scoring set, never a crash or a fabricated score); no mutation of the canonical model;
full determinism; reference-error handling; GENERATED/IMPORTED symmetry (restricted to the
three criteria genuinely available to either origin -- EC_CLASS_COHERENCE is deliberately
excluded from that one comparison, since curated EC numbers have no Antimony-text equivalent
to import, a disclosed, expected asymmetry, not a regression). 18 new tests, all passing;
full Agent 2 suite 1118 passed; lint clean.
