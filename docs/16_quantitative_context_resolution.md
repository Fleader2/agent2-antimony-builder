# Quantitative Context Resolution and Derived Enzyme Concentration

## 1. Objective and insertion point

Agent 1's "Experimental Context and Quantitative Observation Framework" increment
(`AGENT1_CONTRACT_VERSION` "1.3" -> "1.4") exposes `ExperimentalContext`/
`QuantitativeObservation` rows through the handoff -- reference/experiment-specific
protein abundance, protein/metabolite concentration, reaction flux, cell volume, and
growth rate, each with explicit provenance and evidence class. Nothing in Agent 2
consumed any of it before this increment.

**Objective**: derive **enzyme concentrations in canonical nM** from protein abundance
plus cell volume, using the best compatible quantitative context available, with full
provenance and an explicit, disclosed 0.1 pL reference cell-volume assumption only as a
last resort.

**Inspection findings** (this increment's own Step 1):

* `app.agent2.types.Agent1CuratedKnowledgeViewContract` had no mirror of Agent 1's
  `experimental_contexts`/`quantitative_observations` fields at all --
  `AGENT1_HANDOFF_VERSION` was still `"1.3"`. Closing this gap (mirroring
  `CuratedExperimentalContext`/`CuratedQuantitativeObservation` field-for-field,
  `AGENT1_HANDOFF_VERSION` "1.3" -> "1.4") was the necessary first step before any
  derivation could be implemented at all.
* `app.agent2.types.FullNetwork` attaches every other curated collection
  (`kinetic_measurements`, `enzyme_states`, ...) as supporting data verbatim --
  `experimental_contexts`/`quantitative_observations` now join that list, exactly the
  same way, with one new reference-integrity check
  (`quantitative_observations[].experimental_context_id` must resolve against the new
  `experimental_contexts` registry, when set).
* `app.agent2.parameters`/`ParameterSpecification` is scoped to *kinetic-law*
  parameters (always traces back to exactly one `kinetic_law_assignment_id`) -- a
  protein-level enzyme concentration, potentially shared across several reactions/
  catalytic contexts, does not fit that shape and is not a kinetic-law parameter at
  all. A new, dedicated record (`EnzymeConcentration`, `app.agent2.types`) and a new,
  dedicated package (`app.agent2.quantitative_context`) were the smallest correct
  integration point -- reusing `ParameterSpecification` would have forced an artificial
  `kinetic_law_assignment_id` onto a quantity that has none.
* `ModelSpecification` is the one place every other artifact (kinetic laws, parameters,
  boundaries, modules) is finally attached -- `enzyme_concentrations` joins it the same
  way, as a new, optional, empty-by-default field.

## 2. Context-selection precedence (task's own fixed order)

```text
1. experiment-specific protein concentration
2. experiment-specific protein abundance + experiment-specific cell volume
3. reference protein concentration
4. reference protein abundance + compatible reference cell volume
5. reference protein abundance + explicit assumed 0.1 pL cell volume
6. unresolved
```

**A tier is consulted only when the previous tier found a genuine, complete absence of
usable candidates** -- mirrors `app.agent2.parameters.initializer
.initialize_with_fallback`'s own, identically-reasoned precedence policy exactly (an
established precedent in this codebase, not a new idea introduced here). Two or more
candidates at what would otherwise be the winning tier that *disagree* (different
value, or a different derived concentration for tiers 2/4's own abundance/volume
pairs) never silently fall through to a weaker tier and are never averaged or
arbitrarily chosen -- the protein is reported unresolved
(`QuantitativeContextReasonCode.AMBIGUOUS_CANDIDATE_OBSERVATIONS`), exactly as
disagreeing curated kinetic evidence already is by that sibling package.

**Tier 5 only ever consumes `REFERENCE_BASELINE` abundance, never
`EXPERIMENT_SPECIFIC`** -- the task's own literal precedence order, not a
simplification: an experiment-specific abundance measurement with no matching
experiment-specific (or compatible reference) cell-volume observation stays
unresolved rather than being paired with the generic 0.1 pL assumption, which is
reserved for the more broadly representative reference-baseline case.

Implemented in `app.agent2.quantitative_context.resolver
._resolve_one_protein` as a strict ladder: each tier's own helper
(`_resolve_direct_concentration_tier`/`_resolve_abundance_volume_tier`/
`_resolve_assumed_volume_tier`) returns `None` on a genuine absence (fall through) or a
`QuantitativeContextResolutionOutcome` (the final word for that protein, either
resolved or ambiguous) otherwise.

