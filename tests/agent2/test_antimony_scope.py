"""Scope-safety tests for Antimony Generation (Increment 9).

Confirms ``app.agent2.antimony`` never reaches for simulation, parameter
fitting/optimization, boundary reassessment, module recomputation, Agent
3 validation, Agent 4/5 behavior, an LLM, Agent 1's runtime, or a
Tellurium/RoadRunner/libSBML/COPASI/antimony runtime dependency -- all
explicit non-goals of this increment (see
``docs/12_antimony_generation.md`` §29).
"""

from __future__ import annotations

import ast
import copy
import dataclasses
from decimal import Decimal
from pathlib import Path

from app.agent2.antimony import generate_antimony
from app.agent2.boundaries import assess_boundaries
from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.model_specification import assemble_model_specification
from app.agent2.modules import decompose_network
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
ANTIMONY_ROOT = APP_ROOT / "agent2" / "antimony"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _real_model():
    handoff = Agent1CuratedKnowledgeViewContract(
        contract_version="1.2",
        compartments=(CuratedCompartment(id="cyto", name="cytosol"),),
        compounds=(CuratedCompound(id="a", name="A"), CuratedCompound(id="b", name="B")),
        reactions=(CuratedReaction(id="r1", name="reaction 1", reversible=False),),
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
        reaction_enzyme_associations=(
            CuratedReactionEnzymeAssociation(
                reaction_id="r1", protein_id="p1", relationship="CATALYZES"
            ),
        ),
    )
    network = assemble_full_network(handoff)
    characterization = characterize_full_network(network)
    assignments = assign_kinetic_laws(characterization, network)
    parameters = declare_parameters(assignments, network)
    boundaries = assess_boundaries(network, characterization, assignments, parameters)
    modules = decompose_network(network, assignments, parameters, boundaries)
    return assemble_model_specification(network, assignments, parameters, boundaries, modules)


def test_antimony_package_never_imports_forbidden_runtime_libraries():
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
    for path in ANTIMONY_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_package_never_imports_agent1_package():
    for path in ANTIMONY_ROOT.glob("*.py"):
        assert "agent1" not in _imported_roots(path)


def test_antimony_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in ANTIMONY_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in ANTIMONY_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_package_never_imports_random_or_uuid():
    forbidden_roots = {"random", "secrets", "uuid"}
    for path in ANTIMONY_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_antimony_package_never_uses_python_hash_builtin():
    """Step 6-7: no Python ``hash()`` for identifier generation -- checked as an actual AST
    call node, not a bare-word docstring/comment mention (this package's own docstrings
    legitimately say "no Python hash()" to document what was deliberately avoided)."""
    for path in ANTIMONY_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "hash", f"{path} calls hash()"


def test_antimony_package_never_invokes_simulation_fitting_or_later_agents():
    """Checks actual invocation/definition patterns, not the bare words -- this package's own
    docstrings legitimately say things like "no simulation" or "never recomputes" to document
    what it does *not* do."""
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
        "assess_boundaries(",
        "decompose_network(",
        "assign_kinetic_laws(",
        "declare_parameters(",
        "assemble_full_network(",
        "assemble_model_specification(",
    )
    for path in ANTIMONY_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_antimony_package_never_declares_a_numeric_score_field():
    forbidden_field_declarations = ("probability:", "confidence_score:", "score:", "weight:")
    for path in ANTIMONY_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_field_declarations:
            assert forbidden not in source, f"{path} contains forbidden field {forbidden!r}"


def test_generate_antimony_never_mutates_model_specification():
    model = _real_model()
    before = copy.deepcopy(model)
    generate_antimony(model)
    assert model == before


def test_generate_antimony_never_recomputes_upstream_decisions():
    """The output package's boundary_assessments/module_decomposition/model_specification
    must be exactly the input model's own data -- never independently re-derived."""
    model = _real_model()
    package = generate_antimony(model)
    assert package.model_specification is model
    assert package.boundary_assessments == model.boundary_assessments
    assert package.module_decomposition == model.module_decomposition


def test_generate_antimony_output_has_no_simulation_result_fields():
    model = _real_model()
    package = generate_antimony(model)
    field_names = {f.name for f in dataclasses.fields(type(package.full_antimony))}
    assert "simulation_result" not in field_names
    assert "fitted_value" not in field_names
    assert not hasattr(package.full_antimony, "simulate")
