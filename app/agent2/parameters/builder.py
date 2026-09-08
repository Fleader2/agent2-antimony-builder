"""Parameter declaration per kinetic-law type and the public Increment 5 entry point.

``declare_parameters`` is this package's one public API: given a
``KineticLawAssignmentSet`` and the ``FullNetwork`` it was decided from,
resolves every reaction's curated kinetic measurements once, then, for
each non-``UNASSIGNED`` assignment, declares exactly the parameters that
assignment's ``kinetic_law_type`` requires (Increment 5 instructions,
Step 8), each initialized from curated evidence where a deterministic
policy permits (`initializer.py`) and otherwise left an explicitly
``PLACEHOLDER`` slot. Pure and deterministic: no database, no filesystem,
no network access, no LLM, no simulation, no fitting, no random numbers
anywhere in its call graph.
"""

from __future__ import annotations

from app.agent2.kinetics.types import (
    KineticLawAssignment,
    KineticLawAssignmentSet,
    KineticLawReasonCode,
)
from app.agent2.parameters import policy
from app.agent2.parameters.errors import ParameterReferenceError
from app.agent2.parameters.initializer import Initialization, initialize_from_evidence
from app.agent2.parameters.types import ParameterDeclarationSet
from app.agent2.parameters.validation import (
    require_full_network,
    require_kinetic_law_assignment_set,
)
from app.agent2.types import (
    CuratedKineticMeasurement,
    FullNetwork,
    KineticLawType,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    SpeciesSpecification,
)
from app.agent2.version import PARAMETER_DECLARATION_POLICY_VERSION

#: Every family CUSTOM's undifferentiated scan recognizes, each with its own naming prefix.
#: Order is fixed (not derived from dict/set iteration) so CUSTOM's declared parameters are
#: always produced in the same order regardless of curated collection order.
_CUSTOM_FAMILIES: tuple[tuple[str, frozenset[str]], ...] = (
    ("k", policy.RATE_CONSTANT_TYPES),
    ("kf", policy.FORWARD_RATE_TYPES),
    ("kr", policy.REVERSE_RATE_TYPES),
    ("kcat", policy.KCAT_TYPES),
    ("Vmax", policy.VMAX_TYPES),
    ("Km", policy.KM_TYPES),
    ("Ki", policy.KI_TYPES),
    ("Keq", policy.KEQ_TYPES),
    ("n", policy.HILL_COEFFICIENT_TYPES),
)


def _is_tentative(assignment: KineticLawAssignment) -> bool:
    return KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT in assignment.reason_codes


def _matches_context(
    measurement: CuratedKineticMeasurement, assignment: KineticLawAssignment
) -> bool:
    if assignment.enzyme_state_id is not None:
        return measurement.enzyme_state_id == assignment.enzyme_state_id
    if assignment.protein_id is not None:
        return (
            measurement.protein_id == assignment.protein_id
            and measurement.enzyme_state_id is None
        )
    if assignment.complex_id is not None:
        return (
            measurement.complex_id == assignment.complex_id
            and measurement.enzyme_state_id is None
        )
    return (
        measurement.enzyme_state_id is None
        and measurement.protein_id is None
        and measurement.complex_id is None
    )


def _evidence_for(
    assignment: KineticLawAssignment,
    reaction_measurements: tuple[CuratedKineticMeasurement, ...],
    *,
    sibling_count: int,
) -> tuple[CuratedKineticMeasurement, ...]:
    """Every curated measurement relevant to one assignment's catalytic context.

    Deliberately in the same spirit as (though not a byte-for-byte
    reproduction of -- that logic is a private implementation detail of
    ``app.agent2.kinetics.selector``, not exported) Increment 4's own
    evidence-gathering rule: when this assignment is the **sole**
    catalytic context for its reaction (``sibling_count == 1`` -- true
    for a no-catalyst reaction, a single specific catalyst, or several
    isozymes Increment 4 already collapsed into one shared assignment),
    every measurement for the reaction is fair game, tagged or not --
    there is no sibling context it could rightfully belong to instead.
    When more than one distinct context exists for the reaction (multiple
    catalytic enzyme states, or isozymes Increment 4 kept separate
    because their evidence differed), each context only ever sees
    measurements tagged with its own exact identity -- a measurement
    tagged for one state/protein/complex is never visible to a sibling
    context's parameter declaration, exactly as it was never visible to
    that sibling's kinetic-law decision. See
    ``docs/08_parameter_declaration_initialization.md`` §4.
    """
    if sibling_count == 1:
        return reaction_measurements
    return tuple(m for m in reaction_measurements if _matches_context(m, assignment))


def _spec_from_initialization(
    prefix: str,
    *,
    assignment: KineticLawAssignment,
    initialization: Initialization,
    substrate_id: str | None = None,
) -> ParameterSpecification:
    suffix = policy.context_suffix(
        enzyme_state_id=assignment.enzyme_state_id,
        protein_id=assignment.protein_id,
        complex_id=assignment.complex_id,
    )
    slug = policy.build_parameter_slug(
        prefix, reaction_id=assignment.reaction_id, suffix=suffix, substrate_id=substrate_id
    )
    return ParameterSpecification(
        parameter_id=slug,
        name=slug,
        source=initialization.source,
        value=initialization.value,
        unit=initialization.unit,
        source_reference=initialization.source_reference,
        reaction_id=assignment.reaction_id,
        kinetic_law_assignment_id=assignment.assignment_id,
        uncertainty_text=initialization.uncertainty_text,
        provenance_refs=initialization.provenance_refs,
    )


