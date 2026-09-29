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

import dataclasses

from app.agent2.kinetics.types import (
    KineticLawAssignment,
    KineticLawAssignmentSet,
    KineticLawReasonCode,
)
from app.agent2.parameters import policy, reconstruction
from app.agent2.parameters.errors import ParameterReferenceError
from app.agent2.parameters.heuristic_defaults import ParameterKind
from app.agent2.parameters.initializer import (
    Initialization,
    initialize_from_evidence,
    initialize_with_fallback,
)
from app.agent2.parameters.types import MicroscopicConstraint, ParameterDeclarationSet
from app.agent2.parameters.validation import (
    require_full_network,
    require_kinetic_law_assignment_set,
)
from app.agent2.quantitative_context.types import QuantitativeContextResolutionSet
from app.agent2.reversibility import effective_reversible
from app.agent2.types import (
    CuratedKineticMeasurement,
    EnzymeConcentration,
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
    """Mirrors ``app.agent2.kinetics.selector._matches_context`` exactly (a private
    implementation detail of that module, not exported -- see ``_evidence_for``'s own
    docstring), including its plural-``protein_ids``-membership matching for a
    protein-general assignment ("Isozyme-Aware Catalytic Context Resolution" increment;
    real regression: with isozyme contexts no longer collapsed into one, this function's
    own now-frequently-exercised legacy singular-``protein_id``-equality check was
    silently dropping real evidence -- e.g. a measurement whose legacy ``protein_id``
    names a different protein than the one its own authoritative ``protein_ids`` also,
    correctly, names as this reaction's actual catalyst -- from reaching parameter
    declaration, even though the very same measurement had already, correctly, reached
    that catalyst's own kinetic-law assignment).
    """
    if assignment.enzyme_state_id is not None:
        return measurement.enzyme_state_id == assignment.enzyme_state_id
    if assignment.protein_id is not None:
        return (
            assignment.protein_id in measurement.protein_ids
            and measurement.enzyme_state_id is None
        )
    if assignment.complex_id is not None:
        return (
            measurement.complex_id == assignment.complex_id
            and measurement.enzyme_state_id is None
        )
    return (
        measurement.enzyme_state_id is None
        and not measurement.protein_ids
        and measurement.complex_id is None
    )


def _protein_id_for_assignment(
    assignment: KineticLawAssignment, network: FullNetwork
) -> str | None:
    """The single protein this assignment's own catalytic context names, if any --
    ``assignment.protein_id`` directly, or (for a state-specific assignment) the protein the
    named ``CuratedEnzymeState`` itself belongs to. ``None`` for a complex-catalyzed or
    uncatalyzed assignment -- `app.agent2.quantitative_context` resolves enzyme
    concentrations at the protein level only (never for a complex as a whole), so this
    function never invents a stand-in for that case.
    """
    if assignment.protein_id is not None:
        return assignment.protein_id
    if assignment.enzyme_state_id is not None:
        for state in network.enzyme_states:
            if state.id == assignment.enzyme_state_id:
                return state.protein_id
    return None


def _enzyme_concentration_for_assignment(
    assignment: KineticLawAssignment,
    network: FullNetwork,
    enzyme_concentrations_by_protein_id: dict[str, EnzymeConcentration],
) -> EnzymeConcentration | None:
    protein_id = _protein_id_for_assignment(assignment, network)
    if protein_id is None:
        return None
    return enzyme_concentrations_by_protein_id.get(protein_id)


def _anchored_km_initialization(
    km_evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
    network: FullNetwork,
) -> Initialization:
    """A single-substrate-anchored ``Km`` ``Initialization``, for use only as an internal
    input to Derivations C/D (never itself declared as a ``ParameterSpecification`` outside
    `_declare_michaelis_menten`, which declares its own per-substrate `Km` slots
    separately).

    For a single-reactant context, an untagged ``Km`` measurement is assumed to name that
    one reactant (mirrors `_declare_michaelis_menten`'s own identical policy). For a multi-
    reactant context, only a `Km` explicitly and unambiguously naming exactly one of this
    reaction's own reactant compounds is usable (mirrors
    `app.agent2.kinetics.selector`'s own `SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_
    APPROXIMATION` eligibility rule exactly: never an untagged `Km` -- which reactant would
    it even be? -- and never one naming a compound this reaction does not have as a
    reactant) -- two or more distinct anchored compounds is also treated as "nothing usable"
    here, since Derivations C/D both need exactly one `Km` value for exactly one substrate.
    """
    if len(reactant_compound_ids) == 1:
        matches = tuple(
            m
            for m in km_evidence
            if m.compound_id == reactant_compound_ids[0] or m.compound_id is None
        )
    else:
        anchored = tuple(m for m in km_evidence if m.compound_id in reactant_compound_ids)
        anchored_compound_ids = {m.compound_id for m in anchored}
        matches = anchored if len(anchored_compound_ids) == 1 else ()
    return initialize_with_fallback(matches, kind=ParameterKind.CONCENTRATION, network=network)


def _reconstruct_k_eff_for_context(
    evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
    enzyme_concentration: EnzymeConcentration | None,
    network: FullNetwork,
    *,
    molecularity: int,
) -> Initialization | None:
    """Derivation C, pre-computed for a mass-action-style ``k``/``kf`` slot's own
    ``macro_reconstruction`` argument (Derivation B is attempted first, internally, for the
    ``kcat`` half of the ratio -- mirrors the design doc's own step-2-before-step-3+
    ordering). Returns ``None`` immediately for any molecularity other than 2 -- see
    `reconstruction.reconstruct_k_eff_from_kcat_and_km`'s own docstring for why.
    """
    if molecularity != 2:
        return None
    kcat_matches = policy.measurements_of_kind(evidence, policy.KCAT_TYPES)
    vmax_matches = policy.measurements_of_kind(evidence, policy.VMAX_TYPES)
    macro_kcat = reconstruction.resolve_kcat_with_reconstruction(
        kcat_matches, vmax_matches, enzyme_concentration
    )
    kcat_initialization = initialize_with_fallback(
        kcat_matches,
        kind=ParameterKind.RATE_FIRST_ORDER,
        macro_reconstruction=macro_kcat,
        network=network,
    )
    km_initialization = _anchored_km_initialization(
        policy.measurements_of_kind(evidence, policy.KM_TYPES), reactant_compound_ids, network
    )
    return reconstruction.reconstruct_k_eff_from_kcat_and_km(
        kcat_initialization, km_initialization, molecularity=molecularity
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
    ``app.agent2.kinetics.selector``, not exported) that module's own
    evidence-gathering rule: when this assignment is the **sole**
    catalytic context for its reaction (``sibling_count == 1`` -- true
    for a no-catalyst reaction or a single specific catalyst), every
    measurement for the reaction is fair game, tagged or not -- there is
    no sibling context it could rightfully belong to instead. When more
    than one distinct context exists for the reaction (multiple catalytic
    enzyme states, or two or more isozymes -- always kept separate as of
    the "Isozyme-Aware Catalytic Context Resolution" increment,
    regardless of whether their evidence happens to agree), each context
    only ever sees measurements tagged with its own exact identity -- a
    measurement tagged for one state/protein/complex is never visible to a sibling
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


def _reaction_molecularity(
    network: FullNetwork, reaction_id: str, role: ParticipantRole
) -> int:
    """The total stoichiometry of every participant with the given role -- the reaction
    order a mass-action rate constant's own dimensionality depends on (Heuristic Simulation
    Parameter Initialization increment: ``[k] = nM^(1-n) * s^-1``, ``n`` the *reactant*
    molecularity for a forward rate constant, the *product* molecularity for a reverse one).
    Never rounded or approximated -- stoichiometry is already schema-guaranteed to be a
    whole number (``ReactionParticipantSpecification``'s own docstring); this only sums it.
    """
    (reaction,) = (r for r in network.reactions if r.reaction_id == reaction_id)
    total = sum(
        p.stoichiometry for p in reaction.participants if p.role is role
    )
    return int(total)


def _declare_mass_action(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
    enzyme_concentration: EnzymeConcentration | None,
    network: FullNetwork,
) -> tuple[ParameterSpecification, ...]:
    molecularity = _reaction_molecularity(network, assignment.reaction_id, ParticipantRole.REACTANT)
    if _is_tentative(assignment):
        # Increment 5 instructions, Step 16: never attempt curated (or, since the Heuristic
        # Simulation Parameter Initialization increment, AI-predicted) mapping for a tentative
        # default -- the *mechanism itself* is unconfirmed, so no real evidentiary value could
        # justifiably initialize its rate constant even if one happens to exist for this
        # context (doing so would misrepresent that evidence as validating an assumed,
        # unconfirmed mechanism). This is narrower than the Heuristic increment's own §7
        # boundary, which excludes only ``expression=None``, an unsupported ``KineticLawType``
        # (``CUSTOM``), or no declared parameter structure -- none of which is true here: the
        # law type is still ``MASS_ACTION``, its expression is built, and its one ``k`` slot is
        # fully declared. A *heuristic* value makes no evidentiary claim at all (disclosed as
        # ``HEURISTIC_INITIALIZATION``, never ``CURATED``/``LITERATURE_DERIVED``/
        # ``AI_PREDICTED``), so it carries none of the original concern and is still assigned
        # here -- passing an empty evidence tuple so ``initialize_with_fallback`` skips
        # straight past both evidence tiers to its own heuristic-default tier. The generic
        # heuristic/no-match uncertainty text it returns says nothing about *why* no evidence
        # was even attempted, so it is replaced with one that names the tentative mechanism
        # explicitly, preserving every other field verbatim. Identifiability-Aware
        # Macroscopic-to-Microscopic Kinetic Reconstruction increment: a macro-kinetics
        # reconstruction is no less an evidentiary claim than curated/AI-predicted evidence,
        # so it is excluded here for the identical reason -- never attempted for a tentative,
        # unconfirmed mechanism.
        tentative_initialization = initialize_with_fallback(
            (), kind=ParameterKind.MASS_ACTION_RATE, molecularity=molecularity, network=network
        )
        tentative_initialization = dataclasses.replace(
            tentative_initialization,
            uncertainty_text=(
                "Tentative mass-action default (TENTATIVE_MASS_ACTION_DEFAULT): the "
                "underlying mechanism is unconfirmed, so no curated or AI-predicted value is "
                "used even if one exists for this context. "
                + (tentative_initialization.uncertainty_text or "")
            ).strip(),
        )
        return (
            _spec_from_initialization(
                "k", assignment=assignment, initialization=tentative_initialization
            ),
        )
    matches = policy.measurements_of_kind(evidence, policy.RATE_CONSTANT_TYPES)
    # Derivation C (Identifiability-Aware Macroscopic-to-Microscopic Kinetic
    # Reconstruction increment): an effective second-order k_eff = kcat/Km, dimensionally
    # valid only when this reaction's own reactant molecularity is exactly 2 -- see
    # `_reconstruct_k_eff_for_context`'s own docstring.
    macro_reconstruction = _reconstruct_k_eff_for_context(
        evidence, reactant_compound_ids, enzyme_concentration, network, molecularity=molecularity
    )
    return (
        _spec_from_initialization(
            "k",
            assignment=assignment,
            initialization=initialize_with_fallback(
                matches,
                kind=ParameterKind.MASS_ACTION_RATE,
                molecularity=molecularity,
                macro_reconstruction=macro_reconstruction,
                network=network,
            ),
        ),
    )


def _declare_reversible_mass_action(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
    enzyme_concentration: EnzymeConcentration | None,
    network: FullNetwork,
) -> tuple[ParameterSpecification, ...]:
    forward = policy.measurements_of_kind(evidence, policy.FORWARD_RATE_TYPES)
    reverse = policy.measurements_of_kind(evidence, policy.REVERSE_RATE_TYPES)
    # Forward and reverse molecularity are computed independently -- a reaction need not be
    # symmetric (e.g. A + B <=> C is bimolecular forward, unimolecular reverse). Each
    # direction's own rate constant is heuristically initialized purely from its own
    # molecularity; the two are never related through a fabricated equilibrium constant
    # (Increment instructions §5: "Do not claim the resulting pair is an experimentally
    # known equilibrium").
    forward_molecularity = _reaction_molecularity(
        network, assignment.reaction_id, ParticipantRole.REACTANT
    )
    reverse_molecularity = _reaction_molecularity(
        network, assignment.reaction_id, ParticipantRole.PRODUCT
    )
    # Derivation C: only ever attempted for the forward (substrate-binding) direction --
    # kcat/Km says nothing about the reverse rate kr (design doc §2.1/§3), so `reverse`
    # never receives a macro_reconstruction here.
    forward_macro_reconstruction = _reconstruct_k_eff_for_context(
        evidence,
        reactant_compound_ids,
        enzyme_concentration,
        network,
        molecularity=forward_molecularity,
    )
    return (
        _spec_from_initialization(
            "kf",
            assignment=assignment,
            initialization=initialize_with_fallback(
                forward,
                kind=ParameterKind.MASS_ACTION_RATE,
                molecularity=forward_molecularity,
                macro_reconstruction=forward_macro_reconstruction,
                network=network,
            ),
        ),
        _spec_from_initialization(
            "kr",
            assignment=assignment,
            initialization=initialize_with_fallback(
                reverse,
                kind=ParameterKind.MASS_ACTION_RATE,
                molecularity=reverse_molecularity,
                network=network,
            ),
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
    enzyme_concentration: EnzymeConcentration | None,
    network: FullNetwork,
) -> tuple[tuple[ParameterSpecification, ...], tuple[MicroscopicConstraint, ...]]:
    # Derivation B (Identifiability-Aware Macroscopic-to-Microscopic Kinetic
    # Reconstruction increment): kcat = Vmax / [E]_total, attempted only when direct/AI-
    # predicted kcat evidence is genuinely absent (the "macro_reconstruction" tier is only
    # ever consulted by initialize_with_fallback after both stronger tiers return empty).
    kcat_evidence = policy.measurements_of_kind(evidence, policy.KCAT_TYPES)
    vmax_evidence = policy.measurements_of_kind(evidence, policy.VMAX_TYPES)
    macro_kcat = reconstruction.resolve_kcat_with_reconstruction(
        kcat_evidence, vmax_evidence, enzyme_concentration
    )
    kcat_initialization = initialize_with_fallback(
        kcat_evidence,
        # kcat (a turnover number) is always first-order regardless of the reaction's own
        # molecularity -- never molecularity-dependent the way a mass-action rate constant
        # is.
        kind=ParameterKind.RATE_FIRST_ORDER,
        macro_reconstruction=macro_kcat,
        network=network,
    )
    kcat_spec = _spec_from_initialization(
        "kcat", assignment=assignment, initialization=kcat_initialization
    )
    specs = [kcat_spec]

    km_evidence = policy.measurements_of_kind(evidence, policy.KM_TYPES)
    single_substrate = len(reactant_compound_ids) == 1
    km_initializations_by_compound: dict[str, Initialization] = {}
    km_specs_by_compound: dict[str, ParameterSpecification] = {}
    for compound_id in reactant_compound_ids:
        substrate_matches = tuple(
            m
            for m in km_evidence
            if m.compound_id == compound_id or (m.compound_id is None and single_substrate)
        )
        km_initialization = initialize_with_fallback(
            substrate_matches, kind=ParameterKind.CONCENTRATION, network=network
        )
        km_spec = _spec_from_initialization(
            "Km", assignment=assignment, initialization=km_initialization, substrate_id=compound_id
        )
        specs.append(km_spec)
        km_initializations_by_compound[compound_id] = km_initialization
        km_specs_by_compound[compound_id] = km_spec
    # Ki is deliberately never declared here (Increment 5 instructions, Step 8:
    # "Do not invent inhibition constants") -- plain Michaelis-Menten has no inhibition term.

    constraints: list[MicroscopicConstraint] = []
    if single_substrate:
        # Derivation D: preserve Km=(kr+kcat)/kf as a disclosed constraint, never a chosen
        # (kf, kr) point -- only meaningful for the single-substrate E+S<=>ES->E+P
        # mechanism (design doc §2.1/§2.2's own multi-substrate scope exclusion).
        (only_compound_id,) = reactant_compound_ids
        constraint = reconstruction.classify_km_kcat_constraint(
            kcat_initialization,
            km_initializations_by_compound[only_compound_id],
            reaction_id=assignment.reaction_id,
            kinetic_law_assignment_id=assignment.assignment_id,
            kcat_parameter_id=kcat_spec.parameter_id,
            km_parameter_id=km_specs_by_compound[only_compound_id].parameter_id,
        )
        if constraint is not None:
            constraints.append(constraint)

    if len(reactant_compound_ids) > 1:
        # Executable Rate-Law Fallback increment: a genuinely multi-substrate assignment's
        # kcat/Km parameters (above) can never combine into one justified algebraic
        # expression (app.agent2.model_specification.mapping.build_expression_and_species),
        # so that module substitutes a generic, disclosed, non-mechanistic mass-action-style
        # simulation fallback there instead -- this is exactly the minimal extra parameter
        # structure that fallback needs, appended *after* kcat/Km (never replacing or
        # reordering them; both real-evidence-eligible slots remain fully declared and
        # preserved even though the fallback expression never references them). Reuses the
        # same evidence this assignment's kcat/Km slots already saw -- a real curated/
        # AI-predicted rate-constant measurement (K/KF/KR) for this exact context still takes
        # precedence over a heuristic guess, exactly as everywhere else in this module; only
        # in the (expected, common) case no such measurement exists does this fall through to
        # HEURISTIC_INITIALIZATION (or, since this increment, DERIVED_FROM_MACRO_KINETICS
        # Derivation C, when this reaction is exactly bimolecular).
        specs.extend(
            _declare_multi_substrate_mm_fallback(
                assignment, evidence, reactant_compound_ids, enzyme_concentration, network
            )
        )
    return tuple(specs), tuple(constraints)


def _declare_multi_substrate_mm_fallback(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
    enzyme_concentration: EnzymeConcentration | None,
    network: FullNetwork,
) -> tuple[ParameterSpecification, ...]:
    """The minimal mass-action-style rate constant(s) a genuinely multi-substrate
    Michaelis-Menten assignment's simulation fallback needs -- one ``k`` if the reaction is
    (curated or assumed) irreversible, or independently-molecularity-derived ``kf``/``kr`` if
    it is (curated or assumed) reversible, mirroring ``_declare_reversible_mass_action``'s own
    policy exactly (§5/§7 of the increment instructions: never relate the two through a
    fabricated equilibrium constant, never invent a reverse constant the reaction's own
    effective reversibility does not call for).
    """
    forward_molecularity = _reaction_molecularity(
        network, assignment.reaction_id, ParticipantRole.REACTANT
    )
    # Derivation C: real, if narrow, applicability here -- the task's own motivating real
    # example (a two-reactant Michaelis-Menten assignment, e.g. malonyl-CoA:[acp]
    # S-malonyltransferase) is exactly this fallback's own primary real-world case, and
    # forward_molecularity == 2 there matches k_eff=kcat/Km's own dimensional requirement
    # exactly (see `reconstruction.reconstruct_k_eff_from_kcat_and_km`'s docstring). Never
    # attempted for 3+ reactants (task's own explicit "do not apply generically to
    # arbitrary multi-reactant reactions") -- `_reconstruct_k_eff_for_context` itself
    # already enforces this, this call site does not need its own separate check.
    forward_macro_reconstruction = _reconstruct_k_eff_for_context(
        evidence,
        reactant_compound_ids,
        enzyme_concentration,
        network,
        molecularity=forward_molecularity,
    )
    if not effective_reversible(_reaction_reversible(network, assignment.reaction_id)):
        matches = policy.measurements_of_kind(evidence, policy.RATE_CONSTANT_TYPES)
        return (
            _spec_from_initialization(
                "k",
                assignment=assignment,
                initialization=initialize_with_fallback(
                    matches,
                    kind=ParameterKind.MASS_ACTION_RATE,
                    molecularity=forward_molecularity,
                    macro_reconstruction=forward_macro_reconstruction,
                    network=network,
                ),
            ),
        )
    reverse_molecularity = _reaction_molecularity(
        network, assignment.reaction_id, ParticipantRole.PRODUCT
    )
    forward = policy.measurements_of_kind(evidence, policy.FORWARD_RATE_TYPES)
    reverse = policy.measurements_of_kind(evidence, policy.REVERSE_RATE_TYPES)
    return (
        _spec_from_initialization(
            "kf",
            assignment=assignment,
            initialization=initialize_with_fallback(
                forward,
                kind=ParameterKind.MASS_ACTION_RATE,
                molecularity=forward_molecularity,
                macro_reconstruction=forward_macro_reconstruction,
                network=network,
            ),
        ),
        _spec_from_initialization(
            "kr",
            assignment=assignment,
            initialization=initialize_with_fallback(
                reverse,
                kind=ParameterKind.MASS_ACTION_RATE,
                molecularity=reverse_molecularity,
                network=network,
            ),
        ),
    )


def _reaction_reversible(network: FullNetwork, reaction_id: str) -> bool | None:
    (reaction,) = (r for r in network.reactions if r.reaction_id == reaction_id)
    return reaction.reversible


def _declare_hill(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    network: FullNetwork,
) -> tuple[ParameterSpecification, ...]:
    return (
        _spec_from_initialization(
            "Vmax",
            assignment=assignment,
            initialization=initialize_with_fallback(
                policy.measurements_of_kind(evidence, policy.VMAX_TYPES),
                kind=ParameterKind.FLUX,
                network=network,
            ),
        ),
        _spec_from_initialization(
            "Km",
            assignment=assignment,
            initialization=initialize_with_fallback(
                policy.measurements_of_kind(evidence, policy.KM_TYPES),
                kind=ParameterKind.CONCENTRATION,
                network=network,
            ),
        ),
        _spec_from_initialization(
            "n",
            assignment=assignment,
            # A Hill coefficient has no centralized heuristic default (Increment
            # instructions §4 names only concentration/rate/flux/mass-action-rate
            # families as supported) -- ParameterKind.UNSUPPORTED always falls through to
            # the plain, undecorated PLACEHOLDER, never an invented convention.
            initialization=initialize_with_fallback(
                policy.measurements_of_kind(evidence, policy.HILL_COEFFICIENT_TYPES),
                kind=ParameterKind.UNSUPPORTED,
                network=network,
            ),
        ),
    )


def _declare_custom(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    network: FullNetwork,
) -> tuple[ParameterSpecification, ...]:
    specs = []
    for prefix, family in _CUSTOM_FAMILIES:
        matches = policy.measurements_of_kind(evidence, family)
        if matches:
            specs.append(
                _spec_from_initialization(
                    prefix,
                    assignment=assignment,
                    initialization=initialize_from_evidence(matches, network=network),
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
    enzyme_concentrations_by_protein_id: dict[str, EnzymeConcentration],
    *,
    sibling_count: int,
) -> tuple[tuple[ParameterSpecification, ...], tuple[MicroscopicConstraint, ...]]:
    if assignment.kinetic_law_type is KineticLawType.UNASSIGNED:
        return (), ()

    evidence = _evidence_for(assignment, reaction_measurements, sibling_count=sibling_count)
    enzyme_concentration = _enzyme_concentration_for_assignment(
        assignment, network, enzyme_concentrations_by_protein_id
    )

    if assignment.kinetic_law_type is KineticLawType.MASS_ACTION:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        return (
            _declare_mass_action(
                assignment, evidence, reactant_compound_ids, enzyme_concentration, network
            ),
            (),
        )
    if assignment.kinetic_law_type is KineticLawType.REVERSIBLE_MASS_ACTION:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        return (
            _declare_reversible_mass_action(
                assignment, evidence, reactant_compound_ids, enzyme_concentration, network
            ),
            (),
        )
    if assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        return _declare_michaelis_menten(
            assignment, evidence, reactant_compound_ids, enzyme_concentration, network
        )
    if assignment.kinetic_law_type is KineticLawType.HILL:
        return _declare_hill(assignment, evidence, network), ()
    if assignment.kinetic_law_type is KineticLawType.CUSTOM:
        return _declare_custom(assignment, evidence, network), ()

    raise ParameterReferenceError(
        f"declare_parameters has no declaration policy for kinetic_law_type="
        f"{assignment.kinetic_law_type!r} (assignment_id={assignment.assignment_id!r})"
    )


def declare_parameters(
    assignments: KineticLawAssignmentSet,
    network: FullNetwork,
    enzyme_concentrations: QuantitativeContextResolutionSet | None = None,
) -> ParameterDeclarationSet:
    """Declare every parameter Increment 4's kinetic-law assignments require.

    Answers only "what parameters must exist for this model" -- never
    "what are the best values" (Agent 4's job). See
    ``docs/08_parameter_declaration_initialization.md`` §2.

    ``enzyme_concentrations`` (Identifiability-Aware Macroscopic-to-Microscopic Kinetic
    Reconstruction increment) is optional and defaults to ``None`` -- every existing call
    site continues to declare identical parameters (no ``DERIVED_FROM_MACRO_KINETICS``
    value is ever produced without it). When supplied, its own ``network_id`` is cross-
    checked against ``network.network_id`` (mirroring `assignments.network_id`'s own
    identical check immediately below), and its resolved ``EnzymeConcentration`` records
    are made available, by protein id, to Derivations B/C wherever a declaration function's
    own catalytic context names a matching protein.
    """
    require_kinetic_law_assignment_set(assignments)
    require_full_network(network)
    if assignments.network_id != network.network_id:
        raise ParameterReferenceError(
            f"assignments.network_id ({assignments.network_id!r}) does not match "
            f"network.network_id ({network.network_id!r})"
        )
    if enzyme_concentrations is not None and not isinstance(
        enzyme_concentrations, QuantitativeContextResolutionSet
    ):
        raise ParameterReferenceError(
            "declare_parameters requires enzyme_concentrations to be a "
            f"QuantitativeContextResolutionSet or None, got {enzyme_concentrations!r}"
        )
    if enzyme_concentrations is not None and enzyme_concentrations.network_id != network.network_id:
        raise ParameterReferenceError(
            f"enzyme_concentrations.network_id ({enzyme_concentrations.network_id!r}) does "
            f"not match network.network_id ({network.network_id!r})"
        )
    enzyme_concentrations_by_protein_id: dict[str, EnzymeConcentration] = (
        {ec.protein_id: ec for ec in enzyme_concentrations.enzyme_concentrations}
        if enzyme_concentrations is not None
        else {}
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
    constraints: list[MicroscopicConstraint] = []
    for assignment in sorted(assignments.assignments, key=lambda a: a.assignment_id):
        assignment_specs, assignment_constraints = _declare_for_assignment(
            assignment,
            tuple(measurements_by_reaction.get(assignment.reaction_id, ())),
            network,
            species_by_id,
            enzyme_concentrations_by_protein_id,
            sibling_count=sibling_counts[assignment.reaction_id],
        )
        specs.extend(assignment_specs)
        constraints.extend(assignment_constraints)

    declaration_set = ParameterDeclarationSet(
        network_id=assignments.network_id,
        kinetic_law_policy_version=assignments.kinetic_law_policy_version,
        parameter_policy_version=PARAMETER_DECLARATION_POLICY_VERSION,
        parameter_specifications=tuple(specs),
        microscopic_constraints=tuple(constraints),
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
