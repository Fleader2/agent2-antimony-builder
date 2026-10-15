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
``build_calibration_requests`` (``requests``); ``serialize_round_result`` (``serialization``);
every type (``types``); ``CandidateOrchestrationError``,
``CandidateOrchestrationReferenceError`` (``errors``).
"""

from __future__ import annotations

from app.agent2.candidate_orchestration.errors import (
    CandidateOrchestrationError,
    CandidateOrchestrationReferenceError,
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
)

__all__ = [
    "CalibrationDecision",
    "CalibrationDecisionOutcome",
    "CalibrationRunRequestEnvelope",
    "CalibrationSelectionPolicy",
    "CandidateOrchestrationError",
    "CandidateOrchestrationReferenceError",
    "CandidateSearchRoundResult",
    "build_calibration_requests",
    "build_submodel",
    "could_change_ordering",
    "run_candidate_search_round",
    "select_candidates_for_calibration",
    "serialize_round_result",
]
