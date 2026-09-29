# Agent 2 Antimony Generation Contract

## 1. Purpose

Increment 9 serializes the authoritative `ModelSpecification` (Increment
8) into Antimony source text -- one complete `FullAntimonyArtifact` for
the whole network, plus zero or more `ModuleAntimonyArtifact` records
derived from the same specification. **This increment serializes; it
does not reinterpret.** No kinetic-law type is reclassified, no
parameter value is changed, no boundary likelihood is recomputed, no
module cut is revisited, and no missing scientific fact is fabricated to
make the output "look complete." Every scientific and modeling decision
was already made by Increments 4-8; Increment 9's only job is to render
those decisions into deterministic Antimony text, refusing executable
status wherever a decision remains genuinely unresolved.

## 2. Pipeline position

```
Agent1CuratedKnowledgeView
    -> Whole-Network Assembly
    -> FullNetwork
    -> Reaction and Enzyme-State Characterization
    -> NetworkCharacterization
    -> Kinetic-Law Assignment
    -> KineticLawAssignmentSet
    -> Parameter Declaration / Initialization
    -> ParameterDeclarationSet
    -> Heuristic Boundary Assessment
    -> BoundaryAssessmentSet
    -> Module Decomposition
    -> ModuleDecompositionSet
    -> ModelSpecification Assembly
    -> ModelSpecification
    -> Antimony Generation (this increment)
    -> Agent2OutputPackage (FullAntimonyArtifact + ModuleAntimonyArtifact*)
    -> Agent 3 validation
```

Agent 1 is untouched by this increment; nothing in
`agent1-biochemical-curator` was read or modified. No Agent 3/4/5
behavior (validation, simulation, fitting, critique) was implemented.

## 3. ModelSpecification authority

`ModelSpecification` remains the single source of truth. Every fact this
increment serializes -- a species' compartment, a reaction's
participants/stoichiometry/reversibility, a kinetic law's type and
expression, a parameter's value and source, a module's membership, a
boundary interface's explicit semantics -- is read verbatim from it.
Nothing here recomputes `assemble_full_network`,
`characterize_full_network`, `assign_kinetic_laws`, `declare_parameters`,
`assess_boundaries`, or `decompose_network`; `app.agent2.antimony` never
imports any of them.

## 4. Public API

One function, `app.agent2.antimony.generate_antimony`:

```python
def generate_antimony(model: ModelSpecification) -> Agent2OutputPackage: ...
```

Pure and deterministic: no database, no filesystem, no network access, no
simulation, no fitting, no random ids, no wall-clock timestamps, no
mutation of `model`. Raises `UnsupportedAntimonySerializationError` if
`model` is not a `ModelSpecification`.

## 5. Output package

`Agent2OutputPackage` (already defined in Increment 1, unchanged in
shape) is populated with:

* `model_specification` -- `model`, unchanged, always present.
* `full_antimony` -- one `FullAntimonyArtifact`.
* `module_artifacts` -- one `ModuleAntimonyArtifact` per
  `model.module_specifications` entry.
* `contract_version` -- `AGENT2_CONTRACT_VERSION`.
* `boundary_assessments`/`module_decomposition` -- copied verbatim from
  `model` (required to be identical by `Agent2OutputPackage`'s own
  construction-time validation, Increment 1).

No other output. No new top-level type was needed.

## 6. Identifier mapping

`app.agent2.antimony.naming.build_identifier_map(model)` builds one
`IdentifierMap` per generation run, with four independent dictionaries --
`compartments`, `species`, `parameters`, and `reactions` -- each keyed by
the corresponding Agent 2 source id. Every category gets a fixed prefix
(`c_`/`s_`/`p_`/`J_`), so identifiers from different categories can never
collide with each other by construction; only within-category
collisions (two different source ids sanitizing to the same string)
need explicit resolution.

Sanitization (`_sanitize_base`): Unicode is transliterated to ASCII
(`unicodedata.normalize("NFKD", ...)`, standard library only, no external
dependency); every character outside `[A-Za-z0-9_]` becomes `_`; a
leading digit is prefixed with `_`; an empty result becomes `"id"`. A
small, deliberately conservative reserved-word list
(`ANTIMONY_RESERVED_WORDS`) appends a trailing `_` on an exact collision.

Collision resolution (`_resolve_category`): when two or more distinct
source ids sanitize to the same candidate, the one that sorts first *by
its own source id* keeps the bare candidate; the rest receive a
deterministic `_2`, `_3`, ... suffix in sorted order -- independent of
the order the caller supplied the ids in, and never using Python
`hash()` or a random UUID.

## 7. Reaction identifiers are keyed by `reaction_id`

