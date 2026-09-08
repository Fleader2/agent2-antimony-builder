# Whole-Network Assembly (Increment 2)

## 1. Purpose

This document describes Increment 2: the first executable stage of Agent
2. It maps an `Agent1CuratedKnowledgeViewContract` onto a `FullNetwork` --
the single authoritative structural graph every later increment (kinetic-
law assignment, parameter declaration, boundary assessment, module
decomposition, Antimony generation) will build on. It implements no
algorithm beyond that mapping: no kinetic law is assigned, no parameter is
declared, no boundary is assessed, no module is decomposed, and no
Antimony or SBML is generated.

## 2. Architecture

```text
Agent1CuratedKnowledgeViewContract
        |
        v
app.agent2.network.validation.validate_handoff   (pre-assembly checks)
        |
        v
app.agent2.network.builder.*                     (pure mapping functions)
        |
        v
app.agent2.types.FullNetwork(...)                (final construction + validation)
```

Three modules, each with one responsibility:

* `app/agent2/network/errors.py` -- the error hierarchy this package
  raises (`NetworkAssemblyError` and four subclasses), all subclassing
  `ValueError`.
* `app/agent2/network/types.py` -- assembly-internal helper types only
  (`SpeciesKey`, `build_species_id`, `build_enzyme_association_id`). Never
  a core domain contract -- those all live in `app.agent2.types`, per
  Increment 1's own convention, which this increment extends rather than
  duplicates.
* `app/agent2/network/validation.py` -- `validate_handoff`, a pre-
  assembly pass over the raw handoff that raises a specific,
  handoff-referencing error for a genuine structural problem, before any
  `app.agent2.types` object is constructed.
* `app/agent2/network/builder.py` -- pure, deterministic mapping
  functions, one per structural category, assuming `validate_handoff`
  already ran successfully.
* `app/agent2/network/assembler.py` -- `assemble_full_network`, the one
  public entry point, orchestrating the above and constructing the final
  `FullNetwork` (whose own `__post_init__` re-validates reference
  integrity as defense in depth).

## 3. The public entry point

```python
def assemble_full_network(
    handoff: Agent1CuratedKnowledgeViewContract,
) -> FullNetwork: ...
```

Deterministic and pure: no database, no filesystem, no network access, no
connector, no simulation, no randomness, no wall-clock time. Calling it
twice with an equal handoff always returns an equal `FullNetwork`.

## 4. Deterministic behavior

Every id this package produces is a pure function of curated input:

* `compartment_id`/`reaction_id` reuse Agent 1's own id directly.
* `species_id` is `build_species_id(compound_id, compartment_id)` --
  `f"{compound_id}::in::{compartment_id}"`.
* `association_id` (for a synthesized `ReactionEnzymeAssociation`, see §6)
  is `build_enzyme_association_id(reaction_id, index_within_reaction)`,
  where the index counts only that reaction's own curated associations in
  the handoff's own order.
* `network_id`/`name` are a pure function of `handoff.organism_id`
  (`"network::<organism_id>"` or `"network::unscoped"`) -- never random or
  time-based, so assembling the same unscoped handoff twice yields the
  identical network id too.

No dict iteration order or set ordering ever influences an id or the
final tuple ordering that matters for equality: species/reactions/
associations are built by iterating the handoff's own tuples in order.

## 5. Species identity policy

Species identity is **compound + compartment**, never compound alone.
`glucose` in the cytosol and `glucose` in the mitochondrion become two
distinct `SpeciesSpecification` instances, keyed by `SpeciesKey(compound_id,
compartment_id)`. The same `(compound_id, compartment_id)` pair referenced
by many participants (in one reaction or several) collapses to exactly
one `SpeciesSpecification` -- deduplicated by an ordered dict keyed by
`SpeciesKey`, never by re-running a query. A compound never referenced by
any reaction participant gets no species at all (`FullNetwork.species` is
derived only from participation, per Increment 1's own `FullNetwork` type
responsibility).

A participant with `compartment_id=None` is a hard failure
(`MissingCompartmentReferenceError`, §11) -- never a fabricated
compartment, since `SpeciesSpecification.compartment_id` is a required
field and this increment must never invent compartments.

## 6. Reaction identity policy

