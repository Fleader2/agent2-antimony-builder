"""Tests for the Canonical Submodel Materialization for Recursive Modularization increment:
``app.agent2.submodel_materialization``.

Fixture style mirrors ``tests/agent2/test_candidate_orchestration.py``'s own chain network
(A -> B -> C -> D -> E, seed modA={r1,r2}/modB={r3,r4}) exactly, so results can be hand-verified
and the two test files stay easy to cross-reference.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.agent2.antimony.generator import generate_antimony, generate_module_artifacts
from app.agent2.antimony_import import import_antimony
from app.agent2.candidate_orchestration import (
    CalibrationSelectionPolicy,
    build_submodel,
    run_candidate_search_round,
)
from app.agent2.modularization_search import ProposalOperation, SearchPolicy
from app.agent2.module_calibration.request_builder import build_module_calibration_request
from app.agent2.module_evaluation import CriteriaWeights, CriterionWeight, ModularizationCriterion
from app.agent2.submodel_materialization import (
    SubmodelMaterializationReferenceError,
    materialize_submodel,
)
from app.agent2.types import (
    AntimonyArtifactReadiness,
    CompartmentSourceScope,
    CompartmentSpecification,
    CuratedEnzymeState,
    EventAssignmentSpecification,
    EventSpecification,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ModelModularization,
    ModelModule,
    ModelSpecification,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
    ModulePort,
    ModulePortDirection,
    ObservableSpecification,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    RuleSpecification,
    RuleType,
    SpeciesSpecification,
)

# --- Fixtures (mirrors tests/agent2/test_candidate_orchestration.py) ---------------------------


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "c1",
        "name": "c1",
        "source_scope": CompartmentSourceScope.MODELING_CONSTRUCT,
        "assumptions": ("test fixture",),
    } | overrides
    return CompartmentSpecification(**merged)


def _species(**overrides) -> SpeciesSpecification:
    merged = {"species_id": "A", "name": "A", "compartment_id": "c1"} | overrides
    return SpeciesSpecification(**merged)


def _participant(**overrides) -> ReactionParticipantSpecification:
    merged = {
        "species_id": "A",
        "role": ParticipantRole.REACTANT,
        "stoichiometry": Decimal("1"),
    } | overrides
    return ReactionParticipantSpecification(**merged)


def _reaction(**overrides) -> ReactionSpecification:
    merged = {
        "reaction_id": "r1",
        "name": "r1",
        "participants": (
            _participant(species_id="A", role=ParticipantRole.REACTANT),
            _participant(species_id="B", role=ParticipantRole.PRODUCT),
        ),
    } | overrides
    return ReactionSpecification(**merged)


_SUBSTRATE_BY_REACTION = {"r1": "A", "r2": "B", "r3": "C", "r4": "D"}
_PRODUCT_BY_REACTION = {"r1": "B", "r2": "C", "r3": "D", "r4": "E"}


def _chain_network(**overrides) -> FullNetwork:
    merged = {
        "network_id": "n1",
        "name": "n1",
        "compartments": (_compartment(),),
        "species": tuple(_species(species_id=sid) for sid in ("A", "B", "C", "D", "E")),
        "reactions": tuple(
            _reaction(
                reaction_id=rid,
                participants=(
                    _participant(
                        species_id=_SUBSTRATE_BY_REACTION[rid], role=ParticipantRole.REACTANT
                    ),
                    _participant(
                        species_id=_PRODUCT_BY_REACTION[rid], role=ParticipantRole.PRODUCT
                    ),
                ),
            )
            for rid in ("r1", "r2", "r3", "r4")
        ),
    } | overrides
    return FullNetwork(**merged)


def _kinetic_law(reaction_id: str, **overrides) -> KineticLawSpecification:
    substrate = _SUBSTRATE_BY_REACTION[reaction_id]
    merged = {
        "kinetic_law_id": f"kl-{reaction_id}",
        "reaction_id": reaction_id,
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        "expression": f"k_{reaction_id} * {substrate}",
        "parameter_ids": (f"k_{reaction_id}",),
        "species_ids": (substrate,),
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(reaction_id: str) -> ParameterSpecification:
    return ParameterSpecification(
        parameter_id=f"k_{reaction_id}",
        name=f"k_{reaction_id}",
        source=ParameterSource.CURATED,
        value=Decimal("0.5"),
        reaction_id=reaction_id,
    )


def _membership(
    module_id: str, reaction_id: str, *, modularization_id: str = "seed"
) -> ModuleMembership:
    return ModuleMembership(
        membership_id=f"mem_{modularization_id}_{module_id}_{reaction_id}",
        modularization_id=modularization_id,
        module_id=module_id,
        component_type=ModuleComponentType.REACTION,
        component_id=reaction_id,
    )


def _seed_model(**overrides) -> ModelSpecification:
    """modA={r1,r2}, modB={r3,r4} -- the chain's own natural, contiguous split. Real mass-
    action kinetics/parameters for every reaction, plus one real ``externally_controlled``
    boundary port on the shared species "C" -- so ``modA`` is genuinely ``EXECUTABLE``."""
    modularization = ModelModularization(
        modularization_id="seed",
        name="seed",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("modA", "modB"),
    )
    merged = {
        "model_id": "m1",
        "name": "m1",
        "full_network": _chain_network(),
        "kinetic_laws": tuple(_kinetic_law(r) for r in ("r1", "r2", "r3", "r4")),
        "parameters": tuple(_parameter(r) for r in ("r1", "r2", "r3", "r4")),
        "modularizations": (modularization,),
        "model_modules": (
            ModelModule(module_id="modA", name="A"),
            ModelModule(module_id="modB", name="B"),
        ),
        "module_memberships": (
            _membership("modA", "r1"),
            _membership("modA", "r2"),
            _membership("modB", "r3"),
            _membership("modB", "r4"),
        ),
        "module_ports": (
            ModulePort(
                port_id="port-C-modA",
                modularization_id="seed",
                module_id="modA",
                species_id="C",
                direction=ModulePortDirection.OUTPUT,
                externally_controlled=True,
                initial_value=Decimal("1"),
            ),
            ModulePort(
                port_id="port-C-modB",
                modularization_id="seed",
                module_id="modB",
                species_id="C",
                direction=ModulePortDirection.INPUT,
                externally_controlled=True,
                initial_value=Decimal("1"),
            ),
        ),
    } | overrides
    return ModelSpecification(**merged)


def _imported_chain_model() -> ModelSpecification:
    text = """
    model m
      compartment c1 = 1.0;
      species A in c1 = 1.0;
      species B in c1 = 0.0;
      species C in c1 = 0.0;
      species D in c1 = 0.0;
      species E in c1 = 0.0;
      r1: A => B; k1 * A;
      r2: B => C; k2 * B;
      r3: C => D; k3 * C;
      r4: D => E; k4 * D;
      k1 = 0.5;
      k2 = 0.5;
      k3 = 0.5;
      k4 = 0.5;
    end
    """
    return import_antimony(text)


def _topology_weights() -> CriteriaWeights:
    return CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),),
        policy_version="test-v1",
    )


def _search_policy(**overrides) -> SearchPolicy:
    merged = {
        "max_iterations": 2,
        "max_candidates_per_iteration": 10,
        "beam_width": 5,
        "allowed_operations": (ProposalOperation.MOVE_REACTION,),
        "policy_version": "test-v1",
    } | overrides
    return SearchPolicy(**merged)


def _calibration_selection_policy(**overrides) -> CalibrationSelectionPolicy:
    merged = {
        "max_candidates_per_generation": 5,
        "max_modules_per_candidate": 5,
        "score_threshold": Decimal("0"),
        "rank_threshold": 5,
        "only_if_could_change_ordering": False,
        "total_calibration_run_budget": 10,
        "policy_version": "test-v1",
    } | overrides
    return CalibrationSelectionPolicy(**merged)


# --- §7: exact reaction scoping / species-parameter closure / unrelated components excluded -----


def test_materialize_submodel_scopes_to_exactly_the_modules_own_reactions():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    assert {r.reaction_id for r in result.submodel.full_network.reactions} == {"r1", "r2"}
    assert {r.reaction_id for r in result.submodel.full_network.reactions}.isdisjoint({"r3", "r4"})


def test_materialize_submodel_computes_correct_species_and_parameter_closure():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    assert {s.species_id for s in result.submodel.full_network.species} == {"A", "B", "C"}
    assert {p.parameter_id for p in result.submodel.parameters} == {"k_r1", "k_r2"}
    assert {kl.kinetic_law_id for kl in result.submodel.kinetic_laws} == {"kl-r1", "kl-r2"}


def test_materialize_submodel_excludes_unrelated_parent_components():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    species_ids = {s.species_id for s in result.submodel.full_network.species}
    parameter_ids = {p.parameter_id for p in result.submodel.parameters}
    assert "D" not in species_ids
    assert "E" not in species_ids
    assert "k_r3" not in parameter_ids
    assert "k_r4" not in parameter_ids
    # modB itself is not carried forward at all.
    assert result.submodel.model_modules == (ModelModule(module_id="modA", name="A"),)
    assert result.submodel.modularizations[0].module_ids == ("modA",)


def test_materialize_submodel_drops_full_network_supporting_data():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    net = result.submodel.full_network
    assert net.enzyme_associations == ()
    assert net.genes == ()
    assert net.proteins == ()
    assert net.regulatory_interactions == ()
    assert net.kinetic_measurements == ()
    assert net.enzyme_modifications == ()
    assert net.allosteric_interactions == ()
    assert net.enzyme_state_transitions == ()
    assert net.experimental_contexts == ()
    assert net.quantitative_observations == ()
    assert net.publications == ()
    assert result.submodel.enzyme_concentrations == ()
    assert result.submodel.enzyme_state_pools == ()
    assert result.submodel.enzyme_state_concentrations == ()


def test_materialize_submodel_rejects_a_module_with_zero_reactions():
    model = _seed_model(
        model_modules=(
            ModelModule(module_id="modA", name="A"),
            ModelModule(module_id="modB", name="B"),
            ModelModule(module_id="modEmpty", name="empty"),
        ),
        modularizations=(
            ModelModularization(
                modularization_id="seed",
                name="seed",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA", "modB", "modEmpty"),
            ),
        ),
    )
    with pytest.raises(SubmodelMaterializationReferenceError):
        materialize_submodel(model, "seed", "modEmpty")


def test_materialize_submodel_rejects_unknown_modularization_or_module_id():
    model = _seed_model()
    with pytest.raises(SubmodelMaterializationReferenceError):
        materialize_submodel(model, "does-not-exist", "modA")
    with pytest.raises(SubmodelMaterializationReferenceError):
        materialize_submodel(model, "seed", "does-not-exist")


# --- §7: enzyme-species retention -----------------------------------------------------------------


def _enzyme_species_model() -> ModelSpecification:
    """r1 (A -> B) is catalyzed by an explicit enzyme species "E1" that is *not* a reaction
    participant -- linked only via the kinetic law's own ``protein_id``/``enzyme_state_id``."""
    network = _chain_network(
        species=(
            *(_species(species_id=sid) for sid in ("A", "B", "C", "D", "E")),
            _species(
                species_id="E1",
                name="E1",
                source_enzyme_state_id="es1",
            ),
        ),
        enzyme_states=(CuratedEnzymeState(id="es1", state_type="ACTIVE", protein_id="p1"),),
    )
    law_r1 = _kinetic_law("r1", enzyme_state_id="es1")
    model = _seed_model(full_network=network)
    return replace(
        model,
        kinetic_laws=(law_r1, *(kl for kl in model.kinetic_laws if kl.reaction_id != "r1")),
    )


