"""Connected-component decomposition and the public Increment 7 entry point.

``decompose_network`` is this package's one public API: given
``FullNetwork``, ``KineticLawAssignmentSet``, ``ParameterDeclarationSet``,
and ``BoundaryAssessmentSet``, partitions the network's reactions into
modules by removing every selected (``HIGH``/``VERY_HIGH``) boundary and
computing ordinary connected components on what remains, then builds one
``ModuleSpecification`` per component and one ``ModuleDecomposition``
recording the decision. Pure and deterministic: no database, no
filesystem, no network access, no LLM, no simulation, no fitting, no
Antimony, no graph-clustering/spectral/ML algorithm anywhere in its call
graph. Never mutates any of its four inputs -- only reads them.

**Three distinct concepts, never conflated (see
``docs/10_module_decomposition.md``, "Local boundary decisions versus
global connectivity"):** (1) a ``BoundaryAssessment`` is Increment 6's
own local, qualitative evidence for one interface; (2) a *selected*
boundary (``ModuleDecomposition.boundary_assessment_ids``) is this
policy's local decision to remove a ``HIGH``/``VERY_HIGH`` edge from the
connectivity graph; (3) an ``InterModuleBoundaryInterface`` is the
*global* outcome -- it exists only when that removal (together with
every other selected removal) actually left its two reactions in
different final connected components. A selected boundary with an
alternate retained path elsewhere in the graph produces no interface at
all, yet remains fully visible in ``boundary_assessment_ids`` -- it is
never discarded merely because it did not end up separating anything.

**Deviation from a literal reading of Increment 7 Step 3 (public API):**
the specified signature, ``decompose_network(network, boundaries)``, does
not by itself carry enough information to populate
``ModuleSpecification.kinetic_law_assignment_ids``/``.parameter_ids`` or
to validate their references -- inspection of ``app.agent2.kinetics``/
``app.agent2.parameters`` (Increment 7's own mandatory "initial review"
step) confirms ``KineticLawAssignmentSet``/``ParameterDeclarationSet``
are separate pipeline artifacts, never written back onto ``FullNetwork``.
Two additional parameters (``kinetic_laws``, ``parameters``) were
therefore added, in the same accumulating-inputs style every prior
increment's own entry point already uses (e.g. ``assess_boundaries``
takes four inputs, not two) -- see ``docs/10_module_decomposition.md``
§3 for the full rationale.
"""

from __future__ import annotations

from app.agent2.boundaries.types import BoundaryAssessmentSet
from app.agent2.kinetics.types import KineticLawAssignmentSet
from app.agent2.modules.errors import ModuleDecompositionReferenceError
from app.agent2.modules.types import ModuleDecompositionSet
from app.agent2.modules.validation import (
    require_boundary_assessment_set,
    require_full_network,
    require_kinetic_law_assignment_set,
    require_parameter_declaration_set,
)
from app.agent2.parameters.types import ParameterDeclarationSet
from app.agent2.types import (
    BoundaryLikelihood,
    FullNetwork,
    InterModuleBoundaryInterface,
    ModuleDecomposition,
    ModuleSpecification,
    ParameterSpecification,
)
from app.agent2.version import MODULE_DECOMPOSITION_POLICY_VERSION

#: Every candidate boundary at this likelihood or above is removed from the reaction graph
#: before connected components are computed (Increment 7 instructions, Step 8) -- i.e. it is
#: "selected" as an actual module cut. Kept as a frozenset (never a numeric threshold): the
#: combination policy already establishes total ordering among the five qualitative levels
#: (`app.agent2.boundaries.policy`), this package only names which of them cut.
_CUT_LIKELIHOODS = frozenset({BoundaryLikelihood.HIGH, BoundaryLikelihood.VERY_HIGH})

#: Preserved, never discarded, never auto-cut (Increment 7 instructions, Step 9) -- the
#: qualitative evidence is genuinely equivocal, so this policy deliberately declines to guess.
_CANDIDATE_LIKELIHOODS = frozenset({BoundaryLikelihood.MEDIUM})


class _UnionFind:
    """Ordinary disjoint-set union-find over reaction ids -- no graph library, no clustering,
    no spectral method (Increment 7 instructions, Step 10: "do not invent graph algorithms
    beyond ordinary connectivity")."""

    def __init__(self, ids: tuple[str, ...]) -> None:
        self._parent: dict[str, str] = {i: i for i in ids}

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            # Deterministic tie-break: the lexicographically smaller root wins. Union-find's
            # final partition is independent of union order regardless, but a fixed rule keeps
            # intermediate parent pointers themselves deterministic too, not just the result.
            if root_b < root_a:
                root_a, root_b = root_b, root_a
            self._parent[root_b] = root_a


