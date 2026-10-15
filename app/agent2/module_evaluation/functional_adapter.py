"""Converts externally-obtained ``ModuleFunctionalEvaluationResult`` evidence (one Harness
round trip through Agent 3 per module, ``app.agent2.module_functional_evaluation``) into the
Module Boundary Evaluation Framework's own, previously-reserved ``DYNAMIC_ISOLATION``/
``SENSITIVITY_COHERENCE`` criteria (Functional Modularity Criteria from Agents 3 and 4
increment, task instructions §2/§3).

Both criteria are derived from the *identical* underlying evidence -- one module's own battery
of perturbations spanning both inside and outside it, each disclosing a per-species relative-
change profile -- interpreted two different ways:

* **Dynamic isolation** asks about *magnitude*: how much does an internal perturbation's own
  effect stay inside the module (little spillover), how little do the module's own outputs
  move in response to an external perturbation (little external dependence), and how much of
  whatever cross-module influence does exist is absorbed by the module's own declared boundary
  species rather than leaking to the rest of the module.
* **Sensitivity coherence** asks about *shape*: do the module's own internal-target
  perturbations produce *similar* per-species response profiles to each other (evidence the
  grouped components are mechanically coupled), and is that internal profile shape genuinely
  *different* from an external target's own profile shape (evidence the declared boundary
  really does separate two distinct sensitivity groups) -- never conflated with dynamic
  isolation's own magnitude question.

Deliberately kept separate from ``criteria.py`` (every function there reads only canonical-
model data) and from ``calibration_adapter.py`` (a different external agent, Agent 3 rather
than Agent 4) -- mirrors that module's own "adapter, never a simulation" discipline exactly:
this package never runs a simulation itself, it only interprets evidence the Harness already
obtained from Agent 3.

**Never fabricates a score.** Both ``score_dynamic_isolation``/``score_sensitivity_coherence``
return ``available=False`` whenever any of the modularization's own modules has unavailable
evidence (no entry at all, or a disclosed ``INSUFFICIENT_TARGETS``/``UNSUPPORTED_ANALYSIS``
status, or too few usable internal/external perturbations to compute the relevant measure) --
a weakest-link gate across modules, identical in spirit to ``calibration_adapter``'s own.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from app.agent2.module_evaluation.criteria import CriterionResult
from app.agent2.module_evaluation.types import DynamicIsolationDetail, SensitivityCoherenceDetail
from app.agent2.module_functional_evaluation.types import (
    FunctionalEvaluationStatus,
    ModuleFunctionalEvaluationResult,
    PerturbationEffectRecord,
)

#: A deliberately large, finite stand-in for "no internal responsiveness to normalize
#: against, but a real external/spillover effect was measured anyway" -- never ``Decimal
#: ("Infinity")`` (which would propagate uncontrollably through later arithmetic); large
#: enough that ``1 / (1 + ratio)`` is indistinguishable from ``0`` at this policy's own
#: precision.
_UNNORMALIZABLE_RATIO = Decimal(1000)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal(0)) / Decimal(len(values))


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """``numerator / denominator``, never raising for a zero denominator: a zero numerator
    alongside a zero denominator is trivially "no relative effect" (ratio ``0``); a nonzero
    numerator alongside a zero denominator (the module did not respond to its own
    perturbations at all, yet something elsewhere did) is reported as ``_UNNORMALIZABLE_
    RATIO``, never a fabricated/undefined value."""
    if denominator > 0:
        return numerator / denominator
    return Decimal(0) if numerator == 0 else _UNNORMALIZABLE_RATIO


def _usable_effects(
    effects: tuple[PerturbationEffectRecord, ...], *, is_internal: bool
) -> list[PerturbationEffectRecord]:
    return [
        e
        for e in effects
        if e.is_internal == is_internal
        and e.remained_numerically_stable
        and e.relative_change_by_species
    ]


def _mean_over_species(
    effect: PerturbationEffectRecord, species_ids: frozenset[str]
) -> Decimal | None:
    values = [v for sid, v in effect.relative_change_by_species if sid in species_ids]
    return _mean(values)


def _dynamic_isolation_for_module(
    result: ModuleFunctionalEvaluationResult,
    internal_species_ids: frozenset[str],
    boundary_species_ids: frozenset[str],
) -> tuple[Decimal, Decimal, Decimal, Decimal | None] | None:
    """``(score, spillover_ratio, external_dependence_ratio, boundary_capture_fraction)`` for
    one module, or ``None`` when unavailable (status not ``EVALUATED``, or too few usable
    internal/external perturbations to compute a meaningful signal)."""
    if result.status is not FunctionalEvaluationStatus.EVALUATED:
        return None
    internal_effects = _usable_effects(result.perturbation_effects, is_internal=True)
    external_effects = _usable_effects(result.perturbation_effects, is_internal=False)
    if not internal_effects or not external_effects:
        return None

    measured_species = {
        sid for e in result.perturbation_effects for sid, _ in e.relative_change_by_species
    }
    external_species_ids = frozenset(measured_species) - internal_species_ids

    internal_to_internal = _mean(
        [
            v
            for e in internal_effects
            if (v := _mean_over_species(e, internal_species_ids)) is not None
        ]
    )
    if internal_to_internal is None:
        return None
    external_to_internal = _mean(
        [
            v
            for e in internal_effects
            if (v := _mean_over_species(e, external_species_ids)) is not None
        ]
    ) or Decimal(0)

    internal_to_external = _mean(
        [
            v
            for e in external_effects
            if (v := _mean_over_species(e, internal_species_ids)) is not None
        ]
    )
    if internal_to_external is None:
        return None

    boundary_capture_fraction: Decimal | None = None
    if boundary_species_ids:
        non_boundary_species_ids = internal_species_ids - boundary_species_ids
        boundary_response = _mean(
            [
                v
                for e in external_effects
                if (v := _mean_over_species(e, boundary_species_ids)) is not None
            ]
        ) or Decimal(0)
        non_boundary_response = (
            _mean(
                [
                    v
                    for e in external_effects
                    if (v := _mean_over_species(e, non_boundary_species_ids)) is not None
                ]
            )
            or Decimal(0)
            if non_boundary_species_ids
            else Decimal(0)
        )
        total = boundary_response + non_boundary_response
        boundary_capture_fraction = (boundary_response / total) if total > 0 else Decimal(1)

    spillover_ratio = _safe_ratio(external_to_internal, internal_to_internal)
    external_dependence_ratio = _safe_ratio(internal_to_external, internal_to_internal)

    sub_scores = [
        Decimal(1) / (Decimal(1) + spillover_ratio),
        Decimal(1) / (Decimal(1) + external_dependence_ratio),
    ]
    if boundary_capture_fraction is not None:
        sub_scores.append(boundary_capture_fraction)
    score = _mean(sub_scores)
    assert score is not None  # sub_scores is never empty
    return score, spillover_ratio, external_dependence_ratio, boundary_capture_fraction


def score_dynamic_isolation(
    module_ids: tuple[str, ...],
    evidence: Mapping[str, ModuleFunctionalEvaluationResult],
    internal_species_by_module: Mapping[str, frozenset[str]],
    boundary_species_by_module: Mapping[str, frozenset[str]],
) -> CriterionResult:
    """Aggregate ``module_ids``' own ``ModuleFunctionalEvaluationResult``s into one
    ``DYNAMIC_ISOLATION`` result for a modularization -- ``available=True`` only when every
    module has usable evidence; ``raw_score`` is then the unweighted mean of each module's own
    ``[0, 1]`` isolation score."""
    if not module_ids:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "modularization has no modules at all -- DYNAMIC_ISOLATION requires at least one"
            ),
            detail=DynamicIsolationDetail(),
        )

    per_module_scores: list[tuple[str, Decimal]] = []
    per_module_spillover: list[tuple[str, Decimal]] = []
    per_module_dependence: list[tuple[str, Decimal]] = []
    per_module_capture: list[tuple[str, Decimal]] = []
    with_evidence: list[str] = []
    missing: list[str] = []
    for module_id in module_ids:
        result = evidence.get(module_id)
        if result is None:
            missing.append(module_id)
            continue
        computed = _dynamic_isolation_for_module(
            result,
            internal_species_by_module.get(module_id, frozenset()),
            boundary_species_by_module.get(module_id, frozenset()),
        )
        if computed is None:
            missing.append(module_id)
            continue
        score, spillover, dependence, capture = computed
        with_evidence.append(module_id)
        per_module_scores.append((module_id, score))
        per_module_spillover.append((module_id, spillover))
        per_module_dependence.append((module_id, dependence))
        if capture is not None:
            per_module_capture.append((module_id, capture))

    detail = DynamicIsolationDetail(
        module_ids_with_evidence=tuple(sorted(with_evidence)),
        module_ids_missing_evidence=tuple(sorted(missing)),
        per_module_scores=tuple(sorted(per_module_scores)),
        per_module_spillover_ratio=tuple(sorted(per_module_spillover)),
        per_module_external_dependence_ratio=tuple(sorted(per_module_dependence)),
        per_module_boundary_capture_fraction=tuple(sorted(per_module_capture)),
    )
    if missing:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                f"functional evaluation evidence unavailable for module(s) {sorted(missing)} "
                "-- DYNAMIC_ISOLATION requires every module of this modularization to have "
                "usable evidence, never a fabricated partial score"
            ),
            warnings=tuple(
                f"module {m!r}: no usable functional evaluation evidence" for m in missing
            ),
            detail=detail,
        )

    raw_score = sum((s for _, s in per_module_scores), Decimal(0)) / Decimal(len(per_module_scores))
    return CriterionResult(
        available=True,
        raw_score=raw_score,
        explanation=(
            f"mean dynamic-isolation score across {len(per_module_scores)} module(s), every "
            "one with usable functional evaluation evidence"
        ),
        detail=detail,
    )


def _cosine_similarity(
    a: dict[str, Decimal], b: dict[str, Decimal], basis: tuple[str, ...]
) -> Decimal:
    """Cosine similarity of two per-species relative-change profiles, projected onto a fixed
    ``basis`` (species not present in a profile contribute ``0``). Every component is already
    a non-negative magnitude (``abs()`` of a relative change), so the result is always in
    ``[0, 1]`` -- never negative, never requiring a separate clamp. ``0`` (never a division
    error) when either profile has zero magnitude over ``basis`` -- a module with no measured
    response at all has no "shape" to compare, treated as dissimilar to everything, never
    fabricated as similar."""
    va = [a.get(s, Decimal(0)) for s in basis]
    vb = [b.get(s, Decimal(0)) for s in basis]
    dot = sum((x * y for x, y in zip(va, vb, strict=True)), Decimal(0))
    norm_a = sum((x * x for x in va), Decimal(0)).sqrt()
    norm_b = sum((x * x for x in vb), Decimal(0)).sqrt()
    if norm_a == 0 or norm_b == 0:
        return Decimal(0)
    return dot / (norm_a * norm_b)


def _sensitivity_coherence_for_module(
    result: ModuleFunctionalEvaluationResult, internal_species_ids: frozenset[str]
) -> tuple[Decimal, Decimal, Decimal] | None:
    """``(score, within_module_coherence, across_boundary_coherence)`` for one module, or
    ``None`` when unavailable: needs at least two usable internal-target perturbations (a
    "similarity between profiles" requires at least two profiles) and at least one usable
    external-target perturbation."""
    if result.status is not FunctionalEvaluationStatus.EVALUATED:
        return None
    if not internal_species_ids:
        return None
    internal_effects = _usable_effects(result.perturbation_effects, is_internal=True)
    external_effects = _usable_effects(result.perturbation_effects, is_internal=False)
    if len(internal_effects) < 2 or not external_effects:
        return None

    all_species = tuple(
        sorted(
            {sid for e in result.perturbation_effects for sid, _ in e.relative_change_by_species}
        )
    )
    internal_basis = tuple(sorted(internal_species_ids))
    profiles_internal = [dict(e.relative_change_by_species) for e in internal_effects]
    profiles_external = [dict(e.relative_change_by_species) for e in external_effects]

    within_pairs = [
        _cosine_similarity(profiles_internal[i], profiles_internal[j], internal_basis)
        for i in range(len(profiles_internal))
        for j in range(i + 1, len(profiles_internal))
    ]
    within_module_coherence = _mean(within_pairs)
    if within_module_coherence is None:
        return None

    across_pairs = [
        _cosine_similarity(p_int, p_ext, all_species)
        for p_int in profiles_internal
        for p_ext in profiles_external
    ]
    across_boundary_coherence = _mean(across_pairs)
    if across_boundary_coherence is None:
        return None

    score = within_module_coherence * (Decimal(1) - across_boundary_coherence)
    return score, within_module_coherence, across_boundary_coherence


def score_sensitivity_coherence(
    module_ids: tuple[str, ...],
    evidence: Mapping[str, ModuleFunctionalEvaluationResult],
    internal_species_by_module: Mapping[str, frozenset[str]],
) -> CriterionResult:
    """Aggregate ``module_ids``' own ``ModuleFunctionalEvaluationResult``s into one
    ``SENSITIVITY_COHERENCE`` result for a modularization -- identical availability/
    aggregation discipline to ``score_dynamic_isolation`` above."""
    if not module_ids:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "modularization has no modules at all -- SENSITIVITY_COHERENCE requires at "
                "least one"
            ),
            detail=SensitivityCoherenceDetail(),
        )

    per_module_scores: list[tuple[str, Decimal]] = []
    per_module_within: list[tuple[str, Decimal]] = []
    per_module_across: list[tuple[str, Decimal]] = []
    with_evidence: list[str] = []
    missing: list[str] = []
    for module_id in module_ids:
        result = evidence.get(module_id)
        if result is None:
            missing.append(module_id)
            continue
        computed = _sensitivity_coherence_for_module(
            result, internal_species_by_module.get(module_id, frozenset())
        )
        if computed is None:
            missing.append(module_id)
            continue
        score, within, across = computed
        with_evidence.append(module_id)
        per_module_scores.append((module_id, score))
        per_module_within.append((module_id, within))
        per_module_across.append((module_id, across))

    detail = SensitivityCoherenceDetail(
        module_ids_with_evidence=tuple(sorted(with_evidence)),
        module_ids_missing_evidence=tuple(sorted(missing)),
        per_module_scores=tuple(sorted(per_module_scores)),
        per_module_within_module_coherence=tuple(sorted(per_module_within)),
        per_module_across_boundary_coherence=tuple(sorted(per_module_across)),
    )
    if missing:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                f"functional evaluation evidence unavailable for module(s) {sorted(missing)} "
                "-- SENSITIVITY_COHERENCE requires every module of this modularization to "
                "have usable evidence, never a fabricated partial score"
            ),
            warnings=tuple(
                f"module {m!r}: no usable functional evaluation evidence" for m in missing
            ),
            detail=detail,
        )

    raw_score = sum((s for _, s in per_module_scores), Decimal(0)) / Decimal(len(per_module_scores))
    return CriterionResult(
        available=True,
        raw_score=raw_score,
        explanation=(
            f"mean sensitivity-coherence score across {len(per_module_scores)} module(s), "
            "every one with usable functional evaluation evidence"
        ),
        detail=detail,
    )


__all__ = ["score_dynamic_isolation", "score_sensitivity_coherence"]
