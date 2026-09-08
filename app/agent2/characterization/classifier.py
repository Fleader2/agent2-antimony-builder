"""Deterministic ``ReactionClass`` classification (Increment 3).

Every rule here reads only explicit ``FullNetwork`` structure -- never a
reaction's name, an EC number string, or any other free-text signal
(Increment 3 instructions, Step 19-21). A reaction may satisfy more than
one class at once (``classify_reaction`` returns a tuple, sorted for
determinism); ``UNKNOWN`` is added only when no other class applies,
never as a member alongside a positively-identified class.

``ReactionClass.EXCHANGE``/``.SPONTANEOUS`` are never assigned by this
module: no deterministic curated signal exists in the Agent 1 handoff for
either (no "boundary reaction" or "spontaneous" flag anywhere in
``FullNetwork``). Both remain valid vocabulary members -- reserved for a
future increment if Agent 1 ever curates a signal for them -- rather than
removed, since the governing specification names them as intended
long-term vocabulary; this module simply never has grounds to use them
yet, exactly as its own "only include a value if it can be identified
deterministically" instruction requires of *assignment*, not of
*vocabulary membership*.
"""

from __future__ import annotations

from app.agent2.characterization.types import ReactionClass
from app.agent2.types import ParticipantRole, ReactionSpecification, SpeciesSpecification


def classify_reaction(
    reaction: ReactionSpecification,
    *,
    species_by_id: dict[str, SpeciesSpecification],
    is_state_transition_reaction: bool,
) -> tuple[ReactionClass, ...]:
    """Every structural ``ReactionClass`` this reaction satisfies, sorted for determinism.

    ``is_state_transition_reaction`` is precomputed by the caller (whether
    any ``EnzymeStateTransition.reaction_id`` names this reaction) rather
    than recomputed here, since the caller already has the full
    ``FullNetwork.enzyme_state_transitions`` scan available and this
    function stays a pure, network-object-free classifier.
    """
    classes: set[ReactionClass] = set()

    if reaction.enzyme_association_ids:
        classes.add(ReactionClass.ENZYMATIC)

    if is_state_transition_reaction:
        classes.add(ReactionClass.STATE_TRANSITION)

    if _is_transport(reaction, species_by_id):
        classes.add(ReactionClass.TRANSPORT)

    if not classes:
        classes.add(ReactionClass.UNKNOWN)

    return tuple(sorted(classes, key=lambda reaction_class: reaction_class.value))


def _is_transport(
    reaction: ReactionSpecification, species_by_id: dict[str, SpeciesSpecification]
) -> bool:
    """Conservative, deterministic ``TRANSPORT`` rule (Increment 3 instructions, Step 20).

    A reaction is classified ``TRANSPORT`` only when its reactant and
    product species resolve to the **identical set of underlying curated
    compounds** (``source_compound_id``) -- i.e. no chemical conversion
    occurred -- **and** at least one of those compounds actually changes
    compartment between reactant and product side. This is the narrowest
    reliable signal ``FullNetwork``'s own species/participant structure
    supports: it never looks at a reaction's name, and it never guesses
    when a participant's ``source_compound_id`` is unknown (``None``) --
    such a reaction is left unclassified for ``TRANSPORT`` (falls through
    to ``UNKNOWN`` unless another rule applies), per Step 20's explicit
    instruction to leave transport ``UNKNOWN`` rather than guess.

    A reaction with no reactant or no product participant (e.g. a
    modifier-only structural oddity) is never classified ``TRANSPORT``.
    """
    reactants = [p for p in reaction.participants if p.role is ParticipantRole.REACTANT]
    products = [p for p in reaction.participants if p.role is ParticipantRole.PRODUCT]
    if not reactants or not products:
        return False

    reactant_compounds: set[str] = set()
    reactant_compound_compartment_pairs: set[tuple[str, str]] = set()
    for participant in reactants:
        species = species_by_id[participant.species_id]
        if species.source_compound_id is None:
            return False
        reactant_compounds.add(species.source_compound_id)
        reactant_compound_compartment_pairs.add(
            (species.source_compound_id, species.compartment_id)
        )

    product_compounds: set[str] = set()
    product_compound_compartment_pairs: set[tuple[str, str]] = set()
    for participant in products:
        species = species_by_id[participant.species_id]
        if species.source_compound_id is None:
            return False
        product_compounds.add(species.source_compound_id)
        product_compound_compartment_pairs.add(
            (species.source_compound_id, species.compartment_id)
        )

    if reactant_compounds != product_compounds:
        return False  # a chemical conversion occurred -- not pure movement
    # identical compartments too would mean no movement occurred at all
    return reactant_compound_compartment_pairs != product_compound_compartment_pairs


__all__ = ["classify_reaction"]
