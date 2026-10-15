"""Weight-Space Exploration and Stable Boundary Discovery's own error hierarchy.

Mirrors every sibling package's identical convention (e.g.
``app.agent2.module_evaluation.errors``): all subclass ``ValueError``, and exist only for a
genuine structural/programming inconsistency -- never for an empty high-scoring solution set
or an ambiguous boundary, both of which are normal, disclosed outcomes, never raised errors.
"""

from __future__ import annotations


class WeightSpaceExplorationError(ValueError):
    """Base class for every Weight-Space Exploration and Stable Boundary Discovery failure."""


class WeightSpaceExplorationReferenceError(WeightSpaceExplorationError):
    """A cross-reference needed for exploration or stability analysis did not resolve (an
    unknown ``modularization_id``, a malformed weight-grid specification, or a ``model`` that
    is not a real ``ModelSpecification``)."""


__all__ = ["WeightSpaceExplorationError", "WeightSpaceExplorationReferenceError"]
