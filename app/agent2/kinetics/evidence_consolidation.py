"""Multi-Measurement Kinetic Evidence Consolidation and Prioritization.

Consolidation and selection are deliberately separate concerns (task Sec 5):

* **Consolidation** decides which curated measurements represent the *same* kinetic
  concept -- same reaction/catalyst context (the caller's own responsibility, never this
  module's), same recognized parameter kind (also the caller's), and the same substrate/
  compound identity (this module's own ``consolidate_by_substrate`` split) -- and
  classifies that concept as ``SINGLE``/``CORROBORATING``/``DISAGREEING``/
  ``CONTEXT_DISTINCT``/``UNRESOLVED``.
* **Selection** decides, for one already-consolidated concept, which single measurement
  is most biologically relevant to the target model context, by a fixed lexicographic
  priority order: biological identity, then experimental-condition similarity, then
  measurement completeness, then publication recency, then a deterministic tie-break.
  Evidence-class ranking (experimental/literature > AI-predicted) is deliberately **not**
  one of these priorities here -- it is already, and remains, enforced one level up by
  ``app.agent2.parameters.initializer`` never mixing GotEnzymes2-sourced (AI-predicted)
  candidates into the same pool as experimental ones (two entirely separate precedence
  tiers) -- folding it in here as well would risk a newer AI prediction ever
  outranking a suitable experimental measurement, which this package must never do.

Never averages, never fabricates missing experimental conditions, never invents a
canonical yeast physiological value: every priority either compares two *real*, already-
curated fields, or degrades to "no information" (``CONDITIONS_UNKNOWN``, an ignored
recency tier) when the data does not exist -- exactly the same discipline
``app.agent2.quantitative_context.policy.classify_context_compatibility`` already
established for cell-volume/abundance context matching, whose comparison this module
reuses unchanged for condition-matching rather than reimplementing a second, divergent
copy (the isozyme-context-resolution increment's own real lesson: two independent
reimplementations of the same comparison silently drift out of sync).

**Publication recency -- a disclosed, real data-availability gap.** The task asks this
priority to use the primary publication's own date/year, never a database-update or
connector-ingestion timestamp. Agent 1's real database has exactly that
(``Publication.year``), but Agent 1's own curated knowledge view handed to Agent 2 --
and therefore ``CuratedKineticMeasurement`` on this side of the handoff -- exposes only
an opaque ``publication_id`` string, never a year. This module never fabricates one.
``publication_years`` is accordingly an explicit, optional, caller-supplied
``{publication_id: year}`` mapping (default ``{}``, meaning "no information") -- every
real call site in this repository passes nothing today, so this tier always ties and
every real selection falls through to the final deterministic tie-break; the parameter
exists so the ranking is already correct and ready the day a future Agent 1 handoff
increment mirrors ``Publication.year`` across the boundary, without this module's own
logic needing to change at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agent2.quantitative_context.policy import classify_context_compatibility
from app.agent2.quantitative_context.types import ContextCompatibility
from app.agent2.types import CuratedExperimentalContext, CuratedKineticMeasurement, FullNetwork
from app.agent2.version import EVIDENCE_CONSOLIDATION_POLICY_VERSION

#: Agent 1's own curated classification string for a reference (never experiment-
#: specific) ``CuratedExperimentalContext`` -- transcribed from
#: ``app.agent2.quantitative_context``'s own established convention for this exact field
#: (that package's own module compares ``CuratedQuantitativeObservation.evidence_class``
#: strings the identical way; ``CuratedExperimentalContext.classification`` is Agent 1's
#: own plain string, never re-typed as an enum on this side of the handoff -- see that
#: type's own docstring).
_REFERENCE_CLASSIFICATION = "REFERENCE"

#: A ``(value, unit)`` extractor -- the raw, as-reported figure by default. Only
#: ``select_within_concept``'s own AI-predicted caller ever overrides this, to compare
#: canonical ``normalized_value``/``normalized_unit`` instead (mirrors
#: ``app.agent2.parameters.initializer.initialize_from_ai_predicted_evidence``'s own
#: pre-existing, unchanged canonical-value policy).
_ValueUnit = tuple[Decimal | None, str | None]
_ValueUnitExtractor = Callable[[CuratedKineticMeasurement], _ValueUnit]


def _raw_value_unit(m: CuratedKineticMeasurement) -> _ValueUnit:
    return (m.value, m.unit)


class ConsolidationClassification(StrEnum):
    """How one consolidated kinetic-parameter concept's own supporting measurements
    relate to each other -- never a judgement about whether the concept is *usable*
    (see ``ConsolidatedKineticConcept.selected_measurement_id``, which can be ``None``
    for any of these when Priority 1 identity filtering leaves nothing selectable)."""

    #: Exactly one measurement supports this concept.
    SINGLE = "SINGLE"
    #: Two or more measurements, all biologically compatible with each other, that
    #: report the identical value and unit.
    CORROBORATING = "CORROBORATING"
    #: Two or more measurements, all biologically compatible with each other, that
    #: report differing values -- real assay/biological variability, never treated as a
    #: reason to split into separate concepts (task Sec 4: "do not define DISAGREEING
    #: solely because values are unequal" is satisfied by CORROBORATING/DISAGREEING both
    #: being one concept; this classification exists precisely for the case that is
    #: *not* CONTEXT_DISTINCT).
    DISAGREEING = "DISAGREEING"
    #: Two or more measurements whose own biological identity (currently: organism)
    #: explicitly, confirmedly conflicts with each other -- never merged into a plain
    #: agree/disagree numeric verdict.
    CONTEXT_DISTINCT = "CONTEXT_DISTINCT"
    #: Two or more measurements exist, but every one of them explicitly conflicts with
    #: the *target* model context's own organism -- none is a usable candidate.
    UNRESOLVED = "UNRESOLVED"


class ConditionMatch(StrEnum):
    """Priority 2's own closed vocabulary for how closely one measurement's reported
    experimental conditions match the network's own reference context."""

    CANONICAL_CONDITIONS = "CANONICAL_CONDITIONS"
    NEAR_CANONICAL_CONDITIONS = "NEAR_CANONICAL_CONDITIONS"
    NONCANONICAL_CONDITIONS = "NONCANONICAL_CONDITIONS"
    CONDITIONS_UNKNOWN = "CONDITIONS_UNKNOWN"


