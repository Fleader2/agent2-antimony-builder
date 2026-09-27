# Agent 2 ModelSpecification Assembly Contract

## 1. Purpose

Increment 8 assembles every prior increment's validated output --
`FullNetwork`, `KineticLawAssignmentSet`, `ParameterDeclarationSet`,
`BoundaryAssessmentSet`, `ModuleDecompositionSet` -- into one
authoritative `ModelSpecification`: the complete, single source of truth
for the mathematical model Increment 9 will serialize into Antimony.
**This increment assembles; it does not reinterpret.** No kinetic-law
type is reclassified, no parameter value is changed, no boundary
likelihood is recomputed, no module cut is revisited. Every scientific
and modeling decision was already made by Increments 4-7; Increment 8's
only job is to integrate those decisions into one internally consistent,
fully cross-referenced contract.

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
    -> ModelSpecification Assembly (this increment)
    -> ModelSpecification
    -> Antimony Generation (Increment 9, see docs/12_antimony_generation.md)
```

Agent 1 is untouched by this increment; nothing in
`agent1-biochemical-curator` was read or modified.

## 3. Input artifacts

```python
assemble_model_specification(
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet,
    modules: ModuleDecompositionSet,
) -> ModelSpecification
```

Pure function: no database, no filesystem, no network access, no LLM, no
simulation, no fitting, no Antimony anywhere in its call graph. Never
mutates any of its five inputs.

## 4. Output: `ModelSpecification`

Reused entirely unchanged (`app.agent2.types`) -- inspection (Increment
8 instructions' own "do not redesign existing contracts unless a genuine
contradiction exists") found it already complete. It carries or
references: the complete `full_network` (compartments, species,
reactions, participants, enzyme associations, regulation, kinetic
measurements, enzyme states -- all reached through `full_network`
itself, never duplicated as separate top-level fields), `kinetic_laws`
(materialized by this increment, §6), `parameters` (copied verbatim from
the input `ParameterDeclarationSet`), `boundary_assessments` (copied
verbatim), `module_decomposition`/`module_specifications` (copied
verbatim from `ModuleDecompositionSet`), `assumptions`,
`model_assumptions` (§16), `provenance_refs` (§17), and
`contract_version` (`AGENT2_CONTRACT_VERSION`). No parallel duplicate
model representation is ever created -- this is the one, single
authoritative object.

## 5. `FullNetwork` authority

`network` is passed straight through as `ModelSpecification.full_network`
-- never reconstructed, never re-derived from `kinetic_laws`/
`parameters`/`boundaries`/`modules`. Every kinetic law, parameter,
boundary, and module produced by this increment resolves back to ids
already present in this exact `FullNetwork` object; none of them ever
introduces a new compartment, species, or reaction.

## 6. Kinetic-law materialization

`KineticLawAssignment` (Increment 4) is a decision record, not a final
model-level law -- it carries no `expression` field at all. This
increment converts each one into a real `KineticLawSpecification`,
**one-to-one, always** (`app.agent2.model_specification.mapping
.materialize_kinetic_law`):

* `kinetic_law_id` -- deterministic, `f"kinetic-law::{assignment_id}"`
  (§7).
* `reaction_id`, `law_type` -- copied verbatim; no law is ever
  reclassified.
* `assignment_source` -- copied **verbatim** from
  `assignment.assignment_source` (`KineticLawAssignmentSource`, §10 --
  no bridge, no conversion, since `KineticLawSpecification
  .assignment_source` is now the correct type for it).
* `enzyme_state_id`/`protein_id`/`complex_id` -- copied **verbatim**
  from the assignment's own catalytic-context target (§11 -- first-class
  fields, not provenance text).
* `expression` -- a canonical symbolic template for built-in law types
  (restricted to cases the evidence actually supports, §8), the verbatim
  curated text for `CUSTOM`, or `None` for `UNASSIGNED`.
* `parameter_ids` -- every `ParameterSpecification.parameter_id` whose
  `kinetic_law_assignment_id` equals this assignment's id (§9).
* `species_ids` -- the species this specific law's expression actually
  references (§8).
* `assumptions`/`provenance_refs` -- the full `reason_codes`/
  `unresolved_reasons` disclosure and traceability back to the source
  `assignment_id` (§17).

**Every `KineticLawAssignment` produces a `KineticLawSpecification`,
including `UNASSIGNED` ones** -- a deliberate choice, not the
alternative Increment 8 instructions' own Step 9 also allowed
("omit... or use `KineticLawType.UNASSIGNED`"). 1:1 coverage-parity with
`KineticLawAssignmentSet` (which itself covers every reaction, never
silently omitting one) was chosen over omission: a downstream consumer
filtering `model.kinetic_laws` by `reaction_id` should always find
*something*, even if that something is honestly `UNASSIGNED`, rather
than having to separately check "is this reaction missing from the list
because it has no law, or because it was never characterized at all."
`KineticLawSpecification.__post_init__`'s own rule (`expression` may be
`None` only when `law_type is UNASSIGNED`) already supports this
uniformly.

## 7. Kinetic-law IDs

`f"kinetic-law::{assignment.assignment_id}"` -- deterministic, stable,
directly traceable back to the source `KineticLawAssignment` by simple
string construction. Never a random UUID. Because `assignment_id` values
already embed their own `"::"`-delimited structure (e.g.
`"r1::kinetic-law::p1"`), the resulting `kinetic_law_id` can look
verbose (`"kinetic-law::r1::kinetic-law::p1"`) -- this is a cosmetic
consequence of following the exact preferred format Increment 8's own
instructions specify (Step 8: `"kinetic-law::<assignment_id>"`), not a
double-prefixing bug; the id remains unique and trivially reversible
(`kinetic_law_id.removeprefix("kinetic-law::") == assignment_id`).

## 8. Expression semantics

Canonical symbolic expressions -- species ids and parameter ids only,
never a numerical literal, never Antimony syntax
(`app.agent2.model_specification.mapping.build_expression_and_species`):

* **`MASS_ACTION`**: `"{k} * {reactant_1} * {reactant_2} * ..."` (or
  bare `{k}` for a reaction with no reactants).
* **`REVERSIBLE_MASS_ACTION`**: `"{kf} * {reactants...} - {kr} *
  {products...}"`.