**Pre-commit revision.** `reactions` is keyed by
`ReactionSpecification.reaction_id` -- **not**
`KineticLawSpecification.kinetic_law_id`. A biochemical reaction and a
catalytic kinetic contribution are not the same thing (see §11a for the
full architectural rule this section implements): one
`ReactionSpecification` always maps to exactly one Antimony reaction
identifier, regardless of how many distinct `KineticLawSpecification`
rows (catalytic contexts, e.g. one law for enzyme state `E` and a
separate one for `E_P` -- never collapsed, `docs/11` §11) reference it.
A kinetic law's own `kinetic_law_id` is never itself turned into a
second Antimony reaction identifier or a second stoichiometric reaction
-- it remains a plain, non-Antimony string used only in comments and in
`unresolved_kinetic_law_ids`/`unresolved_reaction_ids` metadata (§21).

An earlier draft of this increment keyed the reaction map by
`kinetic_law_id` instead, with a catalytic-context-qualified display
name (`J_r1_E`, `J_r1_E_P`). **Removed before commit**: that produced
*two* stoichiometrically identical Antimony reactions for one
biochemical reaction whenever it had two catalytic-context kinetic laws
-- silently asserting simultaneous parallel flux through the same
stoichiometry, a modeling claim no upstream contract or evidence
actually establishes (§11a).

## 8. Model declaration

```
model <sanitized_model_id>()

...

end
```

`app.agent2.antimony.naming.sanitize_model_name` sanitizes
`model.model_id` the same way as every other category (prefix `m_`).

## 9. Compartments

Emitted in `id_map.compartments`-sorted order. A known `initial_volume`
renders `compartment c_x = <value>;` with the unit as a comment; an
unknown one renders the bare `compartment c_x;` -- Antimony's legal
minimal syntax, never a fabricated numeric size (Step 9).

## 10. Species

