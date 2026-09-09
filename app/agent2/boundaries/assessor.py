"""Candidate-interface generation and the public Increment 6 entry point.

``assess_boundaries`` is this package's one public API: given
``FullNetwork``, ``NetworkCharacterization``, ``KineticLawAssignmentSet``,
and ``ParameterDeclarationSet``, generates every candidate module-boundary
interface from actual network connectivity (never an arbitrary pairwise
reaction comparison -- Increment 6 instructions, Step 5), evaluates
``rules.ALL_RULES`` against each, and combines the outcomes
(``policy.combine_outcomes``) into one qualitative ``BoundaryAssessment``
per candidate. Pure and deterministic: no database, no filesystem, no
network access, no LLM, no simulation, no fitting, no Antimony anywhere
in its call graph. Never mutates any of its four inputs -- only reads
them.
"""

from __future__ import annotations

from app.agent2.boundaries import policy, rules
from app.agent2.boundaries.errors import BoundaryReferenceError
from app.agent2.boundaries.rules import CandidateFacts
from app.agent2.boundaries.types import BoundaryAssessmentSet, RuleStrength
from app.agent2.boundaries.validation import (
    require_full_network,
    require_kinetic_law_assignment_set,
    require_network_characterization,
    require_parameter_declaration_set,
)
from app.agent2.characterization.types import NetworkCharacterization, ReactionCharacterization
from app.agent2.kinetics.types import (
    KineticLawAssignment,
    KineticLawAssignmentSet,
    KineticLawAssignmentSource,
)
from app.agent2.parameters.types import ParameterDeclarationSet
from app.agent2.types import (
    BoundaryAssessment,
    CuratedRegulatoryInteraction,
    FullNetwork,
    KineticLawType,
    ParameterSpecification,
    ParticipantRole,
    ReactionSpecification,
)
from app.agent2.version import BOUNDARY_POLICY_VERSION

#: A species touched by strictly more than this many distinct reactions (producers plus
#: consumers combined) counts as a high-connectivity structural hub. A small, fixed,
#: documented integer count -- never a percentage of network size, and never a per-name
#: currency-metabolite list. See docs/09 sec 21 for the full rationale.
_HIGH_CONNECTIVITY_THRESHOLD = 3

#: Closed, Agent-2-maintained recognition vocabulary for `CuratedRegulatoryInteraction
#: .regulator_type`/`.target_type` -- both fields are deliberately open strings on the
#: already-approved contract (mirroring `CuratedKineticMeasurement.parameter_type`'s own
#: "open on Agent 1's side, closed recognition set on Agent 2's side" pattern). Matched
#: case-insensitively; an interaction whose types do not match is simply never resolved to
#: a side (never guessed) -- see docs/09 sec 14a.
_REGULATOR_COMPOUND_TYPE_MARKERS = frozenset({"COMPOUND"})
_TARGET_REACTION_TYPE_MARKERS = frozenset({"REACTION"})

#: Closed recognition set for an inhibitory `CuratedRegulatoryInteraction.effect` -- used
#: only by `rules.intrinsic_feedback_isolation` (intrinsic/negative feedback is
#: specifically *inhibitory* feedback confined to one side). `crossing_regulatory_interaction`
#: below is not filtered by effect -- crossing is a structural fact independent of sign -- but
#: `rules.extrinsic_feedback_crossing` deliberately never acts on it (Increment 6
#: feedback-heuristic revision; see that function's own docstring for why no inference is made
#: -- direct/strong/constitutive/regulated/adaptive/dynamically-isolating/dynamically-coupling
#: are all currently undeterminable from static curated structure).
_INHIBITORY_EFFECT_MARKERS = frozenset({"INHIBITION", "INHIBITOR", "NEGATIVE"})


