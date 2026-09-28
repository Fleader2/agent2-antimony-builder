"""General/scope tests for Agent 2 (Increment 1: contracts only).

Covers what does not belong to one specific domain file: shared enum
vocabularies, version constants, general immutability, the Agent 1
handoff decoupling, and scope-safety (imports/definitions). Domain-specific
contract behavior lives in ``test_network_contracts.py``,
``test_kinetics_contracts.py``, ``test_module_contracts.py``, and
``test_output_contracts.py``.

Structural checks (imports, definitions) use ``ast`` rather than naive
substring search, so a module's own docstring is free to discuss
Antimony/Tellurium/etc. while explaining what it does *not* do.
"""

from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from app import agent2
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    BoundaryAssessment,
    BoundaryLikelihood,
    CuratedCompartment,
    CuratedKineticMeasurement,
    ModuleBoundaryInterface,
    ModuleDecomposition,
    ModuleSpecification,
    ParameterSource,
)
from app.agent2.version import (
    AGENT1_HANDOFF_VERSION,
    AGENT2_CONTRACT_VERSION,
    BOUNDARY_POLICY_VERSION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"


# --- Enum vocabularies -----------------------------------------------------------------------


def test_boundary_likelihood_has_exactly_five_values():
    assert {member.value for member in BoundaryLikelihood} == {
        "VERY_LOW",
        "LOW",
        "MEDIUM",
        "HIGH",
        "VERY_HIGH",
    }


def test_parameter_source_has_exactly_seven_values():
    """AI_PREDICTED/HEURISTIC_INITIALIZATION added by the Heuristic Simulation Parameter
    Initialization increment -- two new, distinct rungs, never confused with the five
    original values."""
    assert {member.value for member in ParameterSource} == {
        "CURATED",
        "LITERATURE_DERIVED",
        "AI_PREDICTED",
        "HEURISTIC_INITIALIZATION",
        "DEFAULT",
        "PLACEHOLDER",
        "CALIBRATED",
    }


# --- Version constants -----------------------------------------------------------------------


def test_version_constants_exist_and_are_non_empty_strings():
    for value in (AGENT2_CONTRACT_VERSION, AGENT1_HANDOFF_VERSION, BOUNDARY_POLICY_VERSION):
        assert isinstance(value, str)
        assert value.strip()


def test_version_constants_are_exported_from_package_root():
    assert agent2.AGENT2_CONTRACT_VERSION == AGENT2_CONTRACT_VERSION
    assert agent2.AGENT1_HANDOFF_VERSION == AGENT1_HANDOFF_VERSION
    assert agent2.BOUNDARY_POLICY_VERSION == BOUNDARY_POLICY_VERSION


# --- Immutability -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        Agent1CuratedKnowledgeViewContract,
        CuratedCompartment,
        CuratedKineticMeasurement,
        BoundaryAssessment,
        ModuleBoundaryInterface,
        ModuleSpecification,
        ModuleDecomposition,
    ],
)
def test_contract_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


# --- Agent 1 handoff decoupling ------------------------------------------------------------------


def test_agent1_curated_knowledge_view_contract_builds_with_no_agent1_dependency():
    view = Agent1CuratedKnowledgeViewContract(
        contract_version=AGENT1_HANDOFF_VERSION,
        organism_id="org-1",
        compartments=(CuratedCompartment(id="c1", name="cytosol"),),
        limitations=("regulation is schema-ready, not curated end-to-end",),
    )
    assert view.compartments[0].name == "cytosol"


def test_types_module_never_imports_agent1_package():
    """Checks actual import statements via ast, not the bare word 'agent1'
    (which this module's own docstrings/comments use in prose)."""
    source = (APP_ROOT / "agent2" / "types.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert "agent1" not in imported_roots
    assert "app" not in imported_roots or all(
        not name.startswith("agent1") for name in imported_roots
    )


# --- CuratedKineticMeasurement (Agent 1.x Increment A) --------------------------------------


def test_curated_kinetic_measurement_builds_with_minimal_fields():
    measurement = CuratedKineticMeasurement(
        id="km-1", parameter_type="KM", value=Decimal("0.5"), unit="mM"
    )
    assert measurement.reaction_id is None
    assert measurement.normalized_value is None
    assert measurement.normalized_unit is None


def test_curated_kinetic_measurement_value_must_be_decimal_not_float():
    with pytest.raises(TypeError):
        CuratedKineticMeasurement(id="km-1", parameter_type="KM", value=0.5, unit="mM")


def test_curated_kinetic_measurement_rejects_empty_id():
    with pytest.raises(ValueError):
        CuratedKineticMeasurement(id="", parameter_type="KM", value=Decimal("0.5"), unit="mM")


def test_curated_kinetic_measurement_rejects_empty_unit():
    with pytest.raises(ValueError):
        CuratedKineticMeasurement(id="km-1", parameter_type="KM", value=Decimal("0.5"), unit="")


def test_curated_kinetic_measurement_normalized_value_must_be_decimal_or_none():
    with pytest.raises(TypeError):
        CuratedKineticMeasurement(
            id="km-1",
            parameter_type="KM",
            value=Decimal("0.5"),
            unit="mM",
            normalized_value=0.5,
        )


def test_agent1_curated_knowledge_view_contract_carries_kinetic_measurements():
    view = Agent1CuratedKnowledgeViewContract(
        contract_version=AGENT1_HANDOFF_VERSION,
        kinetic_measurements=(
            CuratedKineticMeasurement(
                id="km-1", parameter_type="KM", value=Decimal("0.5"), unit="mM"
            ),
        ),
    )
    assert view.kinetic_measurements[0].id == "km-1"


def test_agent1_curated_knowledge_view_contract_kinetic_measurements_default_empty():
    view = Agent1CuratedKnowledgeViewContract(contract_version=AGENT1_HANDOFF_VERSION)
    assert view.kinetic_measurements == ()


def test_claim_value_numeric_must_be_decimal_not_float():
    from app.agent2.types import CuratedClaim

    with pytest.raises(TypeError):
        CuratedClaim(id="c1", subject_type="protein", predicate="catalyzes", value_numeric=1.23)
    claim = CuratedClaim(
        id="c1", subject_type="protein", predicate="catalyzes", value_numeric=Decimal("1.23")
    )
    assert claim.value_numeric == Decimal("1.23")


# --- Scope-safety: no forbidden implementation exists yet ----------------------------------------


_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "tellurium",
        "roadrunner",
        "libroadrunner",
        "libsbml",
        "antimony",
        "COPASI",
        "basico",
        "cobra",
        "numpy",
        "scipy",
        "pandas",
        "networkx",
    }
)

