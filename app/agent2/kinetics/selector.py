"""Kinetic-law selection and the public Increment 4 entry point.

``assign_kinetic_laws`` is this package's one public API: given a
``NetworkCharacterization`` and the ``FullNetwork`` it was built from, it
resolves every reaction's curated kinetic measurements once, then decides
one or more ``KineticLawAssignment`` records per reaction via
``select_reaction_assignments`` -- one per distinct catalytic context that
reaction actually has -- applying the precedence (Increment 4 revision):

1. an unambiguous, applicable curated reported rate law;
2. the deterministic structural rule;
3. the conservative Michaelis-Menten heuristic;
4. the tentative, provisional mass-action default (``is_tentative``);
5. ``UNASSIGNED`` -- only when even a tentative assignment would be
   structurally inappropriate (no catalyst known at all) or internally
   contradictory (materially conflicting curated reported laws).

Pure and deterministic: no database, no filesystem, no network access, no
LLM, no simulation, no parameter fitting anywhere in its call graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent2.characterization.types import (
    EnzymeStateCharacterization,
    NetworkCharacterization,
    ReactionCharacterization,
)
from app.agent2.kinetics import policy
from app.agent2.kinetics.errors import KineticLawReferenceError
from app.agent2.kinetics.types import (
    KineticLawAssignment,
    KineticLawAssignmentSet,
    KineticLawAssignmentSource,
    KineticLawReasonCode,
)
from app.agent2.kinetics.validation import require_full_network, require_network_characterization
from app.agent2.types import CuratedKineticMeasurement, FullNetwork, KineticLawType
from app.agent2.version import KINETIC_LAW_ASSIGNMENT_POLICY_VERSION

_ASSIGNMENT_ID_SEPARATOR = "::kinetic-law::"


def _build_assignment_id(
    reaction_id: str,
    *,
    enzyme_state_id: str | None,
    protein_id: str | None,
    complex_id: str | None,
) -> str:
    """Deterministic ``assignment_id``, scoped to one reaction (mirrors
    ``app.agent2.network.types.build_enzyme_association_id``'s own pure,
    content-derived, no-hashing style).
    """
    context = enzyme_state_id or protein_id or complex_id or "general"
    return f"{reaction_id}{_ASSIGNMENT_ID_SEPARATOR}{context}"


@dataclass(frozen=True, slots=True)
class _CatalyticContext:
    """Internal-only "target" grouping -- never exported (see ``types.py`` module docstring
    for why ``KineticLawTarget`` is folded onto ``KineticLawAssignment`` instead)."""

    enzyme_state_id: str | None = None
    protein_id: str | None = None
    complex_id: str | None = None


def _is_untagged(measurement: CuratedKineticMeasurement) -> bool:
    """No catalyst identity at all -- carries only ``reaction_id`` context."""
    return (
        measurement.enzyme_state_id is None
        and measurement.protein_id is None
        and measurement.complex_id is None
    )


def _matches_context(measurement: CuratedKineticMeasurement, context: _CatalyticContext) -> bool:
    if context.enzyme_state_id is not None:
        return measurement.enzyme_state_id == context.enzyme_state_id
    if context.protein_id is not None:
        return measurement.protein_id == context.protein_id and measurement.enzyme_state_id is None
    if context.complex_id is not None:
        return measurement.complex_id == context.complex_id and measurement.enzyme_state_id is None
    return _is_untagged(measurement)


def _build_contexts_with_evidence(
    rc: ReactionCharacterization, reaction_measurements: tuple[CuratedKineticMeasurement, ...]
) -> list[tuple[_CatalyticContext, tuple[CuratedKineticMeasurement, ...]]]:
    """Every distinct catalytic context this reaction has, each with its own evidence.

    Never collapses distinct ``catalytic_enzyme_state_ids`` (Increment 4
    instructions, Step 12's closing line) -- one context per state,
    always. Multiple protein/complex-general catalysts (isozymes,
    Step 26) collapse into one shared context only when their own
    evidence is identical after trivial normalization; otherwise each
    keeps its own context, and a global assignment is never forced over
    genuinely differing evidence.

    An untagged measurement (``reaction_id`` only, no catalyst identity)
    is folded into the reaction's **sole** catalytic context as fallback
    evidence, since there is no other context it could plausibly belong
    to. It is never folded into any one of several distinct contexts
    (multiple catalytic states, or multiple non-identical general
    catalysts) -- that would presumptively narrow ambiguous, reaction-
    level evidence onto one specific catalyst.
    """
    if rc.catalytic_enzyme_state_ids:
        contexts = [
            (
                _CatalyticContext(enzyme_state_id=state_id),
                tuple(m for m in reaction_measurements if m.enzyme_state_id == state_id),
            )
            for state_id in rc.catalytic_enzyme_state_ids
        ]
        if len(contexts) == 1:
            context, evidence = contexts[0]
            untagged = tuple(m for m in reaction_measurements if _is_untagged(m))
            return [(context, evidence + untagged)]
        return contexts

    general_catalysts: list[tuple[str, str]] = [
        ("protein_id", protein_id) for protein_id in rc.catalytic_protein_ids
    ] + [("complex_id", complex_id) for complex_id in rc.catalytic_complex_ids]

    if len(general_catalysts) >= 2:
        per_catalyst: dict[tuple[str, str], tuple[CuratedKineticMeasurement, ...]] = {}
        for field_name, catalyst_id in general_catalysts:
            context = _CatalyticContext(**{field_name: catalyst_id})
            per_catalyst[(field_name, catalyst_id)] = tuple(
                m for m in reaction_measurements if _matches_context(m, context)
            )
        text_sets = [
            frozenset(
                policy.normalize_rate_law_text(m.reported_rate_law)
                for m in evidence
                if m.reported_rate_law is not None
            )
            for evidence in per_catalyst.values()
        ]
        if all(text_set == text_sets[0] for text_set in text_sets):
            combined = tuple(m for evidence in per_catalyst.values() for m in evidence)
            untagged = tuple(m for m in reaction_measurements if _is_untagged(m))
            return [(_CatalyticContext(), combined + untagged)]
        return [
            (_CatalyticContext(**{field_name: catalyst_id}), evidence)
            for (field_name, catalyst_id), evidence in per_catalyst.items()
        ]

    if len(general_catalysts) == 1:
        field_name, catalyst_id = general_catalysts[0]
        context = _CatalyticContext(**{field_name: catalyst_id})
        tagged = tuple(m for m in reaction_measurements if _matches_context(m, context))
        untagged = tuple(m for m in reaction_measurements if _is_untagged(m))
        return [(context, tagged + untagged)]

    context = _CatalyticContext()
    return [(context, tuple(m for m in reaction_measurements if _matches_context(m, context)))]


def _allostery_present_for(
    context: _CatalyticContext,
    enzyme_state_characterizations_by_id: dict[str, EnzymeStateCharacterization],
) -> bool:
    if context.enzyme_state_id is None:
        # CuratedAllostericInteraction always requires an enzyme_state_id (non-nullable), so a
        # protein/complex/reaction-level context can never have allostery tied to it directly.
        return False
    state = enzyme_state_characterizations_by_id.get(context.enzyme_state_id)
    return bool(state and state.allosteric_interaction_ids)


def _decide_curated_reported(
    context: _CatalyticContext,
    evidence: tuple[CuratedKineticMeasurement, ...],
    *,
    reaction_id: str,
    policy_version: str,
) -> KineticLawAssignment | None:
    reported = [m for m in evidence if m.reported_rate_law is not None]
    if not reported:
        return None

    normalized_texts = {policy.normalize_rate_law_text(m.reported_rate_law) for m in reported}
    measurement_ids = tuple(sorted(m.id for m in reported))

    if len(normalized_texts) > 1:
        return _assignment(
            reaction_id=reaction_id,
            context=context,
            kinetic_law_type=KineticLawType.UNASSIGNED,
            assignment_source=KineticLawAssignmentSource.UNASSIGNED,
            policy_version=policy_version,
            source_measurement_ids=measurement_ids,
            reason_codes=(KineticLawReasonCode.MULTIPLE_DISTINCT_REPORTED_RATE_LAWS,),
            unresolved_reasons=(KineticLawReasonCode.MULTIPLE_DISTINCT_REPORTED_RATE_LAWS,),
            explanation=(
                "Left UNASSIGNED because multiple materially distinct curated reported rate "
                "laws are present for this catalytic context; no arbitrary winner was chosen."
            ),
        )

    representative = sorted(reported, key=lambda m: m.id)[0].reported_rate_law
    law_type = policy.classify_reported_rate_law_text(representative)
    reason_codes = [KineticLawReasonCode.CURATED_RATE_LAW_PRESENT]
    if law_type is KineticLawType.CUSTOM:
        reason_codes.append(KineticLawReasonCode.CURATED_RATE_LAW_CUSTOM)
        explanation = (
            "Assigned CUSTOM because a curated reported rate law is present and does not map "
            "to a built-in kinetic-law type; the reported text is preserved unchanged."
        )
    else:
        reason_codes.append(KineticLawReasonCode.CURATED_RATE_LAW_CLASSIFIED)
        explanation = (
            f"Assigned {law_type.value} because a curated reported rate law is present and "
            "was deterministically classified into a built-in kinetic-law type."
        )
    if context.enzyme_state_id is not None:
        reason_codes.append(KineticLawReasonCode.STATE_SPECIFIC_KINETICS_PRESENT)

    return _assignment(
        reaction_id=reaction_id,
        context=context,
        kinetic_law_type=law_type,
        assignment_source=KineticLawAssignmentSource.CURATED_REPORTED,
        policy_version=policy_version,
        reported_rate_law_text=representative,
        source_measurement_ids=measurement_ids,
        reason_codes=tuple(reason_codes),
        explanation=explanation,
    )


def _decide_structural(
    rc: ReactionCharacterization,
    context: _CatalyticContext,
    *,
    reaction_id: str,
    policy_version: str,
) -> KineticLawAssignment | None:
    is_general_context = context == _CatalyticContext()
    if not (is_general_context and policy.is_simple_elementary_transition(rc)):
        return None
    if rc.reversible is True:
        return _assignment(
            reaction_id=reaction_id,
            context=context,
            kinetic_law_type=KineticLawType.REVERSIBLE_MASS_ACTION,
            assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
            policy_version=policy_version,
            reason_codes=(KineticLawReasonCode.SIMPLE_REVERSIBLE_ELEMENTARY_TRANSITION,),
            explanation=(
                "Assigned REVERSIBLE_MASS_ACTION because this reaction is a curated, explicitly "
                "reversible enzyme-state transition with no competing catalytic mechanism."
            ),
        )
    return _assignment(
        reaction_id=reaction_id,
        context=context,
        kinetic_law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.DETERMINISTIC_STRUCTURAL,
        policy_version=policy_version,
        reason_codes=(KineticLawReasonCode.SIMPLE_ELEMENTARY_TRANSITION,),
        explanation=(
            "Assigned MASS_ACTION because this reaction is a curated enzyme-state transition "
            "with no competing catalytic mechanism -- a simple elementary structural change."
        ),
    )


def _decide_heuristic(
    rc: ReactionCharacterization,
    context: _CatalyticContext,
    *,
    reaction_id: str,
    policy_version: str,
    catalyst_known: bool,
    allostery_present: bool,
) -> KineticLawAssignment | None:
    if policy.michaelis_menten_eligible(
        rc, catalyst_known=catalyst_known, allostery_present=allostery_present
    ):
        return _assignment(
            reaction_id=reaction_id,
            context=context,
            kinetic_law_type=KineticLawType.MICHAELIS_MENTEN,
            assignment_source=KineticLawAssignmentSource.HEURISTIC,
            policy_version=policy_version,
            reason_codes=(KineticLawReasonCode.ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT,),
            explanation=(
                "Assigned MICHAELIS_MENTEN heuristically: a single known catalyst acting on "
                "exactly one reactant and one product, with no allostery, no reported rate "
                "law, no conflicting reversibility, and no competing catalytic state."
            ),
        )
    if policy.tentative_mass_action_default_eligible(rc, catalyst_known=catalyst_known):
        return _decide_tentative_mass_action_default(
            rc,
            context,
            reaction_id=reaction_id,
            policy_version=policy_version,
            allostery_present=allostery_present,
        )
    return None


def _decide_tentative_mass_action_default(
    rc: ReactionCharacterization,
    context: _CatalyticContext,
    *,
    reaction_id: str,
    policy_version: str,
    allostery_present: bool,
) -> KineticLawAssignment:
    """Build the tentative, provisional mass-action default assignment.

    Approved policy: *"Mass action is the default executable kinetic-law
    structure when an enzymatic reaction has no curated reported law and
    no better justified kinetic-law assignment. This does not mean that
    mass action is treated as curated truth. It is a deliberate
    provisional modeling assumption that allows the model to run."* Never
    equivalent to ``CURATED_REPORTED`` or ``DETERMINISTIC_STRUCTURAL`` --
    ``assignment_source`` stays ``HEURISTIC``, and ``unresolved_reasons``
    is always non-empty (``KineticLawAssignment.is_tentative`` is
    ``True``), so later simulation, calibration (Agent 4), and critique
    (Agent 5) can identify and revisit it (Increment 4 revision, Step 2/3).
    """
    unresolved = [KineticLawReasonCode.KINETIC_MECHANISM_NOT_CURATED]
    explanation_notes = []
    if allostery_present:
        unresolved.append(KineticLawReasonCode.REGULATORY_KINETIC_EFFECT_NOT_MODELED)
        explanation_notes.append(
            "this catalytic context carries curated allosteric regulation whose kinetic "
            "contribution is not represented by this plain mass-action form"
        )
    if len(rc.catalytic_enzyme_state_ids) > 1:
        unresolved.append(KineticLawReasonCode.MULTIPLE_CATALYTIC_STATES)
        explanation_notes.append(
            "this reaction has multiple distinct catalytic enzyme states, each assigned "
            "independently rather than assumed consistent with one another"
        )
    if rc.reversible is True:
        explanation_notes.append(
            "this reaction is curated as reversible, but this tentative form does not "
            "represent the reverse direction"
        )

    explanation = (
        "Assigned MASS_ACTION as a tentative, provisional default: no curated reported rate "
        "law and no stronger approved heuristic (e.g. Michaelis-Menten) applies to this "
        "catalytic context. Mass action is the underlying mechanistic basis for elementary "
        "reaction steps and provides an executable default model structure so the model can "
        "run; it is not treated as curated or otherwise confirmed fact for this specific "
        "reaction, and should be revisited by later simulation, calibration, or critique if "
        "model behavior disagrees with experimental data."
    )
    if explanation_notes:
        explanation += " Additionally: " + "; ".join(explanation_notes) + "."

    return _assignment(
        reaction_id=reaction_id,
        context=context,
        kinetic_law_type=KineticLawType.MASS_ACTION,
        assignment_source=KineticLawAssignmentSource.HEURISTIC,
        policy_version=policy_version,
        reason_codes=(KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT,),
        unresolved_reasons=tuple(unresolved),
        explanation=explanation,
    )


def _decide_unassigned(
    rc: ReactionCharacterization,
    context: _CatalyticContext,
    *,
    reaction_id: str,
    policy_version: str,
    catalyst_known: bool,
    allostery_present: bool,
) -> KineticLawAssignment:
    # Post-revision, this function is reachable only when catalyst_known is False (no catalyst
    # at all -- see policy.tentative_mass_action_default_eligible, consulted first): any context
    # with catalyst_known=True is necessarily ENZYMATIC (it exists only because a curated
    # ReactionEnzyme association put it there) and so always gets a tentative default instead of
    # reaching here. The allostery_present/MULTIPLE_CATALYTIC_STATES checks below are kept as a
    # defensive fallback (allostery/multiple states can only ever arise on a catalyst_known=True
    # context) rather than removed, in case a future caller reaches this function differently.
    unresolved: list[KineticLawReasonCode] = []
    if not catalyst_known:
        unresolved.append(KineticLawReasonCode.INSUFFICIENT_CURATED_CONTEXT)
    if allostery_present:
        unresolved.append(KineticLawReasonCode.ALLOSTERY_PRESENT)
    if len(rc.catalytic_enzyme_state_ids) > 1:
        unresolved.append(KineticLawReasonCode.MULTIPLE_CATALYTIC_STATES)
    if rc.reversible is True:
        unresolved.append(KineticLawReasonCode.HEURISTIC_RULE_NOT_APPLICABLE)
    if rc.reversible is None:
        unresolved.append(KineticLawReasonCode.REVERSIBILITY_UNKNOWN)
    unresolved.append(KineticLawReasonCode.NO_REPORTED_RATE_LAW)
    if not unresolved:
        unresolved.append(KineticLawReasonCode.INSUFFICIENT_CURATED_CONTEXT)

    return _assignment(
        reaction_id=reaction_id,
        context=context,
        kinetic_law_type=KineticLawType.UNASSIGNED,
        assignment_source=KineticLawAssignmentSource.UNASSIGNED,
        policy_version=policy_version,
        reason_codes=tuple(dict.fromkeys(unresolved)),
        unresolved_reasons=tuple(dict.fromkeys(unresolved)),
        explanation=(
            "Left UNASSIGNED because no curated reported rate law, deterministic structural "
            "rule, or approved heuristic rule applies -- and no catalyst is known for this "
            "context at all, so even the tentative mass-action default would be structurally "
            "inappropriate (it requires a known enzymatic catalyst)."
        ),
    )


def _assignment(
    *,
    reaction_id: str,
    context: _CatalyticContext,
    kinetic_law_type: KineticLawType,
    assignment_source: KineticLawAssignmentSource,
    policy_version: str,
    reason_codes: tuple[KineticLawReasonCode, ...],
    explanation: str,
    reported_rate_law_text: str | None = None,
    source_measurement_ids: tuple[str, ...] = (),
    unresolved_reasons: tuple[KineticLawReasonCode, ...] = (),
) -> KineticLawAssignment:
    return KineticLawAssignment(
        assignment_id=_build_assignment_id(
            reaction_id,
            enzyme_state_id=context.enzyme_state_id,
            protein_id=context.protein_id,
            complex_id=context.complex_id,
        ),
        reaction_id=reaction_id,
        kinetic_law_type=kinetic_law_type,
        assignment_source=assignment_source,
        policy_version=policy_version,
        enzyme_state_id=context.enzyme_state_id,
        protein_id=context.protein_id,
        complex_id=context.complex_id,
        reported_rate_law_text=reported_rate_law_text,
        source_measurement_ids=source_measurement_ids,
        reason_codes=reason_codes,
        unresolved_reasons=unresolved_reasons,
        explanation=explanation,
    )


def select_reaction_assignments(
    rc: ReactionCharacterization,
    *,
    reaction_measurements: tuple[CuratedKineticMeasurement, ...],
    enzyme_state_characterizations_by_id: dict[str, EnzymeStateCharacterization],
    policy_version: str,
) -> tuple[KineticLawAssignment, ...]:
    """Decide every catalytic context's kinetic-law assignment for one reaction.

    Applies the precedence curated-reported > deterministic-structural >
    conservative-heuristic (Michaelis-Menten) > tentative-mass-action-
    default > UNASSIGNED independently to each context (module docstring;
    Increment 4 revision) -- a curated law for one context never leaks
    into, and no heuristic (tentative or otherwise) ever overrides,
    another context's own decision.
    """
    contexts_with_evidence = _build_contexts_with_evidence(rc, reaction_measurements)
    assignments: list[KineticLawAssignment] = []
    for context, evidence in contexts_with_evidence:
        curated = _decide_curated_reported(
            context, evidence, reaction_id=rc.reaction_id, policy_version=policy_version
        )
        if curated is not None:
            assignments.append(curated)
            continue

        structural = _decide_structural(
            rc, context, reaction_id=rc.reaction_id, policy_version=policy_version
        )
        if structural is not None:
            assignments.append(structural)
            continue

        catalyst_known = context != _CatalyticContext() or bool(rc.catalyst_association_ids)
        allostery_present = _allostery_present_for(context, enzyme_state_characterizations_by_id)
        heuristic = _decide_heuristic(
            rc,
            context,
            reaction_id=rc.reaction_id,
            policy_version=policy_version,
            catalyst_known=catalyst_known,
            allostery_present=allostery_present,
        )
        if heuristic is not None:
            assignments.append(heuristic)
            continue

        assignments.append(
            _decide_unassigned(
                rc,
                context,
                reaction_id=rc.reaction_id,
                policy_version=policy_version,
                catalyst_known=catalyst_known,
                allostery_present=allostery_present,
            )
        )
    return tuple(assignments)


def assign_kinetic_laws(
    characterization: NetworkCharacterization, network: FullNetwork
) -> KineticLawAssignmentSet:
    """Transform a ``NetworkCharacterization`` into explicit, provenance-aware kinetic-law
    decisions.

    Takes both ``characterization`` and the ``network`` it was built from,
    rather than ``characterization`` alone -- a deliberate, documented
    deviation from Increment 4's own illustrative single-argument
    signature. ``ReactionCharacterization`` only carries kinetic-
    measurement *ids* by design (Increment 3, ``docs/06`` §16: "referenced
    by measurement id only"); reading the actual reported rate-law text
    Step 9 requires this package to preserve verbatim needs the underlying
    ``CuratedKineticMeasurement`` records, which only ``FullNetwork``
    holds. This continues, one pipeline stage further, the exact same
    "characterization holds ids, resolve via the network" pattern
    Increment 3 itself established -- not a new architectural choice.
    See ``docs/07_kinetic_law_assignment.md`` §3.
    """
    require_network_characterization(characterization)
    require_full_network(network)
    if characterization.network_id != network.network_id:
        raise KineticLawReferenceError(
            f"characterization.network_id ({characterization.network_id!r}) does not match "
            f"network.network_id ({network.network_id!r})"
        )

    measurements_by_reaction: dict[str, list[CuratedKineticMeasurement]] = {}
    for measurement in network.kinetic_measurements:
        if measurement.reaction_id is not None:
            measurements_by_reaction.setdefault(measurement.reaction_id, []).append(measurement)
    enzyme_state_characterizations_by_id = {
        state.enzyme_state_id: state for state in characterization.enzyme_state_characterizations
    }

    assignments: list[KineticLawAssignment] = []
    for rc in characterization.reaction_characterizations:
        assignments.extend(
            select_reaction_assignments(
                rc,
                reaction_measurements=tuple(measurements_by_reaction.get(rc.reaction_id, ())),
                enzyme_state_characterizations_by_id=enzyme_state_characterizations_by_id,
                policy_version=KINETIC_LAW_ASSIGNMENT_POLICY_VERSION,
            )
        )

    assignment_set = KineticLawAssignmentSet(
        network_id=characterization.network_id,
        characterization_policy_version=characterization.characterization_policy_version,
        kinetic_law_policy_version=KINETIC_LAW_ASSIGNMENT_POLICY_VERSION,
        assignments=tuple(assignments),
    )

    expected_reaction_ids = {rc.reaction_id for rc in characterization.reaction_characterizations}
    covered_reaction_ids = {a.reaction_id for a in assignment_set.assignments}
    if expected_reaction_ids != covered_reaction_ids:
        raise KineticLawReferenceError(
            "assign_kinetic_laws produced assignments not covering every reaction: "
            f"missing {expected_reaction_ids - covered_reaction_ids!r}, "
            f"unexpected {covered_reaction_ids - expected_reaction_ids!r}"
        )

    return assignment_set


__all__ = ["assign_kinetic_laws", "select_reaction_assignments"]
