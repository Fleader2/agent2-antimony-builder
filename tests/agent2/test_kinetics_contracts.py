"""Tests for the kinetics and parameters domain (Increment 1).

Covers ``KineticLawType``, ``KineticLawSpecification``, and
``ParameterSpecification``. No kinetic-law assignment or parameter
initialization algorithm exists yet -- every object here is constructed
directly, and no expression is ever parsed or evaluated.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.agent2.types import (
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ParameterSource,
    ParameterSpecification,
)


def _kinetic_law(**overrides) -> KineticLawSpecification:
    merged = {
        "kinetic_law_id": "k1",
        "reaction_id": "r1",
        "law_type": KineticLawType.MASS_ACTION,
        "assignment_source": KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        "expression": "k1 * A * B",
    } | overrides
    return KineticLawSpecification(**merged)


def _parameter(**overrides) -> ParameterSpecification:
    merged = {"parameter_id": "p1", "name": "k1", "source": ParameterSource.DEFAULT} | overrides
    return ParameterSpecification(**merged)


# --- Enum vocabulary -----------------------------------------------------------------------


def test_kinetic_law_type_has_exactly_six_values():
    assert {member.value for member in KineticLawType} == {
        "MASS_ACTION",
        "MICHAELIS_MENTEN",
        "HILL",
        "REVERSIBLE_MASS_ACTION",
        "CUSTOM",
        "UNASSIGNED",
    }


# --- Immutability -----------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [KineticLawSpecification, ParameterSpecification])
def test_kinetics_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


def test_parameter_specification_instance_is_immutable():
    parameter = _parameter()
    with pytest.raises(dataclasses.FrozenInstanceError):
        parameter.value = Decimal("1")


# --- KineticLawSpecification -------------------------------------------------------------------


def test_unassigned_law_may_omit_expression():
    law = KineticLawSpecification(
        kinetic_law_id="k1",
        reaction_id="r1",
        law_type=KineticLawType.UNASSIGNED,
        assignment_source=KineticLawAssignmentSource.UNASSIGNED,
    )
    assert law.expression is None


def test_assigned_law_may_omit_expression():
    """Pre-commit revision: `expression` is optional for every `law_type`, not only
    `UNASSIGNED` -- a law family can be known while its exact algebra remains unresolved (e.g.
    a multi-substrate Michaelis-Menten assignment, `app.agent2.model_specification`). The
    previous rule requiring a non-blank expression for any non-UNASSIGNED law_type has been
    removed; `KineticLawType.UNASSIGNED` remains the only way to say "no law was ever
    selected" -- expression=None on an assigned type instead means "family known, algebra
    unresolved."."""
    law = KineticLawSpecification(
        kinetic_law_id="k1",
        reaction_id="r1",
        law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
    )
    assert law.expression is None
    assert law.law_type is KineticLawType.MASS_ACTION
    assert law.has_expression is False
    # A whitespace-only expression is silently normalized to None (already-established
    # _clean_optional_str convention), not rejected.
    blank = KineticLawSpecification(
        kinetic_law_id="k1",
        reaction_id="r1",
        law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        expression="   ",
    )
    assert blank.expression is None


def test_has_expression_property():
    with_expression = _kinetic_law(expression="k1 * A")
    without_expression = _kinetic_law(expression=None)
    assert with_expression.has_expression is True
    assert without_expression.has_expression is False


def test_law_type_requires_real_enum():
    with pytest.raises(TypeError):
        _kinetic_law(law_type="MASS_ACTION")


def test_assignment_source_requires_real_kinetic_law_assignment_source_enum():
    """Increment 8 pre-commit revision: `assignment_source` is `KineticLawAssignmentSource`,
    not `ParameterSource` -- a law's type provenance and a parameter's value provenance are
    different axes (see that enum's own docstring, `docs/11_model_specification_assembly.md`
    §10). A `ParameterSource` value is therefore itself now rejected, not just a bare string."""
    with pytest.raises(TypeError):
        _kinetic_law(assignment_source="DETERMINISTIC_STRUCTURAL")
    with pytest.raises(TypeError):
        _kinetic_law(assignment_source=ParameterSource.DEFAULT)


def test_kinetic_law_never_parses_or_evaluates_expression():
    """A syntactically nonsensical expression must still construct -- no
    parsing/generation logic exists in Increment 1."""
    law = _kinetic_law(expression="this is not a valid rate law at all !!")
    assert law.expression == "this is not a valid rate law at all !!"


# --- Catalytic-context target (Increment 8 pre-commit revision) ---------------------------------


def test_kinetic_law_catalytic_context_defaults_to_none():
    law = _kinetic_law()
    assert law.enzyme_state_id is None
    assert law.protein_id is None
    assert law.complex_id is None


def test_kinetic_law_accepts_one_catalytic_context_field():
    law = _kinetic_law(enzyme_state_id="E_P")
    assert law.enzyme_state_id == "E_P"
    assert law.protein_id is None
    assert law.complex_id is None


def test_kinetic_law_rejects_more_than_one_catalytic_context_field():
    with pytest.raises(ValueError):
        _kinetic_law(enzyme_state_id="E_P", protein_id="p1")
    with pytest.raises(ValueError):
        _kinetic_law(protein_id="p1", complex_id="c1")


# --- ParameterSpecification --------------------------------------------------------------------


def test_parameter_source_exact_vocabulary_enforced():
    with pytest.raises(TypeError):
        _parameter(source="DEFAULT")


def test_parameter_value_may_be_none():
    parameter = _parameter()
    assert parameter.value is None
    assert parameter.has_value is False


def test_parameter_value_must_be_decimal():
    with pytest.raises(TypeError):
        _parameter(value=1.23)
    parameter = _parameter(value=Decimal("1.23"))
    assert parameter.value == Decimal("1.23")
    assert parameter.has_value is True


def test_parameter_placeholder_is_distinguishable():
    parameter = _parameter(source=ParameterSource.PLACEHOLDER)
    assert parameter.is_placeholder is True
    assert parameter.is_curated is False
    assert parameter.is_calibrated is False


def test_parameter_calibrated_is_preserved_with_no_fitting_logic():
    """Increment 1 only preserves the CALIBRATED source -- it never computes one."""
    parameter = _parameter(source=ParameterSource.CALIBRATED, value=Decimal("4.2"))
    assert parameter.is_calibrated is True
    assert parameter.value == Decimal("4.2")


def test_parameter_curated_is_distinguishable():
    parameter = _parameter(source=ParameterSource.CURATED, value=Decimal("1"))
    assert parameter.is_curated is True
    assert parameter.is_placeholder is False


def test_parameter_valid_bounds_accepted():
    parameter = _parameter(lower_bound=Decimal("0"), upper_bound=Decimal("10"))
    assert parameter.lower_bound == Decimal("0")
    assert parameter.upper_bound == Decimal("10")


def test_parameter_invalid_bounds_rejected():
    with pytest.raises(ValueError):
        _parameter(lower_bound=Decimal("10"), upper_bound=Decimal("0"))


def test_parameter_bounds_must_be_decimal():
    with pytest.raises(TypeError):
        _parameter(lower_bound=0.0)
    with pytest.raises(TypeError):
        _parameter(upper_bound=10.0)


def test_parameter_unit_never_invented():
    parameter = _parameter(value=Decimal("1"))
    assert parameter.unit is None


def test_parameter_fixed_flag_is_independent_bool():
    parameter = _parameter(fixed=True)
    assert parameter.fixed is True
    with pytest.raises(TypeError):
        _parameter(fixed="yes")
