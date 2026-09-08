"""Deterministic parameter-naming and curated-measurement-recognition policy (Increment 5).

`CuratedKineticMeasurement.parameter_type` is deliberately an open
`VARCHAR` on Agent 1's side (`app/models/enums.py`'s own module docstring
in `agent1-biochemical-curator`: "the specification requires it to remain
an open VARCHAR... must never be restricted"). Agent 2 therefore cannot
rely on a closed enum to recognize a measurement's kind -- this module
maintains its own small, closed, case-insensitive recognition vocabulary
instead, used only to *match* a measurement to a parameter slot this
package already decided (from the kinetic-law type) needs to exist. It
never widens what parameters get declared; it only decides which curated
measurement, if any, initializes an already-decided slot.
"""

from __future__ import annotations

from app.agent2.types import CuratedKineticMeasurement

_ID_SEPARATOR = "_"

#: Closed, Agent-2-maintained recognition vocabulary -- never presented as Agent 1's own
#: controlled vocabulary (there isn't one). Matched case-insensitively against
#: ``CuratedKineticMeasurement.parameter_type`` only (never ``reported_parameter_type``,
#: which is Agent 1's raw as-reported text and is never parsed here).
KM_TYPES = frozenset({"KM", "K_M", "MICHAELIS_CONSTANT"})
KCAT_TYPES = frozenset({"KCAT", "K_CAT", "TURNOVER_NUMBER"})
VMAX_TYPES = frozenset({"VMAX", "V_MAX"})
KI_TYPES = frozenset({"KI", "K_I", "INHIBITION_CONSTANT"})
KEQ_TYPES = frozenset({"KEQ", "K_EQ", "EQUILIBRIUM_CONSTANT"})
HILL_COEFFICIENT_TYPES = frozenset({"N", "NH", "HILL_COEFFICIENT", "HILL_N"})
RATE_CONSTANT_TYPES = frozenset({"K", "K1", "RATE_CONSTANT"})
FORWARD_RATE_TYPES = frozenset({"KF", "K_FORWARD", "KPLUS", "K_PLUS"})
REVERSE_RATE_TYPES = frozenset({"KR", "K_REVERSE", "KMINUS", "K_MINUS", "K_BACKWARD"})


def normalized_parameter_type(measurement: CuratedKineticMeasurement) -> str:
    """Case/whitespace-normalized ``parameter_type`` -- comparison only, never stored."""
    return measurement.parameter_type.strip().upper()


def measurements_of_kind(
    evidence: tuple[CuratedKineticMeasurement, ...], recognized_types: frozenset[str]
) -> tuple[CuratedKineticMeasurement, ...]:
    """Every measurement in ``evidence`` whose ``parameter_type`` matches ``recognized_types``."""
    return tuple(m for m in evidence if normalized_parameter_type(m) in recognized_types)


def context_suffix(
    *, enzyme_state_id: str | None, protein_id: str | None, complex_id: str | None
) -> str | None:
    """The catalytic-context identity to fold into a parameter id/name, if any.

    At most one of the three is ever set (`KineticLawAssignment`'s own
    invariant) -- returns it verbatim, or `None` for the reaction-general
    context (no distinguishing catalytic identity).
    """
    return enzyme_state_id or protein_id or complex_id


def build_parameter_slug(
    prefix: str,
    *,
    reaction_id: str,
    suffix: str | None,
    substrate_id: str | None = None,
) -> str:
    """Deterministic parameter id/name (Increment 5 instructions, Step 7).

    ``f"{prefix}_{reaction_id}"``, optionally followed by the catalytic-
    context suffix (an enzyme-state/protein/complex id) and/or a
    substrate id (for a per-substrate ``Km``) -- e.g. ``Km_r1_es1_glc``.
    A pure function of its inputs: calling it twice with the same
    arguments always returns the identical string, exactly as
    `app.agent2.network.types.build_species_id`/`build_enzyme_association_id`
    already establish for this codebase's deterministic-id style. Never a
    random UUID.
    """
    parts = [prefix, reaction_id]
    if suffix is not None:
        parts.append(suffix)
    if substrate_id is not None:
        parts.append(substrate_id)
    return _ID_SEPARATOR.join(parts)


def measurements_agree(evidence: tuple[CuratedKineticMeasurement, ...]) -> bool:
    """Whether every measurement in ``evidence`` reports the identical value and unit.

    Never a tolerance-based "close enough" comparison, and never a unit
    conversion -- exact ``Decimal``/string equality only (Increment 5
    instructions, Step 12/13: never average, never rank, never silently
    choose one; treat differing units as a form of disagreement, never
    normalized). An empty or single-element ``evidence`` trivially agrees.
    """
    if len(evidence) <= 1:
        return True
    first = evidence[0]
    return all(m.value == first.value and m.unit == first.unit for m in evidence[1:])


__all__ = [
    "FORWARD_RATE_TYPES",
    "HILL_COEFFICIENT_TYPES",
    "KCAT_TYPES",
    "KEQ_TYPES",
    "KI_TYPES",
    "KM_TYPES",
    "RATE_CONSTANT_TYPES",
    "REVERSE_RATE_TYPES",
    "VMAX_TYPES",
    "build_parameter_slug",
    "context_suffix",
    "measurements_agree",
    "measurements_of_kind",
    "normalized_parameter_type",
]
