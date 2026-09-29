"""Enzyme-State Population Dynamics and Conservation's own error hierarchy (Multi-Context
Catalytic Rate Composition increment, Stage 2).

Mirrors every sibling package's identical convention (e.g.
``app.agent2.parameters.errors``): all subclass ``ValueError``, and exist only for a
genuine structural/programming inconsistency, never for missing or ambiguous curated
data (a protein with no resolvable enzyme-state pool, or a state with no resolvable
initial concentration, is a normal, disclosed outcome -- never a raised error).
"""

from __future__ import annotations


class EnzymeStateDynamicsError(ValueError):
    """Base class for every Enzyme-State Population Dynamics and Conservation failure."""


class EnzymeStateDynamicsReferenceError(EnzymeStateDynamicsError):
    """A cross-reference needed to build enzyme-state dynamics did not resolve, or two
    inputs that must describe the same network do not (``network_id`` mismatch)."""


__all__ = ["EnzymeStateDynamicsError", "EnzymeStateDynamicsReferenceError"]
