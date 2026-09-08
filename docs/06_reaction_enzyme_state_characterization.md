# Agent 2 Reaction and Enzyme-State Characterization Contract

## 1. Purpose

Increment 3 characterizes the complete biological/modeling context of
every reaction and catalytic enzyme state in the assembled `FullNetwork`
so that a later increment can choose kinetic-law structures from explicit
characterization rather than directly from raw curated data.
**Increment 3 describes what kind of biochemical/modeling situation each
reaction represents. It does not yet choose the mathematical rate law.**

## 2. Position in the pipeline

```
Agent1CuratedKnowledgeView
    -> Whole-Network Assembly (Increment 2)
    -> FullNetwork
    -> Reaction and Enzyme-State Characterization (Increment 3)
    -> ReactionCharacterization[] / NetworkCharacterization
    -> Kinetic-Law Assignment (future Increment 4)
    -> ...
```

Agent 1 is input-only for this increment. Nothing in
`agent1-biochemical-curator` was modified to implement Increment 3.

## 3. Architecture

`app/agent2/characterization/`:

* `__init__.py` -- public exports.
* `types.py` -- `ReactionClass`, `CharacterizationFlag`,
  `UnresolvedFeature`, `ReactionCharacterization`,
  `EnzymeStateCharacterization`, `NetworkCharacterization`.
* `classifier.py` -- deterministic `ReactionClass` assignment
  (`classify_reaction`).
* `characterization.py` -- the one public entry point,
  `characterize_full_network`.
* `validation.py` -- input-type guard and a defensive reference-resolution
  backstop.
* `errors.py` -- this package's own error hierarchy.

This is deliberately not a general reasoning engine: every function has a
narrow, named, deterministic job, mirroring `app.agent2.network`'s own
package shape.

## 4. The public entry point

```python
def characterize_full_network(network: FullNetwork) -> NetworkCharacterization: ...
```

Pure and deterministic: no database access, no connector calls, no
filesystem access, no network access, no LLM calls, and no Antimony
generation anywhere in its call graph.

## 5. Deterministic behavior, no LLM

Calling `characterize_full_network` twice with an equal `FullNetwork`
always returns an equal `NetworkCharacterization`. There is no free-form
biological inference anywhere in this package -- no "this is likely
Michaelis-Menten" commentary, no guessing from a reaction or protein name.
Every field is derived from explicit `FullNetwork` structure only.

## 6. `ReactionCharacterization`

One immutable record per curated reaction, holding: reaction identity and
name; participant/reactant/product/modifier species ids (participant
order preserved, never resorted); `reversible` (`bool | None`, passed
through unchanged); the reaction's `ReactionClass` tuple; catalyst
association ids and their protein/complex/enzyme-state buckets;
regulatory-interaction ids; allosteric-interaction ids; the enzyme-state
ids relevant to the reaction; enzyme-state-transition ids; general and
state-specific kinetic-measurement ids; the subset of those that carry a
reported rate law; `characterization_flags`; `unresolved_features`; and
`provenance_refs`.

It never includes a selected kinetic law, a parameter id or value, a
boundary likelihood, a module id, or Antimony text -- those are later
increments' responsibility.

## 7. `ReactionClass` vocabulary

`ENZYMATIC`, `TRANSPORT`, `EXCHANGE`, `SPONTANEOUS`, `STATE_TRANSITION`,
`UNKNOWN`. A class is only assigned when it can be identified
deterministically from explicit `FullNetwork` structure (§17-19).
`UNKNOWN` is the default -- it is added only when no other class applies,
never as an inferred guess alongside one.

## 8. `CharacterizationFlag` vocabulary

