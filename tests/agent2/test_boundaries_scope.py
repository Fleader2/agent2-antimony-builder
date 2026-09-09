"""Scope-safety tests for Heuristic Boundary Assessment (Increment 6).

Confirms ``app.agent2.boundaries`` never reaches for module decomposition,
Antimony generation, simulation, fitting, Agent 3 validation, Agent 5
critique, an LLM, or Agent 1's runtime -- all of which are explicit
non-goals of this increment (see
``docs/09_heuristic_boundary_assessment.md`` §28).
"""

from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
from app.agent2.parameters import declare_parameters
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedCompartment,
    CuratedCompound,
    CuratedReaction,
    CuratedReactionParticipant,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
BOUNDARIES_ROOT = APP_ROOT / "agent2" / "boundaries"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_boundaries_package_never_imports_forbidden_modeling_libraries():
    forbidden_roots = {
        "tellurium",
        "roadrunner",
        "libsbml",
        "antimony",
        "COPASI",
        "scipy",
        "numpy",
        "networkx",
    }
    for path in BOUNDARIES_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_boundaries_package_never_imports_agent1_package():
    for path in BOUNDARIES_ROOT.glob("*.py"):
        assert "agent1" not in _imported_roots(path)


def test_boundaries_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in BOUNDARIES_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_boundaries_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in BOUNDARIES_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_boundaries_package_never_imports_random_module():
    forbidden_roots = {"random", "secrets", "uuid"}
    for path in BOUNDARIES_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_boundaries_package_defines_no_module_or_antimony_or_boundary_creation_logic():
    forbidden_substrings = (
        "ModuleSpecification(",
        "ModuleDecomposition(",
        "ModuleBoundaryInterface(",
        "ModuleAntimonyArtifact(",
        "FullAntimonyArtifact(",
        "ModelSpecification(",
        "antimony",
        "tellurium",
        "roadrunner",
    )
    for path in BOUNDARIES_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_boundaries_package_never_invokes_simulation_fitting_or_later_agents():
    """No call-site usage of simulation/fitting/validation/critique/later-agent behavior.

    Deliberately checks for actual invocation patterns, not the bare
    words -- this package's own docstrings legitimately say things like
    "no simulation" or "Agent 3's job" to document what it does *not* do.
    """
    forbidden_substrings = (
        "curve_fit(",
        "least_squares(",
        "roadrunner.",
        "te.load",
        "app.agent1",
        "app.agent3",
        "app.agent4",
        "app.agent5",
        "scipy.optimize",
        "steady_state(",
        "solve_ivp(",
    )
    for path in BOUNDARIES_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_boundaries_types_never_declare_forbidden_fields():
    """Checks actual dataclass field declarations (`name: type`), not prose -- this
    package's own docstrings legitimately say things like "never a probability" to
    document what a field is *not*, and that must not trip this check."""
    forbidden_field_declarations = (
        "module_id:",
        "cut_set:",
        "partition:",
        "antimony_text:",
        "probability:",
        "confidence_score:",
    )
    source = (BOUNDARIES_ROOT / "types.py").read_text(encoding="utf-8")
    for forbidden in forbidden_field_declarations:
        assert forbidden not in source, f"types.py contains forbidden field {forbidden!r}"


def test_no_module_or_antimony_artifacts_from_a_real_run():
    """Structural check backed by an actual execution."""
    handoff = Agent1CuratedKnowledgeViewContract(
        contract_version="1.2",
        compartments=(CuratedCompartment(id="cyto", name="cytosol"),),
        compounds=(
            CuratedCompound(id="a", name="A"),
            CuratedCompound(id="b", name="B"),
        ),
        reactions=(CuratedReaction(id="r1", name="reaction 1"),),
        reaction_participants=(
            CuratedReactionParticipant(
                reaction_id="r1",
                compound_id="a",
                role="REACTANT",
                stoichiometry=Decimal("1"),
                compartment_id="cyto",
            ),
            CuratedReactionParticipant(
                reaction_id="r1",
                compound_id="b",
                role="PRODUCT",
                stoichiometry=Decimal("1"),
                compartment_id="cyto",
            ),
        ),
    )
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    for assessment in boundaries.assessments:
        assert not hasattr(assessment, "module_id")
        field_names = {f.name for f in dataclasses.fields(type(assessment))}
        assert "module_id" not in field_names
        assert "cut_set" not in field_names