def _placeholder_spec(
    prefix: str,
    *,
    assignment: KineticLawAssignment,
    uncertainty_text: str,
    substrate_id: str | None = None,
) -> ParameterSpecification:
    suffix = policy.context_suffix(
        enzyme_state_id=assignment.enzyme_state_id,
        protein_id=assignment.protein_id,
        complex_id=assignment.complex_id,
    )
    slug = policy.build_parameter_slug(
        prefix, reaction_id=assignment.reaction_id, suffix=suffix, substrate_id=substrate_id
    )
    return ParameterSpecification(
        parameter_id=slug,
        name=slug,
        source=ParameterSource.PLACEHOLDER,
        reaction_id=assignment.reaction_id,
        kinetic_law_assignment_id=assignment.assignment_id,
        uncertainty_text=uncertainty_text,
    )


def _declare_mass_action(
    assignment: KineticLawAssignment, evidence: tuple[CuratedKineticMeasurement, ...]
) -> tuple[ParameterSpecification, ...]:
    if _is_tentative(assignment):
        # Increment 5 instructions, Step 16: never attempt curated mapping for a tentative
        # default -- the mechanism itself is unconfirmed, so no measurement could justifiably
        # initialize its rate constant even if one happens to exist for this context.
        return (
            _placeholder_spec(
                "k",
                assignment=assignment,
                uncertainty_text=(
                    "Tentative mass-action default (TENTATIVE_MASS_ACTION_DEFAULT): the "
                    "underlying mechanism is unconfirmed, so no curated value is used even if "
                    "one exists for this context. Requires calibration."
                ),
            ),
        )
    matches = policy.measurements_of_kind(evidence, policy.RATE_CONSTANT_TYPES)
    return (
        _spec_from_initialization(
            "k", assignment=assignment, initialization=initialize_from_evidence(matches)
        ),
    )


def _declare_reversible_mass_action(
    assignment: KineticLawAssignment, evidence: tuple[CuratedKineticMeasurement, ...]
) -> tuple[ParameterSpecification, ...]:
    forward = policy.measurements_of_kind(evidence, policy.FORWARD_RATE_TYPES)
    reverse = policy.measurements_of_kind(evidence, policy.REVERSE_RATE_TYPES)
    return (
        _spec_from_initialization(
            "kf", assignment=assignment, initialization=initialize_from_evidence(forward)
        ),
        _spec_from_initialization(
            "kr", assignment=assignment, initialization=initialize_from_evidence(reverse)
        ),
    )


def _reactant_compound_ids(
    network: FullNetwork, reaction_id: str, species_by_id: dict[str, SpeciesSpecification]
) -> tuple[str, ...]:
    (reaction,) = (r for r in network.reactions if r.reaction_id == reaction_id)
    reactant_ids = []
    for participant in reaction.participants:
        if participant.role is not ParticipantRole.REACTANT:
            continue
        species = species_by_id[participant.species_id]
        reactant_ids.append(species.source_compound_id or species.species_id)
    return tuple(reactant_ids)


def _declare_michaelis_menten(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
) -> tuple[ParameterSpecification, ...]:
    specs = [
        _spec_from_initialization(
            "kcat",
            assignment=assignment,
            initialization=initialize_from_evidence(
                policy.measurements_of_kind(evidence, policy.KCAT_TYPES)
            ),
        )
    ]
    km_evidence = policy.measurements_of_kind(evidence, policy.KM_TYPES)
    single_substrate = len(reactant_compound_ids) == 1
    for compound_id in reactant_compound_ids:
        substrate_matches = tuple(
            m
            for m in km_evidence
            if m.compound_id == compound_id or (m.compound_id is None and single_substrate)
        )
        specs.append(
            _spec_from_initialization(
                "Km",
                assignment=assignment,
                initialization=initialize_from_evidence(substrate_matches),
                substrate_id=compound_id,
            )
        )
    # Ki is deliberately never declared here (Increment 5 instructions, Step 8:
    # "Do not invent inhibition constants") -- plain Michaelis-Menten has no inhibition term.
    return tuple(specs)


def _declare_hill(
    assignment: KineticLawAssignment, evidence: tuple[CuratedKineticMeasurement, ...]
) -> tuple[ParameterSpecification, ...]:
    return (
        _spec_from_initialization(
            "Vmax",
            assignment=assignment,
            initialization=initialize_from_evidence(
                policy.measurements_of_kind(evidence, policy.VMAX_TYPES)
            ),
        ),
        _spec_from_initialization(
            "Km",
            assignment=assignment,
            initialization=initialize_from_evidence(
                policy.measurements_of_kind(evidence, policy.KM_TYPES)
            ),
        ),
        _spec_from_initialization(
            "n",
            assignment=assignment,
            initialization=initialize_from_evidence(
                policy.measurements_of_kind(evidence, policy.HILL_COEFFICIENT_TYPES)
            ),
        ),
    )


