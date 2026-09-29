# Identifiability-Aware Macroscopic-to-Microscopic Kinetic Reconstruction

## 1. Objective and insertion point

`docs/15_macroscopic_to_microscopic_kinetic_reconstruction_design.md` is the design basis
(§6/§7 in particular). This increment implements a narrower, tightly-scoped subset of
that design's own recommended smallest-first increments (§11): three of its four
genuinely identifiable/constrainable relationships (design doc §2.1/§3), never the
transient-trajectory or Haldane-reversible paths (design doc §6 step 4a/4b, explicitly
named there as separately-scoped future work).

**Insertion point** (inspection findings, task's own Step 1): `app.agent2.parameters
.builder._declare_michaelis_menten`/`_declare_mass_action`/`_declare_reversible_mass_
action`/`_declare_multi_substrate_mm_fallback` are exactly where `kcat`/`Km`/`k`/`kf`/
`kr` are already initialized via `app.agent2.parameters.initializer
.initialize_with_fallback` -- this increment inserts one new tier into that existing
precedence chain (`macro_reconstruction`, consulted only after both real-evidence tiers
return a genuine, complete absence -- the identical "genuine absence only" rule that
chain already enforces for its own two upper tiers) and adds one adjacent, disclosure-only
mechanism (`MicroscopicConstraint`) for the one relationship that is real but not a point
value. **Kinetic-law selection (`app.agent2.kinetics`) is completely unmodified** -- this
increment only changes how an already-selected law's own parameters are initialized.

**One simplification from the design doc, stated explicitly**: the design doc's own §7
proposes two separate tiers, `DERIVED_FROM_EXPERIMENTAL_MACRO_KINETICS` and
`DERIVED_FROM_AI_PREDICTED_MACRO_KINETICS`. This increment's own governing task instead
specifies one, `DERIVED_FROM_MACRO_KINETICS`, ranked below `AI_PREDICTED` unconditionally
(`docs/15...md`'s own two-way split is not implemented) -- the task's own explicit,
authoritative precedence order for this increment. When a derivation's own inputs
include an AI-predicted macro-kinetic value, that dependency is still preserved
explicitly (in `source_reference`/`uncertainty_text`/`provenance_refs`), just not as a
separate `ParameterSource` tier.

## 2. New provenance/status types

* `ParameterSource.DERIVED_FROM_MACRO_KINETICS` (`app.agent2.types`) -- one new enum
  value (not a shape change), ranked `AI_PREDICTED` > `DERIVED_FROM_MACRO_KINETICS` >
  `HEURISTIC_INITIALIZATION`, per the task's own explicit ordering.
* `IdentifiabilityStatus` (`app.agent2.parameters.types`) -- `IDENTIFIABLE`/
  `PARTIALLY_CONSTRAINED`/`UNDERDETERMINED`/`INCOMPATIBLE_CONTEXT`/
  `INSUFFICIENT_EVIDENCE`. Only `IDENTIFIABLE` may ever produce a numeric
  `DERIVED_FROM_MACRO_KINETICS` value (this module never constructs an explicit
  `IdentifiabilityStatus.IDENTIFIABLE` record itself -- a successful `Initialization`
  *is* that verdict, implicitly, exactly like every other tier in this chain).
* `MicroscopicConstraint` (`app.agent2.parameters.types`) -- one disclosed, unresolved
  elementary-rate-constant relationship; never a numeric assignment. New field on
  `ParameterDeclarationSet`: `microscopic_constraints: tuple[MicroscopicConstraint, ...]
  = ()`.

Neither `IdentifiabilityStatus` nor `MicroscopicConstraint` is promoted to
`app.agent2.types` -- both are policy-internal to `app.agent2.parameters`, mirroring
`KineticLawAssignment`/`KineticLawReasonCode` staying in `app.agent2.kinetics.types`
rather than the shared contract module (this codebase's own established "narrower
reading" of what counts as a public output-contract shape change).

## 3. Implemented derivations

**A. Direct `kcat`** -- not new code. `initialize_with_fallback`'s own existing top two
tiers already return immediately whenever real `kcat` evidence exists; this increment's
new `macro_reconstruction` tier is consulted only when they find a genuine, complete
absence. Verified directly: a curated `kcat` is never displaced by an available
Vmax+concentration alternative (`test_curated_km_and_kcat_never_overwritten_by_
available_macro_reconstruction`).

**B. `kcat = Vmax / [E]_total`**
(`app.agent2.parameters.reconstruction.reconstruct_kcat_from_vmax_and_concentration`).
Requires a canonical (`nM_per_s`) `Vmax` -- Agent 1's own C.12 unit normalization is the
sole authority on this, never re-derived -- and a resolved, non-zero
`app.agent2.types.EnzymeConcentration` (from `app.agent2.quantitative_context`) for the
**exact same protein**. Two or more disagreeing canonical `Vmax` candidates, or no
`EnzymeConcentration` at all, leave the slot at `INSUFFICIENT_EVIDENCE` (falls through
to `HEURISTIC_INITIALIZATION`, unchanged). Context matching is deterministic protein-
identity equality only -- no temperature/strain compatibility check is attempted between
a `CuratedKineticMeasurement` and an `EnzymeConcentration`'s own experimental context,
since no existing deterministic rule bridges the two representations (a disclosed
limitation, not an oversight -- see §6 below).

**C. `k_eff = kcat/Km`**
(`reconstruct_k_eff_from_kcat_and_km`). Dimensionally valid **only** for a genuine
two-reactant elementary encounter: `heuristic_defaults.mass_action_rate_unit(n)` gives
`per_sec` for `n=1` and `per_nMs` only for `n=2`, and this codebase never represents the
enzyme itself as a species (only curated compounds are species) -- a single-substrate
reaction's own mass-action rate constant is therefore unimolecular in this codebase's
structural model, not bimolecular, and `kcat/Km` cannot dimensionally seed it. `n >= 3`
is excluded per the task's own explicit "do not apply generically to arbitrary
multi-reactant reactions" instruction. Wired into three call sites sharing one helper
(`builder._reconstruct_k_eff_for_context`): `_declare_mass_action`'s `k`,
`_declare_reversible_mass_action`'s `kf` (never `kr` -- `kcat/Km` says nothing about the
reverse rate), and `_declare_multi_substrate_mm_fallback`'s `k`/`kf` (the task's own real
motivating example -- a two-reactant `MICHAELIS_MENTEN` assignment routed to this
fallback, e.g. the real malonyl-CoA:[acp] S-malonyltransferase reaction, is exactly this
fallback's own primary real-world case). `Km` is anchored to exactly one of the
reaction's own reactant compounds (`builder._anchored_km_initialization`, mirroring
`app.agent2.kinetics.selector`'s own `SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_
APPROXIMATION` eligibility rule) -- never an untagged `Km` for a multi-reactant context,
never one naming a compound this reaction does not have as a reactant.

**D. The `Km = (kr + kcat) / kf` constraint**
(`classify_km_kcat_constraint`). Applies only to the single-substrate `E + S <=> ES ->
E + P` mechanism, when both `Km` and `kcat` are resolved to real (non-heuristic,
non-placeholder) values from any source (direct, AI-predicted, or Derivation-B-derived).
Produces a `MicroscopicConstraint` (`status=PARTIALLY_CONSTRAINED`,
`constraint_expression="kf * Km = kr + kcat"`), **never** a `kf`/`kr`
`ParameterSpecification` -- this codebase declares no elementary rate-constant slots for
a `MICHAELIS_MENTEN` law at all (its own rendered expression, `kcat*S/(Km+S)`, never
references `kf`/`kr`), so inventing unused, unconstrained placeholder parameters for
them would misrepresent an unresolved degree of freedom as a declared simulation
parameter.

## 4. Identifiability classification

Realized structurally, not as a value every function returns explicitly:

* A successful `Initialization` from a reconstruction function *is* the `IDENTIFIABLE`
  verdict (mirrors how `CURATED`/`AI_PREDICTED` already carry no separate status field
  either -- the `ParameterSource` value itself is the verdict).
* A `MicroscopicConstraint` is always `PARTIALLY_CONSTRAINED` (the one status this
  increment's own derivations ever produce for it -- `UNDERDETERMINED` is reserved by
  the type for a hypothetical future derivation with no relationship at all to disclose,
  not produced by any function in this increment).
* `None` from any reconstruction function is `INSUFFICIENT_EVIDENCE` (the ordinary,
  common, non-error case -- no candidate input existed at all) or `INCOMPATIBLE_CONTEXT`
  (a candidate existed but named a different protein/reaction/substrate) -- both fall
  through identically to the pre-existing `HEURISTIC_INITIALIZATION`/`PLACEHOLDER`
  tiers, so the caller-visible behavior for either case is the same "nothing changed"
  outcome; the distinction is disclosed only in this document and in each function's own
  docstring, not as a separate field on `Initialization` (which has no status field to
  add without a real shape change this increment does not need).

## 5. Context matching (task Sec 5)

Reuses existing, deterministic machinery exclusively -- no new compatibility rule was
invented:

* Protein identity: exact string equality only (`builder._protein_id_for_assignment`,
  resolving a state-specific assignment to its own protein via `CuratedEnzymeState
  .protein_id` when needed).
* Reaction/catalytic context: the existing `_evidence_for`/`_matches_context` machinery,
  unchanged -- every reconstruction function only ever sees evidence already scoped to
  one exact catalytic context.
* Substrate: `_anchored_km_initialization`, mirroring `SUBSTRATE_ANCHORED_MM_MULTI_
  REACTANT_APPROXIMATION`'s own eligibility rule exactly.
* Reference-vs-experiment-specific: inherited entirely from `app.agent2
  .quantitative_context`'s own already-vetted `EnzymeConcentration.basis` -- this
  package never re-derives or second-guesses that verdict.

**Disclosed limitation**: no deterministic rule in this codebase compares a
`CuratedKineticMeasurement`'s own `strain`/`temperature_c`/`ph` fields against an
`EnzymeConcentration`'s own `experimental_context_id` -- Derivation B's "condition
matching" is protein-identity-exact only. Building that comparison would require a new
cross-representation rule this increment does not invent (task's own "under current
deterministic rules" instruction is read narrowly here); a future increment could add
it once a real need is demonstrated.

## 6. Heuristic-fallback interaction

Every reconstruction function returns `None` (or, for `classify_km_kcat_constraint`,
nothing at all) rather than a fabricated value whenever it cannot proceed -- the caller
always still calls `initialize_with_fallback` with the raw evidence and, when
applicable, the reconstruction result as `macro_reconstruction`; that function's own
existing, unmodified heuristic-default tier fires exactly when both real-evidence tiers
*and* the new reconstruction tier all found nothing. No reconstruction function is ever
capable of *preventing* the heuristic fallback from firing when reconstruction itself
also fails -- verified directly (`test_k_eff_rejected_for_three_reactant_context`,
`test_no_enzyme_concentration_leaves_kcat_at_heuristic`).

## 7. Real `sce00061` evaluation

Grounded in the real dev database (13 curated fatty-acid-biosynthesis proteins,
read-only inspection, no permanent write):

* **286 real candidate macroscopic measurements** (`KM`/`KCAT`/`KCAT_OVER_KM`/`VMAX`/
  `SPECIFIC_ACTIVITY`/`TEMPERATURE_OPTIMUM`/`PH_OPTIMUM`/`KI`) across the 13 proteins;
  **228** restricted to the four families this increment's own derivations use at all
  (`KM`/`KCAT`/`VMAX`/`KCAT_OVER_KM`).
* **0/228 carry an Agent-1-resolved `reaction_id`** -- exactly the design doc's own §9
  finding, still true today. **140/180** `KM`/`KCAT`/`VMAX` measurements do carry a real
  `substrate_id`, though -- genuinely more real substrate-anchoring than the design
  doc's own original inspection found, and the raw material Agent 2's own (separately-
  scoped, already-implemented) reaction-context resolver could act on.
* **0/228 have a canonical (`nM_per_s`) `Vmax`** -- every real `Vmax` for these 13
  proteins is reported in a mass-specific-activity unit (`nmol/(min*mg)`), which Agent
  1's own C.12 normalization correctly leaves unresolved (dimensionally incompatible
  without a molecular-weight conversion this repository does not perform). **Derivation
  B therefore has zero real applicability for these 13 proteins today** -- confirmed
  correct by design (unit tests), never fabricated on real data.
* **One real, complete Derivation-C demonstration**: the real malonyl-CoA:[acyl-carrier-
  protein] S-malonyltransferase reaction (2 real reactants), real MCT1 evidence
  (GotEnzymes2 `kcat=0.6986 per_sec`, `Km=76300 nM` anchored to Malonyl-CoA), real SGD-
  derived enzyme concentration (`44.93 nM`, tier `REFERENCE_ABUNDANCE_AND_ASSUMED_
  VOLUME`) -- assembled directly from real ids/values (reaction-context resolution
  applied manually here, using the same real `substrate_id` anchor Agent 2's own
  resolver already uses, since running the full connector-backed pipeline end-to-end is
  out of this increment's own scope). Result: the multi-substrate fallback's own `kf`
  parameter resolves to `DERIVED_FROM_MACRO_KINETICS`,
  `k_eff = 0.6986 / 76300 = 9.155963...e-6 per_nMs` -- displacing what would otherwise
  have been the plain heuristic default (`0.001 per_nMs`). `Km` for the reaction's
  second reactant (Acyl-carrier protein) and `kr` both remain
  `HEURISTIC_INITIALIZATION`, correctly and honestly -- no real evidence resolves
  either.
* **Derivation D has zero real applicability for these 13 proteins today**: every real
  `MICHAELIS_MENTEN`-eligible context found is either multi-substrate (where D does not
  apply, by design) or (for the nine real single-reactant reactions, e.g. HTD2's own
  hydro-lyase steps) has no real co-occurring `Km`+`kcat` for the same protein at all
  (confirmed: HTD2/ETR1 carry zero `KM`/`KCAT`/`VMAX` measurements of any kind). D is
  fully verified against synthetic, Run-7-shaped fixtures instead (13/13 targeted tests
  pass) -- never claimed as demonstrated on real data it does not yet apply to.
* **A real, disclosed limitation of the unmodified kinetics selector, discovered while
  building this real evaluation**: `app.agent2.kinetics.selector
  ._build_contexts_with_evidence` collapses two isozymes (e.g. MCT1 and FAS1, both
  catalyzing the same real reaction) into one shared, context-free assignment whenever
  neither sets `reported_rate_law` -- regardless of whether their own `KM`/`kcat`
  *values* actually agree (the collapse check only compares `reported_rate_law` text
  sets, both trivially empty here). With real MCT1 (`Km=76300 nM`) and FAS1
  (`Km=61300 nM`) evidence combined this way, the shared context's own `Km` becomes
  ambiguous and the reaction falls to `TENTATIVE_MASS_ACTION_DEFAULT` instead of
  `MICHAELIS_MENTEN` -- observed directly, not fixed (kinetic-law selection is out of
  this increment's own explicit scope; noted here as a real, disclosed finding for a
  future increment, exactly as `docs/15...md` itself models this kind of honest
  disclosure).

## 8. Scope exclusions honored

No modification to Agent 1. No change to kinetic-law selection. No new flux/metabolite
dataset ingestion. No FBA integration. No `Keq`/thermodynamic inference. No parameter
fitting. No Agent 4 work. No full end-to-end pilot (the real evaluation above is a
bounded, direct construction from real database values, not a live connector-backed
run).

## 9. Versioning

`MACRO_TO_MICRO_RECONSTRUCTION_POLICY_VERSION` introduced at `"macro-to-micro-v1"`.
`PARAMETER_DECLARATION_POLICY_VERSION` "parameter-declaration-v3" ->
"parameter-declaration-v4". `MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`
"model-specification-v7" -> "model-specification-v8". `AGENT2_CONTRACT_VERSION`/
`AGENT1_HANDOFF_VERSION` unchanged (one new `ParameterSource` enum value and one new
field on `ParameterDeclarationSet`, which lives outside `app.agent2.types` -- neither is
a public output-contract shape change per this codebase's own established "narrower
reading"). See `app/agent2/version.py`'s own changelog docstring for the complete,
field-by-field rationale.
