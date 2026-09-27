"""Pure mapping helpers: KineticLawAssignment -> KineticLawSpecification, and deterministic
ModelAssumption construction (Increment 8).

Every function here is a pure, deterministic transformation of already-
decided upstream data -- never a new modeling decision. No kinetic-law
type is reclassified, no parameter value is changed, no boundary
likelihood is reinterpreted, no module cut is revisited. See
``docs/11_model_specification_assembly.md`` §6-11/§16 for the full
rationale behind each choice made here.

**"Unresolved Kinetic Evidence Disclosure" increment** (motivated by Real
Integration Pilot 2 Run 2: 14 real SABIO-RK kinetic measurements survived
the Agent 1 handoff and this module's own assembly untouched, but their
exclusion from reaction-specific kinetic-law assignment -- correct,
required, since none has a resolved ``reaction_id`` -- was invisible in the
final ``ModelSpecification``, indistinguishable from "no kinetic evidence
exists at all"). ``build_model_assumptions`` now also emits one
``ModelAssumption`` (reason code
``KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED``) per
``CuratedKineticMeasurement`` with ``reaction_id is None`` -- a pure,
deterministic disclosure of an already-true fact, never a new inference:
the core selector rule (reaction-specific kinetic evidence requires
justified reaction attribution) is completely unchanged, and this
increment does not, and must not, cause any such measurement to start
contributing a real-valued parameter. Protein applicability
(``CuratedKineticMeasurement.protein_ids``) is disclosed alongside each
such assumption for reviewer context, but is never treated as evidence of
reaction applicability -- see that field's own docstring in ``app.agent2
.types``.

**Pre-commit revisions.** Several prior choices were corrected before
this increment's first commit, each because it would have forced
Increment 9 to parse text, rediscover a fact this module could simply
preserve directly, or misread a status marker as a real expression:

* `assignment.assignment_source` (`KineticLawAssignmentSource`) is now
  copied **verbatim** onto `KineticLawSpecification.assignment_source` --
  the previous lossy bridge into `ParameterSource` has been removed
  entirely, now that the field's own type is correct (see
  ``docs/11_model_specification_assembly.md`` §10).
* `assignment.enzyme_state_id`/`.protein_id`/`.complex_id` are copied
  **verbatim** onto `KineticLawSpecification`'s own new fields of the
  same name -- the previous `_catalytic_context_tag` provenance-string
  workaround has been removed entirely, now that the fields exist
  directly (§11).
**"Substrate-Anchored Michaelis-Menten Eligibility Refinement" increment**
(motivated by Real Integration Pilot 2 Run 3: a real SABIO-RK Km was
uniquely, deterministically reaction-attributed to yeast's real malonyl-
CoA:[acp] S-malonyltransferase reaction, but that reaction has 2 reactants
and 2 products, so it never qualified for the pre-existing single-
substrate Michaelis-Menten heuristic and fell to a tentative mass-action
default whose only parameter is never populated from curated evidence --
the real Km was correctly never fabricated into it, but also never used
at all). `app.agent2.kinetics.selector`/`.policy` gained a new, narrowly-
scoped eligibility path -- `SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_
APPROXIMATION` -- that assigns `MICHAELIS_MENTEN` to a multi-reactant
reaction only when exactly one curated `Km` measurement is unambiguously
anchored (by resolved `compound_id`) to exactly one of that reaction's
own reactant compounds; nothing here changed to make this possible, since
`app.agent2.parameters.builder._declare_michaelis_menten` and
`build_expression_and_species` (this module, unmodified) already declare
a Km slot per reactant and already withhold a fabricated combining
expression for 2+ reactants. `build_model_assumptions` gained one new
disclosure block (below) naming the specific anchored substrate and
source measurement for this case -- distinct from, and layered alongside,
the existing generic multi-substrate-expression disclosure.

* A genuinely multi-substrate `MICHAELIS_MENTEN` assignment now produces
  `expression=None` (`law_type` stays `MICHAELIS_MENTEN`,
  `parameter_ids`/`species_ids` stay populated) -- the previous
  `UNRESOLVED_MULTI_SUBSTRATE_MECHANISM` string sentinel has been removed
  entirely. `KineticLawSpecification.__post_init__` no longer requires a
  non-blank `expression` for a non-`UNASSIGNED` law type (Increment 8
  pre-commit revision, ``docs/11_model_specification_assembly.md`` §8):
  the law *family* can be known while its exact algebra remains
  unresolved, and that state must never be represented by placing a
  non-expression status marker in a field whose entire meaning is "the
  concrete algebraic representation." The unresolved state is disclosed
  instead through `assumptions` (below) and a dedicated `ModelAssumption`
  (`build_model_assumptions`, §16).
"""

