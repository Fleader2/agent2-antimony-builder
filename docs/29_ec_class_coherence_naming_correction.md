# `EC_CLASS_COHERENCE` Naming Correction

## 1. The problem

The Module Boundary Evaluation Framework increment (`docs/27_module_boundary_evaluation_framework.md`)
shipped a criterion named `PATHWAY_ANNOTATION_COHERENCE`. Its own implementation, then and
now, never read genuine pathway or network-membership data at all -- it matched curated
EC-number top-level classes (e.g. `"6.4.1.2"` -> class `"6"`) between reactions in the same
module. That is a real, legitimate signal, but a different, narrower one than "pathway
annotation coherence" names. This increment corrects the name without changing the
underlying behavior at all.

## 2. Final criterion name chosen

`EC_CLASS_COHERENCE` -- the more scientifically precise of the two names the task offered
(`EC_CLASS_COHERENCE` / `ENZYME_FUNCTION_COHERENCE`), since the criterion matches curated
EC-number *classes* specifically, not a broader notion of "enzyme function."

## 3. What changed

- `ModularizationCriterion.PATHWAY_ANNOTATION_COHERENCE` -> `ModularizationCriterion
  .EC_CLASS_COHERENCE` (the enum *value* string also changed, from `"PATHWAY_ANNOTATION_
  COHERENCE"` to `"EC_CLASS_COHERENCE"` -- this criterion's own types are never stored on
  `ModelSpecification`, so there is no persisted data anywhere whose serialized label this
  could silently break; see §6).
- `app.agent2.module_evaluation.criteria.score_pathway_annotation_coherence` ->
  `score_ec_class_coherence` (function body, scoring formula, and every return value
  unchanged byte-for-byte except renamed internal identifiers -- see §4).
- `IMPLEMENTED_CRITERIA` now lists `EC_CLASS_COHERENCE` in the same position
  `PATHWAY_ANNOTATION_COHERENCE` previously occupied.
- `evaluator.py`'s dispatch dict key/import updated to match.
- `tests/agent2/test_module_evaluation.py`: every `PATHWAY_ANNOTATION_COHERENCE` reference,
  and the three `test_pathway_annotation_coherence_*` function names, renamed to
  `EC_CLASS_COHERENCE`/`test_ec_class_coherence_*`. One new test added (§4 below).
- `docs/27_module_boundary_evaluation_framework.md`: every reference updated, plus a
  pointer to this document at the top.
- `README.md`/`app/agent2/version.py`: the Module Boundary Evaluation Framework changelog
  entry's own `PATHWAY_ANNOTATION_COHERENCE` mention corrected.

## 4. `PATHWAY_ANNOTATION_COHERENCE` reserved for genuine future use

`ModularizationCriterion.PATHWAY_ANNOTATION_COHERENCE` is re-declared as a new, separate,
genuinely reserved enum member -- no producer anywhere in this codebase today, exactly like
`DYNAMIC_ISOLATION`/`SENSITIVITY_COHERENCE`/`CALIBRATION_INDEPENDENCE`/
`REGULATORY_COHERENCE`/`EXPERIMENTAL_VALIDATION` already were. It is reserved specifically
for genuine pathway/network-membership data: Agent 1's own curated KEGG `CuratedNetwork`
(`networks`/`network_pathways` on `Agent1KnowledgePackage`), which is not yet wired into
Agent 2's `FullNetwork` at all. A future increment implementing it needs no further
conceptual rename -- it only adds its own `score_pathway_annotation_coherence` function to
`criteria.py` and adds `PATHWAY_ANNOTATION_COHERENCE` to `IMPLEMENTED_CRITERIA`, exactly the
same mechanical extension every other reserved criterion already documents
(`docs/27` §10). Confirmed by test
(`test_pathway_annotation_coherence_is_reserved_vocabulary_with_no_producer`): the member
exists on the enum, is absent from `IMPLEMENTED_CRITERIA`, and a `CriteriaWeights` naming it
never produces a `criterion_score` entry or a fabricated contribution.

## 5. Scoring behavior: unchanged, confirmed

`score_ec_class_coherence`'s own body is identical to the pre-rename
`score_pathway_annotation_coherence` except for internal variable naming cleanup (the
docstring's "today's proxy for pathway coherence" framing was removed, since the function is
no longer pretending to approximate pathway coherence at all -- it is now presented, plainly
and correctly, as EC-class coherence). The formula, the per-module modal-EC-class-fraction
computation, the mean-across-annotated-modules aggregation, and the unavailable-when-
zero-EC-annotated-reactions rule are all byte-for-byte unchanged. Every pre-existing test
that pinned a specific numeric score against this criterion (now renamed, never rewritten in
substance) continues to pass unmodified in its assertions.

## 6. Weighting, symmetry, and downstream contracts: unaffected

- **Weight handling**: `CriteriaWeights`/`CriterionWeight`/`ModularizationCriterionScore`'s
  own types, validation, and normalization math are completely untouched -- the rename only
  changes which `ModularizationCriterion` member a `CriterionWeight`/`criterion_scores` entry
  may name.
- **Generated/imported symmetry**: `score_ec_class_coherence` reads only `FullNetwork`/
  `ModuleMembership`, exactly as its predecessor did -- no origin-specific branch existed
  before this rename, and none exists now.
- **Downstream contracts**: this criterion's own types were never stored on
  `ModelSpecification`/`Agent2OutputPackage` and never crossed the Agent 2 -> Agent 3/4/5
  downstream handoff before this rename (confirmed in `docs/27` §2/§11) -- there is nothing
  for this rename to regress. `AGENT2_CONTRACT_VERSION`/`AGENT2_DOWNSTREAM_CONTRACT_VERSION`
  are both unaffected; no version constant changes at all for this corrective increment.

## 7. Tests / lint

`tests/agent2/test_module_evaluation.py`: 42 tests (41 pre-existing, renamed where they
referenced the old name, plus one new test confirming `PATHWAY_ANNOTATION_COHERENCE`'s own
reserved status). Full Agent 2 suite: 1100 passed. Harness (including the real live-DB yeast
workflow) and Workbench suites both re-run clean. Lint clean on every touched file.
