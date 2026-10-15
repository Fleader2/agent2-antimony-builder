"""Antimony Generation (Increment 9).

Public API: ``generate_antimony``, and (Module Decomposition/Modularization
Reconciliation increment) ``generate_module_artifacts`` -- the explicit, opt-in entry point
for module-view/standalone-submodel Antimony generation, naming one selected
``ModelModularization``. See ``docs/12_antimony_generation.md`` for the full contract.
"""

from __future__ import annotations

from app.agent2.antimony.errors import (
    AntimonyGenerationError,
    AntimonyIdentifierCollisionError,
    AntimonyReferenceError,
    UnresolvedKineticExpressionError,
    UnsupportedAntimonySerializationError,
)
from app.agent2.antimony.generator import generate_antimony, generate_module_artifacts

__all__ = [
    "AntimonyGenerationError",
    "AntimonyIdentifierCollisionError",
    "AntimonyReferenceError",
    "UnresolvedKineticExpressionError",
    "UnsupportedAntimonySerializationError",
    "generate_antimony",
    "generate_module_artifacts",
]
