"""Module Boundary Evaluation Framework: the four currently-implemented criteria.

Each function here answers exactly one, independently-inspectable evidence question, reading
only ``FullNetwork``/the caller's own already-filtered ``ModuleMembership``/``ModulePort``
rows for one modularization -- never the whole ``ModelSpecification``, never any other
criterion's own result, and never anything origin-specific (GENERATED vs IMPORTED). Pure and
deterministic: no database, no filesystem, no network access, no simulation, no fitting, no
random numbers, no mutation of any input.

**Never fabricates a score.** Every function returns a ``CriterionResult`` with
``available=False`` (and ``raw_score=None``) whenever the evidence it needs does not exist
for the modularization it was asked to score -- see each function's own docstring for exactly
when that happens.

Every score, when available, is a ``Decimal`` in ``[0, 1]``, higher meaning "more evidence
this modularization's own boundaries are well-chosen by this one, specific, independent
criterion" -- never a claim about overall modularity (see this package's own
``types.py`` module docstring for the "mechanisms are evidence, not the target" principle).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from app.agent2.module_evaluation.types import (
    CalibrationIndependenceDetail,
    DynamicIsolationDetail,
    ModularizationCriterion,
    SensitivityCoherenceDetail,
    TopologyComponentFilter,
    TopologyFilteringPolicy,
    TopologyRole,
    TopologySeparationDetail,
)
from app.agent2.types import (
    FullNetwork,
    ModuleComponentType,
    ModuleMembership,
    ModulePort,
)

#: Topology Hub/Currency Component Filtering increment: each ``TopologyRole``'s own default
#: weight when a caller's own ``TopologyRoleOverride`` does not specify one explicitly. A
#: policy choice, disclosed here rather than hard-coded into the enum itself --
#: ``UNIVERSAL_CURRENCY``/``USER_EXCLUDED`` hard-exclude (weight 0); ``COFACTOR``/
#: ``GENERIC_ADAPTOR``/``HIGH_DEGREE_HUB`` down-weight rather than hard-exclude, since each is
#: less universally irrelevant than a currency metabolite (task instructions §1/§3).
DEFAULT_TOPOLOGY_ROLE_WEIGHT: dict[TopologyRole, Decimal] = {
    TopologyRole.NORMAL: Decimal("1"),
    TopologyRole.UNIVERSAL_CURRENCY: Decimal("0"),
    TopologyRole.COFACTOR: Decimal("0.3"),
    TopologyRole.GENERIC_ADAPTOR: Decimal("0.3"),
    TopologyRole.HIGH_DEGREE_HUB: Decimal("0.3"),
    TopologyRole.USER_EXCLUDED: Decimal("0"),
}

#: Curated, name-based default classification for the most common currency metabolites
#: (task's own named examples: ATP/ADP, protons/water, phosphate) -- matched by *exact*,
#: case-insensitive match against a species' own curated ``name`` (never a substring match,
#: so e.g. "Acetyl_CoA" is never mistaken for bare "CoA"). A real, disclosed, approximate
#: heuristic: it will not catch a non-standard spelling (e.g. "adenosine triphosphate"
#: instead of "ATP") -- an explicit ``TopologyRoleOverride`` is always the authoritative
#: fallback for exactly that case.
_UNIVERSAL_CURRENCY_NAMES: frozenset[str] = frozenset(
    {
        "atp",
        "adp",
        "amp",
        "gtp",
        "gdp",
        "gmp",
        "utp",
        "udp",
        "ump",
        "ctp",
        "cdp",
        "cmp",
        "water",
        "h2o",
        "proton",
        "h+",
        "hydron",
        "h",
        "orthophosphate",
        "phosphate",
        "pi",
        "diphosphate",
        "pyrophosphate",
        "ppi",
        "co2",
        "carbon dioxide",
        "ammonia",
        "nh3",
        "oxygen",
        "o2",
    }
)
#: Curated, name-based default classification for common redox/acyl-carrier cofactors (task's
#: own named examples: NAD/NADH, NADP/NADPH, CoA, common vitamins) -- same exact-match policy
#: as ``_UNIVERSAL_CURRENCY_NAMES`` above.
_COFACTOR_NAMES: frozenset[str] = frozenset(
    {
        "nad",
        "nad+",
        "nadh",
        "nadp",
        "nadp+",
        "nadph",
        "coa",
        "coenzyme a",
        "fad",
        "fadh",
        "fadh2",
        "thiamine",
        "thiamine diphosphate",
        "biotin",
        "pyridoxal phosphate",
        "tetrahydrofolate",
        "s-adenosylmethionine",
        "sam",
    }
)


def _curated_default_role(name: str | None) -> TopologyRole | None:
    """This species' own curated-name-based default role, or ``None`` when its name matches
    neither built-in list (falls through to ``NORMAL`` by the caller)."""
    if not name:
        return None
    normalized = name.strip().lower()
    if normalized in _UNIVERSAL_CURRENCY_NAMES:
        return TopologyRole.UNIVERSAL_CURRENCY
    if normalized in _COFACTOR_NAMES:
        return TopologyRole.COFACTOR
    return None


#: Every ``ModularizationCriterion`` with a real producer in this module today -- the task's
#: own "initial criteria" list (§2). Kept here, not in ``types.py``, since it describes
#: *behavior* (what is implemented), not the type system's own closed vocabulary.
IMPLEMENTED_CRITERIA: tuple[ModularizationCriterion, ...] = (
    ModularizationCriterion.TOPOLOGICAL_SEPARATION,
    ModularizationCriterion.BOUNDARY_SPARSITY,
    ModularizationCriterion.COMPARTMENT_COHERENCE,
    ModularizationCriterion.EC_CLASS_COHERENCE,
)


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """One criterion function's own raw result, before ``app.agent2.module_evaluation
    .evaluator`` attaches weight information -- never constructed by, or exported to, a
    caller outside this package."""

    available: bool
    raw_score: Decimal | None
    explanation: str
    warnings: tuple[str, ...] = ()
    #: Topology Hub/Currency Component Filtering increment: ``TOPOLOGICAL_SEPARATION``'s own
    #: extended report, threaded through by ``app.agent2.module_evaluation.evaluator`` onto
    #: ``ModularizationCriterionScore.detail``. Recursive Module Evaluation Orchestration
    #: increment: ``CalibrationIndependenceDetail`` (``calibration_adapter
    #: .score_calibration_independence``'s own result). Functional Modularity Criteria from
    #: Agents 3 and 4 increment: ``DynamicIsolationDetail``/``SensitivityCoherenceDetail``
    #: (``functional_adapter``'s own two results). Always ``None`` for every other criterion.
    detail: (
        TopologySeparationDetail
        | CalibrationIndependenceDetail
        | DynamicIsolationDetail
        | SensitivityCoherenceDetail
        | None
    ) = None


def _member_ids(
    memberships: tuple[ModuleMembership, ...], *, component_type: ModuleComponentType
) -> dict[str, set[str]]:
    """``{module_id: {component_id, ...}}`` for every membership of the given component type."""
    result: dict[str, set[str]] = {}
    for m in memberships:
        if m.component_type is component_type:
            result.setdefault(m.module_id, set()).add(m.component_id)
    return result


def _resolve_species_topology_role(
    species_id: str, name: str | None, policy: TopologyFilteringPolicy | None
) -> tuple[TopologyRole, Decimal, str | None]:
    """``(role, weight, source)`` for one species, for ``TOPOLOGICAL_SEPARATION`` filtering
    only. ``source`` is ``None`` for a plain, unfiltered ``NORMAL``/weight-``1`` species
    (never listed in ``TopologySeparationDetail.filters``); otherwise ``"override"`` or
    ``"curated_default"``, in that precedence order (task instructions: "use curated/
    context-defined roles first," with an explicit override always taking final precedence).
    """
    override = policy.override_for(species_id) if policy is not None else None
    if override is not None:
        weight = (
            override.weight
            if override.weight is not None
            else DEFAULT_TOPOLOGY_ROLE_WEIGHT[override.role]
        )
        return override.role, weight, "override"
    default_role = _curated_default_role(name)
    if default_role is not None:
        return default_role, DEFAULT_TOPOLOGY_ROLE_WEIGHT[default_role], "curated_default"
    return TopologyRole.NORMAL, Decimal("1"), None


def score_topological_separation(
    network: FullNetwork,
    memberships: tuple[ModuleMembership, ...],
    topology_filtering: TopologyFilteringPolicy | None = None,
) -> CriterionResult:
    """Do this modularization's own module boundaries cut few of the network's natural
    reaction-adjacency edges (two reactions sharing at least one species), relative to how
    many such edges they keep internal?

    Only reactions that are members of *some* module of this modularization are considered
    (a partially-covered modularization is never penalized for a reaction it never claimed).
    Two member reactions sharing a module (their own module-id sets intersect -- a reaction
    may legitimately belong to more than one module) are "internal"; sharing an edge but no
    common module is "cut."

    **Topology Hub/Currency Component Filtering increment.** Two scores are always both
    computed and disclosed (``TopologySeparationDetail``): ``raw_topology_score`` (every
    shared species counted equally, exactly the pre-increment behavior -- ``internal /
    (internal + cut)`` by *edge count*) and ``filtered_topology_score`` (each edge weighted by
    the *most significant* shared species connecting that reaction pair -- ``max`` over that
    pair's own shared species' resolved weights, so one genuinely pathway-specific shared
    species is never diluted by also sharing an ubiquitous cofactor; weighted sums replace
    counts). ``CriterionResult.raw_score``/``available`` (and therefore this criterion's own
    contribution to ``overall_score``) always reflect the **filtered** score (task
    instructions §4: "use the filtered score for modularization evaluation") -- the unfiltered
    baseline is preserved only in ``detail``, never silently discarded.

    A species' own role/weight is resolved, in order: an explicit
    ``TopologyFilteringPolicy`` override; this package's own curated, name-based default
    (``_curated_default_role`` -- ATP/ADP/water/protons/phosphate as ``UNIVERSAL_CURRENCY``,
    NAD(H)/NADP(H)/CoA/... as ``COFACTOR``); otherwise ``NORMAL`` (weight ``1``, unfiltered).
    Degree-based hub detection (a species connecting at least ``hub_degree_threshold`` member
    reactions) only ever adds that species' id to ``hub_candidate_species_ids`` -- it never
    changes a role or a weight by itself (task instructions §3: "must not silently exclude
    them by default").

    **Unavailable** when this modularization's own member reactions share zero adjacency
    edges at all -- there is then nothing to evaluate, never a fabricated "perfect" or "zero"
    score. The *filtered* score can also independently be unavailable (while the raw score
    remains available) when every shared species connecting this modularization's own
    reactions resolved to weight ``0`` -- the filtered numerator and denominator are both
    zero, a genuine "no real connectivity signal survived filtering" outcome, never silently
    reported as either a perfect or a zero score.
    """
    reaction_modules = _member_ids(memberships, component_type=ModuleComponentType.REACTION)
    module_ids_by_reaction: dict[str, frozenset[str]] = {}
    for module_id, reaction_ids in reaction_modules.items():
        for reaction_id in reaction_ids:
            module_ids_by_reaction.setdefault(reaction_id, set()).add(module_id)
    scoped_reaction_ids = set(module_ids_by_reaction)
    if not scoped_reaction_ids:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "No reaction is a member of any module of this modularization -- nothing to "
                "evaluate."
            ),
        )

    species_to_reactions: dict[str, set[str]] = {}
    for reaction in network.reactions:
        if reaction.reaction_id not in scoped_reaction_ids:
            continue
        for participant in reaction.participants:
            species_to_reactions.setdefault(participant.species_id, set()).add(reaction.reaction_id)

    edge_shared_species: dict[frozenset[str], set[str]] = {}
    for species_id, reaction_ids in species_to_reactions.items():
        if len(reaction_ids) < 2:
            continue
        ordered = sorted(reaction_ids)
        for i, r1 in enumerate(ordered):
            for r2 in ordered[i + 1 :]:
                edge_shared_species.setdefault(frozenset({r1, r2}), set()).add(species_id)

    if not edge_shared_species:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "This modularization's own member reactions share no species-adjacency edges "
                "with each other -- nothing to evaluate."
            ),
        )

    raw_internal = 0
    raw_cut = 0
    for edge in edge_shared_species:
        r1, r2 = tuple(edge)
        if module_ids_by_reaction[r1] & module_ids_by_reaction[r2]:
            raw_internal += 1
        else:
            raw_cut += 1
    raw_score = Decimal(raw_internal) / Decimal(raw_internal + raw_cut)

    species_by_id = {s.species_id: s for s in network.species}
    all_edge_species = {sid for shared in edge_shared_species.values() for sid in shared}
    resolved: dict[str, tuple[TopologyRole, Decimal, str | None]] = {
        sid: _resolve_species_topology_role(
            sid, species_by_id[sid].name if sid in species_by_id else None, topology_filtering
        )
        for sid in all_edge_species
    }

    hub_threshold = (
        topology_filtering.hub_degree_threshold
        if topology_filtering is not None and topology_filtering.hub_degree_threshold is not None
        else max(4, len(scoped_reaction_ids) // 3)
    )
    hub_candidate_species_ids = tuple(
        sorted(sid for sid in all_edge_species if len(species_to_reactions[sid]) >= hub_threshold)
    )

    filtered_internal = Decimal(0)
    filtered_cut = Decimal(0)
    for edge, shared in edge_shared_species.items():
        r1, r2 = tuple(edge)
        edge_weight = max(resolved[sid][1] for sid in shared)
        if module_ids_by_reaction[r1] & module_ids_by_reaction[r2]:
            filtered_internal += edge_weight
        else:
            filtered_cut += edge_weight

    filtered_total = filtered_internal + filtered_cut
    filtered_score = filtered_internal / filtered_total if filtered_total > 0 else None

    filters = tuple(
        sorted(
            (
                TopologyComponentFilter(species_id=sid, role=role, weight=weight, source=source)
                for sid, (role, weight, source) in resolved.items()
                if source is not None
            ),
            key=lambda f: f.species_id,
        )
    )

    detail = TopologySeparationDetail(
        raw_topology_score=raw_score,
        filtered_topology_score=filtered_score,
        filters=filters,
        hub_candidate_species_ids=hub_candidate_species_ids,
    )
    filtered_component_warnings = (
        (f"{len(filters)} component(s) filtered: {', '.join(f.species_id for f in filters)}.",)
        if filters
        else ()
    )

    if filtered_score is None:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "Every species connecting this modularization's own member reactions "
                "resolved to topology weight 0 (fully filtered out) -- no real connectivity "
                "signal survived filtering, even though the unfiltered raw score "
                f"({raw_score}) is available (see detail.raw_topology_score)."
            ),
            warnings=filtered_component_warnings,
            detail=detail,
        )

    return CriterionResult(
        available=True,
        raw_score=filtered_score,
        explanation=(
            f"{filtered_internal} of {filtered_total} weighted reaction-adjacency edge(s) "
            f"(raw, unweighted: {raw_internal} of {raw_internal + raw_cut}) among this "
            f"modularization's own {len(scoped_reaction_ids)} member reaction(s) stayed "
            "internal to a single module (never cut across modules)."
        ),
        warnings=filtered_component_warnings,
        detail=detail,
    )


def score_boundary_sparsity(
    memberships: tuple[ModuleMembership, ...], ports: tuple[ModulePort, ...]
) -> CriterionResult:
    """How sparse is the *explicitly declared* cross-module interface surface
    (``ModulePort``), relative to this modularization's own total species membership?

    ``score = 1 - (distinct species named by some ModulePort) / (distinct species that are
    members of some module)``. Zero declared ports is a real, legitimate ``1.0`` (perfectly
    sparse from the declared-interface perspective) -- never treated as missing evidence,
    since the absence of declared boundary crossings is itself a genuine, observed fact about
    this modularization, not an evidentiary gap. This is a deliberately different signal from
    ``TOPOLOGICAL_SEPARATION`` above: that one reads the network's own *implicit* reaction
    adjacency; this one reads only what was *explicitly declared* as crossing a boundary, so
    the two can, and often will, disagree (e.g. a modularization with excellent topological
    separation but sloppy/incomplete port declarations, or vice versa).

    **Unavailable** only when this modularization has no species membership at all (nothing
    to compute a fraction over).
    """
    species_by_module = _member_ids(memberships, component_type=ModuleComponentType.SPECIES)
    all_species: set[str] = set()
    for species_ids in species_by_module.values():
        all_species |= species_ids
    if not all_species:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation="No species is a member of any module of this modularization.",
        )

    cross_module_species = {p.species_id for p in ports} & all_species
    score = Decimal(1) - (Decimal(len(cross_module_species)) / Decimal(len(all_species)))
    return CriterionResult(
        available=True,
        raw_score=score,
        explanation=(
            f"{len(cross_module_species)} of {len(all_species)} member species have an "
            "explicitly declared ModulePort crossing a module boundary."
        ),
    )


def score_compartment_coherence(
    network: FullNetwork, memberships: tuple[ModuleMembership, ...]
) -> CriterionResult:
    """Does each module's own species membership concentrate in one compartment, or span
    many?

    Per module: ``module_score = (species in that module's own modal/most-common compartment)
    / (total species in that module)``. Overall score is the unweighted mean of every module's
    own score. A module spanning a transport reaction legitimately scores lower -- this is
    expected, disclosed evidence, never an error (mirrors
    ``docs/10_module_decomposition.md`` §17's own identical, pre-existing observation about
    compartment-spanning modules).

    **Unavailable** when this modularization has zero modules with any species membership at
    all.
    """
    species_by_id = {s.species_id: s for s in network.species}
    species_by_module = _member_ids(memberships, component_type=ModuleComponentType.SPECIES)

    module_scores: list[Decimal] = []
    skipped_unresolved = 0
    for _module_id, species_ids in species_by_module.items():
        compartments = [
            species_by_id[sid].compartment_id for sid in species_ids if sid in species_by_id
        ]
        skipped_unresolved += len(species_ids) - len(compartments)
        if not compartments:
            continue
        modal_count = Counter(compartments).most_common(1)[0][1]
        module_scores.append(Decimal(modal_count) / Decimal(len(compartments)))

    if not module_scores:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "No module of this modularization has any species membership resolvable "
                "against the full network."
            ),
        )

    score = sum(module_scores, Decimal(0)) / Decimal(len(module_scores))
    warnings = (
        (f"{skipped_unresolved} membership reference(s) did not resolve to a real species.",)
        if skipped_unresolved
        else ()
    )
    return CriterionResult(
        available=True,
        raw_score=score,
        explanation=(
            f"Averaged, across {len(module_scores)} module(s) with resolvable species "
            "membership, the fraction of each module's own species sharing that module's "
            "single most common compartment."
        ),
        warnings=warnings,
    )


def score_ec_class_coherence(
    network: FullNetwork, memberships: tuple[ModuleMembership, ...]
) -> CriterionResult:
    """Do a module's own reactions share a consistent curated EC-number top-level class
    (e.g. ``"6.4.1.2"`` -> class ``"6"``) -- the one functional-annotation signal
    ``ReactionSpecification`` already carries (Biological Display Metadata increment)?

    **Naming note** (Topology Hub/Currency Component Filtering's own corrective follow-up
    increment): this criterion was previously named ``PATHWAY_ANNOTATION_COHERENCE``, which
    mischaracterized it as reading genuine pathway/network membership data. It never did --
    it has only ever matched curated EC-number classes, a real but narrower, differently-
    scoped signal. Genuine pathway-membership coherence (Agent 1's own curated KEGG
    ``CuratedNetwork``/pathway data, not yet wired into Agent 2's ``FullNetwork`` at all)
    remains a reserved, unimplemented ``ModularizationCriterion.PATHWAY_ANNOTATION_COHERENCE``
    for a future increment -- never conflated with this one again.

    Per module: ``module_score = (EC-annotated reactions sharing that module's own modal EC
    class) / (EC-annotated reactions in that module)``, counting only reactions that carry a
    curated ``ec_number`` at all. Overall score is the unweighted mean across every module
    with at least one EC-annotated reaction.

    **Unavailable** when no reaction in any module of this modularization carries a curated
    EC number at all -- the common case for a model with no EC curation, or for a purely
    synthetic/test fixture; "where available," never fabricated.
    """
    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    reactions_by_module = _member_ids(memberships, component_type=ModuleComponentType.REACTION)

    module_scores: list[Decimal] = []
    annotated_total = 0
    for _module_id, reaction_ids in reactions_by_module.items():
        ec_classes = []
        for rid in reaction_ids:
            reaction = reactions_by_id.get(rid)
            if reaction is None or not reaction.ec_number:
                continue
            ec_classes.append(reaction.ec_number.split(".", 1)[0].strip())
        if not ec_classes:
            continue
        annotated_total += len(ec_classes)
        modal_count = Counter(ec_classes).most_common(1)[0][1]
        module_scores.append(Decimal(modal_count) / Decimal(len(ec_classes)))

    if not module_scores:
        return CriterionResult(
            available=False,
            raw_score=None,
            explanation=(
                "No reaction in any module of this modularization carries a curated EC "
                "number -- the only functional-annotation signal currently available."
            ),
        )

    score = sum(module_scores, Decimal(0)) / Decimal(len(module_scores))
    return CriterionResult(
        available=True,
        raw_score=score,
        explanation=(
            f"Averaged, across {len(module_scores)} module(s) with at least one EC-annotated "
            f"reaction ({annotated_total} such reaction(s) total), the fraction of each "
            "module's own EC-annotated reactions sharing that module's single most common "
            "top-level EC class."
        ),
    )


__all__ = [
    "IMPLEMENTED_CRITERIA",
    "score_boundary_sparsity",
    "score_compartment_coherence",
    "score_ec_class_coherence",
    "score_topological_separation",
]
