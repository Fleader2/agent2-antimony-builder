# Candidate Modularization Search

## 1. Goal and architecture

Generates plausible alternative modularizations from a seed `ModelModularization`, evaluated
entirely through the existing, unchanged Module Boundary Evaluation Framework / Weight-Space
Exploration framework (`evaluate_modularization`/`explore_weight_space`). Never mutates the
canonical `ModelSpecification`; never calls Agent 3/Agent 4 automatically.

```text
canonical whole-network model
  (read-only: full_network/kinetic_laws/parameters)
        |
        v
seed modularization (extract_bundle, then canonicalize_bundle -- see §6)
        |
        v
propose neighboring modularizations (operators.py, bounded by SearchPolicy)
        |
        v
evaluate under weight-space criteria (evaluate_modularization, unchanged)
        |
        v
retain promising candidates (beam, deduplicated by partition+port signature)
        |
        v
propose further candidates from the retained beam (repeat, up to max_iterations)
        |
        v
stable-boundary analysis over every retained candidate together (explore_weight_space, unchanged)
```

Works identically for a `GENERATED` or `IMPORTED` model, and identically when `model` is itself
a previously-derived module/submodel re-assembled as its own `ModelSpecification` (§8) --
every value this package reads comes from `model.full_network`/`.kinetic_laws`/
`.module_memberships`/`.module_ports` alone, never anything origin-specific.

## 2. Content-addressed identity (the load-bearing design decision)

Every module id this package generates is a deterministic function of that module's own
membership *content* (`app.agent2.modularization_search.identity.derive_module_id`, from the
sorted `(component_type, component_id)` pairs naming it) -- never an arbitrary counter. This
one decision solves three problems the task raises together:

- **Duplicate-equivalence** (`candidate_signature`): two candidates with an identical
  membership partition always agree on every module's own id, so "is this a duplicate" is a
  single signature comparison, never a structural diff.
- **Calibration-evidence lookup** (§5): a module in a freshly-generated candidate whose own
  content exactly matches one the caller already has evidence for picks it up automatically,
  regardless of which generation/operation produced it.
- **Port survival across a rebuild** (`assembly.rebuild_bundle`): a port survives a structural
  change (move/merge/split) iff the module it names has *identical content* before and after --
  matched by content, never by comparing module-id strings, so a freshly-extracted seed's own
  human-given module ids (`"modA"`, ...) are first canonicalized (`assembly.canonicalize_bundle`)
  before anything else happens, and every id downstream of that stays content-addressed by
  construction.

## 3. Proposal operators (task instructions §2)

All six operators are pure functions `(bundle, model, constraints) -> tuple[Proposal, ...]`,
never mutating their own inputs, returning *every* valid, constraint-respecting proposal in
deterministic order:

- **`MOVE_REACTION`**: relocates one reaction (alone) to a different existing module. Never
  empties its own source module. **V1 simplification**: never proposed for a reaction that is
  itself a member of a `must_stay_together` group with more than one member (only a whole-group
  move could respect cohesion; not implemented).
