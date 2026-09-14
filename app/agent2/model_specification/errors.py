"""ModelSpecification Assembly's own error hierarchy (Increment 8).

**Missing or incomplete biological information is never an exception.**
An `UNASSIGNED` kinetic law, a `PLACEHOLDER` parameter, or a preserved
`MEDIUM` candidate boundary are all normal, expected states -- they are
disclosed via `KineticLawType.UNASSIGNED`/`ParameterSource.PLACEHOLDER`/
`ModuleDecomposition.candidate_boundary_ids` and `ModelAssumption`
records, never raised as errors. These errors exist only for a genuine
structural/programming inconsistency: a caller passing the wrong type,
inputs that do not describe the same network, inputs produced under
incompatible policy versions, more or fewer than one decomposition under
the current v1 policy, or an assembled `ModelSpecification` that fails to
reference real ids.

All subclass `ValueError`, mirroring
`app.agent2.modules.errors.ModuleDecompositionError`'s identical
convention.
"""

from __future__ import annotations


class ModelSpecificationAssemblyError(ValueError):
    """Base class for every ModelSpecification Assembly failure."""


class UnsupportedModelSpecificationInputError(ModelSpecificationAssemblyError):
    """`assemble_model_specification` (or an internal helper) received the wrong type."""


class IncompatibleArtifactVersionError(ModelSpecificationAssemblyError):
    """Two or more input artifacts disagree on `network_id` or a shared policy version.

    Assembly never silently mixes artifacts produced under different
    policy versions or from different networks -- see
    ``docs/11_model_specification_assembly.md`` §18.
    """


class ModelSpecificationReferenceError(ModelSpecificationAssemblyError):
    """A cross-reference needed to assemble or validate the model did not resolve, or the
    module-decomposition input did not carry exactly one decomposition (Increment 7 v1's own
    invariant). Should not normally occur -- all five inputs already validate their own
    internal references.
    """


__all__ = [
    "IncompatibleArtifactVersionError",
    "ModelSpecificationAssemblyError",
    "ModelSpecificationReferenceError",
    "UnsupportedModelSpecificationInputError",
]
