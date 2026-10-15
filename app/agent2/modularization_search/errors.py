"""Candidate Modularization Search's own error hierarchy.

Mirrors every sibling package's identical convention: all subclass ``ValueError``, and exist
only for a genuine structural/programming inconsistency -- never for a proposal that simply
could not be generated (an operator finding no valid move, a candidate violating a hard
constraint) or evidence that is unavailable, both of which are normal, disclosed outcomes
(``RejectedCandidate``, ``ModularizationCriterionScore.available=False``), never raised errors.
"""

from __future__ import annotations


class ModularizationSearchError(ValueError):
    """Base class for every Candidate Modularization Search failure."""


class ModularizationSearchReferenceError(ModularizationSearchError):
    """A cross-reference needed to run the search did not resolve (an unknown
    ``seed_modularization_id``, or a ``model`` that is not a real ``ModelSpecification``)."""


__all__ = ["ModularizationSearchError", "ModularizationSearchReferenceError"]
