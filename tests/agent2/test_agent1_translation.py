"""Tests for the Agent 1 -> Agent 2 Translation Layer (``app.agent2.handoff``).

Every fixture is a plain, JSON-decoded-shaped ``dict`` mirroring Agent 1's
real ``Agent1CuratedKnowledgeView`` (field names verbatim, including
Agent 1's own ``kinetic_measurement_id``/``substrate_id`` naming) --
deliberately close to the real Run 8 / Pilot 2 shape (a two-protein FAS1/
FAS2-style enzyme association, a kinetic measurement with plural
``protein_ids`` and an already-populated legacy ``protein_id``, an
unresolved ``substrate_id``) rather than an idealized shape convenient for
this translator.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agent2.handoff import MalformedHandoffPayloadError, translate_agent1_view_to_agent2
from app.agent2.network import assemble_full_network


def _view(**overrides) -> dict:
    base = {
        "contract_version": "1.3",
        "organism_id": "org-1",
        "compartments": [{"id": "cyto", "name": "cytosol"}],
        "compounds": [
            {"id": "malonyl-coa", "canonical_name": "Malonyl-CoA"},
            {"id": "acp", "canonical_name": "Acyl-carrier protein"},
            {"id": "malonyl-acp", "canonical_name": "Malonyl-[acp]"},
            {"id": "coa", "canonical_name": "CoA"},
        ],
        "reactions": [
            {"id": "r1", "name": "malonyl-CoA:[acp] transacylase", "reversible": None},
        ],
        "reaction_participants": [
            {
                "reaction_id": "r1",
                "compound_id": "malonyl-coa",
                "role": "REACTANT",
                "stoichiometry": "1",
                "compartment_id": "cyto",
            },
            {
                "reaction_id": "r1",
                "compound_id": "acp",
                "role": "REACTANT",
                "stoichiometry": "1",
                "compartment_id": "cyto",
            },
            {
                "reaction_id": "r1",
                "compound_id": "coa",
                "role": "PRODUCT",
                "stoichiometry": "1",
                "compartment_id": "cyto",
            },
            {
                "reaction_id": "r1",
                "compound_id": "malonyl-acp",
                "role": "PRODUCT",
                "stoichiometry": "1",
                "compartment_id": "cyto",
            },
        ],
        "reaction_enzyme_associations": [
            {
                "reaction_id": "r1",
                "protein_id": "fas2",
                "complex_id": None,
                "enzyme_state_id": None,
                "relationship": "CATALYZES",
            },
        ],
        "regulatory_interactions": [
            {
                "id": "reg-1",
                "regulator_type": "compound",
                "regulator_id": "malonyl-coa",
                "target_type": "reaction",
                "target_id": "r1",
                "effect": "INHIBITOR",
            },
        ],
        "kinetic_measurements": [
            {
                "kinetic_measurement_id": "km-1",
                "reaction_id": None,
                "protein_id": "fas2",
                "complex_id": None,
                "substrate_id": None,
                "organism_id": "org-1",
                "publication_id": "pmid-7044669",
                "parameter_type": "KM",
                "reported_parameter_type": "Km",
                "value": "18.0",
                "unit": "uM",
                "normalized_value": None,
                "normalized_unit": None,
                "strain": "v.R",
                "temperature_c": "25.0",
                "ph": "6.5",
                "reported_rate_law": None,
                "source": "SABIORK",
                "source_id": "18229:Km",
                "confidence_score": None,
                "confidence_class": None,
                "notes": "apparent",
                "enzyme_state_id": None,
                "protein_ids": ["fas2", "fas1"],
            },
        ],
        "enzyme_states": [
            {
                "enzyme_state_id": "es-1",
                "state_type": "BASE",
                "protein_id": "fas2",
                "complex_id": None,
                "state_label": None,
                "compartment_id": None,
                "active_state": True,
                "source": None,
                "source_id": None,
                "notes": None,
            }
        ],
        "enzyme_modifications": [
            {
                "enzyme_modification_id": "mod-1",
                "enzyme_state_id": "es-1",
                "modification_type": "PHOSPHORYLATION",
                "residue": "Ser",
                "residue_position": 15,
                "site_label": None,
                "modifying_compound_id": None,
                "stoichiometry": "1",
                "source": None,
                "source_id": None,
                "notes": None,
            }
        ],
        "allosteric_interactions": [
            {
                "allosteric_interaction_id": "ai-1",
                "enzyme_state_id": "es-1",
                "ligand_compound_id": "malonyl-coa",
                "effect": "INHIBITOR",
                "site_label": None,
                "mechanism": None,
                "source": None,
                "source_id": None,
                "notes": None,
            }
        ],
        "enzyme_state_transitions": [
            {
                "enzyme_state_transition_id": "est-1",
                "from_state_id": "es-1",
                "to_state_id": "es-1",
                "transition_type": "MODIFICATION",
                "reaction_id": None,
                "source": None,
                "source_id": None,
                "notes": None,
            }
        ],
        "claims": [
            {
                "id": "claim-1",
                "subject_type": "reaction",
                "subject_id": "r1",
                "predicate": "catalyzed_by",
                "object_type": "protein",
                "object_id": "fas2",
                "value_text": None,
                "value_numeric": None,
                "unit": None,
            }
        ],
        "evidence": [
            {
                "id": "ev-1",
                "claim_id": "claim-1",
                "publication_id": "pmid-7044669",
                "quoted_support": "FAS1/FAS2 catalyze this step.",
            }
        ],
        "confidence_summaries": [
            {
                "claim_id": "claim-1",
                "status": "HUMAN_ACCEPTED",
                "confidence_score": "90",
                "confidence_class": "HIGH",
            }
        ],
    } | overrides
    return base


# --- Complete structural translation / no entity-count loss --------------------------------------


def test_complete_structural_translation_preserves_every_entity_count():
    view = _view()
    handoff = translate_agent1_view_to_agent2(view)

    assert len(handoff.compartments) == len(view["compartments"]) == 1
    assert len(handoff.compounds) == len(view["compounds"]) == 4
    assert len(handoff.reactions) == len(view["reactions"]) == 1
    assert len(handoff.reaction_participants) == len(view["reaction_participants"]) == 4
    assert (
        len(handoff.reaction_enzyme_associations)
        == len(view["reaction_enzyme_associations"])
        == 1
    )
    assert len(handoff.regulatory_interactions) == len(view["regulatory_interactions"]) == 1
    assert len(handoff.kinetic_measurements) == len(view["kinetic_measurements"]) == 1
    assert len(handoff.enzyme_states) == len(view["enzyme_states"]) == 1
    assert len(handoff.enzyme_modifications) == len(view["enzyme_modifications"]) == 1
    assert len(handoff.allosteric_interactions) == len(view["allosteric_interactions"]) == 1
    assert len(handoff.enzyme_state_transitions) == len(view["enzyme_state_transitions"]) == 1
    assert len(handoff.claims) == len(view["claims"]) == 1
    assert len(handoff.evidence) == len(view["evidence"]) == 1
    assert len(handoff.confidence_summaries) == len(view["confidence_summaries"]) == 1


def test_contract_version_and_organism_id_preserved():
    handoff = translate_agent1_view_to_agent2(_view())
    assert handoff.contract_version == "1.3"
    assert handoff.organism_id == "org-1"


def test_structural_fields_are_faithfully_mapped():
    handoff = translate_agent1_view_to_agent2(_view())
    assert handoff.compartments[0].id == "cyto"
    assert handoff.compartments[0].name == "cytosol"
    compound_names = {c.id: c.name for c in handoff.compounds}
    assert compound_names["malonyl-coa"] == "Malonyl-CoA"
    assert handoff.reactions[0].id == "r1"
    assert handoff.reactions[0].reversible is None
    participant_roles = {(p.compound_id, p.role) for p in handoff.reaction_participants}
    assert ("malonyl-coa", "REACTANT") in participant_roles
    assert ("coa", "PRODUCT") in participant_roles
    assert handoff.reaction_participants[0].stoichiometry == Decimal("1")
    assoc = handoff.reaction_enzyme_associations[0]
    assert assoc.reaction_id == "r1"
    assert assoc.protein_id == "fas2"
    reg = handoff.regulatory_interactions[0]
    assert reg.effect == "INHIBITOR"
    assert reg.target_id == "r1"


# --- Kinetic measurement: reaction_id present / absent --------------------------------------------


def test_kinetic_measurement_without_reaction_id_stays_unresolved():
    (measurement,) = translate_agent1_view_to_agent2(_view()).kinetic_measurements
    assert measurement.reaction_id is None


def test_kinetic_measurement_with_reaction_id_is_preserved():
    view = _view()
    view["kinetic_measurements"][0]["reaction_id"] = "r1"
    (measurement,) = translate_agent1_view_to_agent2(view).kinetic_measurements
    assert measurement.reaction_id == "r1"


# --- Plural protein context -----------------------------------------------------------------------


def test_plural_protein_ids_preserved_and_protein_id_never_nulled():
    """Real defect this increment corrects: the pilot scripts nulled protein_id whenever
    protein_ids had more than one entry. Agent 1's own protein_id is never itself
    ambiguous -- it must be copied verbatim, never re-derived or discarded."""
    (measurement,) = translate_agent1_view_to_agent2(_view()).kinetic_measurements
    assert measurement.protein_id == "fas2"
    assert set(measurement.protein_ids) == {"fas1", "fas2"}


def test_single_protein_measurement_is_unaffected():
    view = _view()
    view["kinetic_measurements"][0]["protein_ids"] = ["fas2"]
    (measurement,) = translate_agent1_view_to_agent2(view).kinetic_measurements
    assert measurement.protein_id == "fas2"
    assert measurement.protein_ids == ("fas2",)


# --- compound_id (resolved / unresolved) ----------------------------------------------------------


def test_unresolved_compound_id_remains_unresolved():
    (measurement,) = translate_agent1_view_to_agent2(_view()).kinetic_measurements
    assert measurement.compound_id is None


def test_resolved_compound_id_copied_exactly():
    view = _view()
    view["kinetic_measurements"][0]["substrate_id"] = "malonyl-coa"
    (measurement,) = translate_agent1_view_to_agent2(view).kinetic_measurements
    assert measurement.compound_id == "malonyl-coa"


def test_no_species_label_to_compound_inference():
    """Even when source_id/notes contain a recognizable species name, compound_id must come
    only from substrate_id -- never inferred from any other text field."""
    view = _view()
    view["kinetic_measurements"][0]["substrate_id"] = None
    view["kinetic_measurements"][0]["notes"] = "Malonyl-CoA, apparent"
    view["kinetic_measurements"][0]["source_id"] = "18229:Km:Malonyl-CoA"
    (measurement,) = translate_agent1_view_to_agent2(view).kinetic_measurements
    assert measurement.compound_id is None


# --- Publication / provenance preservation --------------------------------------------------------


def test_kinetic_measurement_publication_id_preserved():
    (measurement,) = translate_agent1_view_to_agent2(_view()).kinetic_measurements
    assert measurement.publication_id == "pmid-7044669"


def test_evidence_and_confidence_summary_preserved():
    handoff = translate_agent1_view_to_agent2(_view())
    (evidence,) = handoff.evidence
    assert evidence.claim_id == "claim-1"
    assert evidence.publication_reference == "pmid-7044669"
    assert evidence.quoted_support == "FAS1/FAS2 catalyze this step."
    (summary,) = handoff.confidence_summaries
    assert summary.status == "HUMAN_ACCEPTED"
    assert summary.confidence_score == Decimal("90")
    assert summary.confidence_class == "HIGH"


def test_claim_fields_preserved():
    (claim,) = translate_agent1_view_to_agent2(_view()).claims
    assert claim.subject_type == "reaction"
    assert claim.subject_id == "r1"
    assert claim.predicate == "catalyzed_by"
    assert claim.object_id == "fas2"


# --- Deterministic / idempotent -------------------------------------------------------------------


def test_translation_is_deterministic():
    view = _view()
    first = translate_agent1_view_to_agent2(view)
    second = translate_agent1_view_to_agent2(view)
    assert first == second


# --- Compatibility with assemble_full_network -----------------------------------------------------


def test_translated_handoff_assembles_into_a_full_network():
    handoff = translate_agent1_view_to_agent2(_view())
    network = assemble_full_network(handoff)
    assert network.reactions
    assert network.kinetic_measurements[0].reaction_id is None
    assert set(network.kinetic_measurements[0].protein_ids) == {"fas1", "fas2"}


# --- Enzyme-state family structural fidelity ------------------------------------------------------


def test_enzyme_state_family_translated_with_correct_id_field_mapping():
    handoff = translate_agent1_view_to_agent2(_view())
    assert handoff.enzyme_states[0].id == "es-1"
    assert handoff.enzyme_modifications[0].id == "mod-1"
    assert handoff.enzyme_modifications[0].enzyme_state_id == "es-1"
    assert handoff.allosteric_interactions[0].id == "ai-1"
    assert handoff.allosteric_interactions[0].ligand_compound_id == "malonyl-coa"
    assert handoff.enzyme_state_transitions[0].id == "est-1"


# --- Malformed payload ---------------------------------------------------------------------------


def test_missing_contract_version_raises():
    view = _view()
    del view["contract_version"]
    with pytest.raises(MalformedHandoffPayloadError):
        translate_agent1_view_to_agent2(view)


def test_kinetic_measurements_not_a_list_raises():
    view = _view()
    view["kinetic_measurements"] = "not-a-list"
    with pytest.raises(MalformedHandoffPayloadError):
        translate_agent1_view_to_agent2(view)


def test_missing_required_key_in_reaction_raises():
    view = _view()
    del view["reactions"][0]["name"]
    with pytest.raises(MalformedHandoffPayloadError):
        translate_agent1_view_to_agent2(view)


def test_missing_optional_lists_default_to_empty_not_an_error():
    """Agent1CuratedKnowledgeView carries no `limitations` field; every other category
    still degrades gracefully to empty when a key is entirely absent from the payload."""
    view = _view()
    del view["claims"]
    del view["evidence"]
    del view["confidence_summaries"]
    handoff = translate_agent1_view_to_agent2(view)
    assert handoff.claims == ()
    assert handoff.evidence == ()
    assert handoff.confidence_summaries == ()
    assert handoff.limitations == ()
