"""Whole-Network Assembly's own error hierarchy (Increment 2).

Every error here is deterministic and raised only for a genuine structural
problem in the Agent 1 handoff itself -- never for a scientific or
heuristic judgment. ``assemble_full_network`` never silently repairs,
drops, or reinterprets inconsistent data; it raises one of these instead
(``docs/05_whole_network_assembly.md``, "Validation rules").

All subclass ``ValueError`` so a caller that only catches ``ValueError``
(the convention every ``app.agent2.types`` contract's own ``__post_init__``
already uses) still catches every assembly failure without needing to know
this module exists.
"""

from __future__ import annotations


class NetworkAssemblyError(ValueError):
    """Base class for every Whole-Network Assembly failure."""


class DuplicateCuratedIdentifierError(NetworkAssemblyError):
    """Two curated records of the same category share an id the handoff itself assigned.

    Never raised for a compound appearing in more than one reaction
    participant (expected and handled by species deduplication, see
    ``app.agent2.network.builder``) -- only for two distinct
    ``Curated*`` records (e.g. two ``CuratedCompartment`` entries) claiming
    the identical ``id``.
    """


class DanglingReferenceError(NetworkAssemblyError):
    """A curated record references another curated record absent from this handoff.

    For example, a ``CuratedReactionParticipant.reaction_id`` naming a
    reaction not present in ``handoff.reactions``.
    """


class UnknownParticipantRoleError(NetworkAssemblyError):
    """A curated reaction participant's ``role`` does not match any known ``ParticipantRole``.

    ``role`` is never defaulted to ``MODIFIER`` or silently dropped --
    Agent 1's own ``ReactionParticipantRole`` vocabulary has exactly three
    values (``REACTANT``/``PRODUCT``/``MODIFIER``); anything else is a
    handoff-shape problem this increment surfaces rather than guesses at.
    """


class MissingCompartmentReferenceError(NetworkAssemblyError):
    """A curated reaction participant has no compartment reference.

    ``docs/02_agent1_handoff_contract.md`` §4 discloses that Agent 1 v1
    "allows nullable compartment references," but
    ``SpeciesSpecification.compartment_id`` (``app.agent2.types``) is a
    required, non-``None`` field -- species identity is
    compound+compartment, and there is no compartment to combine with a
    compound when none was curated. Never invented (this increment must
    never fabricate a compartment) -- raised instead. See
    ``docs/05_whole_network_assembly.md`` § "Architecture limitations" for
    the discovered gap this documents.
    """


__all__ = [
    "DanglingReferenceError",
    "DuplicateCuratedIdentifierError",
    "MissingCompartmentReferenceError",
    "NetworkAssemblyError",
    "UnknownParticipantRoleError",
]
