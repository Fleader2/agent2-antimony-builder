"""Model Modularization increment: a derived layer on top of the canonical whole-network
model.

Public API: ``ModuleConnection``/``derive_cross_module_connections``. The modularization
types themselves (``ModelModularization``, ``ModelModule``, ``ModuleMembership``,
``ModulePort``, and their enums) live in ``app.agent2.types`` alongside every other canonical
contract type -- this package holds only the one piece of real, computed behavior (deriving
cross-module connections from a modularization's own ports), never a second copy of the types.
See ``docs/22_model_modularization.md`` for the full design.
"""

from __future__ import annotations

from app.agent2.modularization.derivation import ModuleConnection, derive_cross_module_connections

__all__ = ["ModuleConnection", "derive_cross_module_connections"]
