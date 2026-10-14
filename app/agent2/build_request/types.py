"""Scoped-Build Support increment: the Workbench -> Agent 2 ``ModelBuildRequest`` contract.

This is Agent 2's own, local, decoupled representation of a Workbench
``ModelBuildRequest`` (``mechanistic-modeling-workbench/app/models
/model_build_request.py``) -- transcribed, never imported, exactly like
every other cross-repository contract in this project's family
(``app.agent2.types.Agent1CuratedKnowledgeViewContract`` is Agent 2's
identical, pre-existing precedent for Agent 1's own handoff).

Deliberately named ``ModelBuildRequest`` here, matching the Workbench's
own name exactly -- the Workbench chose that name specifically to avoid
colliding with Agent 2's own, unrelated, pre-existing ``ModelSpecification``
(the complete assembled executable model, ``app.agent2.types
.ModelSpecification``). Reusing the Workbench's own name on this side
keeps one contract, one name, across the boundary; it is never confused
with ``ModelSpecification`` because the two name completely different
things and this module never imports ``app.agent2.types.ModelSpecification``.

**What this contract is for.** It carries the user's own build *intent*
(start/end species, seed/required/excluded reactions, important genes/
proteins, compartments to include, pathway scope, PTM/enzyme-state
references, and free-text assumptions) from the Workbench, through the
integration harness, to Agent 2's canonical pipeline
(``app.agent2.pipeline.run_agent2_pipeline``). It never duplicates Agent
1's own curated-knowledge contract (``Agent1CuratedKnowledgeViewContract``)
-- every entity reference here is a plain, already-resolved
``(agent1_entity_type, agent1_entity_id)`` pair or an unresolved
``raw_identifier``, exactly as the Workbench's own ``ModelBuildRequest``
child tables store them. Agent 2 never invents a biological mapping for a
``raw_identifier`` it cannot resolve -- see ``app.agent2.build_request.scope``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: Bumped only when a field in this module's own dataclasses changes --
#: independent of ``AGENT2_CONTRACT_VERSION``/``AGENT2_DOWNSTREAM_CONTRACT_VERSION``
#: (see ``app.agent2.version``), and independent of the Workbench's own
#: ``app.contracts.harness.CONTRACT_VERSION``/``WORKBENCH_HARNESS_CONTRACT_VERSION``
#: (a different boundary entirely -- that one governs the Workbench<->harness
#: invocation/result envelope, never this build-request artifact's own content).
AGENT2_BUILD_REQUEST_CONTRACT_VERSION = "agent2-build-request-v1"


class BuildRequestSpeciesRole(StrEnum):
    """Mirrors the Workbench's own ``ModelBuildRequestSpeciesRole`` exactly."""

    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    BOUNDARY = "BOUNDARY"
    SEED = "SEED"


class BuildRequestReactionRole(StrEnum):
    """Mirrors the Workbench's own ``ModelBuildRequestReactionRole`` exactly."""

    SEED = "SEED"
    REQUIRED = "REQUIRED"
    EXCLUDED = "EXCLUDED"


class BuildRequestGeneProteinRole(StrEnum):
    """Mirrors the Workbench's own ``ModelBuildRequestGeneProteinRole`` exactly."""

    SEED = "SEED"
    IMPORTANT = "IMPORTANT"


class BuildRequestPathwayRole(StrEnum):
    """Mirrors the Workbench's own ``ModelBuildRequestPathwayRole`` exactly."""

    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"


@dataclass(frozen=True, slots=True)
class EntityReference:
    """One Agent-1-resolved (or raw, unresolved) entity reference.

    Mirrors one row of one Workbench ``ModelBuildRequest`` child table,
    flattened for transport. ``agent1_entity_id`` is always Agent 1's own
    primary-key string (never a Workbench-internal id) -- the same
    convention ``app.agent2.types.CuratedReaction.id`` etc. already use
    for every Agent-1-sourced identifier. ``raw_identifier`` is preserved
    verbatim whenever Agent 1 resolution has not (yet) happened -- never
    discarded, and never guessed into a resolved id by anything in this
    module (``docs/20_scoped_build_support.md``).
    """

    role: str | None = None
    agent1_entity_type: str | None = None
    agent1_entity_id: str | None = None
    raw_identifier: str | None = None
    localization_entity_type: str | None = None
    localization_entity_id: str | None = None
    localization_raw_identifier: str | None = None

    # ``role`` is required (one of ``BuildRequestSpeciesRole``/``BuildRequestReactionRole``/
    # ``BuildRequestGeneProteinRole``) for a ``species``/``reactions``/``gene_proteins`` entry,
    # and always ``None`` for a ``compartments``/``regulatory_interactions``/``enzyme_states``
    # entry -- mirroring the Workbench's own ``ModelBuildRequestCompartment``/
    # ``ModelBuildRequestRegulatoryInteraction``/``ModelBuildRequestEnzymeState`` tables, none
    # of which has a ``role`` column at all.
    #
    # ``localization_*`` mirrors the Workbench's own
    # ``ModelBuildRequestGeneProtein.localization_entity_id``/``localization_raw_identifier``
    # -- a subcellular localization constraint on this one gene/protein reference, distinct
    # from "compartments to include" (``compartments``/``ModelBuildRequestCompartment``).
    # Always ``None`` for a ``species``/``reactions``/``compartments``/
    # ``regulatory_interactions``/``enzyme_states`` entry, none of which has this column.