`HAS_CATALYST`, `MULTIPLE_CATALYSTS`, `STATE_SPECIFIC_CATALYSIS`,
`HAS_REGULATION`, `HAS_ALLOSTERY`, `HAS_MODIFIED_ENZYME_STATE`,
`HAS_STATE_TRANSITION`, `HAS_KINETIC_MEASUREMENTS`,
`HAS_STATE_SPECIFIC_KINETICS`, `HAS_REPORTED_RATE_LAW`,
`REVERSIBILITY_KNOWN`, `REVERSIBILITY_UNKNOWN`, `MULTIPLE_COMPARTMENTS`,
`PARTICIPANT_MODIFIERS_PRESENT`. No flag implies a mathematical modeling
decision -- there is no `USE_MICHAELIS_MENTEN`, `USE_HILL`,
`USE_MASS_ACTION`, `FAST`, or `SLOW` flag, and none will be added to this
vocabulary in this increment or any future one without a governing
specification change.

## 9. `UnresolvedFeature` vocabulary

`NO_CATALYST_INFORMATION`, `CATALYST_STATE_UNSPECIFIED`,
`NO_KINETIC_MEASUREMENTS`, `NO_STATE_SPECIFIC_KINETICS`,
`NO_REPORTED_RATE_LAW`, `REVERSIBILITY_UNKNOWN`,
`REGULATION_CONTEXT_INCOMPLETE`, `ENZYME_STATE_CONTEXT_INCOMPLETE`,
`PARTICIPANT_CONTEXT_INCOMPLETE`. Every value here means **"not
represented in the curated input,"** never **"does not exist
biologically."** A feature is only emitted when it is deterministically
absent or unresolved from `FullNetwork`'s own structure.

## 10. Catalyst characterization

Every reaction's `enzyme_association_ids` is preserved in full --
multiple independent catalysts and isozymes all remain visible; none is
ever chosen as preferred. Each association is classified into exactly one
of three buckets by which target field is set on the underlying
`ReactionEnzymeAssociation`: protein-general (`catalytic_protein_ids`),
complex-general (`catalytic_complex_ids`), or state-specific
(`catalytic_enzyme_state_ids`). State-specific catalysis is never inferred
from a state-specific kinetic measurement alone -- only an explicit
state-specific `ReactionEnzymeAssociation` sets
`catalytic_enzyme_state_ids`.

## 11. Enzyme-state characterization

`EnzymeStateCharacterization` exposes, for every curated `EnzymeState`:
its parent protein/complex identity, `state_type`, compartment, the
modifications attached to it, the allosteric interactions naming it, the
state transitions referencing it (as either endpoint), the reactions that
catalytically reference it, and the kinetic measurements reported for it.
An `EnzymeState` is never turned into a `SpeciesSpecification` here --
that mapping, if Agent 2 ever makes it, belongs to a later increment.

## 12. Modification characterization

`CuratedEnzymeModification` facts (modification type, residue/site,
modifying compound, multiple simultaneous modifications on one state) are
preserved structurally by id, grouped under their `EnzymeState`. A
modification is never mapped onto kinetic-law behavior, and its presence
never implies activation or inhibition -- that qualitative relationship,
if curated at all, is a separate `CuratedAllostericInteraction` fact.

## 13. Allostery characterization

Ligand identity, `effect` (e.g. `ACTIVATOR`/`INHIBITOR`), enzyme state,
site information, and provenance are preserved as separate structural
facts on `EnzymeStateCharacterization.allosteric_interaction_ids` and
surfaced on the reaction via `ReactionCharacterization
.allosteric_interaction_ids`. `effect` is never converted into a Hill
coefficient, an inhibition constant, or any other quantitative kinetic
consequence here -- the regulatory relationship and its (if curated)
quantitative measurement remain two separate facts even when they share
an `enzyme_state_id`.

## 14. State-transition characterization

`CuratedEnzymeStateTransition` records are preserved and attached both to
the two `EnzymeState`s they connect (`EnzymeStateCharacterization
.transition_ids`) and, when `reaction_id` is set, to that specific
reaction (`ReactionCharacterization.enzyme_state_transition_ids`,
`HAS_STATE_TRANSITION`). No model reaction is created for a transition
here -- that, if ever done, is later-increment behavior.

## 15. Kinetic-measurement characterization