_CONTEXT_COMPATIBILITY_TO_CONDITION_MATCH: dict[ContextCompatibility, ConditionMatch] = {
    ContextCompatibility.EXACT_CONTEXT: ConditionMatch.CANONICAL_CONDITIONS,
    ContextCompatibility.COMPATIBLE_REFERENCE: ConditionMatch.NEAR_CANONICAL_CONDITIONS,
    ContextCompatibility.CONTEXT_MISMATCH: ConditionMatch.NONCANONICAL_CONDITIONS,
    ContextCompatibility.CONTEXT_UNKNOWN: ConditionMatch.CONDITIONS_UNKNOWN,
}

_CONDITION_RANK: dict[ConditionMatch, int] = {
    ConditionMatch.CANONICAL_CONDITIONS: 0,
    ConditionMatch.NEAR_CANONICAL_CONDITIONS: 1,
    ConditionMatch.NONCANONICAL_CONDITIONS: 2,
    ConditionMatch.CONDITIONS_UNKNOWN: 3,
}


@dataclass(frozen=True, slots=True)
class ConsolidatedKineticConcept:
    """One kinetic-parameter concept: every measurement id sharing the same reaction/
    catalyst context and recognized parameter kind (both already narrowed by the caller
    before this module ever sees them) and the same substrate/compound identity.

    ``measurement_ids`` always names every contributing measurement, deterministically
    sorted -- never only the selected one (task Sec 8: "downstream source_measurement_ids
    must not lose supporting evidence"). ``selected_measurement_id`` is ``None`` exactly
    when ``classification`` is ``CONTEXT_DISTINCT`` or ``UNRESOLVED`` -- real biological
    ambiguity this module never resolves by guessing.
    """

    measurement_ids: tuple[str, ...]
    classification: ConsolidationClassification
    selected_measurement_id: str | None
    selection_reason: str
    policy_version: str


def reference_experimental_context_for_network(
    network: FullNetwork,
) -> CuratedExperimentalContext | None:
    """The network's own single ``REFERENCE``-classified ``CuratedExperimentalContext``
    for its own organism, or ``None`` -- never guessed at when zero or more than one
    candidate exists (this codebase's own established "ambiguous -> conservative"
    discipline, mirroring ``app.agent2.kinetics.reaction_context``'s "never choose among
    several").
    """
    candidates = tuple(
        ctx
        for ctx in network.experimental_contexts
        if ctx.classification == _REFERENCE_CLASSIFICATION
        and ctx.organism_id is not None
        and ctx.organism_id == network.organism_id
    )
    if len(candidates) != 1:
        return None
    return candidates[0]


