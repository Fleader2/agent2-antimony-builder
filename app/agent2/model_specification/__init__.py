"""ModelSpecification Assembly (Increment 8).

Public API: ``assemble_model_specification``. See
``docs/11_model_specification_assembly.md`` for the full contract.
"""

from __future__ import annotations

from app.agent2.model_specification.assembler import assemble_model_specification
from app.agent2.model_specification.errors import (
    IncompatibleArtifactVersionError,
    ModelSpecificationAssemblyError,
    ModelSpecificationReferenceError,
    UnsupportedModelSpecificationInputError,
)

__all__ = [
    "IncompatibleArtifactVersionError",
    "ModelSpecificationAssemblyError",
    "ModelSpecificationReferenceError",
    "UnsupportedModelSpecificationInputError",
    "assemble_model_specification",
]