def test_materialize_submodel_retains_explicit_enzyme_species_linked_via_kinetic_law():
    model = _enzyme_species_model()
    result = materialize_submodel(model, "seed", "modA")
    species_ids = {s.species_id for s in result.submodel.full_network.species}
    assert "E1" in species_ids
    assert result.lineage.explicit_enzyme_species_ids == ("E1",)
    # the retained enzyme_states registry is filtered to just the one state that makes "E1"
    # identifiable as an explicit enzyme species.
    assert {s.id for s in result.submodel.full_network.enzyme_states} == {"es1"}


def test_materialize_submodel_does_not_retain_enzyme_species_for_an_unrelated_module():
    model = _enzyme_species_model()
    result = materialize_submodel(model, "seed", "modB")
    species_ids = {s.species_id for s in result.submodel.full_network.species}
    assert "E1" not in species_ids
    assert result.submodel.full_network.enzyme_states == ()


# --- §7: boundary ports preserved ----------------------------------------------------------------


def test_materialize_submodel_preserves_boundary_port_treatment():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    (port,) = result.submodel.module_ports
    assert port.species_id == "C"
    assert port.direction is ModulePortDirection.OUTPUT
    assert port.externally_controlled is True
    assert port.initial_value == Decimal("1")
    assert port.modularization_id == result.submodel_modularization_id
    assert port.module_id == result.submodel_module_id
    (treatment,) = result.lineage.boundary_treatments
    assert treatment.species_id == "C"
    assert treatment.direction is ModulePortDirection.OUTPUT
    assert treatment.externally_controlled is True


