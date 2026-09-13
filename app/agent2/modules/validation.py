"""Input validation for Module Decomposition (Increment 7).

`FullNetwork`/`KineticLawAssignmentSet`/`ParameterDeclarationSet`/
`BoundaryAssessmentSet` already guarantee their own internal reference
integrity -- this module never repeats that work. Its job is narrower:
confirm the *inputs themselves* are the right types before
`app.agent2.modules.decomposer` does anything with them.
"""

from __future__ import annotations

from app.agent2.boundaries.types import BoundaryAssessmentSet
from app.agent2.kinetics.types import KineticLawAssignmentSet
from app.agent2.modules.errors import UnsupportedModuleDecompositionInputError
from app.agent2.parameters.types import ParameterDeclarationSet
from app.agent2.types import FullNetwork


def require_full_network(network: FullNetwork) -> FullNetwork:
    if not isinstance(network, FullNetwork):
        raise UnsupportedModuleDecompositionInputError(
            f"decompose_network requires a FullNetwork, got {network!r}"
        )
    return network


def require_kinetic_law_assignment_set(
    kinetic_laws: KineticLawAssignmentSet,
) -> KineticLawAssignmentSet:
    if not isinstance(kinetic_laws, KineticLawAssignmentSet):
        raise UnsupportedModuleDecompositionInputError(
            f"decompose_network requires a KineticLawAssignmentSet, got {kinetic_laws!r}"
        )
    return kinetic_laws


def require_parameter_declaration_set(
    parameters: ParameterDeclarationSet,
) -> ParameterDeclarationSet:
    if not isinstance(parameters, ParameterDeclarationSet):
        raise UnsupportedModuleDecompositionInputError(
            f"decompose_network requires a ParameterDeclarationSet, got {parameters!r}"
        )
    return parameters


def require_boundary_assessment_set(boundaries: BoundaryAssessmentSet) -> BoundaryAssessmentSet:
    if not isinstance(boundaries, BoundaryAssessmentSet):
        raise UnsupportedModuleDecompositionInputError(
            f"decompose_network requires a BoundaryAssessmentSet, got {boundaries!r}"
        )
    return boundaries


__all__ = [
    "require_boundary_assessment_set",
    "require_full_network",
    "require_kinetic_law_assignment_set",
    "require_parameter_declaration_set",
]
