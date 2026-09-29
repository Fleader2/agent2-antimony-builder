"""Pure policy: unit usability, context compatibility, and the concentration equation.

No database, no network, no filesystem, no randomness anywhere in this module --
every function here is a pure, deterministic transformation, mirroring every other
``app.agent2.*.policy``/``.heuristic_defaults`` module's identical convention.
Decimal-safe throughout; no ``float`` appears anywhere in this call graph.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.quantitative_context.types import ContextCompatibility
from app.agent2.types import CuratedExperimentalContext, CuratedQuantitativeObservation

# --- Observation-type / evidence-class vocabulary ------------------------------------------
#
# Agent 1's own plain strings (``CuratedQuantitativeObservation.observation_type``/
# ``.evidence_class`` are never re-typed as an enum on this side of the handoff -- see
# that type's own docstring). Compared as literal strings throughout this module,
# exactly like ``app.agent2.parameters.initializer``'s own ``_GOTENZYMES_SOURCE_LABEL``
# convention for ``CuratedKineticMeasurement.source``.

OBSERVATION_TYPE_PROTEIN_CONCENTRATION = "PROTEIN_CONCENTRATION"
OBSERVATION_TYPE_PROTEIN_ABUNDANCE = "PROTEIN_ABUNDANCE"
OBSERVATION_TYPE_CELL_VOLUME = "CELL_VOLUME"

EVIDENCE_CLASS_EXPERIMENT_SPECIFIC = "EXPERIMENT_SPECIFIC"
EVIDENCE_CLASS_REFERENCE_BASELINE = "REFERENCE_BASELINE"

# --- Canonical units --------------------------------------------------------------------------
#
# Mirrors Agent 1's own canonical-unit vocabulary
# (``app.normalization.quantitative_observation`` in the sibling repository) exactly,
# reimplemented independently here -- never imported across repositories.

CONCENTRATION_UNIT_NM = "nM"
ABUNDANCE_UNIT_MOLECULES_PER_CELL = "molecules_per_cell"
VOLUME_UNIT_PL = "pL"

#: Raw, as-reported unit spellings Agent 1 itself recognizes for this family (its own
#: ``_ABUNDANCE_TO_MOLECULES_PER_CELL`` table) -- used only as a fallback when Agent 1's
#: own ``normalized_unit`` is unset (unresolved conversion), never as a substitute for it.
_RAW_MOLECULES_PER_CELL_UNITS = frozenset(
    {"molecules/cell", "molecules per cell", "copies/cell", "copies per cell"}
)


def _normalize_unit_for_comparison(unit: str) -> str:
    return unit.strip().casefold()


# --- Unit-usability extraction (task Sec 3/5: never reinterpret a unit) ------------------------


def usable_concentration_nm(observation: CuratedQuantitativeObservation) -> Decimal | None:
    """A directly-usable nM concentration value, or ``None`` if this observation is not a
    usable ``PROTEIN_CONCENTRATION`` figure.

    Prefers Agent 1's own already-computed canonical ``normalized_value``/
    ``.normalized_unit`` (its own unit-conversion authority); falls back to the raw
    ``value``/``unit`` only when it is already, exactly, reported in ``nM`` -- never
    converts, never reinterprets any other unit as ``nM`` itself (this package performs
    no unit conversion of its own for concentrations; Agent 1 already owns that).
    """
    if observation.observation_type != OBSERVATION_TYPE_PROTEIN_CONCENTRATION:
        return None
    if observation.normalized_value is not None and observation.normalized_unit == (
        CONCENTRATION_UNIT_NM
    ):
        return observation.normalized_value
    if _normalize_unit_for_comparison(observation.unit) == _normalize_unit_for_comparison(
        CONCENTRATION_UNIT_NM
    ):
        return observation.value
    return None


def usable_abundance_molecules_per_cell(
    observation: CuratedQuantitativeObservation,
) -> Decimal | None:
    """A directly-usable molecules/cell abundance value, or ``None``. See
    ``usable_concentration_nm``'s own docstring for the identical
    prefer-canonical-then-recognized-raw policy."""
    if observation.observation_type != OBSERVATION_TYPE_PROTEIN_ABUNDANCE:
        return None
    if (
        observation.normalized_value is not None
        and observation.normalized_unit == ABUNDANCE_UNIT_MOLECULES_PER_CELL
    ):
        return observation.normalized_value
    if _normalize_unit_for_comparison(observation.unit) in {
        _normalize_unit_for_comparison(u) for u in _RAW_MOLECULES_PER_CELL_UNITS
    }:
        return observation.value
    return None


def usable_cell_volume_pl(observation: CuratedQuantitativeObservation) -> Decimal | None:
    """A directly-usable pL cell-volume value, or ``None``. See
    ``usable_concentration_nm``'s own docstring for the identical policy."""
    if observation.observation_type != OBSERVATION_TYPE_CELL_VOLUME:
        return None
    if observation.normalized_value is not None and observation.normalized_unit == VOLUME_UNIT_PL:
        return observation.normalized_value
    if _normalize_unit_for_comparison(observation.unit) == _normalize_unit_for_comparison(
        VOLUME_UNIT_PL
    ):
        return observation.value
    return None