One `ReactionSpecification` per curated reaction, reusing the curated
reaction's own id directly as both `reaction_id` and `source_reaction_id`.
`reversible` is copied verbatim, including `None` (never inferred).
`participants` are built by filtering `handoff.reaction_participants` by
`reaction_id`, preserving handoff order and multiplicity -- two
participants naming the same species and role are never deduplicated.
`kinetic_law_id` is always `None`: kinetic-law assignment is entirely out
of this increment's scope. A curated reaction with zero participants
fails `ReactionSpecification`'s own pre-existing "at least one
participant" rule (Increment 1) -- this increment never pads a
participant list to satisfy it.

## 7. Compartment policy

One `CompartmentSpecification` per curated compartment, `source_scope`
always `AGENT1_CURATED`, `source_entity_id` set to the same id as
`compartment_id`. Never invented, merged, or renamed -- exactly one output
row per input row, even if two curated compartments share an identical
name (`test_compartments_never_merged_even_if_same_name`).

## 8. Reaction participant policy

`role`, `stoichiometry`, and the derived `species_id` are the only three
fields `ReactionParticipantSpecification` carries (Increment 1's own
shape, unchanged). `stoichiometry` is copied verbatim -- never
normalized, never inferred, never defaulted -- and Increment 1's existing
"`stoichiometry > 0` for every role" rule still applies unmodified; a
curated participant that violates it fails construction rather than being
silently clamped. `role` is mapped from Agent 1's free-string vocabulary
(`REACTANT`/`PRODUCT`/`MODIFIER`) onto `ParticipantRole`; anything else
raises `UnknownParticipantRoleError` rather than defaulting to `MODIFIER`
or being dropped. No cofactor (ATP, ADP, water, ...) is ever added that
was not already a curated participant.

## 9. Enzyme-association handling

Every curated `CuratedReactionEnzymeAssociation` becomes one
`ReactionEnzymeAssociation`, attached both to `FullNetwork.enzyme_associations`
and, by id, to its reaction's `ReactionSpecification.enzyme_association_ids`.
**Discovered gap**: the curated handoff record itself carries no id (unlike
`CuratedRegulatoryInteraction`/`CuratedKineticMeasurement`, which do) --
see §14. No enzyme is ever chosen as preferred; two associations naming
different proteins for the same reaction (isozymes) are both preserved,
each its own row. No enzyme complex, catalytic mechanism, or isozyme
relationship is ever inferred -- `protein_id`/`complex_id`/`relationship`
are copied verbatim, including when both `protein_id` and `complex_id`
are absent (mirroring `CuratedReactionEnzymeAssociation`'s own "expected,
never enforced" stance on exactly-one-of).

## 10. Regulation handling

Every curated `CuratedRegulatoryInteraction` is attached to
`FullNetwork.regulatory_interactions` completely unchanged -- the exact
same immutable type the Agent 1 handoff itself uses, never copied into a
near-duplicate Agent-2-side type, never reinterpreted, classified, or
expanded. `effect` is never mapped onto a closed vocabulary. A
convenience index, `ReactionSpecification.regulatory_interaction_ids`,
attaches a regulation's id to every reaction it names as *either*
regulator or target when that endpoint's type is `"reaction"` -- so a
reaction that regulates another reaction is indexed on both ends. This
index is purely a lookup convenience; the authoritative record is always
`FullNetwork.regulatory_interactions` itself.

## 11. Kinetic-measurement attachment policy

Every curated `CuratedKineticMeasurement` is attached to
`FullNetwork.kinetic_measurements`, completely unchanged (Agent 1's own
immutable type, reused as-is -- never a near-duplicate mirror). Attachment
is **at the network level only** -- `ReactionSpecification` has no
`kinetic_measurement_ids` field, and nothing in this package assigns a
measurement to a reaction, chooses a "preferred" measurement among several
reporting the same parameter type, estimates a parameter from one, or
constructs a `ParameterSpecification` from one. Two measurements reporting
different values for the same parameter type are both preserved,
independently -- never averaged or reconciled. Parameter mapping is
explicitly Increment 4's responsibility (`docs/02_agent1_handoff_contract.md`
§9, §4), not this one's.

## 12. Confidence and provenance preservation

