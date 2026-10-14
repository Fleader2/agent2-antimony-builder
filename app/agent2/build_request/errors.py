"""Scoped-Build Support increment: the build-request error hierarchy.

All subclass ``ValueError``, mirroring every other ``app.agent2`` error
hierarchy's own convention (e.g. ``app.agent2.network.errors
.NetworkAssemblyError``) -- a caller that only catches ``ValueError``
still catches every build-request failure without needing to know this
module exists.
"""

from __future__ import annotations


class BuildRequestError(ValueError):
    """Base class for every ``ModelBuildRequest`` scoping failure."""


class BuildRequestContractVersionError(BuildRequestError):
    """A ``ModelBuildRequest`` artifact's own ``contract_version`` does not match
    ``AGENT2_BUILD_REQUEST_CONTRACT_VERSION`` -- never silently accepted or coerced.
    """


class BuildRequestContradictionError(BuildRequestError):
    """A ``ModelBuildRequest`` names the same reaction as both ``REQUIRED`` and
    ``EXCLUDED`` -- a contradictory constraint set, rejected deterministically rather
    than resolved by an arbitrary tie-break.
    """


class BuildRequestEmptyScopeError(BuildRequestError):
    """A ``ModelBuildRequest``'s own constraints resolved to zero retained reactions.

    Every later Agent 2 stage (characterization, kinetic-law assignment, module
    decomposition, ...) assumes a non-empty network -- rejected deterministically here,
    rather than passed through to a stage that was never designed for, and never tested
    against, an empty ``FullNetwork``.
    """


__all__ = [
    "BuildRequestContractVersionError",
    "BuildRequestContradictionError",
    "BuildRequestEmptyScopeError",
    "BuildRequestError",
]
