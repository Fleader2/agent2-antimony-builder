# Agent 1 → Agent 2 Translation Layer

Replaces the uncommitted, pilot-only translation scripts (Real Integration
Pilot 2 Run 1/Run 2's own scratchpad `build_handoff`) with committed,
deterministic production code:
`app.agent2.handoff.translate_agent1_view_to_agent2`.

## 1. Inspection performed before implementation

Read directly, in both repositories:

* Agent 1 `app/agent1/types.py` — `Agent1CuratedKnowledgeView`,
  `Agent1KnowledgePackage`, `CuratedKineticMeasurement`,
  `CuratedEnzymeState`/`CuratedEnzymeModification`/
  `CuratedAllostericInteraction`/`CuratedEnzymeStateTransition`.
* Agent 1 ORM models carried raw onto the View: `Compartment`, `Compound`,
  `Reaction`/`ReactionParticipant`/`ReactionEnzyme`,
  `RegulatoryInteraction`, `Claim`/`Evidence`, `app/models/enums.py`
  (confirmed every enum used is a `StrEnum` whose `.value` already matches
  the plain string Agent 2's own mirrored fields expect).
* Agent 2 `app/agent2/types.py` — `Agent1CuratedKnowledgeViewContract` and
  every `Curated*` type it carries.
* `docs/02_agent1_handoff_contract.md` §2, which already anticipates this
  exact translation layer and its shape ("most likely via serialization
  (e.g. JSON) rather than an in-process Python import across
  repositories").
* The two existing pilot scripts
  (`run_pilot2_run1.py`/`run_pilot2_run2.py`, both uncommitted scratchpad
  files) and the real Run 8 `09_agent1_curated_knowledge_view.json`
  artifact they consume.

### Exact field mismatches found

| Category | Agent 1 field name | Agent 2 field name | Notes |
|---|---|---|---|
| Compartment/Compound/Reaction/etc. | `id` | `id` | Match. |
| Compound | `canonical_name` | `name` | Rename only. |
| Kinetic measurement | `kinetic_measurement_id` | `id` | Rename only. |
| Kinetic measurement | `substrate_id` | `compound_id` | Rename only — **never** populated from a species label (§7). |
| Enzyme state | `enzyme_state_id` | `id` | Rename only. |
| Enzyme modification | `enzyme_modification_id` | `id` | Rename only. |
| Allosteric interaction | `allosteric_interaction_id` | `id` | Rename only. |
| Enzyme state transition | `enzyme_state_transition_id` | `id` | Rename only. |
| Evidence | `publication_id` (a foreign key UUID; `Agent1CuratedKnowledgeView` resolves no `Publication` fields for evidence) | `publication_reference` (a `str`) | The id itself is the only faithful "reference" available — never a fabricated citation string. |
| `limitations` | *(field does not exist on `Agent1CuratedKnowledgeView`* — only on the broader `Agent1KnowledgePackage`) | `limitations: tuple[str, ...] = ()` | Always empty for a View-sourced translation; nothing is lost, since the View never carried this field. |
| Reaction | `ec_number`/`kegg_reaction_id`/`metacyc_reaction_id`/`rhea_id`/`reaction_type`/`status`/`internal_id` | *(no corresponding field)* | Pre-existing, already-disclosed narrower Agent 2 contract (`docs/02_agent1_handoff_contract.md` §4: "each has a stable id" — no further reaction metadata promised). Not addressed here — adding these fields to `CuratedReaction` would be a contract-shape change, out of this increment's scope. |

Every other field name matches exactly between the two sides.

## 2. Translator API

```python
from app.agent2.handoff import translate_agent1_view_to_agent2

handoff = translate_agent1_view_to_agent2(view)  # view: a JSON-decoded dict
```

`view` is a plain `Mapping[str, Any]` shaped exactly like Agent 1's real
`Agent1CuratedKnowledgeView` (each top-level key matching that dataclass's
own field name; each nested entry matching its own row type's field
names) — the same shape every pilot script's `to_jsonable` helper has
produced to date. **Not** a live Python object import: this repository
never imports Agent 1's runtime package, exactly as
`Agent1CuratedKnowledgeViewContract`'s own docstring and
`docs/02_agent1_handoff_contract.md` §2 already establish. `translate.py`'s
own module docstring is the authoritative contract description.

Raises `app.agent2.handoff.MalformedHandoffPayloadError` (a
`HandoffTranslationError`, itself a `ValueError`) only for a payload
missing a required key or shaped unlike a list where one is expected —
never for a legitimately absent/`None`/empty field.

## 3. Kinetic-measurement mapping (the critical case)

Every field is copied verbatim or losslessly reshaped
(`Decimal(str(x))` for numeric strings). Two decisions worth recording
explicitly:

* **`compound_id`** is `substrate_id` verbatim, never derived from
  anything else inside this translator (tested:
  `test_no_species_label_to_compound_inference`, which plants a
  recognizable compound name in `notes`/`source_id` and confirms
  `compound_id` still comes back `None`).
* **`protein_id`/`protein_ids`** are both copied verbatim — this
  **corrects a real defect** found by comparing the pilot scripts against
  Agent 1's actual Run 8 data. The pilot scripts nulled `protein_id`
  whenever `protein_ids` had more than one entry, reasoning that a
  single-valued field "cannot represent" multi-protein applicability.
  That reasoning does not hold: Agent 1's real handoff already reports a
  non-`None` `protein_id` (its own legacy, first-established-context
  value) on every one of the 14 real measurements, including every one
  whose `protein_ids` has two entries — `protein_id` was never itself
  ambiguous in the source data. The pilot scripts' translation silently
  discarded real information Agent 1 had already supplied.
  `CuratedKineticMeasurement.protein_ids`'s own `__post_init__` already
  sorts/deduplicates deterministically regardless of input order, so this
  translator relies on that existing invariant rather than reimplementing
  it.

## 4. Plural protein context

Verified: `protein_ids` arrives intact, and downstream
`Agent2CuratedKineticMeasurement.protein_ids` deduplicates/sorts
deterministically (existing invariant, not reimplemented here). No single
protein is ever chosen. Legacy `protein_id` is retained per the existing
compatibility policy (copied verbatim, documented as legacy/non-
authoritative everywhere it already was).

## 5. Structural fidelity

`compartments`/`compounds`/`reactions`/`reaction_participants`/
`reaction_enzyme_associations`/`regulatory_interactions`/
`enzyme_states`/`enzyme_modifications`/`allosteric_interactions`/
`enzyme_state_transitions`/`claims`/`evidence`/`confidence_summaries` are
all translated — none silently dropped (the pilot scripts hard-coded
`claims=()`/`evidence=()`/`confidence_summaries=()`/`limitations=()`
regardless of what the real View carried; this translator actually reads
and maps all four categories the View can carry). Entity-count
preservation is enforced by test
(`test_complete_structural_translation_preserves_every_entity_count`) and
holds field-for-field, not just by count, for every category.

## 6. Tests

`tests/agent2/test_agent1_translation.py`, 20 tests, covering: complete
structural translation with no entity-count loss; plural protein context
(including the corrected `protein_id` behavior); kinetic measurement with
and without `reaction_id`; resolved `compound_id` copied exactly;
unresolved `compound_id` staying unresolved; no species-label inference;
publication/provenance preservation (measurement `publication_id`,
`CuratedEvidence.publication_reference`/`.quoted_support`,
`CuratedConfidenceSummary`); deterministic translation (same input ->
byte-identical output); compatibility with `assemble_full_network`; and
four malformed-payload cases. All pass.

## 7. Decision point: does Agent 1 currently supply a resolved kinetic `compound_id`?

**No.** Confirmed by direct inspection of the real Run 8
`09_agent1_curated_knowledge_view.json`: `substrate_id` is `None` on all
14 real SABIO-RK kinetic measurements. This translator does not invent
one — it completes the translation faithfully without it, copying
whatever value is actually present (`None`, for all real data today).

The intended scientific chain remains:

```text
source species evidence -> Agent 1 compound resolution -> resolved
substrate_id in the Agent 1 handoff -> this translation -> Agent 2's
reaction-context resolver (app.agent2.kinetics.reaction_context)
```

never source evidence -> this translator -> Agent 2 name matching.

The smallest required follow-up, **not implemented here**: an **Agent 1
kinetic-compound-context resolution increment** — Agent 1 itself
resolving a SABIO-RK kinetic parameter's own `species_label` (see
`docs/13_kinetic_measurement_reaction_context_resolution.md` §1, which
already documents exactly what that source evidence looks like) into a
real `substrate_id` on `KineticMeasurement`, analogous to how Agent 1.x
Increment C.6 already resolves plural protein context. Until that
increment exists, Agent 2's own `reaction_context` resolver will
correctly report `INSUFFICIENT_SOURCE_EVIDENCE` for every real `Km`/`Ki`
measurement passed through this translator, exactly as it does today.

## 8. Scope discipline

No reaction-context matching policy change, no reaction-attribution
inference, no Agent 1 modification, no compound name matching, no
kinetic-law selection change, no parameter-declaration change, no
reversibility work, no Antimony behavior change, no full real-data pilot
run. `agent1-biochemical-curator` was not touched.
