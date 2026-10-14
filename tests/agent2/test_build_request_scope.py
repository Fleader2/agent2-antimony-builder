"""Tests for the Scoped-Build Support increment's scoping engine:
``app.agent2.build_request.scope.apply_build_request_scope``.

Builds a small, three-reaction ``FullNetwork`` (``r1``: a->b, ``r2``: b->c, ``r3``: c->d, the
latter two sharing compartment ``cyto``, with ``r3`` alone in compartment ``vac``) via the real
``assemble_full_network``, then exercises every documented scoping behavior against it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent2.build_request import (
    AGENT2_BUILD_REQUEST_CONTRACT_VERSION,
    BuildRequestContradictionError,
    BuildRequestEmptyScopeError,
    EntityReference,
    ModelBuildRequest,
    PathwayReference,
    apply_build_request_scope,
    build_request_from_dict,
)
from app.agent2.network import assemble_full_network
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
)


def _handoff(**overrides) -> Agent1CuratedKnowledgeViewContract:
    merged = {"contract_version": "1.6"} | overrides
    return Agent1CuratedKnowledgeViewContract(**merged)


def _participant(**overrides) -> CuratedReactionParticipant:
    merged = {
        "reaction_id": "r1",
        "compound_id": "a",
        "role": "REACTANT",
        "stoichiometry": Decimal("1"),
        "compartment_id": "cyto",
    } | overrides
    return CuratedReactionParticipant(**merged)


def _three_reaction_network():
    handoff = _handoff(
        compartments=(
            CuratedCompartment(id="cyto", name="cytosol"),
            CuratedCompartment(id="vac", name="vacuole"),
        ),
        compounds=tuple(CuratedCompound(id=c, name=c.upper()) for c in "abcd"),
        reactions=(
            CuratedReaction(id="r1", name="r1"),
            CuratedReaction(id="r2", name="r2"),
            CuratedReaction(id="r3", name="r3"),
        ),
        reaction_participants=(
            _participant(reaction_id="r1", compound_id="a", role="REACTANT", compartment_id="cyto"),
            _participant(reaction_id="r1", compound_id="b", role="PRODUCT", compartment_id="cyto"),
            _participant(reaction_id="r2", compound_id="b", role="REACTANT", compartment_id="cyto"),
            _participant(reaction_id="r2", compound_id="c", role="PRODUCT", compartment_id="cyto"),
            _participant(reaction_id="r3", compound_id="c", role="REACTANT", compartment_id="vac"),
            _participant(reaction_id="r3", compound_id="d", role="PRODUCT", compartment_id="vac"),
        ),
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(reaction_id="r1", protein_id="p1"),
            CuratedReactionEnzymeAssociation(reaction_id="r2", protein_id="p2"),
            CuratedReactionEnzymeAssociation(reaction_id="r3", protein_id="p3"),
        ),
    )
    return assemble_full_network(handoff)


def _build_request(**overrides) -> ModelBuildRequest:
    merged = {
        "contract_version": AGENT2_BUILD_REQUEST_CONTRACT_VERSION,
        "model_build_request_id": "mbr-1",
    } | overrides
    return ModelBuildRequest(**merged)


# --- No build request / unscoped behavior -------------------------------------------------------


def test_no_inclusion_constraint_keeps_full_network_unscoped():
    network = _three_reaction_network()
    result = apply_build_request_scope(network, _build_request())
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r2", "r3"}
    assert result.warnings == ()


def test_repeated_scoping_is_deterministic():
    network = _three_reaction_network()
    request = _build_request(reactions=(EntityReference(role="REQUIRED", agent1_entity_id="r1"),))
    first = apply_build_request_scope(network, request)
    second = apply_build_request_scope(network, request)
    assert first.network == second.network
    assert first.warnings == second.warnings


# --- Required / excluded reactions --------------------------------------------------------------


def test_required_reaction_is_retained_and_narrows_scope():
    network = _three_reaction_network()
    request = _build_request(reactions=(EntityReference(role="REQUIRED", agent1_entity_id="r1"),))
    result = apply_build_request_scope(network, request)
    assert {r.reaction_id for r in result.network.reactions} == {"r1"}


def test_excluded_reaction_is_omitted():
    network = _three_reaction_network()
    request = _build_request(reactions=(EntityReference(role="EXCLUDED", agent1_entity_id="r2"),))
    result = apply_build_request_scope(network, request)
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r3"}


def test_contradictory_required_and_excluded_reaction_raises():
    network = _three_reaction_network()
    request = _build_request(
        reactions=(
            EntityReference(role="REQUIRED", agent1_entity_id="r1"),
            EntityReference(role="EXCLUDED", agent1_entity_id="r1"),
        )
    )
    with pytest.raises(BuildRequestContradictionError):
        apply_build_request_scope(network, request)


# --- Seed species / gene-protein scoping --------------------------------------------------------


def test_seed_species_scopes_to_touching_reactions():
    network = _three_reaction_network()
    request = _build_request(species=(EntityReference(role="SEED", agent1_entity_id="b"),))
    result = apply_build_request_scope(network, request)
    # "b" is touched by r1 (product) and r2 (reactant), never r3.
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r2"}


def test_start_and_end_boundary_species_scope_to_touching_reactions():
    """``INPUT``/``OUTPUT`` species roles (the user's declared start/end boundary of the
    build) expand scope exactly like ``SEED`` -- both are members of
    ``_SPECIES_SCOPE_EXPANDING_ROLES``."""
    network = _three_reaction_network()
    request = _build_request(
        species=(
            EntityReference(role="INPUT", agent1_entity_id="a"),
            EntityReference(role="OUTPUT", agent1_entity_id="d"),
        )
    )
    result = apply_build_request_scope(network, request)
    # "a" is touched only by r1 (reactant); "d" is touched only by r3 (product).
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r3"}


def test_important_gene_protein_scopes_to_catalyzed_reaction():
    network = _three_reaction_network()
    request = _build_request(
        gene_proteins=(EntityReference(role="IMPORTANT", agent1_entity_id="p3"),)
    )
    result = apply_build_request_scope(network, request)
    assert {r.reaction_id for r in result.network.reactions} == {"r3"}


# --- Compartment constraint ----------------------------------------------------------------------


def test_compartment_constraint_restricts_to_included_compartment():
    network = _three_reaction_network()
    request = _build_request(
        species=(EntityReference(role="SEED", agent1_entity_id="b"),),
        compartments=(EntityReference(agent1_entity_id="cyto"),),
    )
    result = apply_build_request_scope(network, request)
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r2"}
    assert {c.compartment_id for c in result.network.compartments} == {"cyto"}


def test_required_reaction_exempt_from_compartment_constraint():
    network = _three_reaction_network()
    request = _build_request(
        reactions=(EntityReference(role="REQUIRED", agent1_entity_id="r3"),),
        compartments=(EntityReference(agent1_entity_id="cyto"),),
    )
    result = apply_build_request_scope(network, request)
    # r3 lives entirely in "vac", but REQUIRED exempts it from the compartment filter.
    assert "r3" in {r.reaction_id for r in result.network.reactions}


# --- Unresolved references -----------------------------------------------------------------------


def test_unresolved_raw_identifier_is_warned_not_guessed():
    network = _three_reaction_network()
    request = _build_request(
        reactions=(EntityReference(role="SEED", raw_identifier="some unresolved reaction name"),)
    )
    result = apply_build_request_scope(network, request)
    assert any("UNRESOLVED_RAW_IDENTIFIER" in w for w in result.warnings)
    # No inclusion constraint actually resolved, so the network stays unscoped.
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r2", "r3"}


def test_unresolved_agent1_entity_id_is_warned():
    network = _three_reaction_network()
    request = _build_request(
        reactions=(EntityReference(role="REQUIRED", agent1_entity_id="does-not-exist"),)
    )
    result = apply_build_request_scope(network, request)
    assert any("UNRESOLVED_REACTION_REFERENCE" in w for w in result.warnings)


# --- Pathway scope: disclosed, not enforced -------------------------------------------------------


def test_pathway_scope_is_disclosed_as_unsupported():
    network = _three_reaction_network()
    request = _build_request(
        pathways=(PathwayReference(role="INCLUDE", external_pathway_id="path:00061"),)
    )
    result = apply_build_request_scope(network, request)
    assert any("UNSUPPORTED_PATHWAY_SCOPE" in w for w in result.warnings)
    # Not enforced: network is unaffected by the pathway constraint alone.
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r2", "r3"}


def test_localization_constraint_is_disclosed_as_unsupported():
    network = _three_reaction_network()
    request = _build_request(
        gene_proteins=(
            EntityReference(
                role="IMPORTANT", agent1_entity_id="p1", localization_entity_id="compartment-cyto"
            ),
        )
    )
    result = apply_build_request_scope(network, request)
    assert any("UNSUPPORTED_LOCALIZATION_CONSTRAINT" in w for w in result.warnings)


# --- Empty scope ---------------------------------------------------------------------------------


def test_empty_resolved_scope_is_rejected():
    network = _three_reaction_network()
    # "b" resolves and scopes to {r1, r2}, but both are then explicitly excluded.
    request = _build_request(
        species=(EntityReference(role="SEED", agent1_entity_id="b"),),
        reactions=(
            EntityReference(role="EXCLUDED", agent1_entity_id="r1"),
            EntityReference(role="EXCLUDED", agent1_entity_id="r2"),
        ),
    )
    with pytest.raises(BuildRequestEmptyScopeError):
        apply_build_request_scope(network, request)


def test_fully_unresolved_constraints_fall_back_to_unscoped_with_warnings():
    network = _three_reaction_network()
    request = _build_request(
        species=(EntityReference(role="SEED", agent1_entity_id="does-not-exist"),),
        reactions=(EntityReference(role="REQUIRED", agent1_entity_id="also-does-not-exist"),),
    )
    result = apply_build_request_scope(network, request)
    assert {r.reaction_id for r in result.network.reactions} == {"r1", "r2", "r3"}
    assert any("UNRESOLVED_REACTION_REFERENCE" in w for w in result.warnings)
    assert any("UNRESOLVED_SPECIES_REFERENCE" in w for w in result.warnings)


# --- Contract version enforcement -----------------------------------------------------------------


def test_build_request_from_dict_round_trips():
    data = {
        "contract_version": AGENT2_BUILD_REQUEST_CONTRACT_VERSION,
        "model_build_request_id": "mbr-1",
        "reactions": [{"role": "REQUIRED", "agent1_entity_id": "r1"}],
        "species": [{"role": "SEED", "raw_identifier": "glucose"}],
        "pathways": [{"role": "EXCLUDE", "name": "glycolysis"}],
        "assumptions": ["treat compartment X as well-mixed"],
    }
    parsed = build_request_from_dict(data)
    assert parsed.model_build_request_id == "mbr-1"
    assert parsed.reactions == (EntityReference(role="REQUIRED", agent1_entity_id="r1"),)
    assert parsed.species == (EntityReference(role="SEED", raw_identifier="glucose"),)
    assert parsed.pathways == (PathwayReference(role="EXCLUDE", name="glycolysis"),)
    assert parsed.assumptions == ("treat compartment X as well-mixed",)


def test_build_request_from_dict_rejects_contract_version_mismatch():
    from app.agent2.build_request import BuildRequestContractVersionError

    data = {"contract_version": "some-other-version", "model_build_request_id": "mbr-1"}
    with pytest.raises(BuildRequestContractVersionError):
        build_request_from_dict(data)
