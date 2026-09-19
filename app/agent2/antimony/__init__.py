"""Antimony Generation (Increment 9).

Public API: ``generate_antimony``. See ``docs/12_antimony_generation.md``
for the full contract.
"""

from __future__ import annotations

from app.agent2.antimony.errors import (
    AntimonyGenerationError,
    AntimonyIdentifierCollisionError,
    AntimonyReferenceError,
    UnresolvedKineticExpressionError,
    UnsupportedAntimonySerializationError,
)
from app.agent2.antimony.generator import generate_antimony

__all__ = [
    "AntimonyGenerationError",
    "AntimonyIdentifierCollisionError",
    "AntimonyReferenceError",
    "UnresolvedKineticExpressionError",
    "UnsupportedAntimonySerializationError",
    "generate_antimony",
]
