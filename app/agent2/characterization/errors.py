"""Reaction and Enzyme-State Characterization's own error hierarchy (Increment 3).

**Expected incomplete biology is never an exception.** Missing curated
data (no catalyst, no kinetic measurement, unknown reversibility, ...)
always produces an ``UnresolvedFeature`` on the resulting
``ReactionCharacterization`` -- never a raised error. These errors exist
only for a genuine structural/programming inconsistency: a caller passing
the wrong type, or (should it ever happen despite ``FullNetwork`` already
validating its own references) a cross-reference that does not resolve.

All subclass ``ValueError``, mirroring
``app.agent2.network.errors.NetworkAssemblyError``'s identical convention.
"""

from __future__ import annotations


class CharacterizationError(ValueError):
    """Base class for every Reaction and Enzyme-State Characterization failure."""


class ReactionCharacterizationError(CharacterizationError):
    """A single reaction could not be characterized due to a structural inconsistency.

    Never raised for merely incomplete curated data -- see module
    docstring.
    """


class CharacterizationReferenceError(CharacterizationError):
    """A cross-reference within an already-validated ``FullNetwork`` did not resolve.

    Should not normally occur -- ``FullNetwork.__post_init__``
    (``app.agent2.types._validate_full_network_references``) already
    validates every cross-reference this package reads. This exists as a
    defensive backstop, never as this package's primary validation
    mechanism.
    """


class UnsupportedCharacterizationInputError(CharacterizationError):
    """``characterize_full_network`` (or an internal helper) received the wrong type."""


__all__ = [
    "CharacterizationError",
    "CharacterizationReferenceError",
    "ReactionCharacterizationError",
    "UnsupportedCharacterizationInputError",
]
