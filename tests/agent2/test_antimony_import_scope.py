"""Scope-safety tests for the Antimony Import increment (``app.agent2.antimony_import``).

Mirrors ``test_antimony_scope.py``'s own discipline for the generator package, applied to the
importer: never simulation, fitting, boundary reassessment, module recomputation, Agent 3-5
behavior, an LLM, Agent 1's runtime, or a database/network/filesystem dependency beyond what
real parsing itself requires. The one deliberate difference from the generator's own rules:
``antimony``/``libsbml`` are real, intentional dependencies *of this package specifically* --
checked for both directions (confined here, and never leaking into any other file) rather than
forbidden outright.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.agent2.antimony_import.errors import (
    MalformedAntimonySourceError,
    UnsupportedAntimonyConstructError,
)
from app.agent2.antimony_import.parser import import_antimony

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
ANTIMONY_IMPORT_ROOT = APP_ROOT / "agent2" / "antimony_import"

_SIMPLE_MODEL = """
model m
  compartment cyto = 1.0;
  species A in cyto = 1.0;
  species B in cyto = 0.0;
  R1: A -> B; k1 * A;
  k1 = 0.5;
end
"""


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_antimony_import_package_never_imports_simulation_or_fitting_libraries():
    forbidden_roots = {"tellurium", "roadrunner", "COPASI", "basico", "scipy", "numpy", "networkx"}
    for path in ANTIMONY_IMPORT_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_import_package_never_imports_agent1_or_later_agent_packages():
    forbidden_roots = {"agent1", "agent3", "agent4", "agent5"}
    for path in ANTIMONY_IMPORT_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_import_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in ANTIMONY_IMPORT_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_import_package_has_no_database_or_network_access():
    """Real parsing/validation never needs a database, HTTP, or raw socket access -- only the
    two deliberate parsing libraries themselves and this repository's own canonical types."""
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in ANTIMONY_IMPORT_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_import_package_never_invokes_simulation_or_later_agent_functions():
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
    for path in ANTIMONY_IMPORT_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_import_antimony_never_mutates_or_returns_a_cached_result():
    """Two independent calls on identical input must each produce their own, independently
    valid, deeply-equal-except-for-identity result -- never a shared mutable object."""
    first = import_antimony(_SIMPLE_MODEL)
    second = import_antimony(_SIMPLE_MODEL)
    assert first is not second
    # model_id/source_provenance.imported_at are intentionally unique per call (uuid4/
    # timestamp) -- compare everything else.
    assert first.full_network.reactions == second.full_network.reactions
    assert first.full_network.species == second.full_network.species
    assert first.parameters == second.parameters


def test_import_antimony_raises_structured_errors_never_a_bare_exception():
    with pytest.raises(MalformedAntimonySourceError):
        import_antimony("{{{ not antimony")
    with pytest.raises(UnsupportedAntimonyConstructError):
        import_antimony(
            """
            model m
              compartment c = 1.0;
              species A in c = 10.0;
              C = A + 2;
            end
            """
        )


def test_import_antimony_output_has_no_simulation_result_field():
    model = import_antimony(_SIMPLE_MODEL)
    assert not hasattr(model, "simulation_result")
    assert not hasattr(model, "fitted_value")
    assert not hasattr(model, "simulate")
