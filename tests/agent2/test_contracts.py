"""Architecture/scope tests for Agent 2 (Increment 1: contracts only).

These tests verify the *shape and boundaries* of the seeded contracts --
not any generation behavior, since none exists yet. Structural checks
(imports, definitions) use ``ast`` rather than naive substring search, so
a module's own docstring is free to discuss Antimony/Tellurium/etc. while
explaining what it does *not* do.
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
    ModelSpecification,
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


def test_parameter_source_has_exactly_five_values():
    assert {member.value for member in ParameterSource} == {
        "CURATED",
        "LITERATURE_DERIVED",
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
        BoundaryAssessment,
        ModuleBoundaryInterface,
        ModuleSpecification,
        ModuleDecomposition,
        ModelSpecification,
    ],
)
def test_contract_types_are_frozen_dataclasses(cls):
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


def test_model_specification_instance_is_immutable():
    spec = ModelSpecification(model_id="m1", name="test model", full_network_id="net-1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "renamed"


# --- Cross-references between contracts ---------------------------------------------------------


def test_model_specification_can_reference_boundary_assessments_and_module_decomposition():
    boundary = BoundaryAssessment(
        boundary_id="b1",
        upstream_element_id="reaction-1",
        downstream_element_id="reaction-2",
        likelihood=BoundaryLikelihood.MEDIUM,
        explanation="test-only explanation",
    )
    decomposition = ModuleDecomposition(
        decomposition_id="d1",
        name="test decomposition",
        policy_version=BOUNDARY_POLICY_VERSION,
        boundary_assessment_ids=("b1",),
    )
    module = ModuleSpecification(module_id="mod-1", name="test module", source_boundary_ids=("b1",))

    spec = ModelSpecification(
        model_id="m1",
        name="test model",
        full_network_id="net-1",
        boundary_assessments=(boundary,),
        module_decomposition=decomposition,
        module_specifications=(module,),
    )

    assert spec.boundary_assessments[0].boundary_id == "b1"
    assert spec.module_decomposition.decomposition_id == "d1"
    assert spec.module_specifications[0].module_id == "mod-1"


def test_model_specification_rejects_non_boundary_assessment_items():
    with pytest.raises(TypeError):
        ModelSpecification(
            model_id="m1",
            name="test model",
            full_network_id="net-1",
            boundary_assessments=("not-a-boundary-assessment",),
        )


def test_module_specification_can_reference_boundary_interfaces():
    interface = ModuleBoundaryInterface(
        species_id="species-1",
        role="input",
        direction="inbound",
        assumption="constant external concentration",
        externally_controlled=True,
    )
    module = ModuleSpecification(
        module_id="mod-1", name="test module", boundary_interfaces=(interface,)
    )
    assert module.boundary_interfaces[0].species_id == "species-1"


def test_module_specification_rejects_non_interface_items():
    with pytest.raises(TypeError):
        ModuleSpecification(module_id="mod-1", name="test module", boundary_interfaces=("bad",))


def test_boundary_assessment_requires_a_real_likelihood_enum():
    with pytest.raises(TypeError):
        BoundaryAssessment(
            boundary_id="b1",
            upstream_element_id="e1",
            downstream_element_id="e2",
            likelihood="MEDIUM",  # a plain string, not a BoundaryLikelihood
            explanation="test",
        )


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
    }
)

# Checked against actual `def`/`class` names only, case-insensitive, with
# underscores stripped -- never against prose.
_FORBIDDEN_DEFINITION_SUBSTRINGS = (
    "generateantimony",
    "buildantimony",
    "antimonygenerator",
    "sbmlgenerator",
    "runsimulation",
    "simulate",
    "simulation",
    "parameterfit",
    "parameterestimation",
    "calibrate",
    "sensitivityanalysis",
    "steadystateanalysis",
    "massbalance",
    "conservationlaw",
    "modelcritic",
    "thermodynamiccritique",
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


def test_no_simulation_or_validation_module_exists_yet():
    for stale_name in ("simulate.py", "simulation.py", "validate.py", "validator.py", "critic.py"):
        assert not (APP_ROOT / "agent2" / stale_name).exists()


def test_pyproject_declares_no_modeling_or_simulation_dependency():
    import tomllib

    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    dependencies = data.get("project", {}).get("dependencies", [])
    all_dependency_text = " ".join(dependencies).lower()
    for forbidden in ("tellurium", "libsbml", "antimony", "copasi", "basico", "roadrunner"):
        assert forbidden not in all_dependency_text