@dataclass(frozen=True, slots=True)
class PathwayReference:
    """One include/exclude pathway-scope reference.

    No ``Pathway`` entity exists anywhere in this project's family
    (confirmed by the architecture audit for both Agent 1 and the
    Workbench) -- this carries the source's own bare pathway identifier/
    name directly, exactly like the Workbench's own
    ``ModelBuildRequestPathway`` row.
    """

    role: str
    external_pathway_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ModelBuildRequest:
    """What the Workbench hands to Agent 2 (via the harness) to scope one build.

    ``assumptions`` here is the flattened ``assumption`` text of every
    ``ModelBuildRequestAssumption`` row -- free-text, never machine-
    interpreted by Agent 2 (same disclosed-text-only policy as every other
    free-text assumption field in ``app.agent2.types``).
    """

    contract_version: str
    model_build_request_id: str
    species: tuple[EntityReference, ...] = ()
    reactions: tuple[EntityReference, ...] = ()
    gene_proteins: tuple[EntityReference, ...] = ()
    compartments: tuple[EntityReference, ...] = ()
    regulatory_interactions: tuple[EntityReference, ...] = ()
    enzyme_states: tuple[EntityReference, ...] = ()
    pathways: tuple[PathwayReference, ...] = ()
    assumptions: tuple[str, ...] = field(default_factory=tuple)


def _entity_reference_from_dict(data: dict) -> EntityReference:
    return EntityReference(
        role=data.get("role"),
        agent1_entity_type=data.get("agent1_entity_type"),
        agent1_entity_id=data.get("agent1_entity_id"),
        raw_identifier=data.get("raw_identifier"),
        localization_entity_type=data.get("localization_entity_type"),
        localization_entity_id=data.get("localization_entity_id"),
        localization_raw_identifier=data.get("localization_raw_identifier"),
    )


def _pathway_reference_from_dict(data: dict) -> PathwayReference:
    return PathwayReference(
        role=data["role"],
        external_pathway_id=data.get("external_pathway_id"),
        name=data.get("name"),
    )


def build_request_from_dict(data: dict) -> ModelBuildRequest:
    """Parse a plain dict (as read from the artifact the Workbench/harness supplies) into a
    ``ModelBuildRequest``.

    Raises ``app.agent2.build_request.errors.BuildRequestContractVersionError`` if
    ``contract_version`` does not match ``AGENT2_BUILD_REQUEST_CONTRACT_VERSION`` exactly --
    never silently coerced, the same enforcement policy as every other inter-repository
    contract in this project's family. Raises ``KeyError``/``TypeError`` for a malformed
    artifact, exactly like every sibling ``*_from_dict`` function this project already has
    (e.g. ``app.contracts.harness.result_from_dict`` in the Workbench/harness repositories).
    """
    from app.agent2.build_request.errors import BuildRequestContractVersionError

    contract_version = data["contract_version"]
    if contract_version != AGENT2_BUILD_REQUEST_CONTRACT_VERSION:
        raise BuildRequestContractVersionError(
            f"expected contract_version {AGENT2_BUILD_REQUEST_CONTRACT_VERSION!r}, "
            f"got {contract_version!r}"
        )
    return ModelBuildRequest(
        contract_version=contract_version,
        model_build_request_id=data["model_build_request_id"],
        species=tuple(_entity_reference_from_dict(d) for d in data.get("species", ())),
        reactions=tuple(_entity_reference_from_dict(d) for d in data.get("reactions", ())),
        gene_proteins=tuple(_entity_reference_from_dict(d) for d in data.get("gene_proteins", ())),
        compartments=tuple(_entity_reference_from_dict(d) for d in data.get("compartments", ())),
        regulatory_interactions=tuple(
            _entity_reference_from_dict(d) for d in data.get("regulatory_interactions", ())
        ),
        enzyme_states=tuple(_entity_reference_from_dict(d) for d in data.get("enzyme_states", ())),
        pathways=tuple(_pathway_reference_from_dict(d) for d in data.get("pathways", ())),
        assumptions=tuple(data.get("assumptions", ())),
    )


__all__ = [
    "AGENT2_BUILD_REQUEST_CONTRACT_VERSION",
    "BuildRequestGeneProteinRole",
    "BuildRequestPathwayRole",
    "BuildRequestReactionRole",
    "BuildRequestSpeciesRole",
    "EntityReference",
    "ModelBuildRequest",
    "PathwayReference",
    "build_request_from_dict",
]