def _module_id_for(index: int) -> str:
    """Deterministic ``module_NNN`` naming (Increment 7 instructions, Step 14) -- never
    random, never a UUID. ``index`` is 1-based."""
    return f"module_{index:03d}"


def _reaction_species_ids(reaction, species_by_id: dict) -> tuple[str, ...]:
    return tuple(sorted({p.species_id for p in reaction.participants}))


def decompose_network(
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet,
) -> ModuleDecompositionSet:
    """Deterministically partition every reaction in ``network`` into one or more modules.

    Answers only "how should this network be split into modules, given
    Increment 6's own qualitative boundary evidence" -- never "is this
    decomposition biologically correct" (Increment 7 instructions, §2).
    See ``docs/10_module_decomposition.md`` §2.
    """
    require_full_network(network)
    require_kinetic_law_assignment_set(kinetic_laws)
    require_parameter_declaration_set(parameters)
    require_boundary_assessment_set(boundaries)
    for label, other_network_id in (
        ("kinetic_laws", kinetic_laws.network_id),
        ("parameters", parameters.network_id),
        ("boundaries", boundaries.network_id),
    ):
        if other_network_id != network.network_id:
            raise ModuleDecompositionReferenceError(
                f"{label}.network_id ({other_network_id!r}) does not match "
                f"network.network_id ({network.network_id!r})"
            )

    reaction_ids = tuple(sorted(r.reaction_id for r in network.reactions))
    species_by_id = {s.species_id: s for s in network.species}

    selected_boundary_ids = tuple(
        sorted(a.boundary_id for a in boundaries.assessments if a.likelihood in _CUT_LIKELIHOODS)
    )
    candidate_boundary_ids = tuple(
        sorted(
            a.boundary_id for a in boundaries.assessments if a.likelihood in _CANDIDATE_LIKELIHOODS
        )
    )

    union_find = _UnionFind(reaction_ids)
    for assessment in sorted(
        boundaries.assessments, key=lambda a: (a.upstream_element_id, a.downstream_element_id)
    ):
        if assessment.likelihood in _CUT_LIKELIHOODS:
            continue
        union_find.union(assessment.upstream_element_id, assessment.downstream_element_id)

    components: dict[str, list[str]] = {}
    for reaction_id in reaction_ids:
        components.setdefault(union_find.find(reaction_id), []).append(reaction_id)

    ordered_components = sorted(
        (tuple(sorted(members)) for members in components.values()), key=lambda members: members[0]
    )

    reaction_to_module: dict[str, str] = {}
    for index, members in enumerate(ordered_components, start=1):
        module_id = _module_id_for(index)
        for reaction_id in members:
            reaction_to_module[reaction_id] = module_id

    assignments_by_reaction: dict[str, list[str]] = {}
    for assignment in kinetic_laws.assignments:
        assignments_by_reaction.setdefault(assignment.reaction_id, []).append(
            assignment.assignment_id
        )

    parameters_by_reaction: dict[str, list[ParameterSpecification]] = {}
    for spec in parameters.parameter_specifications:
        if spec.reaction_id is not None:
            parameters_by_reaction.setdefault(spec.reaction_id, []).append(spec)

    enzyme_states_by_reaction: dict[str, set[str]] = {}
    for association in network.enzyme_associations:
        if association.enzyme_state_id is not None:
            enzyme_states_by_reaction.setdefault(association.reaction_id, set()).add(
                association.enzyme_state_id
            )

    reactions_by_id = {r.reaction_id: r for r in network.reactions}

    # --- Interfaces: only a boundary the policy actually selected as a cut
    # (HIGH/VERY_HIGH, i.e. excluded from the union-find loop above) can ever produce a final
    # inter-module interface. A retained LOW/MEDIUM/VERY_LOW boundary is *always* unioned
    # directly (its own upstream/downstream reaction ids are the exact arguments passed to
    # `union_find.union` above), so its own two endpoints are *provably* always in the same
    # final connected component -- union-find is monotonic and never un-merges two reactions it
    # has already merged, regardless of what else happens elsewhere in the graph. This is a
    # mathematical invariant of the algorithm, not a policy choice one could get "wrong" by
    # picking different evidence: only iterating cut-eligible assessments here (rather than
    # every assessment) makes that invariant a property of the code's own structure, not
    # something that merely happens to hold. See docs/10_module_decomposition.md, "Local
    # boundary decisions versus global connectivity".
    #
    # A selected (HIGH/VERY_HIGH) boundary is a *local* cut decision, never a guarantee of
    # global separation: if an alternate retained path elsewhere in the graph still connects the
    # two reactions (a cycle or crosstalk), they end up in the same final module despite the
    # cut, and no interface is created for that boundary -- it remains visible only in
    # `selected_boundary_ids` (never silently dropped, §5 of the same doc section). Only when
    # the two reactions genuinely resolve to different final module ids does an actual interface
    # exist.
    interfaces: list[InterModuleBoundaryInterface] = []
    for assessment in sorted(boundaries.assessments, key=lambda a: a.boundary_id):
        if assessment.likelihood not in _CUT_LIKELIHOODS:
            continue
        upstream_module = reaction_to_module.get(assessment.upstream_element_id)
        downstream_module = reaction_to_module.get(assessment.downstream_element_id)
        if (
            upstream_module is not None
            and downstream_module is not None
            and upstream_module != downstream_module
        ):
            interfaces.append(
                InterModuleBoundaryInterface(
                    interface_id=f"interface::{assessment.boundary_id}",
                    upstream_module_id=upstream_module,
                    downstream_module_id=downstream_module,
                    boundary_id=assessment.boundary_id,
                    boundary_likelihood=assessment.likelihood,
                    shared_species_ids=assessment.shared_species_ids,
                )
            )

    interfaces_by_module: dict[str, list[InterModuleBoundaryInterface]] = {}
    for interface in interfaces:
        interfaces_by_module.setdefault(interface.upstream_module_id, []).append(interface)
        interfaces_by_module.setdefault(interface.downstream_module_id, []).append(interface)

    # ModuleSpecification.source_boundary_ids semantics (deliberately broad, not ambiguous):
    # every BoundaryAssessment naming at least one of this module's own reactions as its
    # upstream or downstream element -- regardless of likelihood or cut/candidate/retained
    # status. This includes: the retained (LOW/VERY_LOW/MEDIUM) evidence that kept the module's
    # reactions merged, any MEDIUM candidate boundary lying inside the module (also disclosed
    # separately in `assumptions` below), the boundary behind any of this module's own
    # `interfaces` (its `boundary_id` always appears here too), and any selected HIGH/VERY_HIGH
    # boundary touching this module even when it did not end up separating anything (§5 of
    # docs/10_module_decomposition.md's "Local boundary decisions versus global connectivity").
    # This is a single, precise, consistently-applied rule -- not a mix of several different
    # per-case definitions -- see docs/10_module_decomposition.md §18 for why this scope was
    # chosen over the narrower "only boundaries that materially changed this module's shape".
    source_boundaries_by_module: dict[str, set[str]] = {}
    for assessment in boundaries.assessments:
        for reaction_id in (assessment.upstream_element_id, assessment.downstream_element_id):
            module_id = reaction_to_module.get(reaction_id)
            if module_id is not None:
                source_boundaries_by_module.setdefault(module_id, set()).add(assessment.boundary_id)

    modules: list[ModuleSpecification] = []
    for index, members in enumerate(ordered_components, start=1):
        module_id = _module_id_for(index)
        module_reactions = tuple(sorted(members))
        module_species = tuple(
            sorted(
                {
                    species_id
                    for reaction_id in module_reactions
                    for species_id in _reaction_species_ids(
                        reactions_by_id[reaction_id], species_by_id
                    )
                }
            )
        )
        module_compartments = tuple(
            sorted({species_by_id[species_id].compartment_id for species_id in module_species})
        )
        module_enzyme_states = tuple(
            sorted(
                {
                    enzyme_state_id
                    for reaction_id in module_reactions
                    for enzyme_state_id in enzyme_states_by_reaction.get(reaction_id, ())
                }
            )
        )
        module_kinetic_law_assignment_ids = tuple(
            sorted(
                {
                    assignment_id
                    for reaction_id in module_reactions
                    for assignment_id in assignments_by_reaction.get(reaction_id, ())
                }
            )
        )
        module_parameter_ids = tuple(
            sorted(
                {
                    spec.parameter_id
                    for reaction_id in module_reactions
                    for spec in parameters_by_reaction.get(reaction_id, ())
                }
            )
        )
        module_interfaces = sorted(
            interfaces_by_module.get(module_id, ()), key=lambda i: i.interface_id
        )
        module_interface_ids = tuple(i.interface_id for i in module_interfaces)
        module_interface_species_ids = tuple(
            sorted({species_id for i in module_interfaces for species_id in i.shared_species_ids})
        )
        module_source_boundary_ids = tuple(
            sorted(source_boundaries_by_module.get(module_id, ()))
        )
        module_candidates = sorted(
            set(module_source_boundary_ids) & set(candidate_boundary_ids)
        )
        module_assumptions = ()
        if module_candidates:
            module_assumptions = (
                f"Contains {len(module_candidates)} unresolved (MEDIUM) candidate boundary "
                f"reference(s) not cut in this decomposition: {', '.join(module_candidates)}. "
                "Ambiguity preserved for a future decomposition."
            )
            module_assumptions = (module_assumptions,)

        modules.append(
            ModuleSpecification(
                module_id=module_id,
                name=f"Module {index:03d}",
                reaction_ids=module_reactions,
                species_ids=module_species,
                parameter_ids=module_parameter_ids,
                kinetic_law_assignment_ids=module_kinetic_law_assignment_ids,
                compartment_ids=module_compartments,
                enzyme_state_ids=module_enzyme_states,
                interface_species_ids=module_interface_species_ids,
                boundary_interface_ids=module_interface_ids,
                assumptions=module_assumptions,
                source_boundary_ids=module_source_boundary_ids,
            )
        )

    module_ids = tuple(m.module_id for m in modules)
    interface_boundary_ids = {i.boundary_id for i in interfaces}
    non_separating_selected_ids = tuple(
        sorted(set(selected_boundary_ids) - interface_boundary_ids)
    )
    explanation = (
        f"Decomposed into {len(modules)} module(s) from {len(reaction_ids)} reaction(s). "
        f"Selected (HIGH/VERY_HIGH) boundaries removed from the connectivity graph: "
        f"{len(selected_boundary_ids)}. Candidate (MEDIUM) boundaries preserved, not cut: "
        f"{len(candidate_boundary_ids)}. Final modules are the connected components that "
        f"remain after removing every selected boundary. Inter-module interfaces actually "
        f"realized: {len(interfaces)}. Selected boundaries that did not separate any module "
        "(an alternate retained path kept both sides connected -- possible crosstalk, not "
        f"discarded): {len(non_separating_selected_ids)}."
    )

    decomposition = ModuleDecomposition(
        decomposition_id=f"decomposition::{network.network_id}",
        name="default decomposition",
        policy_version=MODULE_DECOMPOSITION_POLICY_VERSION,
        created_from_network_id=network.network_id,
        module_ids=module_ids,
        boundary_assessment_ids=selected_boundary_ids,
        candidate_boundary_ids=candidate_boundary_ids,
        interfaces=tuple(sorted(interfaces, key=lambda i: i.interface_id)),
        assumptions=(
            "Increment 7 v1 deterministic policy: HIGH/VERY_HIGH boundaries are selected for "
            "removal from the connectivity graph; MEDIUM boundaries are preserved as "
            "candidate_boundary_ids (never auto-cut, never promoted to a selected cut); "
            "LOW/VERY_LOW boundaries are never cut. Final modules are the ordinary connected "
            "components of the reaction graph that remain after removing every selected "
            "boundary. A selected boundary does not guarantee module separation: if an "
            "alternate retained path still connects its two reactions, they remain in the same "
            "module and no InterModuleBoundaryInterface is produced for that boundary, even "
            "though it stays recorded in boundary_assessment_ids for audit.",
        ),
        explanation=explanation,
    )

    decomposition_set = ModuleDecompositionSet(
        network_id=network.network_id,
        boundary_policy_version=boundaries.boundary_policy_version,
        decomposition_policy_version=MODULE_DECOMPOSITION_POLICY_VERSION,
        decompositions=(decomposition,),
        module_specifications=tuple(modules),
    )

    _validate_references(decomposition_set, network=network, kinetic_laws=kinetic_laws,
                          parameters=parameters, boundaries=boundaries)
    return decomposition_set


