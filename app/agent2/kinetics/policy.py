"""Deterministic kinetic-law classification and eligibility rules (Increment 4).

Every rule here is a pure function over already-computed
``ReactionCharacterization``/``EnzymeStateCharacterization`` fields (or a
curated reported-rate-law string) -- never a reaction/protein/compound
name, never an LLM call, never a numeric parameter value (Increment 4
instructions, Step 29/31). See
``docs/07_kinetic_law_assignment.md`` for the full policy rationale.
"""

from __future__ import annotations

import re

from app.agent2.characterization.types import ReactionCharacterization, ReactionClass
from app.agent2.types import CuratedKineticMeasurement, KineticLawType

#: Mirrors ``app.agent2.parameters.policy.KM_TYPES`` exactly -- transcribed, never imported.
#: ``app.agent2.kinetics`` is consulted earlier in the pipeline than ``app.agent2.parameters``
#: and must not depend on it; this is the same "vocabulary exists in two places by
#: transcription, not cross-layer import" discipline already used throughout this project
#: (e.g. ``ParticipantRole``, transcribed verbatim across the two sibling repositories).
_KM_PARAMETER_TYPES = frozenset({"KM", "K_M", "MICHAELIS_CONSTANT"})


def is_km_measurement(measurement: CuratedKineticMeasurement) -> bool:
    """Whether ``measurement.parameter_type`` is recognized as a Michaelis constant.

    Case/whitespace-insensitive, exact-vocabulary match only -- never a
    substring or fuzzy check.
    """
    return measurement.parameter_type.strip().upper() in _KM_PARAMETER_TYPES

#: A bare product-of-terms expression -- letters, digits, underscore, dot, whitespace,
#: and ``*`` only. No ``+``, ``-``, ``/``, ``(``, ``)``, or ``^`` -- those indicate a
#: structure this trivial classifier does not attempt to recognize (Step 9: "do not
#: parse into a mathematical AST ... needed only to recognize a trivial exact
#: structural class"). No `eval`/AST parsing of curated text occurs anywhere here.
_SIMPLE_PRODUCT_PATTERN = re.compile(r"^[A-Za-z0-9_.\s*]+$")


def normalize_rate_law_text(text: str) -> str:
    """Trivial, lossless normalization used only to detect *identical* reported laws.

    Whitespace-collapsing and case-folding only -- never algebraic
    canonicalization (Increment 4 instructions, Step 10).
    """
    return " ".join(text.split()).casefold()


def classify_reported_rate_law_text(text: str) -> KineticLawType:
    """Deterministically classify curated reported rate-law text, or fall back to ``CUSTOM``.

    Recognizes, in order: an explicit "Hill" mention, an explicit
    "Michaelis"/"Menten" mention, a bare two-term difference of simple
    products (``REVERSIBLE_MASS_ACTION``), and a bare simple product
    (``MASS_ACTION``). Anything else is ``CUSTOM`` -- the reported text is
    preserved unchanged by the caller regardless of this classification.
    """
    lowered = text.lower()
    if "hill" in lowered:
        return KineticLawType.HILL
    if "michaelis" in lowered or "menten" in lowered:
        return KineticLawType.MICHAELIS_MENTEN
    parts = [part.strip() for part in text.split(" - ")]
    if len(parts) == 2 and all(_SIMPLE_PRODUCT_PATTERN.match(part) for part in parts):
        return KineticLawType.REVERSIBLE_MASS_ACTION
    if _SIMPLE_PRODUCT_PATTERN.match(text.strip()):
        return KineticLawType.MASS_ACTION
    return KineticLawType.CUSTOM


def is_simple_elementary_transition(rc: ReactionCharacterization) -> bool:
    """Deterministic-structural rule A/B (Increment 4 instructions, Step 13).

    True only for a reaction directly referenced by a curated
    ``EnzymeStateTransition`` (``ReactionClass.STATE_TRANSITION``) that
    carries no curated catalytic association at all
    (``ReactionClass.ENZYMATIC`` absent) -- i.e. a bare, non-enzymatic
    elementary state change. Structural rule C (a general non-enzymatic
    "explicitly modeled as elementary" transformation) is deliberately
    **not** implemented: nothing in ``ReactionCharacterization`` gives a
    deterministic signal for "explicitly modeled as elementary" beyond the
    state-transition case, and Step 13/14's own conservatism ("prefer
    fewer assignments... more UNASSIGNED") means this package does not
    guess one.
    """
    return (
        ReactionClass.STATE_TRANSITION in rc.reaction_classes
        and ReactionClass.ENZYMATIC not in rc.reaction_classes
    )


