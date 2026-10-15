"""Candidate Modularization Search.

Generates plausible alternative modularizations from a seed ``ModelModularization`` via
deterministic proposal operators, evaluated entirely through the existing, unchanged Module
Boundary Evaluation Framework / Weight-Space Exploration framework
(``app.agent2.module_evaluation``/``app.agent2.weight_space_exploration``). Never mutates the
canonical ``ModelSpecification``; never calls Agent 3/Agent 4 automatically (calibration
evidence, if any, must already have been obtained through the existing
``app.agent2.module_calibration``/Harness orchestration layer). See ``docs/
33_candidate_modularization_search.md`` for the full design.

Public API: ``search_candidate_modularizations`` (``search``); every type (``types``);
content-addressed identity helpers (``identity``); hard-constraint checks (``constraints``);
the six proposal operators (``operators``); bundle assembly/attachment helpers (``assembly``);
``ModularizationSearchError``, ``ModularizationSearchReferenceError`` (``errors``).
"""

from __future__ import annotations

from app.agent2.modularization_search.assembly import (
    attach_bundle,
    attach_many,
    extract_bundle,
    restamp_modularization_id,
)
from app.agent2.modularization_search.errors import (
    ModularizationSearchError,
    ModularizationSearchReferenceError,
)
from app.agent2.modularization_search.identity import (
    candidate_signature,
    derive_module_id,
    module_content_key,
)
from app.agent2.modularization_search.operators import (
    propose_add_boundary,
    propose_merge_modules,
    propose_move_reaction,
    propose_remove_boundary,
    propose_split_module,
    propose_vary_module_count,
)
from app.agent2.modularization_search.search import search_candidate_modularizations
from app.agent2.modularization_search.types import (
    BoundaryFixedState,
    CandidateLineage,
    CandidateModularizationBundle,
    CandidateModularizationSearchResult,
    FixedBoundary,
    ProposalOperation,
    RejectedCandidate,
    SearchConstraints,
    SearchPolicy,
)

__all__ = [
    "BoundaryFixedState",
    "CandidateLineage",
    "CandidateModularizationBundle",
    "CandidateModularizationSearchResult",
    "FixedBoundary",
    "ModularizationSearchError",
    "ModularizationSearchReferenceError",
    "ProposalOperation",
    "RejectedCandidate",
    "SearchConstraints",
    "SearchPolicy",
    "attach_bundle",
    "attach_many",
    "candidate_signature",
    "derive_module_id",
    "extract_bundle",
    "module_content_key",
    "propose_add_boundary",
    "propose_merge_modules",
    "propose_move_reaction",
    "propose_remove_boundary",
    "propose_split_module",
    "propose_vary_module_count",
    "restamp_modularization_id",
    "search_candidate_modularizations",
]