def _declare_custom(
    assignment: KineticLawAssignment, evidence: tuple[CuratedKineticMeasurement, ...]
) -> tuple[ParameterSpecification, ...]:
    specs = []
    for prefix, family in _CUSTOM_FAMILIES:
        matches = policy.measurements_of_kind(evidence, family)
        if matches:
            specs.append(
                _spec_from_initialization(
                    prefix, assignment=assignment, initialization=initialize_from_evidence(matches)
                )
            )
    if specs:
        return tuple(specs)
    return (
        _placeholder_spec(
            "k_custom",
            assignment=assignment,
            uncertainty_text=(
                "CUSTOM kinetic law with no recognized curated parameter metadata; the "
                "reported rate-law text is preserved on the KineticLawAssignment but never "
                "symbolically parsed. Requires manual definition and calibration."
            ),
        ),
    )


def _declare_for_assignment(
    assignment: KineticLawAssignment,
    reaction_measurements: tuple[CuratedKineticMeasurement, ...],
    network: FullNetwork,
    species_by_id: dict[str, SpeciesSpecification],
    *,
    sibling_count: int,
) -> tuple[ParameterSpecification, ...]:
    if assignment.kinetic_law_type is KineticLawType.UNASSIGNED:
        return ()

    evidence = _evidence_for(assignment, reaction_measurements, sibling_count=sibling_count)

    if assignment.kinetic_law_type is KineticLawType.MASS_ACTION:
        return _declare_mass_action(assignment, evidence)
    if assignment.kinetic_law_type is KineticLawType.REVERSIBLE_MASS_ACTION:
        return _declare_reversible_mass_action(assignment, evidence)
    if assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        return _declare_michaelis_menten(assignment, evidence, reactant_compound_ids)
    if assignment.kinetic_law_type is KineticLawType.HILL:
        return _declare_hill(assignment, evidence)
    if assignment.kinetic_law_type is KineticLawType.CUSTOM:
        return _declare_custom(assignment, evidence)

    raise ParameterReferenceError(
        f"declare_parameters has no declaration policy for kinetic_law_type="
        f"{assignment.kinetic_law_type!r} (assignment_id={assignment.assignment_id!r})"
    )


def declare_parameters(
    assignments: KineticLawAssignmentSet, network: FullNetwork
) -> ParameterDeclarationSet:
    """Declare every parameter Increment 4's kinetic-law assignments require.

    Answers only "what parameters must exist for this model" -- never
    "what are the best values" (Agent 4's job). See
    ``docs/08_parameter_declaration_initialization.md`` §2.
    """
    require_kinetic_law_assignment_set(assignments)
    require_full_network(network)
    if assignments.network_id != network.network_id:
        raise ParameterReferenceError(
            f"assignments.network_id ({assignments.network_id!r}) does not match "
            f"network.network_id ({network.network_id!r})"
        )

    measurements_by_reaction: dict[str, list[CuratedKineticMeasurement]] = {}
    for measurement in network.kinetic_measurements:
        if measurement.reaction_id is not None:
            measurements_by_reaction.setdefault(measurement.reaction_id, []).append(measurement)
    species_by_id = {species.species_id: species for species in network.species}

    sibling_counts: dict[str, int] = {}
    for assignment in assignments.assignments:
        sibling_counts[assignment.reaction_id] = sibling_counts.get(assignment.reaction_id, 0) + 1

    specs: list[ParameterSpecification] = []
    for assignment in sorted(assignments.assignments, key=lambda a: a.assignment_id):
        specs.extend(
            _declare_for_assignment(
                assignment,
                tuple(measurements_by_reaction.get(assignment.reaction_id, ())),
                network,
                species_by_id,
                sibling_count=sibling_counts[assignment.reaction_id],
            )
        )

    declaration_set = ParameterDeclarationSet(
        network_id=assignments.network_id,
        kinetic_law_policy_version=assignments.kinetic_law_policy_version,
        parameter_policy_version=PARAMETER_DECLARATION_POLICY_VERSION,
        parameter_specifications=tuple(specs),
    )

    valid_assignment_ids = {a.assignment_id for a in assignments.assignments}
    for spec in declaration_set.parameter_specifications:
        if spec.kinetic_law_assignment_id not in valid_assignment_ids:
            raise ParameterReferenceError(
                f"declared parameter {spec.parameter_id!r} names "
                f"kinetic_law_assignment_id={spec.kinetic_law_assignment_id!r}, which does not "
                "match any assignment in the source KineticLawAssignmentSet"
            )
        if spec.source is ParameterSource.CALIBRATED:
            raise ParameterReferenceError(
                f"declared parameter {spec.parameter_id!r} uses ParameterSource.CALIBRATED -- "
                "reserved exclusively for future Agent 4 feedback, never assigned here"
            )

    return declaration_set


__all__ = ["declare_parameters"]