# Checked against actual `def`/`class` names only, case-insensitive, with
# underscores stripped -- never against prose.
#
# "generateantimony" was removed from this list in Increment 9 (Antimony
# Generation): that increment's own specification explicitly authorizes
# exactly one public function of this name
# (``app.agent2.antimony.generate_antimony``, a deterministic text
# serializer -- never simulation, fitting, or a modeling-decision engine).
# Every other substring below remains forbidden -- Increment 9 did not
# authorize simulation, fitting, calibration, or model critique.
_FORBIDDEN_DEFINITION_SUBSTRINGS = (
    "buildantimony",
    "antimonygenerator",
    "sbmlgenerator",
    "runsimulation",
    "simulate",
    "simulation",
    "parameterfit",
    "parameterestimation",
    "runcalibration",
    "performcalibration",
    "calibrateparameter",
    "sensitivityanalysis",
    "steadystateanalysis",
    "massbalance",
    "conservationlaw",
    "modelcritic",
    "thermodynamiccritique",
    "assemblenetwork",
    "networkassembler",
    "kineticassigner",
    "selectkineticlaw",
    "boundaryengine",
    "assessboundary",
    "partitionmodules",
    "modulepartitioner",
)


def _iter_app_python_files():
    yield from APP_ROOT.rglob("*.py")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_forbidden_library_imported_anywhere_in_app():
    offenders: dict[str, set[str]] = {}
    for path in _iter_app_python_files():
        tree = _parse(path)
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        hits = roots & _FORBIDDEN_IMPORT_ROOTS
        if hits:
            offenders[str(path.relative_to(PROJECT_ROOT))] = hits
    assert offenders == {}, f"forbidden simulation/modeling-execution imports found: {offenders}"


def test_no_forbidden_definitions_anywhere_in_app():
    offenders: dict[str, set[str]] = {}
    for path in _iter_app_python_files():
        tree = _parse(path)
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
        hits = {
            name
            for name in defined
            if any(
                substring in name.lower().replace("_", "")
                for substring in _FORBIDDEN_DEFINITION_SUBSTRINGS
            )
        }
        if hits:
            offenders[str(path.relative_to(PROJECT_ROOT))] = hits
    assert offenders == {}, f"forbidden generation/simulation definitions found: {offenders}"


def test_no_agent1_connector_or_runtime_import_anywhere_in_app():
    offenders: dict[str, set[str]] = {}
    for path in _iter_app_python_files():
        tree = _parse(path)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        hits = {
            module
            for module in imported_modules
            if module == "agent1" or module.startswith("agent1.")
        }
        if hits:
            offenders[str(path.relative_to(PROJECT_ROOT))] = hits
    assert offenders == {}, f"Agent 1 runtime imports found: {offenders}"


def test_no_antimony_generation_service_module_exists_yet():
    assert not (APP_ROOT / "agent2" / "antimony.py").exists()
    assert not (APP_ROOT / "agent2" / "generator.py").exists()
    assert not (APP_ROOT / "agent2" / "service.py").exists()
    assert not (APP_ROOT / "agent2" / "network_assembler.py").exists()
    assert not (APP_ROOT / "agent2" / "kinetic_assigner.py").exists()
    assert not (APP_ROOT / "agent2" / "boundary_engine.py").exists()
    assert not (APP_ROOT / "agent2" / "module_partitioner.py").exists()
    assert not (APP_ROOT / "agent2" / "antimony_generator.py").exists()


def test_no_simulation_or_validation_module_exists_yet():
    for stale_name in ("simulate.py", "simulation.py", "validate.py", "validator.py", "critic.py"):
        assert not (APP_ROOT / "agent2" / stale_name).exists()


def test_pyproject_declares_no_modeling_or_simulation_dependency():
    import tomllib

    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    dependencies = data.get("project", {}).get("dependencies", [])
    all_dependency_text = " ".join(dependencies).lower()
    for forbidden in (
        "tellurium",
        "libsbml",
        "antimony",
        "copasi",
        "basico",
        "roadrunner",
        "numpy",
        "scipy",
        "pandas",
        "networkx",
    ):
        assert forbidden not in all_dependency_text
