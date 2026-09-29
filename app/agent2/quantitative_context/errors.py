"""Quantitative Context Resolution's own error hierarchy.

Mirrors ``app.agent2.kinetics.errors``'s identical convention: incomplete or
ambiguous curated quantitative data is never an exception -- it always produces
an unresolved ``QuantitativeContextResolutionOutcome`` instead (see
``app.agent2.quantitative_context.types``). These errors exist only for a
genuine structural/programming inconsistency: a caller passing the wrong type,
or a ``network_id`` mismatch between a ``FullNetwork`` and an already-computed
``QuantitativeContextResolutionSet``.
"""

from __future__ import annotations


class QuantitativeContextError(ValueError):
    """Base class for every Quantitative Context Resolution failure."""


class QuantitativeContextReferenceError(QuantitativeContextError):
    """A cross-reference needed to resolve/attach quantitative context did not
    resolve -- e.g. a ``FullNetwork``/``QuantitativeContextResolutionSet`` pair
    whose ``network_id``s do not match."""


class UnsupportedQuantitativeContextInputError(QuantitativeContextError):
    """A public entry point in this package received the wrong type."""


__all__ = [
    "QuantitativeContextError",
    "QuantitativeContextReferenceError",
    "UnsupportedQuantitativeContextInputError",
]