For each reaction, `CuratedKineticMeasurement` records are gathered by two
independent signals -- `reaction_id` equality, and `enzyme_state_id`
membership in the reaction's `catalytic_enzyme_state_ids` -- and split
into `kinetic_measurement_ids` (`enzyme_state_id is None`, general) and
`state_specific_kinetic_measurement_ids` (`enzyme_state_id` set). Nothing
is ever averaged, unit-converted, ranked by applicability, or selected as
"the" measurement for a reaction: every relevant record's id is preserved,
independently.

## 16. Reported rate laws

`reported_rate_law_measurement_ids` surfaces the fact that one or more
gathered kinetic measurements carry a non-`None` `reported_rate_law`
string. The text itself is never parsed into a `KineticLawSpecification`
here -- it stays exactly as Agent 1 curated it, referenced by measurement
id only.

## 17. `ENZYMATIC` classification rule

Assigned if and only if `reaction.enzyme_association_ids` is non-empty.
Never inferred from an EC number, a reaction name, or any other free-text
signal. A reaction with multiple independent catalysts is still exactly
one `ENZYMATIC` reaction, not one per catalyst.

## 18. `TRANSPORT` classification rule

A conservative, deterministic candidate rule implemented in
`classifier._is_transport`: a reaction is `TRANSPORT` only when its
reactant-side and product-side species resolve to the identical set of
underlying curated compounds (`source_compound_id`) -- no chemical
conversion occurred -- **and** the reactant/product compound-compartment
pairings actually differ, i.e. at least one compound changes compartment.
If any participant's `source_compound_id` is unknown, or there is no
reactant or no product participant, the rule returns `False` and the
reaction is never classified `TRANSPORT` on this basis. This is the only
implemented candidate rule for `TRANSPORT`; no reaction is ever classified
`TRANSPORT` by name matching. `EXCHANGE` and `SPONTANEOUS` remain valid
vocabulary members but are never assigned by this increment -- no
reliable deterministic curated signal exists yet for either.

## 19. `STATE_TRANSITION` classification rule

Assigned if and only if some `EnzymeStateTransition.reaction_id` names
this reaction directly. Never inferred merely because the network happens
to contain enzyme states or transitions elsewhere.

## 20. Reaction-class representation

`ReactionCharacterization.reaction_classes` is a sorted tuple, not a
single field with an imposed precedence order -- a reaction may
legitimately be both `ENZYMATIC` and `TRANSPORT` at once (e.g. a
state-catalyzed transporter), and both classes remain visible rather than
one silently overriding the other. `UNKNOWN` is added only when the tuple
would otherwise be empty.

## 21. Preserved regulatory uncertainty

Absence of a curated `RegulatoryInteraction` or `AllostericInteraction`
never means "no regulation exists" or "this enzyme is not allosterically
regulated" -- it means only that no curated fact is available yet.
Because Agent 1's regulation-curation pipeline is known-incomplete,
`UnresolvedFeature.REGULATION_CONTEXT_INCOMPLETE` is emitted for **every**
reaction, unconditionally -- not only when a reaction happens to have zero
curated regulation. This systemic disclosure is also recorded once, in
plain language, on `NetworkCharacterization.assumptions`. No reason code
anywhere in this package ever states or implies "no regulation exists."

## 22. `NetworkCharacterization`

Holds `network_id`, the full sorted tuple of `reaction_characterizations`,
the full sorted tuple of `enzyme_state_characterizations`,
`characterization_policy_version`, `assumptions`, and `provenance_refs`.
No modules, kinetic laws, parameters, or Antimony text appear anywhere on
this type.

## 23. `EnzymeStateCharacterization`

Optional in principle (Increment 3 instructions, Step 25); implemented
here because it materially improves clarity -- without it, a reader would
have to re-derive "what modifications/allostery/transitions/kinetics
belong to this enzyme state" by re-scanning every `ReactionCharacterization`
in the network. See §11 for its fields.

## 24. Versioning

