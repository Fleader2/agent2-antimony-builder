"""Quantitative Context Resolution and Derived Enzyme Concentration -- output types.

``EnzymeConcentration``/``EnzymeConcentrationDependency``/``EnzymeConcentrationBasis``
themselves live in ``app.agent2.types`` (promoted there, like
``KineticLawSpecification``/``ParameterSpecification`` before them, since
``ModelSpecification`` must reference the final, materialized record directly --
see ``docs/16_quantitative_context_resolution.md`` §1 and
``app.agent2.version``'s own "narrower reading" precedent). This module holds only
the policy-internal wrapping types this package's own resolver produces and
consumes -- mirrors ``app.agent2.kinetics.types``'s/``app.agent2.boundaries.types``'s
identical split (the *decision* record is promoted; the *reason-code vocabulary*
and the *result-set wrapper* stay local).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agent2.types import EnzymeConcentration


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _clean_optional_str(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str or None, got {value!r}")
    stripped = value.strip()
    return stripped or None


class ContextCompatibility(StrEnum):
    """A minimal, wholly deterministic comparison of two experimental contexts --
    reimplemented independently on Agent 2's own side. This repository never
    imports Agent 1's runtime package (``app.normalization.quantitative_observation
    .ContextCompatibility``/``.classify_context_compatibility`` in the sibling
    ``agent1-biochemical-curator`` repository) -- the four-way semantics here are
    intentionally identical to that module's own (mirrored logic, never a
    cross-repository dependency), so a reviewer familiar with one immediately
    understands the other. See ``app.agent2.quantitative_context.policy
    .classify_context_compatibility`` for the actual comparison this enum's
    members describe.
    """

    EXACT_CONTEXT = "EXACT_CONTEXT"
    COMPATIBLE_REFERENCE = "COMPATIBLE_REFERENCE"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    CONTEXT_UNKNOWN = "CONTEXT_UNKNOWN"


class QuantitativeContextReasonCode(StrEnum):
    """Deterministic, closed vocabulary for why one protein's enzyme concentration
    was (or was not) resolved -- richer than ``EnzymeConcentrationBasis``
    (``app.agent2.types``, a categorical "which of the five success tiers" label
    only). ``REFERENCE_CELL_VOLUME_ASSUMED`` is the exact, task-specified marker
    for the 0.1 pL fallback (tier 5); the remaining three describe every way this
    package's own resolver can leave a protein unresolved.
    """

    #: Tier 5: no cell-volume observation of any kind exists for this protein's
    #: own context, so the explicit, disclosed 0.1 pL reference assumption was
    #: used instead of a real measurement.
    REFERENCE_CELL_VOLUME_ASSUMED = "REFERENCE_CELL_VOLUME_ASSUMED"
    #: More than one candidate observation exists at what would otherwise be the
    #: winning precedence tier, and they disagree (different value and/or unit) --
    #: never averaged, never arbitrarily chosen; this tier's own resolution stops
    #: here rather than silently falling through to a weaker tier (mirrors
    #: ``app.agent2.parameters.initializer``'s identical "disagreement is the
    #: final word for this slot" policy).
    AMBIGUOUS_CANDIDATE_OBSERVATIONS = "AMBIGUOUS_CANDIDATE_OBSERVATIONS"
    #: A candidate abundance observation and a candidate cell-volume observation
    #: both exist, but their own experimental contexts are not compatible
    #: (``ContextCompatibility.CONTEXT_MISMATCH``/``.CONTEXT_UNKNOWN``) -- never
    #: combined (task's own explicit rule).
    INCOMPATIBLE_ABUNDANCE_VOLUME_CONTEXT = "INCOMPATIBLE_ABUNDANCE_VOLUME_CONTEXT"
    #: Tier 6: no usable concentration, or abundance-plus-(real-or-assumed)-volume
    #: combination, exists for this protein at all.
    PROTEIN_CONCENTRATION_UNRESOLVED = "PROTEIN_CONCENTRATION_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class QuantitativeContextResolutionOutcome:
    """One protein's own resolution outcome.

    Exactly one of ``concentration``/``unresolved_reason_code`` is ever set --
    never both, never neither (mirrors ``app.agent1.types.ResolutionOutcome``-style
    "exactly one of a resolved value or a disclosed reason" pairing used
    throughout the sibling ``agent1-biochemical-curator`` repository's own
    resolution-outcome types, reimplemented independently here for the identical
    reason).
    """

    protein_id: str
    concentration: EnzymeConcentration | None = None
    unresolved_reason_code: str | None = None
    unresolved_explanation: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "protein_id", _require_non_empty_str(self.protein_id, field_name="protein_id")
        )
        if self.concentration is not None and not isinstance(
            self.concentration, EnzymeConcentration
        ):
            raise TypeError(
                "QuantitativeContextResolutionOutcome.concentration must be an "
                f"EnzymeConcentration or None, got {self.concentration!r}"
            )
        object.__setattr__(
            self,
            "unresolved_reason_code",
            _clean_optional_str(
                self.unresolved_reason_code, field_name="unresolved_reason_code"
            ),
        )
        object.__setattr__(
            self,
            "unresolved_explanation",
            _clean_optional_str(
                self.unresolved_explanation, field_name="unresolved_explanation"
            ),
        )
        if (self.concentration is None) == (self.unresolved_reason_code is None):
            raise ValueError(
                "QuantitativeContextResolutionOutcome requires exactly one of "
                "concentration/unresolved_reason_code, got "
                f"concentration={self.concentration!r} "
                f"unresolved_reason_code={self.unresolved_reason_code!r}"
            )
        if self.concentration is not None and self.concentration.protein_id != self.protein_id:
            raise ValueError(
                "QuantitativeContextResolutionOutcome.concentration.protein_id "
                f"({self.concentration.protein_id!r}) must equal protein_id ({self.protein_id!r})"
            )


@dataclass(frozen=True, slots=True)
class QuantitativeContextResolutionSet:
    """Every protein's own resolution outcome for one ``FullNetwork``.

    Covers exactly the protein-id set the resolver was asked to resolve -- never
    more, never fewer (an omitted protein was simply never asked about, distinct
    from an included-but-unresolved one). ``network_id`` ties this set back to the
    exact ``FullNetwork`` it was computed from, mirroring every sibling
    ``*Set``'s (``KineticLawAssignmentSet``, ``ParameterDeclarationSet``, ...)
    identical convention -- checked by
    ``app.agent2.model_specification.assembler.assemble_model_specification`` when
    this set is supplied.
    """

    network_id: str
    policy_version: str
    outcomes: tuple[QuantitativeContextResolutionOutcome, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        if not isinstance(self.outcomes, tuple) or any(
            not isinstance(item, QuantitativeContextResolutionOutcome) for item in self.outcomes
        ):
            raise TypeError(
                "QuantitativeContextResolutionSet.outcomes must be a tuple of "
                f"QuantitativeContextResolutionOutcome, got {self.outcomes!r}"
            )
        seen: set[str] = set()
        duplicates: set[str] = set()
        for outcome in self.outcomes:
            if outcome.protein_id in seen:
                duplicates.add(outcome.protein_id)
            seen.add(outcome.protein_id)
        if duplicates:
            raise ValueError(
                "QuantitativeContextResolutionSet.outcomes has duplicate protein_id(s): "
                f"{sorted(duplicates)}"
            )

    @property
    def enzyme_concentrations(self) -> tuple[EnzymeConcentration, ...]:
        """Every resolved protein's own ``EnzymeConcentration`` -- ready to attach to
        ``ModelSpecification.enzyme_concentrations`` verbatim."""
        return tuple(o.concentration for o in self.outcomes if o.concentration is not None)

    @property
    def resolved_protein_ids(self) -> tuple[str, ...]:
        return tuple(o.protein_id for o in self.outcomes if o.concentration is not None)

    @property
    def unresolved_protein_ids(self) -> tuple[str, ...]:
        return tuple(o.protein_id for o in self.outcomes if o.concentration is None)


__all__ = [
    "ContextCompatibility",
    "QuantitativeContextReasonCode",
    "QuantitativeContextResolutionOutcome",
    "QuantitativeContextResolutionSet",
]
