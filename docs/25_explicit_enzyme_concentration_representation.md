# Explicit Enzyme Concentration Representation in Kinetic Models

## 1. Objective and insertion point

Before this increment, a single-substrate Michaelis-Menten rate law rendered only
`kcat * S / (Km + S)` -- catalytic enzyme abundance was never represented at all, even when
Agent 1's own curated data (protein abundance, already resolved into a canonical-nM
`EnzymeConcentration` by the Quantitative Context Resolution and Derived Enzyme Concentration
increment, `docs/16_quantitative_context_resolution.md`) made the decomposition possible.
Enzyme abundance and catalytic rate were structurally inseparable: varying one always meant
varying the lumped product of both.

This increment adds one new package, `app.agent2.enzyme_concentration_species`, and its own
public entry point, `build_enzyme_concentration_species`. It sits **after** enzyme-state
dynamics and **before** final parameter declaration and model assembly, which consume its
output instead -- mirroring `app.agent2.enzyme_state_dynamics`'s own, identical
network-augmentation contract (`docs/18_enzyme_state_population_dynamics.md` §1):

```
assign_kinetic_laws -> resolve_enzyme_concentrations -> build_enzyme_state_dynamics
                                                                    |
                                                                    v
                                                  build_enzyme_concentration_species
                                                                    |
                                                                    v
                        declare_parameters(merged assignments, further-augmented network)
                                                                    |
                                                                    v
      assemble_model_specification(further-augmented network, ..., enzyme_species_lookup=...)
                                                                    |
                                                                    v
                                                          generate_antimony
```

`app.agent2.pipeline.run_agent2_pipeline` is the only caller; every lower-level package
(`network`, `characterization`, `kinetics`, `quantitative_context`, `enzyme_state_dynamics`)
runs completely unmodified, against whatever network it already received.

## 2. The explicit enzyme species

`build_enzyme_concentration_species(network, enzyme_concentrations=None)` iterates
`FullNetwork.enzyme_associations`, and for each distinct, resolvable (`protein_id`,
`compartment_id`) pair -- `compartment_id` derived from the uniform compartment of the
catalyzed reaction's own participants (a stand-in for the enzyme's own localization, which
Agent 1 does not yet curate at the protein level -- see §9's own caveat on why this is a
known simplification, not the intended long-term rule), `None` (skipped, disclosed by
omission) when a reaction spans more than one compartment (e.g. transport) -- materializes
exactly one new `SpeciesSpecification`:

```python
SpeciesSpecification(
    species_id="enzyme-concentration::<protein_id>::in::<compartment_id>",
    name=protein.name,
    compartment_id=compartment_id,
    source_protein_id=protein_id,          # new, third, mutually-exclusive species origin
    initial_concentration=<resolved nM value or None>,
    initialization_source=<ParameterSource.LITERATURE_DERIVED or None>,
    assumptions=(...),
    provenance_refs=("protein::<protein_id>", "quantitative-observation::<obs_id>", ...),
)
```

**Deduplicated** exactly like `app.agent2.network.builder.build_species` dedupes
(`compound_id`, `compartment_id`): the same enzyme catalyzing several reactions in the same
compartment gets exactly one species, reused by every one of those reactions' own
kinetic-law expressions (never duplicated per reaction).

**Identity without a resolved concentration is still represented explicitly** (task
instructions §5): an unresolved protein still gets its own species, with
`initial_concentration=None` and a disclosed `assumptions` entry -- never a fabricated
numeric placeholder. **A protein Agent 1 names as a catalyst but whose own record Agent 2's
handoff never exposed** (`network.proteins` has no matching entry) is skipped entirely --
a disclosed data gap, never a fabricated identity.

**Regulation readiness** (task §6): an explicit `SpeciesSpecification` is an ordinary
Antimony species like any other -- nothing about this increment hard-wires a regulatory
mechanism, but a future increment's rules/reactions can reference this species (e.g. its own
concentration, a phosphorylation-state split, a degradation/synthesis reaction) exactly as it
would any compound species, with no further structural change required here.

## 3. Rate-expression injection (where E actually appears)

`app.agent2.model_specification.mapping.build_expression_and_species` gained an optional
`enzyme_species_lookup: dict[(protein_id, compartment_id), species_id]` parameter
(`app.agent2.model_specification.assembler` builds it directly from the already-augmented
`network.species`, filtered by `source_protein_id is not None` -- never a second,
separately-threaded value that could drift out of sync).

