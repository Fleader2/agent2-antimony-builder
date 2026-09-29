# Agent 2 Kinetic-Law Assignment Contract

## 1. Purpose

Increment 4 transforms deterministic `ReactionCharacterization` records
into explicit, provenance-aware `KineticLawAssignment` decisions, while
preserving the distinction between a curated reported rate law, a
deterministic structural choice, a heuristic modeling choice, and an
unresolved case that must remain `UNASSIGNED`. **The central architectural
rule: Agent 2 may assign a kinetic-law structure, but it must never
present a heuristic modeling choice as curated biochemical fact.**

## 2. Pipeline position

```
Agent1CuratedKnowledgeView
    -> Whole-Network Assembly
    -> FullNetwork
    -> Reaction and Enzyme-State Characterization
    -> NetworkCharacterization
    -> Kinetic-Law Assignment (this increment)
    -> KineticLawAssignmentSet
    -> Parameter Declaration / Initialization (future Increment 5)
    -> Heuristic Boundary Assessment
    -> Module Decomposition
    -> ModelSpecification
    -> Antimony Generation
```

Agent 1 is input-only for this increment; nothing in
`agent1-biochemical-curator` was modified to implement it.

## 3. Input contract

`assign_kinetic_laws(characterization: NetworkCharacterization, network: FullNetwork) -> KineticLawAssignmentSet`
-- **two arguments, not the single-argument
`assign_kinetic_laws(characterization) -> KineticLawAssignmentSet`
signature this increment's own instructions illustrated.** This is a
deliberate, documented deviation, not an oversight: `ReactionCharacterization`
carries kinetic-measurement *ids* only, by design
(`docs/06_reaction_enzyme_state_characterization.md` §16 -- "referenced by
measurement id only"). Preserving a reported rate law's exact text (§10)
requires the underlying `CuratedKineticMeasurement` records, which only
`FullNetwork` holds. This continues, one pipeline stage further, the
identical "characterization holds ids, resolve via the network" pattern
Increment 3 itself established for `FullNetwork` relative to the raw
Agent 1 handoff -- not a new architectural choice. `assign_kinetic_laws`
raises `KineticLawReferenceError` if `characterization.network_id !=
network.network_id`.

## 4. Output contract

`KineticLawAssignmentSet`: one immutable collection holding every
`KineticLawAssignment` decided for the given `NetworkCharacterization`,
plus `network_id`, `characterization_policy_version`,
`kinetic_law_policy_version`, `assumptions`, and `provenance_refs`. Every
reaction in the source characterization is covered by at least one
assignment -- never silently omitted (§7).

## 5. `KineticLawAssignmentSource`

`CURATED_REPORTED`, `DETERMINISTIC_STRUCTURAL`, `HEURISTIC`, `UNASSIGNED`
-- the provenance of *the modeling decision itself*, never a confidence
score. Deliberately a **new** enum, not a reuse of
`app.agent2.types.ParameterSource`: that enum answers "where did this
numeric parameter value come from," a different axis that would have
forced `CURATED` to mean both "Agent 1 reported this exact rate law" and
"Agent 1 reported this exact Km value" -- two claims this package must
keep separate.

The tentative mass-action default (§17) is filed under `HEURISTIC`, not a
fifth source value -- it genuinely is a heuristic decision (a real,
executable choice was made), and introducing a distinct source would
blur the actual axis this enum tracks. What distinguishes it from every
other `HEURISTIC` assignment is its reason code
(`KineticLawReasonCode.TENTATIVE_MASS_ACTION_DEFAULT`) and its derived
`KineticLawAssignment.is_tentative` marker (§6) -- `assignment_source`
alone is not enough to tell a tentative default apart from the
conservative Michaelis-Menten heuristic.

## 6. `KineticLawAssignment`

One decision per catalytic context of one reaction: `assignment_id`,
`reaction_id`, `kinetic_law_type` (`app.agent2.types.KineticLawType`,
reused unchanged), `assignment_source`, `policy_version`, then
`enzyme_state_id`/`protein_id`/`complex_id` (at most one set --
`KineticLawTarget`'s conceptual fields folded directly onto this type
rather than introduced as a separate nested type, per §12's own "or
equivalent" instruction), `reported_rate_law_text`,
`source_measurement_ids`, `provenance_refs`, `reason_codes`,
`unresolved_reasons`, `assumptions`, `explanation`. Never carries a
parameter id, a parameter value, a fitted quantity, a boundary field, or a
module field.

**`is_tentative`** is a pure, derived `@property` -- not a stored field
(smallest clean solution: a frozen, slotted dataclass gains no new slot
from a property, and the reason code is already the canonical signal).
`True` exactly when `reason_codes` contains `TENTATIVE_MASS_ACTION_DEFAULT`;
`False` for `CURATED_REPORTED`, `DETERMINISTIC_STRUCTURAL`, the
conservative Michaelis-Menten heuristic, curated `CUSTOM`, and
`UNASSIGNED`. `__post_init__` enforces that a `TENTATIVE_MASS_ACTION_DEFAULT`
assignment always has `assignment_source=HEURISTIC`,
`kinetic_law_type=MASS_ACTION`, and `KINETIC_MECHANISM_NOT_CURATED` in
`unresolved_reasons` -- a tentative default can never silently lose its
tentative marking. `unresolved_reasons` is otherwise disallowed (raises
`ValueError`) for `CURATED_REPORTED`/`DETERMINISTIC_STRUCTURAL` -- those
sources are, by construction, already resolved -- but is expected and
permitted for `HEURISTIC` (including, but not limited to, a tentative
default) and for `UNASSIGNED`.

## 7. `KineticLawAssignmentSet`

`network_id`, `characterization_policy_version`,
`kinetic_law_policy_version`, `assignments`, `assumptions`,
`provenance_refs`. **"One assignment per reaction" is the default, not an
absolute invariant**: a reaction with more than one distinct catalytic
context (most commonly, two or more `catalytic_enzyme_state_ids` that are
never collapsed, per §12's closing instruction) is covered by more than
one assignment. The actual invariant `assign_kinetic_laws` enforces is
"every reaction in the characterization has at least one assignment, and
no assignment names a reaction outside the characterization" -- checked
after construction and raised as `KineticLawReferenceError` if violated
(a defensive backstop; this should never actually happen given a correct
implementation).

## 8. `KineticLawType` vocabulary

Unchanged: `MASS_ACTION`, `MICHAELIS_MENTEN`, `HILL`,
`REVERSIBLE_MASS_ACTION`, `CUSTOM`, `UNASSIGNED`
(`app.agent2.types.KineticLawType`). No mechanism-specific subtype
(`ORDERED_BI_BI`, `PING_PONG`, `COMPETITIVE_INHIBITION`, ...) is added --
nothing in the curated input can deterministically distinguish them.

## 9. Assignment precedence

1. Curated reported rate law, if unambiguous for this catalytic context
   (§10-11).
2. Deterministic structural rule (§13).
3. Conservative Michaelis-Menten heuristic (§15) -- the stronger, more
   specific approved heuristic.
4. Tentative mass-action default (§17) -- broad, always explicitly
   tentative.
5. `UNASSIGNED` (§20) -- only when even a tentative assignment would be
   structurally inappropriate (no catalyst known at all for this
   context) or internally contradictory (materially conflicting curated
   reported laws for this context).

No later step ever overrides an earlier one: a heuristic (tentative or
conservative) never overrides a curated or structural decision, and the
tentative default never overrides a materially conflicting curated law --
each catalytic context is decided independently by trying these five in
order and stopping at the first that applies.

## 10. Curated reported laws

A reported rate law has highest precedence only when it is explicitly
present in curated data for the specific catalytic context being decided.
The exact text is preserved unchanged -- never rewritten, simplified, or
canonicalized. `classify_reported_rate_law_text` (`policy.py`)
deterministically recognizes, via case-insensitive keyword search and one
safe regex (never `eval`, never AST parsing of curated text): an explicit
"Hill" mention (`HILL`), an explicit "Michaelis"/"Menten" mention
(`MICHAELIS_MENTEN`), a bare two-term difference of simple products
(`REVERSIBLE_MASS_ACTION`), a bare simple product
(`MASS_ACTION`) -- anything else is `CUSTOM`, with the exact text
preserved either way. `Vmax*S/(Km+S)` classifies as `CUSTOM` under this
policy (it contains neither keyword and its `/`/`(`/`)` fall outside the
simple-product pattern) -- a deliberately conservative outcome; a future
increment may extend the classifier if a broader deterministic rule is
ever justified.

## 11. Multiple reported laws

Reported-law texts for the *same* catalytic context are compared after a
trivial normalization (`policy.normalize_rate_law_text`: whitespace
collapse and case-fold only, never algebraic canonicalization). If every
normalized text is identical, one shared assignment is made, its
`source_measurement_ids` covering every contributing measurement. If they
differ, the context is left `UNASSIGNED` with reason code
`MULTIPLE_DISTINCT_REPORTED_RATE_LAWS`, and `source_measurement_ids`
preserves every candidate id -- no arbitrary winner, no averaging, no
merging of equations.

## 12. State-specific applicability

A reaction's distinct catalytic contexts are: one per
`catalytic_enzyme_state_ids` entry (never collapsed, regardless of
whether their evidence agrees or conflicts), else one per distinct
general (protein/complex) catalyst -- collapsed into one shared,
reaction-level context only when every such catalyst's own reported-law
evidence is identical after normalization, otherwise kept separate
(§21/§26) -- else, when no catalyst is known at all, one reaction-level
context. A reported law tied to one `EnzymeState` never applies to a
sibling state: evidence-gathering matches a measurement to a context by
its own `enzyme_state_id`/`protein_id`/`complex_id` tag, and a measurement
tagged for one state is never visible to another state's context. An
untagged measurement (`reaction_id` only, no catalyst identity) is folded
in as fallback evidence only when the reaction has exactly **one**
catalytic context overall -- there being no other context it could
plausibly belong to; it is never presumptively attributed to one of
several distinct contexts. This per-context isolation is exactly what
makes independent tentative defaults possible (§17): each context's
kinetic-law decision, tentative or not, is made from only its own
evidence, so a curated law or a tentative default for one enzyme state
can never leak into a sibling state's decision.

## 13. Deterministic structural rules

Exactly one rule is implemented: a reaction directly referenced by a
curated `EnzymeStateTransition` (`ReactionClass.STATE_TRANSITION`) that
carries no curated catalytic association at all (`ReactionClass.ENZYMATIC`
absent) is a bare, non-enzymatic elementary state change --
`MASS_ACTION` (reason `SIMPLE_ELEMENTARY_TRANSITION`), or
`REVERSIBLE_MASS_ACTION` (reason `SIMPLE_REVERSIBLE_ELEMENTARY_TRANSITION`)
when `reversible is True`. The instructions' examples B (elementary
ligand binding/release) and C (a general "explicitly modeled as
elementary" non-enzymatic transformation) are **not implemented**: nothing
in `ReactionCharacterization` gives either a deterministic trigger beyond
the state-transition case already covered, and the increment's own
conservatism ("prefer fewer assignments... more UNASSIGNED") means this
package does not guess one into existence.

## 14. Heuristic rules

Two are implemented, in strict order, after curated/structural rules
have already found nothing for this catalytic context: the conservative
Michaelis-Menten heuristic (§15) and the tentative mass-action default
(§17). `HILL` is never heuristically assigned (§16). The two heuristics
are **not** symmetric: Michaelis-Menten is narrow and disqualified by
allostery, by the reaction having more than one catalytic enzyme state,
or by `reversible is True`; the tentative default is deliberately broader
and disqualified by *none* of those (§17) -- it exists precisely to catch
the reactions Michaelis-Menten's own conservatism excludes, rather than
leaving them `UNASSIGNED`.

## 15. Michaelis-Menten policy

The **stronger, more specific** heuristic -- it wins over the tentative
default whenever it applies (§9), and an assignment made under this rule
is never tentative (`is_tentative` is `False`). Requires, for the
specific catalytic context being decided: the reaction is `ENZYMATIC`;
exactly one reactant species and exactly one product species
(`policy.michaelis_menten_eligible`); the catalyst for this context is
explicitly known; no allostery is tied to this context; the reaction is
not explicitly known to be reversible (`reversible is True` conflicts
with the simple irreversible form); and the reaction has at most one
catalytic enzyme state overall (this package never assumes multiple
states share compatible kinetics without curated confirmation).
Substrate/product *identity* is never inferred from a compound or
species name -- only participant counts. If any condition fails,
Michaelis-Menten is never assigned heuristically; the tentative
mass-action default (§17) or `UNASSIGNED` follow instead. Michaelis-Menten
is never reinterpreted as curated -- it only ever carries
`assignment_source=HEURISTIC`, regardless of how conservative its own
eligibility rule is; the *only* way to reach `assignment_source=CURATED_REPORTED`
is an actual curated reported rate law (§10).

## 16. Hill policy

Never assigned heuristically, mandatorily: allostery is not equivalent to
cooperativity, and nothing in `ReactionCharacterization` distinguishes a
true Hill/cooperative relationship from ordinary allosteric regulation.
`HILL` is reachable only through curated-reported-law classification
(§10, an explicit "Hill" mention or a future extension of that
classifier) -- never as a structural or heuristic guess, and never as a
tentative default (the tentative default is always `MASS_ACTION`, never
`HILL`).

## 17. Mass-action policy: the tentative default

**Approved policy this section encodes:** *"Mass action is the default
executable kinetic-law structure when an enzymatic reaction has no
curated reported law and no better justified kinetic-law assignment.
This does not mean that mass action is treated as curated truth. It is a
deliberate provisional modeling assumption that allows the model to run.
The assignment must remain explicitly tentative so later simulation,
calibration, and model critique can identify and revisit it."*

**Why mass action, specifically.** Mass action is the underlying
mechanistic basis for elementary biochemical reaction steps; Michaelis-Menten
and other reduced/lumped rate laws are themselves derived from an
assumed elementary mass-action mechanism plus additional assumptions
(e.g. rapid equilibrium or steady-state approximations) that this
package has no curated grounds to assume hold here. Falling back to the
more fundamental form, rather than to a more specific reduced form, is
the more conservative choice when the actual mechanism is unconfirmed.

**Mechanistic basis vs. evidence status -- the distinction this section
exists to protect.** That mass action is *mechanistically* the right
default to reach for is a modeling-methodology claim, true independent
of any specific reaction. Whether *this specific reaction* actually
follows simple mass-action kinetics is a separate, unresolved empirical
question this package has no curated evidence to answer. Conflating the
two -- treating the mechanistic default as if it were a confirmed fact
about this reaction -- is exactly what `assignment_source=HEURISTIC`
plus a non-empty `unresolved_reasons` plus `is_tentative=True` exists to
prevent.

**Eligibility (`policy.tentative_mass_action_default_eligible`).**
Consulted only after a curated reported law, the deterministic
structural rule, and Michaelis-Menten have all already found nothing for
this specific catalytic context. Requires only that the reaction is
`ENZYMATIC` and that this context's catalyst is known -- deliberately
broader than the Michaelis-Menten heuristic and than the narrower,
pre-revision fallback this policy supersedes. It is **not** disqualified
by:

* **allostery** -- the assignment instead records
  `REGULATORY_KINETIC_EFFECT_NOT_MODELED` in `unresolved_reasons`, and its
  `explanation` names the specific gap. No allosteric algebra is ever
  invented; the regulatory kinetic effect is simply disclosed as
  unmodeled, not fabricated (§22).
* **multiple catalytic enzyme states** -- each state still receives its
  own, independent tentative default (never collapsed, per §12's own
  rule); the assignment additionally records `MULTIPLE_CATALYTIC_STATES`
  in `unresolved_reasons` (§21).
* **`reversible is True`** -- the tentative default stays plain
  `MASS_ACTION` with reversibility unresolved; it is never reinterpreted
  as `REVERSIBLE_MASS_ACTION` (that stays reserved for the structural
  rule, §18) and its `explanation` states plainly that the reverse
  direction is not represented by this form. This resolves the
  instructions' own choice ("MASS_ACTION with reversibility unresolved,
  or REVERSIBLE_MASS_ACTION if clearly supported") in favor of the first
  option -- "prefer the existing conservative structural rule... do not
  broaden reversible mass action casually."

It **is** still disqualified when no catalyst is known for this context
at all (a non-enzymatic reaction, or a context with no identifiable
catalyst) -- there, `UNASSIGNED` is the only structurally appropriate
outcome (§20).

**`TENTATIVE_MASS_ACTION_DEFAULT`.** Every assignment this eligibility
rule produces carries exactly `reason_codes=(TENTATIVE_MASS_ACTION_DEFAULT,)`,
`assignment_source=HEURISTIC`, `kinetic_law_type=MASS_ACTION`, and a
non-empty `unresolved_reasons` always containing
`KINETIC_MECHANISM_NOT_CURATED` (never cleared merely because a runnable
default was assigned -- Increment 4 revision, Step 3) plus, when
applicable, `REGULATORY_KINETIC_EFFECT_NOT_MODELED`/
`MULTIPLE_CATALYTIC_STATES`. Its `explanation` is deterministic template
text (no LLM) stating plainly: the assignment is provisional; no curated
law and no stronger heuristic applied; mass action provides an
executable default structure so the model can run; the assignment should
be revisited by later simulation, calibration, or critique if model
behavior disagrees with experimental data.

**Superseded pre-revision fallback.** This tentative default replaces
the original, narrower `ENZYMATIC_MECHANISM_UNKNOWN_MASS_ACTION_FALLBACK`
heuristic (which was disqualified by the same conditions as
Michaelis-Menten and so almost never fired for a reaction with any
regulatory or multi-state complexity) -- that reason code has been
removed from `KineticLawReasonCode` since it never shipped in a committed
contract.

**Future Agent 4/Agent 5 use.** A tentative assignment is exactly the set
of decisions later increments should prioritize for scrutiny: Agent 4's
simulation/calibration can flag a tentative assignment whose fitted
behavior disagrees with experimental data, and Agent 5's critique can
flag one whose biology (regulation, multiple catalytic states) the
tentative form admittedly does not represent. `is_tentative` (§6) is the
single machine-readable filter both can use without re-deriving it from
`reason_codes` themselves.

## 18. Reversible mass-action policy

Used only by the structural rule (§13) for an explicitly `reversible`
bare elementary state transition. Never automatically applied to every
`reversible=True` reaction, and never applied by the tentative default
either (§17) -- reversibility alone is not sufficient grounds (Increment
4 instructions, Step 18/22).

## 19. `CUSTOM` policy

Used only when a curated reported rate law is present but does not
classify into a built-in type (§10). No new custom algebra is ever
fabricated; `CUSTOM` always carries the exact preserved reported text via
`reported_rate_law_text`.

## 20. `UNASSIGNED` policy

**Now the narrower of the two "safety valve" outcomes** (the tentative
default, §17, absorbs most of what previously reached `UNASSIGNED` for
an ordinary enzymatic reaction). `UNASSIGNED` still wins, deterministically,
in exactly these cases:

* **no catalyst known at all for this context** -- a non-enzymatic
  reaction, or a context with no identifiable catalyst -- because even a
  tentative mass-action default requires a known enzymatic catalyst
  (§17); `unresolved_reasons` records `INSUFFICIENT_CURATED_CONTEXT`.
* **materially conflicting curated reported laws** for this specific
  catalytic context -- `MULTIPLE_DISTINCT_REPORTED_RATE_LAWS` -- because
  a genuine curated contradiction is never resolved by falling back to
  an assumption; no tentative or otherwise heuristic assignment is ever
  produced once a curated conflict is detected for a context (§11).

Both are structural/evidentiary reasons a *safe* provisional assignment
cannot be made at all -- not merely reasons the *best* assignment is
uncertain (that softer uncertainty is exactly what the tentative default,
§17, now absorbs instead of forcing `UNASSIGNED`). `UNASSIGNED` is never
treated as failure -- it is a central safety feature of this package,
preserved for the cases where even a tentative assignment would be
structurally inappropriate or internally contradictory.

## 21. Multiple catalysts / isozymes

Handled within evidence-gathering (§12): as of the "Isozyme-Aware
Catalytic Context Resolution" increment, two or more distinct
protein/complex-general catalysts on the same reaction are **never**
collapsed into one shared context -- not even when every catalyst's
evidence is identical, including the common case where neither catalyst
has any evidence at all. Distinct catalyst identity is a biological
fact independent of what happens to be curated for it; matching (or
absent) `reported_rate_law` text is never treated as grounds for
treating two catalysts as interchangeable. Each catalyst always
receives its own, independent kinetic-law assignment -- including its
own tentative mass-action default when it has no stronger evidence,
rather than a forced global `UNASSIGNED` (§17). The only form of
cross-catalyst evidence sharing is explicit: a measurement whose own
authoritative plural `protein_ids` names more than one of the
reaction's catalysts is copied into each of those catalysts' own
contexts (never merging the contexts themselves, never invented when
not explicitly present). Distinct catalyst/state identity
(`enzyme_state_id`/`protein_id`/`complex_id`) is always preserved on each
assignment, tentative or not.

This does not, by itself, change the separately-documented
substrate-anchored Michaelis-Menten eligibility rule (§15/`policy
.find_substrate_anchored_km`), which still requires exactly one anchored
Km measurement per context -- a catalyst whose own, now-correctly-
isolated evidence still contains more than one Km measurement (even if
they agree) remains ineligible and falls through to the tentative
mass-action default. That is a distinct, known limitation, tracked
separately.

## 22. Regulation/allostery policy

Presence of curated regulation or allostery alone never implies a
specific kinetic-law structure. Allostery still fully disqualifies the
Michaelis-Menten heuristic (§15, unchanged) -- never a shortcut to `HILL`
or any other type -- but no longer forces `UNASSIGNED` on its own: a
catalytic context with curated allostery and no specific law still
receives a tentative mass-action default (§17), with
`REGULATORY_KINETIC_EFFECT_NOT_MODELED` recorded in `unresolved_reasons`
to disclose that the allosteric/regulatory kinetic contribution is not
represented by the assigned plain mass-action form. No allosteric
equation (Hill, competitive/noncompetitive inhibition, or otherwise) is
ever invented to fill that gap -- the gap is disclosed, never papered
over. A reaction's own `regulation_ids` are not otherwise consulted by
this package.

## 23. Kinetic measurements without rate laws

Km/Ki/kcat/Vmax-type measurements that carry no `reported_rate_law` are
never used, by themselves, to select a kinetic-law structure --
`reported_rate_law is None` measurements are simply invisible to §10's
curated-law logic. No parameter magnitude is ever inspected or compared
by this package (Increment 4 instructions, Step 29).

## 24. Expression/template policy

**This increment constructs zero `KineticLawSpecification` or
`ModelSpecification` instances.** `KineticLawAssignment` is a new,
decoupled decision record; it does not carry an `expression` field at all
(unlike `KineticLawSpecification`, whose own `__post_init__` requires a
non-blank `expression` for every non-`UNASSIGNED` `law_type` --
`KineticLawAssignment` has no analogous requirement, since it never claims
to be a complete Antimony-ready specification). A future increment that
declares parameters may convert a `KineticLawAssignment` into a real
`KineticLawSpecification` once it has a symbolic-template or expression
policy of its own to satisfy that field; inventing one here, without
parameters to back it, would risk presenting a placeholder as though it
were a modeling commitment. `KineticLawSpecification`/`ModelSpecification`
and `app.agent2.types.ParameterSource` are entirely untouched by this
increment.

## 25. Uncertainty preservation

Allosteric regulation is never converted into Hill kinetics (§16).
`ENZYMATIC` never automatically becomes Michaelis-Menten (§15's explicit
eligibility list). `reversible=True` never automatically becomes
`REVERSIBLE_MASS_ACTION` (§18) -- not even by the tentative default,
which stays plain `MASS_ACTION` with reversibility explicitly unresolved
(§17). Every non-curated choice carries an explicit `reason_codes` entry
and a factual `explanation` string tracing exactly why it was made.

> A tentative mass-action assignment is not a claim that the reaction has
> been experimentally established to follow elementary mass-action
> kinetics. It is a provisional executable modeling choice used when no
> more specific supported law is available. Its tentative status remains
> machine-readable so downstream calibration and critique can prioritize
> it for reassessment.

This package never implies that every reaction in a network is
biologically elementary -- only that, absent better curated or
structural grounds, mass action is the conservative executable
placeholder for an enzymatic reaction's *unconfirmed* mechanism. A
tentative assignment's `unresolved_reasons` and `explanation` always say
so explicitly; nothing about `assignment_source=HEURISTIC` or
`kinetic_law_type=MASS_ACTION` alone would.

> The default model should be runnable wherever a structurally safe
> provisional kinetic-law assignment can be made.

## 26. Determinism

`assign_kinetic_laws` is a pure function: the same
`(NetworkCharacterization, FullNetwork)` pair always produces an equal
`KineticLawAssignmentSet`. Catalytic contexts are enumerated from
`ReactionCharacterization`'s own already-sorted id tuples
(`catalytic_enzyme_state_ids`/`catalytic_protein_ids`/
`catalytic_complex_ids`); `source_measurement_ids` are always
`tuple(sorted(...))`; a shared reported-law text is chosen by the lowest
measurement id among ties, never by handoff/collection order.

## 27. Validation

`require_network_characterization`/`require_full_network`
(`validation.py`) confirm input types.
`assign_kinetic_laws` raises `KineticLawReferenceError` if the two
inputs' `network_id`s disagree, or if the computed assignments do not
cover exactly the characterization's own reaction set -- both defensive
backstops that should never actually trigger given a correct
implementation, exactly as `app.agent2.characterization.validation`
established for Increment 3. `KineticLawAssignment.__post_init__` enforces
target exclusivity (at most one of `enzyme_state_id`/`protein_id`/
`complex_id`), the `kinetic_law_type`/`assignment_source` UNASSIGNED
agreement, and that `CURATED_REPORTED` always carries non-blank
`reported_rate_law_text`.

## 28. Explicit non-goals

This increment never: declares a `ParameterSpecification`, selects or
initializes a numeric parameter value, compares Km/kcat/Ki magnitudes or
timescales, assesses a `BoundaryLikelihood`, decomposes a module,
generates Antimony, or implements Agent 3 validation, Agent 4
simulation/fitting, or Agent 5 critique. Structural tests in
`tests/agent2/test_kinetics_scope.py` verify none of these concepts
appear anywhere in `app.agent2.kinetics`.

## 29. Handoff to Increment 5

Increment 5 (Parameter Declaration / Initialization) consumes
`KineticLawAssignmentSet` to declare and initialize the actual parameters
each assigned (non-`UNASSIGNED`) kinetic law needs. It is the first stage
permitted to construct a real `ParameterSpecification`, and the first
permitted to construct a real `KineticLawSpecification` carrying an actual
expression and `parameter_ids` (§24).

## 30. Testing

`tests/agent2/test_kinetics.py` covers assignment-source vocabulary and
immutability; curated single/multiple/conflicting reported laws with
exact text and measurement-id preservation; the deterministic structural
rule (with and without reversibility); the conservative Michaelis-Menten
heuristic's exact eligibility boundary; the tentative mass-action
default's full shape (reason code, unresolved reasons, explanation
wording, `is_tentative`) and its broadened eligibility under allostery,
multiple catalytic states, and `reversible=True`; the full five-step
precedence chain end to end; `UNASSIGNED` as normal output for its two
remaining triggers (no catalyst at all; materially conflicting curated
laws, including a per-state conflict that does not block a sibling
state's own tentative default); state-specificity (a law, or the absence
of one, for one `EnzymeState` never applies to a sibling -- each gets its
own independent tentative default when neither has a curated law);
multiple-catalyst/isozyme collapsing and non-collapsing under a tentative
default; `is_tentative` across every `assignment_source`/reason-code
combination this package produces; the `KineticLawAssignment`
construction invariants tying `TENTATIVE_MASS_ACTION_DEFAULT` to
`HEURISTIC`/`MASS_ACTION`/`KINETIC_MECHANISM_NOT_CURATED`; and
determinism under permuted order-insensitive collections.
`tests/agent2/test_kinetics_scope.py` covers structural scope-safety
(§28), including that no `ParameterSpecification`/boundary/module/
Antimony construction was introduced by this revision.

## 31. Known limitations

The reported-rate-law classifier is intentionally narrow (§10) --
divide/parenthesized forms like a textbook `Vmax*S/(Km+S)` classify as
`CUSTOM` rather than `MICHAELIS_MENTEN` unless the text itself names it.
The Michaelis-Menten heuristic refuses any reaction with more than one
catalytic enzyme state, even when the states' evidence would not
actually conflict -- a deliberately conservative stance this increment
does not attempt to loosen (the tentative default, by contrast,
deliberately does apply per state in that case, §17/§21). The tentative
mass-action default, being broad by design, will fire for many ordinary
enzymatic reactions with merely under-curated (not contradictory)
kinetics -- this is intentional (§17), but means `is_tentative` must be
consulted by any downstream stage that cares about the difference between
"assigned" and "assigned with real justification"; `assignment_source`
alone is not enough (§5/§6). Neither limitation blocks correctness: they
shift more reactions toward `CUSTOM`/a tentative default rather than a
fully-justified assignment, which downstream increments must already
handle.

## 32. Substrate-Anchored Michaelis-Menten Eligibility Refinement

Motivated by Real Integration Pilot 2 Run 3: a real SABIO-RK `Km` was
uniquely, deterministically reaction-attributed (by
`app.agent2.kinetics.reaction_context`, a separate, unmodified increment)
to the real malonyl-CoA:[acp] S-malonyltransferase reaction. That
reaction has 2 reactants and 2 products, so it never satisfied the
single-substrate Michaelis-Menten heuristic (§13-15), and fell to the
tentative mass-action default -- whose sole parameter (a generic rate
constant) is never populated from curated evidence by policy (§17). The
real `Km` was correctly never fabricated into it, but was also never
used at all.

`policy.substrate_anchored_michaelis_menten_eligible`/
`policy.find_substrate_anchored_km` add one new, narrower eligibility
path, consulted only after `michaelis_menten_eligible` has already
returned ineligible for the same context (never a looser replacement for
it): a multi-reactant reaction now receives `MICHAELIS_MENTEN`
(`KineticLawReasonCode.SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION`)
when, and only when, **exactly one** curated `Km` measurement is
unambiguously anchored -- by resolved `compound_id`, never a bare name --
to exactly one of that reaction's own reactant compounds. Every other
safety condition `michaelis_menten_eligible` already enforces (enzymatic,
a known catalyst, no allostery, not curated reversible, at most one
catalytic enzyme state) is required identically here; only the
reactant/product *count* constraint is relaxed, and only when real,
unambiguous evidence justifies it. A `Km` anchored to a product, to two
different reactants, or reported twice with conflicting values for the
same reactant all leave the reaction ineligible -- never an arbitrary
choice among them.

Unlike the plain heuristic, this assignment carries
`source_measurement_ids` (the one real measurement it is anchored to) --
it is positively evidence-driven, not a purely structural decision, but
it is also **not** `is_tentative` (that property checks only for
`TENTATIVE_MASS_ACTION_DEFAULT` -- a deliberately distinct epistemic
category, see that reason code's own docstring).

Nothing downstream needed to change: `app.agent2.parameters
.builder._declare_michaelis_menten` already declares one `Km` slot per
reactant, populated only from a measurement naming that exact compound,
for any reactant count; `app.agent2.model_specification.mapping
.build_expression_and_species` already withholds a fabricated combining
algebra whenever more than one reactant participates
(`MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED`, §24). This refinement only
changes *which* reactions reach that already-correct machinery.
`build_model_assumptions` gained one additional, more specific disclosure
block naming the anchored substrate and source measurement, layered
alongside (never replacing) that existing generic disclosure.

## 33. Plural Protein Context Matching for Kinetic Evidence

Motivated by Real Integration Pilot 2 Run 4: the real, uniquely
reaction-attributed malonyl-CoA `Km` (§32) was confirmed structurally
eligible for the substrate-anchored Michaelis-Menten approximation, but
was still silently excluded from its own reaction's evidence entirely.
`_matches_context`/`_is_untagged` (Increment 4 code) matched a
measurement's catalyst identity by equality against
`CuratedKineticMeasurement.protein_id` -- the legacy, non-authoritative
field (see that field's own docstring: "a legacy convenience field, not
authoritative for protein applicability -- use `protein_ids` instead").
The real reaction's own two curated catalysts did not include the
measurement's legacy `protein_id` (which happened to name a different
real protein than either catalyst), even though the measurement's
authoritative `protein_ids` already, correctly, named one of them.

**Fix**: `_matches_context` now checks `context.protein_id in
measurement.protein_ids` (membership, never equality against the legacy
field); `_is_untagged` now checks that `protein_ids` is empty (never that
the legacy field is `None`). `CuratedKineticMeasurement.__post_init__`
already guarantees `protein_ids` is a non-empty superset of `protein_id`
whenever the latter is set, so this is a pure narrowing-removal, not a
new fallback: a legacy single-protein measurement (`protein_id=P1`,
`protein_ids=(P1,)`) matches exactly as before; a plural measurement now
also matches through any of its other, equally-applicable entries.
Complex/enzyme-state matching is unchanged (Agent 1 has no plural
equivalent for either).

**No evidence broadening beyond intersection.** This still requires a
non-empty intersection between the measurement's `protein_ids` and the
specific catalyst a context is for -- it never treats plural protein
context as reaction-level evidence, never infers `reaction_id` from
`protein_ids`, and never spreads one measurement across every reaction a
listed protein catalyzes (§7 of the corresponding increment's own
instructions). When a single measurement's `protein_ids` now matches
*more than one* of a reaction's own catalysts, and those catalysts'
evidence collapses into one shared context (§12's own pre-existing
collapse rule, unchanged), the measurement is deduplicated into exactly
one evidence record for that shared context -- never counted twice.

## 34. Final architectural rule

Curated rate laws are preserved as evidence-backed modeling inputs.
Deterministic and heuristic kinetic-law choices are modeling decisions
and must be labeled as such. A tentative mass-action default keeps the
model runnable in the absence of better-justified knowledge, but is never
presented as curated or otherwise confirmed fact -- it remains
machine-readable as provisional for exactly as long as it is. Agent 2 may
still leave a reaction `UNASSIGNED` when even a tentative assignment
would be structurally inappropriate or internally contradictory.
Parameter declaration and numerical initialization occur only after
kinetic-law assignment.
