"""Input validation for Quantitative Context Resolution.

``FullNetwork`` already guarantees its own internal reference integrity -- this
module never repeats that work. Its job is narrower: confirm the input itself is
the right type before ``app.agent2.quantitative_context.resolver`` does anything
with it. Mirrors ``app.agent2.kinetics.validation``'s identical convention.
"""

from __future__ import annotations

from app.agent2.quantitative_context.errors import UnsupportedQuantitativeContextInputError
from app.agent2.types import FullNetwork


def require_full_network(network: FullNetwork) -> FullNetwork:
    """Confirm ``network`` is actually a ``FullNetwork``."""
    if not isinstance(network, FullNetwork):
        raise UnsupportedQuantitativeContextInputError(
            f"resolve_enzyme_concentrations requires a FullNetwork, got {network!r}"
        )
    return network


__all__ = ["require_full_network"]