def condition_match_for_measurement(
    measurement: CuratedKineticMeasurement,
    reference_context: CuratedExperimentalContext | None,
) -> ConditionMatch:
    """Priority 2: how closely ``measurement``'s own reported conditions (``strain``,
    ``temperature_c``, ``ph``) match ``reference_context``.

    Reuses ``classify_context_compatibility`` unchanged by wrapping this measurement's
    own condition fields in a synthetic, transient ``CuratedExperimentalContext`` limited
    to exactly the subset of fields ``CuratedKineticMeasurement`` itself carries (no
    ``medium``/``carbon_source``/``growth_phase``/``growth_condition`` -- Agent 2's own
    measurement type has no such fields, and this function never invents one). Never
    fabricates a canonical yeast temperature/pH: ``CONDITIONS_UNKNOWN`` whenever no real
    reference context is available, exactly mirroring
    ``classify_context_compatibility``'s own ``CONTEXT_UNKNOWN`` whenever either side is
    uninformative.
    """
    if reference_context is None:
        return ConditionMatch.CONDITIONS_UNKNOWN
    measurement_context = CuratedExperimentalContext(
        id=f"measurement-condition-view::{measurement.id}",
        organism_id=measurement.organism_id,
        strain=measurement.strain,
        temperature_c=measurement.temperature_c,
        ph=measurement.ph,
    )
    compatibility = classify_context_compatibility(measurement_context, reference_context)
    return _CONTEXT_COMPATIBILITY_TO_CONDITION_MATCH[compatibility]


def _completeness_score(m: CuratedKineticMeasurement) -> int:
    """Priority 4: count of populated, model-relevant descriptive fields. Presence only,
    never a judgement of a field's own value or magnitude -- ``value``/``unit`` (always
    required, so never discriminating) are deliberately excluded.
    """
    fields = (
        m.normalized_value,
        m.compound_id,
        m.temperature_c,
        m.ph,
        m.publication_id,
        m.confidence_score,
        m.confidence_class,
        m.reported_parameter_type,
    )
    return sum(1 for f in fields if f is not None)


def _publication_year(
    m: CuratedKineticMeasurement, publication_years: dict[str, int]
) -> int | None:
    if m.publication_id is None:
        return None
    return publication_years.get(m.publication_id)


def _organism_conflict(a: CuratedKineticMeasurement, b: CuratedKineticMeasurement) -> bool:
    """A real, confirmed organism conflict between two measurements already known (by the
    caller's own grouping) to share reaction/catalyst/parameter-kind/substrate identity --
    unknown (``None``) on either side never conflicts, mirroring
    ``classify_context_compatibility``'s own "unknown never disagrees" discipline exactly.
    """
    return (
        a.organism_id is not None
        and b.organism_id is not None
        and a.organism_id != b.organism_id
    )


def _has_internal_identity_conflict(measurements: tuple[CuratedKineticMeasurement, ...]) -> bool:
    return any(
        _organism_conflict(measurements[i], measurements[j])
        for i in range(len(measurements))
        for j in range(i + 1, len(measurements))
    )


def _target_incompatible(m: CuratedKineticMeasurement, *, target_organism_id: str | None) -> bool:
    """Priority 1: whether ``m`` is excluded from selection candidacy outright (task Sec
    3: "identity mismatch should usually exclude a measurement rather than merely lower
    its rank") -- a confirmed organism mismatch against the network's own target
    organism. Never excludes on an unknown (``None``) organism on either side -- a real
    absence of information, never treated as a confirmed conflict.
    """
    return (
        m.organism_id is not None
        and target_organism_id is not None
        and m.organism_id != target_organism_id
    )


def _select_best(
    candidates: tuple[CuratedKineticMeasurement, ...],
    *,
    reference_context: CuratedExperimentalContext | None,
    publication_years: dict[str, int],
) -> CuratedKineticMeasurement:
    """Priorities 2/4/5 plus the final deterministic tie-break, applied to a
    already-Priority-1-filtered candidate pool (Priority 1 itself is enforced by the
    caller before this function ever runs -- see ``consolidate_concept``).
    """

    def rank(m: CuratedKineticMeasurement) -> tuple:
        year = _publication_year(m, publication_years)
        recency_rank = (0, -year) if year is not None else (1, 0)
        return (
            _CONDITION_RANK[condition_match_for_measurement(m, reference_context)],
            -_completeness_score(m),
            recency_rank,
            m.source or "",
            m.source_id or "",
            m.id,
        )

    return min(candidates, key=rank)


