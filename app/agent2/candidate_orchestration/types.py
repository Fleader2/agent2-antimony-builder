"""Recursive Agent-4-Assisted Candidate Search Orchestration domain model.

**Two-stage evaluation** (task instructions §2): a candidate search round is always scored
first by whichever ``CriteriaWeights`` the caller supplies -- when that vector's own
``CALIBRATION_INDEPENDENCE`` weight is positive but no evidence yet exists for a candidate's own
modules, ``evaluate_modularization`` already reports that criterion ``unavailable`` (no change
needed here, see ``app.agent2.module_evaluation``), so a round's own ``overall_score`` is, for a
not-yet-calibrated candidate, driven entirely by the four cheap structural criteria
(``TOPOLOGICAL_SEPARATION``/``BOUNDARY_SPARSITY``/``COMPARTMENT_COHERENCE``/``EC_CLASS_
COHERENCE``) -- exactly the "inexpensive criteria first" the task names. ``CalibrationSelection
Policy`` (below) is the explicit, deterministic gate controlling which of those structurally-
scored candidates' own modules are worth spending a real Agent 3/Agent 4 round trip on.

**Never a fabricated score.** This package never computes a ``CALIBRATION_INDEPENDENCE`` score
itself -- it only decides *whether* to request real evidence (``CalibrationDecision``) and, once
obtained, feeds it back into the unchanged ``app.agent2.module_evaluation``/``app.agent2
.modularization_search`` scoring machinery for re-ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agent2.modularization_search.types import CandidateModularizationSearchResult
from app.agent2.module_calibration.types import (
    ModuleCalibrationEvaluation,
    ModuleCalibrationRequest,
)
from app.agent2.module_functional_evaluation.types import (
    ModuleFunctionalEvaluationRequest,
    ModuleFunctionalEvaluationResult,
)


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_tuple_of(value: object, item_type: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}, got {value!r}")
    return value


def _require_positive_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{field_name} must be a positive int, got {value!r}")
    return value


class CalibrationDecisionOutcome(StrEnum):
    """One module's own, fully-reasoned fate under one ``CalibrationSelectionPolicy`` (task
    instructions §3: "record why each candidate was or was not calibrated") -- never a silent
    omission. Exactly one outcome per ``(candidate_id, module_id)`` pair considered each round."""

    #: Selected: a real ``ModuleCalibrationRequest`` was built (or, when the module itself has
    #: no eligible standalone artifact, a disclosed ``BOUNDARY_INADEQUATE`` was resolved
    #: locally, requiring no Harness round trip at all).
    CALIBRATE = "CALIBRATE"
    #: This module's own candidate is a degenerate one-module decomposition -- excluded from
    #: ranking by default (task instructions §8: "one-module solutions remain reference-only"),
    #: so calibrating it could never change anything it is eligible to win.
    SKIP_DEGENERATE_CANDIDATE = "SKIP_DEGENERATE_CANDIDATE"
    #: This candidate's own rank (by current structural/blended score) falls outside
    #: ``policy.rank_threshold``.
    SKIP_BELOW_RANK_THRESHOLD = "SKIP_BELOW_RANK_THRESHOLD"
    #: This candidate's own current ``overall_score`` falls below ``policy.score_threshold``
    #: (or is itself unavailable).
    SKIP_BELOW_SCORE_THRESHOLD = "SKIP_BELOW_SCORE_THRESHOLD"
    #: ``policy.max_candidates_per_generation`` candidates already received at least one
    #: ``CALIBRATE`` decision this round -- never a partial/arbitrary cutoff mid-candidate.
    SKIP_CANDIDATE_BUDGET_EXHAUSTED = "SKIP_CANDIDATE_BUDGET_EXHAUSTED"
    #: ``policy.max_modules_per_candidate`` already reached for this one candidate.
    SKIP_MODULE_LIMIT_REACHED = "SKIP_MODULE_LIMIT_REACHED"
    #: ``policy.only_if_could_change_ordering`` is set, and this candidate's own best-case
    #: score (current score plus the maximum possible calibration contribution still
    #: available) could not plausibly move it past either immediate rank-neighbor.
    SKIP_COULD_NOT_CHANGE_ORDERING = "SKIP_COULD_NOT_CHANGE_ORDERING"
    #: This exact module (by its own content-addressed module id) already has available
    #: evidence from an earlier round/cache hit -- never recalibrated.
    SKIP_ALREADY_EVIDENCED = "SKIP_ALREADY_EVIDENCED"
    #: ``policy.total_calibration_run_budget`` (across every round of this orchestration) has
    #: been exhausted.
    SKIP_TOTAL_BUDGET_EXHAUSTED = "SKIP_TOTAL_BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class CalibrationSelectionPolicy:
    """The complete, explicit, deterministic gate between structural scoring and a real Agent
    3/Agent 4 round trip (task instructions §3). Every field below is a hard, disclosed limit --
    never an implicit default that could silently calibrate more (or less) than intended."""

    #: Maximum number of *distinct candidates* that may receive at least one ``CALIBRATE``
    #: decision this round -- never a partial cutoff mid-candidate (every module of a selected
    #: candidate is considered together).
    max_candidates_per_generation: int
    #: Maximum number of a single candidate's own modules that may be calibrated this round.
    #: ``None`` means every eligible module of a selected candidate.
    max_modules_per_candidate: int | None
    #: A candidate's own current ``overall_score`` must be ``>=`` this to be considered.
    #: ``None`` disables this gate.
    score_threshold: Decimal | None
    #: A candidate's own current rank (1-indexed, by descending ``overall_score``) must be
    #: ``<=`` this to be considered. ``None`` disables this gate.
    rank_threshold: int | None
    #: When ``True``, a candidate is only selected if calibrating it could plausibly change its
    #: own ranking relative to an immediate neighbor (task instructions §3) -- see
    #: ``selection.could_change_ordering`` for the exact, deterministic rule.
    only_if_could_change_ordering: bool
    #: Maximum number of real calibration runs this *entire* orchestration (every round
    #: combined) may ever request -- enforced here via the caller-supplied
    #: ``calibration_runs_used_so_far`` running total, never re-derived or guessed.
    total_calibration_run_budget: int
    policy_version: str

    def __post_init__(self) -> None:
        _require_positive_int(
            self.max_candidates_per_generation, field_name="max_candidates_per_generation"
        )
        if self.max_modules_per_candidate is not None:
            _require_positive_int(
                self.max_modules_per_candidate, field_name="max_modules_per_candidate"
            )
        for field_name, value in (
            ("score_threshold", self.score_threshold),
            ("rank_threshold", self.rank_threshold),
        ):
            if value is None:
                continue
            if field_name == "score_threshold":
                if not isinstance(value, Decimal) or value < 0 or value > 1:
                    raise ValueError(
                        f"CalibrationSelectionPolicy.score_threshold must be a Decimal in "
                        f"[0, 1] or None, got {value!r}"
                    )
            else:
                _require_positive_int(value, field_name="rank_threshold")
        if not isinstance(self.only_if_could_change_ordering, bool):
            raise TypeError(
                "CalibrationSelectionPolicy.only_if_could_change_ordering must be a bool, got "
                f"{self.only_if_could_change_ordering!r}"
            )
        if (
            not isinstance(self.total_calibration_run_budget, int)
            or isinstance(self.total_calibration_run_budget, bool)
            or self.total_calibration_run_budget < 0
        ):
            raise ValueError(
                "CalibrationSelectionPolicy.total_calibration_run_budget must be a "
                f"non-negative int, got {self.total_calibration_run_budget!r}"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


@dataclass(frozen=True, slots=True)
class CalibrationDecision:
    """One ``(candidate_id, module_id)`` pair's own, fully-reasoned fate this round -- always
    recorded, regardless of outcome (task instructions §3/§9: a user must be able to
    reconstruct why a module was or was not calibrated)."""

    candidate_id: str
    module_id: str
    outcome: CalibrationDecisionOutcome
    reason: str
    #: The candidate's own current ``overall_score`` at decision time (``None`` when
    #: unavailable) -- preserved for provenance even for a ``SKIP_*`` outcome.
    structural_score: Decimal | None
    #: The candidate's own current rank (1-indexed) at decision time.
    rank: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_non_empty_str(self.candidate_id, field_name="candidate_id"),
        )
        object.__setattr__(
            self, "module_id", _require_non_empty_str(self.module_id, field_name="module_id")
        )
        if not isinstance(self.outcome, CalibrationDecisionOutcome):
            raise TypeError(
                f"CalibrationDecision.outcome must be a CalibrationDecisionOutcome, got "
                f"{self.outcome!r}"
            )
        object.__setattr__(self, "reason", _require_non_empty_str(self.reason, field_name="reason"))
        if self.structural_score is not None and not isinstance(self.structural_score, Decimal):
            raise TypeError(
                f"CalibrationDecision.structural_score must be a Decimal or None, got "
                f"{self.structural_score!r}"
            )
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError(f"CalibrationDecision.rank must be a positive int, got {self.rank!r}")


class FunctionalEvaluationDecisionOutcome(StrEnum):
    """One module's own, fully-reasoned fate under one ``FunctionalEvaluationSelectionPolicy``
    (Automatic Functional-Evaluation Selection and Caching increment, task instructions §2:
    "record why every candidate/module was selected or skipped") -- mirrors
    ``CalibrationDecisionOutcome``'s own identical discipline exactly, with one additional,
    functional-evaluation-specific outcome (``SKIP_ZERO_FUNCTIONAL_WEIGHT``)."""

    #: Selected: a real ``ModuleFunctionalEvaluationRequest`` was built (or, when the whole
    #: network/module itself cannot support the analysis, a disclosed ``UNSUPPORTED_ANALYSIS``/
    #: ``INSUFFICIENT_TARGETS`` was resolved locally, requiring no Harness round trip at all).
    EVALUATE = "EVALUATE"
    #: Both ``DYNAMIC_ISOLATION`` and ``SENSITIVITY_COHERENCE`` have zero (or omitted) weight in
    #: the current ``CriteriaWeights`` -- functional evidence could not change ``overall_score``
    #: at all, so no candidate is ever selected this round (task instructions §2: "whether
    #: evaluation is skipped when both functional-criterion weights are zero"). Checked once,
    #: before any per-candidate gating -- every decision this round carries this one outcome.
    SKIP_ZERO_FUNCTIONAL_WEIGHT = "SKIP_ZERO_FUNCTIONAL_WEIGHT"
    #: This candidate is a degenerate one-module decomposition -- excluded from ranking by
    #: default, so evaluating it could never change a ranking it is not eligible to win.
    SKIP_DEGENERATE_CANDIDATE = "SKIP_DEGENERATE_CANDIDATE"
    #: This candidate's own rank (by current structural/blended score) falls outside
    #: ``policy.rank_threshold``.
    SKIP_BELOW_RANK_THRESHOLD = "SKIP_BELOW_RANK_THRESHOLD"
    #: This candidate's own current ``overall_score`` falls below ``policy.score_threshold``
    #: (or is itself unavailable).
    SKIP_BELOW_SCORE_THRESHOLD = "SKIP_BELOW_SCORE_THRESHOLD"
    #: ``policy.max_candidates_per_generation`` candidates already received at least one
    #: ``EVALUATE`` decision this round.
    SKIP_CANDIDATE_BUDGET_EXHAUSTED = "SKIP_CANDIDATE_BUDGET_EXHAUSTED"
    #: ``policy.max_modules_per_candidate`` already reached for this one candidate.
    SKIP_MODULE_LIMIT_REACHED = "SKIP_MODULE_LIMIT_REACHED"
    #: ``policy.only_if_could_change_ordering`` is set, and this candidate's own best-case score
    #: (current score plus the maximum possible functional-evidence contribution still
    #: available) could not plausibly move it past either immediate rank-neighbor.
    SKIP_COULD_NOT_CHANGE_ORDERING = "SKIP_COULD_NOT_CHANGE_ORDERING"
    #: This exact module (by its own content-addressed module id) already has available
    #: functional evidence from an earlier round/cache hit -- never re-evaluated.
    SKIP_ALREADY_EVIDENCED = "SKIP_ALREADY_EVIDENCED"
    #: ``policy.total_functional_evaluation_budget`` (across every round of this orchestration)
    #: has been exhausted.
    SKIP_TOTAL_BUDGET_EXHAUSTED = "SKIP_TOTAL_BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class FunctionalEvaluationSelectionPolicy:
    """The complete, explicit, deterministic gate between structural scoring and a real Agent 3
    functional-evaluation round trip (Automatic Functional-Evaluation Selection and Caching
    increment, task instructions §2) -- mirrors ``CalibrationSelectionPolicy`` field for field;
    a genuinely separate policy object with its own separate budget (task instructions §5:
    "functional and calibration selection must have separate budgets/policies")."""

    max_candidates_per_generation: int
    max_modules_per_candidate: int | None
    score_threshold: Decimal | None
    rank_threshold: int | None
    only_if_could_change_ordering: bool
    #: Maximum number of real Agent 3 functional-evaluation runs this *entire* orchestration
    #: (every round combined) may ever request -- enforced via the caller-supplied
    #: ``functional_evaluations_used_so_far`` running total, never re-derived or guessed.
    total_functional_evaluation_budget: int
    policy_version: str

    def __post_init__(self) -> None:
        _require_positive_int(
            self.max_candidates_per_generation, field_name="max_candidates_per_generation"
        )
        if self.max_modules_per_candidate is not None:
            _require_positive_int(
                self.max_modules_per_candidate, field_name="max_modules_per_candidate"
            )
        for field_name, value in (
            ("score_threshold", self.score_threshold),
            ("rank_threshold", self.rank_threshold),
        ):
            if value is None:
                continue
            if field_name == "score_threshold":
                if not isinstance(value, Decimal) or value < 0 or value > 1:
                    raise ValueError(
                        f"FunctionalEvaluationSelectionPolicy.score_threshold must be a "
                        f"Decimal in [0, 1] or None, got {value!r}"
                    )
            else:
                _require_positive_int(value, field_name="rank_threshold")
        if not isinstance(self.only_if_could_change_ordering, bool):
            raise TypeError(
                "FunctionalEvaluationSelectionPolicy.only_if_could_change_ordering must be a "
                f"bool, got {self.only_if_could_change_ordering!r}"
            )
        if (
            not isinstance(self.total_functional_evaluation_budget, int)
            or isinstance(self.total_functional_evaluation_budget, bool)
            or self.total_functional_evaluation_budget < 0
        ):
            raise ValueError(
                "FunctionalEvaluationSelectionPolicy.total_functional_evaluation_budget must "
                f"be a non-negative int, got {self.total_functional_evaluation_budget!r}"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


@dataclass(frozen=True, slots=True)
class FunctionalEvaluationDecision:
    """One ``(candidate_id, module_id)`` pair's own, fully-reasoned fate this round under
    ``FunctionalEvaluationSelectionPolicy`` -- always recorded, regardless of outcome. Mirrors
    ``CalibrationDecision`` exactly."""

    candidate_id: str
    module_id: str
    outcome: FunctionalEvaluationDecisionOutcome
    reason: str
    structural_score: Decimal | None
    rank: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_non_empty_str(self.candidate_id, field_name="candidate_id"),
        )
        object.__setattr__(
            self, "module_id", _require_non_empty_str(self.module_id, field_name="module_id")
        )
        if not isinstance(self.outcome, FunctionalEvaluationDecisionOutcome):
            raise TypeError(
                "FunctionalEvaluationDecision.outcome must be a "
                f"FunctionalEvaluationDecisionOutcome, got {self.outcome!r}"
            )
        object.__setattr__(self, "reason", _require_non_empty_str(self.reason, field_name="reason"))
        if self.structural_score is not None and not isinstance(self.structural_score, Decimal):
            raise TypeError(
                "FunctionalEvaluationDecision.structural_score must be a Decimal or None, got "
                f"{self.structural_score!r}"
            )
        if not isinstance(self.rank, int) or isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError(
                f"FunctionalEvaluationDecision.rank must be a positive int, got {self.rank!r}"
            )


@dataclass(frozen=True, slots=True)
class FunctionalEvaluationRunRequestEnvelope:
    """One ``EVALUATE`` decision's own, already-built ``ModuleFunctionalEvaluationRequest`` --
    ready for some other caller (always the Harness) to route through Agent 3. Never built for
    a module/network that cannot support the analysis -- that case resolves locally instead
    (see ``locally_resolved_functional_evidence``), never reaching this envelope at all."""

    decision: FunctionalEvaluationDecision
    request: ModuleFunctionalEvaluationRequest

    def __post_init__(self) -> None:
        if not isinstance(self.decision, FunctionalEvaluationDecision):
            raise TypeError(
                "FunctionalEvaluationRunRequestEnvelope.decision must be a "
                f"FunctionalEvaluationDecision, got {self.decision!r}"
            )
        if not isinstance(self.request, ModuleFunctionalEvaluationRequest):
            raise TypeError(
                "FunctionalEvaluationRunRequestEnvelope.request must be a "
                f"ModuleFunctionalEvaluationRequest, got {self.request!r}"
            )


@dataclass(frozen=True, slots=True)
class CalibrationRunRequestEnvelope:
    """One ``CALIBRATE`` decision's own, already-built ``ModuleCalibrationRequest`` -- ready for
    some other caller (always the Harness) to route through Agent 3 then Agent 4. Never built
    for a module with no eligible standalone artifact -- that case resolves locally and
    locally-resolved evidence) instead, never reaching this envelope at all."""

    decision: CalibrationDecision
    request: ModuleCalibrationRequest

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CalibrationDecision):
            raise TypeError(
                f"CalibrationRunRequestEnvelope.decision must be a CalibrationDecision, got "
                f"{self.decision!r}"
            )
        if not isinstance(self.request, ModuleCalibrationRequest):
            raise TypeError(
                "CalibrationRunRequestEnvelope.request must be a ModuleCalibrationRequest, "
                f"got {self.request!r}"
            )


@dataclass(frozen=True, slots=True)
class CandidateSearchRoundResult:
    """Everything one ``run_candidate_search_round`` call produces: the underlying, unchanged
    ``search_candidate_modularizations`` result, plus this round's own calibration-selection
    decisions and whatever those decisions actually require (a built request for the Harness to
    route, or an already-resolved local evidence record)."""

    search_result: CandidateModularizationSearchResult
    calibration_decisions: tuple[CalibrationDecision, ...]
    calibration_requests: tuple[CalibrationRunRequestEnvelope, ...]
    locally_resolved_evidence: tuple[ModuleCalibrationEvaluation, ...]
    policy_version: str
    #: Automatic Functional-Evaluation Selection and Caching increment -- always empty tuples
    #: when the caller does not supply a ``functional_evaluation_selection_policy`` to
    #: ``run_candidate_search_round`` (purely additive, zero-default-behavior-change, mirroring
    #: how ``functional_evaluation_evidence`` itself was rolled out).
    functional_evaluation_decisions: tuple[FunctionalEvaluationDecision, ...] = ()
    functional_evaluation_requests: tuple[FunctionalEvaluationRunRequestEnvelope, ...] = ()
    locally_resolved_functional_evidence: tuple[ModuleFunctionalEvaluationResult, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.search_result, CandidateModularizationSearchResult):
            raise TypeError(
                "CandidateSearchRoundResult.search_result must be a "
                f"CandidateModularizationSearchResult, got {self.search_result!r}"
            )
        object.__setattr__(
            self,
            "calibration_decisions",
            _require_tuple_of(
                self.calibration_decisions, CalibrationDecision, field_name="calibration_decisions"
            ),
        )
        object.__setattr__(
            self,
            "calibration_requests",
            _require_tuple_of(
                self.calibration_requests,
                CalibrationRunRequestEnvelope,
                field_name="calibration_requests",
            ),
        )
        object.__setattr__(
            self,
            "locally_resolved_evidence",
            _require_tuple_of(
                self.locally_resolved_evidence,
                ModuleCalibrationEvaluation,
                field_name="locally_resolved_evidence",
            ),
        )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        object.__setattr__(
            self,
            "functional_evaluation_decisions",
            _require_tuple_of(
                self.functional_evaluation_decisions,
                FunctionalEvaluationDecision,
                field_name="functional_evaluation_decisions",
            ),
        )
        object.__setattr__(
            self,
            "functional_evaluation_requests",
            _require_tuple_of(
                self.functional_evaluation_requests,
                FunctionalEvaluationRunRequestEnvelope,
                field_name="functional_evaluation_requests",
            ),
        )
        object.__setattr__(
            self,
            "locally_resolved_functional_evidence",
            _require_tuple_of(
                self.locally_resolved_functional_evidence,
                ModuleFunctionalEvaluationResult,
                field_name="locally_resolved_functional_evidence",
            ),
        )


__all__ = [
    "CalibrationDecision",
    "CalibrationDecisionOutcome",
    "CalibrationRunRequestEnvelope",
    "CalibrationSelectionPolicy",
    "CandidateSearchRoundResult",
    "FunctionalEvaluationDecision",
    "FunctionalEvaluationDecisionOutcome",
    "FunctionalEvaluationRunRequestEnvelope",
    "FunctionalEvaluationSelectionPolicy",
]