`REACTION_CHARACTERIZATION_POLICY_VERSION = "reaction-characterization-v1"`
(`app/agent2/version.py`) versions this package's own deterministic rule
set (e.g. the `TRANSPORT` candidate rule, the flag/unresolved-feature
emission rules) -- distinct from `AGENT2_CONTRACT_VERSION`, which versions
data shape. `AGENT2_CONTRACT_VERSION` was bumped `"0.3"` -> `"0.4"`
because `FullNetwork` gained the four enzyme-state-family fields and
`ReactionEnzymeAssociation`/`CuratedReactionEnzymeAssociation` gained
`enzyme_state_id` (§25), and a new output-contract package
(`app.agent2.characterization`) was introduced. `AGENT1_HANDOFF_VERSION`
is unchanged at `"1.2"` -- Agent 1 was not modified in this increment. See
`app/agent2/version.py` for the full, dated version history.

## 25. Discovered gap, fixed by extension

While inspecting the current handoff types (never assumed from a prior
spec), `CuratedReactionEnzymeAssociation` and the network-level
`ReactionEnzymeAssociation` were found not to carry `enzyme_state_id`,
despite Agent 1's real `ReactionEnzyme` row having gained the equivalent
column in Agent 1.x Increment B. This blocked state-specific catalyst
characterization (§10) entirely, so both types were extended -- by
addition only, never redesigned -- and `app.agent2.network.builder`/
`.assembler`/`.validation` were updated to carry the field through and
validate it. See `docs/05_whole_network_assembly.md` §17 and each type's
own docstring for the full account.

## 26. Explicit non-goals

This increment never: selects a `KineticLawSpecification`
(`MASS_ACTION`/`MICHAELIS_MENTEN`/`HILL`/`REVERSIBLE_MASS_ACTION`/
`CUSTOM`); declares or initializes a `ParameterSpecification`, or maps a
curated Km/Ki/kcat/Vmax value onto one; assesses a `BoundaryLikelihood` or
decomposes a module; generates Antimony text; or implements any Agent 3,
4, or 5 behavior. Structural tests in
`tests/agent2/test_characterization_scope.py` verify none of these
concepts appear anywhere in `app.agent2.characterization`.

## 27. Determinism and error handling

Every "set-like" id-tuple field (catalysts, regulation, allostery,
transitions, kinetic measurements, flags, unresolved features, both
top-level characterization tuples) is sorted before being returned, so
that two `FullNetwork`s equal up to internal tuple ordering always
characterize identically. Participant-order fields
(`participant_species_ids`/`reactant_species_ids`/`product_species_ids`/
`modifier_species_ids`) preserve the curated reaction's own original
order and are never resorted, since that ordering is itself a
semantically meaningful curated fact. Errors
(`ReactionCharacterizationError`, `CharacterizationReferenceError`,
`UnsupportedCharacterizationInputError`) are raised only for a structural
or programming inconsistency -- an incomplete curated fact always produces
an `UnresolvedFeature`, never an exception.

## 28. Final architectural rule

Reaction and Enzyme-State Characterization is the seam between "what
Agent 1 curated" and "what Agent 2 chooses to model." Everything on this
seam's near side (this increment) is a lossless, deterministic
reorganization of curated fact. Everything on its far side (kinetic-law
assignment, parameter declaration, boundary assessment, module
decomposition, Antimony generation) is a modeling choice, and belongs to
a later increment that has not yet been implemented.

---

> Increment 3 describes what kind of biochemical/modeling situation each
> reaction and catalytic enzyme state represents. It does not choose a
> rate law, does not declare a parameter, and does not assess a module
> boundary.
>
> Every curated catalyst, regulatory interaction, allosteric interaction,
> enzyme modification, state transition, and kinetic measurement is
> preserved and attached to the reactions and enzyme states it actually
> describes -- nothing is invented, nothing is collapsed, and nothing is
> dropped merely because it is incomplete.
>
> Absence of a curated fact is disclosed as an unresolved feature of the
> curated input. It is never asserted as absence of the underlying
> biology.