Emitted in `id_map.species`-sorted order as `species s_x in c_y;`. If
`initial_amount` or `initial_concentration` is set (never both --
`SpeciesSpecification`'s own Increment 1 invariant), a second line
`s_x = <value>;` follows, tagged with an explicit comment naming which
one it is. **Known limitation, disclosed here and in §32**: this
increment does not assert an SBML-level `hasOnlySubstanceUnits`/bracket
(`[S]`) distinction in the Antimony syntax itself -- the amount-vs-
concentration fact is disclosed only via the comment, not via a verified
Antimony-native syntactic marker, since asserting one without a real
Antimony parser to confirm against would risk stating an unverified
syntax claim as fact. A species with neither value set is declared bare,
with no initial-value line -- never a fabricated concentration.

## 11. Enzyme-state species

Distinct catalytic contexts are already preserved by construction:
`KineticLawSpecification.enzyme_state_id`/`protein_id`/`complex_id` are
first-class (Increment 8), and each context an upstream increment did
not collapse keeps its own `KineticLawSpecification` row, with the
context disclosed in a comment (`catalytic_context=E_P`) wherever that
law appears -- in a resolved reaction's rate-line comment (§12), or
among the named contexts of an unresolved multi-context reaction (§11a).
This increment does **not** materialize enzyme states themselves as
Antimony species with their own dynamics:
`FullNetwork.enzyme_states`/`enzyme_modifications`/
`enzyme_state_transitions` remain curated supporting data, never turned
into a `SpeciesSpecification` or a reaction by any prior increment
(`docs/04` §3), and inventing state-interconversion reactions here would
be new biology this increment has no authority to add. `E`/`E_P` are
therefore never collapsed (the catalytic-context distinction is fully
preserved at the kinetic-law level), but they are also never
independently simulated as interconverting species -- a disclosed scope
boundary, not an oversight.

## 11a. Biochemical reaction identity vs. kinetic contribution

**Central architectural rule, corrected before this increment's first
commit:**

> A `KineticLawSpecification` represents a kinetic contribution or
> context, not a new biochemical reaction.
>
> One `ReactionSpecification` normally serializes to one Antimony
> reaction.
>
> Multiple kinetic contributions may be summed only when simultaneous
> applicability is explicitly established; otherwise the reaction
> remains non-executable rather than being duplicated or arbitrarily
> composed.

**The problem this corrects.** Increment 4 (Kinetic-Law Assignment) may
attach more than one `KineticLawAssignment` -- hence more than one
`KineticLawSpecification` -- to the same `reaction_id` when a reaction
has multiple, non-identical catalytic contexts (distinct enzyme states,
or distinct isozymes whose evidence was not identical enough to collapse
-- `app.agent2.kinetics.selector._build_contexts_with_evidence`). An
earlier Antimony Generation draft serialized each such law as its own,
separately-identified Antimony reaction sharing the same stoichiometry
(`J_r1_E: A -> B; v_E;` and `J_r1_EP: A -> B; v_EP;`). That is
**biologically wrong by construction**: two Antimony reactions with
identical stoichiometry produce two simultaneous stoichiometric fluxes,
mathematically equivalent to a single net rate of `v_E + v_EP` --
additive composition, asserted silently, merely because two kinetic-law
records happened to exist. Nothing upstream ever claimed the two
catalytic contexts act *simultaneously*; they may equally be alternative
isozymes, mutually exclusive enzyme states, or measurements from
different experimental conditions.

**Single-context reactions (the common case).** When a reaction has
exactly one `KineticLawSpecification`, nothing changes: it serializes to
exactly one Antimony reaction using the biochemical reaction id, the
reaction's own stoichiometry, and that law's own expression -- identical
to every case already described in §12-19.

**Multiple-context reactions.** `app.agent2.antimony.generator
.resolve_reaction_rate_expression` is the narrow, reaction-level
resolution helper this revision introduced. Given one
`ReactionSpecification` and every `KineticLawSpecification` that
references it, it returns one of:

* `RESOLVED_SINGLE` -- exactly one law, itself resolved (§15).
* `RESOLVED_COMPOSED` -- **implemented as of the "Multi-Context Catalytic
  Rate Composition, Stage 1" increment.** `_context_group_composability`
  (`app.agent2.antimony.generator`) treats a *homogeneous* group of two
  or more distinct, independently-resolved catalytic contexts -- all
  protein-general, or all complex-general, never a group containing any
  `enzyme_state_id` context and never a mixed protein/complex group -- as
  simultaneously applicable by the standard isozyme-summation convention:
  nothing in the current data model curates explicit mutual-exclusivity
  or co-expression signals between distinct isozymes/complexes, so real,
  distinct catalyst identity with no curated basis for exclusivity is the
  only defensible, non-fabricated default. Enzyme-state groups are
  deliberately excluded -- state populations are mutually exclusive
  fractions of one total enzyme pool and no population-fraction data
  exists yet to justify summing them; that remains Stage 2's job. A
  composable group in which at least one individual contribution is
  itself unresolved does **not** produce `RESOLVED_COMPOSED` -- it
  produces `UNRESOLVED_MULTIPLE_CONTEXTS` with reason
  `MULTIPLE_CATALYTIC_CONTEXTS_COMPOSABLE_BUT_UNRESOLVED`, never silently
  dropping the unresolved contribution and composing only the resolved
  remainder (see "Composition" below for the rendered expression shape).
* `UNRESOLVED_MULTIPLE_CONTEXTS` -- two or more laws share this
  `reaction_id`, and either (a) the group is not composable at all
  (reason `MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED` -- a mixed
  protein/complex group, any group containing an enzyme-state context, or
  any other case with no established simultaneous-applicability basis),
  or (b) the group is composable but at least one contribution is itself
  unresolved (reason `MULTIPLE_CATALYTIC_CONTEXTS_COMPOSABLE_BUT_
  UNRESOLVED`, see above). Distinct enzyme states (§11), or any other
  catalytic-context plurality that fails composability, land in case (a)
  exactly as before this increment. Never summed across incompatible
  contexts, never arbitrarily chosen among, never duplicated into
  multiple stoichiometric reactions.
* `UNRESOLVED_EXPRESSION` / `UNASSIGNED` -- exactly one law, itself
  unresolved for its own reasons (§15-17), unchanged from before this
  revision.

**Rendering.** Every reaction gets exactly one line, keyed by
`id_map.reactions[reaction_id]`:

```
J_r1: s_a -> s_b; <rendered expression>;  // reaction_id=r1 kinetic_law_id=... law_type=... reversible=... [catalytic_context=...]
```

for `RESOLVED_SINGLE`/`RESOLVED_COMPOSED`, or, for
`UNRESOLVED_MULTIPLE_CONTEXTS`:

```
J_r1: s_a -> s_b;  // reaction_id=r1 UNRESOLVED multiple catalytic contexts (k-E[E], k-EP[E_P]) reasons=(MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED) reversible=... -- simultaneous composition not established, rate withheld, see ModelSpecification.model_assumptions
```

-- naming every involved `kinetic_law_id` and its catalytic context, so
each contribution remains individually inspectable (enzyme_state_id/
protein_id/complex_id, assignment_source, parameter_ids, provenance are
all still present on the underlying `KineticLawSpecification` objects,
none of which this revision removes or collapses), never a fake rate
clause and never a second stoichiometric reaction. The machine-readable
reason code `MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED` is
always present in the comment, not only prose.

**Isozymes get the identical treatment** (§10 of the original increment
instructions): two protein-general catalysts with independent kinetic
contexts and no simultaneous-applicability signal resolve to
`UNRESOLVED_MULTIPLE_CONTEXTS` exactly like two enzyme states do --
co-expression, tissue-specificity, or mutual exclusivity are all
plausible and this package has no basis to prefer one interpretation.

**Composition** builds the total expression from already-resolved
contribution expressions with explicit parenthesization (e.g.
`(p_k1 * s_a) + (p_k2 * s_a)`), sorted by `kinetic_law_id` for
determinism (identical output regardless of construction/input order),
never algebraically simplified, and never invents a numeric weight not
already encoded upstream. The comment discloses every contributing
`kinetic_law_id`/context and the reason code
`MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY`. Real-data result for
the fresh-pilot fatty-acid pathway (no fresh Agent 1 curation): executable
reactions went from 5/38 to 38/38 -- every one of the 33 newly-executable
reactions is a pure protein-general isozyme case (0 of the real 75
kinetic-law assignments in this pathway carry `complex_id` or
`enzyme_state_id`), including the real MCT1/FAS1 malonyl-CoA:[acp]
S-malonyltransferase reaction, whose two isozyme contexts now compose
additively with each context's own real, distinct Km provenance
(`LITERATURE_DERIVED`/`AI_PREDICTED`) fully preserved.

## 12. Reactions

One line per **biochemical reaction** (§11a), never one line per kinetic
law:

```
J_r1: s_a + s_b -> s_c; <rendered expression>;  // reaction_id=... kinetic_law_id=... law_type=... reversible=... [catalytic_context=...]
```

Stoichiometry renders as `format_stoichiometry` -- the bare species id
when the coefficient is `1`, else `"<coefficient> <species_id>"` (Step
12 of the original increment instructions: never rewritten, never a
fabricated coefficient). `MODIFIER` participants never appear in the
arrow equation (only `REACTANT`/`PRODUCT` do); a modifier's role in the
rate law, if any, is already encoded structurally by the law's own
`species_ids`/`expression`, not by the stoichiometric equation.

## 13. Reversibility

`reaction.reversible` is read verbatim, never inferred or rewritten, and
disclosed as a `reversible=reversible|irreversible|reversible(assumed)`
comment (`_reversible_comment`, via `app.agent2.reversibility
.classify_reversibility_basis`). Encoding reversibility as a special
Antimony arrow token remains out of scope for the same reason as before
(no Antimony parser is available in this repository to verify a claimed
syntax construct, per Step 37 -- see §28).

**Conservative Reversibility Default for Unresolved Reactions**
(Agent 2 increment, motivated by Real Integration Pilot 2 Run 5):
an unresolved (`None`) curated `reversible` flag no longer disqualifies
a reaction's kinetic law from executable status on its own. Superseding
this section's original policy, `app.agent2.reversibility
.effective_reversible` treats `None` as tentatively reversible *for
model-construction purposes only* -- the reaction's own curated
`reversible` field is never mutated, and the assumption is disclosed
twice: via the non-blocking `REACTION_REVERSIBILITY_ASSUMED` reason in
`_resolve_law`'s own reasons list (informational only, never withheld
from executable status by itself), and authoritatively via a
`ModelSpecification.model_assumptions` entry (reason code
`REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE`; see
`docs/11_model_specification_assembly.md`). A law with an unresolved
`reversible` reaches `EXECUTABLE` if, and only if, its expression is
rendered and every referenced parameter already has a numeric value --
exactly the same bar an already-curated-reversible reaction must clear.
This assumption is purely structural: it never fabricates a reverse rate
constant, an equilibrium constant, or any other reverse-direction
kinetic parameter, so a `REVERSIBLE_MASS_ACTION` law with a genuinely
unresolved `kr` remains `NON_EXECUTABLE_UNRESOLVED_KINETICS` regardless
of reversibility basis. It is also never treated as boundary evidence:
only a curated `reversible is False` may support an irreversible-output
boundary rule (`app.agent2.boundaries.rules
.irreversible_output_isolation`); curated-reversible and assumed-
reversible reactions never can (see `docs/09_heuristic_boundary_
assessment.md`).

## 14. Kinetic-law serialization

`app.agent2.antimony.serializer.render_kinetic_law_expression` renders
`law.expression` into Antimony-safe identifiers via **exact,
closed-vocabulary token substitution** (`substitute_identifiers`): the
only tokens ever substituted are exactly `law.species_ids` and
`law.parameter_ids`, each mapped through the shared `IdentifierMap`,
longest-token-first so no token is ever partially matched. This is never
a blanket free-text `.replace()` -- every built-in expression template
(`app.agent2.model_specification.mapping.build_expression_and_species`)
is built purely by joining these exact tokens with fixed operators/
parens/whitespace, so an exact-match substitution over that closed
vocabulary can never mis-rewrite anything else. A defensive serializer-
integrity check (`_require_closed_vocabulary`) confirms every character
of the rendered text is drawn from the known-safe set; it should never
fail given a valid `ModelSpecification`.

## 15. Expression resolution

Two layers, not one (§11a): `app.agent2.antimony.generator._resolve_law`
decides whether **one kinetic law, considered alone**, is resolved;
`resolve_reaction_rate_expression` then decides whether **the reaction**
is resolved, which additionally requires that layer to have found
exactly one law for that reaction (§11a) -- a reaction with a fully
resolved individual law can still be reaction-level unresolved if a
sibling law shares its `reaction_id`.

A single `KineticLawSpecification` is resolved at its own layer only
when all three hold:

1. `law.expression is not None` **and** `law.law_type is not CUSTOM`
   (§17);
2. every `parameter_id` in `law.parameter_ids` has `has_value is True`
   (§19);
3. the owning `ReactionSpecification.reversible is not None` (§13).

If any one fails, or if the reaction has more than one kinetic law
(§11a), that reaction's rate is withheld -- the reaction's stoichiometric
equation is still emitted (`J_r1: s_a -> s_b;`), but with no trailing
rate clause, and a comment naming every reason code that blocked it
(`UNASSIGNED_KINETIC_LAW`, `UNRESOLVED_KINETIC_EXPRESSION`,
`CUSTOM_LAW_SYMBOL_MAPPING_UNAVAILABLE`,
`PARAMETER_VALUE_UNRESOLVED:<ids>`, `REACTION_REVERSIBILITY_UNRESOLVED`,
`MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED`, any combination).
Every involved `KineticLawSpecification.kinetic_law_id` is added to the
artifact's own `unresolved_kinetic_law_ids`, the reaction's own
`reaction_id` is added to `unresolved_reaction_ids`, and the artifact's
`readiness` becomes `NON_EXECUTABLE_UNRESOLVED_KINETICS`.

## 16. Unresolved expressions

Increment 8 established: **unresolved expression ≠ serializable
expression** (`docs/11` §8a). When `law.law_type != UNASSIGNED` and
`law.expression is None` (the unresolved multi-substrate
Michaelis-Menten case, or any future law family with the same shape),
this increment never fabricates a replacement -- no simplified algebra,
no `UNRESOLVED_MULTI_SUBSTRATE_MECHANISM`-style string sentinel anywhere
in the emitted text, and no silent mass-action or Michaelis-Menten
guess. The reaction's rate is withheld per §15, with reason code
`UNRESOLVED_KINETIC_EXPRESSION` in the comment; the full,
already-existing `ModelAssumption` (reason code
`MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED`) remains the authoritative
disclosure, referenced but never duplicated in the Antimony comment.

## 17. UNASSIGNED kinetic laws

Handled identically to §16 via the same withhold-the-rate mechanism,
tagged `UNASSIGNED_KINETIC_LAW` instead -- never a silent mass-action
default. `UNASSIGNED` remains a real, disclosed unresolved state, not an
error.

## 18. Tentative mass action

A `MASS_ACTION` law with `assignment_source=HEURISTIC` and
`is_tentative` reason codes (Increment 4), **as the sole kinetic law for
its reaction**, serializes exactly like any other resolved `MASS_ACTION`
law -- tentative status never blocks executable serialization (this is
precisely why the tentative default exists, to provide a runnable
baseline model). Its `assignment_source`/`law_type` are disclosed in the
same reaction-line comment as every other law (`law_type=MASS_ACTION`);
the tentative nature itself remains recorded in
`ModelSpecification.model_assumptions` (Increment 8), not re-asserted
redundantly in the Antimony comment.

**Multiple tentative contexts on one reaction are not a special case**:
§11a's `UNRESOLVED_MULTIPLE_CONTEXTS` policy applies exactly as it does
to any other catalytic-context plurality -- being tentative does not
make two contexts more or less composable, and this package never sums
them merely because both happen to carry the same tentative provenance.

## 19. CUSTOM laws

`CUSTOM`'s curated `reported_rate_law_text` is preserved verbatim
elsewhere in `ModelSpecification`, but this increment never attempts to
substitute identifiers into it: the text may use compound names,
bracket notation, or any other free-form convention with no structured,
closed-vocabulary symbol mapping this package can safely verify (Step
20). `render_kinetic_law_expression` returns `None` for every `CUSTOM`
law unconditionally; the reaction's rate is withheld per §15 (reason
code `CUSTOM_LAW_SYMBOL_MAPPING_UNAVAILABLE`). No `eval`, no AST
evaluation, no heuristic keyword-based substitution was implemented or
considered. **Known limitation**: a `CUSTOM` law can therefore never
reach `EXECUTABLE` status through this increment's policy, regardless of
how well-formed its curated text is -- a future increment could relax
this only by adding a genuine structured symbol-mapping contract
upstream (out of this increment's scope).

## 20. Parameters

Every `ParameterSpecification` referenced by at least one
`KineticLawSpecification` in the rendered body is declared, sorted by
`id_map.parameters`. A parameter with `has_value is True` renders
`p_x = <value>;` with `source`/`unit` as a trailing comment; one without
a value renders as a comment-only line naming its `parameter_id`/
`source` and stating explicitly that no numeric value was declared --
never a numeric line at all for it. `ParameterSpecification.value`/
`.source` are never mutated (§30).

## 21. PLACEHOLDER parameter policy

**No serialization-only placeholder numeric value is ever invented.**
Step 23 explicitly permitted one only under strict conditions (clearly
distinguished, deterministic, explicitly labeled, never mutating
`ModelSpecification`) and explicitly authorized withholding executable
generation instead when no approved placeholder value exists in current
docs/contracts -- and none does (`docs/08`'s `ParameterSource.PLACEHOLDER`
carries no numeric convention of its own). This increment takes that
conservative branch: a valueless parameter referenced by a kinetic law
makes that law's rate withheld (`PARAMETER_VALUE_UNRESOLVED:<ids>`,
§15), never `1.0` or any other guessed constant. This is a deliberate,
documented v1 policy decision, not an oversight -- a future increment
could introduce an explicit, versioned placeholder-value policy if a
later increment's needs justify one.

## 22. Units

Units are never converted, never dimensionally analyzed, and never used
to reject or adjust a value. `ParameterSpecification.unit`/
`CompartmentSpecification.volume_unit` are surfaced only as trailing
comments beside their numeric declaration. Agent 3 remains responsible
for real unit-consistency validation.

## 23. FullAntimonyArtifact

One artifact, containing:

* `model_id`/`model_specification_id` -- both `model.model_id`.
* `antimony_text` -- the complete, deterministic Antimony source (§8-20,
  ordering per §26).
* `generator_version` -- `ANTIMONY_GENERATION_POLICY_VERSION`.
* `provenance_refs` -- `("model-specification::<model_id>",)`.
* `readiness` -- `AntimonyArtifactReadiness.EXECUTABLE` when every
  **reaction** in the model is resolved (§11a/§15), else
  `NON_EXECUTABLE_UNRESOLVED_KINETICS`. `VIEW_ONLY` is not a legal value
  here (`FullAntimonyArtifact.__post_init__` rejects it) -- the full
  model is never merely a subset view.
* `unresolved_kinetic_law_ids` -- every blocking `kinetic_law_id`
  (including *every* law of an unresolved multi-context reaction, §11a),
  sorted; empty iff `readiness is EXECUTABLE`.
* `unresolved_reaction_ids` -- **added in this increment's pre-commit
  revision**: every blocking `reaction_id`, sorted; empty iff
  `readiness is EXECUTABLE`. Exists because
  `unresolved_kinetic_law_ids` alone cannot tell a downstream consumer
  *which reactions* are blocked without re-deriving the law-to-reaction
  mapping itself, and because a biochemical reaction, not a kinetic law,
  is the unit Agent 3 ultimately needs to know is (non-)executable
  (§11a).

`AntimonyArtifactReadiness` and these fields are
Increment-9-introduced additions to `app.agent2.types` (§33).

## 24. Module views vs. standalone module models

Two distinct concepts, both supported:

* **Module view** -- a textual subset of the full model's reactions/
  species/parameters/compartments for one `ModuleSpecification`. Always
  generated. Never independently claimed simulatable
  (`readiness=VIEW_ONLY` unless promoted to §25's standalone case).
* **Standalone module model** -- an independently-runnable Antimony
  model for a module, generated **only** when every one of the module's
  `boundary_interfaces` is explicit
  (`ModuleSpecification.has_explicit_boundary_interfaces`). A module
  view never silently becomes a standalone model.

A module's kinetic laws are identified by `law.reaction_id in
set(module.reaction_ids)` (`module.reaction_ids` is always populated and
validated by `ModelSpecification`) -- **not** by
`ModuleSpecification.kinetic_law_ids`, which Increment 7 deliberately
left unpopulated (`docs/10` §5/§ version-history); every kinetic law for
a module's own reactions is included this way regardless.

## 25. Standalone module eligibility and boundary interfaces

When `module.has_explicit_boundary_interfaces` is `True`:

* if every **reaction** among the module's reactions is resolved
  (§11a/§15) -- which requires each to have exactly one kinetic law and
  that law to itself be resolved, not merely each individual kinetic law
  considered in isolation -- a standalone model is generated
  (`readiness=EXECUTABLE`): the same body as the view, plus one block
  per `ModuleBoundaryInterface` -- `externally_controlled=True` species
  get a `const s_x;` declaration and, only if the interface itself
  already carries an `initial_value`, an `s_x = <value>;` line using
  that exact value (never a fabricated one); every interface's
  `role`/`direction`/`assumption`/`unit` is disclosed in a trailing
  comment.
* if any reaction among the module's reactions is unresolved -- **for
  any reason, including unresolved catalytic-context composition** -- the
  standalone text is **withheld entirely** (`standalone_antimony=None`,
  `readiness=NON_EXECUTABLE_UNRESOLVED_KINETICS`,
  `unresolved_kinetic_law_ids`/`unresolved_reaction_ids` both populated)
  -- never emitted as though it were runnable just because the
  interfaces were explicit. A module whose only problem is an unresolved
  multi-context reaction is therefore just as ineligible for a
  standalone model as one with a missing parameter value or an
  unresolved reversibility flag.

When `module.has_explicit_boundary_interfaces` is `False`, no standalone
model is attempted at all (`readiness=VIEW_ONLY`) -- no boundary
condition is ever invented to make a module "simulatable"
(`docs/01` §14, `.cursor/rules/03_scientific_safety.mdc`).

## 26. Shared identifier mapping

One `IdentifierMap` is built once per `generate_antimony` call and
reused for the full model and every module view/standalone artifact
(Step 32) -- the same Agent 2 entity always receives the same Antimony
identifier everywhere in one generation run. Per-law executability
verdicts (`_LawResolution`) are likewise computed once and reused.

## 27. Ordering and determinism

Within `_render_model`, sections always appear in this order: model
declaration, compartments, species, reactions, parameters, `end`
(assignments/rules/events: none exist upstream to serialize). Within
each section, entries are sorted by their own Antimony identifier
(`id_map.<category>[source_id]`) -- stable, deterministic, independent of
the input tuple's own order. Reaction participant ordering within one
reaction's equation preserves the original `ReactionSpecification
.participants` order (never re-sorted) -- filtered to `REACTANT`/
`PRODUCT` only, in that relative order. Two calls to `generate_antimony`
on the same `ModelSpecification` produce byte-identical
`antimony_text`/`antimony_view`/`standalone_antimony` (verified by
`tests/agent2/test_antimony_generation.py`).

## 28. Provenance and comments

Every reaction line carries `reaction_id`, its `reversible` disclosure,
and either one `kinetic_law_id`/`law_type`/(optional)`catalytic_context`
(a single-context reaction, §12) or every involved
`kinetic_law_id`/catalytic-context pair (an unresolved multi-context
reaction, §11a); every parameter line carries
`parameter_id`/`source`/(optional)`unit`; every compartment/species line
carries its own source id. Comments are concise and machine-stable --
never the full evidence text already recorded in
`ModelSpecification.model_assumptions`/`assumptions`, which remain the
authoritative disclosure a downstream reader should consult for the full
rationale.

## 29. Serializer validation

`app.agent2.antimony.validation.validate_serializer_integrity` runs
before any text is rendered, checking only serializer preconditions --
no two entities in one Antimony symbol-table category share an
identifier (`AntimonyIdentifierCollisionError`), and every kinetic-law/
module reference the generator is about to use actually resolves against
`model` (`AntimonyReferenceError`). Both should be unreachable given a
valid `ModelSpecification`, mirroring the identical "defensive backstop"
pattern already established in
`app.agent2.model_specification.assembler._validate_cross_artifact_references`.
**Never** mass-balance, connectivity, duplicate-reaction-biology,
disconnected-subnetwork, or unit-consistency analysis -- Agent 3's job.

## 30. Explicit non-goals

This increment does not, and must not:

* reassess kinetic laws, reinitialize parameters, reassess boundaries,
  or recompute module decomposition -- every fact is read, never
  recomputed;
* perform Agent-3-level model validation (mass balance, conservation
  laws, disconnected-subnetwork, full unit consistency);
* simulate a model or fit/calibrate a parameter (Agent 4);
* critique biological plausibility (Agent 5);
* import Agent 1's runtime, an LLM client, or a
  Tellurium/RoadRunner/libSBML/COPASI/`antimony` runtime dependency
  (`tests/agent2/test_antimony_scope.py` enforces this structurally);
* mutate `ModelSpecification` or any object it references.

## 31. Handoff to Agent 3

Agent 3 receives `Agent2OutputPackage.full_antimony`/`.module_artifacts`.
The mandatory invariant it can rely on: a `FullAntimonyArtifact`/
`ModuleAntimonyArtifact` whose `readiness` is
`NON_EXECUTABLE_UNRESOLVED_KINETICS` must never be treated as though its
`antimony_text`/`standalone_antimony` were a complete, runnable model --
`unresolved_reaction_ids` names exactly which biochemical reactions
blocked it, `unresolved_kinetic_law_ids` names every contributing
`KineticLawSpecification` involved (all of them, for an unresolved
multi-context reaction -- §11a), and the corresponding reaction lines in
the text itself carry no trailing rate clause. A `VIEW_ONLY` module
artifact must never be treated as independently simulatable regardless
of its own kinetics' resolution state. A reaction present in
`unresolved_reaction_ids` may still have every one of its individual
kinetic laws' own expressions/parameters/reversibility fully resolved --
`UNRESOLVED_MULTIPLE_CONTEXTS` is a reaction-level fact, not necessarily
visible from any single `KineticLawSpecification` in isolation.

## 32. Testing

`tests/agent2/test_antimony_generation.py` (49 tests) covers everything
described in the original increment's own test plan (hostile-input
identifier sanitization always producing a valid
`^[A-Za-z_][A-Za-z0-9_]*$` identifier; deterministic within-category
collision resolution; a minimal empty model; multiple reactions;
reversible/irreversible/unresolved-reversibility disclosure; verbatim
stoichiometric-coefficient preservation; exact-token-substitution
rendering for every built-in expression template; `CUSTOM`'s permanent
non-executable status; `UNASSIGNED` and an assigned-but-`expression=None`
law both withheld, never a fabricated equation; parameter serialization
for `CURATED`/`LITERATURE_DERIVED`/`PLACEHOLDER`, the last never
receiving a fabricated numeric value; module views; standalone-model
eligibility; full determinism; no mutation), **plus the pre-commit
revision's own dedicated coverage of §11a**: a single-context reaction
produces exactly one Antimony reaction, id derived from `reaction_id`;
two enzyme-state-specific contexts (`E`/`E_P`) on one reaction produce
no `J_r1_E`/`J_r1_EP` duplicates, no summed rate, a single unresolved
`J_r1:` line naming both `kinetic_law_id`s and contexts, and both ids
present in `unresolved_kinetic_law_ids` with `unresolved_reaction_ids ==
("r1",)`; two protein-general isozyme contexts resolve identically
(no arbitrary selection, no summation); multiple *tentative*
mass-action contexts on one reaction are not auto-composed merely
because both are tentative; a module view containing a multi-context
reaction still has exactly one reaction line, reusing the full-model
Antimony reaction id, and stays `VIEW_ONLY`; a module whose boundary
interfaces are fully explicit but whose sole reaction has unresolved
catalytic-context composition is still denied a standalone model
(`standalone_antimony=None`, `NON_EXECUTABLE_UNRESOLVED_KINETICS`); and
permuting the order of a reaction's multiple kinetic-law contexts
changes neither the Antimony reaction id, the unresolved metadata, the
comment, nor the overall text (order-independence).
`tests/agent2/test_antimony_scope.py` (11 tests) confirms, structurally
(via `ast`, not substring search), that `app.agent2.antimony` never
imports a Tellurium/RoadRunner/libSBML/COPASI/`antimony`/LLM/database/
network/random/Agent-1 dependency, never calls
`assess_boundaries`/`decompose_network`/`assign_kinetic_laws`/
`declare_parameters`/`assemble_full_network`/
`assemble_model_specification` itself, never defines a numeric-score
field, never calls the Python `hash()` builtin (checked via an actual
AST call node, not a bare-word docstring mention, since this package's
own docstrings legitimately explain that `hash()` was deliberately
avoided) -- backed by two real, executed generations confirming no
mutation and that the output package's `model_specification`/
`boundary_assessments`/`module_decomposition` are exactly the objects
supplied as input. `tests/agent2/test_output_contracts.py` gained seven
tests total confirming `FullAntimonyArtifact`/`ModuleAntimonyArtifact`'s
new `readiness` default values and their new cross-field validation
(`VIEW_ONLY` rejected on `FullAntimonyArtifact`; `EXECUTABLE` rejected
without a populated `standalone_antimony`;
`NON_EXECUTABLE_UNRESOLVED_KINETICS` rejected unless *both*
`unresolved_kinetic_law_ids` **and** `unresolved_reaction_ids` -- the
pre-commit revision's own addition -- are non-empty).
`tests/agent2/test_contracts.py` had one stale Increment-1 forbidden-name
entry (`"generateantimony"`) removed from its scope-guard list, since
this increment's own specification explicitly authorizes exactly that
public function name; every other forbidden substring (simulation,
fitting, calibration, critique, ...) remains enforced unchanged.

## 33. Known limitations

* The amount-vs-concentration distinction (§10) is disclosed only via a
  comment, not via a verified Antimony-native syntactic marker (e.g. a
  confirmed `[S]`-bracket convention) -- no Antimony parser exists in
  this repository to confirm one, and asserting an unverified syntax
  claim as fact would be worse than an honest, explicit comment.
* Reversibility (§13) is disclosed only via a comment, not via a
  dedicated Antimony arrow token -- the same "no parser to verify
  against" reasoning applies. Unresolved curated reversibility (`None`)
  is disclosed, not gated: it is modeled as tentatively reversible for
  structural purposes, distinguishable in the comment
  (`reversible(assumed)`) and in `ModelSpecification.model_assumptions`,
  never silently upgraded to curated evidence.
* `CUSTOM` laws (§19) can never reach `EXECUTABLE` status under this
  increment's policy, however well-formed their curated text is -- there
  is no structured, verified symbol mapping to substitute safely.
* No serialization-only placeholder numeric value exists for a
  valueless parameter (§21) -- a deliberate, documented v1 policy choice,
  not an oversight; Agent 4 remains the source of real calibrated
  values.
* A `ModuleSpecification`'s enzyme-state identities (§11) are disclosed
  in reaction comments but never materialized as independently dynamic
  Antimony species -- consistent with every upstream increment's own
  "enzyme states are supporting data, not structural graph elements"
  stance (`docs/04` §3).
* A reaction whose multiple catalytic-context kinetic laws are **not** a
  homogeneous, distinct-identity protein-general or complex-general group
  (§11a) -- a mixed protein/complex group, or any group containing an
  `enzyme_state_id` context -- can never reach `EXECUTABLE` status under
  this version's policy, however well-resolved each individual context's
  own expression/parameters/reversibility is: there is no current
  upstream signal this package can trust to justify summing enzyme-state
  populations or heterogeneous catalyst kinds, so it always withholds the
  rate instead. Enzyme-state composition, state-population fractions, and
  total-enzyme conservation remain Stage 2's job.

None of these block correctness: each is a disclosed, deliberate scope
boundary, never a silent wrong answer.

## 34. Final architectural rule

> `ModelSpecification` remains the authoritative Agent 2 model contract.

> Antimony artifacts are deterministic serializations of that
> specification.

> Antimony generation must never invent kinetics, parameters, module
> boundaries, or catalytic context that are absent from
> `ModelSpecification`.

> Module views are not standalone simulatable models unless all required
> interface semantics are explicitly specified.
