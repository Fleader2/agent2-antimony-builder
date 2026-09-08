"""Scope-safety tests for Reaction and Enzyme-State Characterization (Increment 3).

Confirms ``app.agent2.characterization`` never reaches for kinetic-law
assignment, parameter declaration, boundary assessment, module
decomposition, Antimony generation, simulation, an LLM, or Agent 1's
runtime -- all of which are explicit non-goals of this increment (see
``docs/06_reaction_enzyme_state_characterization.md`` §26).
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
CHARACTERIZATION_ROOT = APP_ROOT / "agent2" / "characterization"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_characterization_package_never_imports_forbidden_modeling_libraries():
    forbidden_roots = {
        "tellurium",
        "roadrunner",
        "libsbml",
        "antimony",
        "COPASI",
        "scipy",
        "numpy",
    }
    for path in CHARACTERIZATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_characterization_package_never_imports_agent1_package():
    for path in CHARACTERIZATION_ROOT.glob("*.py"):
        assert "agent1" not in _imported_roots(path)


def test_characterization_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in CHARACTERIZATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_characterization_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in CHARACTERIZATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_characterization_package_defines_no_kinetic_law_or_parameter_or_boundary_or_module_logic():
    forbidden_substrings = (
        "KineticLawSpecification(",
        "ParameterSpecification(",
        "BoundaryAssessment(",
        "BoundaryLikelihood(",
        "ModuleSpecification(",
        "ModuleDecomposition(",
        "ModuleBoundaryInterface(",
        "FullAntimonyArtifact(",
        "ModuleAntimonyArtifact(",
        "KineticLawType.",
        "ParameterSource.",
        "antimony",
        "tellurium",
        "roadrunner",
    )
    for path in CHARACTERIZATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_characterization_package_never_invokes_simulation_fitting_or_later_agents():
    """No call-site usage of simulation/fitting/later-agent behavior.

    Deliberately checks for actual invocation patterns, not the bare words
    -- this package's own docstrings legitimately say things like "no
    simulation" to document what it does *not* do, and that disclaimer
    text must not trip this check.
    """
    forbidden_substrings = (
        "curve_fit(",
        "least_squares(",
        "roadrunner.",
        "te.load",
        "app.agent3",
        "app.agent4",
        "app.agent5",
    )
    for path in CHARACTERIZATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_characterization_types_never_declare_forbidden_fields():
    forbidden_field_names = (
        "kinetic_law",
        "parameter_id",
        "parameter_value",
        "boundary_likelihood",
        "module_id",
        "antimony_text",
    )
    source = (CHARACTERIZATION_ROOT / "types.py").read_text(encoding="utf-8")
    for forbidden in forbidden_field_names:
        assert forbidden not in source, f"types.py contains forbidden field name {forbidden!r}"
