"""Boundary-id construction, categorical likelihood combination, parameter-basis, and
explanation-text policy (Increment 6).

`combine_outcomes` is the one function that turns a candidate's
individual `RuleOutcome`s into a final `BoundaryLikelihood` -- an
explicit, fully-enumerated categorical decision table (Increment 6
instructions, Step 28), never a hidden numeric weighted sum. See
``docs/09_heuristic_boundary_assessment.md`` §10 for the full documented
rationale behind each branch.
"""

from __future__ import annotations

from app.agent2.boundaries.types import RuleDirection, RuleOutcome, RuleStrength
from app.agent2.types import BoundaryLikelihood, BoundaryParameterBasis, ParameterSource

_BOUNDARY_ID_SEPARATOR = "::"


def build_boundary_id(upstream_reaction_id: str, downstream_reaction_id: str) -> str:
    """Deterministic ``boundary_id``, a pure function of the two reaction ids it connects.

    Never a random UUID; independent of candidate-discovery order (built
    directly from the two ids, never from an iteration index). Adapted
    from the instructions' own illustrative ``boundary:R1:S3:R2`` format
    -- the middle species slug is dropped since one candidate may carry
    several shared species (`shared_species_ids` is itself a tuple), so
    embedding just one in the id would be arbitrary and misleading; the
    ordered reaction-id pair alone already uniquely identifies one
    candidate under this package's one-candidate-per-ordered-pair
    generation policy (`assessor.py`).
    """
    sep = _BOUNDARY_ID_SEPARATOR
    return f"boundary{sep}{upstream_reaction_id}{sep}{downstream_reaction_id}"


def combine_outcomes(outcomes: tuple[RuleOutcome, ...]) -> BoundaryLikelihood:
    """Combine every rule's outcome for one candidate into one qualitative likelihood.

    Fully categorical, fully enumerated -- no numeric score is ever
    computed or compared against a hidden threshold. Reads as a strict,
    ordered if/elif chain; the first branch whose condition holds wins:

    1. No supporting evidence at all, and at least one ``STRONG``
       opposing signal -> ``VERY_LOW``.
    2. No supporting evidence at all (any weaker opposition, or none) ->
       ``LOW`` -- the conservative default for a "weakly connected
       interface": never assume a boundary merely because nothing else
       was said about it.
    3. **(Increment 6 pre-commit revision)** At least one ``STRONG``
       supporting signal, and no ``MODERATE``-or-stronger opposition ->
       ``VERY_HIGH``. Under the current rule catalog (`rules.py`),
       ``STRONG`` support is reachable *only* through
       `irreversible_output_isolation` -- every structural proxy is
       capped at `MODERATE`, the parameterization-convenience rules are
       permanently `NEUTRAL`, `shared_catalyst_coupling` is an opposing
       rule capped at `MODERATE`, `intrinsic_feedback_isolation` is now
       an *opposing* rule (Increment 6 feedback-heuristic revision -- see
       ``docs/09_heuristic_boundary_assessment.md``, "Nested Feedback
       Loops"), and `extrinsic_feedback_crossing` always returns
       `NEUTRAL`. This is the deliberate fix for the pre-revision
       behavior, where ``VERY_HIGH`` could be reached by merely
       accumulating several structural discontinuities (e.g. transport +
       compartment transition) with no genuine evidence of functional
       isolation. ``VERY_HIGH`` now requires convincing isolation
       evidence and no meaningful opposition -- never mere structural
       accumulation.
    4. At least one ``STRONG`` supporting signal (not already resolved to
       ``VERY_HIGH`` above because of ``MODERATE``-or-stronger
       opposition), or two-or-more ``MODERATE``-or-stronger supporting
       signals, and no ``STRONG`` opposition -> ``HIGH``.
    5. Supporting evidence exists but is weak, and there is
       ``MODERATE``-or-stronger opposition -> ``LOW``.
    6. Anything else with at least one supporting signal (weak support
       alone with no opposition; or genuinely mixed support/opposition
       that did not already resolve to ``HIGH``/``VERY_HIGH``/``LOW``
       above) -> ``MEDIUM``.
    """
    supports = tuple(o for o in outcomes if o.direction is RuleDirection.SUPPORT)
    opposes = tuple(o for o in outcomes if o.direction is RuleDirection.OPPOSE)

    def _has(rules: tuple[RuleOutcome, ...], *strengths: RuleStrength) -> bool:
        return any(o.strength in strengths for o in rules)

    strong_support_count = sum(1 for o in supports if o.strength is RuleStrength.STRONG)
    moderate_or_higher_support_count = sum(
        1 for o in supports if o.strength in (RuleStrength.MODERATE, RuleStrength.STRONG)
    )
    has_strong_oppose = _has(opposes, RuleStrength.STRONG)
    has_moderate_or_higher_oppose = _has(opposes, RuleStrength.MODERATE, RuleStrength.STRONG)

    if not supports:
        return BoundaryLikelihood.VERY_LOW if has_strong_oppose else BoundaryLikelihood.LOW

    if strong_support_count >= 1 and not has_moderate_or_higher_oppose:
        return BoundaryLikelihood.VERY_HIGH

    enough_moderate_support = strong_support_count >= 1 or moderate_or_higher_support_count >= 2
    if enough_moderate_support and not has_strong_oppose:
        return BoundaryLikelihood.HIGH

    only_weak_support = moderate_or_higher_support_count == 0
    if only_weak_support and has_moderate_or_higher_oppose:
        return BoundaryLikelihood.LOW

    return BoundaryLikelihood.MEDIUM


