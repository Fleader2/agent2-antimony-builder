"""Input validation for Heuristic Boundary Assessment (Increment 6).

`FullNetwork`/`NetworkCharacterization`/`KineticLawAssignmentSet`/
`ParameterDeclarationSet` already guarantee their own internal reference
integrity -- this module never repeats that work. Its job is narrower:
confirm the *inputs themselves* are the right types before
`app.agent2.boundaries.assessor` does anything with them.
"""

from __future__ import annotations

from app.agent2.boundaries.errors import UnsupportedBoundaryInputError
from app.agent2.characterization.types import NetworkCharacterization
from app.agent2.kinetics.types import KineticLawAssignmentSet
from app.agent2.parameters.types import ParameterDeclarationSet
from app.agent2.types import FullNetwork


def require_full_network(network: FullNetwork) -> FullNetwork:
    if not isinstance(network, FullNetwork):
        raise UnsupportedBoundaryInputError(
            f"assess_boundaries requires a FullNetwork, got {network!r}"
        )
    return network


def require_network_characterization(
    characterization: NetworkCharacterization,
) -> NetworkCharacterization:
    if not isinstance(characterization, NetworkCharacterization):
        raise UnsupportedBoundaryInputError(
            f"assess_boundaries requires a NetworkCharacterization, got {characterization!r}"
        )
    return characterization


def require_kinetic_law_assignment_set(
    kinetic_laws: KineticLawAssignmentSet,
) -> KineticLawAssignmentSet:
    if not isinstance(kinetic_laws, KineticLawAssignmentSet):
        raise UnsupportedBoundaryInputError(
            f"assess_boundaries requires a KineticLawAssignmentSet, got {kinetic_laws!r}"
        )
    return kinetic_laws


def require_parameter_declaration_set(
    parameters: ParameterDeclarationSet,
) -> ParameterDeclarationSet:
    if not isinstance(parameters, ParameterDeclarationSet):
        raise UnsupportedBoundaryInputError(
            f"assess_boundaries requires a ParameterDeclarationSet, got {parameters!r}"
        )
    return parameters


__all__ = [
    "require_full_network",
    "require_kinetic_law_assignment_set",
    "require_network_characterization",
    "require_parameter_declaration_set",
]
