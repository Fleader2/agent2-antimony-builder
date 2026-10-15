"""Module-Count / Resolution Bias Audit domain model.

The central scientific question this package answers, per criterion: *does this criterion's
own score change systematically as a mathematical consequence of module count/size, even when
there is no real biological structure at all?* Answered by scoring a deterministic,
structure-blind ``NULL_REFERENCE`` partition (``null_partition.build_null_partition``) at each
tested module count -- any trend *that null partition's own score* shows is, by construction,
a pure resolution artifact, never genuine biological signal (it has none).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agent2.module_evaluation.types import ModularizationCriterion


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_tuple_of(value: object, item_type: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}, got {value!r}")
    return value


class BiasSeverity(StrEnum):
    """One criterion's own classification, decided entirely from how much (and in which
    direction) a structure-blind null partition's own score varies across the tested module
    counts (task instructions §4) -- never from the real/heuristic partition's own score,
    which could legitimately vary for genuine biological reasons."""

    #: The null partition's own score varies by less than a small, disclosed threshold across
    #: every tested resolution -- no material module-count/size dependence detected.
    NO_MATERIAL_BIAS = "NO_MATERIAL_BIAS"
    #: A real, but modest, swing in the null partition's own score across resolutions.
    MILD_RESOLUTION_DEPENDENCE = "MILD_RESOLUTION_DEPENDENCE"
    #: A large swing, decreasing as module count grows -- fewer, larger modules are
    #: mathematically favored by this criterion's own formula, independent of biology.
    STRONG_COARSE_BIAS = "STRONG_COARSE_BIAS"
    #: A large swing, increasing as module count grows -- more, smaller modules are
    #: mathematically favored by this criterion's own formula, independent of biology.
    STRONG_FINE_BIAS = "STRONG_FINE_BIAS"
    #: Fewer than two tested resolutions produced an available null-partition score to compare
    #: -- never guessed from one data point or zero.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ResolutionAuditEntry:
    """One tested resolution's own complete record for one criterion -- the real/heuristic
    modularization's own score, side by side with its matched null-partition baseline."""

    modularization_id: str
    module_count: int
    module_size_distribution: tuple[int, ...]
    available: bool
    raw_score: Decimal | None
    null_modularization_id: str
    null_available: bool
    null_reference_score: Decimal | None
    corrected_score: Decimal | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modularization_id",
            _require_non_empty_str(self.modularization_id, field_name="modularization_id"),
        )
        invalid_count = (
            not isinstance(self.module_count, int)
            or isinstance(self.module_count, bool)
            or self.module_count < 0
        )
        if invalid_count:
            raise ValueError(
                f"ResolutionAuditEntry.module_count must be a non-negative int, got "
                f"{self.module_count!r}"
            )
        object.__setattr__(
            self,
            "module_size_distribution",
            _require_tuple_of(
                self.module_size_distribution, int, field_name="module_size_distribution"
            ),
        )
        if self.available and self.raw_score is None:
            raise ValueError(
                "ResolutionAuditEntry.raw_score must not be None when available is True"
            )
        if not self.available and self.raw_score is not None:
            raise ValueError(
                "ResolutionAuditEntry.raw_score must be None when available is False -- never "
                "a fabricated score for missing evidence"
            )
        object.__setattr__(
            self,
            "null_modularization_id",
            _require_non_empty_str(
                self.null_modularization_id, field_name="null_modularization_id"
            ),
        )
        if self.null_available and self.null_reference_score is None:
            raise ValueError(
                "ResolutionAuditEntry.null_reference_score must not be None when "
                "null_available is True"
            )
        if not self.null_available and self.null_reference_score is not None:
            raise ValueError(
                "ResolutionAuditEntry.null_reference_score must be None when null_available "
                "is False"
            )
        if self.corrected_score is not None and (
            self.null_reference_score is None or self.raw_score is None
        ):
            raise ValueError(
                "ResolutionAuditEntry.corrected_score must be None unless both raw_score and "
                "null_reference_score are available"
            )


@dataclass(frozen=True, slots=True)
class CriterionResolutionAudit:
    """Every tested resolution's own entry for one criterion, plus the resulting bias
    classification (task instructions §4) -- never declares a "correct" resolution; only
    whether the criterion's own formula is resolution-biased."""

    criterion: ModularizationCriterion
    entries: tuple[ResolutionAuditEntry, ...]
    bias_severity: BiasSeverity
    explanation: str
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, ModularizationCriterion):
            raise TypeError(
                f"CriterionResolutionAudit.criterion must be a ModularizationCriterion, got "
                f"{self.criterion!r}"
            )
        object.__setattr__(
            self,
            "entries",
            _require_tuple_of(self.entries, ResolutionAuditEntry, field_name="entries"),
        )
        if not isinstance(self.bias_severity, BiasSeverity):
            raise TypeError(
                f"CriterionResolutionAudit.bias_severity must be a BiasSeverity, got "
                f"{self.bias_severity!r}"
            )
        object.__setattr__(
            self,
            "explanation",
            _require_non_empty_str(self.explanation, field_name="explanation"),
        )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


__all__ = ["BiasSeverity", "CriterionResolutionAudit", "ResolutionAuditEntry"]
