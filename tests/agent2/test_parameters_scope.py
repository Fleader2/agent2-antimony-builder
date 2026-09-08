"""Scope-safety tests for Parameter Declaration / Initialization (Increment 5).

Confirms ``app.agent2.parameters`` never reaches for boundary assessment,
module decomposition, Antimony generation, simulation, fitting/
calibration/optimization, an LLM, or Agent 1's runtime -- all of which
are explicit non-goals of this increment (see
``docs/08_parameter_declaration_initialization.md`` §19).
"""

from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
PARAMETERS_ROOT = APP_ROOT / "agent2" / "parameters"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_parameters_package_never_imports_forbidden_modeling_libraries():
    forbidden_roots = {
        "tellurium",
        "roadrunner",
        "libsbml",
        "antimony",
        "COPASI",
        "scipy",
        "numpy",
    }
    for path in PARAMETERS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_parameters_package_never_imports_agent1_package():
    for path in PARAMETERS_ROOT.glob("*.py"):
        assert "agent1" not in _imported_roots(path)


def test_parameters_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in PARAMETERS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_parameters_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in PARAMETERS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_parameters_package_never_imports_random_module():
    forbidden_roots = {"random", "secrets", "uuid"}
    for path in PARAMETERS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_parameters_package_defines_no_boundary_or_module_or_antimony_logic():
    forbidden_substrings = (
        "BoundaryAssessment(",
        "BoundaryLikelihood(",
        "ModuleSpecification(",
        "ModuleDecomposition(",
        "ModuleBoundaryInterface(",
        "FullAntimonyArtifact(",
        "ModuleAntimonyArtifact(",
        "ModelSpecification(",
        "antimony",
        "tellurium",
        "roadrunner",
    )
    for path in PARAMETERS_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_parameters_package_never_invokes_simulation_fitting_or_later_agents():
    """No call-site usage of simulation/fitting/calibration/later-agent behavior.

    Deliberately checks for actual invocation patterns, not the bare
    words -- this package's own docstrings legitimately say things like
    "no fitting" or "no calibration" to document what it does *not* do.
    """
    forbidden_substrings = (
        "curve_fit(",
        "least_squares(",
        "roadrunner.",
        "te.load",
        "app.agent3",
        "app.agent4",
        "app.agent5",
        "scipy.optimize",
    )
    for path in PARAMETERS_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_parameters_package_never_assigns_calibrated_source():
    """No call site in this package literally names ParameterSource.CALIBRATED as an
    assignment target -- it appears only in the defensive backstop check and comments."""
    source = (PARAMETERS_ROOT / "builder.py").read_text(encoding="utf-8")
    assignment_lines = [
        line
        for line in source.splitlines()
        if "ParameterSource.CALIBRATED" in line and "source=" in line
    ]
    assert assignment_lines == []


def test_no_boundary_or_module_or_antimony_artifacts_from_a_real_run():
    """Structural check backed by an actual execution."""
    handoff = Agent1CuratedKnowledgeViewContract(
        contract_version="1.2",
        compartments=(CuratedCompartment(id="cyto", name="cytosol"),),
        compounds=(
            CuratedCompound(id="glc", name="glucose"),
            CuratedCompound(id="g6p", name="glucose-6-phosphate"),
        ),
        reactions=(CuratedReaction(id="r1", name="hexokinase reaction"),),
        reaction_participants=(
            CuratedReactionParticipant(
                reaction_id="r1",
                compound_id="glc",
                role="REACTANT",
                stoichiometry=Decimal("1"),
                compartment_id="cyto",
            ),
            CuratedReactionParticipant(
                reaction_id="r1",
                compound_id="g6p",
                role="PRODUCT",
                stoichiometry=Decimal("1"),
                compartment_id="cyto",
            ),
        ),
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(
                reaction_id="r1", protein_id="hk1", relationship="CATALYZES"
            ),
        ),
    )
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    declaration = declare_parameters(assignments, network)
    for spec in declaration.parameter_specifications:
        assert not hasattr(spec, "boundary_likelihood")
        assert not hasattr(spec, "module_id")
        field_names = {f.name for f in dataclasses.fields(type(spec))}
        assert "boundary_likelihood" not in field_names
        assert "antimony_text" not in field_names
