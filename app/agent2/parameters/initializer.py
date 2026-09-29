"""Curated-value initialization policy for one already-decided parameter slot (Increment 5;
extended by the Heuristic Simulation Parameter Initialization increment; extended again by
the Multi-Measurement Kinetic Evidence Consolidation and Prioritization increment).

``initialize_from_evidence`` resolves a parameter slot from real experimental measurements
only. ``initialize_from_ai_predicted_evidence`` applies the same consolidation policy to
GotEnzymes2-sourced measurements' own canonical values, one precedence rung below.
``initialize_with_fallback`` (this module's public entry point) tries experimental evidence,
then AI-predicted evidence, then a centralized heuristic default -- see
``app.agent2.parameters.heuristic_defaults``.

Multiple candidate measurements for the same slot no longer collapse to a plain
``PLACEHOLDER`` merely because they disagree numerically (Multi-Measurement Kinetic
Evidence Consolidation and Prioritization increment): they consolidate into one concept
(``app.agent2.kinetics.evidence_consolidation``) and, when the concept is not
``CONTEXT_DISTINCT``/``UNRESOLVED``, the single most biologically relevant measurement is
selected -- never averaged, never chosen nondeterministically -- while every candidate's id
is preserved in ``provenance_refs``. See `docs/08_parameter_declaration_initialization.md`
§6/§10-13/§14 and this module's own function docstrings below.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.agent2.kinetics.evidence_consolidation import (
    ConsolidationClassification,
    consolidate_by_substrate,
    publication_years_for_network,
    reference_experimental_context_for_network,
)
from app.agent2.parameters.heuristic_defaults import ParameterKind, heuristic_default_for_kind
from app.agent2.types import CuratedKineticMeasurement, FullNetwork, ParameterSource
from app.agent2.version import HEURISTIC_INITIALIZATION_POLICY_VERSION

#: Agent 1's own provenance marker for a GotEnzymes2-sourced measurement
#: (``app.models.enums.SourceType.GOTENZYMES`` on Agent 1's side; carried through the
#: handoff verbatim as this plain string on ``CuratedKineticMeasurement.source``). Compared
#: as a literal string, never an enum member -- ``CuratedKineticMeasurement.source`` is
#: Agent 1's own free-text field on this side of the handoff, exactly like
#: ``.parameter_type`` (see ``app.agent2.parameters.policy``'s own module docstring for the
#: identical reasoning).
_GOTENZYMES_SOURCE_LABEL = "GOTENZYMES"


@dataclass(frozen=True, slots=True)
class Initialization:
    """One parameter slot's resolved source/value/unit/provenance -- not yet a full
    `ParameterSpecification` (identity/name are decided by `builder.py`)."""

    source: ParameterSource
    value: Decimal | None
    unit: str | None
    source_reference: str | None
    provenance_refs: tuple[str, ...]
    uncertainty_text: str | None


_NO_MATCH = Initialization(
    source=ParameterSource.PLACEHOLDER,
    value=None,
    unit=None,
    source_reference=None,
    provenance_refs=(),
    uncertainty_text=(
        "No curated measurement matches this parameter; requires calibration."
    ),
)


def initialize_from_evidence(
    evidence_of_kind: tuple[CuratedKineticMeasurement, ...],
    *,
    network: FullNetwork | None = None,
) -> Initialization:
    """Resolve one parameter slot from the *experimental* curated measurements that match
    its recognized kind -- GotEnzymes2-sourced (AI-predicted) measurements are excluded here
    unconditionally (Heuristic Simulation Parameter Initialization increment) and considered
    separately, at lower precedence, by ``initialize_from_ai_predicted_evidence``: an
    AI-predicted value must never be represented as ``CURATED``/``LITERATURE_DERIVED``,
    which is exactly what would happen here (this function's own pre-existing rule already
    assigns ``CURATED`` to any agreeing evidence with no ``publication_id`` -- true of every
    real GotEnzymes2 measurement) without this exclusion.

    The remaining candidates consolidate (``app.agent2.kinetics.evidence_consolidation
    .consolidate_by_substrate``) by substrate/compound identity, then within one resulting
    concept:

    * **No matching measurement** -- ``PLACEHOLDER``, ``value=None``.
    * **Two or more different substrate/compound concepts** -- never merged into one slot
      (a genuinely multi-substrate ambiguity this function does not attempt to resolve) --
      ``PLACEHOLDER``, ``value=None``, every candidate id preserved.
    * **The one concept is ``CONTEXT_DISTINCT``/``UNRESOLVED``** (a real, confirmed
      biological-identity conflict, or no candidate compatible with the target model
      context) -- ``PLACEHOLDER``, ``value=None``, every candidate id preserved,
      ``uncertainty_text`` discloses why.
    * **Otherwise** (``SINGLE``/``CORROBORATING``/``DISAGREEING`` -- multiple *agreeing or
      disagreeing but biologically compatible* measurements no longer force
      ``PLACEHOLDER`` on their own, Multi-Measurement Kinetic Evidence Consolidation and
      Prioritization increment) -- the single most biologically relevant candidate's
      value/unit are used verbatim (never rounded, never converted, never averaged);
      ``ParameterSource.LITERATURE_DERIVED`` if that candidate names a ``publication_id``,
      else ``ParameterSource.CURATED``; ``provenance_refs`` names every candidate's id,
      not only the selected one; ``uncertainty_text`` discloses the disagreement and
      selection reason whenever the concept is ``DISAGREEING`` (``None`` for
      ``SINGLE``/``CORROBORATING``, exactly as before this increment).

    ``network`` is optional (defaulted to ``None`` for full backward compatibility) and
    supplies the target organism and reference experimental context consolidation's own
    Priority 1/2 use; without it, every candidate resolves through the identical priority
    order with no organism filtering and ``CONDITIONS_UNKNOWN`` throughout, degrading
    gracefully to the deterministic tie-break.

    Never assigns ``ParameterSource.DEFAULT`` (see
    `docs/08_parameter_declaration_initialization.md` §7 for why -- no
    conventional default value is established anywhere in this codebase
    to assign deterministically) or ``ParameterSource.CALIBRATED`` (Step 9:
    "reserve exclusively for future Agent 4").
    """
    evidence_of_kind = tuple(
        m for m in evidence_of_kind if m.source != _GOTENZYMES_SOURCE_LABEL
    )
    if not evidence_of_kind:
        return _NO_MATCH

    target_organism_id = network.organism_id if network is not None else None
    reference_context = (
        reference_experimental_context_for_network(network) if network is not None else None
    )
    publication_years = publication_years_for_network(network) if network is not None else {}
    concepts = consolidate_by_substrate(
        evidence_of_kind,
        target_organism_id=target_organism_id,
        reference_context=reference_context,
        publication_years=publication_years,
    )

    all_candidate_ids = tuple(sorted(m.id for m in evidence_of_kind))
    if len(concepts) != 1:
        return Initialization(
            source=ParameterSource.PLACEHOLDER,
            value=None,
            unit=None,
            source_reference=None,
            provenance_refs=all_candidate_ids,
            uncertainty_text=(
                f"{len(evidence_of_kind)} curated measurements match this parameter but name "
                f"{len(concepts)} different substrate/compound identities; no single kinetic "
                "concept was chosen. Requires calibration."
            ),
        )

    concept = concepts[0]
    if concept.selected_measurement_id is None:
        return Initialization(
            source=ParameterSource.PLACEHOLDER,
            value=None,
            unit=None,
            source_reference=None,
            provenance_refs=concept.measurement_ids,
            uncertainty_text=f"{concept.selection_reason} Requires calibration.",
        )

    selected = next(m for m in evidence_of_kind if m.id == concept.selected_measurement_id)
    source = (
        ParameterSource.LITERATURE_DERIVED
        if selected.publication_id is not None
        else ParameterSource.CURATED
    )
    source_reference = selected.publication_id or selected.source_id or selected.source
    uncertainty_text = (
        f"{concept.selection_reason} Requires calibration."
        if concept.classification is ConsolidationClassification.DISAGREEING
        else None
    )
    return Initialization(
        source=source,
        value=selected.value,
        unit=selected.unit,
        source_reference=source_reference,
        provenance_refs=concept.measurement_ids,
        uncertainty_text=uncertainty_text,
    )


def _normalized_value_unit(m: CuratedKineticMeasurement) -> tuple[Decimal | None, str | None]:
    return (m.normalized_value, m.normalized_unit)


def initialize_from_ai_predicted_evidence(
    evidence_of_kind: tuple[CuratedKineticMeasurement, ...],
    *,
    network: FullNetwork | None = None,
) -> Initialization:
    """Resolve one parameter slot from GotEnzymes2-sourced (AI-predicted) measurements only,
    at the precedence rung directly below ``initialize_from_evidence``'s own
    ``LITERATURE_DERIVED``/``CURATED`` (Heuristic Simulation Parameter Initialization
    increment).

    Uses each candidate's own **canonical** ``normalized_value``/``.normalized_unit``
    (Agent 1.x Increment C.12), never the raw, source-specific reported figure -- a
    deliberate choice distinct from ``initialize_from_evidence``'s own policy: an
    AI-predicted value is never a human-authored, source-attributed report the way a
    literature figure is, so there is no "as-reported" figure worth preserving verbatim
    over the canonical one the way there is for a real experimental measurement. A
    candidate with no resolved canonical value (Agent 1 itself could not convert its unit)
    is excluded entirely -- never falls back to its own raw value.

    Mirrors ``initialize_from_evidence``'s own consolidation policy exactly, one level
    down, comparing/ranking on the canonical value/unit instead of the raw one: no
    candidates -- ``PLACEHOLDER``, ``value=None``; a single consolidated concept that is
    not ``CONTEXT_DISTINCT``/``UNRESOLVED`` -- ``ParameterSource.AI_PREDICTED`` using the
    selected candidate's canonical value (multiple agreeing *or* disagreeing but
    biologically compatible candidates no longer force ``PLACEHOLDER`` on their own,
    Multi-Measurement Kinetic Evidence Consolidation and Prioritization increment); every
    candidate id is always preserved in ``provenance_refs``.
    """
    candidates = tuple(
        m
        for m in evidence_of_kind
        if m.source == _GOTENZYMES_SOURCE_LABEL and m.normalized_value is not None
    )
    if not candidates:
        return _NO_MATCH

    target_organism_id = network.organism_id if network is not None else None
    reference_context = (
        reference_experimental_context_for_network(network) if network is not None else None
    )
    publication_years = publication_years_for_network(network) if network is not None else {}
    concepts = consolidate_by_substrate(
        candidates,
        target_organism_id=target_organism_id,
        reference_context=reference_context,
        publication_years=publication_years,
        value_of=_normalized_value_unit,
    )

    all_candidate_ids = tuple(sorted(m.id for m in candidates))
    base_note = "AI-predicted by GotEnzymes2 -- never a curated experimental measurement."
    if len(concepts) != 1:
        return Initialization(
            source=ParameterSource.PLACEHOLDER,
            value=None,
            unit=None,
            source_reference=None,
            provenance_refs=all_candidate_ids,
            uncertainty_text=(
                f"{base_note} {len(candidates)} GotEnzymes2 AI-predicted measurements match "
                f"this parameter but name {len(concepts)} different substrate/compound "
                "identities; no single kinetic concept was chosen. Requires calibration."
            ),
        )

    concept = concepts[0]
    if concept.selected_measurement_id is None:
        return Initialization(
            source=ParameterSource.PLACEHOLDER,
            value=None,
            unit=None,
            source_reference=None,
            provenance_refs=concept.measurement_ids,
            uncertainty_text=f"{base_note} {concept.selection_reason} Requires calibration.",
        )

    selected = next(m for m in candidates if m.id == concept.selected_measurement_id)
    uncertainty_text = (
        f"{base_note} {concept.selection_reason} Requires calibration."
        if concept.classification is ConsolidationClassification.DISAGREEING
        else f"{base_note} Requires calibration."
    )
    return Initialization(
        source=ParameterSource.AI_PREDICTED,
        value=selected.normalized_value,
        unit=selected.normalized_unit,
        source_reference=selected.source_id or selected.source,
        provenance_refs=concept.measurement_ids,
        uncertainty_text=uncertainty_text,
    )


def initialize_with_fallback(
    evidence_of_kind: tuple[CuratedKineticMeasurement, ...],
    *,
    kind: ParameterKind,
    molecularity: int | None = None,
    macro_reconstruction: Initialization | None = None,
    network: FullNetwork | None = None,
) -> Initialization:
    """The full precedence a parameter slot resolves through: ``LITERATURE_DERIVED``/
    ``CURATED`` > ``AI_PREDICTED`` > ``DERIVED_FROM_MACRO_KINETICS`` >
    ``HEURISTIC_INITIALIZATION`` > ``PLACEHOLDER`` (Heuristic Simulation Parameter
    Initialization increment for the first two rungs below the top; Identifiability-Aware
    Macroscopic-to-Microscopic Kinetic Reconstruction increment for
    ``DERIVED_FROM_MACRO_KINETICS``).

    **A tier is only ever consulted when the previous tier found a genuine, complete
    absence of matching evidence** -- never when real evidence exists but disagrees.
    Disagreeing evidence (real measurements that conflict) is strictly more informative
    than no evidence at all, and is never silently discarded in favor of a lower-precedence
    guess: its own disclosed ``PLACEHOLDER`` (with every conflicting candidate's id in
    ``provenance_refs``) is the final word for that slot, exactly as
    ``initialize_from_evidence``'s own original Increment 5 policy already established for
    experimental evidence -- every lower tier extends the identical principle.

    ``macro_reconstruction`` is an already-computed ``Initialization`` (typically from
    ``app.agent2.parameters.reconstruction``, e.g.
    ``reconstruct_kcat_from_vmax_and_concentration``) the *caller* is responsible for
    building -- this function never computes a reconstruction itself, mirroring how it
    never computes a heuristic default itself beyond calling
    ``heuristic_default_for_kind``. Consulted only when both evidence tiers above it found
    a genuine, complete absence of matching evidence (identical "genuine absence only"
    rule) -- never when real curated/AI-predicted evidence exists but disagrees.
    Defaulted to ``None`` for full backward compatibility: every existing call site that
    does not pass it continues to resolve through exactly the same three tiers as before
    this increment.

    ``kind``/``molecularity`` select the centralized heuristic default
    (``app.agent2.parameters.heuristic_defaults.heuristic_default_for_kind``) -- when that
    returns ``None`` (a parameter kind this increment's own policy does not support, e.g. a
    Hill coefficient or an equilibrium constant), the plain, no-evidence-at-all
    ``PLACEHOLDER`` from the experimental tier is returned unchanged, never an invented
    convention for an unsupported kind.
    """
    experimental = initialize_from_evidence(evidence_of_kind, network=network)
    if experimental.source is not ParameterSource.PLACEHOLDER or experimental.provenance_refs:
        return experimental

    ai_predicted = initialize_from_ai_predicted_evidence(evidence_of_kind, network=network)
    if ai_predicted.source is not ParameterSource.PLACEHOLDER or ai_predicted.provenance_refs:
        return ai_predicted

    if macro_reconstruction is not None:
        return macro_reconstruction

    default = heuristic_default_for_kind(kind, molecularity=molecularity)
    if default is None:
        return experimental

    return Initialization(
        source=ParameterSource.HEURISTIC_INITIALIZATION,
        value=default.value,
        unit=default.unit,
        source_reference=f"heuristic-initialization-policy::{HEURISTIC_INITIALIZATION_POLICY_VERSION}",
        provenance_refs=(),
        uncertainty_text=(
            f"No experimental or AI-predicted evidence exists for this parameter; "
            f"heuristically initialized to a numerically well-behaved starting value "
            f"({default.value} {default.unit}) for simulation purposes only -- never a "
            "biochemical claim of any kind. Requires calibration."
        ),
    )


__all__ = [
    "Initialization",
    "initialize_from_ai_predicted_evidence",
    "initialize_from_evidence",
    "initialize_with_fallback",
]
