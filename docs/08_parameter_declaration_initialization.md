# Agent 2 Parameter Declaration / Initialization Contract

## 1. Purpose

Increment 5 declares the parameters every Increment 4 `KineticLawAssignment`
requires, and initializes each declared parameter from curated Agent 1
knowledge where a deterministic policy permits -- explicitly marking
every remaining parameter as an unresolved placeholder otherwise. **The
output answers "what parameters must exist for this model," never "what
are the best values."**

## 2. Pipeline position

```
Agent1CuratedKnowledgeView
    -> Whole-Network Assembly
    -> FullNetwork
    -> Reaction and Enzyme-State Characterization
    -> NetworkCharacterization
    -> Kinetic-Law Assignment
    -> KineticLawAssignmentSet
    -> Parameter Declaration / Initialization (this increment)
    -> ParameterDeclarationSet
    -> Heuristic Boundary Assessment (future Increment 6)
    -> Module Decomposition
    -> ModelSpecification
    -> Antimony Generation
```

Agent 1 is input-only for this increment; nothing in
`agent1-biochemical-curator` was modified to implement it.

## 3. Input contract

`declare_parameters(assignments: KineticLawAssignmentSet, network: FullNetwork) -> ParameterDeclarationSet`
-- exactly the two-argument signature the increment's own instructions
specified, with no deviation this time. `FullNetwork` supplies everything
this stage needs beyond `KineticLawAssignmentSet` itself: the curated
`kinetic_measurements` to initialize parameter values from, and the
`reactions`/`species` structure needed to enumerate a Michaelis-Menten
reaction's substrates. `declare_parameters` raises `ParameterReferenceError`
if `assignments.network_id != network.network_id`.

## 4. Output contract

`ParameterDeclarationSet`: `network_id`, `kinetic_law_policy_version`
(carried through from the source `KineticLawAssignmentSet`, not
recomputed), `parameter_policy_version`, `parameter_specifications`,
`assumptions`, `provenance_refs`. Unlike `KineticLawAssignmentSet` (which
covers every reaction) there is no "one entry per X" coverage invariant
here -- a reaction whose assignment is `UNASSIGNED` contributes zero
parameters (§7). What is enforced: every parameter's
`kinetic_law_assignment_id` is set, no `parameter_id` repeats
(`ParameterDeclarationSet.__post_init__`), and, after construction,
`declare_parameters` itself confirms every `kinetic_law_assignment_id`
actually names a real assignment in the source set and that no parameter
ever carries `ParameterSource.CALIBRATED` -- both defensive backstops
raised as `ParameterReferenceError`, mirroring the identical pattern
`app.agent2.kinetics.selector.assign_kinetic_laws` already established.

## 5. Reused `ParameterSpecification` -- the one extension

`ParameterSpecification`/`ParameterSource` (`app.agent2.types`) are
reused unchanged except for one new field:
`kinetic_law_assignment_id: str | None = None`. This is the essential
missing field found on inspection (Step 6): the type's existing
`reaction_id` field cannot disambiguate a parameter declared for one
catalytic context (e.g. one specific `EnzymeState`) from a sibling
context on the same reaction, and every parameter Increment 5 declares
must trace back to exactly one `KineticLawAssignment` (§13/§14). No other
field was added -- `value`/`unit`/`source`/`source_reference`/
`uncertainty_text`/`provenance_refs`/`lower_bound`/`upper_bound`/`fixed`
already covered everything else this increment needs.
`ParameterDeclarationSet` itself is the only genuinely new type, and it
lives in `app.agent2.parameters`, not `app.agent2.types`.

## 6. Parameter identity and naming policy

Deterministic, content-derived, never a random UUID -- `parameter_id`
and `name` are set to the identical string
(`policy.build_parameter_slug`): `f"{prefix}_{reaction_id}"`, optionally
followed by the catalytic-context suffix (`enzyme_state_id`/`protein_id`/
`complex_id`, whichever is set) and/or a substrate id (for a per-substrate
`Km`) -- e.g. `Km_r1_es1_glc`, `kcat_r1_hk1`, `k_r1`. `parameter_id` and
`name` are deliberately identical (a simplification: the increment's own
naming examples do not distinguish an "id" from a "name," and inventing
an under-specified separate short-symbol policy was judged out of scope).
The reaction's own curated id is used directly (e.g. `r1`), not a
separately-invented flux-numbering scheme (`J1`) -- the exact syntax may
differ from the instructions' own illustrative examples, but remains
deterministic, stable, and reproducible from the same inputs.