from __future__ import annotations

from app.agent2.kinetics.types import KineticLawAssignment, KineticLawReasonCode
from app.agent2.model_specification.errors import ModelSpecificationReferenceError
from app.agent2.reversibility import (
    REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE,
    is_assumed,
)
from app.agent2.types import (
    CuratedKineticMeasurement,
    KineticLawSpecification,
    KineticLawType,
    ModelAssumption,
    ParameterSpecification,
    ParticipantRole,
    ReactionSpecification,
)

#: Stable, machine-readable reason code (Agent 2 "Unresolved Kinetic
#: Evidence Disclosure" increment): a kinetic measurement exists but its
#: reaction applicability is unresolved -- distinct from "no kinetic
#: evidence exists at all," which produces no assumption of this kind
#: (there is nothing to disclose). Not a ``KineticLawReasonCode`` member:
#: that enum's own domain is reasons a kinetic-law *assignment* made a
#: particular choice for a reaction it was already grouped under; this
#: category describes a measurement that never reached grouping at all,
#: mirroring how ``"PLACEHOLDER"``/``"MEDIUM"``/
#: ``"MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED"`` above are also plain,
#: purpose-specific strings outside that enum.
KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED = "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"


def _is_tentative(assignment: KineticLawAssignment) -> bool:
    return KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT in assignment.reason_codes


def _reactant_species_ids(reaction: ReactionSpecification) -> tuple[str, ...]:
    return tuple(
        p.species_id for p in reaction.participants if p.role is ParticipantRole.REACTANT
    )


def _product_species_ids(reaction: ReactionSpecification) -> tuple[str, ...]:
    return tuple(
        p.species_id for p in reaction.participants if p.role is ParticipantRole.PRODUCT
    )


def _all_participant_species_ids(reaction: ReactionSpecification) -> tuple[str, ...]:
    return tuple(sorted({p.species_id for p in reaction.participants}))


def build_expression_and_species(
    assignment: KineticLawAssignment,
    reaction: ReactionSpecification,
    law_parameters: tuple[ParameterSpecification, ...],
) -> tuple[str | None, tuple[str, ...]]:
    """Canonical symbolic expression (species/parameter ids only, never a numeric literal, never
    Antimony syntax -- Increment 8 instructions, Step 9) and the species this specific law
    references, for one assignment.

    `law_parameters` must already be filtered to exactly this assignment's own declared
    parameters (`ParameterSpecification.kinetic_law_assignment_id == assignment.assignment_id`),
    in their original `ParameterDeclarationSet` order -- `app.agent2.parameters.builder` always
    declares them in one fixed role order per `kinetic_law_type` (Step 8's own docstring:
    MASS_ACTION -> [k]; REVERSIBLE_MASS_ACTION -> [kf, kr]; MICHAELIS_MENTEN -> [kcat, Km...,
    one per reactant participant, in participant order]; HILL -> [Vmax, Km, n]), so positional
    unpacking here is exactly as reliable as, and far simpler than, parsing each parameter's own
    slug text.
    """
    law_type = assignment.kinetic_law_type
    reactants = _reactant_species_ids(reaction)
    products = _product_species_ids(reaction)

    if law_type is KineticLawType.UNASSIGNED:
        return None, ()

    if law_type is KineticLawType.CUSTOM:
        # Step 9: preserve the reported text verbatim, never rewritten into Antimony or any
        # other symbolic form -- this package cannot safely reinterpret opaque curated text.
        expression = assignment.reported_rate_law_text
        return expression, _all_participant_species_ids(reaction)

    if law_type is KineticLawType.MASS_ACTION:
        _require_parameter_count(assignment, law_parameters, exactly=1)
        (k,) = (p.parameter_id for p in law_parameters)
        factors = " * ".join((k, *reactants)) if reactants else k
        return factors, tuple(reactants)

    if law_type is KineticLawType.REVERSIBLE_MASS_ACTION:
        _require_parameter_count(assignment, law_parameters, exactly=2)
        kf, kr = (p.parameter_id for p in law_parameters)
        forward = " * ".join((kf, *reactants)) if reactants else kf
        reverse = " * ".join((kr, *products)) if products else kr
        return f"{forward} - {reverse}", tuple(sorted(set(reactants) | set(products)))

    if law_type is KineticLawType.MICHAELIS_MENTEN:
        _require_parameter_count(assignment, law_parameters, at_least=1)
        kcat_param, *km_params = law_parameters
        kcat = kcat_param.parameter_id
        if not reactants or not km_params:
            # No curated reactant/Km pairing at all -- an honest, minimal fallback rather than
            # a fabricated substrate term.
            return kcat, tuple(reactants)
        terms = list(zip(reactants, km_params, strict=False))
        if len(terms) > 1:
            # Genuinely multi-substrate: no single combining algebra is scientifically
            # justified from independently-declared Km values alone. The law family is known
            # (law_type stays MICHAELIS_MENTEN) but the exact algebra is not -- expression=None
            # discloses that honestly, never a fabricated equation and never a non-expression
            # status marker in this field (see module docstring; the disclosure itself lives in
            # `_assumptions_for` and the dedicated ModelAssumption in `build_model_assumptions`).
            return None, tuple(reactants)
        (s, km) = terms[0]
        numerator = f"{kcat} * {s}"
        denominator = f"{km.parameter_id} + {s}"
        return f"{numerator} / ({denominator})", tuple(reactants)

    if law_type is KineticLawType.HILL:
        _require_parameter_count(assignment, law_parameters, exactly=3)
        vmax_param, km_param, n_param = law_parameters
        vmax, km, n = vmax_param.parameter_id, km_param.parameter_id, n_param.parameter_id
        substrate = " * ".join(reactants) if reactants else "S"
        expression = f"{vmax} * {substrate}^{n} / ({km}^{n} + {substrate}^{n})"
        return expression, tuple(reactants)

    raise ValueError(
        f"build_expression_and_species has no expression policy for law_type={law_type!r} "
        f"(assignment_id={assignment.assignment_id!r})"
    )


