"""Input validation for Kinetic-Law Assignment (Increment 4).

``FullNetwork``/``NetworkCharacterization`` already guarantee their own
internal reference integrity -- this module never repeats that work. Its
job is narrower: confirm the *inputs themselves* are the right types
before ``app.agent2.kinetics.selector`` does anything with them. The
``network_id`` cross-check and the "every reaction covered" backstop live
in ``selector.assign_kinetic_laws`` itself (they need both inputs and the
computed output together, not just one input in isolation).
"""

from __future__ import annotations

from app.agent2.characterization.types import NetworkCharacterization
from app.agent2.kinetics.errors import UnsupportedKineticLawInputError
from app.agent2.types import FullNetwork


def require_network_characterization(
    characterization: NetworkCharacterization,
) -> NetworkCharacterization:
    """Confirm ``characterization`` is actually a ``NetworkCharacterization``."""
    if not isinstance(characterization, NetworkCharacterization):
        raise UnsupportedKineticLawInputError(
            f"assign_kinetic_laws requires a NetworkCharacterization, got {characterization!r}"
        )
    return characterization


def require_full_network(network: FullNetwork) -> FullNetwork:
    """Confirm ``network`` is actually a ``FullNetwork``."""
    if not isinstance(network, FullNetwork):
        raise UnsupportedKineticLawInputError(
            f"assign_kinetic_laws requires a FullNetwork, got {network!r}"
        )
    return network


__all__ = ["require_full_network", "require_network_characterization"]
