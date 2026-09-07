"""Agent 2 — Antimony Builder.

Consumes curated biochemical knowledge produced by Agent 1 (a separate
repository, ``agent1-biochemical-curator``) and transforms it into valid
Antimony model specifications. See ``docs/01_agent2_architecture.md`` for
the full architecture and ``docs/02_agent1_handoff_contract.md`` for the
Agent 1 handoff contract.

Increment 1 (this repository seed) defines only the immutable domain
contracts (``app.agent2.types``) and version markers
(``app.agent2.version``). No network assembly, kinetic-law assignment,
boundary heuristic, module decomposition, or Antimony generation is
implemented yet -- there is no service module to import.
"""

from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    BoundaryAssessment,
    BoundaryLikelihood,
    CuratedClaim,
    CuratedCompartment,
    CuratedCompound,
    CuratedConfidenceSummary,
    CuratedEvidence,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    CuratedRegulatoryInteraction,
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

__all__ = [
    "AGENT1_HANDOFF_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "BOUNDARY_POLICY_VERSION",
    "Agent1CuratedKnowledgeViewContract",
    "BoundaryAssessment",
    "BoundaryLikelihood",
    "CuratedClaim",
    "CuratedCompartment",
    "CuratedCompound",
    "CuratedConfidenceSummary",
    "CuratedEvidence",
    "CuratedReaction",
    "CuratedReactionEnzymeAssociation",
    "CuratedReactionParticipant",
    "CuratedRegulatoryInteraction",
    "ModelSpecification",
    "ModuleBoundaryInterface",
    "ModuleDecomposition",
    "ModuleSpecification",
    "ParameterSource",
]