# --- Context compatibility (task Sec 5) --------------------------------------------------------
#
# A direct, independent reimplementation of Agent 1's own
# ``app.normalization.quantitative_observation.classify_context_compatibility`` -- this
# repository never imports Agent 1's runtime package, so the identical deterministic
# policy is reproduced here rather than shared in code. Any future divergence between
# the two implementations would be a real, disclosed correctness bug -- there is
# currently no automated cross-repository check for that, an accepted limitation of the
# two-repository architecture (see ``docs/02_agent1_handoff_contract.md`` §2).

_CONTEXT_DETAIL_FIELDS: tuple[str, ...] = (
    "strain",
    "medium",
    "carbon_source",
    "temperature_c",
    "ph",
    "growth_phase",
    "growth_condition",
)


def classify_context_compatibility(
    a: CuratedExperimentalContext | None, b: CuratedExperimentalContext | None
) -> ContextCompatibility:
    """Exactly field-subset equality, never a numeric or weighted score (task's own
    explicit "do not introduce weighted/scored matching" instruction):

    * either side missing, or organism unknown on either side -> ``CONTEXT_UNKNOWN``;
    * organisms known and different -> ``CONTEXT_MISMATCH``;
    * organisms match, and any detail field both sides report disagrees ->
      ``CONTEXT_MISMATCH``;
    * organisms match, no field disagrees, but neither side reports any detail field at
      all -> ``CONTEXT_UNKNOWN``;
    * organisms match, no field disagrees, and every detail field one side reports is
      also reported (and equal) on the other -> ``EXACT_CONTEXT``;
    * organisms match, no field disagrees, but at least one side reports a detail field
      the other leaves unset -> ``COMPATIBLE_REFERENCE``.

    Never fuzzy-matches strings (``"YPD"`` vs. ``"yeast peptone dextrose"`` is a plain,
    disagreeing mismatch).
    """
    if a is None or b is None:
        return ContextCompatibility.CONTEXT_UNKNOWN
    if a.organism_id is None or b.organism_id is None:
        return ContextCompatibility.CONTEXT_UNKNOWN
    if a.organism_id != b.organism_id:
        return ContextCompatibility.CONTEXT_MISMATCH

    compared_any = False
    only_a_has_extra = False
    only_b_has_extra = False
    for field_name in _CONTEXT_DETAIL_FIELDS:
        value_a = getattr(a, field_name)
        value_b = getattr(b, field_name)
        if value_a is not None and value_b is not None:
            compared_any = True
            if value_a != value_b:
                return ContextCompatibility.CONTEXT_MISMATCH
        elif value_a is not None:
            only_a_has_extra = True
        elif value_b is not None:
            only_b_has_extra = True

    if not compared_any and not only_a_has_extra and not only_b_has_extra:
        return ContextCompatibility.CONTEXT_UNKNOWN
    if only_a_has_extra or only_b_has_extra:
        return ContextCompatibility.COMPATIBLE_REFERENCE
    return ContextCompatibility.EXACT_CONTEXT


