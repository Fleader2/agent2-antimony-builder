"""Recursive Agent-4-Assisted Candidate Search Orchestration: Agent 2's own side of closing the
modularization loop.

This package never calls Agent 3 or Agent 4, and never decides how many rounds to run, when to
stop, or how to cache evidence across separate orchestration invocations -- all of that is the
Harness's own job (``agent-integration-harness/app/harness/recursive_candidate_search``), which
drives this package one round at a time via a dedicated subprocess runner, exactly like every
other Agent2<->Harness boundary in this project. This package only ever: (1) runs one bounded,
structurally-scored candidate search under whatever calibration evidence already exists
(reusing ``app.agent2.modularization_search``/``app.agent2.module_evaluation`` unchanged), (2)
decides, via an explicit, deterministic policy, which of that round's own candidates' modules
are worth a real calibration round trip, and (3) builds the request (or resolves a disclosed
``BOUNDARY_INADEQUATE`` locally) for whatever the gate selects.

Public API: ``run_candidate_search_round``, ``build_submodel`` (``round``);
``select_candidates_for_calibration``, ``could_change_ordering`` (``selection``);
``build_calibration_requests`` (``requests``);
``select_modules_for_functional_evaluation``, ``total_functional_weight``
(``functional_selection``); ``build_functional_evaluation_requests``
(``functional_requests``); ``serialize_round_result`` (``serialization``); every type
(``types``); ``CandidateOrchestrationError``, ``CandidateOrchestrationReferenceError``
(``errors``).

**Automatic Functional-Evaluation Selection and Caching increment** extends this package with a
second, genuinely separate gate (``FunctionalEvaluationSelectionPolicy``/``select_modules_for
_functional_evaluation``/``build_functional_evaluation_requests``), mirroring the calibration
gate exactly but deciding which candidates' modules are worth a real Agent 3 *functional-
evaluation* round trip (``DYNAMIC_ISOLATION``/``SENSITIVITY_COHERENCE``) instead of an Agent
3/Agent 4 *calibration* round trip. Still never calls Agent 3 directly; still never decides how
many rounds to run.
"""

from __future__ import annotations

from app.agent2.candidate_orchestration.errors import (
    CandidateOrchestrationError,
    CandidateOrchestrationReferenceError,
)
from app.agent2.candidate_orchestration.functional_requests import (
    build_functional_evaluation_requests,
)
from app.agent2.candidate_orchestration.functional_selection import (
    select_modules_for_functional_evaluation,
    total_functional_weight,
)
from app.agent2.candidate_orchestration.requests import build_calibration_requests
from app.agent2.candidate_orchestration.round import build_submodel, run_candidate_search_round
from app.agent2.candidate_orchestration.selection import (
    could_change_ordering,
    select_candidates_for_calibration,
)
from app.agent2.candidate_orchestration.serialization import serialize_round_result
from app.agent2.candidate_orchestration.types import (
    CalibrationDecision,
    CalibrationDecisionOutcome,
    CalibrationRunRequestEnvelope,
    CalibrationSelectionPolicy,
    CandidateSearchRoundResult,
    FunctionalEvaluationDecision,
    FunctionalEvaluationDecisionOutcome,
    FunctionalEvaluationRunRequestEnvelope,
    FunctionalEvaluationSelectionPolicy,
)

__all__ = [
    "CalibrationDecision",
    "CalibrationDecisionOutcome",
    "CalibrationRunRequestEnvelope",
    "CalibrationSelectionPolicy",
    "CandidateOrchestrationError",
    "CandidateOrchestrationReferenceError",
    "CandidateSearchRoundResult",
    "FunctionalEvaluationDecision",
    "FunctionalEvaluationDecisionOutcome",
    "FunctionalEvaluationRunRequestEnvelope",
    "FunctionalEvaluationSelectionPolicy",
    "build_calibration_requests",
    "build_functional_evaluation_requests",
    "build_submodel",
    "could_change_ordering",
    "run_candidate_search_round",
    "select_candidates_for_calibration",
    "select_modules_for_functional_evaluation",
    "serialize_round_result",
    "total_functional_weight",
]