* **`MICHAELIS_MENTEN`, single substrate**: `"{kcat} * {S} / ({Km} +
  {S})"` -- the conceptual example from Increment 8's own instructions,
  produced exactly. This is the scientifically standard, unambiguous
  Michaelis-Menten rate law -- valid whenever there is exactly one
  reactant participant. Deliberately omits an explicit
  enzyme-concentration factor (no conceptual `"E *"` term): this
  repository never models a catalytic protein/complex as a
  `SpeciesSpecification` (species come only from curated compounds), so
  there is no `E` species or parameter to reference -- inventing one
  would misrepresent what is actually modeled.
* **`MICHAELIS_MENTEN`, multiple substrates -- corrected twice,
  pre-commit**: **`expression = None`.** `law_type` remains
  `MICHAELIS_MENTEN` (the law *family* is known -- curated evidence
  explicitly identified Michaelis-Menten kinetics) and
  `parameter_ids`/`species_ids` still list every declared
  `kcat`/`Km`/substrate; only the *concrete algebraic representation* is
  left unresolved, and `expression=None` is the honest, direct way to
  say so.

  Two earlier drafts of this section (and of the implementation) got
  this wrong in different ways, both corrected before commit:

  1. The first draft produced a simplified product-of-independent-terms
     expression (`"kcat * S1 * S2 / ((Km1+S1) * (Km2+S2))"`). **Removed**:
     it is not a scientifically justified rate law for an arbitrary
     multi-substrate mechanism -- ordered-sequential, ping-pong, and
     random-order kinetics all combine two substrates differently, and
     `app.agent2.parameters.builder` itself only ever declares one `Km`
     per substrate *independently*, with no mechanism-specific combining
     policy to draw from.
  2. The second draft, having correctly decided not to assert an
     unjustified equation, placed a string status marker
     (`"UNRESOLVED_MULTI_SUBSTRATE_MECHANISM"`) directly in `expression`
     instead. **Also removed**: a field whose entire meaning is "the
     concrete algebraic representation" must never hold a non-expression
     status value, however clearly named. `KineticLawSpecification
     .__post_init__` no longer requires a non-blank expression for any
     non-`UNASSIGNED` `law_type` (§8a) specifically so this case can be
     represented honestly as `None` instead.

  The unresolved state is disclosed exclusively through `assumptions`
  and a dedicated `ModelAssumption` (§16) -- never through `expression`
  itself. This case can only arise from a curated reported-law text
  explicitly naming "Michaelis-Menten" on a reaction with more than one
  reactant -- the non-curated heuristic path (Increment 4) is itself
  restricted to exactly one reactant and one product, so it can never
  produce this case on its own.
* **`HILL`**: `"{Vmax} * {S}^{n} / ({Km}^{n} + {S}^{n})"`.
* **`CUSTOM`**: the curated `reported_rate_law_text`, preserved
  **verbatim**, never rewritten into any symbolic or Antimony form --
  this package cannot safely reinterpret opaque curated text.
* **`UNASSIGNED`**: `expression = None`.