def test_materialize_submodel_with_no_ports_produces_no_boundary_treatments():
    model = _seed_model(module_ports=())
    result = materialize_submodel(model, "seed", "modA")
    assert result.submodel.module_ports == ()
    assert result.lineage.boundary_treatments == ()


# --- §7: rules/events/observables retained only when valid --------------------------------------


def test_materialize_submodel_retains_a_rule_entirely_within_closure():
    model = _seed_model(
        rules=(
            RuleSpecification(
                rule_id="rule-1", rule_type=RuleType.ASSIGNMENT, formula="A + B", variable="k_r1"
            ),
        )
    )
    result = materialize_submodel(model, "seed", "modA")
    assert {r.rule_id for r in result.submodel.rules} == {"rule-1"}
    assert result.unresolved_dependencies == ()


def test_materialize_submodel_discloses_a_rule_referencing_an_out_of_scope_id():
    model = _seed_model(
        rules=(
            RuleSpecification(
                rule_id="rule-1", rule_type=RuleType.ASSIGNMENT, formula="D + k_r3", variable="k_r1"
            ),
        )
    )
    result = materialize_submodel(model, "seed", "modA")
    assert result.submodel.rules == ()
    (disclosure,) = result.unresolved_dependencies
    assert disclosure.component_type == "RULE"
    assert disclosure.component_id == "rule-1"
    assert set(disclosure.referenced_ids) == {"D", "k_r3"}


