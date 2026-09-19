"""Antimony Generation's own error hierarchy (Increment 9).

**Missing or unresolved kinetics is never an exception.** An unresolved
kinetic-law expression, an unresolved reversibility flag, a valueless
parameter, or a module lacking explicit boundary interfaces are all
normal, expected states -- they are disclosed via
``AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS``/
``.VIEW_ONLY`` and ``unresolved_kinetic_law_ids``, never raised as
errors. These errors exist only for a genuine structural/programming
inconsistency: a caller passing the wrong type, a reference that does not
resolve against the supplied ``ModelSpecification``, or a serializer
integrity failure (e.g. a closed-vocabulary substitution left an
unexpected symbol behind) that should never occur given a valid input.

All subclass ``ValueError``, mirroring every other Agent 2 package's own
error-hierarchy convention (see
``app.agent2.model_specification.errors``/``app.agent2.modules.errors``).
"""

from __future__ import annotations


class AntimonyGenerationError(ValueError):
    """Base class for every Antimony Generation failure."""


class UnsupportedAntimonySerializationError(AntimonyGenerationError):
    """``generate_antimony`` (or an internal helper) received the wrong type."""


class AntimonyReferenceError(AntimonyGenerationError):
    """A reference needed to serialize an artifact did not resolve against the supplied
    ``ModelSpecification``. Should not normally occur -- ``ModelSpecification`` already
    validates its own internal reference integrity at construction time.
    """


class AntimonyIdentifierCollisionError(AntimonyGenerationError):
    """Two entities in the same Antimony symbol-table category resolved to the same
    identifier even after this package's own deterministic collision-resolution policy.

    Should never occur given ``app.agent2.antimony.naming``'s own collision
    resolution (which always produces a unique identifier per unique
    source id) -- reserved for a serializer-integrity backstop check.
    """


class UnresolvedKineticExpressionError(AntimonyGenerationError):
    """A serializer-integrity failure while rendering a *resolved* kinetic-law expression --
    never raised merely because a law is unresolved (that is the normal, disclosed
    ``NON_EXECUTABLE_UNRESOLVED_KINETICS`` state, not an error). Raised only if a
    closed-vocabulary token substitution left a character behind that is not a valid,
    Antimony-safe identifier/operator character -- a structural inconsistency between a
    ``KineticLawSpecification``'s ``expression`` and its own declared
    ``parameter_ids``/``species_ids``, which should never happen given a valid
    ``ModelSpecification``.
    """


__all__ = [
    "AntimonyGenerationError",
    "AntimonyIdentifierCollisionError",
    "AntimonyReferenceError",
    "UnresolvedKineticExpressionError",
    "UnsupportedAntimonySerializationError",
]