If a curated reported-rate-law text happens to also exist for a
built-in type (e.g. `CURATED_REPORTED` classified as `MASS_ACTION`), the
canonical templated expression is still used -- Increment 8 instructions
Step 9 frames built-in types as always using "canonical symbolic
expressions," not conditionally; the original reported text is never
discarded, it remains reachable via the source `KineticLawAssignment`
(cross-referenced through `provenance_refs`, §17).

## 8a. `kinetic_law_type` vs. `expression` -- two distinct facts

**Corrected pre-commit.** `KineticLawSpecification.__post_init__`
previously required a non-blank `expression` whenever `law_type is not
UNASSIGNED`. That rule has been **removed**. The final, intentional
contract:

```text
kinetic_law_type
    = the selected law family (e.g. MICHAELIS_MENTEN)

expression
    = the concrete algebraic representation, if one is known

expression = None
    = the law family is known, but the exact algebra is unresolved
```

This is intentionally different from `kinetic_law_type = UNASSIGNED`,
which means no law-selection decision was made at all. Both states
happen to produce `expression is None`, but they are not
interchangeable: `UNASSIGNED` says "nothing is known"; a non-`UNASSIGNED`
`law_type` with `expression = None` says "the family is known; the exact
formula is not." Always check `law_type` to tell them apart -- never
infer one from `expression` alone. The pure, derived
`KineticLawSpecification.has_expression` property (`expression is not
None`) answers only "does this law currently carry a usable expression,"
independent of which case applies; it is not a substitute for checking
`law_type`.

Removing the non-blank requirement is a genuine validation-behavior
change, not a field addition/removal/retype -- under this repository's
own established `app.agent2.version` convention, field-shape changes
bump `AGENT2_CONTRACT_VERSION`, while validation/policy-behavior changes
are tracked by the relevant `*_POLICY_VERSION` instead. This change is
therefore tracked by `MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`, not
`AGENT2_CONTRACT_VERSION` (see `app.agent2.version`'s own Increment 8
entries for the full versioning decision).

Only one case in the current implementation actually constructs a
non-`UNASSIGNED` law with `expression = None`: the multi-substrate
Michaelis-Menten case (§8). Every other built-in law type
(`MASS_ACTION`/`REVERSIBLE_MASS_ACTION`/`HILL`) and `CUSTOM` always
produces a real expression today; the contract is deliberately general
(not hard-coded to `MICHAELIS_MENTEN` specifically) so a future
increment can represent the identical "family known, algebra unresolved"
situation for another law type without another contract change.

## 9. Parameter linkage

Every `ParameterSpecification` in the supplied `ParameterDeclarationSet`
is grouped by its own `kinetic_law_assignment_id` (already set by
Increment 5 for every declared parameter); the resulting group, in its
*original* `ParameterDeclarationSet` order, is passed to
`build_expression_and_species` for that one assignment. Positional
unpacking (`kcat, *kms = law_parameters`, etc.) is reliable because
`app.agent2.parameters.builder` always declares parameters for one
`kinetic_law_type` in one fixed role order (`MASS_ACTION` -> `[k]`;
`REVERSIBLE_MASS_ACTION` -> `[kf, kr]`; `MICHAELIS_MENTEN` -> `[kcat,
Km_1, Km_2, ...]`, one `Km` per reactant participant in participant
order; `HILL` -> `[Vmax, Km, n]`) -- a fixed, already-established
contract this increment reads, never redefines. A parameter count that
does not match what a law type expects (a genuine structural
inconsistency between the supplied `KineticLawAssignmentSet`/
`ParameterDeclarationSet` -- never a normal missing-biology case) raises
`ModelSpecificationReferenceError` explicitly, rather than crashing on a
bare Python tuple-unpack error (§21).

Every declared `ParameterSpecification` is copied into
`ModelSpecification.parameters` **verbatim** -- `value`, `unit`,
`source`, `source_reference`, `lower_bound`/`upper_bound`,
`uncertainty_text`, `fixed`, and `assumptions`/`provenance_refs` are
never changed, never re-derived, never duplicated.

## 10. Tentative laws

`KineticLawAssignment.is_tentative` (Increment 4's own derived property,
`True` exactly when `reason_codes` contains
`TENTATIVE_MASS_ACTION_DEFAULT`) is read, never recomputed.
`assignment_source` is copied **verbatim** as `KineticLawAssignmentSource`
(§6, §11a) -- a tentative and a non-tentative assignment can both carry
`HEURISTIC`, so `assignment_source` alone does not distinguish them (by
design: they genuinely share the same law-selection provenance category;
tentativeness is a separate fact, carried on `reason_codes`, not folded
into a different `assignment_source` value). `is_tentative` therefore
remains machine-identifiable exactly as it already was on the source
`KineticLawAssignment` -- via `reason_codes` -- disclosed on the
materialized law's own `assumptions` (a sentence explicitly naming
`TENTATIVE_MASS_ACTION_DEFAULT` when present) and via a dedicated
`ModelAssumption` (category `"kinetics"`, reason_code
`"TENTATIVE_MASS_ACTION_DEFAULT"`) generated for every tentative law
(§16). **Never upgraded**: nothing in this increment ever changes a
tentative assignment's `assignment_source`, `reason_codes`, or
`law_type` -- they are copied verbatim, exactly as decided.

