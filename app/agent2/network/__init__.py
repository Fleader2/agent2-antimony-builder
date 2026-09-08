"""Whole-Network Assembly (Increment 2).

The canonical implementation of mapping an
``Agent1CuratedKnowledgeViewContract`` onto a ``FullNetwork``. See
``docs/05_whole_network_assembly.md`` for the full architecture and
``app.agent2.network.assembler`` for the one public entry point,
``assemble_full_network``.

This package produces exactly one type, ``app.agent2.types.FullNetwork``.
It never produces a ``ModelSpecification``, a ``BoundaryAssessment``, a
``ModuleSpecification``, Antimony, SBML, a simulation result, or a
validation report -- kinetic-law assignment, parameter declaration,
boundary assessment, module decomposition, and Antimony generation all
remain later increments, out of scope here.
"""

from app.agent2.network.assembler import assemble_full_network
from app.agent2.network.errors import (
    DanglingReferenceError,
    DuplicateCuratedIdentifierError,
    MissingCompartmentReferenceError,
    NetworkAssemblyError,
    UnknownParticipantRoleError,
)

__all__ = [
    "DanglingReferenceError",
    "DuplicateCuratedIdentifierError",
    "MissingCompartmentReferenceError",
    "NetworkAssemblyError",
    "UnknownParticipantRoleError",
    "assemble_full_network",
]
