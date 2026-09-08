"""Parameter Declaration / Initialization's own error hierarchy (Increment 5).

**Missing or ambiguous curated numeric evidence is never an exception.**
No matching curated measurement, multiple conflicting measurements, or an
`UNASSIGNED`/tentative kinetic-law assignment always produce a
`PLACEHOLDER` (or, for `UNASSIGNED`, simply no parameter at all) --
never a raised error. These errors exist only for a genuine structural/
programming inconsistency: a caller passing the wrong type, a
`KineticLawAssignmentSet`/`FullNetwork` pair that do not describe the same
network, or a declared parameter that fails to trace back to a real
`KineticLawAssignment`.

All subclass `ValueError`, mirroring
`app.agent2.kinetics.errors.KineticLawAssignmentError`'s identical
convention.
"""

from __future__ import annotations


class ParameterDeclarationError(ValueError):
    """Base class for every Parameter Declaration / Initialization failure."""


class ParameterReferenceError(ParameterDeclarationError):
    """A cross-reference needed to declare or resolve a parameter did not resolve.

    Includes a `KineticLawAssignmentSet`/`FullNetwork` pair whose
    `network_id`s do not match, and the defensive post-declaration check
    that every declared parameter's `kinetic_law_assignment_id` names a
    real assignment. Should not normally occur -- both inputs already
    validate their own internal references.
    """


class UnsupportedParameterDeclarationInputError(ParameterDeclarationError):
    """`declare_parameters` (or an internal helper) received the wrong type."""


__all__ = [
    "ParameterDeclarationError",
    "ParameterReferenceError",
    "UnsupportedParameterDeclarationInputError",
]