## 11. Catalytic-context identity -- first-class, corrected pre-commit

**`KineticLawSpecification.enzyme_state_id`/`.protein_id`/`.complex_id`
are first-class fields**, copied verbatim from the source
`KineticLawAssignment`'s own identically-named, identically-exclusive
target fields. An earlier draft of this increment preserved this fact
only as `provenance_refs` text (e.g.
`"catalytic-context::enzyme_state::E_P"`) -- **that text-only encoding
has been removed.** `ModelSpecification` is meant to be the authoritative
handoff to Antimony generation; requiring Increment 9 to parse a
provenance string (or re-derive the fact from the original
`KineticLawAssignmentSet` by cross-referencing `provenance_refs`) to
answer "which catalytic context does this law belong to" would have
defeated that purpose. All three `None` means exactly what it already
means on `KineticLawAssignment`: the reaction as a whole, with no
distinguishing catalytic identity (no catalyst known, or several
catalysts collapsed because their evidence was identical, §12).

## 11a. State-specific catalytic contexts

`KineticLawAssignmentSet` already guarantees at most one assignment per
`(reaction_id, enzyme_state_id, protein_id, complex_id)` catalytic
context (its own construction-time uniqueness check). Because this
increment materializes exactly one `KineticLawSpecification` per
`KineticLawAssignment`, state-specific separation (e.g. `E` vs. `E_P`)
is preserved **structurally, by construction** -- never collapsed to a
parent protein or to the whole reaction, and now directly resolvable via
`enzyme_state_id`/`protein_id`/`complex_id` (§11) rather than only via
provenance text.

## 12. Multiple catalysts/isozymes

Whatever `KineticLawAssignmentSet` already decided is preserved exactly:
if Increment 4 kept two isozymes as separate catalytic contexts (their
evidence differed), two separate `KineticLawSpecification` rows result,
each with its own parameters; if Increment 4 already collapsed them into
one shared, context-free assignment (identical evidence), exactly one
`KineticLawSpecification` results. This increment never re-runs that
collapsing decision and never forces one global kinetic law for a
reaction that legitimately has several catalytic contexts --
`ModelSpecification.kinetic_laws` is an unrestricted flat list, so
nothing here or in the underlying contract prevents more than one law
per `reaction_id` (§13).

## 13. Reaction-to-law linkage

**No extension made to `ReactionSpecification`.** Increment 8
instructions' own Step 14 explicitly allowed one (e.g.
`kinetic_law_ids`) "only if genuinely required" -- inspection found it
is not: `ModelSpecification.kinetic_laws` is already a flat tuple of
`KineticLawSpecification`, each independently naming its own
`reaction_id`, with no uniqueness constraint across `reaction_id`
values. A consumer wanting "every law for reaction R" already gets a
complete, correct answer by filtering `model.kinetic_laws` on
`reaction_id == R` -- exactly as many rows as Increment 4 decided for
that reaction, never fewer. Extending `ReactionSpecification`/
`FullNetwork` (this increment's own structural authority, never
reconstructed -- §5) was therefore correctly avoided, keeping
`AGENT2_CONTRACT_VERSION` unbumped for this reason (§21 of
`app.agent2.version`).

## 14. Module integration