def _build_producers_consumers(
    network: FullNetwork,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    producers: dict[str, set[str]] = {}
    consumers: dict[str, set[str]] = {}
    for reaction in network.reactions:
        for participant in reaction.participants:
            if participant.role is ParticipantRole.PRODUCT:
                producers.setdefault(participant.species_id, set()).add(reaction.reaction_id)
            elif participant.role is ParticipantRole.REACTANT:
                consumers.setdefault(participant.species_id, set()).add(reaction.reaction_id)
    return producers, consumers


def _generate_candidates(
    producers: dict[str, set[str]], consumers: dict[str, set[str]]
) -> dict[tuple[str, str], tuple[str, ...]]:
    """One candidate per ordered (upstream_reaction, downstream_reaction) pair actually
    connected by at least one shared species -- never an arbitrary pairwise comparison."""
    pairs: dict[tuple[str, str], set[str]] = {}
    for species_id, producer_ids in producers.items():
        consumer_ids = consumers.get(species_id, set())
        for upstream in producer_ids:
            for downstream in consumer_ids:
                if upstream == downstream:
                    continue
                pairs.setdefault((upstream, downstream), set()).add(species_id)
    return {pair: tuple(sorted(species)) for pair, species in pairs.items()}


def _reaction_compartments(reaction, species_by_id) -> frozenset[str]:
    return frozenset(species_by_id[p.species_id].compartment_id for p in reaction.participants)


def _has_curated_regulatory_context(rc: ReactionCharacterization) -> bool:
    return bool(rc.regulation_ids) or bool(rc.allosteric_interaction_ids)


def _assignment_confidence(assignment: KineticLawAssignment) -> RuleStrength:
    """Deliberately distinct from `KineticLawAssignmentSource` itself: an `UNASSIGNED`
    assignment means "no law decision was made at all," which is weaker evidence than even a
    tentative default (which at least picked a structure), so it is its own `WEAK` case
    rather than falling through to the generic `MODERATE` default below."""
    if assignment.kinetic_law_type is KineticLawType.UNASSIGNED or assignment.is_tentative:
        return RuleStrength.WEAK
    if assignment.assignment_source in (
        KineticLawAssignmentSource.CURATED_REPORTED,
        KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
    ):
        return RuleStrength.STRONG
    return RuleStrength.MODERATE


def _weakest_confidence(assignments: tuple[KineticLawAssignment, ...]) -> RuleStrength | None:
    if not assignments:
        return None
    confidences = [_assignment_confidence(a) for a in assignments]
    weakest = confidences[0]
    for confidence in confidences[1:]:
        weakest = rules.weaker_strength(weakest, confidence)
    return weakest


def _catalytic_ids(rc: ReactionCharacterization | None) -> frozenset[str]:
    if rc is None:
        return frozenset()
    return frozenset(rc.catalytic_protein_ids) | frozenset(rc.catalytic_complex_ids) | frozenset(
        rc.catalytic_enzyme_state_ids
    )


def _reaction_compound_ids(
    reaction: ReactionSpecification, species_by_id
) -> frozenset[str]:
    """Every curated compound touched (any participant role) by one reaction -- the local,
    single-reaction scope `rules.intrinsic_feedback_isolation`/`crossing_regulatory_interaction`
    resolve a regulator's "side" against (see module docstring and docs/09 sec 14a)."""
    compound_ids = set()
    for participant in reaction.participants:
        source_compound_id = species_by_id[participant.species_id].source_compound_id
        if source_compound_id is not None:
            compound_ids.add(source_compound_id)
    return frozenset(compound_ids)


def _regulatory_interactions_by_target(
    network: FullNetwork,
) -> dict[str, list[CuratedRegulatoryInteraction]]:
    """Every curated regulatory interaction whose `target_type`/`target_id` resolve
    (case-insensitively) to a real reaction id -- grouped by that reaction id. An
    interaction whose types/ids do not resolve is simply excluded here (never guessed)."""
    by_target: dict[str, list[CuratedRegulatoryInteraction]] = {}
    for interaction in network.regulatory_interactions:
        if interaction.target_id is None or interaction.regulator_id is None:
            continue
        if interaction.target_type.strip().upper() not in _TARGET_REACTION_TYPE_MARKERS:
            continue
        if interaction.regulator_type.strip().upper() not in _REGULATOR_COMPOUND_TYPE_MARKERS:
            continue
        by_target.setdefault(interaction.target_id, []).append(interaction)
    return by_target


def _resolve_feedback(
    *,
    upstream_id: str,
    downstream_id: str,
    upstream_compound_ids: frozenset[str],
    downstream_compound_ids: frozenset[str],
    regulatory_by_target: dict[str, list[CuratedRegulatoryInteraction]],
) -> tuple[bool, bool]:
    """Whether any curated, fully-resolvable regulatory interaction touching this candidate
    is (a) an inhibitory interaction confined entirely within one side
    (`confined_inhibitory_feedback`) or (b) any interaction whose regulator and target
    resolve to *different* sides (`crossing_regulatory_interaction`).

    An interaction whose regulator compound touches both sides, or neither, is ambiguous or
    external and contributes to neither signal -- conservatively excluded, never guessed
    (Increment 6 revision: "Initially this rule may often return NEUTRAL because
    insufficient information exists. That is acceptable.").
    """
    confined_inhibitory = False
    crossing = False
    for target_id, own_compound_ids, other_compound_ids in (
        (upstream_id, upstream_compound_ids, downstream_compound_ids),
        (downstream_id, downstream_compound_ids, upstream_compound_ids),
    ):
        for interaction in regulatory_by_target.get(target_id, ()):
            regulator_compound_id = interaction.regulator_id
            on_own_side = regulator_compound_id in own_compound_ids
            on_other_side = regulator_compound_id in other_compound_ids
            if on_own_side and not on_other_side:
                if interaction.effect.strip().upper() in _INHIBITORY_EFFECT_MARKERS:
                    confined_inhibitory = True
            elif on_other_side and not on_own_side:
                crossing = True
            # else: ambiguous (both sides) or external (neither side) -- no signal.
    return confined_inhibitory, crossing


def assess_boundaries(
    network: FullNetwork,
    characterization: NetworkCharacterization,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
) -> BoundaryAssessmentSet:
    """Deterministically evaluate every candidate module-boundary interface in ``network``.

    Answers only "how plausible is this interface as a module boundary" --
    never "where should the network actually be cut" (Increment 7's job).
    See ``docs/09_heuristic_boundary_assessment.md`` §2.
    """
    require_full_network(network)
    require_network_characterization(characterization)
    require_kinetic_law_assignment_set(kinetic_laws)
    require_parameter_declaration_set(parameters)
    for label, other_network_id in (
        ("characterization", characterization.network_id),
        ("kinetic_laws", kinetic_laws.network_id),
        ("parameters", parameters.network_id),
    ):
        if other_network_id != network.network_id:
            raise BoundaryReferenceError(
                f"{label}.network_id ({other_network_id!r}) does not match "
                f"network.network_id ({network.network_id!r})"
            )

    species_by_id = {s.species_id: s for s in network.species}
    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    reaction_characterizations_by_id = {
        rc.reaction_id: rc for rc in characterization.reaction_characterizations
    }
    assignments_by_reaction: dict[str, list[KineticLawAssignment]] = {}
    for assignment in kinetic_laws.assignments:
        assignments_by_reaction.setdefault(assignment.reaction_id, []).append(assignment)
    parameters_by_reaction: dict[str, list[ParameterSpecification]] = {}
    for spec in parameters.parameter_specifications:
        if spec.reaction_id is not None:
            parameters_by_reaction.setdefault(spec.reaction_id, []).append(spec)
    regulatory_by_target = _regulatory_interactions_by_target(network)

    producers, consumers = _build_producers_consumers(network)
    candidates = _generate_candidates(producers, consumers)

    connectivity: dict[str, int] = {
        species_id: len(producers.get(species_id, ())) + len(consumers.get(species_id, ()))
        for species_id in set(producers) | set(consumers)
    }

    reaction_compartments_cache: dict[str, frozenset[str]] = {}
    reaction_compound_ids_cache: dict[str, frozenset[str]] = {}

    def compartments_for(reaction_id: str) -> frozenset[str]:
        if reaction_id not in reaction_compartments_cache:
            reaction_compartments_cache[reaction_id] = _reaction_compartments(
                reactions_by_id[reaction_id], species_by_id
            )
        return reaction_compartments_cache[reaction_id]

    def compound_ids_for(reaction_id: str) -> frozenset[str]:
        if reaction_id not in reaction_compound_ids_cache:
            reaction_compound_ids_cache[reaction_id] = _reaction_compound_ids(
                reactions_by_id[reaction_id], species_by_id
            )
        return reaction_compound_ids_cache[reaction_id]

    assessments: list[BoundaryAssessment] = []
    for (upstream_id, downstream_id), shared_species in sorted(candidates.items()):
        upstream_rc = reaction_characterizations_by_id.get(upstream_id)
        downstream_rc = reaction_characterizations_by_id.get(downstream_id)
        upstream_assignments = tuple(assignments_by_reaction.get(upstream_id, ()))
        downstream_assignments = tuple(assignments_by_reaction.get(downstream_id, ()))
        upstream_params = tuple(parameters_by_reaction.get(upstream_id, ()))
        downstream_params = tuple(parameters_by_reaction.get(downstream_id, ()))

        upstream_compound_ids = compound_ids_for(upstream_id)
        downstream_compound_ids = compound_ids_for(downstream_id)
        confined_inhibitory_feedback, crossing_regulatory_interaction = _resolve_feedback(
            upstream_id=upstream_id,
            downstream_id=downstream_id,
            upstream_compound_ids=upstream_compound_ids,
            downstream_compound_ids=downstream_compound_ids,
            regulatory_by_target=regulatory_by_target,
        )

        facts = CandidateFacts(
            upstream_reaction_id=upstream_id,
            downstream_reaction_id=downstream_id,
            shared_species_ids=shared_species,
            upstream_classes=(
                frozenset(upstream_rc.reaction_classes) if upstream_rc else frozenset()
            ),
            downstream_classes=(
                frozenset(downstream_rc.reaction_classes) if downstream_rc else frozenset()
            ),
            upstream_compartments=compartments_for(upstream_id),
            downstream_compartments=compartments_for(downstream_id),
            upstream_regulatory_context=(
                _has_curated_regulatory_context(upstream_rc) if upstream_rc else False
            ),
            downstream_regulatory_context=(
                _has_curated_regulatory_context(downstream_rc) if downstream_rc else False
            ),
            upstream_law_types=frozenset(a.kinetic_law_type for a in upstream_assignments),
            downstream_law_types=frozenset(a.kinetic_law_type for a in downstream_assignments),
            upstream_law_confidence=_weakest_confidence(upstream_assignments),
            downstream_law_confidence=_weakest_confidence(downstream_assignments),
            any_shared_species_branch=any(
                len(consumers.get(species_id, ())) > 1 for species_id in shared_species
            ),
            any_shared_species_convergence=any(
                len(producers.get(species_id, ())) > 1 for species_id in shared_species
            ),
            any_shared_species_high_connectivity=any(
                connectivity.get(species_id, 0) > _HIGH_CONNECTIVITY_THRESHOLD
                for species_id in shared_species
            ),
            upstream_reversible=reactions_by_id[upstream_id].reversible,
            downstream_reversible=reactions_by_id[downstream_id].reversible,
            upstream_catalytic_ids=_catalytic_ids(upstream_rc),
            downstream_catalytic_ids=_catalytic_ids(downstream_rc),
            confined_inhibitory_feedback=confined_inhibitory_feedback,
            crossing_regulatory_interaction=crossing_regulatory_interaction,
        )

        outcomes = tuple(rule(facts) for rule in rules.ALL_RULES)
        supports = tuple(o for o in outcomes if o.direction.value == "SUPPORT")
        opposes = tuple(o for o in outcomes if o.direction.value == "OPPOSE")
        likelihood = policy.combine_outcomes(outcomes)

        involved_parameter_sources = tuple(p.source for p in (*upstream_params, *downstream_params))
        parameter_basis = policy.compute_parameter_basis(involved_parameter_sources)

        explanation = policy.build_explanation(
            likelihood=likelihood,
            supports=supports,
            opposes=opposes,
            parameter_basis=parameter_basis,
        )

        involved_kinetic_law_ids = tuple(
            sorted(a.assignment_id for a in (*upstream_assignments, *downstream_assignments))
        )
        involved_parameter_ids = tuple(
            sorted(p.parameter_id for p in (*upstream_params, *downstream_params))
        )

        assessments.append(
            BoundaryAssessment(
                boundary_id=policy.build_boundary_id(upstream_id, downstream_id),
                upstream_element_id=upstream_id,
                downstream_element_id=downstream_id,
                likelihood=likelihood,
                explanation=explanation,
                policy_version=BOUNDARY_POLICY_VERSION,
                shared_species_ids=shared_species,
                connecting_reaction_ids=tuple(sorted({upstream_id, downstream_id})),
                supporting_reason_codes=tuple(sorted(o.reason_code.value for o in supports)),
                opposing_reason_codes=tuple(sorted(o.reason_code.value for o in opposes)),
                kinetic_law_ids=involved_kinetic_law_ids,
                parameter_ids=involved_parameter_ids,
                parameter_basis=parameter_basis,
            )
        )

    assessment_set = BoundaryAssessmentSet(
        network_id=network.network_id,
        characterization_policy_version=characterization.characterization_policy_version,
        kinetic_law_policy_version=kinetic_laws.kinetic_law_policy_version,
        parameter_policy_version=parameters.parameter_policy_version,
        boundary_policy_version=BOUNDARY_POLICY_VERSION,
        assessments=tuple(assessments),
    )

    _validate_references(
        assessment_set, network=network, kinetic_laws=kinetic_laws, parameters=parameters
    )
    return assessment_set


def _validate_references(
    assessment_set: BoundaryAssessmentSet,
    *,
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
) -> None:
    """Defensive backstop: every referenced reaction/species/law/parameter id actually
    exists. Should never trigger given a correct implementation -- mirrors the identical
    post-construction pattern already established in app.agent2.kinetics/app.agent2.parameters.
    """
    reaction_ids = {r.reaction_id for r in network.reactions}
    species_ids = {s.species_id for s in network.species}
    kinetic_law_ids = {a.assignment_id for a in kinetic_laws.assignments}
    parameter_ids = {p.parameter_id for p in parameters.parameter_specifications}

    for assessment in assessment_set.assessments:
        if assessment.upstream_element_id not in reaction_ids:
            raise BoundaryReferenceError(
                f"boundary {assessment.boundary_id!r} references unknown upstream reaction "
                f"{assessment.upstream_element_id!r}"
            )
        if assessment.downstream_element_id not in reaction_ids:
            raise BoundaryReferenceError(
                f"boundary {assessment.boundary_id!r} references unknown downstream reaction "
                f"{assessment.downstream_element_id!r}"
            )
        for species_id in assessment.shared_species_ids:
            if species_id not in species_ids:
                raise BoundaryReferenceError(
                    f"boundary {assessment.boundary_id!r} references unknown species {species_id!r}"
                )
        for law_id in assessment.kinetic_law_ids:
            if law_id not in kinetic_law_ids:
                raise BoundaryReferenceError(
                    f"boundary {assessment.boundary_id!r} references unknown kinetic law {law_id!r}"
                )
        for parameter_id in assessment.parameter_ids:
            if parameter_id not in parameter_ids:
                raise BoundaryReferenceError(
                    f"boundary {assessment.boundary_id!r} references unknown parameter "
                    f"{parameter_id!r}"
                )


__all__ = ["assess_boundaries"]
