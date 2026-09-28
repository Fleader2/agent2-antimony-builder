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
  **Executable Rate-Law Fallback increment**: when the reaction has more
  than one `REACTANT` participant (genuinely multi-substrate -- no single
  kcat/Km combining algebra is ever asserted, §24 of this document), one
  additional `k` (if the reaction's effective reversibility --
  `app.agent2.reversibility.effective_reversible` -- is irreversible) or
  independently-molecularity-derived `kf`/`kr` (if reversible) is
  declared *after* kcat/Km, never replacing or reordering them --
  `app.agent2.parameters.builder._declare_multi_substrate_mm_fallback`.
  Real curated/AI-predicted rate-constant evidence (a `K`/`KF`/`KR`
  measurement for this exact context) still takes precedence over a
  heuristic default here, exactly like every other mass-action-style slot
  in this package.
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
`ParameterSource.CALIBRATED` value, and never converts or reconciles a
real, evidence-based measurement's units. Structural tests in
`tests/agent2/test_parameters_scope.py` verify none of these concepts
appear anywhere in `app.agent2.parameters`.

**Since the Heuristic Simulation Parameter Initialization increment**
(§24), a true `PLACEHOLDER` -- one with neither experimental nor
AI-predicted evidence, for a parameter kind this package's own
centralized policy supports -- *is* assigned a disclosed, non-evidentiary
starting number (`ParameterSource.HEURISTIC_INITIALIZATION`), never
silently and never confused with any evidence-based source. This is a
narrower, more precise restatement of the original "never fabricates a
plausible number for a `PLACEHOLDER`" non-goal, not a reversal of it: the
number is real (a simulator can use it), but it is exhaustively
disclosed as an Agent-2-invented initialization assumption, never as a
biochemical claim -- see §24 for the full boundary.

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
eventually assign -- never this package. Since §24, a
`HEURISTIC_INITIALIZATION` parameter is exactly as much a calibration
target as a bare `PLACEHOLDER` ever was -- Agent 4 should treat both as
"no real evidence exists here yet," distinguishing only `AI_PREDICTED`
(a weaker, but non-arbitrary, prior) as a separate category worth
weighting differently during fitting.

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
(§19). `tests/agent2/test_heuristic_initialization.py` (§24) covers the
full 4-tier precedence waterfall, every supported parameter kind's
molecularity-dependent unit, the unsupported/no-expression-law boundary,
determinism, explicit provenance, and a Run-6-shaped mixed-evidence
fixture; `tests/agent2/test_model_specification.py` additionally confirms
the Antimony-executability consequence (§24.6).

## 22. Versioning