## 3. Concentration equation and constants

```text
[E]_M  = N / (N_A * V)
[E]_nM = [E]_M * 1e9
```

`N` = abundance in molecules/cell, `V` = cell volume in litres. Three explicit
constants only, never an independently hard-coded combined conversion factor
(`app.agent2.quantitative_context.policy`):

* `AVOGADRO_NUMBER = Decimal("6.02214076e23")` -- the CODATA 2019 exact defined value.
* `PICOLITERS_PER_LITER = Decimal("1e12")` -- `1 L = 1e12 pL`.
* `NM_PER_MOLAR = Decimal("1e9")` -- `1 M = 1e9 nM`.
* `DEFAULT_ASSUMED_CELL_VOLUME_PL = Decimal("0.1")` -- the task's own explicit default,
  an ordinary function parameter (`resolve_enzyme_concentrations
  (..., assumed_cell_volume_pl=...)`), never a hidden constant.

All Decimal arithmetic throughout (`derive_concentration_nm`); no `float` anywhere in
this package's call graph. Real, live-confirmed worked example: 6670 molecules/cell at
0.1 pL derives to `110.7579557804955724747954912` nM.

## 4. Provenance and dependency representation

`EnzymeConcentration` (`app.agent2.types`) carries:

* `protein_id`/`value`/`unit` (always `"nM"`)/`basis`
  (`EnzymeConcentrationBasis`, one of the five success tiers above)/`policy_version`.
* `dependencies: tuple[EnzymeConcentrationDependency, ...]` -- every input this
  concentration was derived from. Each dependency names a `role`
  (`"concentration_input"`/`"abundance_input"`/`"cell_volume_input"`) and either a real
  `observation_id` (a `CuratedQuantitativeObservation.id`) or, for the 0.1 pL case, an
  `assumption_notes` string with no underlying observation at all -- at least one of
  the two is always set. This is a **derived/modeling-context record, never a direct
  measurement** -- it is never written back onto, and never mistaken for, the source
  `CuratedQuantitativeObservation`, which stays exactly as Agent 1 reported it.
* `experimental_context_id` -- the context the derivation's own inputs were resolved
  under, when known.

## 5. The 0.1 pL assumption

Used only at tier 5, only for `REFERENCE_BASELINE` abundance, only when no compatible
volume observation (real or reference) exists. Every such `EnzymeConcentration` carries
`assumption_reason_codes = ("REFERENCE_CELL_VOLUME_ASSUMED",)` and a dependency with
`assumption_notes` naming the exact assumed value -- never silently embedded only in
free-text `notes`. `app.agent2.model_specification.mapping.build_model_assumptions`
additionally emits one machine-readable `ModelAssumption` (`category=
"quantitative_context"`, `reason_code="REFERENCE_CELL_VOLUME_ASSUMED"`) per such
protein, so the assumption is visible in `ModelSpecification.model_assumptions`
without a consumer needing to inspect every `EnzymeConcentration` individually.

## 6. Context-mismatch behavior

`app.agent2.quantitative_context.policy.classify_context_compatibility` is a direct,
independent reimplementation of Agent 1's own `classify_context_compatibility`
(`app.normalization.quantitative_observation` in the sibling `agent1-biochemical-
curator` repository) -- this repository never imports Agent 1's runtime package, so
the identical deterministic four-way policy (`EXACT_CONTEXT`/`COMPATIBLE_REFERENCE`/
`CONTEXT_MISMATCH`/`CONTEXT_UNKNOWN`) is reproduced here rather than shared in code.
Exactly field-subset equality over `strain`/`medium`/`carbon_source`/`temperature_c`/
`ph`/`growth_phase`/`growth_condition`, gated on matching `organism_id` -- never a
weighted or scored match.

