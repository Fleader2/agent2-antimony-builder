# Human-Readable Antimony Naming and Provenance Separation

## 1. Problem and scope

Before this increment, every Antimony identifier Agent 2 generated (compartments, species,
reactions, parameters, events, observables) was derived directly from the component's own
internal canonical id -- for Agent 1-sourced data, a raw UUID. A real curated model's
Antimony text was consequently dominated by strings like `c_6e1bdc18_bebc_494b_95b6_...` and
reaction-line comments carrying full `kinetic_law_id` chains and catalytic-context UUIDs --
technically correct, essentially unreadable by a human inspecting the model.

This increment separates three previously-conflated concerns:

1. **Internal identity** -- `compartment_id`/`species_id`/`reaction_id`/`parameter_id`/
   Agent-1 entity ids/kinetic-law ids. Unchanged, still the only thing any cross-reference,
   validation, or the canonical downstream handoff ever uses.
2. **Human-readable Antimony symbol** -- what actually appears as the identifier in the
   generated `.ant` text. Now derived from a curated biological name wherever one exists; a
   UUID-derived string is a *fallback*, used only when no meaningful name is available.
3. **Provenance** -- the full traceability chain from a symbol back to its internal identity
   and source. Previously inline (long UUID chains crowding reaction-line comments); now
   primarily a structured, queryable map (`AntimonySymbolProvenance`/
   `build_symbol_provenance_map`), with only a short disclosure left inline.

Non-goals (unchanged from the task): no modularization, simulation, calibration, or UI work.
This increment touches only `app.agent2.antimony.naming` and the inline-comment formatting
in `app.agent2.antimony.generator` -- never the resolution/assembly logic that produces the
executable math itself.

## 2. Naming hierarchy

For a `GENERATED` model (Agent 2's own build path), `build_identifier_map` derives each
category's *display basis* -- the text sanitization/collision-resolution below actually
operates on -- via `_display_basis_for_source`:

1. The component's own curated biological name (`CompartmentSpecification.name`/
   `SpeciesSpecification.name`/`ReactionSpecification.name`/`ParameterSpecification.name`/
   `ObservableSpecification.name` -- all already populated with Agent 1's curated names by
   `app.agent2.network.builder` on the pre-existing build path; nothing new had to populate
   them for this increment).
2. If that name is empty or contains no alphanumeric content (`_biological_display_basis`
   returns `None`), the raw canonical id is the fallback.