def _require_parameter_count(
    assignment: KineticLawAssignment,
    law_parameters: tuple[ParameterSpecification, ...],
    *,
    exactly: int | None = None,
    at_least: int | None = None,
) -> None:
    """A non-UNASSIGNED, non-CUSTOM law type always has a fixed, known minimum parameter
    count under the current `app.agent2.parameters` policy (Step 8's own docstring) -- a
    count mismatch here is a genuine structural inconsistency between the supplied
    `KineticLawAssignmentSet`/`ParameterDeclarationSet` (Increment 8 instructions, Step 30:
    "should not cause assembly errors unless the structure is inconsistent" -- this is exactly
    that case), never expected missing biology. Raises the package's own typed error rather
    than letting a bare tuple-unpack `ValueError` leak out with a confusing message."""
    count = len(law_parameters)
    if exactly is not None and count != exactly:
        raise ModelSpecificationReferenceError(
            f"kinetic-law assignment {assignment.assignment_id!r} "
            f"(law_type={assignment.kinetic_law_type.value}) expects exactly {exactly} "
            f"declared parameter(s), found {count}"
        )
    if at_least is not None and count < at_least:
        raise ModelSpecificationReferenceError(
            f"kinetic-law assignment {assignment.assignment_id!r} "
            f"(law_type={assignment.kinetic_law_type.value}) expects at least {at_least} "
            f"declared parameter(s), found {count}"
        )


def _assumptions_for(
    assignment: KineticLawAssignment, *, expression: str | None
) -> tuple[str, ...]:
    """Deterministic, template-based disclosure text -- never prose speculation."""
    reason_codes = ", ".join(sorted(code.value for code in assignment.reason_codes))
    sentences = [
        f"Kinetic-law assignment_source={assignment.assignment_source.value}; "
        f"reason_codes=({reason_codes})."
    ]
    if _is_tentative(assignment):
        sentences.append(
            "Tentative mass-action default: the underlying kinetic mechanism is not curated "
            "or confirmed. Never upgraded to a deterministic or curated law by this increment."
        )
    if assignment.unresolved_reasons:
        unresolved = ", ".join(sorted(code.value for code in assignment.unresolved_reasons))
        sentences.append(f"Unresolved: ({unresolved}).")
    if expression is None and assignment.kinetic_law_type is KineticLawType.MICHAELIS_MENTEN:
        # The only way a MICHAELIS_MENTEN assignment produces expression=None is the
        # genuinely-multi-substrate branch of build_expression_and_species -- the single-
        # substrate and no-curated-Km fallback paths both always return a non-None string.
        sentences.append(
            "Multi-substrate Michaelis-Menten mechanism: the law family is known, but no "
            "single combining algebra is asserted -- ordered-sequential, ping-pong, and "
            "random mechanisms all differ, and no curated or deterministic evidence "
            "distinguishes among them. The declared parameters (kcat, one Km per substrate) "
            "are preserved regardless. Serialization must be withheld until a concrete "
            "expression is available."
        )
    return tuple(sentences)