def test_materialize_submodel_retains_an_event_entirely_within_closure():
    model = _seed_model(
        events=(
            EventSpecification(
                event_id="event-1",
                trigger_formula="A > 1",
                assignments=(EventAssignmentSpecification(variable="k_r1", formula="k_r2"),),
            ),
        )
    )
    result = materialize_submodel(model, "seed", "modA")
    assert {e.event_id for e in result.submodel.events} == {"event-1"}


def test_materialize_submodel_discloses_an_event_referencing_an_out_of_scope_id():
    model = _seed_model(
        events=(
            EventSpecification(
                event_id="event-1",
                trigger_formula="D > 1",
                assignments=(EventAssignmentSpecification(variable="k_r1", formula="k_r2"),),
            ),
        )
    )
    result = materialize_submodel(model, "seed", "modA")
    assert result.submodel.events == ()
    (disclosure,) = result.unresolved_dependencies
    assert disclosure.component_type == "EVENT"
    assert disclosure.component_id == "event-1"
    assert "D" in disclosure.referenced_ids


def test_materialize_submodel_retains_an_observable_entirely_within_closure():
    model = _seed_model(
        observables=(ObservableSpecification(observable_id="obs-1", name="A+B", formula="A + B"),)
    )
    result = materialize_submodel(model, "seed", "modA")
    assert {o.observable_id for o in result.submodel.observables} == {"obs-1"}


def test_materialize_submodel_discloses_an_observable_referencing_an_out_of_scope_id():
    model = _seed_model(
        observables=(ObservableSpecification(observable_id="obs-1", name="A+D", formula="A + D"),)
    )
    result = materialize_submodel(model, "seed", "modA")
    assert result.submodel.observables == ()
    (disclosure,) = result.unresolved_dependencies
    assert disclosure.component_type == "OBSERVABLE"
    assert disclosure.component_id == "obs-1"
    assert "D" in disclosure.referenced_ids


def test_materialize_submodel_never_rejects_a_rule_referencing_only_unknown_tokens():
    """A rule formula mentioning something that is not any known parent-model id at all (a
    bare literal/unit symbol) is retained -- vacuously within scope, never rejected merely
    because it references nothing resolvable (task instructions §3's own "never invent a
    cross-reference requirement" spirit, mirrored from ``RuleSpecification.variable``'s own
    established convention)."""
    model = _seed_model(
        rules=(
            RuleSpecification(
                rule_id="rule-1", rule_type=RuleType.ASSIGNMENT, formula="2 * pi", variable="k_r1"
            ),
        )
    )
    result = materialize_submodel(model, "seed", "modA")
    assert {r.rule_id for r in result.submodel.rules} == {"rule-1"}
    assert result.unresolved_dependencies == ()