**One important refinement found during this increment's own test development**: an
abundance and a cell-volume observation that name the *identical*
`experimental_context_id` are always treated as `EXACT_CONTEXT` directly, without
running the field-by-field comparison at all. Running that comparison on a context
compared with itself would otherwise (incorrectly) report `CONTEXT_UNKNOWN` whenever
the row has no populated detail fields -- a real, common case: SGD's own reference
context reports no strain/medium/temperature/pH whatsoever (see the sibling
`agent1-biochemical-curator` repository's "SGD Reference Protein Abundance
Integration" increment). The field-by-field comparison is reserved for two genuinely
*different* context rows.

`CONTEXT_UNKNOWN`/`CONTEXT_MISMATCH` pairs are excluded from the candidate set for
tiers 2/4 (never treated as an error at that point) -- the tier simply contributes no
combinable pair, and the ladder falls through to the next tier. `COMBINABLE_CONTEXT_
COMPATIBILITY = {EXACT_CONTEXT, COMPATIBLE_REFERENCE}` -- `CONTEXT_UNKNOWN` is
deliberately excluded: an unconfirmable relationship is never treated as though it
were confirmed compatible.

## 7. Enzyme-state handling

Derivation is **protein-level only** (task's own explicit scope). The protein-id set
`resolve_enzyme_concentrations` resolves against comes from
`FullNetwork.enzyme_associations[].protein_id` (deduplicated) -- never from
`FullNetwork.enzyme_states`. A protein with more than one catalytic context (multiple
`EnzymeState`s, a complex) still gets exactly one total-protein `EnzymeConcentration`;
no allocation across states/PTM states/complexes/isoforms is attempted, and no such
allocation evidence exists in the current real data to attempt it from.

## 8. ModelSpecification exposure

`app.agent2.model_specification.assembler.assemble_model_specification` gained one new,
optional parameter, `enzyme_concentrations: QuantitativeContextResolutionSet | None =
None`. When supplied: its `network_id` is cross-checked against the network being
assembled (mirroring `_require_matching_networks`'s identical convention for every
other artifact); its `.enzyme_concentrations` are attached verbatim onto
`ModelSpecification.enzyme_concentrations`; and `build_model_assumptions` is given them
to generate the `REFERENCE_CELL_VOLUME_ASSUMED` disclosures above. Every existing call
site (none of which passes this new parameter) continues to construct an identical
`ModelSpecification` -- full backward compatibility.

**Not yet used to alter any kinetic parameter** (task's own explicit exclusion,
Sec 7/10): no line of `app.agent2.parameters`/`app.agent2.kinetics` was touched.

## 9. Real `sce00061` evaluation

Using the real 13 SGD reference protein-abundance observations (median molecules/cell,
confirmed live during the sibling repository's "SGD Reference Protein Abundance
Integration" increment) and the current real baseline (no cell-volume observations of
any kind), every protein resolves via tier 5:

| Protein | Abundance (molecules/cell) | Derived concentration (nM) |
|---|---:|---:|
| HFA1 | 433 | 7.19 |
| HTD2 | 972 | 16.14 |
| FAA2 | 1180 | 19.59 |
| OAR1 | 1760 | 29.23 |
| MCT1 | 2706 | 44.93 |
| CEM1 | 3023 | 50.20 |
| FAA3 | 4023 | 66.80 |
| ETR1 | 9388 | 155.89 |
| FAA4 | 17682 | 293.62 |
| FAA1 | 24250 | 402.68 |
| ACC1 | 29049 | 482.37 |
| FAS2 | 52956 | 879.36 |
| FAS1 | 74144 | 1231.19 |

13/13 proteins resolved, 0 unresolved, all 13 via
`REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME` (0.1 pL), derived range 7.19-1231.19 nM,
median 66.80 nM, 26 total dependency records (2 per protein: one real abundance
observation + one explicit assumption). Not yet fed into macro-to-micro kinetic
reconstruction (out of this increment's scope, per its own explicit exclusion).

## 10. Scope exclusions honored

No modification to Agent 1. No kcat-from-Vmax derivation, no kf/kr derivation, no FBA
flux use, no kinetic-law-selection change, no heuristic-parameter-default change, no
enzyme-state/complex/isoform allocation, no Agent 4 work, no full end-to-end pilot.

## 11. Versioning

`QUANTITATIVE_CONTEXT_POLICY_VERSION` introduced at `"quantitative-context-v1"`.
`AGENT1_HANDOFF_VERSION` "1.3" -> "1.4". `AGENT2_CONTRACT_VERSION` "0.9" -> "0.10".
`MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION` "model-specification-v6" ->
"model-specification-v7". See `app/agent2/version.py`'s own changelog docstring for
the complete, field-by-field rationale for every one of these bumps.