def _validate_references(
    decomposition_set: ModuleDecompositionSet,
    *,
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet,
) -> None:
    """Defensive backstop: every referenced id actually exists, and every
    ``InterModuleBoundaryInterface`` genuinely represents a selected cut that actually
    separated two modules. Should never trigger given a correct implementation -- mirrors the
    identical post-construction pattern already established in
    app.agent2.boundaries/app.agent2.kinetics/app.agent2.parameters."""
    reaction_ids = {r.reaction_id for r in network.reactions}
    species_ids = {s.species_id for s in network.species}
    compartment_ids = {c.compartment_id for c in network.compartments}
    enzyme_state_ids = {s.id for s in network.enzyme_states}
    assignment_ids = {a.assignment_id for a in kinetic_laws.assignments}
    parameter_ids = {p.parameter_id for p in parameters.parameter_specifications}
    boundary_ids = {b.boundary_id for b in boundaries.assessments}
    assessment_by_id = {b.boundary_id: b for b in boundaries.assessments}

    for module in decomposition_set.module_specifications:
        _require_known(module.reaction_ids, reaction_ids, module.module_id, "reaction_ids")
        _require_known(module.species_ids, species_ids, module.module_id, "species_ids")
        _require_known(module.compartment_ids, compartment_ids, module.module_id, "compartment_ids")
        _require_known(
            module.enzyme_state_ids, enzyme_state_ids, module.module_id, "enzyme_state_ids"
        )
        _require_known(
            module.kinetic_law_assignment_ids,
            assignment_ids,
            module.module_id,
            "kinetic_law_assignment_ids",
        )
        _require_known(module.parameter_ids, parameter_ids, module.module_id, "parameter_ids")
        _require_known(
            module.source_boundary_ids, boundary_ids, module.module_id, "source_boundary_ids"
        )
        _require_known(
            module.interface_species_ids, species_ids, module.module_id, "interface_species_ids"
        )

    module_ids = {m.module_id for m in decomposition_set.module_specifications}
    reaction_ids_by_module = {
        m.module_id: set(m.reaction_ids) for m in decomposition_set.module_specifications
    }
    for decomposition in decomposition_set.decompositions:
        _require_known(
            decomposition.module_ids, module_ids, decomposition.decomposition_id, "module_ids"
        )
        _require_known(
            decomposition.boundary_assessment_ids,
            boundary_ids,
            decomposition.decomposition_id,
            "boundary_assessment_ids",
        )
        _require_known(
            decomposition.candidate_boundary_ids,
            boundary_ids,
            decomposition.decomposition_id,
            "candidate_boundary_ids",
        )
        for interface in decomposition.interfaces:
            _require_known(
                (interface.upstream_module_id, interface.downstream_module_id),
                module_ids,
                decomposition.decomposition_id,
                f"interface {interface.interface_id} module ids",
            )
            _require_known(
                (interface.boundary_id,),
                boundary_ids,
                decomposition.decomposition_id,
                f"interface {interface.interface_id}.boundary_id",
            )
            _require_known(
                interface.shared_species_ids,
                species_ids,
                decomposition.decomposition_id,
                f"interface {interface.interface_id}.shared_species_ids",
            )
            # Step 6/13 invariant: an interface may only exist for a boundary the policy
            # actually selected as a cut (HIGH/VERY_HIGH) -- a retained LOW/MEDIUM/VERY_LOW
            # boundary can never produce one (§ module docstring). Re-checked here defensively,
            # even though it is already guaranteed by construction above.
            assessment = assessment_by_id.get(interface.boundary_id)
            if assessment is not None and assessment.likelihood not in _CUT_LIKELIHOODS:
                raise ModuleDecompositionReferenceError(
                    f"interface {interface.interface_id!r} refers to boundary "
                    f"{interface.boundary_id!r} with likelihood {assessment.likelihood.value!r}, "
                    "which was never selected as a cut -- a retained boundary must never "
                    "produce an InterModuleBoundaryInterface"
                )
            # Step 13 invariant: an interface's endpoints must actually belong to the modules
            # it claims to connect -- never merely two module ids that happen to exist.
            if assessment is not None:
                upstream_reactions = reaction_ids_by_module.get(interface.upstream_module_id, set())
                downstream_reactions = reaction_ids_by_module.get(
                    interface.downstream_module_id, set()
                )
                if assessment.upstream_element_id not in upstream_reactions:
                    raise ModuleDecompositionReferenceError(
                        f"interface {interface.interface_id!r}.upstream_module_id "
                        f"{interface.upstream_module_id!r} does not contain reaction "
                        f"{assessment.upstream_element_id!r}"
                    )
                if assessment.downstream_element_id not in downstream_reactions:
                    raise ModuleDecompositionReferenceError(
                        f"interface {interface.interface_id!r}.downstream_module_id "
                        f"{interface.downstream_module_id!r} does not contain reaction "
                        f"{assessment.downstream_element_id!r}"
                    )


def _require_known(ids: tuple[str, ...], known: set[str], owner_id: str, field_name: str) -> None:
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ModuleDecompositionReferenceError(
            f"{owner_id}.{field_name} references unknown id(s): {unknown}"
        )


__all__ = ["decompose_network"]
