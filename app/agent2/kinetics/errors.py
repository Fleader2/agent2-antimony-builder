"""Kinetic-Law Assignment's own error hierarchy (Increment 4).

**Incomplete or ambiguous curated biology is never an exception.** No
curated law, a structural rule that does not apply, or conflicting
reported laws always produce a ``KineticLawType.UNASSIGNED`` assignment
-- never a raised error. These errors exist only for a genuine
structural/programming inconsistency: a caller passing the wrong type, a
``NetworkCharacterization``/``FullNetwork`` pair that do not describe the
same network, or a cross-reference that does not resolve.

All subclass ``ValueError``, mirroring
``app.agent2.characterization.errors.CharacterizationError``'s identical
convention.
"""

from __future__ import annotations


class KineticLawAssignmentError(ValueError):
    """Base class for every Kinetic-Law Assignment failure."""


class KineticLawReferenceError(KineticLawAssignmentError):
    """A cross-reference needed to assign a kinetic law did not resolve.

    Includes a ``NetworkCharacterization``/``FullNetwork`` pair whose
    ``network_id``s do not match, and the defensive post-assignment check
    that every reaction was actually covered. Should not normally occur --
    ``FullNetwork``/``NetworkCharacterization`` already validate their own
    internal references.
    """


class UnsupportedKineticLawInputError(KineticLawAssignmentError):
    """``assign_kinetic_laws`` (or an internal helper) received the wrong type."""


__all__ = [
    "KineticLawAssignmentError",
    "KineticLawReferenceError",
    "UnsupportedKineticLawInputError",
]