`PARAMETER_DECLARATION_POLICY_VERSION` introduced as
`"parameter-declaration-v1"` for the first real parameter-declaration
rule set; bumped to `"parameter-declaration-v2"` by the Heuristic
Simulation Parameter Initialization increment (§24) -- a narrower-reading
policy-version bump (new, additive initialization behavior; no existing
declaration behavior changed for a parameter that already had real
evidence). `HEURISTIC_INITIALIZATION_POLICY_VERSION =
"heuristic-initialization-v1"` introduced by that same increment,
versioning the heuristic-default policy (`heuristic_defaults.py`)
independently of the declaration policy that consumes it. `AGENT2_CONTRACT_VERSION`
bumped `"0.4"` -> `"0.5"` for this increment's original
`kinetic_law_assignment_id` field addition (§5) -- unchanged again by
§24, which added two `ParameterSource` enum values (never a shape change
under this repository's own bump criterion) but no new field to any
`app.agent2.types` type. `AGENT1_HANDOFF_VERSION` is unchanged by either
-- Agent 1 was not modified for this increment. Full reasoning recorded
in `app/agent2/version.py`'s own docstring.

## 23. Final architectural statement

> Parameter declaration identifies which parameters exist and captures
> the best currently available curated initialization. It never performs
> optimization, estimation, fitting, or calibration. Numerical refinement
> is exclusively the responsibility of Agent 4.

## 24. Heuristic Simulation Parameter Initialization increment

### 24.1 Purpose

A parameter left as a bare `PLACEHOLDER` after §1-23's own curated/
AI-predicted initialization has *no* numeric value at all -- Antimony
correctly refuses to generate an executable rate law for it (§12). This
increment closes that gap for every parameter kind its own policy
supports, assigning a deterministic, disclosed, non-evidentiary starting
value so a simulator has *something* numerically well-behaved to run
with, while making it structurally impossible to confuse that value with
real biochemical evidence or a future Agent 4 calibration result.

### 24.2 Precedence

`LITERATURE_DERIVED`/`CURATED` > `AI_PREDICTED` >
`HEURISTIC_INITIALIZATION` > `PLACEHOLDER`
(`app.agent2.parameters.initializer.initialize_with_fallback`). A lower
tier is consulted **only** when the previous tier found a genuine,
complete absence of matching evidence (`provenance_refs == ()`) --
disagreeing real evidence at any tier is preserved as its own disclosed,
terminal `PLACEHOLDER` (with every conflicting candidate's id retained),
never silently discarded in favor of a lower-precedence guess.

`ParameterSource.AI_PREDICTED` is new: a GotEnzymes2-sourced measurement
(Agent 1.x Increment C.11, identified on this side by the literal string
`CuratedKineticMeasurement.source == "GOTENZYMES"`) is excluded
unconditionally from `initialize_from_evidence` (which would otherwise
mislabel it `CURATED`, since it never carries a `publication_id`) and
resolved instead by the new `initialize_from_ai_predicted_evidence`,
using its own canonical `normalized_value`/`normalized_unit` (Agent 1.x
Increment C.12) rather than its raw, source-specific reported figure --
an AI-predicted value is never a human-authored, source-attributed
report the way a real literature figure is.

### 24.3 Heuristic defaults

`app.agent2.parameters.heuristic_defaults` centralizes every default
behind exactly two reference constants: `REFERENCE_RATE_PER_SEC = 1`
(per second) and `REFERENCE_CONCENTRATION_NM = 1000` (nM). Every other
default is derived, never chosen independently:

| `ParameterKind` | Default value | Canonical unit |
|---|---|---|
| `CONCENTRATION` (Km/Ki-like) | `REFERENCE_CONCENTRATION_NM` | `nM` |
| `RATE_FIRST_ORDER` (kcat, ...) | `REFERENCE_RATE_PER_SEC` | `per_sec` |
| `FLUX` (Vmax-like) | `REFERENCE_RATE_PER_SEC * REFERENCE_CONCENTRATION_NM` | `nM_per_s` |
| `MASS_ACTION_RATE` (k/kf/kr) | `REFERENCE_RATE_PER_SEC / REFERENCE_CONCENTRATION_NM ** (n - 1)` | `per_sec` (n=1) / `nM_per_s` (n=0) / `per_nMs` (n=2) / `"nM^{1-n} s^-1"` (any other n) |
| `UNSUPPORTED` (Hill n, Keq) | -- | -- (`None`; never an invented convention) |

The mass-action formula is chosen so that, at exactly the reference
concentration (every reactant/product at `REFERENCE_CONCENTRATION_NM`),
*every* heuristically-initialized mass-action reaction -- regardless of
its own order -- produces the identical characteristic flux
(`REFERENCE_RATE_PER_SEC * REFERENCE_CONCENTRATION_NM`, `nM_per_s`): one
coherent rationale for every order's magnitude, never an unexplained
per-order magic number. `n` is the reaction's own molecularity for the
direction being initialized -- reactant-stoichiometry sum for a forward
constant, product-stoichiometry sum for a reverse one
(`app.agent2.parameters.builder._reaction_molecularity`) -- computed
independently per direction, never symmetrized or related through a
fabricated equilibrium constant (§24.4).

### 24.4 Reversible reactions

`_declare_reversible_mass_action` computes forward and reverse
molecularity independently (from `ParticipantRole.REACTANT` and
`ParticipantRole.PRODUCT` respectively) and initializes each direction's
own rate constant through the same 4-tier waterfall. A reaction need not
be symmetric (`A + B <=> C` is bimolecular forward, unimolecular
reverse); the two resulting values are never claimed to be an
experimentally known equilibrium, and no `kr`/equilibrium constant is
ever invented for a law that does not itself declare one.

### 24.5 The `TENTATIVE_MASS_ACTION_DEFAULT` boundary

A `MASS_ACTION` assignment flagged `TENTATIVE_MASS_ACTION_DEFAULT`
(Increment 5, Step 16) never maps *real* evidence -- curated or
AI-predicted -- to its rate constant, even when a matching measurement
exists for the exact context: the underlying mechanism assumption itself
is unconfirmed, so attributing real evidence to it would misrepresent
that evidence as validating an assumed mechanism. This increment does
**not** extend that exclusion to heuristic initialization: the law type
is still `MASS_ACTION` with a built expression and a fully declared `k`
slot -- not `expression=None`, not an unsupported `KineticLawType`, and
not "no declared parameter structure" (the three conditions §24.6's own
boundary actually excludes) -- and a heuristic value makes no
evidentiary claim the tentative mechanism could be misrepresented as
validating. `_declare_mass_action` therefore always calls
`initialize_with_fallback` for a tentative default too, but with an
empty evidence tuple (skipping straight to the heuristic tier), and
overrides the resulting `uncertainty_text` to still name the tentative
mechanism explicitly.

### 24.6 Rate-law boundary: parameters only, never a new rate law

This increment initializes declared parameter *slots* only. A reaction
whose kinetic law has `expression=None` (an unresolved multi-substrate
Michaelis-Menten, `UNASSIGNED`, or `CUSTOM`) never gets a new rate law
invented for it here -- `_declare_custom` is deliberately unmodified
(CUSTOM structurally means "unsupported mechanism"; no molecularity or
dimension can be safely inferred for its generic `k`/`kf`/`kr`/etc. slot,
so it stays a bare `PLACEHOLDER`), and a substrate-anchored
multi-substrate Michaelis-Menten's every Km slot (anchored or not) and
its kcat are still heuristically initialized even though the reaction's
overall `expression` stays `None` -- initializing a law's *parameters*
is legitimate independent of whether its *expression* is resolved.

The practical, positive consequence: `ParameterSpecification.has_value`
is a pure, source-agnostic value-presence check
(`self.value is not None`), so a reaction whose *only* prior blocker was
missing parameter numbers (never an unresolved expression) now correctly
becomes `AntimonyArtifactReadiness.EXECUTABLE` once every one of its
parameters is heuristically initialized -- confirmed by
`tests/agent2/test_model_specification.py::test_heuristic_initialization_makes_a_value_only_blocked_reaction_executable`.
A reaction with a genuinely unresolved expression remains correctly
non-executable regardless
(`test_heuristic_initialization_never_makes_an_unresolved_expression_law_executable`).

### 24.7 Boundary-assessment interaction

`app.agent2.boundaries.policy.compute_parameter_basis` (§9's own
Increment 6 policy) treats `HEURISTIC_INITIALIZATION` identically to the
pre-existing `ParameterSource.DEFAULT` for the `BoundaryParameterBasis
.DEFAULT_ONLY` classification: both are values Agent 2 invented itself,
from its own policy, never real evidence -- conceptually identical for
this qualitative disclosure, even though they remain two distinct,
never-confused `ParameterSource` values everywhere else.
`ParameterSource.AI_PREDICTED` is deliberately left unhandled there (it
falls through to the safe `MIXED` classification) -- a separate design
question this increment did not need to resolve.

### 24.8 Real coverage evaluation (Pilot 2 Run 6 network, sce00061)

Run against the real, saved Agent 1 handoff for the 38-reaction yeast
fatty-acid-biosynthesis network (the same handoff Pilot 2 Run 6's own
report used), *not* through Agent 4:

| | Before (Run 6 report) | After (this increment) |
|---|---|---|
| Total parameters | 41 | 41 |
| `LITERATURE_DERIVED` | 1 | 1 |
| `AI_PREDICTED` | 0 | 0 (none of this handoff's own measurements happen to be GotEnzymes2-sourced) |
| `HEURISTIC_INITIALIZATION` | 0 | 40 |
| `PLACEHOLDER` | 40 | 0 |
| Reactions | 38 | 38 |
| Non-executable (`expression=None`) | -- | 1 (a multi-substrate Michaelis-Menten reaction; unaffected by this increment, per §24.6) |
| Non-executable (other reasons -- missing values) | -- | 0 |

Heuristic-initialized parameters by canonical unit: `per_nMs` 25 (the
network's dominant shape -- catalyzed, reversible, bimolecular
`TENTATIVE_MASS_ACTION_DEFAULT` reactions), `per_sec` 10, `nM^-2 s^-1` 3
(trimolecular mass-action reactions), `nM` 2 (Km-like slots). The one
remaining non-executable reaction is exactly the real, already-known
ACC1/malonyl-CoA-ACP substrate-anchored multi-substrate Michaelis-Menten
case (§24.6) -- correctly left for a future "Executable Rate-Law
Fallback" increment, never guessed at here.

### 24.9 Explicit non-goals (this increment specifically)

Never invents a new rate law for `expression=None`; never assigns
`ParameterSource.CALIBRATED`; never runs Agent 4 calibration or a full
pilot; never overwrites `LITERATURE_DERIVED`/`CURATED`/`AI_PREDICTED`
evidence, even when it disagrees with itself (§24.2); never assigns a
heuristic default to a parameter kind not named in §24.3's own table.

## 25. Executable Rate-Law Fallback increment

The one real limitation §24.8 found -- the last remaining non-executable
reaction, a genuinely multi-substrate Michaelis-Menten law -- is resolved
by this increment, entirely on the parameter-declaration side by
`app.agent2.parameters.builder._declare_multi_substrate_mm_fallback`
(the expression-construction side lives in
`app.agent2.model_specification.mapping` -- see
`docs/11_model_specification_assembly.md` §8 for the full picture).

### 25.1 What gets declared

Fires only when a `MICHAELIS_MENTEN` assignment's own reactant count is
greater than one (§7's own MICHAELIS_MENTEN bullet, updated). Never
touches the existing kcat/Km declarations -- appends after them:

* **Irreversible** (curated `reversible=False`, or curated `True`/`None`
  routed through `app.agent2.reversibility.effective_reversible` as
  `False` -- today, only an explicit curated `False` ever produces this):
  one `k`, molecularity from summed `REACTANT` stoichiometry.
* **Reversible** (curated `True`, or curated `None` -- "assumed
  reversible" -- via the same `effective_reversible`): `kf` (forward
  molecularity) and `kr` (reverse molecularity, from summed `PRODUCT`
  stoichiometry), computed and initialized completely independently --
  never related through a fabricated equilibrium constant, mirroring
  `_declare_reversible_mass_action`'s own established policy exactly.

Each new parameter is resolved through the same `initialize_with_fallback`
waterfall (§24.2) using this assignment's own already-filtered evidence,
restricted to the `K`/`KF`/`KR` recognized families (§9) -- a real
curated or AI-predicted rate-constant measurement for this exact context
still wins; only in the (expected, common) case none exists does this
fall through to `HEURISTIC_INITIALIZATION`.

### 25.2 Real coverage evaluation (Pilot 2 Run 6 network, sce00061)

Run against the same real, saved Agent 1 handoff as §24.8:

| | Before (§24.8) | After (this increment) |
|---|---|---|
| Total parameters | 41 | 43 |
| `LITERATURE_DERIVED` | 1 | 1 |
| `HEURISTIC_INITIALIZATION` | 40 | 42 |
| Reactions executable | 37 | **38** |
| Reactions non-executable (`expression=None`) | 1 | 0 |

The two new parameters are exactly the `kf`/`kr` fallback pair for the
one real, previously-permanently-blocked reaction (the ACC1/malonyl-CoA:
[acp] S-malonyltransferase reaction, uncurated/assumed reversible) --
every one of the real network's 38 reactions is now `EXECUTABLE`.

### 25.3 Versioning

`PARAMETER_DECLARATION_POLICY_VERSION` bumped
`"parameter-declaration-v2"` -> `"parameter-declaration-v3"` (a real
behavioral rule-set change: a genuinely multi-substrate `MICHAELIS_MENTEN`
assignment now declares extra parameters it previously never did).
`AGENT2_CONTRACT_VERSION` unchanged -- no `app.agent2.types` dataclass
shape changed. Full reasoning in `app/agent2/version.py`.

### 25.4 Explicit non-goals (this increment specifically)

Never applies to `CUSTOM` (§7's own CUSTOM bullet, unmodified -- an
opaque, unparsed law has no molecularity/dimension this package can
safely infer a fallback from); never invents an equilibrium constant;
never reinterprets kcat/Km as mass-action parameters; never removes or
overwrites a real curated/AI-predicted parameter already declared for
the same law; never runs Agent 4 calibration or a full pilot.
