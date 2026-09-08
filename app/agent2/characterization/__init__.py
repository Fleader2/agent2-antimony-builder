"""Reaction and Enzyme-State Characterization (Increment 3).

Public API: ``characterize_full_network``. See
``docs/06_reaction_enzyme_state_characterization.md`` for the full
contract.
"""

from __future__ import annotations

from app.agent2.characterization.characterization import characterize_full_network
from app.agent2.characterization.errors import (
    CharacterizationError,
    CharacterizationReferenceError,
    ReactionCharacterizationError,
    UnsupportedCharacterizationInputError,
)
from app.agent2.characterization.types import (
    CharacterizationFlag,
    EnzymeStateCharacterization,
    NetworkCharacterization,
    ReactionCharacterization,
    ReactionClass,
    UnresolvedFeature,
)

__all__ = [
    "CharacterizationError",
    "CharacterizationFlag",
    "CharacterizationReferenceError",
    "EnzymeStateCharacterization",
    "NetworkCharacterization",
    "ReactionCharacterization",
    "ReactionCharacterizationError",
    "ReactionClass",
    "UnresolvedFeature",
    "UnsupportedCharacterizationInputError",
    "characterize_full_network",
]
