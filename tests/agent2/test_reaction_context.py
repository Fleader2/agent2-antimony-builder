"""Tests for Kinetic-Measurement Reaction-Context Resolution.

Every fixture is deliberately shaped after the real yeast fatty-acid
synthase (FAS1/FAS2, EC 2.3.1.86) SABIO-RK records this increment
inspected live (Real Integration Pilot 1 Run 8 / Pilot 2 Run 2, and this
increment's own read-only re-query): a malonyl-CoA:[acp] transacylase
step and an acetyl-CoA:[acp] transacylase step both exist as separate
curated reactions and both name a free-CoA primer compound as a
``REACTANT`` -- exactly the real ambiguity/uniqueness split this module
must reproduce deterministically. No fixture invents biology beyond what
the real data already showed: Malonyl-CoA is a REACTANT of exactly one
curated reaction; Acetyl-CoA is a REACTANT of more than one.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.kinetics.reaction_context import (
    ReactionContextMatchResult,
    ReactionContextResolution,
    apply_resolved_reaction_context,
    resolve_kinetic_measurement_reaction_context,
)
from app.agent2.model_specification import assemble_model_specification
from app.agent2.modules import decompose_network
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    FullNetwork,
    ParameterSource,
)

# --- Fixtures ----------------------------------------------------------------------------------


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.3"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _compartment(**overrides) -> CuratedCompartment:
    merged = {"id": "cyto", "name": "cytosol"} | overrides
    return CuratedCompartment(**merged)


def _compound(**overrides) -> CuratedCompound:
    merged = {"id": "acetyl-coa", "name": "Acetyl-CoA"} | overrides
    return CuratedCompound(**merged)


def _reaction(**overrides) -> CuratedReaction:
    merged = {"id": "r-malonyl-transfer", "name": "malonyl-CoA:[acp] transacylase"} | overrides
    return CuratedReaction(**merged)


def _participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r-malonyl-transfer",
        "compound_id": "malonyl-coa",
        "role": "REACTANT",
        "stoichiometry": Decimal("1"),
        "compartment_id": "cyto",
    } | overrides
    return CuratedReactionParticipant(**merged)


def _measurement(**overrides) -> CuratedKineticMeasurement:
    merged = {
        "id": "km-1",
        "parameter_type": "KM",
        "value": Decimal("18.0"),
        "unit": "uM",
        "reaction_id": None,
        "source": "SABIORK",
        "source_id": "18229:Km",
    } | overrides
    return CuratedKineticMeasurement(**merged)


#: Two FAS-like reactions: one where the primer compound (Malonyl-CoA) is a
#: REACTANT of exactly one reaction, one where a different primer compound
#: (Acetyl-CoA) is a REACTANT of two reactions -- mirrors the real,
#: live-confirmed shape exactly (see module docstring).
_FAS_LIKE_HANDOFF = _handoff(
    compartments=(_compartment(),),
    compounds=(
        _compound(id="acetyl-coa", name="Acetyl-CoA"),
        _compound(id="malonyl-coa", name="Malonyl-CoA"),
        _compound(id="acp", name="Acyl-carrier protein"),
        _compound(id="acetyl-acp", name="Acetyl-[acp]"),
        _compound(id="malonyl-acp", name="Malonyl-[acp]"),
        _compound(id="coa", name="CoA"),
        _compound(id="long-chain-acyl-coa", name="Long-chain acyl-CoA"),
    ),
    reactions=(
        _reaction(id="r-malonyl-transfer", name="malonyl-CoA:[acp] transacylase"),
        _reaction(id="r-acetyl-transfer", name="acetyl-CoA:[acp] transacylase"),
        _reaction(id="r-acetyl-condense", name="acyl-CoA:malonyl-CoA C-acyltransferase"),
    ),
    reaction_participants=(
        _participant(
            reaction_id="r-malonyl-transfer", compound_id="malonyl-coa", role="REACTANT"
        ),
        _participant(reaction_id="r-malonyl-transfer", compound_id="acp", role="REACTANT"),
        _participant(reaction_id="r-malonyl-transfer", compound_id="coa", role="PRODUCT"),
        _participant(
            reaction_id="r-malonyl-transfer", compound_id="malonyl-acp", role="PRODUCT"
        ),
        _participant(reaction_id="r-acetyl-transfer", compound_id="acetyl-coa", role="REACTANT"),
        _participant(reaction_id="r-acetyl-transfer", compound_id="acp", role="REACTANT"),
        _participant(reaction_id="r-acetyl-transfer", compound_id="coa", role="PRODUCT"),
        _participant(
            reaction_id="r-acetyl-transfer", compound_id="acetyl-acp", role="PRODUCT"
        ),
        _participant(
            reaction_id="r-acetyl-condense", compound_id="acetyl-coa", role="REACTANT"
        ),
        _participant(
            reaction_id="r-acetyl-condense",
            compound_id="long-chain-acyl-coa",
            role="PRODUCT",
        ),
    ),
    reaction_enzyme_associations=(
        CuratedReactionEnzymeAssociation(
            reaction_id="r-malonyl-transfer", protein_id="fas2", relationship="CATALYZES"
        ),
        CuratedReactionEnzymeAssociation(
            reaction_id="r-acetyl-transfer", protein_id="fas2", relationship="CATALYZES"
        ),
        CuratedReactionEnzymeAssociation(
            reaction_id="r-acetyl-condense", protein_id="fas2", relationship="CATALYZES"
        ),
    ),
)


def _network_with(measurements: tuple[CuratedKineticMeasurement, ...]) -> FullNetwork:
    return assemble_full_network(
        dataclasses.replace(_FAS_LIKE_HANDOFF, kinetic_measurements=measurements)
    )


# --- 1. UNIQUE_MATCH -----------------------------------------------------------------------------


def test_unique_match_resolves_reaction_id():
    """Malonyl-CoA is a REACTANT of exactly one curated reaction -- UNIQUE_MATCH."""
    measurement = _measurement(id="km-malonyl", compound_id="malonyl-coa", reaction_id=None)
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.measurement_id == "km-malonyl"
    assert resolution.result is ReactionContextMatchResult.UNIQUE_MATCH
    assert resolution.matched_reaction_id == "r-malonyl-transfer"
    assert resolution.candidate_reaction_ids == ("r-malonyl-transfer",)


# --- 2. MULTIPLE_COMPATIBLE ----------------------------------------------------------------------


def test_multiple_compatible_when_two_reactions_share_the_reactant():
    """Acetyl-CoA is a REACTANT of two curated reactions -- MULTIPLE_COMPATIBLE, no assignment."""
    measurement = _measurement(id="km-acetyl", compound_id="acetyl-coa", reaction_id=None)
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.result is ReactionContextMatchResult.MULTIPLE_COMPATIBLE
    assert resolution.matched_reaction_id is None
    assert set(resolution.candidate_reaction_ids) == {"r-acetyl-transfer", "r-acetyl-condense"}


# --- 3. NO_MATCH -----------------------------------------------------------------------------


def test_no_match_when_compound_is_not_curated_as_a_reactant_anywhere():
    """A compound with no curated reaction at all (real analogue: Propionyl-CoA, confirmed
    absent from the real curated FAS compound set) -- NO_MATCH."""
    measurement = _measurement(
        id="km-propionyl", compound_id="propionyl-coa", reaction_id=None
    )
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.result is ReactionContextMatchResult.NO_MATCH
    assert resolution.matched_reaction_id is None
    assert resolution.candidate_reaction_ids == ()


def test_no_match_when_compound_exists_only_as_a_product():
    """A compound that is curated, but only ever appears as a PRODUCT -- never a REACTANT --
    is still NO_MATCH (role compatibility, not mere compound presence, is required)."""
    measurement = _measurement(
        id="km-longchain", compound_id="long-chain-acyl-coa", reaction_id=None
    )
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.result is ReactionContextMatchResult.NO_MATCH


# --- 4. INSUFFICIENT_SOURCE_EVIDENCE (missing compound_id) ---------------------------------------


def test_insufficient_evidence_when_compound_id_is_none():
    measurement = _measurement(id="km-no-compound", compound_id=None, reaction_id=None)
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.result is ReactionContextMatchResult.INSUFFICIENT_SOURCE_EVIDENCE
    assert resolution.matched_reaction_id is None


# --- 5. Protein/EC context alone never substitutes for compound evidence ------------------------


def test_protein_context_alone_never_resolves_a_reaction():
    """A measurement naming the catalyzing protein (which catalyzes three reactions) but no
    compound_id must not be resolved via that protein/EC context -- still insufficient."""
    measurement = _measurement(
        id="km-protein-only", compound_id=None, protein_id="fas2", reaction_id=None
    )
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.result is ReactionContextMatchResult.INSUFFICIENT_SOURCE_EVIDENCE


# --- 6. Substrate-specific Km resolves ------------------------------------------------------------


def test_substrate_specific_km_resolves_while_preserving_other_fields():
    measurement = _measurement(
        id="km-malonyl-2",
        compound_id="malonyl-coa",
        value=Decimal("18.0"),
        unit="uM",
        reaction_id=None,
    )
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)
    resolved_network = apply_resolved_reaction_context(network, (resolution,))

    (resolved_measurement,) = resolved_network.kinetic_measurements
    assert resolved_measurement.reaction_id == "r-malonyl-transfer"
    assert resolved_measurement.value == Decimal("18.0")
    assert resolved_measurement.unit == "uM"
    assert resolved_measurement.compound_id == "malonyl-coa"


# --- 7. Vmax never resolved, even if it happened to carry a compound_id -------------------------


def test_vmax_never_resolved_even_with_a_uniquely_matching_compound_id():
    measurement = _measurement(
        id="vmax-1",
        parameter_type="VMAX",
        compound_id="malonyl-coa",
        value=Decimal("3340.0"),
        unit="nmol/(min*mg)",
        reaction_id=None,
    )
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)

    assert resolution.result is ReactionContextMatchResult.INSUFFICIENT_SOURCE_EVIDENCE
    assert resolution.matched_reaction_id is None


# --- 8. No arbitrary selection among multiple compatible reactions -------------------------------


def test_no_arbitrary_reaction_is_ever_chosen_from_multiple_compatible():
    measurement = _measurement(id="km-acetyl-2", compound_id="acetyl-coa", reaction_id=None)
    network = _network_with((measurement,))

    (resolution,) = resolve_kinetic_measurement_reaction_context(network)
    resolved_network = apply_resolved_reaction_context(network, (resolution,))

    (resolved_measurement,) = resolved_network.kinetic_measurements
    assert resolved_measurement.reaction_id is None


# --- 9. Order-independence ------------------------------------------------------------------------


def test_resolution_is_order_independent():
    measurements_forward = (
        _measurement(id="km-malonyl-a", compound_id="malonyl-coa", reaction_id=None),
        _measurement(id="km-acetyl-a", compound_id="acetyl-coa", reaction_id=None),
        _measurement(id="km-propionyl-a", compound_id="propionyl-coa", reaction_id=None),
    )
    measurements_reversed = tuple(reversed(measurements_forward))

    network_forward = _network_with(measurements_forward)
    network_reversed = _network_with(measurements_reversed)

    by_id_forward = {
        r.measurement_id: r.result
        for r in resolve_kinetic_measurement_reaction_context(network_forward)
    }
    by_id_reversed = {
        r.measurement_id: r.result
        for r in resolve_kinetic_measurement_reaction_context(network_reversed)
    }
    assert by_id_forward == by_id_reversed


# --- 10. Matched measurements enter parameter declaration normally -------------------------------


def test_unique_match_measurement_is_consumed_by_parameter_declaration():
    """A single-reactant/single-product reaction (Michaelis-Menten-eligible) with one
    catalyst and no reported law -- the resolved Km measurement must reach real parameter
    declaration exactly as a natively-attributed one would."""
    mm_handoff = _handoff(
        compartments=(_compartment(),),
        compounds=(
            _compound(id="malonyl-coa", name="Malonyl-CoA"),
            _compound(id="malonyl-acp", name="Malonyl-[acp]"),
        ),
        reactions=(_reaction(id="r-mm", name="malonyl-CoA:[acp] transacylase (MM-shaped)"),),
        reaction_participants=(
            _participant(reaction_id="r-mm", compound_id="malonyl-coa", role="REACTANT"),
            _participant(reaction_id="r-mm", compound_id="malonyl-acp", role="PRODUCT"),
        ),
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(
                reaction_id="r-mm", protein_id="fas2", relationship="CATALYZES"
            ),
        ),
        kinetic_measurements=(
            _measurement(
                id="km-malonyl-3",
                compound_id="malonyl-coa",
                value=Decimal("18.0"),
                unit="uM",
                reaction_id=None,
            ),
        ),
    )
    network = assemble_full_network(mm_handoff)
    resolutions = resolve_kinetic_measurement_reaction_context(network)
    resolved_network = apply_resolved_reaction_context(network, resolutions)

    characterization = characterize_full_network(resolved_network)
    assignments = assign_kinetic_laws(characterization, resolved_network)
    parameters = declare_parameters(assignments, resolved_network)

    km_params = [
        p
        for p in parameters.parameter_specifications
        if p.reaction_id == "r-mm" and "km-malonyl-3" in p.provenance_refs
    ]
    assert km_params, "resolved measurement never reached parameter declaration"
    assert km_params[0].source in (ParameterSource.CURATED, ParameterSource.LITERATURE_DERIVED)
    assert km_params[0].value == Decimal("18.0")


# --- 11. Unresolved measurements remain disclosed exactly as before ------------------------------


def test_unresolved_measurement_still_produces_the_disclosure_assumption():
    measurement = _measurement(
        id="km-propionyl-2", compound_id="propionyl-coa", reaction_id=None
    )
    network = _network_with((measurement,))
    resolutions = resolve_kinetic_measurement_reaction_context(network)
    resolved_network = apply_resolved_reaction_context(network, resolutions)

    characterization = characterize_full_network(resolved_network)
    assignments = assign_kinetic_laws(characterization, resolved_network)
    parameters = declare_parameters(assignments, resolved_network)
    boundaries = assess_boundaries(resolved_network, characterization, assignments, parameters)
    modules = decompose_network(resolved_network, assignments, parameters, boundaries)
    model = assemble_model_specification(
        resolved_network, assignments, parameters, boundaries, modules
    )

    matching = [
        a
        for a in model.model_assumptions
        if a.reason_code == "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"
        and "km-propionyl-2" in a.related_entity_ids
    ]
    assert matching, "unresolved measurement lost its disclosure after a resolution pass"


# --- 12. apply_resolved_reaction_context never fabricates or alters value/unit -------------------


def test_apply_never_changes_anything_but_reaction_id():
    measurement = _measurement(
        id="km-malonyl-4",
        compound_id="malonyl-coa",
        value=Decimal("18.0"),
        unit="uM",
        reaction_id=None,
        notes="apparent",
    )
    network = _network_with((measurement,))
    resolutions = resolve_kinetic_measurement_reaction_context(network)
    resolved_network = apply_resolved_reaction_context(network, resolutions)

    (before,) = network.kinetic_measurements
    (after,) = resolved_network.kinetic_measurements
    assert dataclasses.replace(after, reaction_id=before.reaction_id) == before
    assert after.reaction_id == "r-malonyl-transfer"


# --- Vocabulary / type tests -----------------------------------------------------------------


def test_apply_with_no_unique_matches_returns_the_same_network_object():
    measurement = _measurement(id="km-propionyl-3", compound_id="propionyl-coa", reaction_id=None)
    network = _network_with((measurement,))
    resolutions = resolve_kinetic_measurement_reaction_context(network)

    assert apply_resolved_reaction_context(network, resolutions) is network


def test_already_attributed_measurements_produce_no_resolution():
    measurement = _measurement(
        id="km-already", compound_id="malonyl-coa", reaction_id="r-malonyl-transfer"
    )
    network = _network_with((measurement,))

    resolutions = resolve_kinetic_measurement_reaction_context(network)

    assert resolutions == ()


def test_unique_match_requires_matched_reaction_id():
    with pytest.raises(ValueError):
        ReactionContextResolution(
            measurement_id="km-x",
            result=ReactionContextMatchResult.UNIQUE_MATCH,
            matched_reaction_id=None,
        )


def test_non_unique_match_rejects_a_matched_reaction_id():
    with pytest.raises(ValueError):
        ReactionContextResolution(
            measurement_id="km-x",
            result=ReactionContextMatchResult.NO_MATCH,
            matched_reaction_id="r1",
        )
