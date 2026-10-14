# Biological Display Metadata (Agent 1 → Agent 2 Contract, `AGENT1_HANDOFF_VERSION` `"1.7"`)

## 1. Ownership rule (unchanged by this increment)

Agent 1 owns curated biological identity and naming metadata — which gene, which protein,
which EC number a reaction/complex is associated with. Agent 2 owns Antimony symbol
generation — the naming *preference order*, sanitization, collision resolution, and the
final rendered symbol. This increment moves no logic across that boundary: Agent 1 exposes
facts (new, additive handoff fields); Agent 2 decides how to render them (a new tier in its
own, pre-existing naming hierarchy). Agent 2 never infers a gene/protein identity from free
text, and never resolves a new biological mapping Agent 1 did not already curate.

## 2. New contract fields

`Agent1CuratedKnowledgeViewContract` (this repository's local mirror of Agent 1's real
`Agent1CuratedKnowledgeView`) gains two new, additive, raw-field-mirroring collections:

- `genes: tuple[CuratedGene, ...]` — `id`, `symbol` (optional), `systematic_name` (optional),
  `name` (optional). Agent 1's own `Gene.symbol`/`.systematic_name` carry no presence
  guarantee (`app.models.gene.Gene` places no uniqueness or presence requirement on either
  column) — a caller must tolerate both being `None`.
