"""Curated-value initialization policy for one already-decided parameter slot (Increment 5).

``initialize_from_evidence`` is this module's one function: given the
curated measurements that match one parameter slot's recognized type
(already narrowed by `policy.measurements_of_kind`), decide that slot's
`ParameterSource`, `value`, `unit`, `source_reference`, `provenance_refs`,
and `uncertainty_text`. Never called with numeric comparison, unit
conversion, averaging, or ranking -- see module-level policy notes below
and `docs/08_parameter_declaration_initialization.md` §6/§10-13.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.agent2.parameters import policy
from app.agent2.types import CuratedKineticMeasurement, ParameterSource


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
    """Resolve one parameter slot from the curated measurements that match its recognized kind.

    * **No matching measurement** -- ``PLACEHOLDER``, ``value=None``.
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


__all__ = ["Initialization", "initialize_from_evidence"]