**Scope: single-substrate Michaelis-Menten only.** When a `MICHAELIS_MENTEN` law has exactly
one reactant/Km pair and its own catalytic context (`assignment.protein_id` plus the
reaction's own uniform compartment) resolves against the lookup:

```
kcat * E * S / (Km + S)        # KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION
```

replaces the pre-existing

```
kcat * S / (Km + S)            # KineticLawRateScope.LUMPED_EFFECTIVE_RATE
```

Every other case -- no lookup supplied, no resolvable catalytic context, a multi-substrate or
no-reactant Michaelis-Menten law, and **every `MASS_ACTION`/`REVERSIBLE_MASS_ACTION`/`HILL`
law regardless of whether its own enzyme is resolvable** -- stays
`LUMPED_EFFECTIVE_RATE`, explicitly tagged, never silently downgraded. Single-substrate
Michaelis-Menten is simply the first kinetic-law family for which Agent 2 currently performs
this decomposition (task §7, disclosed, not an oversight): this codebase has no real
decomposition basis for a mass-action rate constant or a Hill `Vmax` today (unlike `kcat`,
which is uniformly semantically per-molecule across every one of its own provenance tiers --
see §5 below), and a multi-substrate Michaelis-Menten law already withholds its own single
combining algebra for the identical reason (`docs/11_model_specification_assembly.md`
§8).

`KineticLawSpecification.rate_law_scope: KineticLawRateScope` (new field, defaults to
`LUMPED_EFFECTIVE_RATE` for every pre-existing construction site -- purely additive) makes
this tag a first-class, machine-readable fact rather than something a downstream consumer
would have to re-derive by pattern-matching the expression text.

## 4. Naming

`app.agent2.antimony.naming._species_basis` gained a protein-aware branch: a
`source_protein_id`-tagged species prefers that protein's own curated **gene symbol**
(task's own named example, `ACC1_c`), falling back to the protein's curated name, falling
back to the raw species id -- mirrors `_catalyst_display_basis`'s identical per-protein
gene-symbol-then-name preference (`docs/24_biological_display_metadata.md` §4), reused here
via the new `_protein_display_basis` helper. The pre-existing compartment-suffix convention
applies unchanged, so a real yeast run renders `s_ACC1_cytosol`, `s_FAS1_cytosol`,
`s_HFA1_cytosol`, etc.

`AntimonySymbolProvenance.agent1_entity_id` -- previously always `species.source_compound_id`
-- now falls back to `species.source_protein_id` when the former is `None`, so an explicit
enzyme species' own traceability record resolves back to its real Agent-1 protein id, not
`None`.

## 5. Why no change to `kcat`'s own reconstruction math was needed

`app.agent2.parameters.reconstruction`'s "Derivation B" (`kcat = Vmax / [E]_total`, tagged
`ParameterSource.DERIVED_FROM_MACRO_KINETICS`) already divides a curated macroscopic rate by
the resolved enzyme-total concentration at *parameter-declaration* time. Multiplying `[E]`
back into the *rendered expression* at generation time (§3 above) algebraically reconstructs
the originally-measured `Vmax` while keeping `kcat` and `E` independently queryable and
variable -- exactly the task's own stated goal, achieved with no change to that reconstruction
code at all. Verified directly against `app.agent2.parameters.heuristic_defaults`'s own
provenance-tier documentation that every `kcat` tier this codebase produces (not just
`DERIVED_FROM_MACRO_KINETICS`) is uniformly semantically "per-molecule," so this
reconstruction is correct regardless of which tier actually produced a given law's `kcat`.

## 6. Concentration resolution and unit conversion

Unchanged: `app.agent2.quantitative_context.resolve_enzyme_concentrations`'s own six-tier
precedence (`docs/16_quantitative_context_resolution.md`) is the sole source of every
resolved value this package consumes. `build_enzyme_concentration_species` never recomputes a
concentration, never guesses a volume, and never invents an abundance -- it only reads
`QuantitativeContextResolutionOutcome.concentration`, verbatim, and copies it onto the new
species' `initial_concentration`. A protein with no usable abundance/concentration
observation at all (or an ambiguous one, per that package's own disagreement rule) still gets
an explicit species -- just with `initial_concentration=None` and the disclosed
`"...could not be resolved..."` assumption, never a fabricated number.

## 7. Contract/version changes

- `AGENT2_CONTRACT_VERSION` `"0.13"` -> `"0.14"`: `SpeciesSpecification` gained
  `source_protein_id` (third, mutually-exclusive species origin alongside
  `source_compound_id`/`source_enzyme_state_id`); `KineticLawSpecification` gained
  `rate_law_scope`.
- `MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION` `"v11"` -> `"v12"`: `assemble_model_specification`
  now accepts and threads an enzyme-species lookup.
- New `ENZYME_CONCENTRATION_SPECIES_POLICY_VERSION = "enzyme-concentration-species-v1"`.
- `AGENT2_DOWNSTREAM_CONTRACT_VERSION` `"agent2-downstream-v2"` -> `"agent2-downstream-v3"`:
  the canonical downstream handoff's `species[]` gained `source_protein_id`,
  `kinetic_laws[]` gained `rate_law_scope` -- both purely additive, needed so Agents 3/4/5 can
  eventually distinguish an explicit enzyme-concentration species/rate law from a compound
  species/lumped rate for their own future calibration and regulation work (not implemented
  by this increment itself). Agents 3, 4, and 5 each bumped their own identical
  `AGENT{3,4,5}_HANDOFF_CONTRACT_VERSION`/`AGENT2_HANDOFF_CONTRACT_VERSION` constant in step
  (each repository's own `app.agent{3,4,5}.version`); none of their own handoff-parsing code
  needed a change, since each already parses every species/kinetic-law dict permissively
  (`.get(...)`, no extra-key rejection) -- consuming either new field is deferred to a future
  increment in those repositories. `agent-integration-harness/app/harness/version.py` synced
  identically, plus its own static JSON fixtures that declare a literal `contract_version`.

## 8. Real-data regression

Running the real pipeline (`run_agent2_pipeline`) against the live yeast
(*Saccharomyces cerevisiae*) lipid-biosynthesis organism now produces, where it previously did
not:

```
species s_ACC1_cytosol in c_cytosol;
s_ACC1_cytosol = 482.3699936233307173643679494;   // initial_concentration

species s_FAS1_cytosol in c_cytosol;
s_FAS1_cytosol = 1231.190085965376870400485292;   // initial_concentration

J_FAS1_FAS2: s_Acetyl_CoA_cytosol -> s_Long_chain_acyl_CoA_cytosol;
    (p_kcat_FAS1_FAS2 * s_FAS1_cytosol * s_Acetyl_CoA_cytosol
        / (p_Km_FAS1_FAS2_Acetyl_CoA + s_Acetyl_CoA_cytosol))
  + (p_kcat_FAS1_FAS2_2 * s_FAS2_cytosol * s_Acetyl_CoA_cytosol
        / (p_Km_FAS1_FAS2_Acetyl_CoA_2 + s_Acetyl_CoA_cytosol));
```

All 13 curated proteins (ACC1, HFA1, FAS1, FAS2, CEM1, ETR1, FAA1-4, MCT1, OAR1, HTD2) resolve
to an explicit species; every one of them, in this organism's data, happens to resolve to a
single cytosolic compartment, so each gets exactly one species (13 new species total: 53
compound species -> 66). The model remains `EXECUTABLE`.

## 9. Remaining limitations (disclosed, not addressed by this increment)

- Injection is scoped to single-substrate Michaelis-Menten laws only (§3). Single-substrate
  Michaelis-Menten is the first kinetic-law family for which Agent 2 currently performs
  explicit enzyme-concentration decomposition. Other law families remain
  `LUMPED_EFFECTIVE_RATE` until a scientifically valid decomposition policy is implemented for
  that family. **This is a current implementation limitation, not a permanent scientific
  restriction.** Future, scientifically valid extensions this increment deliberately leaves
  for later work include: multi-substrate Michaelis-Menten; reversible enzyme kinetics;
  Hill-type kinetics; and mechanistic mass-action enzyme schemes (an explicit elementary
  encounter between enzyme and substrate species, rather than a lumped rate constant).
- No regulatory mechanism (phosphorylation-state-dependent activity, allosteric inhibition,
  degradation/synthesis) is implemented -- only the structural readiness for one (§2) is
  provided, per the task's own explicit exclusion.
- No calibration, modularization, or UI change -- per the task's own explicit exclusion.
- **Compartment is currently derived from reaction participants, not enzyme localization --
  a known simplification, not the intended long-term model.** A catalytic enzyme's own
  explicit concentration should ultimately be anchored to that enzyme's own curated
  localization/compartment, not merely inferred from "all of this reaction's own participants
  happen to share one compartment." Today's rule and that intended one coincide for an
  ordinary single-compartment metabolic reaction (which is why the real yeast regression in
  §8 resolves correctly), but they diverge whenever they should not be conflated -- most
  importantly for **transporters and membrane-associated enzymes**, where the catalyst itself
  is localized to a specific membrane/compartment that is distinct from, and not deducible
  from, its substrate's and product's own compartments on either side. A reaction whose own
  participants span more than one compartment (e.g. transport) gets no explicit enzyme
  species for that reaction at all under today's rule -- disclosed by omission, not a
  fabricated guess, but a real future localization problem this increment does not solve:
  Agent 1 does not yet curate protein-level localization data for Agent 2 to read, and
  resolving it will require consuming that data directly (once curated) rather than
  continuing to infer it from reaction participants.
