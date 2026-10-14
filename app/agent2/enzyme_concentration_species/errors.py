"""Explicit Enzyme Concentration Representation's own error hierarchy.

Mirrors every sibling package's identical convention (e.g.
``app.agent2.enzyme_state_dynamics.errors``): all subclass ``ValueError``, and exist only
for a genuine structural/programming inconsistency, never for missing or ambiguous curated
data (a protein with no resolvable compartment, or an unresolved enzyme concentration, is a
normal, disclosed outcome -- never a raised error).
"""

from __future__ import annotations


class EnzymeConcentrationSpeciesError(ValueError):
    """Base class for every Explicit Enzyme Concentration Representation failure."""


class EnzymeConcentrationSpeciesReferenceError(EnzymeConcentrationSpeciesError):
    """A cross-reference needed to build enzyme-concentration species did not resolve, or two
    inputs that must describe the same network do not (``network_id`` mismatch)."""


__all__ = ["EnzymeConcentrationSpeciesError", "EnzymeConcentrationSpeciesReferenceError"]
