"""Curated-value initialization policy for one already-decided parameter slot (Increment 5;
extended by the Heuristic Simulation Parameter Initialization increment).

``initialize_from_evidence`` (Increment 5, unmodified in what it decides for non-GotEnzymes2
evidence) resolves a parameter slot from real experimental measurements only. This
increment adds ``initialize_from_ai_predicted_evidence`` (the same agreement policy, applied
to GotEnzymes2-sourced measurements' own canonical values) and ``initialize_with_fallback``
(this module's new public entry point: tries experimental evidence, then AI-predicted
evidence, then a centralized heuristic default -- see
``app.agent2.parameters.heuristic_defaults``). Never called with numeric comparison, unit
conversion, averaging, or ranking beyond exact-agreement checks -- see module-level policy
notes below and `docs/08_parameter_declaration_initialization.md` §6/§10-13/§14 (Heuristic
Simulation Parameter Initialization).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.agent2.parameters import policy
from app.agent2.parameters.heuristic_defaults import ParameterKind, heuristic_default_for_kind
from app.agent2.types import CuratedKineticMeasurement, ParameterSource
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
) -> Initialization:
    """Resolve one parameter slot from the *experimental* curated measurements that match
    its recognized kind -- GotEnzymes2-sourced (AI-predicted) measurements are excluded here
    unconditionally (Heuristic Simulation Parameter Initialization increment) and considered
    separately, at lower precedence, by ``initialize_from_ai_predicted_evidence``: an
    AI-predicted value must never be represented as ``CURATED``/``LITERATURE_DERIVED``,
    which is exactly what would happen here (this function's own pre-existing rule already
    assigns ``CURATED`` to any agreeing evidence with no ``publication_id`` -- true of every
    real GotEnzymes2 measurement) without this exclusion.

    * **No matching (non-AI-predicted) measurement** -- ``PLACEHOLDER``, ``value=None``.
    * **Every matching measurement agrees** (identical value *and* unit,
      exact comparison -- `policy.measurements_agree`) -- the value/unit
      are used verbatim (never rounded, never converted);
      ``ParameterSource.LITERATURE_DERIVED`` if the representative
      measurement (lowest ``id``, for determinism) names a
      ``publication_id``, else ``ParameterSource.CURATED``;
      ``provenance_refs`` names every agreeing measurement's id, not only
      the representative one (Increment 5 instructions, Step 11).
    * **Matching measurements disagree** (different value, or the same
      value in different units -- units are never normalized, so this
      counts as disagreement too) -- ``PLACEHOLDER``, ``value=None``,
      ``provenance_refs`` still names every candidate id (Step 12: "never
      average, never rank, never choose one silently... preserve all
      provenance").

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

    if not policy.measurements_agree(evidence_of_kind):
        candidate_ids = tuple(sorted(m.id for m in evidence_of_kind))
        return Initialization(
            source=ParameterSource.PLACEHOLDER,
            value=None,
            unit=None,
            source_reference=None,
            provenance_refs=candidate_ids,
            uncertainty_text=(
                f"{len(evidence_of_kind)} curated measurements match this parameter but report "
                "different values and/or units; no value was chosen. Requires calibration."
            ),
        )

    representative = sorted(evidence_of_kind, key=lambda m: m.id)[0]
    all_ids = tuple(sorted(m.id for m in evidence_of_kind))
    source = (
        ParameterSource.LITERATURE_DERIVED
        if representative.publication_id is not None
        else ParameterSource.CURATED
    )
    source_reference = (
        representative.publication_id or representative.source_id or representative.source
    )
    return Initialization(
        source=source,
        value=representative.value,
        unit=representative.unit,
        source_reference=source_reference,
        provenance_refs=all_ids,
        uncertainty_text=None,
    )


def initialize_from_ai_predicted_evidence(
    evidence_of_kind: tuple[CuratedKineticMeasurement, ...],
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

    Mirrors ``initialize_from_evidence``'s own agreement policy exactly, one level down:
    no candidates -- ``PLACEHOLDER``, ``value=None``; every candidate's canonical value/unit
    agrees -- ``ParameterSource.AI_PREDICTED``; candidates disagree -- ``PLACEHOLDER``,
    ``value=None``, every candidate id preserved in ``provenance_refs``.
    """
    candidates = tuple(
        m
        for m in evidence_of_kind
        if m.source == _GOTENZYMES_SOURCE_LABEL and m.normalized_value is not None
    )
    if not candidates:
        return _NO_MATCH

    first = candidates[0]
    agree = all(
        m.normalized_value == first.normalized_value and m.normalized_unit == first.normalized_unit
        for m in candidates[1:]
    )
    all_ids = tuple(sorted(m.id for m in candidates))
    if not agree:
        return Initialization(
            source=ParameterSource.PLACEHOLDER,
            value=None,
            unit=None,
            source_reference=None,
            provenance_refs=all_ids,
            uncertainty_text=(
                f"{len(candidates)} GotEnzymes2 AI-predicted measurements match this "
                "parameter but report different canonical values; no value was chosen. "
                "Requires calibration."
            ),
        )

    representative = sorted(candidates, key=lambda m: m.id)[0]
    return Initialization(
        source=ParameterSource.AI_PREDICTED,
        value=representative.normalized_value,
        unit=representative.normalized_unit,
        source_reference=representative.source_id or representative.source,
        provenance_refs=all_ids,
        uncertainty_text=(
            "AI-predicted by GotEnzymes2 -- never a curated experimental measurement. "
            "Requires calibration."
        ),
    )


def initialize_with_fallback(
    evidence_of_kind: tuple[CuratedKineticMeasurement, ...],
    *,
    kind: ParameterKind,
    molecularity: int | None = None,
) -> Initialization:
    """The full precedence a parameter slot resolves through (Heuristic Simulation
    Parameter Initialization increment): ``LITERATURE_DERIVED``/``CURATED`` >
    ``AI_PREDICTED`` > ``HEURISTIC_INITIALIZATION`` > ``PLACEHOLDER``.

    **A tier is only ever consulted when the previous tier found a genuine, complete
    absence of matching evidence** -- never when real evidence exists but disagrees.
    Disagreeing evidence (real measurements that conflict) is strictly more informative
    than no evidence at all, and is never silently discarded in favor of a lower-precedence
    guess: its own disclosed ``PLACEHOLDER`` (with every conflicting candidate's id in
    ``provenance_refs``) is the final word for that slot, exactly as
    ``initialize_from_evidence``'s own original Increment 5 policy already established for
    experimental evidence -- this increment extends the identical principle to the
    AI-predicted tier.

    ``kind``/``molecularity`` select the centralized heuristic default
    (``app.agent2.parameters.heuristic_defaults.heuristic_default_for_kind``) -- when that
    returns ``None`` (a parameter kind this increment's own policy does not support, e.g. a
    Hill coefficient or an equilibrium constant), the plain, no-evidence-at-all
    ``PLACEHOLDER`` from the experimental tier is returned unchanged, never an invented
    convention for an unsupported kind.
    """
    experimental = initialize_from_evidence(evidence_of_kind)
    if experimental.source is not ParameterSource.PLACEHOLDER or experimental.provenance_refs:
        return experimental

    ai_predicted = initialize_from_ai_predicted_evidence(evidence_of_kind)
    if ai_predicted.source is not ParameterSource.PLACEHOLDER or ai_predicted.provenance_refs:
        return ai_predicted

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