#: Compatibility verdicts under which an abundance and a cell-volume observation may be
#: combined (task Sec 5: "if abundance and cell volume are incompatible, do not combine
#: them") -- ``CONTEXT_UNKNOWN`` is deliberately excluded: an unconfirmable relationship
#: is never treated as though it were confirmed compatible.
COMBINABLE_CONTEXT_COMPATIBILITY = frozenset(
    {ContextCompatibility.EXACT_CONTEXT, ContextCompatibility.COMPATIBLE_REFERENCE}
)


# --- Concentration equation (task Sec 3) --------------------------------------------------------

#: CODATA 2019 exact defined value (mol^-1) -- the SI Avogadro constant, defined exactly
#: since the 2019 SI redefinition, never an approximated/rounded figure chosen ad hoc.
AVOGADRO_NUMBER = Decimal("6.02214076e23")
#: 1 mol/L (M) = 1e9 nM.
NM_PER_MOLAR = Decimal("1e9")
#: 1 L = 1e12 pL.
PICOLITERS_PER_LITER = Decimal("1e12")
#: The task's own explicit default yeast reference cell-volume assumption, used only
#: when no better (real, curated) volume observation exists for a protein's own context
#: (tier 5 of the precedence order) -- never silently substituted for a genuine,
#: available measurement.
DEFAULT_ASSUMED_CELL_VOLUME_PL = Decimal("0.1")


def derive_concentration_nm(
    *, abundance_molecules_per_cell: Decimal, cell_volume_pl: Decimal
) -> Decimal:
    """``[E]_nM = N / (N_A * V) * 1e9``, ``V`` in litres (task Sec 3) -- Decimal-safe
    throughout, no independently hard-coded conversion factor (``PICOLITERS_PER_LITER``/
    ``NM_PER_MOLAR``/``AVOGADRO_NUMBER`` are the only three constants this function ever
    multiplies or divides by).

    Raises ``ValueError`` for a non-positive volume (never divides by zero, never
    returns a negative or infinite concentration) or a negative abundance (never a real,
    curated figure -- a defensive check, not an expected input).
    """
    if cell_volume_pl <= 0:
        raise ValueError(f"cell_volume_pl must be > 0, got {cell_volume_pl!r}")
    if abundance_molecules_per_cell < 0:
        raise ValueError(
            f"abundance_molecules_per_cell must be >= 0, got {abundance_molecules_per_cell!r}"
        )
    volume_l = cell_volume_pl / PICOLITERS_PER_LITER
    molarity = abundance_molecules_per_cell / (AVOGADRO_NUMBER * volume_l)
    return molarity * NM_PER_MOLAR


__all__ = [
    "ABUNDANCE_UNIT_MOLECULES_PER_CELL",
    "AVOGADRO_NUMBER",
    "COMBINABLE_CONTEXT_COMPATIBILITY",
    "CONCENTRATION_UNIT_NM",
    "DEFAULT_ASSUMED_CELL_VOLUME_PL",
    "EVIDENCE_CLASS_EXPERIMENT_SPECIFIC",
    "EVIDENCE_CLASS_REFERENCE_BASELINE",
    "NM_PER_MOLAR",
    "OBSERVATION_TYPE_CELL_VOLUME",
    "OBSERVATION_TYPE_PROTEIN_ABUNDANCE",
    "OBSERVATION_TYPE_PROTEIN_CONCENTRATION",
    "PICOLITERS_PER_LITER",
    "VOLUME_UNIT_PL",
    "classify_context_compatibility",
    "derive_concentration_nm",
    "usable_abundance_molecules_per_cell",
    "usable_cell_volume_pl",
    "usable_concentration_nm",
]