def consolidate_concept(
    measurements: tuple[CuratedKineticMeasurement, ...],
    *,
    target_organism_id: str | None = None,
    reference_context: CuratedExperimentalContext | None = None,
    publication_years: dict[str, int] | None = None,
    value_of: _ValueUnitExtractor = _raw_value_unit,
) -> ConsolidatedKineticConcept:
    """Classify and (when possible) select a representative for one already-narrowed
    group of measurements -- the caller is responsible for having already restricted
    ``measurements`` to one reaction/catalyst context, one recognized parameter kind, and
    one substrate/compound identity (``consolidate_by_substrate`` performs that last
    split automatically; a caller with its own narrower context, e.g.
    ``app.agent2.kinetics.policy.find_substrate_anchored_km``, may call this directly).

    Never averages, never picks nondeterministically -- see the module docstring for the
    full priority order and this type's own ``ConsolidationClassification`` for what each
    outcome means.
    """
    if not measurements:
        raise ValueError("consolidate_concept requires at least one measurement")
    publication_years = publication_years or {}
    all_ids = tuple(sorted(m.id for m in measurements))

    if len(measurements) == 1:
        only = measurements[0]
        return ConsolidatedKineticConcept(
            measurement_ids=all_ids,
            classification=ConsolidationClassification.SINGLE,
            selected_measurement_id=only.id,
            selection_reason="Only one measurement supports this kinetic concept.",
            policy_version=EVIDENCE_CONSOLIDATION_POLICY_VERSION,
        )

    candidates = tuple(
        m
        for m in measurements
        if not _target_incompatible(m, target_organism_id=target_organism_id)
    )
    if not candidates:
        return ConsolidatedKineticConcept(
            measurement_ids=all_ids,
            classification=ConsolidationClassification.UNRESOLVED,
            selected_measurement_id=None,
            selection_reason=(
                "Every measurement supporting this concept explicitly reports an organism "
                "different from the target model context; none is a compatible candidate."
            ),
            policy_version=EVIDENCE_CONSOLIDATION_POLICY_VERSION,
        )

    if _has_internal_identity_conflict(measurements):
        return ConsolidatedKineticConcept(
            measurement_ids=all_ids,
            classification=ConsolidationClassification.CONTEXT_DISTINCT,
            selected_measurement_id=None,
            selection_reason=(
                "This concept's own supporting measurements report explicitly conflicting "
                "organism identity with each other; no single value was chosen across "
                "incompatible biological context."
            ),
            policy_version=EVIDENCE_CONSOLIDATION_POLICY_VERSION,
        )

    first_value_unit = value_of(candidates[0])
    agree = all(value_of(m) == first_value_unit for m in candidates[1:])
    selected = _select_best(
        candidates, reference_context=reference_context, publication_years=publication_years
    )
    condition = condition_match_for_measurement(selected, reference_context)
    if agree:
        return ConsolidatedKineticConcept(
            measurement_ids=all_ids,
            classification=ConsolidationClassification.CORROBORATING,
            selected_measurement_id=selected.id,
            selection_reason=(
                f"{len(candidates)} compatible measurement(s) agree on value and unit for "
                f"this concept; {selected.id} selected as the representative "
                f"(condition={condition.value})."
            ),
            policy_version=EVIDENCE_CONSOLIDATION_POLICY_VERSION,
        )
    return ConsolidatedKineticConcept(
        measurement_ids=all_ids,
        classification=ConsolidationClassification.DISAGREEING,
        selected_measurement_id=selected.id,
        selection_reason=(
            f"{len(candidates)} compatible measurement(s) support this concept but report "
            f"differing values; {selected.id} selected as the most biologically relevant "
            f"(condition={condition.value}); every candidate is preserved as supporting "
            "evidence -- no value was averaged or discarded."
        ),
        policy_version=EVIDENCE_CONSOLIDATION_POLICY_VERSION,
    )


def consolidate_by_substrate(
    evidence: tuple[CuratedKineticMeasurement, ...],
    *,
    target_organism_id: str | None = None,
    reference_context: CuratedExperimentalContext | None = None,
    publication_years: dict[str, int] | None = None,
    value_of: _ValueUnitExtractor = _raw_value_unit,
) -> tuple[ConsolidatedKineticConcept, ...]:
    """Splits already reaction/catalyst/kind-narrowed ``evidence`` further by
    ``compound_id`` (task Sec 2/6: never merge across different substrates -- including
    ``None``, "untagged", which is its own distinct concept, never assumed to be the same
    substrate as a tagged one) and consolidates each resulting group independently.

    Deterministically ordered: ``None`` (untagged) last, then every real compound id in
    sorted order -- never input-order-dependent.
    """
    by_compound: dict[str | None, list[CuratedKineticMeasurement]] = {}
    for m in evidence:
        by_compound.setdefault(m.compound_id, []).append(m)
    concepts = []
    for compound_id in sorted(by_compound, key=lambda c: (c is None, c or "")):
        concepts.append(
            consolidate_concept(
                tuple(by_compound[compound_id]),
                target_organism_id=target_organism_id,
                reference_context=reference_context,
                publication_years=publication_years,
                value_of=value_of,
            )
        )
    return tuple(concepts)


__all__ = [
    "ConditionMatch",
    "ConsolidatedKineticConcept",
    "ConsolidationClassification",
    "condition_match_for_measurement",
    "consolidate_by_substrate",
    "consolidate_concept",
    "reference_experimental_context_for_network",
]
