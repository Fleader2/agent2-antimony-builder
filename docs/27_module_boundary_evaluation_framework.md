# Module Boundary Evaluation Framework

> **Naming correction** (`docs/29_ec_class_coherence_naming_correction.md`): the criterion
> this document originally named `PATHWAY_ANNOTATION_COHERENCE` never read genuine pathway/
> network membership data -- it matched curated EC-number top-level classes only. It is now
> named `EC_CLASS_COHERENCE` (scoring formula and behavior unchanged);
> `PATHWAY_ANNOTATION_COHERENCE` is re-declared as a genuinely reserved, unimplemented
> criterion for the real pathway-membership signal. Every reference to the old name below is
> updated accordingly.

## 1. Scientific principle

> **Module mechanisms are evidence; functional/contextual independence is the eventual
> target property.**

Topology, compartment membership, pathway annotations, regulation, dynamics, calibration
behavior, etc. are criteria contributing evidence for modularity -- none of them
individually *defines* it. This increment's entire purpose is to stop treating one mechanism
(e.g. the pre-existing heuristic topological decomposition, `docs/26_...md`) as "the"
definition of a good module boundary, and instead score any candidate `ModelModularization`
against several independent evidence signals, explicitly weighted, with every criterion's own
raw score always separately inspectable.

## 2. Architecture

```text
ModelSpecification (GENERATED or IMPORTED, unaffected)
          |
          v
  ModelModularization (existing, unified representation, docs/22+docs/26)
          |
          v
  evaluate_modularization(model, modularization_id, weights)
          |
          +--> TOPOLOGICAL_SEPARATION      (criteria.score_topological_separation)
          +--> BOUNDARY_SPARSITY           (criteria.score_boundary_sparsity)
          +--> COMPARTMENT_COHERENCE       (criteria.score_compartment_coherence)
          +--> EC_CLASS_COHERENCE          (criteria.score_ec_class_coherence)
          |
          v
  ModularizationEvaluation (individual scores + weighted overall_score)
```

New package `app.agent2.module_evaluation` (`types.py`, `criteria.py`, `evaluator.py`,
`errors.py`). Read-only: it only reads an already-assembled `ModelSpecification`'s
`full_network`/`modularizations`/`model_modules`/`module_memberships`/`module_ports`, never
mutates anything, and never imports `app.agent2.antimony` -- executable whole-network
semantics and standalone-module generation (`docs/26_...md`) are completely untouched. None
of this package's own types are ever stored on `ModelSpecification`/`Agent2OutputPackage` --
an evaluation is always a derived, on-demand analysis, exactly like
`app.agent2.modularization.derivation.ModuleConnection` is "always computed, never
persisted."

## 3. Types

- **`ModularizationCriterion`** (`StrEnum`): `TOPOLOGICAL_SEPARATION`/`BOUNDARY_SPARSITY`/
  `COMPARTMENT_COHERENCE`/`EC_CLASS_COHERENCE` (implemented today) plus
  `PATHWAY_ANNOTATION_COHERENCE`/`DYNAMIC_ISOLATION`/`SENSITIVITY_COHERENCE`/
  `CALIBRATION_INDEPENDENCE`/`REGULATORY_COHERENCE`/`EXPERIMENTAL_VALIDATION` (reserved
  vocabulary for future increments -- mirrors `ModularizationMethod`'s own identical
  closed-enum-with-reserved-members convention, docs/22 §2).