# --- §7: parent-child lineage --------------------------------------------------------------------


def test_materialize_submodel_lineage_records_exact_traceability():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    lineage = result.lineage
    assert lineage.parent_model_id == "m1"
    assert lineage.parent_modularization_id == "seed"
    assert lineage.parent_module_id == "modA"
    assert lineage.submodel_modularization_id == result.submodel_modularization_id
    assert lineage.submodel_module_id == result.submodel_module_id
    assert lineage.retained_reaction_ids == ("r1", "r2")
    assert lineage.retained_species_ids == ("A", "B", "C")
    assert lineage.retained_parameter_ids == ("k_r1", "k_r2")
    assert lineage.materialization_policy_version
    assert any("submodel-materialization" in ref for ref in result.submodel.provenance_refs)


# --- §7: GENERATED/IMPORTED parent symmetry -------------------------------------------------


def test_materialize_submodel_produces_symmetric_results_for_generated_and_imported_parents():
    generated = _seed_model()
    imported = _imported_chain_model()
    imported_with_modularization = replace(
        imported,
        modularizations=(
            ModelModularization(
                modularization_id="seed",
                name="seed",
                method=ModularizationMethod.USER_DEFINED,
                module_ids=("modA", "modB"),
            ),
        ),
        model_modules=(
            ModelModule(module_id="modA", name="A"),
            ModelModule(module_id="modB", name="B"),
        ),
        module_memberships=(
            _membership("modA", "r1"),
            _membership("modA", "r2"),
            _membership("modB", "r3"),
            _membership("modB", "r4"),
        ),
    )
    result_generated = materialize_submodel(generated, "seed", "modA")
    result_imported = materialize_submodel(imported_with_modularization, "seed", "modA")
    assert {r.reaction_id for r in result_generated.submodel.full_network.reactions} == {
        r.reaction_id for r in result_imported.submodel.full_network.reactions
    }
    assert {s.species_id for s in result_generated.submodel.full_network.species} == {
        s.species_id for s in result_imported.submodel.full_network.species
    }


# --- §7: no mutation of parent model -------------------------------------------------------------


def test_materialize_submodel_never_mutates_the_parent_model():
    model = _seed_model()
    before = replace(model)
    materialize_submodel(model, "seed", "modA")
    assert model == before


# --- §7: recursive compatibility -- candidate search, weight-space exploration, standalone -------
# --- Antimony generation, Harness->Agent3->Agent4 calibration orchestration compatibility --------


def test_materialized_submodel_is_valid_input_to_search_candidate_modularizations():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    round_result = run_candidate_search_round(
        result.submodel,
        result.submodel_modularization_id,
        _topology_weights(),
        _search_policy(),
        _calibration_selection_policy(),
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert round_result.search_result.model_id == result.submodel.model_id


def test_materialized_submodel_generates_executable_standalone_antimony():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    package = generate_antimony(result.submodel)
    assert package.full_antimony.readiness is AntimonyArtifactReadiness.EXECUTABLE
    (artifact,) = generate_module_artifacts(
        result.submodel, result.submodel_modularization_id, module_ids=(result.submodel_module_id,)
    )
    assert artifact.readiness is AntimonyArtifactReadiness.EXECUTABLE
    assert artifact.standalone_antimony is not None


def test_materialized_submodel_is_compatible_with_module_calibration_request_building():
    model = _seed_model()
    result = materialize_submodel(model, "seed", "modA")
    request = build_module_calibration_request(
        result.submodel,
        result.submodel_modularization_id,
        result.submodel_module_id,
        correlation_id="corr-1",
        run_id="run-1",
    )
    assert request.module_id == result.submodel_module_id
    assert request.module_handoff["antimony_text"]


def test_build_submodel_now_delegates_to_materialize_submodel_and_is_genuinely_scoped():
    """``app.agent2.candidate_orchestration.round.build_submodel``'s own external signature is
    unchanged, but it no longer carries the parent's entire, untruncated network forward."""
    model = _seed_model()
    submodel, sub_id = build_submodel(model, "seed", "modA")
    assert {r.reaction_id for r in submodel.full_network.reactions} == {"r1", "r2"}
    assert {s.species_id for s in submodel.full_network.species} == {"A", "B", "C"}
    assert sub_id == "submodel::seed::modA"
