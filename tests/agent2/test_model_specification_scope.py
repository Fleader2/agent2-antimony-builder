"""Scope-safety tests for ModelSpecification Assembly (Increment 8).

Confirms ``app.agent2.model_specification`` never reaches for Antimony
generation, simulation, parameter fitting/optimization, boundary
reassessment, module recomputation, Agent 3 validation, Agent 5 critique,
an LLM, or Agent 1's runtime -- all of which are explicit non-goals of
this increment (see ``docs/11_model_specification_assembly.md`` §22).
"""

from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

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
    CuratedReactionParticipant,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
MODEL_SPECIFICATION_ROOT = APP_ROOT / "agent2" / "model_specification"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_model_specification_package_never_imports_forbidden_modeling_libraries():
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
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_model_specification_package_never_imports_agent1_package():
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        assert "agent1" not in _imported_roots(path)


def test_model_specification_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_model_specification_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_model_specification_package_never_imports_random_module():
    forbidden_roots = {"random", "secrets", "uuid"}
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_model_specification_package_defines_no_antimony_generation_logic():
    forbidden_substrings = (
        "ModuleAntimonyArtifact(",
        "FullAntimonyArtifact(",
        "antimony",
        "tellurium",
        "roadrunner",
    )
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_model_specification_package_never_invokes_simulation_fitting_or_later_agents():
    """No call-site usage of simulation/fitting/validation/critique/later-agent behavior, nor
    of boundary reassessment or module recomputation -- this increment assembles, it never
    recomputes an upstream decision. Deliberately checks actual invocation/definition patterns,
    not the bare words -- this package's own docstrings legitimately say things like "no
    simulation" or "never recomputes" to document what it does *not* do."""
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
    )
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_model_specification_package_never_declares_a_numeric_score_field():
    """Checks actual dataclass field declarations (`name: type`), not prose. This package
    introduces no new top-level type of its own (unlike boundaries/kinetics/parameters/
    modules, it assembles into the pre-existing ``ModelSpecification`` rather than defining a
    new collection type), so every ``*.py`` file is scanned rather than a single ``types.py``."""
    forbidden_field_declarations = (
        "probability:",
        "confidence_score:",
        "score:",
        "weight:",
    )
    for path in MODEL_SPECIFICATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_field_declarations:
            assert forbidden not in source, f"{path} contains forbidden field {forbidden!r}"


def test_no_antimony_or_simulation_artifacts_from_a_real_run():
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
    modules = decompose_network(network, assignments, parameters, boundaries)
    model = assemble_model_specification(network, assignments, parameters, boundaries, modules)
    field_names = {f.name for f in dataclasses.fields(type(model))}
    assert "antimony_text" not in field_names
    assert "probability" not in field_names
    assert not hasattr(model, "antimony_text")


def test_boundaries_and_modules_are_never_recomputed_from_a_real_run():
    """The assembled ModelSpecification's boundary_assessments/module_decomposition must be
    exactly the same objects supplied as input -- never independently re-derived."""
    handoff = Agent1CuratedKnowledgeViewContract(
        contract_version="1.2",
        compartments=(CuratedCompartment(id="cyto", name="cytosol"),),
        compounds=(CuratedCompound(id="a", name="A"), CuratedCompound(id="b", name="B")),
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
    modules = decompose_network(network, assignments, parameters, boundaries)
    model = assemble_model_specification(network, assignments, parameters, boundaries, modules)
    assert model.boundary_assessments == boundaries.assessments
    assert model.module_decomposition == modules.decompositions[0]
    assert model.module_specifications == modules.module_specifications