- **`CriterionWeight`**: `criterion`, `weight` (`Decimal >= 0`, raw/un-normalized).
- **`CriteriaWeights`**: `weights: tuple[CriterionWeight, ...]`, `policy_version`. Rejects a
  duplicate criterion and an all-zero vector at construction. `raw_weight(criterion)`/
  `normalized_weight(criterion)` are pure methods: a criterion's own normalized share of the
  total *positive* weight always sums to `1` across every positive-weight criterion in the
  vector; a zero or omitted criterion always normalizes to exactly `0` ("zero weight disables
  a criterion," task §3).
- **`ModularizationCriterionScore`**: one criterion's full result -- `available`, `raw_score`
  (`Decimal` in `[0, 1]` or `None`), `raw_weight`, `normalized_weight`,
  `weighted_contribution` (`None` whenever unavailable or zero-weighted), `explanation`,
  `warnings`, `provenance_refs`.
- **`ModularizationEvaluation`**: `evaluation_id`, `modularization_id`, `module_count`,
  `criterion_scores` (always one entry per *implemented* criterion, regardless of weight --
  "each criterion must remain separately inspectable," task §1), `weights`, `overall_score`,
  `evaluated_weight_fraction`, `policy_version`, `warnings`, `provenance_refs`.

## 4. The four implemented criteria

All four read only `FullNetwork` + the caller's own already-filtered `ModuleMembership`/
`ModulePort` rows for one modularization -- "currently supportable from Agent 2/canonical-
model information" (task §2), no new data source, no Agent 1 contract change.

1. **`TOPOLOGICAL_SEPARATION`**: builds the network's own implicit reaction-adjacency graph
   (two reactions adjacent iff they share at least one species), restricted to reactions that
   are members of this modularization. `score = internal_edges / (internal_edges +
   cut_edges)`. **Known, disclosed limitation**: the simplest possible adjacency rule does
   not special-case common, high-degree cofactors (ATP, water, CoA, ...), which can make a
   real metabolic network's own adjacency graph far denser -- and this score correspondingly
   lower -- than a cofactor-aware measure would report. Verified directly against the real
   yeast lipid-biosynthesis organism (score `0.236` under the heuristic TOPOLOGICAL
   modularization); not a defect, a disclosed characteristic of this specific criterion.
2. **`BOUNDARY_SPARSITY`**: `score = 1 - (distinct species named by some ModulePort) /
   (distinct species that are members of some module)`. Zero declared ports is a real,
   legitimate `1.0` (perfectly sparse from the *declared*-interface perspective), never
   missing evidence. Deliberately reads a different signal than criterion 1 (explicit
   declaration vs. implicit network structure) -- the two can, and often will, disagree.
3. **`COMPARTMENT_COHERENCE`**: per module, `(species in that module's own modal compartment)
   / (total species in that module)`, averaged across modules. A module spanning a transport
   reaction legitimately scores lower -- expected, disclosed evidence (mirrors
   `docs/10_module_decomposition.md` §17's own identical observation).
4. **`EC_CLASS_COHERENCE`**: the curated EC-number top-level class
   (`ReactionSpecification.ec_number`, Biological Display Metadata increment) -- the one
   functional-annotation signal Agent 2 already carries. Per module, `(EC-annotated reactions
   sharing that module's own modal EC class) / (EC-annotated reactions in that module)`,
   averaged across modules with at least one EC-annotated reaction. **This is not genuine
   pathway-membership coherence** -- it was originally, incorrectly, named
   `PATHWAY_ANNOTATION_COHERENCE`; that name is now reserved instead for the real signal
   (`docs/29_ec_class_coherence_naming_correction.md`). Agent 1's own curated KEGG
   `CuratedNetwork`/pathway data (`networks`/`network_pathways` on `Agent1KnowledgePackage`)
   is not yet wired into Agent 2's `FullNetwork` at all -- wiring it in, and implementing the
   reserved `PATHWAY_ANNOTATION_COHERENCE` criterion against it, is a disclosed extension
   point for a future increment, not attempted here (would require an Agent 1 -> Agent 2
   contract change, outside this increment's own scope of "criteria currently supportable
   from Agent 2/canonical-model information").

## 5. Missing-evidence policy

Every criterion function returns `available=False` (never a fabricated number) exactly when:

- `TOPOLOGICAL_SEPARATION`: this modularization's own member reactions share zero adjacency
  edges.
- `BOUNDARY_SPARSITY`/`COMPARTMENT_COHERENCE`: this modularization has zero species
  membership at all.
- `EC_CLASS_COHERENCE`: no reaction in any module carries a curated EC number.

`ModularizationEvaluation.overall_score` is `None` exactly when `evaluated_weight_fraction ==
0` (zero positive-weight criteria have available evidence) -- never a fabricated score from
nothing. When some, but not all, positive-weight criteria are available, `overall_score` is
the sum of only the *available* criteria's own weighted contributions, computed from the
**original, un-renormalized** weights -- deliberately never redistributed among just the
available subset, so the number's own meaning never silently shifts depending on what
happened to be available this time. The resulting shortfall from the nominal total weight is
exactly what `evaluated_weight_fraction` discloses, honestly, every time. A criterion that is
unavailable despite carrying a positive weight also adds a named, explicit warning to
`ModularizationEvaluation.warnings`.

## 6. Weighting behavior

`CriteriaWeights` requires at least one positive weight (an all-zero vector carries no
comparative information and is rejected at construction). Normalization is deterministic and
automatic: every positive-weight criterion's own `normalized_weight` always sums to `1`
across the vector; a zero or *omitted* criterion normalizes to exactly `0` -- omission and an
explicit `weight=0` are indistinguishable from `evaluate_modularization`'s own perspective, by
design. Every implemented criterion's own raw score is always computed and reported
regardless of its weight; weight only ever gates the *weighted contribution*.

## 7. Multi-weight / multi-modularization comparison

- `evaluate_modularization_under_weights(model, modularization_id, weight_vectors)`: scores
  the identical modularization once per supplied `CriteriaWeights`, in the given order,
  one-to-one -- the task's own "weight-space exploration" (§5), structured so a future
  Workbench UI can supply slider-driven vectors directly without any interface change.
- `compare_modularizations(model, modularization_ids, weights)`: scores several alternative
  modularizations -- of possibly different module counts -- under the identical weights,
  returned in the given order. **Neither function ever picks a winner** (task §6): no
  sorting-by-score, no argmax, no "best" field anywhere in `ModularizationEvaluation`.

## 8. Generated/imported symmetry

Verified directly by test (`tests/agent2/test_module_evaluation.py
::test_evaluation_works_identically_for_generated_and_imported_models`): the identical
`ModelModularization`/`ModelModule`/`ModuleMembership`/`ModulePort` bundle, attached via plain
`dataclasses.replace` to both a GENERATED and an IMPORTED model of the same reaction/species
shape, produces identical `available`/`raw_score` for every criterion and an identical
`overall_score`. No origin-specific branch exists anywhere in `app.agent2.module_evaluation`.

## 9. Stability preparation (not implemented, only prepared for)

Task §7 asks that the result representation support a *later* increment measuring boundary
recurrence/stability across weight space, and hierarchical/recursive modularization. Nothing
further was built here: `ModularizationEvaluation`'s own `modularization_id`/`module_count`/
`criterion_scores` are already a clean, directly-comparable, serializable snapshot, and
`evaluate_modularization_under_weights` already produces exactly the kind of "many
evaluations of the same modularization across weight space" collection such a future
increment would need to analyze -- no new type or interface change is anticipated.

## 10. Extension points for Agent 3/4/5

`DYNAMIC_ISOLATION` (Agent 3), `SENSITIVITY_COHERENCE`/`CALIBRATION_INDEPENDENCE` (Agent 4),
`REGULATORY_COHERENCE`, `EXPERIMENTAL_VALIDATION` (Agent 5) are reserved `ModularizationCriterion`
members with no producer in this codebase today. A future increment implementing one needs no
interface change: it adds its own `score_*` function to `criteria.py`, adds the criterion to a
(possibly extended) `IMPLEMENTED_CRITERIA` tuple, and `evaluate_modularization` picks it up
automatically -- `CriteriaWeights`/`ModularizationCriterionScore`/`ModularizationEvaluation`
already support an arbitrary-length criterion set.

## 11. Contract/version changes

New `MODULE_EVALUATION_POLICY_VERSION = "module-evaluation-v1"`. No other version constant
changes: this package's own types are never stored on `ModelSpecification`/
`Agent2OutputPackage`, so `AGENT2_CONTRACT_VERSION`/`AGENT2_DOWNSTREAM_CONTRACT_VERSION` are
both unaffected.

## 12. Explicit non-goals (honored)

No UI (sliders deferred to a future Workbench increment -- the API is already structured for
one, §7 above). No automatic/recursive weight-space search. No simulation, calibration, or
experimental-design logic. No sophisticated clustering of candidate solutions. No winner ever
automatically chosen between alternative modularizations or weight vectors.