Confidence: `CuratedKineticMeasurement.confidence_score`/
`.confidence_class` are carried through completely unmodified, because
the type itself is attached unchanged (§11) -- nothing in this package
ever reads, recomputes, or reinterprets them. No other structural type
this increment produces carries a confidence field at all (compartments/
species/reactions/enzyme associations have none in either Agent 1's
handoff or Agent 2's own domain contracts); no confidence is fabricated
for them.

Provenance: every `CompartmentSpecification.source_entity_id`,
`SpeciesSpecification.source_compound_id`, and
`ReactionSpecification.source_reaction_id` names the exact Agent 1 id the
structural object was built from. No additional `provenance_refs` string
is invented -- none is specified anywhere in the handoff contract for
compartments/compounds/reactions, and inventing a format not requested
would misrepresent whose provenance scheme it is. `SpeciesSpecification`'s
"Agent 1 confidence references where applicable" (per this increment's own
instructions) resolves to *nothing to preserve*: Agent 1 v1.1 has no
per-compound confidence field, and this increment does not fabricate one.

## 13. Validation rules

`app.agent2.network.validation.validate_handoff` runs first, entirely
against the raw handoff, and raises the first violation it finds, in this
order:

1. No two curated compartments/compounds/reactions/regulatory
   interactions/kinetic measurements share an id
   (`DuplicateCuratedIdentifierError`).
2. Every reaction participant's `reaction_id`/`compound_id` exists among
   curated reactions/compounds (`DanglingReferenceError`).
3. Every reaction participant's `role` is a known `ParticipantRole` value
   (`UnknownParticipantRoleError`).
4. Every reaction participant has a non-`None` `compartment_id`
   (`MissingCompartmentReferenceError`).
5. Every reaction participant's `compartment_id` exists among curated
   compartments (`DanglingReferenceError`).
6. Every curated enzyme association's `reaction_id` exists among curated
   reactions (`DanglingReferenceError`).

`FullNetwork.__post_init__` (`app.agent2.types`, extended in this
increment, never redesigned) then re-validates independently, as defense
in depth, over the objects this package actually builds:

* compartment/species/reaction/enzyme-association/regulatory-interaction/
  kinetic-measurement ids are each internally unique;
* every species' `compartment_id` exists in `compartments`;
* every reaction participant's `species_id` exists in `species`;
* every reaction's `enzyme_association_ids`/`regulatory_interaction_ids`
  exist in `enzyme_associations`/`regulatory_interactions`;
* every enzyme association's `reaction_id` exists in `reactions`;
* every regulatory interaction's `regulator_id`/`target_id` exists among
  `reactions`/the compound ids `species` was derived from, **only when**
  the corresponding `regulator_type`/`target_type` is `"reaction"`/
  `"compound"` -- any other type (`"protein"`, `"gene"`, ...) is left
  unchecked (§14).

**Never validated, by design (Agent 3's job)**: mass balance, graph
connectivity/reachability, unit consistency, conservation laws, or
duplicate-reaction detection by content. A network with a fully isolated,
disconnected reaction assembles successfully.

## 14. FullNetwork integrity guarantees

Construction fails, and no partially-built `FullNetwork` is ever returned
or reachable, when: any duplicate id exists in any of the six id
namespaces above; any dangling reference exists (species-to-compartment,
participant-to-species, reaction-to-enzyme-association,
reaction-to-regulatory-interaction, enzyme-association-to-reaction,
resolvable regulation endpoint); or a curated reaction has zero
participants. `assemble_full_network` raises before ever constructing a
`FullNetwork` for a violation `validate_handoff` catches, and propagates
whatever `ValueError` `app.agent2.types` itself raises otherwise -- never
catching and reinterpreting either.

**Two limitations discovered and resolved by extension, not redesign, in
this increment:**

* `CuratedReactionEnzymeAssociation` (Agent 1.x handoff, unchanged) has no
  id of its own, while `ReactionSpecification.enzyme_association_ids`
  (Increment 1) already implied one exists somewhere. Resolved by adding
  `app.agent2.types.ReactionEnzymeAssociation` (a new domain type, mirroring
  the curated record field-for-field plus a synthesized, deterministic
  `association_id`) rather than changing the already-approved,
  cross-repository `CuratedReactionEnzymeAssociation` shape.
* `FullNetwork` (Increment 1) had no field to attach enzyme associations,
  regulatory interactions, or kinetic measurements to at all, even though
  `ReactionSpecification` already referenced the first two by id. Resolved
  by adding three new fields with empty-tuple defaults (`enzyme_associations`,
  `regulatory_interactions`, `kinetic_measurements`) plus matching
  reference-integrity checks -- an additive extension of an already-approved
  contract (`AGENT2_CONTRACT_VERSION` bumped `"0.2"` -> `"0.3"`
  accordingly), not a redesign.

**One limitation left open, disclosed rather than worked around**:
`FullNetwork` has no first-class registry for proteins, enzyme complexes,
genes, organisms, or publications, so `enzyme_associations[].protein_id`/
`.complex_id`, `kinetic_measurements[].protein_id`/`.complex_id`/
`.organism_id`/`.publication_id`, and any regulation endpoint of a type
other than `"reaction"`/`"compound"` are preserved but never referentially
validated. Inventing a check `FullNetwork` cannot actually perform would
be worse than leaving it undone; a future increment that needs to validate
these would first need to decide whether `FullNetwork` should model
proteins/organisms/publications as first-class entities at all.

## 15. Preserved uncertainty

`None` is never converted to `False`, and nothing "unknown" or "missing"
is converted into a definite negative:

* `ReactionSpecification.reversible=None` means "Agent 1 did not record
  reversibility," never "irreversible."
* A reaction with no enzyme association means "none curated," never
  "uncatalyzed."
* An empty `regulatory_interactions`/`kinetic_measurements` tuple means
  "none curated for this scope," never "none exists biologically."
* A regulation endpoint of an unresolvable type (§13, §14) is preserved
  with its original, possibly-dangling `entity_id` rather than being
  cleared to `None` or silently accepted as valid.

## 16. Explicit handoff to Increment 3

Increment 2 ends at a valid, reference-consistent `FullNetwork`. Increment
3 ("Kinetic Laws and Parameter Initialization" per
`docs/01_agent2_architecture.md`'s roadmap) must:

* assign a `KineticLawSpecification` (structural form only) to each
  `ReactionSpecification.kinetic_law_id`, which this increment always
  leaves `None`;
* declare and initialize `ParameterSpecification`s, deciding for the
  first time how a `CuratedKineticMeasurement` attached to
  `FullNetwork.kinetic_measurements` (§11) maps onto a specific
  reaction's specific kinetic-law parameter -- a decision this increment
  explicitly does not make;
* never assign a kinetic law from a `CuratedKineticMeasurement`'s
  `reported_rate_law` text without an explicit parsing/mapping decision --
  that free-text field is preserved verbatim here, never parsed;
* leave boundary assessment, module decomposition, and Antimony
  generation to their own later increments, exactly as
  `docs/04_core_domain_contracts.md` §25 and this increment's own
  instructions require.

This increment does not begin Increment 3. No `KineticLawSpecification`,
`ParameterSpecification`, `BoundaryAssessment`, `ModuleSpecification`, or
Antimony artifact is ever constructed by anything in `app.agent2.network`.

## 17. Richer handoff acknowledged, not consumed (Agent 1.x Increment B)

Agent 1's handoff gained `enzyme_states`/`enzyme_modifications`/
`allosteric_interactions`/`enzyme_state_transitions`, plus
`CuratedKineticMeasurement.enzyme_state_id`
(`docs/02_agent1_handoff_contract.md` §4B). `assemble_full_network` was
**not** modified to read or attach any of them -- `FullNetwork` already
preserves `CuratedKineticMeasurement` unchanged (§11), so
`enzyme_state_id` passes through automatically wherever a kinetic
measurement already did, but no new field was added to `FullNetwork` for
the four new curated types, since nothing in this package's own behavior
needed to change to remain correct. Agent 2's future Reaction
Characterization stage will be the one to map a `CuratedEnzymeState` onto
a distinct model species -- not implemented here, and not begun by this
note.

---

> Increment 2 assembles the complete structural network. It does not
> choose a rate law, does not declare a parameter, and does not decide
> which kinetic measurement belongs to which reaction.
>
> Every curated compartment, species, reaction, enzyme association,
> regulatory interaction, and kinetic measurement is preserved exactly as
> Agent 1 curated it -- nothing invented, nothing merged, nothing dropped.