**Disclosed limitation**: the task's own illustrative hierarchy includes a "familiar
gene/enzyme identifier" tier (its own example, `R_ACC1`). Agent 1's full handoff contract
(`Agent1CuratedKnowledgeViewContract`) carries no gene/protein *symbol* field at all --
`reaction_enzyme_associations` carries only bare `protein_id`/`complex_id` UUID strings, never
a name. This tier is therefore not reachable with Agent 2's current data access; reactions
read via their own curated name (tier 1/3 in the task's numbering) and catalytic-context
UUIDs remain UUIDs wherever they appear (short, disclosed, never hidden).

Each structural category gets its own Antimony-id prefix (`c_`/`s_`/`J_`/`p_`/`E_`/`obs_`),
so two different categories can never collide with each other by construction -- only a
within-category collision (two different source ids producing the same sanitized text) ever
needs resolution.

### Species: compartment-aware disambiguation

A `GENERATED` species' display basis folds in its own compartment's *already-resolved* basis
as a suffix (e.g. `Acetyl_CoA_cytosol` vs. `Acetyl_CoA_mitochondrial_matrix`), rather than a
single-letter suffix (the task's own illustrative `_c`): real curated data can have several
compartments sharing a prefix (four of the real yeast organism's thirteen compartments all
start with "mitochondrial"), where a single-letter abbreviation would itself be ambiguous. The
full compartment name is always available and already readable, so it is used directly.

### Parameters: readable-reaction substitution

A parameter's own curated `name` is, on the real build path
(`app.agent2.parameters.policy.build_parameter_slug`), a slug of the shape
`f"{prefix}_{reaction_id}[_{protein_or_state_id}][_{substrate_id}]"` -- i.e. it already embeds
its owning reaction's *raw* id verbatim, plus an opaque protein/enzyme-state/substrate suffix.
`_parameter_basis` locates that exact, already-known `reaction_id` substring in the raw name
(**before** any word-splitting -- see the implementation note below), replaces it with the
reaction's own already-resolved readable basis, and **drops** the trailing
protein/substrate-context segment entirely from the visible symbol (e.g.
`Km_<uuid>_<protein-uuid>` becomes `Km_<reaction-name>`, never
`Km_<reaction-name>_<protein-uuid>`). Agent 2 has no gene/protein symbol data to render that
segment with (same disclosed limitation as reactions above), so keeping the raw id would not
have made it more readable. Any resulting collision between two parameters that share the
same prefix and reaction (e.g. isozyme-specific `Km` values) is resolved exactly like every
other category's collisions -- see §3.

**Implementation note, since this was a real bug caught and fixed before release**: the
substitution must run on the *raw*, still-hyphenated `name` string, before
`_biological_display_basis` ever touches it. That function rejoins hyphen-separated hex
segments with `_` (splitting on any non-alphanumeric boundary), so a hyphenated UUID
substring -- the exact text stored in `parameter.reaction_id` -- can never be found as a
literal substring inside an already-word-split basis string. Doing the substitution first,
then handing the result to `_biological_display_basis`, is the only order that works.

### Imported models: symbols are never renamed

For an `IMPORTED` model (`app.agent2.antimony_import`), `_display_basis_for_source` always
returns the component's own canonical id unchanged, regardless of any curated name -- an
imported model's symbols are the user's own, authored symbols; renaming them by default would
violate the task's own explicit instruction ("do not rename user-uploaded Antimony symbols by
default"). This increment's naming logic is reached for an `IMPORTED` model exactly as before
(same sanitization/reserved-word backstop for safety), it simply never substitutes a different
display basis for the one already there.

## 3. Collision rules

`_resolve_category` groups every (id, display-basis) pair by the sanitized candidate string
each basis produces. Within a group that collides, the colliding source ids are sorted
(never insertion order, never random), and assigned the bare candidate plus `_2`, `_3`, ...
in that sorted order -- deterministic and stable across repeated generation (no `hash()`, no
UUID). Categories never collide with each other (disjoint prefixes), only within themselves.

Three distinct collision scenarios this increment's tests exercise:

- Two species records for the same compound in two different compartments: disambiguated by
  the (already-readable) compartment suffix, not a numeric one -- `s_Acetyl_CoA_cytosol` /
  `s_Acetyl_CoA_mitochondrial_matrix`.
- Two parameters for the same reaction with different (unrenderable) protein/substrate
  contexts: collapse to the same basis, disambiguated by the numeric suffix --
  `p_Km_ligase` / `p_Km_ligase_2`.
- Two genuinely identically-named components with no other available disambiguator: numeric
  suffix, deterministic by sorted source id.

## 4. Provenance-map design

`build_symbol_provenance_map(model) -> tuple[AntimonySymbolProvenance, ...]` (in
`app.agent2.antimony.naming`) recomputes the identifier map and emits one record per
compartment/species/reaction/parameter/event/observable:

```python
AntimonySymbolProvenance(
    antimony_symbol: str,       # the readable (or fallback) symbol
    component_type: str,        # "COMPARTMENT" | "SPECIES" | "REACTION" | "PARAMETER" | "EVENT" | "OBSERVABLE"
    canonical_id: str,          # the component's own Agent 2 canonical id -- always exact
    agent1_entity_id: str | None,   # the matching Agent 1 source id, where one exists
    source_reference: str | None,   # parameter-only: ParameterSpecification.source_reference
    provenance_refs: tuple[str, ...],  # whatever evidence/source refs the component already carried
)
```

`FullAntimonyArtifact.symbol_provenance` carries this tuple as a new, additive field,
validated unique by `antimony_symbol` (never two records can claim the same symbol, mirroring
every other identifier-uniqueness invariant in this codebase). This is the structured
replacement for what used to be inline, verbose comment text: a caller that needs a symbol's
full traceability chain now queries this map directly instead of parsing a comment string.

## 5. Rendering changes: shorter, non-dominating reaction/parameter comments

The task's explicit complaint -- "long catalytic-context explanations and UUID chains should
not dominate reaction lines" -- was traced to two specific fields in
`app.agent2.antimony.generator._reaction_line`/`_parameter_line`:

- `kinetic_law_id` (often itself a composite, `::`-joined id on real composed/multi-context
  data) was named in **every** reaction-line comment, including the overwhelmingly common
  single-law case. It is now omitted from the inline comment entirely -- a reader has the
  reaction's own id (`reaction_id=...`), law type, and reversibility inline; full per-law
  identity remains available programmatically from the model (`resolution.laws`) and is never
  lost, only no longer printed on every line.
- The `RESOLVED_COMPOSED` case's comment named every contributing law's full `kinetic_law_id`
  alongside its context, then appended several sentences of fixed prose explaining additive
  composition. The per-law `kinetic_law_id` listing is dropped (the contributing *contexts*
  alone already distinguish the contributions); the explanatory prose is dropped (the
  `reason=MULTIPLE_CATALYTIC_CONTEXTS_COMPOSED_ADDITIVELY` machine-readable tag, which several
  existing tests already pin, is kept as the sole explanation).
- A resolved parameter's comment used to repeat the parameter's own full (potentially
  UUID-chain-heavy) `parameter_id`. Since the parameter's own Antimony symbol -- now readable
  -- already opens that exact line, repeating the raw id added length without adding
  information; it is dropped from the resolved-parameter comment.

Deliberately **not** touched: the rare `UNRESOLVED_MULTIPLE_CONTEXTS` and single-law
`UNRESOLVED` branches keep their existing, more detailed format (including per-law
`kinetic_law_id[context]` listings) -- these are diagnostic, exceptional paths, already
pinned by several pre-existing tests expecting that exact detail, and the task's own
complaint is specifically about the *common* case dominating every line, not about rare
diagnostic cases carrying extra detail.

No executable semantics changed anywhere in this section: the equation, the arrow
(`=>`/`->`), and `resolution.expression` are untouched; only trailing-comment text was
shortened.

## 6. Fallback behavior when no biological name is available

Whenever `_biological_display_basis` returns `None` -- the name is empty, or contains no
alphanumeric content after stripping bracketed/parenthetical detail -- every call site falls
back to the component's own raw canonical id, sanitized exactly as before this increment
(`_sanitize_base` + category prefix + reserved-word backstop). This is never an error path:
a `GENERATED` component with no meaningful curated name reads exactly as it always has.

## 7. Verification

- `tests/agent2/test_antimony_naming.py` (new, 19 tests): readable compartment/species/
  reaction/parameter symbols from curated names; compartment-aware species disambiguation;
  duplicate-name and duplicate-parameter-context collision resolution; deterministic
  repeated generation; `build_symbol_provenance_map` round-trip from symbol back to canonical
  id; no UUID-shaped symbol when a real name exists; imported-model symbols preserved
  byte-for-byte (both the identifier map and the round-tripped Antimony text); semantic
  invariants (stoichiometry/reversibility/parameter values) unchanged across a
  generate-then-reimport round trip; the canonical downstream handoff unaffected by a
  component's `name` length/shape; and the task's own explicitly-named regression --  a
  yeast-lipid-biosynthesis-shaped model generating human-readable Antimony with no raw
  UUID exposed as a declared identifier and no `kinetic_law_id=` in the output.
- Every pre-existing test in `tests/agent2/` (1013 tests) still passes unchanged in behavior;
  the only test-file changes were fixture-default hardening (see the completion report) and
  two dedicated-naming tests' expectations, which genuinely needed updating for the new,
  correct collision semantics.
- Verified against the real yeast lipid-biosynthesis organism (13 compartments, 53 species,
  38 reactions, 91 parameters): every compartment/species/reaction/parameter symbol in the
  regenerated Antimony text is now fully biological-name-based (e.g. `c_cytosol`,
  `s_Acetyl_CoA_cytosol`, `J__3_hydroxyacyl_NADP_oxidoreductase`,
  `p_Km_acetyl_CoA_carbon_dioxide_ligase`), re-parsed via `import_antimony` with identical
  compartment/species/reaction counts, and the downstream handoff's own structural counts
  unchanged (53 species, 38 reactions, `EXECUTABLE`, now declaring `agent2-downstream-v2` --
  see §8).

## 8. Cross-repository contract impact (`agent2-downstream-v1` -> `agent2-downstream-v2`)

Changing the symbol-derivation rule is an Agent-2-internal change, but it broke something
outside Agent 2: Agents 3 (`agent3-simulation-diagnostics`), 4 (`agent4-calibration-
estimator`), and 5 (`agent5-validation-experimental-design`) each carried their own
independent `antimony_ids.py` module, re-implementing the *old* "symbol is a pure function of
the raw canonical id" rule locally rather than reading it from Agent 2 -- a real, previously
latent cross-repository contract gap, invisible until this increment's naming rule actually
changed what that pure function would have had to compute.

Fixed by making Antimony symbol assignment unambiguously Agent-2-owned data, never
re-derivable data: `AGENT2_DOWNSTREAM_CONTRACT_VERSION` bumped `"agent2-downstream-v1"` ->
`"agent2-downstream-v2"`, adding exactly one new field to `build_canonical_downstream_handoff`
-- `antimony_symbol_map`, `{"species": {id: symbol}, "reactions": {...}, "parameters": {...}}`,
built directly from `FullAntimonyArtifact.symbol_provenance` (`_antimony_symbol_map` in
`app.agent2.pipeline`). Every other field in the contract is unchanged.

Agents 3/4/5 each had their own `antimony_ids.py` module removed entirely and now resolve a
handoff entity id to its real Antimony symbol via a direct lookup in this field -- see each
repository's own `docs/02_*_contract.md` for the exact code-level changes on their side
(`app.agent{3,4,5}.handoff.species_antimony_id_map`/`reaction_antimony_id_map` replace the
removed modules' reverse-map builders). `ANTIMONY_GENERATION_POLICY_VERSION` was also bumped
(`"antimony-generation-v4"` -> `"antimony-generation-v5"`) for the naming-rule and comment-
format changes themselves -- a separate, narrower version from the downstream contract shape.

Verified end to end: the full test suites of `agent2-antimony-builder` (1033),
`agent3-simulation-diagnostics` (36), `agent4-calibration-estimator` (60),
`agent5-validation-experimental-design` (44), `agent-integration-harness` (62 fast + 8
hermetic real-subprocess), and `mechanistic-modeling-workbench` (88) all pass. Two of the
sibling repositories' own real-`sce00061`-organism fixtures (`agent3`/`agent4`) needed a full
regeneration (not just a field patch) to pick up `antimony_symbol_map`; regenerating them
against the current live organism also surfaced an unrelated, pre-existing staleness --
the real organism's own parameter count had drifted from a previously-recorded 115 to the
current, real 91 (84 heuristic, 7 literature-derived) due to curation work between when those
fixtures were last captured and now, entirely unrelated to Antimony naming. Disclosed and
fixed in the same pass (updating the few test assertions that pinned the old count) rather
than left as a silent, unrelated test failure.