`modules.decompositions[0]` and `modules.module_specifications` are used
directly -- `ModelSpecification.module_decomposition`/
`.module_specifications` are assigned these objects **verbatim**, no
transformation. `assemble_model_specification` first validates that
`len(modules.decompositions) == 1` (Increment 7 v1's own invariant),
raising `ModelSpecificationReferenceError` if zero or more than one is
present -- never silently picking one among alternatives, since none
exist yet.

## 15. Boundary ambiguity preservation

`ModuleDecomposition.candidate_boundary_ids` (every `MEDIUM` boundary
Increment 7 deliberately did not cut) and `.boundary_assessment_ids`
(every `HIGH`/`VERY_HIGH` boundary Increment 7 selected as a cut,
**exactly as produced**, including any selected boundary that did not
end up separating any module because an alternate retained path existed
-- `docs/10_module_decomposition.md` §11a) are carried through
unchanged. `.interfaces` (the actual, realized inter-module interfaces)
are likewise copied verbatim. This increment never creates a new
interface, never reinterprets a selected cut, and never resolves a
candidate boundary -- module-decomposition policy is entirely
Increment 7's concern.

## 16. Model assumptions

`ModelAssumption` (already existing, `app.agent2.types`) is populated
deterministically from eight disclosed-incompleteness categories
(`app.agent2.model_specification.mapping.build_model_assumptions`): the
four Increment 8 instructions' own Step 18 names concretely, plus four
added by later increments:

* one per tentative mass-action law (`category="kinetics"`, `reason_code
  ="TENTATIVE_MASS_ACTION_DEFAULT"`);
* one per `UNASSIGNED` kinetic law (`category="kinetics"`, `reason_code
  ="UNASSIGNED"`);
* one per `PLACEHOLDER` parameter (`category="parameters"`, `reason_code
  ="PLACEHOLDER"`);
* one per preserved `MEDIUM` candidate boundary (`category="modules"`,
  `reason_code="MEDIUM"`);
* **(pre-commit revision)** one per multi-substrate `MICHAELIS_MENTEN`
  law whose combining algebra was left unresolved
  (`category="kinetics"`, `reason_code=
  "MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED"`, §8/§8a) -- the concrete,
  machine-readable disclosure that pairs with `expression = None`,
  identified by `law_type is MICHAELIS_MENTEN and expression is None`
  (the only path that can produce that combination, §8). The statement
  text names all four required facts: the law family is Michaelis-
  Menten, multiple substrates are present, no justified canonical
  multi-substrate algebra has been specified, and serialization must be
  withheld until a concrete expression is available;
* **("Unresolved Kinetic Evidence Disclosure" increment)** one per
  curated kinetic measurement whose reaction applicability remains
  unresolved (`category="kinetics"`, `reason_code=
  "KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED"`), naming the
  measurement id and any tagged protein ids;
* **("Substrate-Anchored Michaelis-Menten Eligibility Refinement"
  increment)** one per `MICHAELIS_MENTEN` law anchored to one real,
  uniquely-attributed `Km` for a multi-reactant reaction
  (`category="kinetics"`, `reason_code=
  "SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION"`) -- distinct
  from the plain multi-substrate-expression disclosure above: this one
  names the specific anchored substrate and source measurement, and
  fires even in the rare case a future `build_expression_and_species`
  extension might resolve an expression for it;
* **("Conservative Reversibility Default for Unresolved Reactions"
  increment)** one per reaction whose curated `reversible` is `None`
  (`category="kinetics"`, `reason_code=
  "REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE"`, `source=
  "app.agent2.reversibility"`) -- the authoritative, machine-readable
  record that the reaction is modeled as tentatively reversible for
  model-construction purposes only (see
  `docs/12_antimony_generation.md` §13), never as curated biochemical
  fact, never fabricating a reverse kinetic parameter, and never usable
  as irreversible-output boundary evidence (§15, `docs/
  09_heuristic_boundary_assessment.md`). The original curated
  `reversible` value on `ReactionSpecification` is never rewritten.

Each `assumption_id` is deterministic, keyed off exactly the one entity
id it describes (e.g. `f"assumption::tentative-law::{kinetic_law_id}"`),
so repeated assembly of the same inputs never produces a duplicate or
differently-ordered assumption set (verified by
`tests/agent2/test_model_specification.py::test_assumptions_are_deterministically_ordered_and_never_duplicated`).
**Deliberately not attempted**: "known incompleteness of regulation
context" (named as an example in Increment 8 instructions' own Step 18)
-- there is no single, already-computed, deterministic signal for this
without inventing a new heuristic (which would be Increment 6's job, not
this one's); generating an assumption per curated-regulation gap would
also risk being extremely noisy. Left as a disclosed limitation (§25)
rather than fabricated.

## 17. Provenance

`ModelSpecification.provenance_refs` carries `network.provenance_refs`
(the Agent 1 lineage already attached to the network) plus a
`"module-decomposition::<decomposition_id>"` tag and a
`"model-specification-policy::<MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION>"`
tag. Finer-grained provenance stays scoped to the object it belongs to,
never flattened away: every materialized `KineticLawSpecification`
carries its own `"kinetic-law-assignment::<assignment_id>"` (full
traceability back to the exact Increment 4 decision) plus the
assignment's own original `provenance_refs`; every `ParameterSpecification`
keeps its own `provenance_refs` exactly as Increment 5 produced them;
every `BoundaryAssessment`/`ModuleSpecification` keeps its own,
already-established provenance fields unchanged. Catalytic-context
identity is **not** carried as a provenance tag (a prior draft did this;
removed pre-commit) -- it is now a first-class field (§11), so encoding
it a second time as text would only risk drift between the two.

## 18. Version compatibility

Before constructing anything, five checks run
(`app.agent2.model_specification.assembler._require_matching_networks`/
`_require_compatible_policy_versions`), raising
`IncompatibleArtifactVersionError` on any mismatch:

* `kinetic_laws.network_id`/`parameters.network_id`/
  `boundaries.network_id`/`modules.network_id` must all equal
  `network.network_id`;
* `parameters.kinetic_law_policy_version` must equal
  `kinetic_laws.kinetic_law_policy_version`;
* `boundaries.kinetic_law_policy_version` must equal
  `kinetic_laws.kinetic_law_policy_version`;
* `boundaries.parameter_policy_version` must equal
  `parameters.parameter_policy_version`;
* `modules.boundary_policy_version` must equal
  `boundaries.boundary_policy_version`.

**Disclosed, not actively checked**: `boundaries.characterization_policy_version`
has no second artifact to compare it against here --
`NetworkCharacterization` itself is not an Increment 8 input (Increment
6 already validated it when it built `BoundaryAssessmentSet`). `FullNetwork`
carries no per-instance "network contract version" field of its own to
check either -- only the process-wide `AGENT2_CONTRACT_VERSION`/
`AGENT1_HANDOFF_VERSION`, already implicitly consistent since every
package in one process imports the same `app.agent2.version` module. No
compatibility shim is ever invented for a genuine mismatch -- assembly
is refused outright.

## 19. Cross-reference validation

`ModelSpecification.__post_init__`'s own existing, already-established
`_validate_model_specification_references` already enforces most of
Increment 8 instructions' Step 22 checklist by construction (compartment/
species/reaction existence via `FullNetwork`'s own validation; kinetic
law -> reaction/parameter/species; module -> reaction/species/parameter/
compartment/enzyme-state/source-boundary/interface-species; decomposition
-> module/boundary/candidate-boundary/interface). This increment's own
pre-commit revision added one more: **(new)** every
`kinetic_laws[].enzyme_state_id` (when set) resolves against
`full_network.enzyme_states` -- a real, complete registry, now that the
field is first-class (§11) rather than provenance text. `.protein_id`/
`.complex_id` remain unchecked, the same disclosed limitation
`_validate_full_network_references` already documents for those entity
types elsewhere (`FullNetwork` tracks no protein/complex registry at
all). Two checks that type cannot perform (it carries no
`KineticLawAssignment` registry to check the `assignment_id` namespace
against) are added defensively by this increment's own
`_validate_cross_artifact_references`:

* every `ParameterSpecification.kinetic_law_assignment_id` resolves
  against the real `kinetic_laws.assignments`;
* every `ModuleSpecification.kinetic_law_assignment_ids` resolves
  against the same set.

A third, trivially-true-by-construction check (every final
`KineticLawSpecification.kinetic_law_id` maps back to a real
`assignment_id`) is also re-verified defensively, mirroring the
established "should never trigger" backstop pattern already used in
`app.agent2.boundaries`/`app.agent2.kinetics`/`app.agent2.parameters`/
`app.agent2.modules`. **Never performed**: mass-balance, elemental/charge
balance, stoichiometric consistency, conservation-law analysis, unit
dimensional consistency or conversion, steady-state/flux/sensitivity/
relaxation-time/stability/parameter-identifiability evaluation -- all
Agent 3/4's job, never this increment's.

## 20. Determinism

Every collection this increment iterates is sorted before use
(`kinetic_laws.assignments` by `assignment_id`, `model_assumptions`'
three source collections each by their own id) so construction order
never leaks into the result. `model_id` (§21) and every `kinetic_law_id`/
`assumption_id` are pure functions of stable input ids, never Python's
built-in `hash()`, never a random UUID, never wall-clock time. Repeated
assembly of the same five inputs produces an identical
`ModelSpecification` (verified by
`tests/agent2/test_model_specification.py::test_repeated_assembly_is_fully_deterministic`).

## 21. Model identity

`model_id = f"model::{network.network_id}::{decomposition.decomposition_id}"`
-- deterministic, depends only on the two most stable upstream ids
(the network's own id and the one decomposition's own deterministic id,
`docs/10_module_decomposition.md` §14), never execution order, never
`hash()`, never a random UUID.

## 22. Explicit non-goals

No Antimony generation, full or module-level -- no Antimony string is
ever produced, no `antimony`/`tellurium`/`roadrunner`/`libsbml` import
exists anywhere in this package (enforced by
`tests/agent2/test_model_specification_scope.py`). No SBML
serialization. No Agent 3 mass-balance/connectivity/unit-consistency/
conservation-law validation. No Agent 4 simulation, calibration,
sensitivity analysis, or parameter fitting. No Agent 5
biological-plausibility critique. No boundary reassessment, no module
recomputation -- both remain entirely Increment 6/7's concern. No
graph-theoretic or numeric-optimization "solution" to a multi-substrate
Michaelis-Menten mechanism was ever attempted -- disclosing it as
unresolved (§8) is the entire response.

**Two `ModelSpecification`/`KineticLawSpecification`-shape extensions
were made, both pre-commit, both corrections rather than new features**
(§6, §10-11): `KineticLawSpecification.assignment_source` changed type
from `ParameterSource` to `KineticLawAssignmentSource`, and three new
optional fields (`enzyme_state_id`/`protein_id`/`complex_id`) were
added. Both are genuine public core-contract changes -- `AGENT2_CONTRACT_VERSION`
was bumped accordingly (§21 of `app.agent2.version`). **One candidate
extension considered and still rejected**: `ReactionSpecification`
gained no `kinetic_law_ids` field (§13) -- `ModelSpecification
.kinetic_laws` already supports many laws per reaction without it.

## 23. Handoff to Increment 9

`ModelSpecification` now carries a complete, internally consistent,
fully cross-referenced mathematical model: real kinetic-law expressions
(species/parameter ids only), every declared parameter linked to its
law, every module and boundary preserved exactly as decided, and a
deterministic assumption trail disclosing every remaining piece of
incompleteness. Increment 9 may serialize this into Antimony (full and
module-specific) but must not reinterpret any modeling decision already
encoded here -- in particular, it must translate `KineticLawSpecification
.expression` into Antimony syntax, never invent a different rate law,
and must resolve the `KineticLawSpecification`/pre-existing (never
populated) `KineticLawSpecification`-via-`ReactionSpecification.kinetic_law_id`
duality itself if it chooses to also populate that older field -- a
decision squarely out of Increment 8's own scope (§13).

**Serialization invariant (mandatory, non-negotiable for Increment 9;
its exact failure policy is Increment 9's own decision, not made
here):**

> A `KineticLawSpecification` whose law family is assigned
> (`law_type is not UNASSIGNED`) but whose `expression` is unresolved
> (`expression is None`, equivalently `has_expression is False`) must
> not be serialized into executable Antimony as if a valid expression
> existed.

Concretely: `law_type is not UNASSIGNED and expression is None` (the
multi-substrate Michaelis-Menten case is the only one the current
implementation produces, §8/§8a, but the check must be general, not
hard-coded to that one law type) means **unresolved expression ≠
serializable expression**. Increment 9 must do one of the following for
that specific reaction's kinetic law -- which one is entirely Increment
9's own decision, not decided here:

* withhold that reaction's executable kinetic expression from the
  generated Antimony (e.g. omit the rate rule, or emit a structurally
  inert placeholder the Antimony/SBML toolchain does not execute as a
  real rate law);
* emit a clearly non-executable diagnostic artifact alongside the model,
  if Increment 9's own contract explicitly defines and permits one; or
* fail that specific serialization path in a controlled, well-typed way
  (e.g. a dedicated Increment 9 error), rather than silently emitting
  something that looks executable but is not scientifically justified.

What Increment 9 must never do: treat `expression is None` on a
non-`UNASSIGNED` law the same as a genuinely missing/`UNASSIGNED` law
(the two are different claims, §8a), and never fabricate an expression
to fill the gap merely to produce syntactically complete Antimony. The
`ModelAssumption` this increment already attaches (§16, reason_code
`MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED`) is the machine-readable
signal Increment 9 should key its own handling off of, in addition to
checking `has_expression` directly on the law itself.

## 24. Testing

`tests/agent2/test_model_specification.py` (45 tests) covers: an empty
network (zero reactions, zero laws, still a valid model); one-reaction/
one-law/one-parameter/one-module assembly; deterministic `model_id` and
full repeated-assembly determinism; every built-in expression template
(`MASS_ACTION`/`REVERSIBLE_MASS_ACTION`/`MICHAELIS_MENTEN`/`HILL`)
confirmed empirically against the real Increment 4/5 pipeline, plus
`CUSTOM` verbatim-text preservation and `UNASSIGNED` no-expression
handling; **a genuinely multi-substrate `MICHAELIS_MENTEN` law
(constructed via curated reported-law text, since the non-curated
heuristic path can never produce one) confirmed to keep
`law_type=MICHAELIS_MENTEN`, receive `expression=None` (never a
simplified equation, never a status marker), preserve every declared
parameter/species/catalytic-context/assignment-source, and generate a
matching `ModelAssumption` (reason_code
`MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED`) naming all four required
facts**; a dedicated test confirming the removed string sentinel is
neither importable from `app.agent2.model_specification.mapping` nor
present in any real assembled output; confirmation no kinetic-law
decision is ever recomputed; parameter linkage (correct assignment/law,
dangling-reference rejection, no duplication, byte-for-byte
value/unit/source preservation); tentative mass-action
machine-identifiability (via `reason_codes`/`assumptions`, since
`assignment_source` alone is `HEURISTIC` either way) and never-upgraded
status; enzyme-state specificity (`E`/`E_P` never collapsed, resolved
via the first-class `enzyme_state_id` field, separate parameters);
multiple-catalyst behavior (a genuinely collapsed isozyme pair stays
collapsed, divergent contexts stay separate); module integration
(exactly-one-decomposition enforcement, verbatim module/boundary/
interface preservation, candidate-boundary assumption generation);
`ModelAssumption` generation (all five categories, deterministic
ordering, no duplicates); version-compatibility rejection for every
cross-checked policy-version pair and for a `network_id` mismatch, with
no compatibility shim; and structural-validation rejection for a
dangling parameter/module kinetic-law-assignment reference, a dangling
reaction reference, a dangling module species reference, a dangling
kinetic-law enzyme-state reference, and zero decompositions.
`tests/agent2/test_kinetics_contracts.py` also gained five tests
confirming `KineticLawSpecification.assignment_source` rejects a
`ParameterSource` value (not just a bare string), that the new
`enzyme_state_id`/`protein_id`/`complex_id` fields default to `None` and
enforce the same mutual-exclusivity rule as `KineticLawAssignment`, that
`expression=None` is now legal for a non-`UNASSIGNED` `law_type` (a
whitespace-only expression is silently normalized to `None`, not
rejected), and `has_expression`'s own true/false behavior.
`tests/agent2/test_model_specification_scope.py` (10 tests) confirms,
structurally (via `ast`, not substring search), that
`app.agent2.model_specification` never imports a modeling/simulation
library, Agent 1's runtime, or an LLM client, never calls
`assess_boundaries`/`decompose_network`/`assign_kinetic_laws`/
`declare_parameters` itself (never recomputes an upstream stage), and
never invokes simulation or fitting -- backed by two real, executed
assemblies confirming no Antimony-shaped field exists and that
`boundary_assessments`/`module_decomposition`/`module_specifications`
are exactly the objects supplied as input.

## 25. Known limitations

* "Known incompleteness of regulation context" (§16) generates no
  `ModelAssumption` -- no single, already-computed, deterministic,
  non-noisy signal exists for it without inventing a new heuristic.
* `boundaries.characterization_policy_version` is preserved but not
  actively cross-checked (§18) -- `NetworkCharacterization` is not an
  Increment 8 input.
* A multi-substrate `MICHAELIS_MENTEN` law's *mechanism* (ordered-
  sequential vs. ping-pong vs. random) is never determined -- only
  disclosed as unresolved (§8). A future increment could resolve this if
  Agent 1 ever curates a mechanism-specific classification; nothing here
  guesses one from structure alone.
