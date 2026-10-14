"""Scoped-Build Support increment: the Workbench -> Agent 2 ``ModelBuildRequest`` contract and
the scoping engine that applies it to an assembled ``FullNetwork``.

See ``app.agent2.build_request.types`` for the contract shape and
``app.agent2.build_request.scope`` for the scoping policy.
"""

from __future__ import annotations

from app.agent2.build_request.errors import (
    BuildRequestContractVersionError,
    BuildRequestContradictionError,
    BuildRequestEmptyScopeError,
    BuildRequestError,
)
from app.agent2.build_request.scope import ScopedNetworkResult, apply_build_request_scope
from app.agent2.build_request.types import (
    AGENT2_BUILD_REQUEST_CONTRACT_VERSION,
    BuildRequestGeneProteinRole,
    BuildRequestPathwayRole,
    BuildRequestReactionRole,
    BuildRequestSpeciesRole,
    EntityReference,
    ModelBuildRequest,
    PathwayReference,
    build_request_from_dict,
)

__all__ = [
    "AGENT2_BUILD_REQUEST_CONTRACT_VERSION",
    "BuildRequestContractVersionError",
    "BuildRequestContradictionError",
    "BuildRequestEmptyScopeError",
    "BuildRequestError",
    "BuildRequestGeneProteinRole",
    "BuildRequestPathwayRole",
    "BuildRequestReactionRole",
    "BuildRequestSpeciesRole",
    "EntityReference",
    "ModelBuildRequest",
    "PathwayReference",
    "ScopedNetworkResult",
    "apply_build_request_scope",
    "build_request_from_dict",
]
