"""Recursive Agent-4-Assisted Candidate Search Orchestration: domain errors."""

from __future__ import annotations


class CandidateOrchestrationError(ValueError):
    """Base error for this package -- a malformed policy or request, never a disclosed
    scientific outcome (which is always a typed result, never an exception)."""


class CandidateOrchestrationReferenceError(CandidateOrchestrationError):
    """Raised for a reference to something that does not exist (an unknown candidate/module id,
    a submodel module id absent from the seed modularization)."""


__all__ = ["CandidateOrchestrationError", "CandidateOrchestrationReferenceError"]
