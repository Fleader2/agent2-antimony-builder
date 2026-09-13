"""Module Decomposition (Increment 7).

Public API: ``decompose_network``. See
``docs/10_module_decomposition.md`` for the full contract.
"""

from __future__ import annotations

from app.agent2.modules.decomposer import decompose_network
from app.agent2.modules.errors import (
    ModuleDecompositionError,
    ModuleDecompositionReferenceError,
    UnsupportedModuleDecompositionInputError,
)
from app.agent2.modules.types import ModuleDecompositionSet

__all__ = [
    "ModuleDecompositionError",
    "ModuleDecompositionReferenceError",
    "ModuleDecompositionSet",
    "UnsupportedModuleDecompositionInputError",
    "decompose_network",
]
