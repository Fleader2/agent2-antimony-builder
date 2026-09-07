"""Tests for the module-decomposition domain (Increment 1).

Covers ``BoundaryAssessment``, ``BoundaryParameterBasis``,
``ModuleBoundaryInterface``, ``ModuleInterfaceRole``,
``ModuleSpecification``, and ``ModuleDecomposition``. No boundary
heuristic or partitioning algorithm exists yet -- every object here is
constructed directly.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.types import (
    BoundaryAssessment,
    BoundaryLikelihood,
    BoundaryParameterBasis,
    ModuleBoundaryInterface,
    ModuleDecomposition,
    ModuleInterfaceRole,
    ModuleSpecification,
)


def _boundary(**overrides) -> BoundaryAssessment:
    merged = {
        "boundary_id": "b1",
        "upstream_element_id": "r1",
        "downstream_element_id": "r2",
        "likelihood": BoundaryLikelihood.MEDIUM,
        "explanation": "test-only explanation",
        "policy_version": "boundary-v1",
    } | overrides
    return BoundaryAssessment(**merged)


def _interface(**overrides) -> ModuleBoundaryInterface:
    merged = {
        "species_id": "s1",
        "role": ModuleInterfaceRole.INPUT,
        "direction": "inbound",
        "assumption": "constant external concentration",
        "externally_controlled": True,
    } | overrides
    return ModuleBoundaryInterface(**merged)


def _module(**overrides) -> ModuleSpecification:
    merged = {"module_id": "mod-1", "name": "test module", "reaction_ids": ("r1",)} | overrides
    return ModuleSpecification(**merged)


# --- Enum vocabularies -----------------------------------------------------------------------


def test_boundary_parameter_basis_has_exactly_six_values():
    assert {member.value for member in BoundaryParameterBasis} == {
        "NONE",
        "PLACEHOLDER_ONLY",
        "DEFAULT_ONLY",
        "CURATED_OR_LITERATURE",
        "CALIBRATED",
        "MIXED",
    }


def test_module_interface_role_has_exactly_four_values():
    assert {member.value for member in ModuleInterfaceRole} == {
        "INPUT",
        "OUTPUT",
        "BIDIRECTIONAL",
        "SHARED",
    }


# --- Immutability -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [BoundaryAssessment, ModuleBoundaryInterface, ModuleSpecification, ModuleDecomposition],
)
def test_module_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


# --- BoundaryAssessment: qualitative only ------------------------------------------------------


def test_boundary_assessment_has_no_numeric_probability_field():
    boundary = _boundary()
    field_names = {f.name for f in dataclasses.fields(boundary)}
    for forbidden in ("probability", "score", "confidence", "weight"):
        assert forbidden not in field_names


def test_boundary_assessment_likelihood_requires_real_enum():
    with pytest.raises(TypeError):
        _boundary(likelihood="MEDIUM")


def test_boundary_assessment_supporting_and_opposing_reasons_preserved():
    boundary = _boundary(
        supporting_reason_codes=("COMPARTMENT_TRANSITION",),
        opposing_reason_codes=("SHARED_HIGH_FLUX_INTERMEDIATE",),
    )
    assert boundary.supporting_reason_codes == ("COMPARTMENT_TRANSITION",)
    assert boundary.opposing_reason_codes == ("SHARED_HIGH_FLUX_INTERMEDIATE",)


def test_boundary_assessment_parameter_basis_requires_real_enum():
    with pytest.raises(TypeError):
        _boundary(parameter_basis="MIXED")
    boundary = _boundary(parameter_basis=BoundaryParameterBasis.MIXED)
    assert boundary.parameter_basis is BoundaryParameterBasis.MIXED


def test_boundary_assessment_parameter_basis_defaults_to_none():
    boundary = _boundary()
    assert boundary.parameter_basis is None


def test_boundary_assessment_requires_policy_version():
    with pytest.raises(ValueError):
        BoundaryAssessment(
            boundary_id="b1",
            upstream_element_id="r1",
            downstream_element_id="r2",
            likelihood=BoundaryLikelihood.LOW,
            explanation="test",
            policy_version="",
        )


# --- ModuleBoundaryInterface --------------------------------------------------------------------


def test_module_boundary_interface_role_requires_real_enum():
    with pytest.raises(TypeError):
        _interface(role="INPUT")


def test_module_boundary_interface_externally_controlled_must_be_bool():
    with pytest.raises(TypeError):
        _interface(externally_controlled="yes")


def test_module_boundary_interface_initial_value_must_be_decimal():
    with pytest.raises(TypeError):
        _interface(initial_value=1.0)
    interface = _interface(initial_value=Decimal("1.0"), unit="mM")
    assert interface.initial_value == Decimal("1.0")


# --- ModuleSpecification -----------------------------------------------------------------------


def test_module_requires_at_least_one_reaction():
    with pytest.raises(ValueError):
        ModuleSpecification(module_id="mod-1", name="empty module", reaction_ids=())


def test_module_with_explicit_boundary_interfaces():
    module = _module(boundary_interfaces=(_interface(),))
    assert module.has_explicit_boundary_interfaces is True


def test_module_without_boundary_interfaces():
    module = _module()
    assert module.has_explicit_boundary_interfaces is False


def test_module_rejects_duplicate_ids_within_a_category():
    with pytest.raises(ValueError):
        _module(reaction_ids=("r1", "r1"))
    with pytest.raises(ValueError):
        _module(species_ids=("s1", "s1"))
    with pytest.raises(ValueError):
        _module(parameter_ids=("p1", "p1"))
    with pytest.raises(ValueError):
        _module(kinetic_law_ids=("k1", "k1"))


def test_module_rejects_non_interface_items():
    with pytest.raises(TypeError):
        _module(boundary_interfaces=("bad",))


def test_module_traceable_to_source_boundaries():
    module = _module(source_boundary_ids=("b1", "b2"))
    assert module.source_boundary_ids == ("b1", "b2")


# --- ModuleDecomposition -----------------------------------------------------------------------


def test_module_decomposition_references_modules_by_id_only():
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test decomposition",
        policy_version="boundary-v1",
        created_from_network_id="n1",
        module_ids=("mod-1", "mod-2"),
        boundary_assessment_ids=("b1",),
    )
    assert decomposition.module_ids == ("mod-1", "mod-2")


def test_module_decomposition_rejects_duplicate_module_ids():
    with pytest.raises(ValueError):
        ModuleDecomposition(
            decomposition_id="d1",
            name="test decomposition",
            policy_version="boundary-v1",
            created_from_network_id="n1",
            module_ids=("mod-1", "mod-1"),
        )


def test_module_decomposition_rejects_duplicate_boundary_ids():
    with pytest.raises(ValueError):
        ModuleDecomposition(
            decomposition_id="d1",
            name="test decomposition",
            policy_version="boundary-v1",
            created_from_network_id="n1",
            boundary_assessment_ids=("b1", "b1"),
        )


def test_module_decomposition_parameter_basis_summary_requires_real_enum():
    with pytest.raises(TypeError):
        ModuleDecomposition(
            decomposition_id="d1",
            name="test decomposition",
            policy_version="boundary-v1",
            created_from_network_id="n1",
            parameter_basis_summary="MIXED",
        )
