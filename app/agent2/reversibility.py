"""Conservative reversibility default for unresolved reactions (Agent 2 increment).

Motivated by Real Integration Pilot 2 Run 5 and Agent 1.x Increment C.8:
Agent 1 now correctly, honestly leaves `ReactionSpecification.reversible`
`None` whenever curated evidence is absent or conflicting (never guessed).
For Agent 2's own model-*construction* purposes, an unresolved reaction
must still be usable -- a network where every reaction is either curated
`True`/`False` or silently blocked is not viable given today's real data
(Increment C.8 found zero real reactions currently resolve). This module
defines the one, narrowly-scoped modeling decision this increment adds:

    Agent 1 True  -> CURATED_REVERSIBLE    -> effective reversible = True
    Agent 1 False -> CURATED_IRREVERSIBLE  -> effective reversible = False
    Agent 1 None  -> ASSUMED_REVERSIBLE    -> effective reversible = True (tentative)

**This is a modeling assumption, never curated biochemical knowledge.**
`ReactionSpecification.reversible`/`ReactionCharacterization.reversible`
are never mutated or overridden anywhere in this codebase because of this
module -- every function here is a pure, read-only classification of an
already-curated value, always callable with the *original* `bool | None`,
never with a value this module has itself modified in place. Nothing here
is written back onto any `app.agent2.types`/`app.agent2.characterization`
dataclass field.

**Deliberately not used by kinetic-law eligibility or assignment**
(`app.agent2.kinetics.policy.michaelis_menten_eligible`/
`.substrate_anchored_michaelis_menten_eligible`, `app.agent2.kinetics
.selector._decide_structural`/`._decide_tentative_mass_action_default`/
`._decide_unassigned`): every one of those already reads the *raw*
`rc.reversible` value directly and is intentionally left untouched by this
increment (in scope explicitly excludes "change kinetic-law policy" and
"change substrate-anchored MM policy"). In particular, `michaelis_menten_
eligible`'s own `rc.reversible is not True` condition already treats
`None` exactly as conservatively as `False` for *eligibility* purposes --
changing it to consult `effective_reversible` (which turns `None` into
`True`) would flip that condition's outcome and silently regress the real,
already-validated malonyl-CoA case from Real Integration Pilot 2 Run 5.
This module's own effective-boolean is consulted only where a genuinely
binary *model-construction* decision is needed for a reaction whose
kinetic-law *type* has already been decided by those unmodified rules --
today, that is exactly one place: `app.agent2.antimony.generator`'s own
per-law/per-reaction resolution-readiness gate (see that module for the
wiring) -- never kinetic-law type selection, never parameter declaration,
never boundary assessment.

**Boundary/module safety invariant** (unaffected by this module,
confirmed by inspection, not changed): `app.agent2.boundaries.rules
.irreversible_output_isolation` already reads `facts.upstream_reversible
is False` specifically -- excluding both `True` and `None` already,
before this module ever existed. This module's own `ASSUMED_REVERSIBLE`
classification is never fed into boundary assessment at all; the
CandidateFacts population in `app.agent2.boundaries.assessor` reads
`ReactionSpecification.reversible` directly, unchanged. An assumption
made for model usability must never manufacture evidence for module
isolation -- see the regression tests in `tests/agent2/test_boundaries.py`.
"""

from __future__ import annotations

from enum import StrEnum

#: Stable, machine-readable reason code for the one ``ModelAssumption`` category this
#: module motivates (``app.agent2.model_specification.mapping.build_model_assumptions``).
#: A plain string, not a ``KineticLawReasonCode`` member -- that enum's own domain is
#: reasons a kinetic-law *assignment* made a particular choice for a reaction it was
#: already grouped under; this describes a reaction-level, model-construction-only
#: assumption, orthogonal to which kinetic-law type was assigned (mirrors
#: ``KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED``/
#: ``MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED``'s identical precedent).
REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE = "REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE"


class ReversibilityBasis(StrEnum):
    """The provenance of one reaction's reversibility value, for model-construction purposes.

    Purely a read-only classification of ``ReactionSpecification.reversible`` -- never stored
    on any contract type, never itself persisted; call ``classify_reversibility_basis`` again
    wherever this distinction is needed.
    """

    CURATED_REVERSIBLE = "CURATED_REVERSIBLE"
    CURATED_IRREVERSIBLE = "CURATED_IRREVERSIBLE"
    ASSUMED_REVERSIBLE = "ASSUMED_REVERSIBLE"


def classify_reversibility_basis(reversible: bool | None) -> ReversibilityBasis:
    """Classify one already-curated ``reversible`` value's provenance. Pure; never guesses."""
    if reversible is True:
        return ReversibilityBasis.CURATED_REVERSIBLE
    if reversible is False:
        return ReversibilityBasis.CURATED_IRREVERSIBLE
    return ReversibilityBasis.ASSUMED_REVERSIBLE


def effective_reversible(reversible: bool | None) -> bool:
    """The boolean to use for model-*construction* purposes only.

    ``True``/``False`` pass through unchanged; ``None`` (curated evidence
    absent or conflicting) becomes ``True`` -- a tentative modeling
    assumption, never a claim that reversibility was actually curated.
    Callers that need the original, unmodified curated value must read
    ``ReactionSpecification.reversible`` directly, never this function's
    return value -- this function is one-directional (curated -> model
    behavior) and is never used to reconstruct or infer the original
    curated fact.
    """
    return True if reversible is None else reversible


def is_assumed(reversible: bool | None) -> bool:
    """Whether ``reversible`` reflects this module's own tentative assumption (``None``),
    as opposed to an explicit curated value (``True``/``False``)."""
    return reversible is None


__all__ = [
    "REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE",
    "ReversibilityBasis",
    "classify_reversibility_basis",
    "effective_reversible",
    "is_assumed",
]