def _provenance_for(assignment: KineticLawAssignment) -> tuple[str, ...]:
    return (f"kinetic-law-assignment::{assignment.assignment_id}", *assignment.provenance_refs)


def materialize_kinetic_law(
    assignment: KineticLawAssignment,
    *,
    reaction: ReactionSpecification,
    law_parameters: tuple[ParameterSpecification, ...],
) -> KineticLawSpecification:
    """One `KineticLawAssignment` -> exactly one `KineticLawSpecification`, 1:1, always
    (Increment 8 instructions, Step 9: never omitted, including `UNASSIGNED` -- see docs/11 §6
    for why 1:1 coverage-parity with `KineticLawAssignmentSet` was chosen over omission).

    Never re-runs kinetic-law selection: `law_type` is copied verbatim from `assignment`, as is
    `assignment_source` and the catalytic-context target
    (`enzyme_state_id`/`protein_id`/`complex_id`) -- both first-class, verbatim copies since
    the pre-commit revision (see module docstring).
    """
    expression, species_ids = build_expression_and_species(assignment, reaction, law_parameters)
    return KineticLawSpecification(
        kinetic_law_id=f"kinetic-law::{assignment.assignment_id}",
        reaction_id=assignment.reaction_id,
        law_type=assignment.kinetic_law_type,
        assignment_source=assignment.assignment_source,
        expression=expression,
        parameter_ids=tuple(p.parameter_id for p in law_parameters),
        species_ids=species_ids,
        enzyme_state_id=assignment.enzyme_state_id,
        protein_id=assignment.protein_id,
        complex_id=assignment.complex_id,
        assumptions=_assumptions_for(assignment, expression=expression),
        provenance_refs=_provenance_for(assignment),
    )


