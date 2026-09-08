"""Input validation for Reaction and Enzyme-State Characterization (Increment 3).

``FullNetwork.__post_init__`` already guarantees every internal
cross-reference within it resolves (``app.agent2.types
._validate_full_network_references``) -- this module never repeats that
work. Its own job is narrower: confirm the *input itself* is a real
``FullNetwork`` before ``app.agent2.characterization.characterization``
does anything with it, and provide a defensive resolution helper for the
rare case a reference does not resolve despite that guarantee (a
programming-error backstop, never this package's primary validation
mechanism -- see ``app.agent2.characterization.errors``).
"""

from __future__ import annotations

from collections.abc import Mapping

from app.agent2.characterization.errors import (
    CharacterizationReferenceError,
    UnsupportedCharacterizationInputError,
)
from app.agent2.types import FullNetwork


def require_full_network(network: FullNetwork) -> FullNetwork:
    """Confirm ``network`` is actually a ``FullNetwork`` before characterizing it."""
    if not isinstance(network, FullNetwork):
        raise UnsupportedCharacterizationInputError(
            f"characterize_full_network requires a FullNetwork, got {network!r}"
        )
    return network


def require_resolved[T](registry: Mapping[str, T], entity_id: str, *, entity_type: str) -> T:
    """Resolve ``entity_id`` in ``registry``, or raise a defensive backstop error.

    Should never actually raise given an already-validated ``FullNetwork``
    -- see module docstring.
    """
    try:
        return registry[entity_id]
    except KeyError as exc:
        raise CharacterizationReferenceError(
            f"characterization could not resolve {entity_type} {entity_id!r} -- "
            "FullNetwork should have already guaranteed this reference resolves"
        ) from exc


__all__ = ["require_full_network", "require_resolved"]
