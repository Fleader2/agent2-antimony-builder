"""Model Modularization increment: a derived layer on top of the canonical whole-network
model.

Public API: ``ModuleConnection``/``derive_cross_module_connections``, and (Module
Decomposition/Modularization Reconciliation increment) ``ModularizationBundle``/
``modularizations_from_decomposition_set`` -- converts the pre-existing heuristic module
decomposition algorithm's output into this same unified representation. The modularization
types themselves (``ModelModularization``, ``ModelModule``, ``ModuleMembership``,
``ModulePort``, and their enums) live in ``app.agent2.types`` alongside every other canonical
contract type -- this package holds only real, computed behavior, never a second copy of the
types. See ``docs/22_model_modularization.md``/
``docs/26_module_decomposition_modularization_reconciliation.md`` for the full design.
"""

from __future__ import annotations

from app.agent2.modularization.adapter import (
    ModularizationBundle,
    modularizations_from_decomposition_set,
)
from app.agent2.modularization.derivation import ModuleConnection, derive_cross_module_connections

__all__ = [
    "ModularizationBundle",
    "ModuleConnection",
    "derive_cross_module_connections",
    "modularizations_from_decomposition_set",
]