def build_model_assumptions(
    *,
    kinetic_laws: tuple[KineticLawSpecification, ...],
    kinetic_law_assignments_by_kinetic_law_id: dict[str, KineticLawAssignment],
    parameters: tuple[ParameterSpecification, ...],
    candidate_boundary_ids: tuple[str, ...],
    kinetic_measurements: tuple[CuratedKineticMeasurement, ...] = (),
    reactions: tuple[ReactionSpecification, ...] = (),
) -> tuple[ModelAssumption, ...]:
    """Deterministic `ModelAssumption` records for eight disclosed-incompleteness categories:
    the four Increment 8 instructions, Step 18, name concretely (tentative mass-action
    defaults, PLACEHOLDER parameters, UNASSIGNED kinetic laws, unresolved MEDIUM candidate
    boundaries), one added in a later pre-commit revision (unresolved multi-substrate
    Michaelis-Menten mechanisms, §8), one added by the "Unresolved Kinetic Evidence
    Disclosure" increment (a kinetic measurement whose reaction applicability is unresolved,
    below), and one added by the "Substrate-Anchored Michaelis-Menten Eligibility Refinement"
    increment (a `MICHAELIS_MENTEN` law anchored to one real, uniquely-attributed Km for a
    multi-reactant reaction -- distinct from the plain multi-substrate-expression disclosure
    above: this one names the specific anchored substrate and source measurement, and fires
    even in the rare case a future `build_expression_and_species` extension might resolve an
    expression for it), and one added by the "Conservative Reversibility Default for
    Unresolved Reactions" increment (a reaction whose curated `reversible` is `None` is
    modeled as tentatively reversible for model-construction purposes -- see
    `app.agent2.reversibility` -- and that assumption is disclosed here explicitly, never
    silently). Never prose speculation, never a duplicate `assumption_id` (each is keyed
    deterministically off the one entity id it describes), never invented for a category
    this increment has no clean, already-computed signal for (see docs/11 §16 for what was
    deliberately not attempted, e.g. "known incompleteness of regulation context").

    ``kinetic_measurements``/``reactions`` both default to ``()`` for backward compatibility
    with any existing caller that does not (yet) pass them -- an empty tuple simply produces
    no assumptions of the corresponding new category, exactly as if that parameter did not
    exist."""
    assumptions: list[ModelAssumption] = []
    measurements_by_id = {m.id: m for m in kinetic_measurements}

    for law in sorted(kinetic_laws, key=lambda law: law.kinetic_law_id):
        assignment = kinetic_law_assignments_by_kinetic_law_id.get(law.kinetic_law_id)
        if assignment is not None and (
            KineticLawReasonCode.SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION
            in assignment.reason_codes
        ):
            (anchor_measurement_id,) = assignment.source_measurement_ids
            anchor_measurement = measurements_by_id.get(anchor_measurement_id)
            anchored_compound = (
                anchor_measurement.compound_id if anchor_measurement is not None else None
            )
            assumptions.append(
                ModelAssumption(
                    assumption_id=(
                        f"assumption::substrate-anchored-mm-approximation::{law.kinetic_law_id}"
                    ),
                    category="kinetics",
                    statement=(
                        f"Reaction {law.reaction_id} uses a substrate-anchored "
                        "Michaelis-Menten approximation: curated measurement "
                        f"{anchor_measurement_id} reports a Km uniquely and explicitly for "
                        f"reactant compound {anchored_compound!r}, but this reaction has more "
                        "than one reactant/co-substrate. This is a partial, lumped "
                        "approximation anchored to that one substrate only -- it is not a "
                        "claim that the reaction's full multi-substrate mechanism (ordered, "
                        "random, ping-pong, ...) has been established, no value is invented "
                        "for any other reactant, and no combining algebraic expression is "
                        "asserted (see MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED when this "
                        "reaction has more than one reactant)."
                    ),
                    related_entity_ids=tuple(
                        eid
                        for eid in (
                            law.reaction_id,
                            law.kinetic_law_id,
                            anchor_measurement_id,
                            anchored_compound,
                        )
                        if eid is not None
                    ),
                    source="app.agent2.kinetics",
                    reason_code=(
                        KineticLawReasonCode.SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION.value
                    ),
                )
            )
        if assignment is not None and _is_tentative(assignment):
            assumptions.append(
                ModelAssumption(
                    assumption_id=f"assumption::tentative-law::{law.kinetic_law_id}",
                    category="kinetics",
                    statement=(
                        f"Reaction {law.reaction_id} uses a tentative mass-action default "
                        "kinetic law; the actual mechanism is not curated or confirmed."
                    ),
                    related_entity_ids=(law.reaction_id, law.kinetic_law_id),
                    source="app.agent2.kinetics",
                    reason_code=KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT.value,
                )
            )
        if law.law_type is KineticLawType.UNASSIGNED:
            assumptions.append(
                ModelAssumption(
                    assumption_id=f"assumption::unassigned-law::{law.kinetic_law_id}",
                    category="kinetics",
                    statement=(
                        f"Reaction {law.reaction_id} has no assigned kinetic-law mechanism "
                        "(UNASSIGNED)."
                    ),
                    related_entity_ids=(law.reaction_id, law.kinetic_law_id),
                    source="app.agent2.kinetics",
                    reason_code=KineticLawType.UNASSIGNED.value,
                )
            )
        if law.law_type is KineticLawType.MICHAELIS_MENTEN and law.expression is None:
            # The only way a MICHAELIS_MENTEN law reaches this state is the genuinely-multi-
            # substrate branch of build_expression_and_species (see that function's own
            # docstring) -- the single-substrate and no-curated-Km fallback paths both always
            # produce a non-None expression.
            assumptions.append(
                ModelAssumption(
                    assumption_id=f"assumption::unresolved-multi-substrate::{law.kinetic_law_id}",
                    category="kinetics",
                    statement=(
                        f"Reaction {law.reaction_id}: the kinetic-law family is "
                        "Michaelis-Menten; multiple substrates are present; no justified "
                        "canonical multi-substrate algebra has been specified (ordered-"
                        "sequential, ping-pong, and random mechanisms all differ, and no "
                        "curated or deterministic evidence distinguishes among them); "
                        "serialization must be withheld until a concrete expression is "
                        "available. The declared parameters (kcat, one Km per substrate) are "
                        "preserved regardless."
                    ),
                    related_entity_ids=(law.reaction_id, law.kinetic_law_id),
                    source="app.agent2.kinetics",
                    reason_code="MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED",
                )
            )

    for spec in sorted(parameters, key=lambda p: p.parameter_id):
        if spec.is_placeholder:
            assumptions.append(
                ModelAssumption(
                    assumption_id=f"assumption::placeholder-parameter::{spec.parameter_id}",
                    category="parameters",
                    statement=(
                        f"Parameter {spec.parameter_id} remains a PLACEHOLDER value (not "
                        "curated, not calibrated). Requires future initialization/calibration."
                    ),
                    related_entity_ids=(spec.parameter_id,),
                    source="app.agent2.parameters",
                    reason_code="PLACEHOLDER",
                )
            )

    for boundary_id in sorted(candidate_boundary_ids):
        assumptions.append(
            ModelAssumption(
                assumption_id=f"assumption::candidate-boundary::{boundary_id}",
                category="modules",
                statement=(
                    f"Boundary {boundary_id} remains an unresolved MEDIUM candidate boundary "
                    "-- not cut in this decomposition, not discarded."
                ),
                related_entity_ids=(boundary_id,),
                source="app.agent2.modules",
                reason_code="MEDIUM",
            )
        )

    for measurement in sorted(kinetic_measurements, key=lambda m: m.id):
        if measurement.reaction_id is not None:
            continue
        # "Kinetic evidence exists but reaction applicability is unresolved" --
        # distinct from "no kinetic evidence exists" (which produces no
        # assumption of any kind, since there is nothing to disclose). This
        # measurement is, and remains, correctly excluded from
        # reaction-specific kinetic-law assignment (app.agent2.kinetics
        # .selector groups strictly by reaction_id) -- this assumption only
        # makes that already-true exclusion visible, never reverses it.
        # Protein applicability (protein_ids) is never treated as evidence of
        # reaction applicability here or anywhere else in this package.
        source_ref = (
            f"{measurement.source}:{measurement.source_id}"
            if measurement.source and measurement.source_id
            else "unknown source"
        )
        protein_ref = (
            ", ".join(measurement.protein_ids)
            if measurement.protein_ids
            else "no resolved protein"
        )
        assumptions.append(
            ModelAssumption(
                assumption_id=(
                    f"assumption::kinetic-measurement-reaction-unresolved::{measurement.id}"
                ),
                category="kinetics",
                statement=(
                    f"Kinetic measurement {measurement.id} ({measurement.parameter_type} = "
                    f"{measurement.value} {measurement.unit}, {source_ref}) exists and is "
                    "structurally preserved, but has no resolved reaction attribution -- it "
                    "is excluded from reaction-specific kinetic-law assignment until Agent 1 "
                    "(or another upstream source) establishes which reaction it applies to. "
                    f"Applicable protein(s): {protein_ref}; protein applicability is not, by "
                    "itself, evidence of reaction applicability, and is never used to infer "
                    "it."
                ),
                related_entity_ids=(measurement.id, *measurement.protein_ids),
                source="app.agent2.model_specification",
                reason_code=KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED,
            )
        )

    for reaction in sorted(reactions, key=lambda r: r.reaction_id):
        if not is_assumed(reaction.reversible):
            continue
        # "Conservative Reversibility Default for Unresolved Reactions" increment: Agent 1's
        # own curated reversible is None (evidence absent or conflicting, per Agent 1.x
        # Increment C.8) -- this reaction is modeled as tentatively reversible for model-
        # construction purposes only. The original curated value is never rewritten; this
        # assumption is the sole, explicit record that the reaction's own effective
        # reversibility is a modeling decision, not curated biochemical knowledge.
        assumptions.append(
            ModelAssumption(
                assumption_id=f"assumption::reversibility-assumed::{reaction.reaction_id}",
                category="kinetics",
                statement=(
                    f"Reaction {reaction.reaction_id} has no curated reversibility evidence "
                    "(reversible=None) -- it is modeled as tentatively reversible for model-"
                    "construction purposes only, never as curated biochemical fact. This "
                    "assumption never fabricates a reverse rate constant, equilibrium "
                    "constant, or other reverse-direction kinetic parameter, and is never used "
                    "as evidence for module-boundary isolation."
                ),
                related_entity_ids=(reaction.reaction_id,),
                source="app.agent2.reversibility",
                reason_code=REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE,
            )
        )

    return tuple(assumptions)


__all__ = [
    "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED",
    "build_expression_and_species",
    "build_model_assumptions",
    "materialize_kinetic_law",
]