- **`ADD_BOUNDARY`**/**`REMOVE_BOUNDARY`**: declare/remove an explicit `ModulePort` pair for one
  species already topologically shared between two modules -- the membership partition is
  completely unchanged; only port declarations change (relevant to `BOUNDARY_SPARSITY`/
  standalone-submodel eligibility specifically). Direction is inferred deterministically from
  participant roles (PRODUCT-only in A + REACTANT-only in B -> OUTPUT/INPUT; otherwise
  `INPUT_OUTPUT` for both, never guessed).
- **`MERGE_MODULES`**: combines two modules *only if they are genuinely topologically adjacent*
  (share a species via some reaction in each, `topology.modules_are_adjacent`) -- never an
  arbitrary pair.
- **`SPLIT_MODULE`**: partitions one module's own reactions using its own internal topology
  (`topology.connected_components`) when it is not fully connected; falls back to a disclosed,
  simple sorted-id bisection when it is (task instructions: "do not implement sophisticated
  ML/optimization yet"). Species/parameters follow the bucket containing the majority of their
  own anchor reactions (a genuine tie creates a real new boundary species, never silently
  resolved by a coin flip).
- **`VARY_MODULE_COUNT`**: a "fast lane" directly toward whichever end of the allowed
  `[min_module_count, max_module_count]` range is not already the current count, via repeated
  deterministic merge/split -- correctly in *whichever direction actually reaches that target*
  (shrinking to reach a `max_module_count` below the current count, or growing to reach a
  `min_module_count` above it; a real bug caught only against the real yeast model, §7). Produces
  nothing when neither bound is set (no defined "extreme" to jump to).

Module size/count is always measured in `REACTION` membership count.

## 4. Constraint model (task instructions §3)

`SearchConstraints` -- every field defaults to "unconstrained"; checked at generation time,
never post-hoc (a violating candidate's own membership/port rows are never constructed at all):

| Constraint | Field | Enforced by |
|---|---|---|
| Must remain together | `must_stay_together: tuple[frozenset[str], ...]` | `MOVE_REACTION` (skips any grouped member), `SPLIT_MODULE` (declines a split that would separate a group) |
| Required module membership | `required_module_component_ids` | satisfied by construction -- no operator ever drops a component from every module (documented, not actively enforced by a separate check) |
| Forbidden module membership | `excluded_component_ids` | `SPLIT_MODULE` drops an excluded species/parameter's own row rather than carrying it into either new module |
| Forbidden together | `forbidden_together: tuple[frozenset[str], ...]` | `MOVE_REACTION`/`MERGE_MODULES`/`SPLIT_MODULE` |
| Fixed boundaries | `fixed_boundaries: tuple[FixedBoundary, ...]` (`MUST_BE_DECLARED`/`MUST_NOT_BE_DECLARED`) | `ADD_BOUNDARY`/`REMOVE_BOUNDARY` alone |
| Module size range | `min_module_size`/`max_module_size` | every structural operator |
| Module count range | `min_module_count`/`max_module_count` | every structural operator (per-candidate); `VARY_MODULE_COUNT`'s own *intermediate* greedy steps are deliberately exempt from this one check (see §7) -- only the final candidate's own count is ever validated against it |

## 5. Candidate evaluation (task instructions §5) -- the existing framework, unchanged

Every candidate is scored by calling `evaluate_modularization` on an ephemeral view of `model`
carrying *only* that one candidate (`assembly.attach_bundle`, `dataclasses.replace` --
`model` itself is never touched). `topology_filtering` (currency/hub filtering) and
`calibration_evidence` are threaded straight through, unchanged from the Recursive Module
Evaluation Orchestration / Calibration Evidence Integration increments.

**Calibration evidence** (optional) is a flat mapping keyed by module *content* (§2) --
`Mapping[frozenset[(component_type, component_id)], ModuleCalibrationEvaluation]`. Agent 4 is
never called automatically inside this search (task instructions §5): only evidence a caller
already obtained via the existing `app.agent2.module_calibration`/Harness orchestration layer is
ever consulted, and a module in a freshly-generated candidate picks it up by content match
alone. When the overall mapping is supplied but a module has no matching entry, that module is
honestly `missing` (weakest-link `available=False`), never fabricated or silently dropped --
unchanged from `calibration_adapter.score_calibration_independence`'s own policy.

**Retention**: a deterministic beam/best-first search (`SearchPolicy`: `max_iterations`,
`max_candidates_per_iteration`, `beam_width`, `allowed_operations`). Every candidate proposed
this generation is scored; the top `beam_width` (by `overall_score`, `None` sorting last, ties
broken by candidate id) become next generation's frontier *and* join the cumulative retained
set (every candidate that ever made a beam, not just the final frontier -- task instructions
§7: "all evaluated candidates retained by policy"). The search stops early, before
`max_iterations`, the moment a generation produces no new, non-duplicate candidate (bounded
termination, never looping uselessly).

**Fair per-operation capping** (a real fix, not a simplification -- §7): `max_candidates_per_
iteration` is split evenly across every operation that actually produced at least one raw
proposal this generation, not one global, lexicographically-ordered cut. A single global cut
would let whichever operation happens to produce the most raw proposals (`ADD_BOUNDARY`,
observed on the real yeast model) silently starve every other allowed operation out of ever
being considered at all, even though the caller explicitly enabled it.

After the beam search concludes, every retained candidate is attached *together*
(`assembly.attach_many`, deduplicating any module/membership byte-identical across candidates --
content-addressing again) and passed to `explore_weight_space` (unchanged) for stable-boundary
discovery -- `stability_weight_vectors`/`high_scoring_policy` (optional) default to the single
`criteria_weights` vector and a "keep every retained candidate" `TOP_N` policy, since the beam
search's own retention policy already did the filtering.

## 6. Candidate identity/provenance (task instructions §6)

Every candidate -- retained or rejected -- has a `CandidateLineage` entry: `candidate_id`
(`"candidate::gen<N>::<counter>"`, deterministic, sequential), `parent_candidate_id` (`None`
only for the seed), `operation`, `affected_component_ids`/`affected_module_ids`, `generation`
(search depth), `policy_version`. Every `RejectedCandidate` (a duplicate, or a candidate that
did not make a generation's beam cutoff) carries its own parent and a human-readable reason --
never silently dropped. Lineage always terminates at the seed (verified by test, walking every
candidate's own ancestry chain).

## 7. Example search on the real yeast model (sce00061)

Ran against the real, cached Agent 1 curated knowledge view (no live-DB round trip needed --
`agent-integration-harness/tests/fixtures/sce00061_agent1_curated_knowledge_view.json`), through
the real `run_agent2_pipeline`: 53 species, 38 reactions, and the default heuristic
decomposition's own 26-module seed (one 13-reaction module, 25 single-reaction modules).
Weighted `TOPOLOGICAL_SEPARATION`/`BOUNDARY_SPARSITY`/`COMPARTMENT_COHERENCE` equally, with
`SearchConstraints(min_module_size=1, min_module_count=2, max_module_count=8)` and all six
operators allowed:

- **Seed score**: `0.806` at 26 modules.
- **Module counts actually explored**: `{2, 3, 6, 7, 8, 26}` -- a real range, not just the seed's
  own starting count.
- **Best retained candidate**: `0.961` at 2 modules -- a real, substantial improvement the seed
  itself never considered.

**Two genuine bugs were caught only by running against this real, 26-module model** (every
hand-built fixture in the test suite starts from 1-4 modules, too small to expose either):

1. `VARY_MODULE_COUNT`'s own direction logic only ever handled "grow toward a `max_module_count`
   currently above the seed" and "shrink toward a `min_module_count` currently below it" --
   never the reverse (shrink toward a `max_module_count` the seed is *already above*, as every
   real case with `max_module_count=8` and a 26-module seed actually is). Fixed: the target
   (`max_module_count`/`min_module_count`, whichever differs from the current count) now always
   determines direction from its own relationship to the current count, not from which bound it
   came from.
2. A single, global, lexicographically-ordered truncation of raw proposals let `ADD_BOUNDARY`
   (405 raw proposals on the real model) completely starve `VARY_MODULE_COUNT` (2 raw proposals)
   out of ever being evaluated at any `max_candidates_per_iteration` budget that `ADD_BOUNDARY`
   alone could fill. Fixed: `_cap_fairly_across_operations` (§5) splits the budget evenly across
   every operation that produced at least one proposal.

Both are now covered by dedicated regression tests (`test_vary_module_count_shrinks_toward_max_
when_currently_above_it`, `test_vary_module_count_grows_toward_min_when_currently_below_it`,
`test_cap_fairly_across_operations_never_starves_a_low_volume_operation`).

## 8. Recursive readiness (not implemented, but not precluded)

Nothing in `search_candidate_modularizations`'s own signature assumes "the whole canonical
model" -- it takes an ordinary `ModelSpecification` and a `seed_modularization_id`, exactly like
`evaluate_modularization`/`explore_weight_space` already do. A future increment running this
same search on a scoped module/submodel only needs to build that scoped `ModelSpecification`
the identical way the Recursive Module Evaluation Orchestration increment's own recursive-
readiness test already does by hand -- no interface change is anticipated. Automatic recursive
descent (recursing into one promising candidate's own module to search *it*) is explicitly not
implemented in this increment (task instructions §8).

## 9. Scope boundary honored

No UI, no automatic recursion, no new Agent 3/4 algorithms (Agent 4 is never called inside this
search -- only caller-supplied evidence, already obtained through the existing orchestration
layer, is ever consulted), no Agent 5 logic, no sophisticated ML/optimization (every operator is
a simple, disclosed, deterministic heuristic -- connected components or sorted-id bisection for
splitting, nothing learned or optimized).

## 10. Tests / lint

`tests/agent2/test_modularization_search.py` (37 tests): every proposal operator (including
constraint-respecting and constraint-violating cases for each), deterministic search, no
canonical-model mutation, bounded termination (both `max_iterations` and "no new candidates"
early-stop), `max_candidates_per_iteration` capping, duplicate-candidate elimination,
module-count variation, candidate lineage tracing to the seed, rejected-candidate reasons,
rankings changing under different criterion weights, calibration evidence affecting retention
(both a clear win and an honestly-unavailable partial-evidence case), filtered-topology
integration, GENERATED/IMPORTED symmetry, the "no declared winner" output shape, and the two
real-data regression tests from §7. Full Agent 2 suite 1188 passed; lint clean.
