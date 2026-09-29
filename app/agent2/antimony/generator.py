"""Antimony Generation (Increment 9): the public ``generate_antimony`` entry point.

Serializes one authoritative ``ModelSpecification`` into a complete
``Agent2OutputPackage`` -- one ``FullAntimonyArtifact`` plus zero or more
``ModuleAntimonyArtifact`` records -- without reinterpreting or changing
any scientific or modeling decision made in Increments 1-8. Pure and
deterministic: no database, no filesystem, no network access, no
simulation, no fitting, no mutation of ``model``. See
``docs/12_antimony_generation.md`` for the full contract.

**Pre-commit revision -- biochemical reaction identity vs. kinetic
contribution** (``docs/12_antimony_generation.md`` §11a): a
``KineticLawSpecification`` represents one catalytic kinetic
*contribution* to a reaction's rate, never a second biochemical reaction.
One ``ReactionSpecification`` always serializes to exactly one Antimony
reaction, regardless of how many distinct catalytic-context kinetic laws
reference it. When more than one kinetic law shares a ``reaction_id``,
this module never emits duplicate stoichiometric reactions and never
sums the contributions unless simultaneous applicability is established
-- never inferred from the mere existence of multiple contexts -- see
``resolve_reaction_rate_expression``.

**Multi-Context Catalytic Rate Composition increment (Stage 1)**: the
simultaneous-applicability signal §11a's own ``RESOLVED_COMPOSED`` had
always been reserved for now exists, scoped narrowly --
``_context_group_composability`` composes a homogeneous group of two or
more distinct protein-general contexts, or a homogeneous group of two or
more distinct complex-general contexts, additively (never a mix of the
two). Two or more independently-resolved isozymes acting on the same
reaction now produce one real, disclosed, summed rate (`(v_p1) + (v_p2)`)
instead of an unconditional `UNRESOLVED_MULTIPLE_CONTEXTS`.

**Stage 2 (Enzyme-State Population Dynamics and Conservation)**: a
homogeneous group of two or more distinct enzyme-state contexts is now
*also* composable, but only when every one of those states belongs to the
identical parent protein's dynamically-modeled, conserved pool
(``ModelSpecification.enzyme_state_pools`` -- produced by
``app.agent2.enzyme_state_dynamics``, never inferred merely from two
states sharing a parent protein). Two or more enzyme-state contexts with
no such pool, states spanning two different parent proteins, or any mix
of enzyme-state with protein/complex-general contexts, still resolve to
`UNRESOLVED_MULTIPLE_CONTEXTS` exactly as in Stage 1 -- composing across a
pool-conservation basis this increment does not itself establish would
still be fabricated biology.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agent2.antimony.errors import UnsupportedAntimonySerializationError
from app.agent2.antimony.naming import (
    IdentifierMap,
    build_identifier_map,
    sanitize_model_name,
)
from app.agent2.antimony.serializer import (
    format_decimal,
    format_stoichiometry,
    render_kinetic_law_expression,
)
from app.agent2.antimony.validation import validate_serializer_integrity
from app.agent2.reversibility import ReversibilityBasis, classify_reversibility_basis
from app.agent2.types import (
    Agent2OutputPackage,
    AntimonyArtifactReadiness,
    CompartmentSpecification,
    FullAntimonyArtifact,
    KineticLawSpecification,
    KineticLawType,
    ModelSpecification,
    ModuleAntimonyArtifact,
    ModuleSpecification,
    ParameterSpecification,
    ParticipantRole,
    ReactionSpecification,
    SpeciesSpecification,
)
from app.agent2.version import AGENT2_CONTRACT_VERSION, ANTIMONY_GENERATION_POLICY_VERSION


@dataclass(frozen=True)
class _LawResolution:
    """One kinetic law's own, context-local serialization-readiness verdict: is *this*
    law's expression/parameters/reversibility resolved, independent of whether any sibling
    law shares its ``reaction_id``. Computed once, reused everywhere (Step 32)."""

    rendered_expression: str | None
    resolved: bool
    reasons: tuple[str, ...]


class _ReactionRateStatus(StrEnum):
    """The reaction-level (not law-level) verdict ``resolve_reaction_rate_expression``
    returns -- see that function's own docstring.

    **Multi-Context Catalytic Rate Composition increment (Stage 1, extended in Stage 2)**:
    ``RESOLVED_COMPOSED`` is now genuinely produced -- see ``_context_group_composability``
    for the exact simultaneous-applicability gate. It fires only for a homogeneous group of
    protein-general-only contexts, complex-general-only contexts, or (Stage 2)
    enzyme-state-only contexts whose states all belong to one common parent protein's
    dynamically-modeled, conserved pool -- never a group mixing two different kinds, and
    never an enzyme-state group outside a modeled pool -- where every individual law is
    itself independently resolved."""

    RESOLVED_SINGLE = "RESOLVED_SINGLE"
    RESOLVED_COMPOSED = "RESOLVED_COMPOSED"
    UNRESOLVED_MULTIPLE_CONTEXTS = "UNRESOLVED_MULTIPLE_CONTEXTS"
    UNRESOLVED_EXPRESSION = "UNRESOLVED_EXPRESSION"
    UNASSIGNED = "UNASSIGNED"


_RESOLVED_REACTION_STATUSES = frozenset(
    {_ReactionRateStatus.RESOLVED_SINGLE, _ReactionRateStatus.RESOLVED_COMPOSED}
)


@dataclass(frozen=True)
class _ReactionRateResolution:
    """One ``ReactionSpecification``'s reaction-level rate resolution -- the unit of
    executability this package actually cares about (never a single kinetic law in
    isolation, since a reaction's true rate may depend on more than one contribution)."""

    status: _ReactionRateStatus
    expression: str | None
    laws: tuple[KineticLawSpecification, ...] = ()
    unresolved_law_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def _context_kind(law: KineticLawSpecification) -> str:
    if law.enzyme_state_id is not None:
        return "enzyme_state"
    if law.protein_id is not None:
        return "protein"
    if law.complex_id is not None:
        return "complex"
    return "general"


def _context_group_composability(
    laws: tuple[KineticLawSpecification, ...],
    pooled_state_protein_by_id: dict[str, str],
) -> bool:
    """Multi-Context Catalytic Rate Composition increment (Stage 1, extended in Stage 2)
    -- the simultaneous-applicability gate ``docs/12_antimony_generation.md`` §11a's own
    ``RESOLVED_COMPOSED`` always required but never had a signal for, until Stage 1.

    True for a **homogeneous** group of two or more distinct protein-general contexts, a
    homogeneous group of two or more distinct complex-general contexts, or (Stage 2) a
    homogeneous group of two or more distinct enzyme-state contexts whose states all
    belong to the identical parent protein's **dynamically-modeled, conserved pool**
    (``pooled_state_protein_by_id`` -- built from ``ModelSpecification.enzyme_state_pools``,
    never from ``FullNetwork.enzyme_states`` directly, so a state merely sharing a parent
    protein with no curated transition/conservation basis is never composed). Never a mix
    of two different kinds (a whole enzyme complex and one of its own subunit proteins are
    never established as independently, additively active; nothing curated confirms that
    combination is not double-counting), and never a group containing an enzyme-state
    context outside a modeled pool, or spanning two different parent proteins' pools.

    **Why enzyme-state composition is safe now, when Stage 1 explicitly forbade it**: Stage
    1's own concern was that a modification state's population is a mutually exclusive
    *fraction* of one total pool, and summing state-specific rates as though every state
    were simultaneously, fully present would fabricate biology no curated data supported.
    That concern is about the *catalyst concentration* each contribution's own parameters
    were initialized from, not about whether two states' *reactions* can coexist -- and
    Stage 2's own ``app.agent2.enzyme_state_dynamics`` never hands the full parent
    concentration to more than one sibling state (each gets, at most, its own distinct,
    conservation-consistent share, or nothing at all). Composing their independently-
    resolved rates additively is therefore exactly as safe as composing two isozymes: each
    contribution's own parameters already account for (or honestly withhold) its own
    catalyst's real population, so summing the resulting rates never double-counts.

    A "general" (no catalyst identity at all) context is also never composed with anything
    -- there is no basis to confirm it is biologically distinct from a sibling law rather
    than an artifact of ambiguous/collapsed evidence.
    """
    if len(laws) < 2:
        return False
    kinds = {_context_kind(law) for law in laws}
    if kinds == {"protein"} or kinds == {"complex"}:
        identities = {law.protein_id or law.complex_id for law in laws}
        return len(identities) == len(laws)
    if kinds == {"enzyme_state"}:
        state_ids = tuple(law.enzyme_state_id for law in laws)
        if len(set(state_ids)) != len(state_ids):
            return False
        parent_protein_ids = {pooled_state_protein_by_id.get(state_id) for state_id in state_ids}
        if None in parent_protein_ids:
            return False
        return len(parent_protein_ids) == 1
    return False


def resolve_reaction_rate_expression(
    reaction: ReactionSpecification,
    laws: tuple[KineticLawSpecification, ...],
    law_resolutions: dict[str, _LawResolution],
    pooled_state_protein_by_id: dict[str, str],
) -> _ReactionRateResolution:
    """Resolve one reaction's total rate from every ``KineticLawSpecification`` that
    references it.

    **Central architectural rule**: a ``KineticLawSpecification`` is a kinetic
    *contribution*, not a second biochemical reaction. Exactly one law -> that law's own
    resolution, verbatim (``RESOLVED_SINGLE`` or its own unresolved reason). Two or more laws
    sharing this ``reaction_id`` compose additively (``RESOLVED_COMPOSED``) only when
    ``_context_group_composability`` establishes they are simultaneously, independently
    applicable **and** every one of them is individually resolved on its own; otherwise
    ``UNRESOLVED_MULTIPLE_CONTEXTS`` -- never summed, never arbitrarily chosen among, never
    duplicated into multiple stoichiometric reactions. See ``docs/12_antimony_generation.md``
    §11a for the full inspection and the Multi-Context Catalytic Rate Composition
    increment's own extension of it.
    """
    ordered_laws = tuple(sorted(laws, key=lambda law: law.kinetic_law_id))
    if not ordered_laws:
        # Defensive only: Increment 8 guarantees 1:1 coverage (every reaction gets exactly
        # one KineticLawSpecification, even if UNASSIGNED) -- should be unreachable.
        return _ReactionRateResolution(
            status=_ReactionRateStatus.UNASSIGNED,
            expression=None,
            laws=(),
            unresolved_law_ids=(),
            reasons=("NO_KINETIC_LAW_FOR_REACTION",),
        )

    if len(ordered_laws) > 1:
        law_ids = tuple(law.kinetic_law_id for law in ordered_laws)
        if not _context_group_composability(ordered_laws, pooled_state_protein_by_id):
            return _ReactionRateResolution(
                status=_ReactionRateStatus.UNRESOLVED_MULTIPLE_CONTEXTS,
                expression=None,
                laws=ordered_laws,
                unresolved_law_ids=law_ids,
                reasons=("MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED",),
            )
        contribution_resolutions = tuple(
            law_resolutions[law.kinetic_law_id] for law in ordered_laws
        )
        if not all(r.resolved for r in contribution_resolutions):
            # Composable in principle, but at least one contribution is not itself
            # resolved -- never silently drop it and compose only the resolved remainder
            # (that would understate the real total rate without disclosure), and never
            # let its own unresolved status corrupt a sibling contribution's independent
            # resolution (each ``_LawResolution`` above was computed in total isolation).
            return _ReactionRateResolution(
                status=_ReactionRateStatus.UNRESOLVED_MULTIPLE_CONTEXTS,
                expression=None,
                laws=ordered_laws,
                unresolved_law_ids=law_ids,
                reasons=("MULTIPLE_CATALYTIC_CONTEXTS_COMPOSABLE_BUT_UNRESOLVED",),
            )
        composed_expression = " + ".join(
            f"({r.rendered_expression})" for r in contribution_resolutions
        )
        return _ReactionRateResolution(
            status=_ReactionRateStatus.RESOLVED_COMPOSED,
            expression=composed_expression,
            laws=ordered_laws,
        )

    law = ordered_laws[0]
    resolution = law_resolutions[law.kinetic_law_id]
    if resolution.resolved:
        return _ReactionRateResolution(
            status=_ReactionRateStatus.RESOLVED_SINGLE,
            expression=resolution.rendered_expression,
            laws=ordered_laws,
        )
    status = (
        _ReactionRateStatus.UNASSIGNED
        if law.law_type is KineticLawType.UNASSIGNED
        else _ReactionRateStatus.UNRESOLVED_EXPRESSION
    )
    return _ReactionRateResolution(
        status=status,
        expression=None,
        laws=ordered_laws,
        unresolved_law_ids=(law.kinetic_law_id,),
        reasons=resolution.reasons,
    )


def generate_antimony(model: ModelSpecification) -> Agent2OutputPackage:
    """Deterministically serialize ``model`` into one ``Agent2OutputPackage``.

    Never reassesses kinetic laws, parameters, boundaries, or module
    decomposition -- every scientific/modeling decision is read verbatim
    from ``model``. Never mutates ``model``.
    """
    if not isinstance(model, ModelSpecification):
        raise UnsupportedAntimonySerializationError(
            f"generate_antimony requires a ModelSpecification, got {model!r}"
        )

    id_map = build_identifier_map(model)
    validate_serializer_integrity(model, id_map)

    reactions_by_id = {r.reaction_id: r for r in model.full_network.reactions}
    parameters_by_id = {p.parameter_id: p for p in model.parameters}
    species_by_id = {s.species_id: s for s in model.full_network.species}
    compartments_by_id = {c.compartment_id: c for c in model.full_network.compartments}

    law_resolutions = {
        law.kinetic_law_id: _resolve_law(
            law, reactions_by_id[law.reaction_id], parameters_by_id, id_map
        )
        for law in model.kinetic_laws
    }

    laws_by_reaction: dict[str, list[KineticLawSpecification]] = {}
    for law in model.kinetic_laws:
        laws_by_reaction.setdefault(law.reaction_id, []).append(law)

    # Multi-Context Catalytic Rate Composition increment, Stage 2: every enzyme-state id
    # that is part of some dynamically-modeled, conserved pool, mapped to that pool's own
    # parent protein id -- never built from FullNetwork.enzyme_states directly, so a state
    # with no curated transition/conservation basis is never treated as composable.
    pooled_state_protein_by_id = {
        state_id: pool.protein_id
        for pool in model.enzyme_state_pools
        for state_id in pool.state_ids
    }

    reaction_resolutions = {
        reaction_id: resolve_reaction_rate_expression(
            reaction,
            tuple(laws_by_reaction.get(reaction_id, ())),
            law_resolutions,
            pooled_state_protein_by_id,
        )
        for reaction_id, reaction in reactions_by_id.items()
    }

    full_text, full_readiness, full_unresolved_laws, full_unresolved_reactions = _render_model(
        model_name=model.model_id,
        compartments=model.full_network.compartments,
        species=model.full_network.species,
        kinetic_laws=model.kinetic_laws,
        reactions_by_id=reactions_by_id,
        reaction_resolutions=reaction_resolutions,
        parameters=model.parameters,
        id_map=id_map,
    )
    full_antimony = FullAntimonyArtifact(
        model_id=model.model_id,
        model_specification_id=model.model_id,
        antimony_text=full_text,
        generator_version=ANTIMONY_GENERATION_POLICY_VERSION,
        provenance_refs=(f"model-specification::{model.model_id}",),
        readiness=full_readiness,
        unresolved_kinetic_law_ids=full_unresolved_laws,
        unresolved_reaction_ids=full_unresolved_reactions,
    )

    module_artifacts = tuple(
        _generate_module_artifact(
            module,
            model=model,
            id_map=id_map,
            reaction_resolutions=reaction_resolutions,
            reactions_by_id=reactions_by_id,
            parameters_by_id=parameters_by_id,
            compartments_by_id=compartments_by_id,
            species_by_id=species_by_id,
        )
        for module in sorted(model.module_specifications, key=lambda m: m.module_id)
    )

    return Agent2OutputPackage(
        contract_version=AGENT2_CONTRACT_VERSION,
        model_specification=model,
        full_antimony=full_antimony,
        module_artifacts=module_artifacts,
        boundary_assessments=model.boundary_assessments,
        module_decomposition=model.module_decomposition,
    )


# --- Per-law readiness (Step 15-19 of the original Increment 9 instructions) -------------------


def _resolve_law(
    law: KineticLawSpecification,
    reaction: ReactionSpecification,
    parameters_by_id: dict[str, ParameterSpecification],
    id_map: IdentifierMap,
) -> _LawResolution:
    """A kinetic law is executable, *considered alone*, only when its expression is resolved
    and every parameter it references has a numeric value -- never because Increment 9
    fabricated a missing fact for either. This is a necessary, but not sufficient, condition
    for the *reaction's* rate to be resolved -- see ``resolve_reaction_rate_expression`` for
    the reaction-level policy.

    **Conservative reversibility default** (Agent 2 increment, motivated by Real Integration
    Pilot 2 Run 5 and Agent 1.x Increment C.8): an unresolved curated ``reversible`` (``None``)
    no longer blocks this law's own resolution -- ``app.agent2.reversibility
    .effective_reversible`` treats it as tentatively reversible for model-construction
    purposes, disclosed via ``REACTION_REVERSIBILITY_ASSUMED`` (never silently). The original
    curated value is never mutated; ``ReactionSpecification.reversible`` still reads exactly
    what Agent 1 supplied, and the authoritative disclosure of this assumption lives in
    ``ModelSpecification.model_assumptions`` (``REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE``),
    not here -- this reason string is a convenience surfaced in the Antimony comment only.
    """
    reasons: list[str] = []
    rendered = render_kinetic_law_expression(law, id_map)

    if law.expression is None:
        reasons.append(
            "UNASSIGNED_KINETIC_LAW"
            if law.law_type is KineticLawType.UNASSIGNED
            else "UNRESOLVED_KINETIC_EXPRESSION"
        )
    elif law.law_type is KineticLawType.CUSTOM:
        reasons.append("CUSTOM_LAW_SYMBOL_MAPPING_UNAVAILABLE")

    missing_parameters = sorted(
        pid for pid in law.parameter_ids if not parameters_by_id[pid].has_value
    )
    if missing_parameters:
        reasons.append("PARAMETER_VALUE_UNRESOLVED:" + ",".join(missing_parameters))

    if reaction.reversible is None:
        reasons.append("REACTION_REVERSIBILITY_ASSUMED")

    resolved = rendered is not None and not missing_parameters
    return _LawResolution(rendered_expression=rendered, resolved=resolved, reasons=tuple(reasons))


# --- Text rendering ------------------------------------------------------------------------------


def _compartment_line(compartment: CompartmentSpecification, antimony_id: str) -> str:
    if compartment.initial_volume is not None:
        unit_comment = f" unit={compartment.volume_unit}" if compartment.volume_unit else ""
        return (
            f"compartment {antimony_id} = {format_decimal(compartment.initial_volume)};"
            f"  // compartment_id={compartment.compartment_id}{unit_comment}"
        )
    return (
        f"compartment {antimony_id};"
        f"  // compartment_id={compartment.compartment_id} (initial size unresolved)"
    )


def _species_lines(
    species: SpeciesSpecification, antimony_id: str, compartment_id_map: dict[str, str]
) -> list[str]:
    compartment_antimony_id = compartment_id_map[species.compartment_id]
    lines = [
        f"species {antimony_id} in {compartment_antimony_id};  // species_id={species.species_id}"
    ]
    if species.initial_amount is not None:
        lines.append(
            f"{antimony_id} = {format_decimal(species.initial_amount)};"
            "  // initial_amount (amount, not concentration -- see ModelSpecification)"
        )
    elif species.initial_concentration is not None:
        lines.append(
            f"{antimony_id} = {format_decimal(species.initial_concentration)};"
            "  // initial_concentration (concentration, not amount -- see ModelSpecification)"
        )
    return lines


def _reversible_comment(reaction: ReactionSpecification) -> str:
    basis = classify_reversibility_basis(reaction.reversible)
    if basis is ReversibilityBasis.ASSUMED_REVERSIBLE:
        return "reversible(assumed)"
    return "reversible" if basis is ReversibilityBasis.CURATED_REVERSIBLE else "irreversible"


def _law_context(law: KineticLawSpecification) -> str | None:
    return law.enzyme_state_id or law.protein_id or law.complex_id


def _reaction_line(
    reaction: ReactionSpecification,
    resolution: _ReactionRateResolution,
    id_map: IdentifierMap,
) -> str:
    reactants = [
        (p.species_id, p.stoichiometry)
        for p in reaction.participants
        if p.role is ParticipantRole.REACTANT
    ]
    products = [
        (p.species_id, p.stoichiometry)
        for p in reaction.participants
        if p.role is ParticipantRole.PRODUCT
    ]
    lhs = " + ".join(format_stoichiometry(stoich, id_map.species[sid]) for sid, stoich in reactants)
    rhs = " + ".join(format_stoichiometry(stoich, id_map.species[sid]) for sid, stoich in products)
    equation = f"{lhs} -> {rhs}".strip()
    antimony_reaction_id = id_map.reactions[reaction.reaction_id]
    reversible_comment = _reversible_comment(reaction)

    if resolution.status is _ReactionRateStatus.RESOLVED_SINGLE:
        (law,) = resolution.laws
        context = _law_context(law)
        context_comment = f" catalytic_context={context}" if context else ""
        return (
            f"{antimony_reaction_id}: {equation}; {resolution.expression};"
            f"  // reaction_id={reaction.reaction_id} kinetic_law_id={law.kinetic_law_id} "
            f"law_type={law.law_type.value} reversible={reversible_comment}{context_comment}"
        )

    if resolution.status is _ReactionRateStatus.RESOLVED_COMPOSED:
        # Multi-Context Catalytic Rate Composition increment (Stage 1): two or more
        # simultaneously-applicable, independently-resolved catalytic contexts, composed
        # additively -- every contributing law id/context is named explicitly, never
        # collapsed into an anonymous total (§11a: "each contribution remains individually
        # inspectable").
        contexts = ", ".join(
            f"{law.kinetic_law_id}[{_law_context(law) or 'no-context'}]" for law in resolution.laws
        )
        law_types = ",".join(sorted({law.law_type.value for law in resolution.laws}))
        return (
            f"{antimony_reaction_id}: {equation}; {resolution.expression};"
            f"  // reaction_id={reaction.reaction_id} COMPOSED from ({contexts}) "
            f"law_types=({law_types}) reversible={reversible_comment} reason="
            "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY -- simultaneously-applicable, "
            "independently-resolved catalytic contexts summed additively, never merged into "
            "one shared law or parameter set"
        )

    if resolution.status is _ReactionRateStatus.UNRESOLVED_MULTIPLE_CONTEXTS:
        contexts = ", ".join(
            f"{law.kinetic_law_id}[{_law_context(law) or 'no-context'}]" for law in resolution.laws
        )
        reasons = ",".join(resolution.reasons)
        # Two distinct real reasons share this status: composition was never eligible at
        # all (a mixed-kind group, or an enzyme-state group outside a modeled pool/spanning
        # two parent proteins), or it was eligible but at least one contribution is not
        # itself resolved yet -- ``reasons`` (always present) already discloses which,
        # machine-readably; the prose below stays generically accurate for both rather than
        # guessing.
        outcome = (
            "eligible for composition but at least one contribution is unresolved"
            if "MULTIPLE_CATALYTIC_CONTEXTS_COMPOSABLE_BUT_UNRESOLVED" in resolution.reasons
            else "simultaneous composition not established"
        )
        return (
            f"{antimony_reaction_id}: {equation};"
            f"  // reaction_id={reaction.reaction_id} UNRESOLVED multiple catalytic contexts "
            f"({contexts}) reasons=({reasons}) reversible={reversible_comment} -- {outcome}, "
            "rate withheld, see ModelSpecification.model_assumptions"
        )

    # A single, unresolved law (UNASSIGNED or UNRESOLVED_EXPRESSION -- see _resolve_law).
    law = resolution.laws[0] if resolution.laws else None
    law_comment = (
        f"kinetic_law_id={law.kinetic_law_id} law_type={law.law_type.value} " if law else ""
    )
    context_comment = f" catalytic_context={_law_context(law)}" if law and _law_context(law) else ""
    reasons = ",".join(resolution.reasons)
    return (
        f"{antimony_reaction_id}: {equation};"
        f"  // reaction_id={reaction.reaction_id} {law_comment}"
        f"UNRESOLVED reasons=({reasons}) reversible={reversible_comment}{context_comment} -- "
        "rate withheld, see ModelSpecification.model_assumptions"
    )


def _parameter_line(parameter: ParameterSpecification, antimony_id: str) -> str:
    if parameter.has_value:
        assert isinstance(parameter.value, Decimal)
        unit_comment = f" unit={parameter.unit}" if parameter.unit else ""
        return (
            f"{antimony_id} = {format_decimal(parameter.value)};"
            f"  // parameter_id={parameter.parameter_id} source={parameter.source.value}"
            f"{unit_comment}"
        )
    return (
        f"// {antimony_id} UNRESOLVED (parameter_id={parameter.parameter_id} "
        f"source={parameter.source.value}) -- no numeric value declared"
    )


def _render_model(
    *,
    model_name: str,
    compartments: tuple[CompartmentSpecification, ...],
    species: tuple[SpeciesSpecification, ...],
    kinetic_laws: tuple[KineticLawSpecification, ...],
    reactions_by_id: dict[str, ReactionSpecification],
    reaction_resolutions: dict[str, _ReactionRateResolution],
    parameters: tuple[ParameterSpecification, ...],
    id_map: IdentifierMap,
) -> tuple[str, AntimonyArtifactReadiness, tuple[str, ...], tuple[str, ...]]:
    """Deterministic Antimony text for one full model or module view/standalone body (Step
    33 ordering: model declaration, compartments, species, reactions, parameters, ``end``).

    One line per **biochemical reaction** (``reaction_resolutions``, keyed by
    ``reaction_id``) -- never one line per kinetic law. Returns the text, the readiness it
    implies, every blocking ``kinetic_law_id``, and every blocking ``reaction_id``.
    """
    lines: list[str] = [f"model {sanitize_model_name(model_name)}()", ""]

    ordered_compartments = sorted(compartments, key=lambda c: id_map.compartments[c.compartment_id])
    if ordered_compartments:
        lines.append("// compartments")
        lines.extend(
            _compartment_line(c, id_map.compartments[c.compartment_id])
            for c in ordered_compartments
        )
        lines.append("")

    ordered_species = sorted(species, key=lambda s: id_map.species[s.species_id])
    if ordered_species:
        lines.append("// species")
        for s in ordered_species:
            lines.extend(_species_lines(s, id_map.species[s.species_id], id_map.compartments))
        lines.append("")

    ordered_reaction_ids = sorted(reaction_resolutions, key=lambda rid: id_map.reactions[rid])
    unresolved_law_ids: list[str] = []
    unresolved_reaction_ids: list[str] = []
    if ordered_reaction_ids:
        lines.append("// reactions")
        for reaction_id in ordered_reaction_ids:
            resolution = reaction_resolutions[reaction_id]
            lines.append(_reaction_line(reactions_by_id[reaction_id], resolution, id_map))
            if resolution.status not in _RESOLVED_REACTION_STATUSES:
                unresolved_reaction_ids.append(reaction_id)
                unresolved_law_ids.extend(resolution.unresolved_law_ids)
        lines.append("")

    referenced_parameter_ids = {pid for law in kinetic_laws for pid in law.parameter_ids}
    ordered_parameters = sorted(
        (p for p in parameters if p.parameter_id in referenced_parameter_ids),
        key=lambda p: id_map.parameters[p.parameter_id],
    )
    if ordered_parameters:
        lines.append("// parameters")
        lines.extend(
            _parameter_line(p, id_map.parameters[p.parameter_id]) for p in ordered_parameters
        )
        lines.append("")

    lines.append("end")
    text = "\n".join(lines).rstrip("\n") + "\n"

    unresolved_laws = tuple(sorted(unresolved_law_ids))
    unresolved_reactions = tuple(sorted(unresolved_reaction_ids))
    readiness = (
        AntimonyArtifactReadiness.EXECUTABLE
        if not unresolved_reactions
        else AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS
    )
    return text, readiness, unresolved_laws, unresolved_reactions


# --- Module views and standalone models ----------------------------------------------------------


def _generate_module_artifact(
    module: ModuleSpecification,
    *,
    model: ModelSpecification,
    id_map: IdentifierMap,
    reaction_resolutions: dict[str, _ReactionRateResolution],
    reactions_by_id: dict[str, ReactionSpecification],
    parameters_by_id: dict[str, ParameterSpecification],
    compartments_by_id: dict[str, CompartmentSpecification],
    species_by_id: dict[str, SpeciesSpecification],
) -> ModuleAntimonyArtifact:
    module_reaction_ids = set(module.reaction_ids)
    module_laws = tuple(
        law for law in model.kinetic_laws if law.reaction_id in module_reaction_ids
    )
    module_species = tuple(species_by_id[sid] for sid in module.species_ids if sid in species_by_id)

    module_compartments = tuple(
        compartments_by_id[cid] for cid in module.compartment_ids if cid in compartments_by_id
    )
    if not module_compartments:
        derived_compartment_ids = sorted({s.compartment_id for s in module_species})
        module_compartments = tuple(
            compartments_by_id[cid] for cid in derived_compartment_ids if cid in compartments_by_id
        )

    module_parameters = tuple(
        parameters_by_id[pid] for pid in module.parameter_ids if pid in parameters_by_id
    )
    if not module_parameters and module_laws:
        referenced = sorted({pid for law in module_laws for pid in law.parameter_ids})
        module_parameters = tuple(
            parameters_by_id[pid] for pid in referenced if pid in parameters_by_id
        )

    module_reaction_resolutions = {
        reaction_id: reaction_resolutions[reaction_id] for reaction_id in module.reaction_ids
    }

    view_text, _, view_unresolved_laws, view_unresolved_reactions = _render_model(
        model_name=f"{model.model_id}::module::{module.module_id}::view",
        compartments=module_compartments,
        species=module_species,
        kinetic_laws=module_laws,
        reactions_by_id=reactions_by_id,
        reaction_resolutions=module_reaction_resolutions,
        parameters=module_parameters,
        id_map=id_map,
    )

    if not module.has_explicit_boundary_interfaces:
        # Standalone models require explicit interface semantics -- never invent one.
        return ModuleAntimonyArtifact(
            module_id=module.module_id,
            model_specification_id=model.model_id,
            generator_version=ANTIMONY_GENERATION_POLICY_VERSION,
            antimony_view=view_text,
            readiness=AntimonyArtifactReadiness.VIEW_ONLY,
        )

    if view_unresolved_reactions:
        # A reaction-level unresolved rate (including unresolved catalytic-context
        # composition) blocks standalone eligibility even when boundary interfaces are
        # otherwise fully explicit -- never emit a standalone model that looks runnable but
        # is missing a real rate for one of its own reactions.
        return ModuleAntimonyArtifact(
            module_id=module.module_id,
            model_specification_id=model.model_id,
            generator_version=ANTIMONY_GENERATION_POLICY_VERSION,
            antimony_view=view_text,
            boundary_interfaces=module.boundary_interfaces,
            readiness=AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS,
            unresolved_kinetic_law_ids=view_unresolved_laws,
            unresolved_reaction_ids=view_unresolved_reactions,
        )

    standalone_text = _render_standalone_module(
        module,
        model=model,
        compartments=module_compartments,
        species=module_species,
        kinetic_laws=module_laws,
        reactions_by_id=reactions_by_id,
        reaction_resolutions=module_reaction_resolutions,
        parameters=module_parameters,
        id_map=id_map,
    )
    return ModuleAntimonyArtifact(
        module_id=module.module_id,
        model_specification_id=model.model_id,
        generator_version=ANTIMONY_GENERATION_POLICY_VERSION,
        antimony_view=view_text,
        standalone_antimony=standalone_text,
        boundary_interfaces=module.boundary_interfaces,
        readiness=AntimonyArtifactReadiness.EXECUTABLE,
    )


def _render_standalone_module(
    module: ModuleSpecification,
    *,
    model: ModelSpecification,
    compartments: tuple[CompartmentSpecification, ...],
    species: tuple[SpeciesSpecification, ...],
    kinetic_laws: tuple[KineticLawSpecification, ...],
    reactions_by_id: dict[str, ReactionSpecification],
    reaction_resolutions: dict[str, _ReactionRateResolution],
    parameters: tuple[ParameterSpecification, ...],
    id_map: IdentifierMap,
) -> str:
    """A standalone module model is the same body as its view, plus explicit handling of
    every declared ``ModuleBoundaryInterface`` -- never a fabricated boundary condition
    (only what the interface itself already states). Only ever called once every included
    reaction's rate is already confirmed resolved (see ``_generate_module_artifact``)."""
    base_text, _, _, _ = _render_model(
        model_name=f"{model.model_id}::module::{module.module_id}::standalone",
        compartments=compartments,
        species=species,
        kinetic_laws=kinetic_laws,
        reactions_by_id=reactions_by_id,
        reaction_resolutions=reaction_resolutions,
        parameters=parameters,
        id_map=id_map,
    )
    body_lines = base_text.rstrip("\n").removesuffix("end").rstrip("\n").splitlines()
    body_lines.append("")
    body_lines.append("// boundary interfaces (explicit -- never inferred)")
    for interface in sorted(module.boundary_interfaces, key=lambda i: i.species_id):
        antimony_id = id_map.species.get(interface.species_id, interface.species_id)
        if interface.externally_controlled:
            body_lines.append(f"const {antimony_id};")
            if interface.initial_value is not None:
                body_lines.append(f"{antimony_id} = {format_decimal(interface.initial_value)};")
        unit_comment = f" unit={interface.unit}" if interface.unit else ""
        body_lines.append(
            f"// interface species_id={interface.species_id} role={interface.role.value} "
            f"direction={interface.direction} "
            f"externally_controlled={interface.externally_controlled}"
            f"{unit_comment} assumption={interface.assumption!r}"
        )
    body_lines.append("")
    body_lines.append("end")
    return "\n".join(body_lines) + "\n"


__all__ = ["generate_antimony"]
