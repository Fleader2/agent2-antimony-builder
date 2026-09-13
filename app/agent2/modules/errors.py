"""Module Decomposition's own error hierarchy (Increment 7).

**Missing or ambiguous boundary evidence is never an exception.** A
network with no boundary evidence at all still decomposes -- typically
into one module. These errors exist only for a genuine structural/
programming inconsistency: a caller passing the wrong type, inputs that
do not describe the same network, or a produced decomposition that fails
to reference real network/law/parameter/boundary ids.

All subclass `ValueError`, mirroring
`app.agent2.boundaries.errors.BoundaryAssessmentError`'s identical
convention.
"""

from __future__ import annotations


class ModuleDecompositionError(ValueError):
    """Base class for every Module Decomposition failure."""


class ModuleDecompositionReferenceError(ModuleDecompositionError):
    """A cross-reference needed to decompose or validate a module did not resolve.

    Includes input pairs whose `network_id`s disagree, and the defensive
    post-decomposition check that every module/decomposition's referenced
    reaction/species/compartment/enzyme-state/kinetic-law/parameter/
    boundary ids actually exist. Should not normally occur -- all inputs
    already validate their own internal references.
    """


class UnsupportedModuleDecompositionInputError(ModuleDecompositionError):
    """`decompose_network` (or an internal helper) received the wrong type."""


__all__ = [
    "ModuleDecompositionError",
    "ModuleDecompositionReferenceError",
    "UnsupportedModuleDecompositionInputError",
]