def michaelis_menten_eligible(
    rc: ReactionCharacterization, *, catalyst_known: bool, allostery_present: bool
) -> bool:
    """Conservative Michaelis-Menten heuristic eligibility (Increment 4 instructions, Step 15).

    The **stronger, more specific** heuristic: it wins over the tentative
    mass-action default (below) whenever it applies, but is deliberately
    narrower than that default so it is never assigned on weak grounds.
    All of the following must hold for the *specific catalytic context*
    being decided (a whole reaction, or one specific catalytic protein/
    complex/enzyme state):

    * the reaction is ``ENZYMATIC``;
    * exactly one reactant species and exactly one product species;
    * the catalyst for this context is explicitly known;
    * no allostery is tied to this context;
    * the reaction is not explicitly known to be reversible
      (``reversible is True`` conflicts with the simple irreversible
      Michaelis-Menten form; ``False``/``None`` do not);
    * the reaction has at most one catalytic enzyme state overall -- with
      two or more, no single context's kinetics may be assumed consistent
      with the others without curated confirmation (conservative reading
      of "no multiple distinct catalytic states with incompatible
      evidence": this package never assumes states are *compatible*
      either).

    Substrate/product identity is never inferred from a compound or
    species name -- only participant *counts* are used. Unlike the
    tentative mass-action default, an assignment made under this rule is
    **not** tentative (``KineticLawAssignment.is_tentative`` is ``False``)
    -- it is deliberately conservative precisely so that when it does
    fire, it represents real, reviewable justification rather than a
    blind default.
    """
    return (
        ReactionClass.ENZYMATIC in rc.reaction_classes
        and catalyst_known
        and len(rc.reactant_species_ids) == 1
        and len(rc.product_species_ids) == 1
        and not allostery_present
        and rc.reversible is not True
        and len(rc.catalytic_enzyme_state_ids) <= 1
    )


def substrate_anchored_michaelis_menten_eligible(
    rc: ReactionCharacterization, *, catalyst_known: bool, allostery_present: bool
) -> bool:
    """Structural preconditions for the substrate-anchored Michaelis-Menten approximation
    (Real Integration Pilot 2 Run 3 finding), consulted only after ``michaelis_menten_
    eligible`` has already returned ``False`` for the same context -- never a looser
    replacement for it, only a fallback for the specific case that rule's own single-
    reactant/single-product requirement rejects.

    Deliberately does **not** constrain reactant or product count at all: a Km
    characterizes one substrate's own binding affinity, independent of how many other
    reactants or products the reaction has (confirmed live: the real malonyl-CoA:[acp]
    S-malonyltransferase reaction has 2 reactants and 2 products). Every other safety
    condition is identical to ``michaelis_menten_eligible`` -- enzymatic, a known catalyst,
    no allostery tied to this context, not curated as reversible, at most one catalytic
    enzyme state -- this function only asks "is a substrate-anchored approximation
    *structurally* safe to consider," never "does a qualifying measurement actually exist"
    (see ``find_substrate_anchored_km`` for the evidence-dependent half of this decision).
    """
    return (
        ReactionClass.ENZYMATIC in rc.reaction_classes
        and catalyst_known
        and not allostery_present
        and rc.reversible is not True
        and len(rc.catalytic_enzyme_state_ids) <= 1
    )


def find_substrate_anchored_km(
    evidence: tuple[CuratedKineticMeasurement, ...],
    *,
    reactant_compound_ids: frozenset[str],
) -> CuratedKineticMeasurement | None:
    """The single, unambiguous ``Km`` measurement anchored to exactly one of this reaction's
    own reactant compounds -- or ``None`` when no such measurement exists, or the evidence is
    ambiguous or conflicting.

    Deterministic and conservative, mirroring
    ``app.agent2.kinetics.reaction_context``'s own "never choose among several" discipline:
    a measurement counts only when it is recognized as a ``Km`` (``is_km_measurement``), its
    ``compound_id`` is set, and that id is one of ``reactant_compound_ids`` -- never a
    product, never a bare name match. **More than one** such measurement -- whether two
    reports for the same reactant (conflicting evidence) or reports anchored to two different
    reactants (which would imply a fuller multi-substrate mechanism this function does not
    attempt to characterize) -- makes this return ``None`` rather than pick one arbitrarily.
    """
    anchored = [
        m
        for m in evidence
        if is_km_measurement(m)
        and m.compound_id is not None
        and m.compound_id in reactant_compound_ids
    ]
    if len(anchored) != 1:
        return None
    return anchored[0]


def tentative_mass_action_default_eligible(
    rc: ReactionCharacterization, *, catalyst_known: bool
) -> bool:
    """Tentative mass-action default eligibility (Increment 4 revision, approved policy).

    *"Mass action is the default executable kinetic-law structure when an
    enzymatic reaction has no curated reported law and no better
    justified kinetic-law assignment."* Consulted only after a curated
    reported law, the deterministic structural rule, and the conservative
    Michaelis-Menten heuristic have all already found nothing for this
    specific catalytic context (§9/§13/§15) -- this function never
    overrides any of them.

    Deliberately **broader** than the pre-revision enzymatic-mass-action
    fallback it supersedes: eligibility here requires only that the
    reaction is ``ENZYMATIC`` and that this context's catalyst is known.
    Unlike Michaelis-Menten, it is **not** disqualified by allostery, by
    the reaction having multiple catalytic enzyme states, or by
    ``reversible is True`` -- those conditions instead surface as
    additional ``unresolved_reasons`` on the resulting assignment
    (``REGULATORY_KINETIC_EFFECT_NOT_MODELED``/``MULTIPLE_CATALYTIC_STATES``
    /an explanation noting reversibility is not represented), never as a
    reason to withhold a runnable default. Every assignment this
    eligibility check leads to carries
    ``KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT`` and is
    ``is_tentative`` -- a deliberate, machine-readable epistemic downgrade
    from a curated fact or a deterministic/conservative-heuristic
    decision, never presented as either.
    """
    return ReactionClass.ENZYMATIC in rc.reaction_classes and catalyst_known


__all__ = [
    "classify_reported_rate_law_text",
    "find_substrate_anchored_km",
    "is_km_measurement",
    "is_simple_elementary_transition",
    "michaelis_menten_eligible",
    "normalize_rate_law_text",
    "substrate_anchored_michaelis_menten_eligible",
    "tentative_mass_action_default_eligible",
]
