"""Kinetic-Law Assignment domain model (Increment 4).

Deliberately narrow: one decision record per catalytic context
(``KineticLawAssignment``) and one immutable collection of them
(``KineticLawAssignmentSet``). Neither type carries a parameter id, a
parameter value, a boundary likelihood, a module id, or Antimony text --
see ``docs/07_kinetic_law_assignment.md`` §28.

**``KineticLawTarget`` note (Increment 4 instructions, Step 12):** rather
than introduce a separate nested ``KineticLawTarget`` type, its three
conceptual fields (``enzyme_state_id``/``protein_id``/``complex_id``) are
folded directly onto ``KineticLawAssignment`` alongside ``reaction_id`` --
"or equivalent" per that step's own instruction. This keeps the schema
flat; deterministic target exclusivity (at most one of the three set) is
validated in ``KineticLawAssignment.__post_init__`` exactly as it would be
on a separate type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agent2.types import KineticLawType

# --- Local validation helpers (mirrors app.agent2.types/app.agent2.characterization.types) -----


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _clean_optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string or None, got {value!r}")
    return value


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


def _require_enum_tuple(value: object, enum_cls: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, enum_cls) for item in value):
        raise TypeError(f"{field_name} must be a tuple of {enum_cls.__name__}, got {value!r}")
    return value


# --- KineticLawAssignmentSource ------------------------------------------------------------------


class KineticLawAssignmentSource(StrEnum):
    """Provenance of *the modeling decision itself* -- never a confidence score.

    Distinct from ``app.agent2.types.ParameterSource`` on purpose:
    ``ParameterSource`` answers "where did this numeric parameter value
    come from," which conflates a very different axis (curated value vs.
    default vs. calibrated-by-Agent-4) with what this enum answers instead
    -- "why does this reaction have *this kind* of rate-law structure."
    Reusing ``ParameterSource`` would have forced ``CURATED`` to mean both
    "Agent 1 reported this exact rate law" and "Agent 1 reported this
    exact Km value" -- two different claims this package must keep
    separate. See ``docs/07_kinetic_law_assignment.md`` §5.
    """

    CURATED_REPORTED = "CURATED_REPORTED"
    DETERMINISTIC_STRUCTURAL = "DETERMINISTIC_STRUCTURAL"
    HEURISTIC = "HEURISTIC"
    UNASSIGNED = "UNASSIGNED"


class KineticLawReasonCode(StrEnum):
    """Controlled, deterministic reason-code vocabulary (Increment 4 instructions, Step 21).

    Several entries are additions beyond that step's own suggested
    starting list, needed because the suggested list did not name a code
    for every rule this package actually implements -- documented here
    rather than silently reusing an ill-fitting existing code:

    * ``TENTATIVE_MASS_ACTION_DEFAULT`` -- the tentative, provisional
      mass-action-as-executable-default policy (Increment 4 revision:
      "Preserve the heuristic mass-action fallback ... make it explicitly
      tentative"). Supersedes the pre-revision
      ``ENZYMATIC_MECHANISM_UNKNOWN_MASS_ACTION_FALLBACK`` code (removed;
      never shipped in a committed contract) -- this is the canonical,
      machine-readable marker that an assignment is a provisional
      executable default, not curated or strongly justified, fact. See
      ``KineticLawAssignment.is_tentative`` and
      ``docs/07_kinetic_law_assignment.md`` §5-6/33.
    * ``KINETIC_MECHANISM_NOT_CURATED`` -- records, on a tentative
      default, that the reaction's actual kinetic mechanism (including
      its true rate-law form and, when relevant, its reverse-direction
      behavior) has not been curated or otherwise confirmed -- the
      tentative assignment provides a runnable structure only, never a
      claim about the real mechanism.
    * ``REGULATORY_KINETIC_EFFECT_NOT_MODELED`` -- records, on a
      tentative default for a catalytic context that does carry curated
      allostery, that the allosteric/regulatory kinetic contribution is
      not represented by the assigned (plain mass-action) form.
    * ``NO_REPORTED_RATE_LAW`` -- records that no curated reported rate
      law was available at all for this catalytic context (distinct from
      ``MULTIPLE_DISTINCT_REPORTED_RATE_LAWS``, which records that
      reported laws exist but conflict).
    """

    CURATED_RATE_LAW_PRESENT = "CURATED_RATE_LAW_PRESENT"
    CURATED_RATE_LAW_CLASSIFIED = "CURATED_RATE_LAW_CLASSIFIED"
    CURATED_RATE_LAW_CUSTOM = "CURATED_RATE_LAW_CUSTOM"
    MULTIPLE_DISTINCT_REPORTED_RATE_LAWS = "MULTIPLE_DISTINCT_REPORTED_RATE_LAWS"
    SIMPLE_ELEMENTARY_TRANSITION = "SIMPLE_ELEMENTARY_TRANSITION"
    SIMPLE_REVERSIBLE_ELEMENTARY_TRANSITION = "SIMPLE_REVERSIBLE_ELEMENTARY_TRANSITION"
    ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT = "ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT"
    TENTATIVE_MASS_ACTION_DEFAULT = "TENTATIVE_MASS_ACTION_DEFAULT"
    KINETIC_MECHANISM_NOT_CURATED = "KINETIC_MECHANISM_NOT_CURATED"
    REGULATORY_KINETIC_EFFECT_NOT_MODELED = "REGULATORY_KINETIC_EFFECT_NOT_MODELED"
    ALLOSTERY_PRESENT = "ALLOSTERY_PRESENT"
    STATE_SPECIFIC_KINETICS_PRESENT = "STATE_SPECIFIC_KINETICS_PRESENT"
    MULTIPLE_CATALYTIC_STATES = "MULTIPLE_CATALYTIC_STATES"
    REVERSIBILITY_UNKNOWN = "REVERSIBILITY_UNKNOWN"
    NO_REPORTED_RATE_LAW = "NO_REPORTED_RATE_LAW"
    STRUCTURAL_RULE_NOT_APPLICABLE = "STRUCTURAL_RULE_NOT_APPLICABLE"
    HEURISTIC_RULE_NOT_APPLICABLE = "HEURISTIC_RULE_NOT_APPLICABLE"
    INSUFFICIENT_CURATED_CONTEXT = "INSUFFICIENT_CURATED_CONTEXT"


@dataclass(frozen=True, slots=True)
class KineticLawAssignment:
    """One kinetic-law decision for one catalytic context of one reaction.

    A "catalytic context" is the reaction itself when no catalyst
    distinguishes sub-contexts, or one specific enzyme state / protein /
    complex when it does -- see ``docs/07_kinetic_law_assignment.md`` §12.
    At most one of ``enzyme_state_id``/``protein_id``/``complex_id`` is
    ever set; all three ``None`` means "the reaction as a whole, with no
    distinguishing catalytic identity" (no catalyst known, or several
    catalysts collapsed because their evidence is identical -- §21/§26).

    Never carries a parameter id, a parameter value, a fitted quantity, a
    boundary field, or a module field (Increment 4 instructions, Step 6).

    **Tentative assignments** (``reason_codes`` containing
    ``KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT`` -- see
    ``is_tentative``) are a deliberate exception to "an assignment
    resolves what it decides": they carry ``assignment_source ==
    HEURISTIC`` (a real, if provisional, modeling decision -- the model
    can run) *and* a non-empty ``unresolved_reasons`` (the actual
    mechanism remains unconfirmed). ``CURATED_REPORTED``/
    ``DETERMINISTIC_STRUCTURAL`` assignments never carry
    ``unresolved_reasons`` -- those sources are, by construction, already
    resolved.
    """

    assignment_id: str
    reaction_id: str
    kinetic_law_type: KineticLawType
    assignment_source: KineticLawAssignmentSource
    policy_version: str
    enzyme_state_id: str | None = None
    protein_id: str | None = None
    complex_id: str | None = None
    reported_rate_law_text: str | None = None
    source_measurement_ids: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    reason_codes: tuple[KineticLawReasonCode, ...] = ()
    unresolved_reasons: tuple[KineticLawReasonCode, ...] = ()
    assumptions: tuple[str, ...] = ()
    explanation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assignment_id",
            _require_non_empty_str(self.assignment_id, field_name="assignment_id"),
        )
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        if not isinstance(self.kinetic_law_type, KineticLawType):
            raise TypeError(
                "KineticLawAssignment.kinetic_law_type must be a KineticLawType, "
                f"got {self.kinetic_law_type!r}"
            )
        if not isinstance(self.assignment_source, KineticLawAssignmentSource):
            raise TypeError(
                "KineticLawAssignment.assignment_source must be a KineticLawAssignmentSource, "
                f"got {self.assignment_source!r}"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        object.__setattr__(
            self,
            "enzyme_state_id",
            _clean_optional_str(self.enzyme_state_id, field_name="enzyme_state_id"),
        )
        object.__setattr__(
            self, "protein_id", _clean_optional_str(self.protein_id, field_name="protein_id")
        )
        object.__setattr__(
            self, "complex_id", _clean_optional_str(self.complex_id, field_name="complex_id")
        )
        target_fields = [self.enzyme_state_id, self.protein_id, self.complex_id]
        if sum(field is not None for field in target_fields) > 1:
            raise ValueError(
                "KineticLawAssignment allows at most one of enzyme_state_id/protein_id/"
                f"complex_id to be set, got enzyme_state_id={self.enzyme_state_id!r}, "
                f"protein_id={self.protein_id!r}, complex_id={self.complex_id!r}"
            )
        object.__setattr__(
            self,
            "reported_rate_law_text",
            _clean_optional_str(self.reported_rate_law_text, field_name="reported_rate_law_text"),
        )
        if (
            self.assignment_source is KineticLawAssignmentSource.CURATED_REPORTED
            and self.reported_rate_law_text is None
        ):
            raise ValueError(
                "KineticLawAssignment with assignment_source=CURATED_REPORTED requires a "
                "non-blank reported_rate_law_text"
            )
        is_unassigned_type = self.kinetic_law_type is KineticLawType.UNASSIGNED
        is_unassigned_source = self.assignment_source is KineticLawAssignmentSource.UNASSIGNED
        if is_unassigned_type != is_unassigned_source:
            raise ValueError(
                "KineticLawAssignment.kinetic_law_type is UNASSIGNED if and only if "
                f"assignment_source is UNASSIGNED, got kinetic_law_type="
                f"{self.kinetic_law_type.value}, assignment_source={self.assignment_source.value}"
            )
        object.__setattr__(
            self,
            "source_measurement_ids",
            _require_str_tuple(self.source_measurement_ids, field_name="source_measurement_ids"),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        object.__setattr__(
            self,
            "reason_codes",
            _require_enum_tuple(self.reason_codes, KineticLawReasonCode, field_name="reason_codes"),
        )
        if not self.reason_codes:
            raise ValueError("KineticLawAssignment.reason_codes must never be empty")
        object.__setattr__(
            self,
            "unresolved_reasons",
            _require_enum_tuple(
                self.unresolved_reasons, KineticLawReasonCode, field_name="unresolved_reasons"
            ),
        )
        resolved_sources = (
            KineticLawAssignmentSource.CURATED_REPORTED,
            KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        )
        if bool(self.unresolved_reasons) and self.assignment_source in resolved_sources:
            raise ValueError(
                "KineticLawAssignment.unresolved_reasons must be empty when assignment_source "
                f"is {self.assignment_source.value} -- that source is, by construction, already "
                "resolved (unresolved_reasons is permitted for HEURISTIC, including a tentative "
                "default, and for UNASSIGNED)"
            )
        is_tentative_reason = (
            KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT in self.reason_codes
        )
        if is_tentative_reason:
            if self.assignment_source is not KineticLawAssignmentSource.HEURISTIC:
                raise ValueError(
                    "KineticLawAssignment with reason_codes containing "
                    "TENTATIVE_MASS_ACTION_DEFAULT must have assignment_source=HEURISTIC, "
                    f"got {self.assignment_source.value}"
                )
            if self.kinetic_law_type is not KineticLawType.MASS_ACTION:
                raise ValueError(
                    "KineticLawAssignment with reason_codes containing "
                    "TENTATIVE_MASS_ACTION_DEFAULT must have kinetic_law_type=MASS_ACTION, "
                    f"got {self.kinetic_law_type.value}"
                )
            if KineticLawReasonCode.KINETIC_MECHANISM_NOT_CURATED not in self.unresolved_reasons:
                raise ValueError(
                    "KineticLawAssignment with reason_codes containing "
                    "TENTATIVE_MASS_ACTION_DEFAULT must record KINETIC_MECHANISM_NOT_CURATED in "
                    "unresolved_reasons -- a tentative default never clears unresolved status"
                )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self, "explanation", _require_non_empty_str(self.explanation, field_name="explanation")
        )

    @property
    def is_tentative(self) -> bool:
        """Pure, derived machine-readable marker: is this a provisional default, not a
        curated or strongly justified assignment?

        Computed from ``reason_codes`` rather than stored as a separate
        field -- the reason code is already the canonical signal (smallest
        clean solution: Increment 4 revision, Step 4). ``True`` exactly
        when ``reason_codes`` contains
        ``KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT``; ``False``
        for every ``CURATED_REPORTED`` assignment, every
        ``DETERMINISTIC_STRUCTURAL`` assignment, the conservative
        Michaelis-Menten heuristic, curated ``CUSTOM``, and ``UNASSIGNED``.
        """
        return KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT in self.reason_codes


@dataclass(frozen=True, slots=True)
class KineticLawAssignmentSet:
    """Every kinetic-law assignment decided for one ``NetworkCharacterization``.

    Every reaction in the source ``NetworkCharacterization`` is covered by
    at least one assignment -- never silently omitted (Increment 4
    instructions, Step 7). A reaction with more than one distinct
    catalytic context (e.g. two catalytic ``EnzymeState``\\ s never
    collapsed into one decision, per Step 12's closing instruction) is
    covered by more than one assignment; this is the documented exception
    to "one assignment per reaction" -- see
    ``docs/07_kinetic_law_assignment.md`` §7.
    """

    network_id: str
    characterization_policy_version: str
    kinetic_law_policy_version: str
    assignments: tuple[KineticLawAssignment, ...]
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        object.__setattr__(
            self,
            "characterization_policy_version",
            _require_non_empty_str(
                self.characterization_policy_version, field_name="characterization_policy_version"
            ),
        )
        object.__setattr__(
            self,
            "kinetic_law_policy_version",
            _require_non_empty_str(
                self.kinetic_law_policy_version, field_name="kinetic_law_policy_version"
            ),
        )
        if not isinstance(self.assignments, tuple) or any(
            not isinstance(item, KineticLawAssignment) for item in self.assignments
        ):
            raise TypeError(
                f"KineticLawAssignmentSet.assignments must be a tuple of KineticLawAssignment, "
                f"got {self.assignments!r}"
            )
        seen_contexts: set[tuple[str, str | None, str | None, str | None]] = set()
        seen_ids: set[str] = set()
        for assignment in self.assignments:
            context = (
                assignment.reaction_id,
                assignment.enzyme_state_id,
                assignment.protein_id,
                assignment.complex_id,
            )
            if context in seen_contexts:
                raise ValueError(
                    f"KineticLawAssignmentSet has more than one assignment for the same "
                    f"catalytic context {context!r}"
                )
            seen_contexts.add(context)
            if assignment.assignment_id in seen_ids:
                raise ValueError(
                    f"KineticLawAssignmentSet has duplicate assignment_id "
                    f"{assignment.assignment_id!r}"
                )
            seen_ids.add(assignment.assignment_id)
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = [
    "KineticLawAssignment",
    "KineticLawAssignmentSet",
    "KineticLawAssignmentSource",
    "KineticLawReasonCode",
]
