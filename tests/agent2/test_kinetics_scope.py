"""Scope-safety tests for Kinetic-Law Assignment (Increment 4).

Confirms ``app.agent2.kinetics`` never reaches for parameter declaration/
initialization, boundary assessment, module decomposition, Antimony
generation, simulation, an LLM, or Agent 1's runtime -- all of which are
explicit non-goals of this increment (see
``docs/07_kinetic_law_assignment.md`` §28), and structurally verifies no
``ParameterSpecification`` is ever constructed or numeric value selected
(§28's own "confirm no ParameterSpecification generation" requirement).
"""

from __future__ import annotations

import ast
import dataclasses
from decimal import Decimal
from pathlib import Path

from app.agent2.characterization import characterize_full_network
from app.agent2.kinetics import assign_kinetic_laws
from app.agent2.network import assemble_full_network
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
KINETICS_ROOT = APP_ROOT / "agent2" / "kinetics"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_kinetics_package_never_imports_forbidden_modeling_libraries():
    forbidden_roots = {
        "tellurium",
        "roadrunner",
        "libsbml",
        "antimony",
        "COPASI",
        "scipy",
        "numpy",
    }
    for path in KINETICS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_kinetics_package_never_imports_agent1_package():
    for path in KINETICS_ROOT.glob("*.py"):
        assert "agent1" not in _imported_roots(path)


def test_kinetics_package_never_imports_llm_or_ai_client_libraries():
    forbidden_roots = {"anthropic", "openai", "langchain", "transformers"}
    for path in KINETICS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_kinetics_package_has_no_database_or_filesystem_or_network_access():
    forbidden_roots = {"sqlalchemy", "psycopg", "httpx", "requests", "socket", "urllib"}
    for path in KINETICS_ROOT.glob("*.py"):
        imported = _imported_roots(path)
        assert not (imported & forbidden_roots), f"{path} imports {imported & forbidden_roots}"


def test_kinetics_package_defines_no_parameter_or_boundary_or_module_logic():
    forbidden_substrings = (
        "ParameterSpecification(",
        "ParameterSource.DEFAULT",
        "ParameterSource.PLACEHOLDER",
        "ParameterSource.CURATED",
        "ParameterSource.CALIBRATED",
        "ParameterSource.LITERATURE_DERIVED",
        "BoundaryAssessment(",
        "BoundaryLikelihood(",
        "ModuleSpecification(",
        "ModuleDecomposition(",
        "ModuleBoundaryInterface(",
        "FullAntimonyArtifact(",
        "ModuleAntimonyArtifact(",
        "KineticLawSpecification(",
        "ModelSpecification(",
        "antimony",
        "tellurium",
        "roadrunner",
    )
    for path in KINETICS_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_kinetics_package_never_invokes_simulation_fitting_or_later_agents():
    """No call-site usage of simulation/fitting/later-agent behavior.

    Deliberately checks for actual invocation patterns, not the bare
    words -- this package's own docstrings legitimately say things like
    "no simulation" to document what it does *not* do.
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
    for path in KINETICS_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_substrings:
            assert forbidden not in source, f"{path} contains forbidden text {forbidden!r}"


def test_kinetics_types_never_declare_forbidden_fields():
    forbidden_field_names = (
        "parameter_value",
        "initial_value",
        "boundary_likelihood",
        "module_id",
        "antimony_text",
        "parameter_ids",
    )
    source = (KINETICS_ROOT / "types.py").read_text(encoding="utf-8")
    for forbidden in forbidden_field_names:
        assert forbidden not in source, f"types.py contains forbidden field name {forbidden!r}"


def test_no_parameter_specification_instances_created_by_a_real_run():
    """Structural check backed by an actual execution: no ``ParameterSpecification``
    is ever constructed while assigning kinetic laws for a realistic network."""
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
    assignment_set = assign_kinetic_laws(characterization, network)
    for assignment in assignment_set.assignments:
        assert not hasattr(assignment, "parameter_ids")
        assert not hasattr(assignment, "parameter_values")
    assert dataclasses.fields(type(assignment_set.assignments[0]))
    field_names = {f.name for f in dataclasses.fields(type(assignment_set.assignments[0]))}
    assert "parameter_ids" not in field_names
    assert "parameter_values" not in field_names
