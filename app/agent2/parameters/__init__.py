"""Parameter Declaration / Initialization (Increment 5).

Public API: ``declare_parameters``. See
``docs/08_parameter_declaration_initialization.md`` for the full
contract.
"""

from __future__ import annotations

from app.agent2.parameters.builder import declare_parameters
from app.agent2.parameters.errors import (
    ParameterDeclarationError,
    ParameterReferenceError,
    UnsupportedParameterDeclarationInputError,
)
from app.agent2.parameters.types import ParameterDeclarationSet

__all__ = [
    "ParameterDeclarationError",
    "ParameterDeclarationSet",
    "ParameterReferenceError",
    "UnsupportedParameterDeclarationInputError",
    "declare_parameters",
]