* `is_tentative` remains derivable only via `reason_codes` (a
  `KineticLawReasonCode` tuple), not via a boolean field on
  `KineticLawSpecification` itself -- consistent with
  `KineticLawAssignment`'s own existing design (`is_tentative` is a
  derived property there too, never a stored field), but still requires
  a downstream consumer to know to check `reason_codes` rather than
  reading `assignment_source` alone (§10).

None of these block correctness: each is a disclosed, deliberate scope
boundary, never a silent wrong answer.

**Resolved in this increment's own pre-commit revision** (previously
listed here as limitations, now corrected -- see §6/§10/§11/§22 for the
full rationale): `KineticLawSpecification.assignment_source` was a
lossy `ParameterSource` bridge from `KineticLawAssignmentSource` -- now
the correct type, copied verbatim; a law's catalytic context was
disclosed only as `provenance_refs` text -- now first-class
`enzyme_state_id`/`protein_id`/`complex_id` fields; a multi-substrate
`MICHAELIS_MENTEN` law received a simplified, scientifically-unjustified
combining expression -- now explicitly disclosed as unresolved instead.

## 26. Final architectural rule

> `ModelSpecification` is the authoritative mathematical-model contract
> produced by Agent 2.

> It integrates structural network knowledge, kinetic-law decisions,
> parameter declarations, boundary assessments, and module decomposition
> without performing simulation or serialization.

> Increment 9 may serialize this specification into complete and
> module-specific Antimony artifacts, but it must not reinterpret the
> modeling decisions already encoded here.
