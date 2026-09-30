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
from collections import defaultdict

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
            assignment.protein_id in measurement.protein_ids and measurement.enzyme_state_id is None
        )
    if assignment.complex_id is not None:
        return (
            measurement.complex_id == assignment.complex_id and measurement.enzyme_state_id is None
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


def _ambiguous_state_parent_keys(
    assignments: KineticLawAssignmentSet, network: FullNetwork
) -> frozenset[tuple[str, str]]:
    """``(reaction_id, protein_id)`` pairs where two or more distinct enzyme-state
    contexts on the same reaction share the same parent protein (Multi-Context Catalytic
    Rate Composition increment, Stage 1).

    A derived ``EnzymeConcentration`` represents one protein's own total,
    undifferentiated abundance -- real only once per protein, never once per modification
    state. Handing the identical full concentration independently to two or more of that
    protein's own states on the same reaction (e.g. ``E``/``E_P``) would silently double-
    (or N-times-) count it -- this repository has no real state-population/conservation
    data to split it correctly (Stage 2's own job: state-interconversion dynamics), so it
    is withheld for exactly these keys instead of guessed at. A protein/complex-general
    context, or a single, unambiguous state context, is never affected.
    """
    state_protein_by_id = {state.id: state.protein_id for state in network.enzyme_states}
    states_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for assignment in assignments.assignments:
        if assignment.enzyme_state_id is None:
            continue
        protein_id = state_protein_by_id.get(assignment.enzyme_state_id)
        if protein_id is None:
            continue
        states_by_key[(assignment.reaction_id, protein_id)].add(assignment.enzyme_state_id)
    return frozenset(key for key, states in states_by_key.items() if len(states) > 1)


def _enzyme_concentration_for_assignment(
    assignment: KineticLawAssignment,
    network: FullNetwork,
    enzyme_concentrations_by_protein_id: dict[str, EnzymeConcentration],
    ambiguous_state_parent_keys: frozenset[tuple[str, str]],
    enzyme_concentrations_by_state_id: dict[str, EnzymeConcentration],
) -> EnzymeConcentration | None:
    if assignment.enzyme_state_id is not None:
        # Multi-Context Catalytic Rate Composition increment, Stage 2: a real, resolved
        # state-level concentration (app.agent2.enzyme_state_dynamics) takes precedence
        # over Stage 1's own blanket ambiguous-sibling withholding below -- it is exactly
        # this state's own share of the parent pool, never the full undifferentiated total,
        # so handing it to this one context never double-counts a sibling's identical
        # share (each sibling gets its own, distinct entry in this same dict, if resolved
        # at all).
        state_concentration = enzyme_concentrations_by_state_id.get(assignment.enzyme_state_id)
        if state_concentration is not None:
            return state_concentration
    protein_id = _protein_id_for_assignment(assignment, network)
    if protein_id is None:
        return None
    if (
        assignment.enzyme_state_id is not None
        and (assignment.reaction_id, protein_id) in ambiguous_state_parent_keys
    ):
        return None
    return enzyme_concentrations_by_protein_id.get(protein_id)


def _substrate_matches(
    evidence_of_kind: tuple[CuratedKineticMeasurement, ...],
    compound_id: str,
    *,
    single_substrate: bool,
) -> tuple[CuratedKineticMeasurement, ...]:
    """Every measurement of one already-recognized kind (Km, kcat, ...) that legitimately
    supports ``compound_id``'s own substrate-specific kinetic-parameter concept for this
    catalytic context (Substrate-Specific Kinetic Parameterization for Promiscuous
    Reactions increment): an exact ``compound_id`` match always, plus untagged
    (``compound_id is None``) evidence only when this reaction has exactly one reactant at
    all -- the only context in which "unspecified substrate" can unambiguously mean "this
    one reactant" (task's own "[use generic evidence] only where existing policy supports
    generic applicability"; for two or more reactants, an untagged measurement could name
    any of them and is never assumed to be this one -- see ``_declare_kcat_specs``'s own
    handling of leftover untagged evidence there).

    The result is intentionally handed to ``initialize_with_fallback`` with
    ``already_substrate_scoped=True``: for the single-reactant case this set may contain
    both a real ``compound_id`` and ``None``-tagged entries together, which
    ``consolidate_by_substrate`` would otherwise wrongly re-split into two spurious
    "different substrate" concepts (the real Pilot 4 regression this increment fixes).
    """
    return tuple(
        m
        for m in evidence_of_kind
        if m.compound_id == compound_id or (m.compound_id is None and single_substrate)
    )


def _anchor_compound_id(
    km_evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
) -> str | None:
    """The single reactant compound this catalytic context's own curated ``Km`` evidence
    unambiguously anchors to, or ``None`` when no such single anchor exists.

    A single-reactant context is always its own anchor (evidence or not -- there is only
    ever one candidate). A multi-reactant context anchors only when exactly one of its own
    declared reactant compounds has any ``Km`` evidence naming it at all (mirrors
    `app.agent2.kinetics.selector`'s own `SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_
    APPROXIMATION` eligibility rule exactly) -- never an untagged `Km` for a multi-reactant
    context (which reactant would it even be?), and never a `Km` naming a compound this
    reaction does not have as a reactant at all (a real, observed case: a promiscuous
    catalyst's own curated evidence naming a product, or a compound belonging to a
    chemically related but structurally distinct reaction this coarse model does not
    itself represent -- excluded here, never guessed onto this reaction's own species).
    Two or more distinct anchored compounds is also "no anchor" -- Derivation C/D and the
    ``kcat``/``Km`` pairing both need exactly one shared substrate concept.
    """
    if len(reactant_compound_ids) == 1:
        return reactant_compound_ids[0]
    anchored_ids = {m.compound_id for m in km_evidence if m.compound_id in reactant_compound_ids}
    if len(anchored_ids) == 1:
        return next(iter(anchored_ids))
    return None


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

    **Never pairs ``kcat`` from one substrate with ``Km`` from another** (Substrate-
    Specific Kinetic Parameterization for Promiscuous Reactions increment, task's own
    central rule): both sides are restricted to the identical anchor compound
    (``_anchor_compound_id``, computed once from this context's own ``Km`` evidence) before
    either is ever resolved -- real Pilot 4 regression this fixes: reaction
    ``10c1fab0-...`` (palmitate:CoA ligase), where one real ``kcat`` measurement is tagged
    with this reaction's own genuine reactant substrate and a second, equally real
    ``kcat`` measurement is tagged with this reaction's own *product* (the reverse-
    direction "substrate") -- the second is correctly excluded here, never merged with, or
    treated as contradicting, the first.
    """
    if molecularity != 2:
        return None
    km_evidence = policy.measurements_of_kind(evidence, policy.KM_TYPES)
    anchor = _anchor_compound_id(km_evidence, reactant_compound_ids)
    if anchor is None:
        return None
    single_substrate = len(reactant_compound_ids) == 1
    km_matches = _substrate_matches(km_evidence, anchor, single_substrate=single_substrate)
    kcat_evidence = policy.measurements_of_kind(evidence, policy.KCAT_TYPES)
    # Unlike Km/Ki (a property of one specific substrate's own binding), kcat is a
    # property of the catalytic turnover itself -- an *untagged* kcat measurement makes no
    # substrate-specific claim at all, so it is never treated as ambiguous about which
    # reactant it concerns the way an untagged Km genuinely would be for 2+ reactants; it is
    # always compatible with the one substrate Km itself anchors to
    # (`_substrate_matches(..., single_substrate=True)` unconditionally, regardless of this
    # reaction's own real reactant count). Only kcat evidence explicitly tagged to a
    # *different* real compound is excluded -- a genuine, real competing substrate claim.
    kcat_matches = _substrate_matches(kcat_evidence, anchor, single_substrate=True)
    vmax_matches = policy.measurements_of_kind(evidence, policy.VMAX_TYPES)
    macro_kcat = reconstruction.resolve_kcat_with_reconstruction(
        kcat_matches, vmax_matches, enzyme_concentration
    )
    kcat_initialization = initialize_with_fallback(
        kcat_matches,
        kind=ParameterKind.RATE_FIRST_ORDER,
        macro_reconstruction=macro_kcat,
        network=network,
        already_substrate_scoped=True,
    )
    km_initialization = initialize_with_fallback(
        km_matches,
        kind=ParameterKind.CONCENTRATION,
        network=network,
        already_substrate_scoped=True,
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


def _reaction_molecularity(network: FullNetwork, reaction_id: str, role: ParticipantRole) -> int:
    """The total stoichiometry of every participant with the given role -- the reaction
    order a mass-action rate constant's own dimensionality depends on (Heuristic Simulation
    Parameter Initialization increment: ``[k] = nM^(1-n) * s^-1``, ``n`` the *reactant*
    molecularity for a forward rate constant, the *product* molecularity for a reverse one).
    Never rounded or approximated -- stoichiometry is already schema-guaranteed to be a
    whole number (``ReactionParticipantSpecification``'s own docstring); this only sums it.
    """
    (reaction,) = (r for r in network.reactions if r.reaction_id == reaction_id)
    total = sum(p.stoichiometry for p in reaction.participants if p.role is role)
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


def _unmapped_substrate_note(
    assignment: KineticLawAssignment,
    evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
) -> str | None:
    """Substrate-Specific Kinetic Parameterization for Promiscuous Reactions increment:
    one disclosed sentence, or ``None``, naming every curated ``Km``/``kcat`` measurement
    tagged with a real compound this reaction does not itself declare as a reactant
    participant (a product -- the reverse-direction "substrate" -- or a compound entirely
    foreign to this reaction, e.g. one belonging to a chemically related but structurally
    distinct step a promiscuous catalyst also acts on).

    Never used to build any parameter's value -- excluded from every substrate-specific
    slot entirely (`_substrate_matches` already only ever matches `reactant_compound_ids`)
    -- this function only makes that exclusion visible rather than silent, per the task's
    own "preserve the ambiguity explicitly rather than fabricating a mapping." Real Pilot 4
    cases: reaction `10c1fab0-...` (palmitate:CoA ligase) has real `kcat`/`Km` evidence
    tagged with its own product compound; reaction `dc8db885-...` (a promiscuous
    fatty-acid-elongation acyltransferase, EC 2.3.1.86) has real evidence tagged with two
    compounds belonging to other elongation-cycle steps this coarse reaction model does not
    itself represent.
    """
    relevant = policy.measurements_of_kind(evidence, policy.KM_TYPES | policy.KCAT_TYPES)
    unmapped_ids = sorted(
        m.id
        for m in relevant
        if m.compound_id is not None and m.compound_id not in reactant_compound_ids
    )
    if not unmapped_ids:
        return None
    unmapped_compounds = sorted(
        {
            m.compound_id
            for m in relevant
            if m.compound_id is not None and m.compound_id not in reactant_compound_ids
        }
    )
    return (
        f"kinetic-law-assignment::{assignment.assignment_id}: {len(unmapped_ids)} curated "
        f"Km/kcat measurement(s) ({', '.join(unmapped_ids)}) name a compound "
        f"({', '.join(unmapped_compounds)}) that is not one of this reaction's own declared "
        "reactant participants (a product, or a compound belonging to a different reaction "
        "this coarse model does not itself represent) -- excluded from every "
        "substrate-specific kcat/Km concept for this context rather than mapped onto a "
        "species it does not actually describe."
    )


def _declare_kcat_specs(
    assignment: KineticLawAssignment,
    kcat_evidence: tuple[CuratedKineticMeasurement, ...],
    reactant_compound_ids: tuple[str, ...],
    macro_kcat: Initialization | None,
    network: FullNetwork,
) -> tuple[ParameterSpecification, tuple[ParameterSpecification, ...], Initialization]:
    """The primary (position-0, backward-compatible, unsuffixed) ``kcat`` slot every
    Michaelis-Menten assignment declares exactly one of, plus zero or more additional,
    substrate-suffixed ``kcat`` slots -- one per reactant compound that carries its own,
    independently-resolvable evidence distinct from every other reactant's -- returned
    *separately* from the primary slot so the caller (`_declare_michaelis_menten`) can
    place them strictly *after* every positionally-significant parameter this law type
    declares (`app.agent2.model_specification.mapping.build_expression_and_species` reads
    `kcat` from position 0 and `Km`/fallback parameters immediately after by a fixed
    count; see that module's own docstring). Also returns the primary slot's own
    ``Initialization``, for `_declare_michaelis_menten`'s own Derivation D use.

    Substrate-Specific Kinetic Parameterization for Promiscuous Reactions increment,
    central rule: kcat evidence explicitly tagged to different, real reactant compounds
    represents genuinely distinct kinetic concepts, never merged, never averaged, never
    forced to agree merely because one physical enzyme active site is shared:

    * **Zero or one reactant compound has evidence explicitly tagged to it** (every
      reaction in the real Pilot 4 evaluation) -- the ordinary case, unchanged in shape
      from before this increment: one primary slot, resolved from that one compound's own
      tagged evidence plus any untagged evidence (kcat, unlike Km/Ki, makes no
      substrate-specific claim at all when untagged, so it is never treated as a competing
      claim against the one tagged compound -- see `_reconstruct_k_eff_for_context`'s
      identical policy), or from untagged evidence alone when no reactant compound is
      tagged at all.
    * **Two or more reactant compounds each have their own explicitly-tagged evidence** --
      a real, disclosed ambiguity for the *one* generic slot every Michaelis-Menten law
      declares (which single number would it even report?): that slot is left an explicit
      ``PLACEHOLDER`` naming every contributing substrate, while each substrate's own
      concept is fully preserved, immediately after, as its own named, independently
      resolved parameter -- built from its own exact tag only, never diluted with the
      now-genuinely-ambiguous untagged evidence (which of the 2+ real concepts would it
      belong to?) -- never silently dropped, never arbitrarily preferred.
    """
    tagged_by_compound: dict[str, tuple[CuratedKineticMeasurement, ...]] = {}
    for compound_id in reactant_compound_ids:
        tagged = tuple(m for m in kcat_evidence if m.compound_id == compound_id)
        if tagged:
            tagged_by_compound[compound_id] = tagged
    generic = tuple(m for m in kcat_evidence if m.compound_id is None)

    if len(tagged_by_compound) <= 1:
        only_tagged = next(iter(tagged_by_compound.values()), ())
        primary_evidence = only_tagged + generic
        primary_initialization = initialize_with_fallback(
            primary_evidence,
            # kcat (a turnover number) is always first-order regardless of the reaction's
            # own molecularity -- never molecularity-dependent the way a mass-action rate
            # constant is.
            kind=ParameterKind.RATE_FIRST_ORDER,
            macro_reconstruction=macro_kcat,
            network=network,
            already_substrate_scoped=True,
        )
        primary_spec = _spec_from_initialization(
            "kcat", assignment=assignment, initialization=primary_initialization
        )
        return primary_spec, (), primary_initialization

    primary_initialization = Initialization(
        source=ParameterSource.PLACEHOLDER,
        value=None,
        unit=None,
        source_reference=None,
        provenance_refs=tuple(sorted(m.id for group in tagged_by_compound.values() for m in group)),
        uncertainty_text=(
            f"{len(tagged_by_compound)} distinct reactant substrates "
            f"({', '.join(sorted(tagged_by_compound))}) each carry their own "
            "independently-resolvable kcat evidence for this catalytic context; no single "
            "one is this reaction's own generic turnover number, so none is arbitrarily "
            "preferred for this slot. See this same kinetic-law assignment's own "
            "substrate-specific kcat parameters for each individually-resolved concept. "
            "Requires calibration."
        ),
    )
    primary_spec = _spec_from_initialization(
        "kcat", assignment=assignment, initialization=primary_initialization
    )
    extra_specs = tuple(
        _spec_from_initialization(
            "kcat",
            assignment=assignment,
            initialization=initialize_with_fallback(
                tagged_by_compound[compound_id],
                kind=ParameterKind.RATE_FIRST_ORDER,
                network=network,
                already_substrate_scoped=True,
            ),
            substrate_id=compound_id,
        )
        for compound_id in reactant_compound_ids
        if compound_id in tagged_by_compound
    )
    return primary_spec, extra_specs, primary_initialization


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
    # Computed once, against the *primary* kcat concept only (below) -- a reaction with two
    # or more independently-resolvable substrate-specific kcat concepts (rare; see
    # `_declare_kcat_specs`) does not attempt a substrate-specific Derivation B for each one.
    kcat_evidence = policy.measurements_of_kind(evidence, policy.KCAT_TYPES)
    vmax_evidence = policy.measurements_of_kind(evidence, policy.VMAX_TYPES)
    macro_kcat = reconstruction.resolve_kcat_with_reconstruction(
        kcat_evidence, vmax_evidence, enzyme_concentration
    )
    primary_kcat_spec, extra_kcat_specs, kcat_initialization = _declare_kcat_specs(
        assignment, kcat_evidence, reactant_compound_ids, macro_kcat, network
    )
    specs = [primary_kcat_spec]

    km_evidence = policy.measurements_of_kind(evidence, policy.KM_TYPES)
    single_substrate = len(reactant_compound_ids) == 1
    km_initializations_by_compound: dict[str, Initialization] = {}
    km_specs_by_compound: dict[str, ParameterSpecification] = {}
    for compound_id in reactant_compound_ids:
        substrate_matches = _substrate_matches(
            km_evidence, compound_id, single_substrate=single_substrate
        )
        km_initialization = initialize_with_fallback(
            substrate_matches,
            kind=ParameterKind.CONCENTRATION,
            network=network,
            already_substrate_scoped=True,
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
        # mechanism (design doc §2.1/§2.2's own multi-substrate scope exclusion). A
        # single-reactant context always has exactly one (the primary) kcat concept -- see
        # `_declare_kcat_specs`.
        (only_compound_id,) = reactant_compound_ids
        constraint = reconstruction.classify_km_kcat_constraint(
            kcat_initialization,
            km_initializations_by_compound[only_compound_id],
            reaction_id=assignment.reaction_id,
            kinetic_law_assignment_id=assignment.assignment_id,
            kcat_parameter_id=primary_kcat_spec.parameter_id,
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
    # Any additional, substrate-suffixed kcat concepts (`_declare_kcat_specs`, the rare
    # two-or-more-mappable-reactants case) are appended last, strictly after every
    # positionally-significant parameter above -- `build_expression_and_species` only ever
    # reads a fixed, bounded number of parameters from each known position, so purely
    # informational extras trailing after them are never misread as Km or fallback
    # rate-constant slots.
    specs.extend(extra_kcat_specs)
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
    ambiguous_state_parent_keys: frozenset[tuple[str, str]],
    enzyme_concentrations_by_state_id: dict[str, EnzymeConcentration],
    *,
    sibling_count: int,
) -> tuple[tuple[ParameterSpecification, ...], tuple[MicroscopicConstraint, ...], tuple[str, ...]]:
    if assignment.kinetic_law_type is KineticLawType.UNASSIGNED:
        return (), (), ()

    evidence = _evidence_for(assignment, reaction_measurements, sibling_count=sibling_count)
    enzyme_concentration = _enzyme_concentration_for_assignment(
        assignment,
        network,
        enzyme_concentrations_by_protein_id,
        ambiguous_state_parent_keys,
        enzyme_concentrations_by_state_id,
    )

    if assignment.kinetic_law_type is KineticLawType.MASS_ACTION:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        note = _unmapped_substrate_note(assignment, evidence, reactant_compound_ids)
        return (
            _declare_mass_action(
                assignment, evidence, reactant_compound_ids, enzyme_concentration, network
            ),
            (),
            (note,) if note is not None else (),
        )
    if assignment.kinetic_law_type is KineticLawType.REVERSIBLE_MASS_ACTION:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        note = _unmapped_substrate_note(assignment, evidence, reactant_compound_ids)
        return (
            _declare_reversible_mass_action(
                assignment, evidence, reactant_compound_ids, enzyme_concentration, network
            ),
            (),
            (note,) if note is not None else (),
        )
    if assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN:
        reactant_compound_ids = _reactant_compound_ids(
            network, assignment.reaction_id, species_by_id
        )
        note = _unmapped_substrate_note(assignment, evidence, reactant_compound_ids)
        specs, constraints = _declare_michaelis_menten(
            assignment, evidence, reactant_compound_ids, enzyme_concentration, network
        )
        return specs, constraints, (note,) if note is not None else ()
    if assignment.kinetic_law_type is KineticLawType.HILL:
        return _declare_hill(assignment, evidence, network), (), ()
    if assignment.kinetic_law_type is KineticLawType.CUSTOM:
        return _declare_custom(assignment, evidence, network), (), ()

    raise ParameterReferenceError(
        f"declare_parameters has no declaration policy for kinetic_law_type="
        f"{assignment.kinetic_law_type!r} (assignment_id={assignment.assignment_id!r})"
    )


def declare_parameters(
    assignments: KineticLawAssignmentSet,
    network: FullNetwork,
    enzyme_concentrations: QuantitativeContextResolutionSet | None = None,
    enzyme_state_concentrations: tuple[EnzymeConcentration, ...] = (),
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

    ``enzyme_state_concentrations`` (Multi-Context Catalytic Rate Composition increment,
    Stage 2) is optional and defaults to ``()`` -- every existing call site continues to
    declare identical parameters. When supplied (``app.agent2.enzyme_state_dynamics``'s own
    output), each entry's own ``enzyme_state_id`` takes precedence, for that exact state's
    own catalytic context, over Stage 1's blanket ambiguous-sibling-state withholding -- see
    ``_enzyme_concentration_for_assignment``.
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
    if any(ec.enzyme_state_id is None for ec in enzyme_state_concentrations):
        raise ParameterReferenceError(
            "declare_parameters requires every enzyme_state_concentrations entry to have "
            f"enzyme_state_id set, got {enzyme_state_concentrations!r}"
        )
    enzyme_concentrations_by_state_id: dict[str, EnzymeConcentration] = {
        ec.enzyme_state_id: ec
        for ec in enzyme_state_concentrations
        if ec.enzyme_state_id is not None
    }

    measurements_by_reaction: dict[str, list[CuratedKineticMeasurement]] = {}
    for measurement in network.kinetic_measurements:
        if measurement.reaction_id is not None:
            measurements_by_reaction.setdefault(measurement.reaction_id, []).append(measurement)
    species_by_id = {species.species_id: species for species in network.species}

    sibling_counts: dict[str, int] = {}
    for assignment in assignments.assignments:
        sibling_counts[assignment.reaction_id] = sibling_counts.get(assignment.reaction_id, 0) + 1
    ambiguous_state_parent_keys = _ambiguous_state_parent_keys(assignments, network)

    specs: list[ParameterSpecification] = []
    constraints: list[MicroscopicConstraint] = []
    assumptions: list[str] = []
    for assignment in sorted(assignments.assignments, key=lambda a: a.assignment_id):
        assignment_specs, assignment_constraints, assignment_notes = _declare_for_assignment(
            assignment,
            tuple(measurements_by_reaction.get(assignment.reaction_id, ())),
            network,
            species_by_id,
            enzyme_concentrations_by_protein_id,
            ambiguous_state_parent_keys,
            enzyme_concentrations_by_state_id,
            sibling_count=sibling_counts[assignment.reaction_id],
        )
        specs.extend(assignment_specs)
        constraints.extend(assignment_constraints)
        assumptions.extend(assignment_notes)

    declaration_set = ParameterDeclarationSet(
        network_id=assignments.network_id,
        kinetic_law_policy_version=assignments.kinetic_law_policy_version,
        parameter_policy_version=PARAMETER_DECLARATION_POLICY_VERSION,
        parameter_specifications=tuple(specs),
        microscopic_constraints=tuple(constraints),
        assumptions=tuple(assumptions),
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