## 7. Parameter requirements by kinetic-law type

* **`MASS_ACTION`** -- exactly one parameter, `k`. (A reverse rate
  constant is never added here even when the underlying reaction is
  curated `reversible=True` -- see §15 for why: that is
  `REVERSIBLE_MASS_ACTION`'s own, separate policy, and adding `kr` to a
  law the assignment stage itself chose *not* to represent as reversible
  would contradict that decision.)
* **`REVERSIBLE_MASS_ACTION`** -- `kf`, `kr`.
* **`MICHAELIS_MENTEN`** -- `kcat`, plus one `Km` per `REACTANT`
  participant of the reaction (zero reactants -> zero `Km` parameters).
  No `Ki` is ever declared here (Step 8: "do not invent inhibition
  constants" -- plain Michaelis-Menten has no inhibition term).
* **`HILL`** -- `Vmax`, `Km`, `n` (the Hill coefficient).
* **`CUSTOM`** -- never symbolically parsed (Step 8/12). Every curated
  measurement in this context whose `parameter_type` matches a
  recognized family (§9) is declared, one parameter per family present,
  in a fixed order (`k`, `kf`, `kr`, `kcat`, `Vmax`, `Km`, `Ki`, `Keq`,
  `n`); if none match, exactly one documented placeholder, `k_custom`,
  is declared instead.
* **`UNASSIGNED`** -- no parameters at all.

## 8. `ParameterSource` policy

Reused unchanged (`CURATED`/`LITERATURE_DERIVED`/`DEFAULT`/`PLACEHOLDER`/
`CALIBRATED`). This package's own mapping:

* **`CURATED`** -- one or more curated measurements match this parameter
  slot's recognized type and this catalytic context, and (when more than
  one) they all report the identical value and unit.
* **`LITERATURE_DERIVED`** -- the same condition, but the representative
  matching measurement (lowest `id`, for determinism) names a
  `publication_id`. This is this package's own considered, documented
  distinction between the two (`CuratedKineticMeasurement` does not
  itself draw this line): a measurement explicitly attributed to a
  publication is `LITERATURE_DERIVED`; one without that attribution
  (e.g. a bare connector-curated database value) is `CURATED`.
* **`DEFAULT`** -- vocabulary member reused unchanged, but never actually
  assigned by this increment's logic: no conventional default numeric
  value is established anywhere in this codebase to assign
  deterministically, and inventing one would violate "do not fabricate
  numerical values" (Step 16). `PLACEHOLDER` is used in every case the
  instructions' own text offered `DEFAULT` as an alternative.
* **`PLACEHOLDER`** -- no matching curated measurement, or matching
  measurements disagree (§10); `value=None`.
* **`CALIBRATED`** -- never assigned by this package; reserved exclusively
  for a future Agent 4 feedback loop. `declare_parameters` defensively
  verifies no declared parameter ever carries it (§4).

## 9. Curated-measurement recognition vocabulary

`CuratedKineticMeasurement.parameter_type` is deliberately an open
`VARCHAR` on Agent 1's side ("the specification requires it to remain an
open VARCHAR... must never be restricted," per that field's own
governing comment in `agent1-biochemical-curator`), so Agent 2 cannot
rely on a closed Agent-1-defined enum to recognize a measurement's kind.
`policy.py` instead maintains its own small, closed, case-insensitive
recognition vocabulary (`KM_TYPES`, `KCAT_TYPES`, `VMAX_TYPES`,
`KI_TYPES`, `KEQ_TYPES`, `HILL_COEFFICIENT_TYPES`, `RATE_CONSTANT_TYPES`,
`FORWARD_RATE_TYPES`, `REVERSE_RATE_TYPES`), matched only against
`parameter_type` -- never `reported_parameter_type`, which is Agent 1's
raw as-reported text and is never parsed here. This vocabulary widens
what a curated measurement can *initialize*; it never widens what
parameters a kinetic-law type itself requires (§7) -- a `Ki`-recognized
measurement is still never declared for `MICHAELIS_MENTEN`.

## 10. Multiple-measurement policy

