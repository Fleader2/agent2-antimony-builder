"""Deterministic heuristic rules, each evaluating one candidate interface.

Every rule is a pure function `CandidateFacts -> RuleOutcome`: it reads
only already-precomputed structural/kinetic/parameter/regulatory facts
about the candidate's two reactions (built once per candidate by
`assessor.py`), never touches `FullNetwork`/`NetworkCharacterization`/
`KineticLawAssignmentSet`/`ParameterDeclarationSet` directly, and never
assigns a final `BoundaryLikelihood` itself -- that combination is
`policy.combine_outcomes`'s job.

**Increment 6 pre-commit scientific revision.** A module is a functional
unit whose intrinsic behavior is largely independent of its surrounding
network -- not merely a densely connected graph region. This file's rule
catalog is organized around that distinction (see
``docs/09_heuristic_boundary_assessment.md`` §10a for the full
rationale): structural/topological rules are weakened (they are proxies,
not evidence), parameterization-convenience rules are retired to
permanent `NEUTRAL`, and new rules evaluate functional isolation,
resource coupling, and feedback directly. `STRONG` support is reachable
only through `irreversible_output_isolation`; `STRONG` opposition only
through `intrinsic_feedback_isolation` and the structural
`strong_local_continuity` -- reserving `BoundaryLikelihood.VERY_HIGH`
(see `policy.combine_outcomes`) for genuine isolation evidence, never an
accumulation of structural discontinuities alone.

**Increment 6 feedback-heuristic revision.** Nested feedback loops are
ordinary biology: an intrinsic loop confined to one side of a candidate
interface is what defines that side as a module, while an extrinsic loop
crossing the interface is typically module-*regulating* communication,
not proof the two sides are one unit. `negative_feedback_isolation` was
renamed `intrinsic_feedback_confinement` and now opposes (not supports)
a boundary; `feedback_crossing_boundary` was renamed
`extrinsic_feedback_crossing` and now always returns `NEUTRAL` -- Agent 2
has no dynamic-simulation capability to determine whether a
boundary-crossing loop is direct, strong, constitutive, local, and
minimally regulated, and must not pretend otherwise. See
``docs/09_heuristic_boundary_assessment.md``, "Nested Feedback Loops".

**Increment 6 terminology revision (naming/documentation only, no
behavior change).** `intrinsic_feedback_confinement` was renamed
`intrinsic_feedback_isolation`: the scientific concept is that local,
direct, strong negative feedback provides functional *isolation* by
reducing retroactivity, not merely that it is spatially "confined." Its
deterministic trigger, direction (`OPPOSE`), and strength (`STRONG`) are
unchanged. See ``docs/09_heuristic_boundary_assessment.md`` §24.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent2.boundaries.types import BoundaryReasonCode as Code
from app.agent2.boundaries.types import RuleDirection as Direction
from app.agent2.boundaries.types import RuleOutcome
from app.agent2.boundaries.types import RuleStrength as Strength
from app.agent2.characterization.types import ReactionClass
from app.agent2.types import KineticLawType

_STRENGTH_RANK: dict[Strength, int] = {
    Strength.WEAK: 0,
    Strength.MODERATE: 1,
    Strength.STRONG: 2,
}


def weaker_strength(a: Strength, b: Strength) -> Strength:
    """The lesser of two known qualitative strengths (ordinal min, never a numeric score).

    Used only to reconcile two sides of one discontinuity rule -- never
    to combine multiple rules' outcomes into a final likelihood (that is
    `policy.combine_outcomes`'s own, separately documented, categorical
    logic).
    """
    return a if _STRENGTH_RANK[a] <= _STRENGTH_RANK[b] else b


@dataclass(frozen=True, slots=True)
class CandidateFacts:
    """Every precomputed fact one candidate interface's rules may need.

    Built once per candidate by `assessor.py` from `FullNetwork`/
    `NetworkCharacterization`/`KineticLawAssignmentSet`/
    `ParameterDeclarationSet` -- rules never see those source objects
    directly, only this narrow, already-resolved bundle.

    **Revision note:** the pre-revision fields
    `upstream_parameter_sources`/`downstream_parameter_sources`/
    `upstream_all_placeholder`/`downstream_all_placeholder`/
    `upstream_any_curated`/`downstream_any_curated` were removed -- once
    `parameter_source_discontinuity`/`placeholder_parameter_region`/
    `parameterization_continuity` were retired to permanent `NEUTRAL`
    (see module docstring), no rule read them anymore. `parameter_basis`
    (a `BoundaryAssessment` field, disclosed for audit regardless of
    boundary-likelihood evidence) is computed directly in `assessor.py`
    from the actual parameter lists, independent of this bundle.
    """

    upstream_reaction_id: str
    downstream_reaction_id: str
    shared_species_ids: tuple[str, ...]
    upstream_classes: frozenset[ReactionClass]
    downstream_classes: frozenset[ReactionClass]
    upstream_compartments: frozenset[str]
    downstream_compartments: frozenset[str]
    upstream_regulatory_context: bool
    downstream_regulatory_context: bool
    upstream_law_types: frozenset[KineticLawType]
    downstream_law_types: frozenset[KineticLawType]
    upstream_law_confidence: Strength | None
    downstream_law_confidence: Strength | None
    any_shared_species_branch: bool
    any_shared_species_convergence: bool
    any_shared_species_high_connectivity: bool
    upstream_reversible: bool | None
    downstream_reversible: bool | None
    upstream_catalytic_ids: frozenset[str]
    downstream_catalytic_ids: frozenset[str]
    confined_inhibitory_feedback: bool
    crossing_regulatory_interaction: bool


# =================================================================================================
# Structural proxies -- correlate with modularity, are not themselves evidence of it. Never
# exceed MODERATE strength (see module docstring): VERY_HIGH is reserved for the functional-
# modularity rules below.
# =================================================================================================


def compartment_transition(facts: CandidateFacts) -> RuleOutcome:
    """Supports when the two reactions' own participant compartments differ.

    Never true for an ordinary shared-species edge alone (species
    identity already embeds compartment, so two reactions sharing one
    species always agree on *that* species' compartment) -- this fires
    when either reaction also touches a *different* compartment via its
    other participants, i.e. primarily on the edges adjacent to a
    multi-compartment (typically transport) reaction. Distinct from
    `transport_interface` below: a reaction can span compartments without
    meeting Increment 3's own conservative `TRANSPORT` classification.
    Retained at `MODERATE` (unchanged by this revision): physical
    compartmentalization is a classical, genuine isolation mechanism, but
    on its own it is still only a structural proxy -- it does not confirm
    the two sides behave independently.
    """
    if facts.upstream_compartments != facts.downstream_compartments:
        return RuleOutcome(Code.COMPARTMENT_TRANSITION, Direction.SUPPORT, Strength.MODERATE)
    return RuleOutcome(Code.COMPARTMENT_TRANSITION, Direction.NEUTRAL)


def transport_interface(facts: CandidateFacts) -> RuleOutcome:
    """Supports when either side is Increment 3's own deterministic
    ``ReactionClass.TRANSPORT`` classification -- never a hard boundary.

    **Revision: downgraded from `STRONG` to `MODERATE`.** Transport marks
    a compartment interface, but does not by itself confirm retroactivity
    insulation (e.g. a transporter can still be tightly, reversibly
    coupled to both sides via near-equilibrium exchange) -- it remains a
    structural proxy, not confirmed functional isolation.
    """
    upstream_transport = ReactionClass.TRANSPORT in facts.upstream_classes
    downstream_transport = ReactionClass.TRANSPORT in facts.downstream_classes
    if upstream_transport or downstream_transport:
        return RuleOutcome(Code.TRANSPORT_INTERFACE, Direction.SUPPORT, Strength.MODERATE)
    return RuleOutcome(Code.TRANSPORT_INTERFACE, Direction.NEUTRAL)


def branch_point(facts: CandidateFacts) -> RuleOutcome:
    """Supports when a shared species is consumed by more than one reaction -- pure
    structural topology, never an inferred pathway name.

    **Revision: downgraded from `MODERATE` to `WEAK`.** A branch point is
    purely topological: the branches could still be tightly co-regulated
    (e.g. shared allosteric control), so this is weaker evidence of
    functional independence than the original strength implied.
    """
    if facts.any_shared_species_branch:
        return RuleOutcome(Code.BRANCH_POINT, Direction.SUPPORT, Strength.WEAK)
    return RuleOutcome(Code.BRANCH_POINT, Direction.NEUTRAL)


def convergence_point(facts: CandidateFacts) -> RuleOutcome:
    """Supports when a shared species is produced by more than one reaction.

    **Revision: downgraded from `MODERATE` to `WEAK`**, for the identical
    reason as `branch_point`: pure topology, not functional evidence.
    """
    if facts.any_shared_species_convergence:
        return RuleOutcome(Code.CONVERGENCE_POINT, Direction.SUPPORT, Strength.WEAK)
    return RuleOutcome(Code.CONVERGENCE_POINT, Direction.NEUTRAL)


def enzyme_state_transition(facts: CandidateFacts) -> RuleOutcome:
    """Supports when either side is directly referenced by a curated
    ``EnzymeStateTransition`` (Increment 3's own ``ReactionClass.STATE_TRANSITION``) --
    never automatically splits regulatory states into separate modules on its own.

    **Revision: reconsidered, retained at `MODERATE`.** A regulatory-state
    change is more biologically specific than pure topology, but still
    does not itself confirm the two catalytic forms behave independently.
    """
    upstream_transition = ReactionClass.STATE_TRANSITION in facts.upstream_classes
    downstream_transition = ReactionClass.STATE_TRANSITION in facts.downstream_classes
    if upstream_transition or downstream_transition:
        return RuleOutcome(Code.ENZYME_STATE_TRANSITION, Direction.SUPPORT, Strength.MODERATE)
    return RuleOutcome(Code.ENZYME_STATE_TRANSITION, Direction.NEUTRAL)


def curated_regulatory_context_change(facts: CandidateFacts) -> RuleOutcome:
    """Supports, weakly, when exactly one side carries curated regulation/allostery.

    Absence on one side is never treated as biological absence -- only as
    "no curated fact available," hence the deliberately weak strength and
    the reason code's own "CURATED_..._CONTEXT_CHANGE" wording (never
    "REGULATION_PRESENT_VS_ABSENT"). **Revision: reconsidered, retained
    at `WEAK`** -- already appropriately conservative.
    """
    if facts.upstream_regulatory_context != facts.downstream_regulatory_context:
        return RuleOutcome(Code.CURATED_REGULATORY_CONTEXT_CHANGE, Direction.SUPPORT, Strength.WEAK)
    return RuleOutcome(Code.CURATED_REGULATORY_CONTEXT_CHANGE, Direction.NEUTRAL)


def kinetic_law_discontinuity(facts: CandidateFacts) -> RuleOutcome:
    """Supports when the two sides' assigned kinetic-law types differ.

    **Revision: strength ceiling lowered to `MODERATE`** (previously could
    reach `STRONG` when both sides were confidently curated/structural).
    A kinetic-law *type* difference is a modeling-form artifact -- it
    reflects how Agent 2 chose to represent each reaction's rate law, not
    a direct biological claim of independence, so it must never carry the
    same weight as genuine functional-isolation evidence. Still uses the
    *weaker* of the two sides' own assignment confidence
    (`weaker_strength`) to decide between `WEAK` and `MODERATE`: a
    discontinuity next to a tentative default remains weaker evidence
    than one between two well-supported curated/structural laws.
    """
    if (
        facts.upstream_law_types
        and facts.downstream_law_types
        and facts.upstream_law_types != facts.downstream_law_types
    ):
        weakest = weaker_strength(
            facts.upstream_law_confidence or Strength.WEAK,
            facts.downstream_law_confidence or Strength.WEAK,
        )
        weak_only = weakest not in (Strength.MODERATE, Strength.STRONG)
        strength = Strength.WEAK if weak_only else Strength.MODERATE
        return RuleOutcome(Code.KINETIC_LAW_DISCONTINUITY, Direction.SUPPORT, strength)
    return RuleOutcome(Code.KINETIC_LAW_DISCONTINUITY, Direction.NEUTRAL)


def high_connectivity_continuity(facts: CandidateFacts) -> RuleOutcome:
    """*Opposes* when a shared species is a high-connectivity structural hub (see
    `assessor._HIGH_CONNECTIVITY_THRESHOLD` for the exact deterministic threshold) -- a
    currency-metabolite-like species is a poor module anchor, so a connection through it is
    weaker grounds for a boundary here, not stronger.

    **Revision: reconsidered, retained at `MODERATE`.** This is, in
    effect, a network-scale form of resource coupling (see
    `shared_catalyst_coupling` below) and remains well-justified
    unchanged.
    """
    if facts.any_shared_species_high_connectivity:
        return RuleOutcome(Code.HIGH_CONNECTIVITY_CONTINUITY, Direction.OPPOSE, Strength.MODERATE)
    return RuleOutcome(Code.HIGH_CONNECTIVITY_CONTINUITY, Direction.NEUTRAL)


def strong_local_continuity(facts: CandidateFacts) -> RuleOutcome:
    """Opposes, strongly, when every continuity condition holds at once: same compartment,
    same *and meaningfully assigned* kinetic-law type(s), no branch, no convergence, not
    transport.

    **Revision: reconsidered, retained at `STRONG`, with one correction.**
    "Same law type" no longer counts when both sides are merely
    `{KineticLawType.UNASSIGNED}` -- two reactions that both lack any
    assigned mechanism are not thereby shown to share one; that was mutual
    *absence* of information masquerading as continuity evidence, exactly
    the failure mode this revision exists to correct. Genuine mixed
    evidence (e.g. this rule firing alongside a real isolation signal
    such as `irreversible_output_isolation`) is not specially excluded --
    that is legitimate evidence on both sides, which
    `policy.combine_outcomes` already resolves conservatively toward
    `MEDIUM` rather than an extreme likelihood.
    """
    same_compartment = facts.upstream_compartments == facts.downstream_compartments
    both_unassigned = facts.upstream_law_types == facts.downstream_law_types == frozenset(
        {KineticLawType.UNASSIGNED}
    )
    same_law = (
        bool(facts.upstream_law_types)
        and facts.upstream_law_types == facts.downstream_law_types
        and not both_unassigned
    )
    no_branch = not facts.any_shared_species_branch
    no_convergence = not facts.any_shared_species_convergence
    not_transport = (
        ReactionClass.TRANSPORT not in facts.upstream_classes
        and ReactionClass.TRANSPORT not in facts.downstream_classes
    )
    if same_compartment and same_law and no_branch and no_convergence and not_transport:
        return RuleOutcome(Code.STRONG_LOCAL_CONTINUITY, Direction.OPPOSE, Strength.STRONG)
    return RuleOutcome(Code.STRONG_LOCAL_CONTINUITY, Direction.NEUTRAL)


# =================================================================================================
# Parameterization convenience -- retired to permanent NEUTRAL (Increment 6 revision). Which
# measurements Agent 1 happened to curate is a fact about our knowledge state, never about the
# organism's biology -- see module docstring and docs/09 sec 10a. Kept as functions (not deleted)
# so the retirement itself, and the reasoning behind it, stays visible and testable.
# =================================================================================================


def parameter_source_discontinuity(facts: CandidateFacts) -> RuleOutcome:
    """**Retired to permanent `NEUTRAL`.** A difference in which curated-measurement
    provenance categories exist on each side reflects what Agent 1 happened to curate, not
    a biological fact about the reactions -- never evidence of functional modularity."""
    return RuleOutcome(Code.PARAMETER_SOURCE_DISCONTINUITY, Direction.NEUTRAL)


def placeholder_parameter_region(facts: CandidateFacts) -> RuleOutcome:
    """**Retired to permanent `NEUTRAL`.** Placeholder-heavy parameterization on one side
    reflects a knowledge gap, not evidence the two sides function independently."""
    return RuleOutcome(Code.PLACEHOLDER_PARAMETER_REGION, Direction.NEUTRAL)


def parameterization_continuity(facts: CandidateFacts) -> RuleOutcome:
    """**Retired to permanent `NEUTRAL`.** Shared parameter-source provenance is, for the
    identical reason, never evidence that two reactions form one functional unit -- its
    kinetic-law-sameness component is already covered, on genuinely structural grounds, by
    `strong_local_continuity` above."""
    return RuleOutcome(Code.PARAMETERIZATION_CONTINUITY, Direction.NEUTRAL)


# =================================================================================================
# Functional modularity -- evaluate the biological definition directly (isolation, coupling,
# feedback). Of these, only `intrinsic_feedback_isolation` (oppose) and
# `irreversible_output_isolation` (support) may return STRONG (see module docstring).
# `shared_catalyst_coupling` caps at MODERATE; `extrinsic_feedback_crossing` is always NEUTRAL
# (see its own docstring -- Increment 6 feedback-heuristic revision).
# =================================================================================================


def shared_catalyst_coupling(facts: CandidateFacts) -> RuleOutcome:
    """Opposes when the two sides share a catalytic identity (the same protein, complex, or
    enzyme state catalyzes both) -- they compete for the same limiting catalytic resource, a
    textbook form of coupling that argues against treating them as independent modules
    (functional definition: "shared-resource coupling")."""
    shared_catalysts = facts.upstream_catalytic_ids & facts.downstream_catalytic_ids
    if facts.upstream_catalytic_ids and facts.downstream_catalytic_ids and shared_catalysts:
        return RuleOutcome(Code.SHARED_RESOURCE_COUPLING, Direction.OPPOSE, Strength.MODERATE)
    return RuleOutcome(Code.SHARED_RESOURCE_COUPLING, Direction.NEUTRAL)


def intrinsic_feedback_isolation(facts: CandidateFacts) -> RuleOutcome:
    """Opposes, strongly, only when a curated inhibitory regulatory interaction is
    confirmed confined entirely within one side of this interface (its regulator and its
    target both resolve to the same side, never the other).

    **Increment 6 feedback-heuristic revision (renamed from
    `negative_feedback_isolation`; direction flipped from support to
    oppose).** Nested feedback loops are ordinary biology: an inner loop
    confined to one side of a candidate interface is what makes that side
    a functional module in the first place -- it is *intrinsic* feedback,
    direct, local, and (as far as this interaction is curated) largely
    unregulated. That is evidence *against* introducing more boundary
    structure right at that side's edge, not evidence that this
    particular interface is a good place to cut. See
    ``docs/09_heuristic_boundary_assessment.md``, "Nested Feedback Loops".

    **Increment 6 terminology revision (renamed again from
    `intrinsic_feedback_confinement`; naming/documentation only, no
    behavior change).** The scientific concept is not merely that the
    feedback is spatially/topologically "confined" -- it is that local,
    direct, strong negative feedback can provide functional *isolation*
    by reducing retroactivity and preserving intrinsic module behavior.
    "Confinement" describes a geometric fact about where the interaction
    sits; "isolation" names the functional consequence this package
    actually cares about, so it is the more accurate name for the rule
    and its reason code. The deterministic trigger, direction, and
    strength below are unchanged from the prior name.

    **What `OPPOSE` means here (do not read this rule as "these two
    reactions should be merged into one module"):** this rule opposes
    placing *another* boundary inside the locally isolated circuit that
    the confined feedback interaction already defines -- it argues for
    preserving the integrity of that self-regulated circuit, not for any
    particular merge decision between the two candidate reactions. This
    package never decides which modules should be merged; that is
    Increment 7's job. See "Nested Feedback Loops" and the "Preserving
    the local circuit" note in docs §24 for the full clarification.

    Returns `NEUTRAL` whenever confinement cannot be confirmed -- the
    common case, since Agent 1's regulation pipeline is known-incomplete
    and most curated interactions do not resolve to identifiable
    compound/reaction ids on both sides. That is expected and acceptable,
    never treated as "no feedback exists."
    """
    if facts.confined_inhibitory_feedback:
        return RuleOutcome(
            Code.INTRINSIC_FEEDBACK_ISOLATION, Direction.OPPOSE, Strength.STRONG
        )
    return RuleOutcome(Code.INTRINSIC_FEEDBACK_ISOLATION, Direction.NEUTRAL)


def extrinsic_feedback_crossing(facts: CandidateFacts) -> RuleOutcome:
    """**Always `NEUTRAL`.** A curated regulatory interaction whose regulator resolves to
    one side of this interface and target to the other (`facts.crossing_regulatory_interaction`)
    is deliberately never interpreted here -- see below.

    **Increment 6 feedback-heuristic revision (renamed from
    `feedback_crossing_boundary`; no longer opposes).** Feedback that
    crosses a proposed module boundary is not, by itself, evidence the
    two sides should be merged: nested feedback loops are expected in
    biology, and a loop spanning modules is frequently *extrinsic*,
    module-regulating communication (e.g. a downstream module signaling
    demand back to an upstream one) rather than proof the two sides are
    one functional unit. Only a boundary-crossing loop that is
    additionally confirmed direct, strong, constitutive, local, and
    minimally regulated would be legitimate grounds to oppose a boundary
    -- and Agent 2 has no dynamic-simulation capability (no loop gain,
    response time, relaxation time, retroactivity, buffering strength, or
    condition-dependence estimate) with which to determine any of those
    properties. Rather than fabricate that judgment, this rule
    deliberately ignores `facts.crossing_regulatory_interaction` and
    always returns `NEUTRAL`. The fact itself remains computed (see
    `assessor._resolve_feedback`) so a future revision -- once Agent 4
    can supply the missing dynamic evidence -- can reactivate this rule
    without reworking the underlying detection. See
    ``docs/09_heuristic_boundary_assessment.md``, "Nested Feedback Loops"
    and "Future Dynamic Refinement".

    **Why no inference is made, spelled out (terminology revision, no
    behavior change):** even though a crossing interaction is confirmed
    structurally, Agent 2 currently has no way to determine whether it is
    direct, strong, constitutive, regulated, adaptive, dynamically
    isolating, or dynamically coupling -- any one of which could change
    whether it is legitimate evidence against a boundary. This is not a
    gap this rule tries to paper over with a plausible-sounding guess;
    a concise, deterministic `NEUTRAL` that says "not enough information"
    is the honest answer, and no dynamic measurement is invented in its
    place.
    """
    return RuleOutcome(Code.EXTRINSIC_FEEDBACK_CROSSING_DEFERRED, Direction.NEUTRAL)


def irreversible_output_isolation(facts: CandidateFacts) -> RuleOutcome:
    """Supports, strongly, only when the *upstream* reaction (the one feeding this
    interface) is explicitly curated `reversible=False` -- a genuinely irreversible,
    committed step insulates whatever precedes it from downstream retroactivity by
    construction (downstream demand cannot propagate backward through an irreversible
    step).

    `NEUTRAL` when reversibility is `True` or unrecorded (`None`) --
    never guessed. This package cannot yet distinguish *why* a reaction
    is irreversible (proteolysis, an irreversible covalent modification,
    or simply a strongly favorable equilibrium) -- see
    ``docs/09_heuristic_boundary_assessment.md`` §15a for that
    limitation.
    """
    if facts.upstream_reversible is False:
        return RuleOutcome(Code.IRREVERSIBLE_OUTPUT_ISOLATION, Direction.SUPPORT, Strength.STRONG)
    return RuleOutcome(Code.IRREVERSIBLE_OUTPUT_ISOLATION, Direction.NEUTRAL)


# =================================================================================================
# Deferred principles -- always NEUTRAL until a later agent exists to evaluate them (Agent 4
# dynamics, or cross-context/cross-organism data this package has no access to). Never
# fabricated from static curated structure alone. See docs/09 sec 16a-18a.
# =================================================================================================


def relaxation_time_invariance(facts: CandidateFacts) -> RuleOutcome:
    """**Deferred.** Whether a module's internal relaxation time is invariant to (much
    faster than) perturbations from its surroundings is a genuine functional-modularity
    criterion, but evaluating it requires dynamical simulation -- Agent 4's job, not yet
    implemented. Always `NEUTRAL` until that capability exists; never inferred from static
    structure or parameter magnitude alone."""
    return RuleOutcome(Code.RELAXATION_TIME_INVARIANCE_DEFERRED, Direction.NEUTRAL)


def context_reusability(facts: CandidateFacts) -> RuleOutcome:
    """**Deferred.** Whether a candidate module's behavior is reusable/composable across
    different surrounding biological contexts cannot be assessed from one curated network
    alone -- it requires comparison across multiple organisms/conditions Agent 1 does not
    yet curate in a comparable form. Always `NEUTRAL`."""
    return RuleOutcome(Code.CONTEXT_REUSABILITY_DEFERRED, Direction.NEUTRAL)


def stable_functional_role(facts: CandidateFacts) -> RuleOutcome:
    """**Deferred.** Whether a candidate module performs a stable, identifiable functional
    role (e.g. "switch," "oscillator," "amplifier") independent of context is a dynamical-
    systems classification this package cannot make from static curated structure alone.
    Always `NEUTRAL` until a later agent can characterize dynamical behavior."""
    return RuleOutcome(Code.STABLE_FUNCTIONAL_ROLE_DEFERRED, Direction.NEUTRAL)


#: Fixed, documented evaluation order -- never affects the final result, since `policy
#: .combine_outcomes` only ever counts/aggregates outcomes by direction and strength, never
#: by position. Kept as an explicit tuple (not e.g. a decorator-populated registry) so the
#: full rule set is visible in one place.
ALL_RULES = (
    # Structural proxies
    compartment_transition,
    transport_interface,
    branch_point,
    convergence_point,
    enzyme_state_transition,
    curated_regulatory_context_change,
    kinetic_law_discontinuity,
    high_connectivity_continuity,
    strong_local_continuity,
    # Parameterization convenience (always NEUTRAL)
    parameter_source_discontinuity,
    placeholder_parameter_region,
    parameterization_continuity,
    # Functional modularity
    shared_catalyst_coupling,
    intrinsic_feedback_isolation,
    extrinsic_feedback_crossing,
    irreversible_output_isolation,
    # Deferred principles (always NEUTRAL)
    relaxation_time_invariance,
    context_reusability,
    stable_functional_role,
)


__all__ = [
    "ALL_RULES",
    "CandidateFacts",
    "branch_point",
    "compartment_transition",
    "context_reusability",
    "convergence_point",
    "curated_regulatory_context_change",
    "enzyme_state_transition",
    "extrinsic_feedback_crossing",
    "high_connectivity_continuity",
    "intrinsic_feedback_isolation",
    "irreversible_output_isolation",
    "kinetic_law_discontinuity",
    "parameter_source_discontinuity",
    "parameterization_continuity",
    "placeholder_parameter_region",
    "relaxation_time_invariance",
    "shared_catalyst_coupling",
    "stable_functional_role",
    "strong_local_continuity",
    "transport_interface",
    "weaker_strength",
]