- `proteins: tuple[CuratedProtein, ...]` — `id`, `name` (required), `gene_id` (optional,
  mirrors Agent 1's own nullable `Protein.gene_id`), `ec_number` (optional).

`CuratedReaction` gains one new field: `ec_number: str | None = None`, copied verbatim from
Agent 1's own already-curated `Reaction.ec_number` column (which was already present on the
raw, unreshaped `Reaction` row Agent 1's handoff passes through, but never previously carried
into this repository's own local mirror type).

All three are parsed by `app.agent2.handoff.translate.translate_agent1_view_to_agent2`
exactly like every other additive field this contract has ever gained: `_require_list`
already defaults a missing key to `[]`, so a still-`"1.6"`-shaped payload (no `genes`/
`proteins` keys at all) translates successfully, with empty tuples — never an error.

## 3. Where the data flows after translation

- `FullNetwork` gains matching `genes: tuple[CuratedGene, ...]`/
  `proteins: tuple[CuratedProtein, ...]` passthrough fields, mirroring its own pre-existing
  `enzyme_associations` convention ("supporting data the structural graph carries forward,"
  never a structural graph element itself). Populated by `assemble_full_network` directly
  from the handoff — no new query, no new resolution.
- `ReactionSpecification` gains `ec_number: str | None = None`, copied verbatim by
  `app.agent2.network.builder.build_reactions` from the matching `CuratedReaction`.
- `ParameterSpecification` gains `substrate_id: str | None = None` — the compound id a
  substrate-specific parameter (e.g. a Michaelis constant) was declared for.
  `app.agent2.parameters.builder` already knew this value at construction time (it was being
  flattened into `parameter_id`'s own slug via `app.agent2.parameters.policy
  .build_parameter_slug`'s own `substrate_id` argument, never otherwise retained); this
  increment only starts *storing* it as its own field, so the naming layer can read it
  directly instead of ever re-parsing it out of the slug string.

None of these additions touch a canonical id, a stoichiometry, a kinetic law, a parameter
value, or any simulation-relevant field — purely additive display/provenance metadata.

## 4. Agent 2 naming preference order (reactions)

`app.agent2.antimony.naming._reaction_display_basis` implements the task's own
approximate hierarchy, for a `GENERATED` model only (`IMPORTED` models are unaffected — see
§6):

1. **Gene symbol(s)** of the reaction's own curated catalyst(s)
   (`_catalyst_display_basis`): for each of the reaction's `FullNetwork.enzyme_associations`,
   resolve `association.protein_id` → `FullNetwork.proteins` → that protein's own
   `gene_id` → `FullNetwork.genes` → that gene's own `symbol`.
2. **Protein/enzyme name**, for any one of those same catalysts whose linked gene has no
   `symbol` (or no linked gene at all) — that catalyst's own curated `Protein.name`.
3. **The reaction's own EC number** (`_ec_display_basis`), reached only when neither tier 1
   nor 2 resolves to anything *and* the reaction's own curated name (tier 4) is also
   unusable — e.g. `"6.4.1.2"` → `EC__6_4_1_2`.
4. **The reaction's own curated name** — the pre-existing
   `_biological_display_basis(reaction.name)` path from the Human-Readable Antimony Naming
   increment, unchanged.
5. **The raw canonical reaction id** — the existing final fallback, unchanged.

Tiers 1 and 2 are resolved **per catalyst**, not as a single either/or switch across the
whole reaction: a reaction with two associated proteins, one with a gene symbol and one
without, uses that first protein's symbol *and* the second protein's own name side by side
(e.g. `J_ENZ1_Enzyme_two`) — a catalyst with no resolvable metadata at all is skipped, never
dropping the whole reaction down to tier 3. Multiple resolved labels are **sorted and joined
with `"_"`** — deterministic, never an arbitrary "first one found" (e.g. the real yeast
acetyl-CoA carboxylase reaction, catalyzed by both nuclear `ACC1` and mitochondrial `HFA1`,
becomes `J_ACC1_HFA1` regardless of which association Agent 1 happened to list first).

This is a strict **preference order**, never a requirement: the task's own instruction "do
not require every reaction to have a gene symbol" holds at every tier — a reaction with no
curated catalyst metadata at all falls straight through to tier 4/5 exactly as it did before
this increment (verified: zero change to any pre-existing test's expected output).

**Enzyme complexes are a disclosed, out-of-scope gap for this increment**: Agent 1 does not
yet query `EnzymeComplex`/`EnzymeComplexMember` into its own knowledge package at all (see
the sibling `agent1-biochemical-curator` repository's own `docs/33_biological_display_metadata.md`
§"Not in scope"), so an association naming a `complex_id` (rather than a `protein_id`) has no
corresponding entry in `FullNetwork.proteins`/`.genes` and is silently skipped by
`_catalyst_display_basis`, falling through exactly like any other unresolvable catalyst.

## 5. Parameter naming (inherited, plus a new substrate-name tier)

A parameter's own symbol already substitutes its owning reaction's readable basis for the
raw reaction-id substring embedded in its slug (Human-Readable Antimony Naming increment) —
this happens automatically and needed no change: a reaction that now resolves to `ACC1_HFA1`
instead of `acetyl_CoA_carboxylase` makes every one of its own parameters read as
`kcat_ACC1_HFA1`/`Km_ACC1_HFA1_...` without any parameter-specific code change.

New in this increment: when `ParameterSpecification.substrate_id` is set and resolves to a
known compound (via `FullNetwork.species[].source_compound_id`, already-assembled data, no
new lookup), that compound's own readable name is appended as a suffix — the task's own
explicit example, `Km_ACC1_acetyl_CoA` (rendered here as `p_Km_ACC1_Acetyl_CoA`, following
this repository's own existing `_biological_display_basis` capitalization-preserving
convention). A `substrate_id` that does not resolve to any known compound is a silent no-op
(no suffix), never an error — identical discipline to every other optional metadata tier.

## 6. Imported models are unaffected

`_reaction_display_basis` returns the raw reaction id unchanged for an `IMPORTED` model,
exactly as `_display_basis_for_source` already does for every other category — this
increment never looks up catalyst metadata for an imported model, and an imported model's
own user-authored symbols are never renamed (task instructions, "this increment primarily
fixes the GENERATED model path").

## 7. Fallback / missing-metadata behavior, summarized

| Situation | Result |
|---|---|
| No `enzyme_associations` at all for a reaction | Falls straight to tier 4 (curated name) |
| An association exists, but its `protein_id` matches no curated `CuratedProtein` | That one association is skipped; other resolvable associations (if any) still contribute |
| A resolved protein has no linked gene, or its gene has no `symbol` | Falls back to that protein's own `name` |
| Neither tier 1 nor 2 resolves, and the reaction's own curated `name` is unusable | Falls to the reaction's own `ec_number`, if curated |
| Nothing resolves at any tier | Falls to the raw canonical reaction id (unchanged pre-existing behavior) |
| A parameter's `substrate_id` does not match a known compound | No substrate-name suffix (silent no-op) |

## 8. Cross-repository compatibility

`AGENT2_DOWNSTREAM_CONTRACT_VERSION` is **unchanged** (`"agent2-downstream-v2"`) — the
downstream handoff Agents 3/4/5 consume has the identical shape as before this increment,
including the `antimony_symbol_map` field the Human-Readable Antimony Naming increment
already added. Only the *symbol values* that field carries for a model with curated gene/
protein associations improve; no downstream repository needed any code change, and no
cross-repo integration test's own expectations about downstream shape changed. `AGENT1_
HANDOFF_VERSION` was bumped `"1.5"` → `"1.7"` (also finally catching up to Agent 1's own real,
current contract version — previously disclosed, unenforced drift since Increment 3) and the
sibling `agent-integration-harness` repository's own version matrix (`AGENT1_CONTRACT_VERSION`/
`AGENT2_EXPECTED_AGENT1_VERSION`) was synced to match.

## 9. Verification

- `tests/agent2/test_agent1_translation.py`: genes/proteins/`ec_number` translated verbatim;
  default to empty/`None` when absent from an older-shaped payload; assemble into
  `FullNetwork` correctly.
- `tests/agent2/test_biological_display_metadata.py` (new, 16 tests): reaction with a gene
  symbol; reaction with a protein name but no linked gene (and with a linked gene that itself
  has no symbol); multiple catalysts (all-gene-symbol, and mixed gene-symbol/protein-name);
  missing-association/unresolvable-protein/no-curated-name-or-EC fallback chains;
  parameter inheriting its reaction's catalyst-based basis; the task's own
  `Km_ACC1_acetyl_CoA`-shaped substrate-name suffix (and its unresolvable-substrate no-op);
  deterministic collision handling across repeated calls; exact provenance traceability via
  `build_symbol_provenance_map`; the canonical downstream handoff's own fields (reaction_id/
  name/`antimony_symbol_map`) unaffected by the naming change; and the task's own named real-
  shaped yeast lipid-biosynthesis regression (`ACC1`/`HFA1`-shaped isozymes → `J_ACC1_HFA1`).
- Verified against the real yeast organism (13 genes, 13 proteins, already curated, zero new
  curation): regenerated Antimony output shows real reactions resolving to `J_ACC1_HFA1`,
  `J_CEM1_FAS2`, `J_ETR1`, `J_FAS1`, `J_FAA1_FAA2_FAA3_FAA4`, with parameters inheriting the
  identical basis (`p_kf_ACC1_HFA1`, `p_Km_FAS1_FAS2_Acetyl_CoA`,
  `p_Km_FAS1_MCT1_Malonyl_CoA`) — re-parsed via `import_antimony` with identical
  compartment/species/reaction counts, and the downstream handoff's own structural counts and
  `agent2-downstream-v2` contract version unchanged.