Never averaged, never ranked, never silently chosen among (Step 12).
`policy.measurements_agree` checks every matching measurement for
*exact* value **and** unit equality (`Decimal`/string equality, never a
tolerance). All agree -> one shared `CURATED`/`LITERATURE_DERIVED`
initialization, `provenance_refs` naming every agreeing measurement's id.
Any disagreement (including two measurements agreeing on value but
reported in different units -- see §11) -> `PLACEHOLDER`, `value=None`,
`provenance_refs` still names every candidate id, and `uncertainty_text`
records the disagreement explicitly and factually.

## 11. Unit policy

Units are never converted or normalized (Step 13). Preserved exactly as
curated on `value`/`unit`. Two measurements reporting the "same"
physical quantity in different units are treated as disagreeing (§10),
not reconciled -- unit reconciliation is left to future calibration
(Agent 4), never guessed here.

## 12. Provenance preservation

Every initialized parameter's `provenance_refs` names every curated
measurement id that contributed to its resolution -- not only the one
whose value/unit was used representatively. `source_reference` carries
the representative measurement's own `publication_id`/`source_id`/
`source` (in that priority order) verbatim -- never reformatted,
reworded, or fabricated. A `PLACEHOLDER` from disagreement still
preserves every candidate's id in `provenance_refs`, so the conflict
itself remains traceable even though no value was chosen.

## 13. Enzyme-state specificity

A reaction's distinct catalytic contexts (never collapsed by Increment 4
for distinct `EnzymeState`s, §14 of `docs/07`) each get their own,
completely independent parameter declaration: `E`'s parameters and
`E_P`'s parameters are declared, named, and initialized from
`E`/`E_P`'s own curated evidence only. A curated measurement tagged for
one state is never visible when declaring a sibling state's parameters
(`builder._evidence_for`, strict tagged-only matching whenever a reaction
has more than one catalytic context -- §14 below). An `EnzymeState`
lacking any curated measurement of its own still gets its own
`PLACEHOLDER` parameter, independently of whatever its sibling state
resolved to.

## 14. Multiple catalysts / isozymes

