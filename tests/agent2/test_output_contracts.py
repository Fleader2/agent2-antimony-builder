"""Tests for the top-level output contracts (Increment 1).

Covers ``ModelSpecification`` (and its full internal reference-integrity
validation), ``FullAntimonyArtifact``, ``ModuleAntimonyArtifact``, and
``Agent2OutputPackage``. No network assembly, kinetic-law assignment,
boundary heuristic, module partitioning, or Antimony generation algorithm
exists yet -- every object here is constructed directly.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.types import (
    Agent2OutputPackage,
    BoundaryAssessment,
    BoundaryLikelihood,
    CompartmentSourceScope,
    CompartmentSpecification,
    FullAntimonyArtifact,
    FullNetwork,
    KineticLawSpecification,
    KineticLawType,
    ModelAssumption,
    ModelSpecification,
    ModuleAntimonyArtifact,
    ModuleBoundaryInterface,
    ModuleDecomposition,
    ModuleInterfaceRole,
    ModuleSpecification,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)
from app.agent2.version import AGENT2_CONTRACT_VERSION


def _network() -> FullNetwork:
    compartment = CompartmentSpecification(
        compartment_id="c1",
        name="cytosol",
        source_scope=CompartmentSourceScope.AGENT1_CURATED,
        source_entity_id="agent1-c1",
    )
    species = SpeciesSpecification(species_id="s1", name="A", compartment_id="c1")
    participant = ReactionParticipantSpecification(
        species_id="s1", role=ParticipantRole.REACTANT, stoichiometry=Decimal("1")
    )
    reaction = ReactionSpecification(
        reaction_id="r1", name="test reaction", participants=(participant,), kinetic_law_id="k1"
    )
    return FullNetwork(
        network_id="n1",
        name="test network",
        compartments=(compartment,),
        species=(species,),
        reactions=(reaction,),
    )


def _kinetic_law(**overrides) -> KineticLawSpecification:
    merged = {
        "kinetic_law_id": "k1",
        "reaction_id": "r1",
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": ParameterSource.DEFAULT,
        "expression": "k1 * A",
        "parameter_ids": ("p1",),
        "species_ids": ("s1",),
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(**overrides) -> ParameterSpecification:
    merged = {
        "parameter_id": "p1",
        "name": "k1",
        "source": ParameterSource.DEFAULT,
        "reaction_id": "r1",
    } | overrides
    return ParameterSpecification(**merged)


def _boundary(**overrides) -> BoundaryAssessment:
    merged = {
        "boundary_id": "b1",
        "upstream_element_id": "r1",
        "downstream_element_id": "r1",
        "likelihood": BoundaryLikelihood.MEDIUM,
        "explanation": "test",
        "policy_version": "boundary-v1",
    } | overrides
    return BoundaryAssessment(**merged)


def _module(**overrides) -> ModuleSpecification:
    merged = {
        "module_id": "mod-1",
        "name": "test module",
        "reaction_ids": ("r1",),
        "species_ids": ("s1",),
        "parameter_ids": ("p1",),
        "kinetic_law_ids": ("k1",),
        "source_boundary_ids": ("b1",),
    } | overrides
    return ModuleSpecification(**merged)


def _model_specification(**overrides) -> ModelSpecification:
    merged = {
        "model_id": "m1",
        "name": "test model",
        "full_network": _network(),
        "kinetic_laws": (_kinetic_law(),),
        "parameters": (_parameter(),),
        "boundary_assessments": (_boundary(),),
        "module_specifications": (_module(),),
    } | overrides
    return ModelSpecification(**merged)


# --- Immutability -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls", [ModelSpecification, FullAntimonyArtifact, ModuleAntimonyArtifact, Agent2OutputPackage]
)
def test_output_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


def test_model_specification_instance_is_immutable():
    spec = _model_specification()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "renamed"


# --- ModelSpecification: valid construction ------------------------------------------------------


def test_model_specification_builds_with_valid_complete_object():
    spec = _model_specification()
    assert spec.full_network.network_id == "n1"
    assert spec.kinetic_laws[0].kinetic_law_id == "k1"
    assert spec.parameters[0].parameter_id == "p1"
    assert spec.module_specifications[0].module_id == "mod-1"
    assert spec.contract_version == AGENT2_CONTRACT_VERSION


def test_model_specification_can_hold_model_decomposition():
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test decomposition",
        policy_version="boundary-v1",
        created_from_network_id="n1",
        module_ids=("mod-1",),
        boundary_assessment_ids=("b1",),
    )
    spec = _model_specification(module_decomposition=decomposition)
    assert spec.module_decomposition.decomposition_id == "d1"


def test_model_specification_can_hold_model_assumptions():
    assumption = ModelAssumption(
        assumption_id="a1", category="kinetics", statement="assumed mass-action kinetics"
    )
    spec = _model_specification(model_assumptions=(assumption,))
    assert spec.model_assumptions[0].assumption_id == "a1"


# --- ModelSpecification: reference-integrity rejections --------------------------------------


def test_model_specification_rejects_kinetic_law_with_unknown_reaction_id():
    with pytest.raises(ValueError):
        _model_specification(kinetic_laws=(_kinetic_law(reaction_id="does-not-exist"),))


def test_model_specification_rejects_kinetic_law_with_unknown_parameter_id():
    with pytest.raises(ValueError):
        _model_specification(kinetic_laws=(_kinetic_law(parameter_ids=("missing-param",)),))


def test_model_specification_rejects_kinetic_law_with_unknown_species_id():
    with pytest.raises(ValueError):
        _model_specification(kinetic_laws=(_kinetic_law(species_ids=("missing-species",)),))


def test_model_specification_rejects_parameter_with_unknown_reaction_id():
    with pytest.raises(ValueError):
        _model_specification(parameters=(_parameter(reaction_id="does-not-exist"),))


def test_model_specification_rejects_reaction_with_unknown_kinetic_law_id():
    bad_network = dataclasses.replace(
        _network(),
        reactions=(
            ReactionSpecification(
                reaction_id="r1",
                name="test reaction",
                participants=(
                    ReactionParticipantSpecification(
                        species_id="s1", role=ParticipantRole.REACTANT, stoichiometry=Decimal("1")
                    ),
                ),
                kinetic_law_id="unknown-law",
            ),
        ),
    )
    with pytest.raises(ValueError):
        _model_specification(full_network=bad_network, kinetic_laws=(_kinetic_law(),))


def test_model_specification_rejects_module_with_unknown_species_id():
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(species_ids=("missing",)),))


def test_model_specification_rejects_module_with_unknown_reaction_id():
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(reaction_ids=("missing",)),))


def test_model_specification_rejects_module_with_unknown_parameter_id():
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(parameter_ids=("missing",)),))


def test_model_specification_rejects_module_with_unknown_kinetic_law_id():
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(kinetic_law_ids=("missing",)),))


def test_model_specification_rejects_module_with_unknown_source_boundary_id():
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(source_boundary_ids=("missing",)),))


def test_model_specification_rejects_module_boundary_interface_with_unknown_species():
    interface = ModuleBoundaryInterface(
        species_id="missing",
        role=ModuleInterfaceRole.INPUT,
        direction="inbound",
        assumption="test",
        externally_controlled=True,
    )
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(boundary_interfaces=(interface,)),))


def test_model_specification_rejects_decomposition_with_unknown_module_id():
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test",
        policy_version="boundary-v1",
        created_from_network_id="n1",
        module_ids=("missing-module",),
    )
    with pytest.raises(ValueError):
        _model_specification(module_decomposition=decomposition)


def test_model_specification_rejects_decomposition_with_unknown_boundary_id():
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test",
        policy_version="boundary-v1",
        created_from_network_id="n1",
        boundary_assessment_ids=("missing-boundary",),
    )
    with pytest.raises(ValueError):
        _model_specification(module_decomposition=decomposition)


def test_model_specification_rejects_decomposition_from_a_different_network():
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test",
        policy_version="boundary-v1",
        created_from_network_id="a-different-network",
    )
    with pytest.raises(ValueError):
        _model_specification(module_decomposition=decomposition)


def test_model_specification_rejects_duplicate_kinetic_law_ids():
    with pytest.raises(ValueError):
        _model_specification(kinetic_laws=(_kinetic_law(), _kinetic_law()))


def test_model_specification_rejects_duplicate_parameter_ids():
    with pytest.raises(ValueError):
        _model_specification(parameters=(_parameter(), _parameter()))


def test_model_specification_rejects_duplicate_module_ids():
    with pytest.raises(ValueError):
        _model_specification(module_specifications=(_module(), _module()))


def test_model_specification_rejects_duplicate_boundary_ids():
    with pytest.raises(ValueError):
        _model_specification(boundary_assessments=(_boundary(), _boundary()))


def test_model_specification_never_performs_agent3_level_validation():
    """A model with an unbalanced, single-participant reaction and no
    connectivity to anything else must still construct successfully."""
    spec = _model_specification()
    assert len(spec.full_network.reactions[0].participants) == 1


# --- FullAntimonyArtifact ----------------------------------------------------------------------


def test_full_antimony_artifact_construction():
    artifact = FullAntimonyArtifact(
        model_id="m1",
        model_specification_id="m1",
        antimony_text="// placeholder Antimony text",
        generator_version="0.0",
    )
    assert artifact.antimony_text == "// placeholder Antimony text"


def test_full_antimony_artifact_requires_non_blank_text():
    with pytest.raises(ValueError):
        FullAntimonyArtifact(
            model_id="m1", model_specification_id="m1", antimony_text="", generator_version="0.0"
        )


# --- ModuleAntimonyArtifact --------------------------------------------------------------------


def test_module_antimony_artifact_view_without_standalone_allowed():
    artifact = ModuleAntimonyArtifact(
        module_id="mod-1",
        model_specification_id="m1",
        generator_version="0.0",
        antimony_view="// module view only",
    )
    assert artifact.antimony_view == "// module view only"
    assert artifact.standalone_antimony is None


def test_module_antimony_artifact_standalone_requires_explicit_boundary_interfaces():
    with pytest.raises(ValueError):
        ModuleAntimonyArtifact(
            module_id="mod-1",
            model_specification_id="m1",
            generator_version="0.0",
            standalone_antimony="// standalone attempt",
        )


def test_module_antimony_artifact_standalone_allowed_with_explicit_interfaces():
    interface = ModuleBoundaryInterface(
        species_id="s1",
        role=ModuleInterfaceRole.INPUT,
        direction="inbound",
        assumption="constant",
        externally_controlled=True,
    )
    artifact = ModuleAntimonyArtifact(
        module_id="mod-1",
        model_specification_id="m1",
        generator_version="0.0",
        standalone_antimony="// standalone",
        boundary_interfaces=(interface,),
    )
    assert artifact.standalone_antimony == "// standalone"


def test_no_antimony_generator_function_exists_on_artifact_types():
    for cls in (FullAntimonyArtifact, ModuleAntimonyArtifact):
        assert not hasattr(cls, "generate")
        assert not hasattr(cls, "to_antimony")


# --- Agent2OutputPackage -----------------------------------------------------------------------


def _full_antimony(model_specification_id: str = "m1") -> FullAntimonyArtifact:
    return FullAntimonyArtifact(
        model_id="m1",
        model_specification_id=model_specification_id,
        antimony_text="// placeholder",
        generator_version="0.0",
    )


def test_agent2_output_package_valid_construction():
    spec = _model_specification()
    package = Agent2OutputPackage(
        contract_version=AGENT2_CONTRACT_VERSION,
        model_specification=spec,
        full_antimony=_full_antimony(),
        boundary_assessments=spec.boundary_assessments,
        module_decomposition=spec.module_decomposition,
    )
    assert package.model_specification.model_id == "m1"


def test_agent2_output_package_rejects_mismatched_full_antimony_link():
    spec = _model_specification()
    with pytest.raises(ValueError):
        Agent2OutputPackage(
            contract_version=AGENT2_CONTRACT_VERSION,
            model_specification=spec,
            full_antimony=_full_antimony(model_specification_id="different-model"),
        )


def test_agent2_output_package_rejects_module_artifact_for_unknown_module():
    spec = _model_specification()
    artifact = ModuleAntimonyArtifact(
        module_id="unknown-module",
        model_specification_id="m1",
        generator_version="0.0",
        antimony_view="// view",
    )
    with pytest.raises(ValueError):
        Agent2OutputPackage(
            contract_version=AGENT2_CONTRACT_VERSION,
            model_specification=spec,
            full_antimony=_full_antimony(),
            module_artifacts=(artifact,),
        )


def test_agent2_output_package_rejects_duplicate_module_artifacts():
    spec = _model_specification()
    artifact = ModuleAntimonyArtifact(
        module_id="mod-1",
        model_specification_id="m1",
        generator_version="0.0",
        antimony_view="// view",
    )
    with pytest.raises(ValueError):
        Agent2OutputPackage(
            contract_version=AGENT2_CONTRACT_VERSION,
            model_specification=spec,
            full_antimony=_full_antimony(),
            module_artifacts=(artifact, artifact),
        )


def test_agent2_output_package_requires_matching_boundary_assessments():
    spec = _model_specification()
    with pytest.raises(ValueError):
        Agent2OutputPackage(
            contract_version=AGENT2_CONTRACT_VERSION,
            model_specification=spec,
            full_antimony=_full_antimony(),
            boundary_assessments=(),
        )


def test_agent2_output_package_requires_matching_module_decomposition():
    spec = _model_specification()
    other_decomposition = ModuleDecomposition(
        decomposition_id="different",
        name="different",
        policy_version="boundary-v1",
        created_from_network_id="n1",
    )
    with pytest.raises(ValueError):
        Agent2OutputPackage(
            contract_version=AGENT2_CONTRACT_VERSION,
            model_specification=spec,
            full_antimony=_full_antimony(),
            boundary_assessments=spec.boundary_assessments,
            module_decomposition=other_decomposition,
        )


def test_agent2_output_package_full_model_linkage_accepts_valid_artifact():
    spec = _model_specification()
    artifact = ModuleAntimonyArtifact(
        module_id="mod-1",
        model_specification_id="m1",
        generator_version="0.0",
        antimony_view="// view",
    )
    package = Agent2OutputPackage(
        contract_version=AGENT2_CONTRACT_VERSION,
        model_specification=spec,
        full_antimony=_full_antimony(),
        module_artifacts=(artifact,),
        boundary_assessments=spec.boundary_assessments,
        module_decomposition=spec.module_decomposition,
    )
    assert package.module_artifacts[0].module_id == "mod-1"
