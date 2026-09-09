"""Heuristic Boundary Assessment domain model (Increment 6).

`BoundaryAssessment`/`BoundaryLikelihood`/`BoundaryParameterBasis`
(`app.agent2.types`) are reused entirely unchanged -- inspection found no
essential missing field (Step 6/34: "reuse... do not redesign unless a
genuine contradiction exists"). This module adds only what those
pre-existing, already-approved contracts do not carry: the internal rule
vocabulary (`RuleDirection`/`RuleStrength`/`BoundaryReasonCode`/
`RuleOutcome`) used to *build* a `BoundaryAssessment`'s
`supporting_reason_codes`/`opposing_reason_codes`/`likelihood`, and the
new top-level collection, `BoundaryAssessmentSet`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agent2.types import BoundaryAssessment

# --- Local validation helpers (mirrors the identical pattern already used in
# app.agent2.characterization.types / app.agent2.kinetics.types / app.agent2.parameters.types) --


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


class RuleDirection(StrEnum):
    """Whether one heuristic rule's outcome, on one candidate interface, argues for or
    against treating it as a module boundary -- never a magnitude, never a probability."""

    SUPPORT = "SUPPORT"
    OPPOSE = "OPPOSE"
    NEUTRAL = "NEUTRAL"


class RuleStrength(StrEnum):
    """A rule outcome's own qualitative strength -- never converted to a number.

    Used in exactly two narrow, documented ways: (1) as a label attached
    to a `RuleOutcome`, surfaced only insofar as it decides which
    categorical branch `policy.combine_outcomes` takes, and (2) internally,
    to pick the *weaker* of two known strengths when a rule (e.g.
    kinetic-law discontinuity) must reconcile mismatched-confidence
    evidence on its two sides -- an ordinal min/max comparison between two
    already-qualitative labels, never a numeric score or weighted sum.
    """

    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


class BoundaryReasonCode(StrEnum):
    """Controlled, deterministic reason-code vocabulary.

    Every value here is written verbatim onto `BoundaryAssessment
    .supporting_reason_codes`/`.opposing_reason_codes` (as `.value`, since
    that field is a plain `tuple[str, ...]`, not a typed enum tuple, on
    the already-approved `app.agent2.types` contract).

    **Increment 6 pre-commit scientific revision.** The catalog is split
    into three groups, documented in full in
    ``docs/09_heuristic_boundary_assessment.md`` §10a:

    * **Structural proxies** (`COMPARTMENT_TRANSITION` through
      `STRONG_LOCAL_CONTINUITY` below) -- topological/modeling facts that
      *correlate* with functional modularity but are not themselves
      evidence of it. Several were downgraded in strength for this reason
      (see `rules.py`).
    * **Parameterization-convenience codes** (`PARAMETER_SOURCE_DISCONTINUITY`,
      `PLACEHOLDER_PARAMETER_REGION`, `PARAMETERIZATION_CONTINUITY`) --
      **retained in this vocabulary but their rule functions now always
      return `NEUTRAL`.** Which measurements Agent 1 happened to curate is
      a fact about our knowledge state, never about the organism's
      biology, so these never contribute to a boundary's likelihood
      anymore. Kept as vocabulary (not deleted) so the underlying
      distinction stays documented and so a future increment could
      reactivate them for a clearly-labeled non-biological purpose (e.g.
      an Increment 7 "calibration convenience" side-channel) without
      inventing new names.
    * **Functional-modularity codes** (`SHARED_RESOURCE_COUPLING` through
      `STABLE_FUNCTIONAL_ROLE_DEFERRED`) -- new in this revision,
      evaluating the biological definition of a module directly
      (isolation, coupling, feedback) rather than mere structural
      discontinuity. Three are deliberately-NEUTRAL-only placeholders
      pending later-agent capability (see docs §10a).

    **Increment 6 feedback-heuristic revision.** Nested feedback loops are
    ordinary biology: an *intrinsic* loop confined to one side of an
    interface is what makes that side a functional module in the first
    place, while an *extrinsic* loop that crosses module boundaries is how
    already-independent modules communicate and get regulated -- it is
    not evidence they should be merged. `NEGATIVE_FEEDBACK_ISOLATION` was
    therefore renamed `INTRINSIC_FEEDBACK_CONFINEMENT` and its direction
    flipped from support to **oppose** (confined feedback argues for
    preserving that side intact, i.e. against introducing more boundary
    structure right at its edge -- never for cutting there).
    `FEEDBACK_CROSSING_BOUNDARY` was renamed
    `EXTRINSIC_FEEDBACK_CROSSING_DEFERRED` and now always evaluates
    `NEUTRAL`: Agent 2 cannot yet determine whether a boundary-crossing
    loop is direct, strong, constitutive, local, and minimally regulated
    (the properties that would be required before crossing feedback could
    legitimately oppose a boundary), so it must not pretend to. See
    ``docs/09_heuristic_boundary_assessment.md`` §10a/§25/"Nested Feedback
    Loops" for the full rationale.

    **Increment 6 terminology revision (naming/documentation only, no
    behavior change).** `INTRINSIC_FEEDBACK_CONFINEMENT` was renamed
    `INTRINSIC_FEEDBACK_ISOLATION`: the scientific concept is not merely
    that the feedback is spatially/topologically "confined," but that
    local, direct, strong negative feedback provides genuine functional
    *isolation* by reducing retroactivity and preserving intrinsic module
    behavior. The deterministic trigger, direction (`OPPOSE`), and
    strength (`STRONG`) are byte-identical to the prior name -- see
    ``docs/09_heuristic_boundary_assessment.md`` §24.

    Deliberately excludes a parameter-magnitude/timescale code (not
    implemented -- see docs §19).
    """

    # --- Structural proxies (weakened; never alone worth more than MODERATE) -------------
    COMPARTMENT_TRANSITION = "COMPARTMENT_TRANSITION"
    TRANSPORT_INTERFACE = "TRANSPORT_INTERFACE"
    BRANCH_POINT = "BRANCH_POINT"
    CONVERGENCE_POINT = "CONVERGENCE_POINT"
    ENZYME_STATE_TRANSITION = "ENZYME_STATE_TRANSITION"
    CURATED_REGULATORY_CONTEXT_CHANGE = "CURATED_REGULATORY_CONTEXT_CHANGE"
    KINETIC_LAW_DISCONTINUITY = "KINETIC_LAW_DISCONTINUITY"
    HIGH_CONNECTIVITY_CONTINUITY = "HIGH_CONNECTIVITY_CONTINUITY"
    STRONG_LOCAL_CONTINUITY = "STRONG_LOCAL_CONTINUITY"

    # --- Parameterization convenience (retained vocabulary; always NEUTRAL) ---------------
    PARAMETER_SOURCE_DISCONTINUITY = "PARAMETER_SOURCE_DISCONTINUITY"
    PLACEHOLDER_PARAMETER_REGION = "PLACEHOLDER_PARAMETER_REGION"
    PARAMETERIZATION_CONTINUITY = "PARAMETERIZATION_CONTINUITY"

    # --- Functional modularity (new; STRONG-capable codes) --------------------------------
    SHARED_RESOURCE_COUPLING = "SHARED_RESOURCE_COUPLING"
    INTRINSIC_FEEDBACK_ISOLATION = "INTRINSIC_FEEDBACK_ISOLATION"
    IRREVERSIBLE_OUTPUT_ISOLATION = "IRREVERSIBLE_OUTPUT_ISOLATION"

    # --- Extrinsic feedback (recognized structurally; always NEUTRAL pending a future
    # dynamic-capability revision -- see class docstring and rules.py) --------------------
    EXTRINSIC_FEEDBACK_CROSSING_DEFERRED = "EXTRINSIC_FEEDBACK_CROSSING_DEFERRED"

    # --- Deferred principles (new; always NEUTRAL until a later agent exists) ------------
    RELAXATION_TIME_INVARIANCE_DEFERRED = "RELAXATION_TIME_INVARIANCE_DEFERRED"
    CONTEXT_REUSABILITY_DEFERRED = "CONTEXT_REUSABILITY_DEFERRED"
    STABLE_FUNCTIONAL_ROLE_DEFERRED = "STABLE_FUNCTIONAL_ROLE_DEFERRED"


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """One heuristic rule's evaluation of one candidate interface.

    `strength` is `None` exactly when `direction` is `NEUTRAL` (a rule
    that does not apply has no strength to report) and non-`None`
    otherwise -- enforced in `__post_init__`.
    """

    reason_code: BoundaryReasonCode
    direction: RuleDirection
    strength: RuleStrength | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, BoundaryReasonCode):
            raise TypeError(
                f"RuleOutcome.reason_code must be a BoundaryReasonCode, got {self.reason_code!r}"
            )
        if not isinstance(self.direction, RuleDirection):
            raise TypeError(
                f"RuleOutcome.direction must be a RuleDirection, got {self.direction!r}"
            )
        is_neutral = self.direction is RuleDirection.NEUTRAL
        if is_neutral and self.strength is not None:
            raise ValueError("RuleOutcome.strength must be None when direction is NEUTRAL")
        if not is_neutral and not isinstance(self.strength, RuleStrength):
            raise ValueError(
                "RuleOutcome.strength must be a RuleStrength when direction is SUPPORT/OPPOSE, "
                f"got {self.strength!r}"
            )


@dataclass(frozen=True, slots=True)
class BoundaryAssessmentSet:
    """Every `BoundaryAssessment` decided for one fully-parameterized `FullNetwork`.

    One candidate interface generates exactly one assessment (unlike
    `KineticLawAssignmentSet`/`ParameterDeclarationSet`, a boundary
    candidate is never split into multiple catalytic-context-scoped
    records -- see `docs/09_heuristic_boundary_assessment.md` §5).
    """

    network_id: str
    characterization_policy_version: str
    kinetic_law_policy_version: str
    parameter_policy_version: str
    boundary_policy_version: str
    assessments: tuple[BoundaryAssessment, ...]
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        for field_name in (
            "characterization_policy_version",
            "kinetic_law_policy_version",
            "parameter_policy_version",
            "boundary_policy_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty_str(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.assessments, tuple) or any(
            not isinstance(item, BoundaryAssessment) for item in self.assessments
        ):
            raise TypeError(
                f"BoundaryAssessmentSet.assessments must be a tuple of BoundaryAssessment, "
                f"got {self.assessments!r}"
            )
        seen_ids: set[str] = set()
        for assessment in self.assessments:
            if assessment.boundary_id in seen_ids:
                raise ValueError(
                    f"BoundaryAssessmentSet has duplicate boundary_id {assessment.boundary_id!r}"
                )
            seen_ids.add(assessment.boundary_id)
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = [
    "BoundaryAssessmentSet",
    "BoundaryReasonCode",
    "RuleDirection",
    "RuleOutcome",
    "RuleStrength",
]
