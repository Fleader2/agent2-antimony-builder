"""Input validation for Parameter Declaration / Initialization (Increment 5).

`KineticLawAssignmentSet`/`FullNetwork` already guarantee their own
internal reference integrity -- this module never repeats that work. Its
job is narrower: confirm the *inputs themselves* are the right types
before `app.agent2.parameters.builder` does anything with them.
"""

from __future__ import annotations

from app.agent2.kinetics.types import KineticLawAssignmentSet
from app.agent2.parameters.errors import UnsupportedParameterDeclarationInputError
from app.agent2.types import FullNetwork


def require_kinetic_law_assignment_set(
    assignments: KineticLawAssignmentSet,
) -> KineticLawAssignmentSet:
    """Confirm ``assignments`` is actually a ``KineticLawAssignmentSet``."""
    if not isinstance(assignments, KineticLawAssignmentSet):
        raise UnsupportedParameterDeclarationInputError(
            f"declare_parameters requires a KineticLawAssignmentSet, got {assignments!r}"
        )
    return assignments


def require_full_network(network: FullNetwork) -> FullNetwork:
    """Confirm ``network`` is actually a ``FullNetwork``."""
    if not isinstance(network, FullNetwork):
        raise UnsupportedParameterDeclarationInputError(
            f"declare_parameters requires a FullNetwork, got {network!r}"
        )
    return network


__all__ = ["require_full_network", "require_kinetic_law_assignment_set"]