Mirrors the same evidence-scoping rule Increment 4 itself uses when
*deciding* a kinetic law (independently re-derived here, since that logic
is a private implementation detail of `app.agent2.kinetics.selector`, not
exported -- see `builder._evidence_for`'s own docstring): when an
assignment is the **sole** catalytic context for its reaction (no
sibling assignment shares that `reaction_id` -- true for a single known
catalyst, a no-catalyst reaction, or several isozymes Increment 4 already
collapsed into one shared assignment because their kinetic-law evidence
agreed), every curated measurement for that reaction is fair game for
parameter initialization, tagged or not -- there is no sibling context a
differently-tagged measurement could rightfully belong to instead. When
more than one distinct context exists for the reaction (isozymes
Increment 4 kept separate because their evidence differed), each
context's parameters are initialized only from measurements tagged with
that context's own exact protein/complex identity -- never a sibling
isozyme's.

## 15. Tentative mass-action default policy

`KineticLawAssignment.is_tentative`/`TENTATIVE_MASS_ACTION_DEFAULT`
(Increment 4's own revision) is followed through explicitly and
conservatively: a tentative assignment's single `k` parameter is
**always** declared `PLACEHOLDER`, unconditionally -- never mapped to a
curated measurement even when one happens to exist for that context. The
underlying kinetic mechanism itself is, by `TENTATIVE_MASS_ACTION_DEFAULT`'s
own definition, unconfirmed; treating an incidentally-matching measurement
as though it justified this specific reaction's rate constant would
smuggle back exactly the epistemic overclaim Increment 4's revision
introduced that reason code to prevent. This is a deliberate, narrower
exception to the general curated-measurement-mapping policy (§9-10), not
an oversight -- every other, non-tentative `MASS_ACTION` assignment
(deterministic-structural, or a hypothetical future non-tentative
heuristic) still maps curated evidence normally.

## 16. Placeholder philosophy

A placeholder parameter's status is machine-readable through the same
existing, established mechanism `ParameterSpecification` already
provides -- `source is ParameterSource.PLACEHOLDER`
(`ParameterSpecification.is_placeholder`) -- rather than a new field:
`value is None` accompanies it structurally, and `uncertainty_text`
always carries a concise, factual, deterministic (never LLM-generated)
explanation of *why*: no curated measurement matched, curated
measurements disagreed, the assignment is a tentative default, or (for
`CUSTOM` with no recognized metadata) the law was never symbolically
parsed at all. `is_placeholder` is this package's canonical
machine-readable "requires calibration" marker, exactly paralleling
`KineticLawAssignment.is_tentative` from Increment 4.

## 17. Determinism

`declare_parameters` is a pure function: the same
`(KineticLawAssignmentSet, FullNetwork)` pair always produces an equal
`ParameterDeclarationSet`. Assignments are processed in
`assignment_id`-sorted order; every `provenance_refs`/measurement-id
collection this package produces is `tuple(sorted(...))`; a shared
representative measurement is always the lowest-`id` match among ties,
never handoff/collection order. Parameter identity (§6) is a pure
function of `(prefix, reaction_id, catalytic-context suffix, substrate
id)` -- changing the order assignments or measurements were declared or
collected in never changes any `parameter_id`.

## 18. Validation

`require_kinetic_law_assignment_set`/`require_full_network`
(`validation.py`) confirm input types.
`ParameterDeclarationSet.__post_init__` rejects a parameter with no
`kinetic_law_assignment_id` and rejects a duplicate `parameter_id`.
`declare_parameters` itself additionally verifies, after construction,
that every `kinetic_law_assignment_id` actually names a real assignment
in the source set, and that no declared parameter ever carries
`ParameterSource.CALIBRATED` -- both raised as `ParameterReferenceError`,
both defensive backstops that should never actually trigger given a
correct implementation, exactly as `app.agent2.kinetics`/
`app.agent2.characterization` established for their own increments.

## 19. Explicit non-goals

This increment never: selects, fits, estimates, optimizes, or calibrates
a numeric parameter value; assesses a `BoundaryLikelihood`; decomposes a
module; generates Antimony; or implements Agent 3 validation, Agent 4
simulation/fitting, or Agent 5 critique. It never invents a
`ParameterSource.CALIBRATED` value, never fabricates a plausible number
for a `PLACEHOLDER`, and never converts or reconciles units. Structural
tests in `tests/agent2/test_parameters_scope.py` verify none of these
concepts appear anywhere in `app.agent2.parameters`.

## 20. Future Agent 4 interaction

`ParameterDeclarationSet` is exactly the input a future Agent 4
calibration stage needs to know what to fit: every `PLACEHOLDER`
parameter (`is_placeholder`) names a real gap requiring a numeric value,
every `CURATED`/`LITERATURE_DERIVED` parameter carries the curated
starting point (and its full provenance, §12) a calibration might refine
or confirm, and `kinetic_law_assignment_id` lets Agent 4 cross-reference
back to `is_tentative` (Increment 4) to prioritize a tentative
assignment's parameters for scrutiny first. `ParameterSource.CALIBRATED`
is the value Agent 4's own feedback, and only that feedback, may
eventually assign -- never this package.

## 21. Testing

`tests/agent2/test_parameters.py` covers every kinetic-law type's
declared parameter set (`MASS_ACTION`/`MICHAELIS_MENTEN`/
`REVERSIBLE_MASS_ACTION`/`HILL`/`CUSTOM`/`UNASSIGNED`); placeholder
creation and curated initialization (single measurement, agreeing
multiple measurements, disagreeing multiple measurements); state-specific
and isozyme independence (including the collapsed-isozyme evidence-folding
case); the tentative-default placeholder override; provenance
preservation; determinism under permuted order-insensitive collections;
parameter-identity stability; duplicate detection; and every documented
validation failure (including a forbidden `CALIBRATED`).
`tests/agent2/test_parameters_scope.py` covers structural scope-safety
(§19).

## 22. Versioning

`PARAMETER_DECLARATION_POLICY_VERSION = "parameter-declaration-v1"`
introduced for the first real parameter-declaration rule set.
`AGENT2_CONTRACT_VERSION` bumped `"0.4"` -> `"0.5"`:
`ParameterSpecification` (`app.agent2.types`) gained
`kinetic_law_assignment_id` (§5) -- a real `app.agent2.types` shape
change per this repository's own bump criterion, unlike Increment 4
(which added no field to any `app.agent2.types` type and so did not
bump it). `AGENT1_HANDOFF_VERSION` is unchanged -- Agent 1 was not
modified. Full reasoning recorded in `app/agent2/version.py`'s own
docstring.

## 23. Final architectural statement

> Parameter declaration identifies which parameters exist and captures
> the best currently available curated initialization. It never performs
> optimization, estimation, fitting, or calibration. Numerical refinement
> is exclusively the responsibility of Agent 4.