def compute_parameter_basis(
    parameter_sources: tuple[ParameterSource, ...],
) -> BoundaryParameterBasis:
    """Qualitative disclosure of what kind of parameter evidence informed this boundary.

    A structural summary of the *set* of `ParameterSource` values
    actually involved -- never a numeric confidence (Increment 6
    instructions, Step 34).
    """
    if not parameter_sources:
        return BoundaryParameterBasis.NONE
    distinct = set(parameter_sources)
    if distinct == {ParameterSource.PLACEHOLDER}:
        return BoundaryParameterBasis.PLACEHOLDER_ONLY
    if distinct == {ParameterSource.DEFAULT}:
        return BoundaryParameterBasis.DEFAULT_ONLY
    if distinct == {ParameterSource.CALIBRATED}:
        return BoundaryParameterBasis.CALIBRATED
    if distinct <= {ParameterSource.CURATED, ParameterSource.LITERATURE_DERIVED}:
        return BoundaryParameterBasis.CURATED_OR_LITERATURE
    return BoundaryParameterBasis.MIXED


def build_explanation(
    *,
    likelihood: BoundaryLikelihood,
    supports: tuple[RuleOutcome, ...],
    opposes: tuple[RuleOutcome, ...],
    parameter_basis: BoundaryParameterBasis,
) -> str:
    """Deterministic, template-based explanation text -- no LLM, no prose speculation.

    Lists every firing supporting/opposing reason code by name (sorted
    for determinism) and closes with a factual parameter-evidence note.
    """
    sentences = [f"Boundary likelihood {likelihood.value}."]
    if supports:
        codes = ", ".join(sorted(o.reason_code.value for o in supports))
        sentences.append(f"Supporting evidence: {codes}.")
    else:
        sentences.append("No supporting evidence was found.")
    if opposes:
        codes = ", ".join(sorted(o.reason_code.value for o in opposes))
        sentences.append(f"Opposing evidence: {codes}.")
    else:
        sentences.append("No opposing evidence was found.")
    sentences.append(f"Parameter basis: {parameter_basis.value}.")
    return " ".join(sentences)


__all__ = [
    "build_boundary_id",
    "build_explanation",
    "combine_outcomes",
    "compute_parameter_basis",
]
