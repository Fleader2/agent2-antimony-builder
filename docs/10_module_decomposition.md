# Agent 2 Module Decomposition Contract

## 1. Purpose

Increment 7 transforms `FullNetwork` + `BoundaryAssessmentSet` (Increment
6) into a `ModuleDecompositionSet`: one or more `ModuleDecomposition`\
records, each partitioning the network's reactions into `ModuleSpecification`
modules. **This increment does not decide whether a decomposition is
biologically correct.** It produces deterministic decompositions that
are fully traceable back to the boundary evidence that justified them --
nothing more.

> **Modules are views of the `FullNetwork`, not independent reconstructed
> models.**

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
    -> Module Decomposition (this increment)
    -> ModuleDecompositionSet
    -> ModelSpecification (future Increment 8)
    -> Antimony Generation
    -> Agent 3 validation
    -> Agent 4 parameter estimation + simulation
        -> calibrated feedback
            -> Parameter Declaration / Initialization
            -> Boundary Reassessment / Module Revision as needed
```

Agent 1 is untouched by this increment; nothing in
`agent1-biochemical-curator` was read or modified.

## 3. Public API

```python
decompose_network(
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet,
) -> ModuleDecompositionSet
```

Pure function: no database, no filesystem, no connectors, no LLM, no
simulation, no Antimony, no graph-clustering/spectral/ML algorithm
anywhere in its call graph. Never mutates any of its four inputs.

**Deviation from Increment 7's own literal 2-argument signature
(`decompose_network(network, boundaries)`), disclosed explicitly.**
Section 1's own mandatory "initial review" step (read
`app/agent2/kinetics/*`, `app/agent2/parameters/*` before writing code)
surfaces the reason a bare two-argument signature cannot work:
`KineticLawAssignmentSet`/`ParameterDeclarationSet` are separate pipeline
artifacts, never written back onto `FullNetwork.reactions[].kinetic_law_id`
(that field is reserved for a different, not-yet-produced
`KineticLawSpecification` id namespace -- see §5). Populating
`ModuleSpecification.kinetic_law_assignment_ids`/`.parameter_ids`, and
validating their references, is impossible without both. Two additional
parameters were therefore added, in the same accumulating-inputs style
every prior increment's own entry point already uses (`assess_boundaries`
itself takes four inputs, not two). This is a conservative extension to
make the specified behavior achievable, not a redesign -- the core
algorithm (§8-10) is exactly what was specified.

## 4. Output package: `ModuleDecompositionSet`

```
network_id: str
boundary_policy_version: str
decomposition_policy_version: str
decompositions: tuple[ModuleDecomposition, ...]
module_specifications: tuple[ModuleSpecification, ...] = ()
assumptions: tuple[str, ...] = ()
provenance_refs: tuple[str, ...] = ()
```

Lives in `app.agent2.modules.types` (mirroring `BoundaryAssessmentSet` in
`app.agent2.boundaries.types`, `KineticLawAssignmentSet` in
`app.agent2.kinetics.types`, `ParameterDeclarationSet` in
`app.agent2.parameters.types` -- each increment's own top-level
collection lives beside its algorithm, not in `app.agent2.types`).

**Design note (`module_specifications`, a deliberate, disclosed addition
beyond Increment 7's own minimal field list for this type):**
`ModuleDecomposition.module_ids` is id-only by design (already
established before this increment: "references modules/boundaries by
id -- never duplicates them"), so the actual `ModuleSpecification`
objects must live somewhere. `module_specifications` is added here as a
sibling field, mirroring the identical, already-established
`ModelSpecification.module_decomposition` + `.module_specifications`
sibling relationship (§18 of `docs/04_core_domain_contracts.md`).

Each `ModuleDecomposition` (`app.agent2.types`, reused and extended, not
reinvented) contains:

```
decomposition_id: str
name: str
policy_version: str
created_from_network_id: str
module_ids: tuple[str, ...] = ()
boundary_assessment_ids: tuple[str, ...] = ()      # selected cuts (HIGH/VERY_HIGH)
candidate_boundary_ids: tuple[str, ...] = ()        # preserved, not cut (MEDIUM) -- new
interfaces: tuple[InterModuleBoundaryInterface, ...] = ()  # new
assumptions: tuple[str, ...] = ()
parameter_basis_summary: BoundaryParameterBasis | None = None
explanation: str | None = None                      # new
```

`boundary_assessment_ids` and `candidate_boundary_ids` are validated
disjoint (`ModuleDecomposition.__post_init__`) -- a boundary is either a
selected cut or a preserved candidate, never both.

## 5. `ModuleSpecification`

Reused and extended (`app.agent2.types`), never redesigned. Pre-existing
fields (`module_id`, `name`, `reaction_ids`, `species_ids`,
`parameter_ids`, `kinetic_law_ids`, `boundary_interfaces`, `assumptions`,
`source_boundary_ids`, `provenance_refs`) are untouched. Five fields were
added:

```
kinetic_law_assignment_ids: tuple[str, ...] = ()
compartment_ids: tuple[str, ...] = ()
enzyme_state_ids: tuple[str, ...] = ()
interface_species_ids: tuple[str, ...] = ()
boundary_interface_ids: tuple[str, ...] = ()
```

Every id-bearing tuple, old and new, is internally unique
(`ModuleSpecification.__post_init__`).

**Why `kinetic_law_assignment_ids`, not the pre-existing
`kinetic_law_ids`.** `kinetic_law_ids` was seeded in Increment 1 to
reference `KineticLawSpecification.kinetic_law_id` -- a type no real
algorithm in this repository has ever produced. The kinetic-law decisions
Increment 7 actually consumes are
`app.agent2.kinetics.types.KineticLawAssignment.assignment_id` values --
a distinct id namespace. Conflating the two would silently claim a
`ModuleSpecification` references `KineticLawSpecification` records that
do not exist. Increment 7 therefore never populates `kinetic_law_ids`
(left `()`), and introduces the separate, correctly-named field instead.
Reconciling the two namespaces, if ever needed, is a future increment's
decision, not this one's.

**Why `boundary_interface_ids` is not the pre-existing
`boundary_interfaces`.** `boundary_interfaces` (`ModuleBoundaryInterface`,
Increment 1) is a *per-species* record for a future standalone-Antimony
model's boundary condition (`role`, `direction`, `initial_value`, ...) --
it describes one module's own external-input/output declaration.
`boundary_interface_ids` instead references the *pairwise*
`InterModuleBoundaryInterface` records this increment introduces (§11) --
a different concept entirely (which two modules meet, at which boundary,
at what likelihood). Both fields can eventually be populated for the
same module without conflict; they answer different questions.

## 6. Fundamental architectural rule

**The `FullNetwork` always remains authoritative.** Modules are views
onto it, never copies. Nothing inside a module is modified, simplified,
or duplicated. Every `ModuleSpecification` field is a tuple of ids
referencing objects that already exist in `FullNetwork` (or in
`KineticLawAssignmentSet`/`ParameterDeclarationSet`, which Increment 7
also only reads). `decompose_network` never constructs a new
`CompartmentSpecification`/`SpeciesSpecification`/`ReactionSpecification`
-- see the exhaustive non-goal list in §14.

## 7. Boundary interpretation

Increment 6's five `BoundaryLikelihood` values (`VERY_LOW`/`LOW`/
`MEDIUM`/`HIGH`/`VERY_HIGH`) are qualitative evidence levels, never
probabilities (`docs/09_heuristic_boundary_assessment.md` §1). Increment
7 converts those qualitative statements into module cuts through one
fixed, fully-enumerated, categorical policy (§8) -- never a numeric
threshold, weighted sum, or score.

## 8. Default decomposition policy (v1)

```
VERY_HIGH -> cut
HIGH      -> cut
MEDIUM    -> does not cut; recorded as a candidate boundary (§9)
LOW       -> never cuts
VERY_LOW  -> never cuts
```

"Cut" means: the boundary's two reactions are *not* connected by this
edge when computing connected components (§10) -- they may still end up
in the same module via another path (a genuine possibility in a network
with cycles; see §11a, "Local boundary decisions versus global
connectivity"). "Never cuts" means the edge is simply an ordinary
internal connection, keeping its two reactions merged, with no separate
bookkeeping needed -- the qualitative evidence at `LOW`/`VERY_LOW` says
nothing distinguishes this interface from an ordinary internal
reaction-to-reaction link, and (§11a) a retained edge can *never* itself
become an `InterModuleBoundaryInterface`, regardless of what else
happens elsewhere in the graph.

## 9. Preserve ambiguity: `candidate_boundary_ids`

One of Agent 2's central goals is preserving uncertainty rather than
forcing a decision an evidence level does not support. `MEDIUM`
boundaries are therefore never discarded and never silently treated as
either "definitely a boundary" or "definitely not." Every `MEDIUM`
boundary's id is recorded in `ModuleDecomposition.candidate_boundary_ids`
-- available for a future decomposition (a "conservative" or
"aggressive" variant, §13) to actually cut, without Increment 7 ever
guessing which choice is correct. A module containing a preserved
candidate boundary discloses this in its own `assumptions` (a
human-readable note naming the candidate boundary ids it contains) --
never left implicit in code comments only (`.cursor/rules/03_scientific_safety.mdc`).

## 10. Connected-component decomposition

After removing every edge corresponding to a `HIGH`/`VERY_HIGH`
boundary, ordinary connected components are computed over the remaining
graph (nodes = every `FullNetwork.reactions[].reaction_id`; edges = every
other `BoundaryAssessment`, regardless of likelihood -- `LOW`/`VERY_LOW`/
`MEDIUM` all keep their two reactions merged). Implemented as plain
union-find (`app.agent2.modules.decomposer._UnionFind`) -- no graph
library, no clustering, no spectral method, no optimization, no machine
learning (Increment 7 instructions, Step 10, honored literally: `numpy`/
`scipy`/`networkx` are on this package's own forbidden-import list,
enforced by `tests/agent2/test_modules_scope.py`).

A reaction that never appears in any `BoundaryAssessment` at all (no
shared species with anything) is still included as its own graph node --
it becomes a singleton module, never silently dropped.

Component-to-`module_NNN` assignment is deterministic: each component's
member reaction ids are sorted, the lexicographically smallest becomes
that component's anchor, components are sorted by their anchor, and
`module_001`, `module_002`, ... are assigned in that order (§14).

## 11. Interface definition

Whenever a **selected** (`HIGH`/`VERY_HIGH`) boundary's two reactions end
up in *different* final modules after decomposition, one
`InterModuleBoundaryInterface` is created (`app.agent2.types`, new in
Increment 7):

```
interface_id: str
upstream_module_id: str
downstream_module_id: str
boundary_id: str
boundary_likelihood: BoundaryLikelihood
shared_species_ids: tuple[str, ...] = ()
assumptions: tuple[str, ...] = ()
```

**Limited to selected (`HIGH`/`VERY_HIGH`) boundaries only -- corrected
in a post-implementation revision.** An earlier draft of this section
(and of the implementation itself) claimed a retained `LOW`/`MEDIUM`
edge could also become an interface, "if it happens to bridge two
components separated by an unrelated cut elsewhere." **That claim was
wrong and has been removed.** It is not merely rare -- it is
mathematically impossible under this algorithm: a retained edge's own
two reaction ids are the exact arguments passed to union-find's `union`
call (§10), so those two reactions are unconditionally placed in the
same set. Union-find never un-merges two ids it has already merged, so
no matter what else is cut elsewhere in the graph, a retained edge's own
two endpoints are *always* in the same final connected component. Only a
boundary the policy actually excluded from union (`HIGH`/`VERY_HIGH`)
can ever have its two reactions land in different final modules --
`decompose_network`'s own interface-building loop now iterates only
those, both because the alternative was dead code (the "different
module" condition could never be true for anything else) and because
this makes the invariant a property of the code's structure rather than
an emergent fact one could get wrong by touching the code elsewhere. See
§11a for a worked example, and
`tests/agent2/test_modules.py::test_retained_edge_cannot_bridge_final_modules`
for the proof.

Even restricted to selected boundaries, an interface is still not
guaranteed: §11a explains why a selected boundary can fail to separate
anything at all. No boundary condition is ever invented here:
`boundary_likelihood` and `shared_species_ids` are copied verbatim from
the source `BoundaryAssessment`.

`interface_id` is deterministic: `f"interface::{boundary_id}"` (at most
one interface per selected assessment, 1:1, so reusing the boundary id
as a stable suffix is both deterministic and immediately traceable).

## 11a. Local boundary decisions versus global connectivity

Three concepts must never be conflated:

* **A. `BoundaryAssessment`** (Increment 6) -- local, qualitative
  evidence: "this interface has evidence suggesting whether it is a
  plausible module boundary."
* **B. Selected boundary / cut decision**
  (`ModuleDecomposition.boundary_assessment_ids`) -- Increment 7's local
  policy decision: "this `HIGH`/`VERY_HIGH` boundary is excluded from the
  connectivity graph."
* **C. `InterModuleBoundaryInterface`** -- the *global* outcome: "after
  every selected exclusion and every retained alternate path is
  considered, this boundary's two reactions actually ended up in
  different final modules."

A selected boundary is a *local* decision; it does not by itself
guarantee *global* separation. Consider:

```
R1 -- HIGH -- R2
 \            /
   \--LOW ---/
```

1. `boundary::R1::R2` (`HIGH`) is selected: excluded from union-find.
2. The alternate `LOW` path (via some other reaction, or a direct
   second retained connection) is still unioned normally.
3. R1 and R2 therefore remain connected through that alternate path and
   land in the **same** final connected component -- one module, not
   two.
4. The selected boundary remains in `boundary_assessment_ids` --
   **never** silently discarded merely because it did not end up
   separating anything (§5/§9 of the original Increment 7 instructions:
   preserve evidence rather than force a decision the graph does not
   support).
5. No `InterModuleBoundaryInterface` is produced for `boundary::R1::R2`,
   because no final module separation actually occurred.

> **Local boundary evidence does not guarantee a global partition in
> networks with alternate paths.** A `HIGH`/`VERY_HIGH` boundary means
> "the policy chose to cut here," not "this network is now split here."
> Only the connected-component computation over the *entire* retained
> graph decides the actual modules.

This is scientifically useful, not a defect: a selected boundary that
failed to separate anything is a machine-readable record of "locally
this looked like a strong boundary, but globally the network remained
connected" -- exactly the kind of crosstalk or alternate-coupling signal
a later Agent 4/Agent 5 analysis might want to investigate.
`decompose_network`'s own `explanation` string reports how many selected
boundaries did not end up producing an interface, for this reason (§14).

This package deliberately does **not** try to "fix" this by finding a
minimum cut, deleting additional retained edges, optimizing module
count, clustering, spectral partitioning, or maximizing some likelihood
score (Increment 7 instructions, Step 11 in this revision's own prompt:
"do not turn decomposition into optimization"). The v1 policy remains
exactly: remove every selected `HIGH`/`VERY_HIGH` edge, then compute
ordinary connected components on what remains. A more sophisticated
global partition strategy, if ever needed, is a future policy revision
(§13), never an implicit change smuggled into v1.

See `tests/agent2/test_modules.py`'s
`test_selected_boundary_fails_to_separate_because_of_alternate_retained_path`
for a concrete, executable version of the example above (a 3-reaction
cycle: `R1 --VERY_HIGH--> R2 --LOW--> R3 --LOW--> R1`).

## 12. Interface species

`InterModuleBoundaryInterface.shared_species_ids` are references to
`FullNetwork.species` only -- the exact same ids already present on the
source `BoundaryAssessment.shared_species_ids`. Never duplicated, never
turned into a source/sink reaction, never a fabricated "ghost" species.
A module's own `interface_species_ids` is simply the (deduplicated,
sorted) union of every interface it participates in's
`shared_species_ids` -- again, references only.

## 13. Multiple decompositions

`ModuleDecompositionSet.decompositions` is structurally a tuple, ready
to hold more than one `ModuleDecomposition` (e.g. a future conservative
or aggressive variant built from the same `candidate_boundary_ids`, or a
context-specific one). **v1 always produces exactly one.** No such
alternative-decomposition logic exists yet -- implementing it is
explicitly out of scope for Increment 7.

## 14. Module naming

`module_id` values are generated as `f"module_{index:03d}"` (`module_001`,
`module_002`, ...) over the deterministic anchor-sorted component order
described in §10. Never random, never a UUID; stable under repeated
execution with the same inputs (verified by
`tests/agent2/test_modules.py::test_repeated_execution_is_fully_deterministic`).
`decomposition_id` is likewise deterministic:
`f"decomposition::{network.network_id}"`.

## 15. Parameter ownership

Every `ParameterSpecification.reaction_id` in the supplied
`ParameterDeclarationSet` is looked up against which module contains
that reaction; the parameter's `parameter_id` is added to exactly that
module's `parameter_ids`. A parameter with no `reaction_id` (should not
occur under the current parameter-declaration policy, which always sets
it) is not decided by this increment. No parameter is ever duplicated
across modules, and no `ParameterSpecification` object itself is copied,
modified, or reconstructed -- `ParameterSpecification.module_ids` (a
pre-existing field, seeded in Increment 1) is deliberately **not**
written to by this increment: doing so would require reconstructing an
immutable, already-produced `ParameterSpecification` (a mutation of data
that is supposed to remain untouched, §6), whereas
`ModuleSpecification.parameter_ids` already expresses the identical
"this parameter belongs to this module" fact as a pure reference, with
no reconstruction needed. This is a deliberate design decision, not an
oversight -- see `docs/04_core_domain_contracts.md`'s own description of
`ParameterSpecification.module_ids` for the field's original intent,
which a future increment may revisit.

## 16. Enzyme-state ownership

`FullNetwork.enzyme_associations[].enzyme_state_id` (when set) is
grouped by `.reaction_id`; every reaction's associated enzyme-state ids
are added to its module's `enzyme_state_ids`. Since one enzyme
association names exactly one reaction, and one reaction belongs to
exactly one module (§10's partition is total and non-overlapping by
construction), no enzyme state can ever be split across two modules.

## 17. Compartments

`ModuleSpecification.compartment_ids` is the (deduplicated, sorted) set
of `SpeciesSpecification.compartment_id` values for every species touched
by the module's own reactions -- never a separately curated or
duplicated `CompartmentSpecification`. A module spanning a transport
reaction (e.g. `docs/10_module_decomposition.md`'s own §10 transport
example) legitimately lists more than one compartment id; this is
expected, not an error, and reflects exactly what that module's
reactions actually touch.

## 18. Provenance

Every `ModuleSpecification` preserves, as plain id references, every
`KineticLawAssignment.assignment_id` for its reactions
(`kinetic_law_assignment_ids`), every `ParameterSpecification.parameter_id`
for its reactions (`parameter_ids`), and its own `reaction_ids`. Nothing
becomes anonymous: every id a module carries resolves against a real
object in `FullNetwork`/`KineticLawAssignmentSet`/
`ParameterDeclarationSet`/`BoundaryAssessmentSet`, defensively re-checked
by `decompose_network`'s own post-construction validation (§20) even
though construction-time validation already enforces internal
consistency.

**`ModuleSpecification.source_boundary_ids` -- exact, single, precise
definition (do not broaden or narrow it ambiguously).** It lists every
`BoundaryAssessment.boundary_id` whose `upstream_element_id` or
`downstream_element_id` names one of this module's own `reaction_ids` --
**regardless of that boundary's likelihood or cut/candidate/retained
status.** This is one consistent rule, applied uniformly, not a mix of
several different per-case definitions. Concretely, it always includes:

* every retained (`LOW`/`VERY_LOW`/`MEDIUM`) boundary that helped keep
  this module's reactions merged (§8/§10);
* every `MEDIUM` candidate boundary lying inside this module (also
  separately disclosed in the module's own `assumptions`, §9);
* the boundary behind any of this module's own `interfaces` -- that
  `boundary_id` always appears here too;
* any *selected* (`HIGH`/`VERY_HIGH`) boundary touching this module,
  **even when it did not end up separating anything** (§11a) -- a
  selected-but-non-separating boundary is not specially excluded, since
  it is still real Increment-6 evidence naming one of this module's own
  reactions.

This is deliberately the broad "every assessment naming a reaction in
this module" reading, not the narrower "only boundaries that materially
changed this module's final shape" reading (which would require tracking
which specific retained edges were the actual spanning-tree connections
union-find used, versus merely-redundant ones in a cycle -- a real
distinction, but one this package does not attempt to draw, since
`ModuleDecomposition.boundary_assessment_ids`/`.candidate_boundary_ids`/
`.interfaces` already separately and precisely disclose the cut/
candidate/interface status of every boundary; `source_boundary_ids`
answers only "which boundaries name a reaction in this module," a
strictly simpler and unambiguous question). Consult
`boundary_assessment_ids`/`candidate_boundary_ids`/`interfaces` (§4, §11)
-- never `source_boundary_ids` alone -- to determine whether a specific
boundary was a cut, a candidate, or an actual interface.

## 19. Dynamic neutrality

This increment uses only Increment 6's own qualitative
`BoundaryLikelihood` outputs and Increment 4/5's structural kinetic-law/
parameter ids. It never computes or references relaxation time,
retroactivity, impedance, buffering, sensitivity, a simulation result, or
a calibration result -- those remain Agent 4's job
(`tests/agent2/test_modules_scope.py` enforces no `scipy`/simulation
call-site exists anywhere in `app.agent2.modules`).

## 20. Validation

`decompose_network` rejects (raising
`app.agent2.modules.errors.ModuleDecompositionReferenceError`, or a type
error from the underlying `app.agent2.types` construction for a
structurally malformed input):

* an input whose `network_id` disagrees with `network.network_id`
  (`kinetic_laws`/`parameters`/`boundaries`, mirroring
  `assess_boundaries`'s identical four-input cross-check);
* a duplicate `module_id`/`decomposition_id`/`interface_id` (enforced by
  `ModuleDecompositionSet`/`ModuleDecomposition` construction itself);
* a dangling reaction/species/compartment/enzyme-state/kinetic-law-
  assignment/parameter/boundary reference on any produced module or
  decomposition, via `decompose_network`'s own defensive
  `_validate_references` backstop -- mirrors the identical
  post-construction pattern already established in
  `app.agent2.boundaries`/`app.agent2.kinetics`/`app.agent2.parameters`.
  Should never trigger given a correct implementation;
* **(this revision)** an `InterModuleBoundaryInterface` whose underlying
  `BoundaryAssessment` was never selected as a cut (`HIGH`/`VERY_HIGH`)
  -- re-checks the §11 invariant defensively, even though it is already
  guaranteed by construction (the interface-building loop only ever
  considers cut-eligible assessments);
* **(this revision)** an `InterModuleBoundaryInterface` whose
  `upstream_module_id`/`downstream_module_id` does not actually contain
  the underlying assessment's `upstream_element_id`/`downstream_element_id`
  reaction -- confirms an interface's endpoints genuinely belong to the
  modules it claims to connect, not merely that those module ids exist.

Both new checks are exercised directly (not only through the successful
path) by
`tests/agent2/test_modules.py::test_validate_references_rejects_interface_for_a_retained_boundary`.

Structurally allowed, never rejected: `boundary_assessment_ids` may
legally contain ids absent from every `interfaces[].boundary_id` (§11a);
`candidate_boundary_ids` and `boundary_assessment_ids` are validated
disjoint at the type level (`ModuleDecomposition.__post_init__`, §4).

`app.agent2.types` also grew matching checks in
`_validate_model_specification_references` for every new
`ModuleSpecification`/`ModuleDecomposition` field (with one disclosed
exception -- `kinetic_law_assignment_ids` has no `ModelSpecification`
registry to validate against yet, since `ModelSpecification` does not
carry `KineticLawAssignment` objects; see that function's own docstring
note and `app.agent2.version`'s Increment 7 entry).

## 21. Versioning

`MODULE_DECOMPOSITION_POLICY_VERSION` is introduced at
`"module-decomposition-v1"` for the first real module-decomposition rule
set (§8's cut/candidate/never-cut policy, §10's connected-component
partitioning). `AGENT2_CONTRACT_VERSION` was bumped `"0.5"` -> `"0.6"`:
`ModuleSpecification` gained five fields, `ModuleDecomposition` gained
three, and a new type (`InterModuleBoundaryInterface`) was introduced --
every new field has a default, so existing keyword-based construction is
unaffected, but this is a real output-contract shape change per
`app.agent2.version`'s own bump criterion. `AGENT1_HANDOFF_VERSION` is
unchanged -- Agent 1 was not modified (input-only, as always).

**Post-implementation consistency revision (still pre-release, no
version bump).** The correction described in §11/§11a -- restricting
`InterModuleBoundaryInterface` creation to selected (`HIGH`/`VERY_HIGH`)
assessments, since a retained boundary can mathematically never satisfy
the "different final module" condition -- produces **byte-identical**
output to the prior code for every input: the removed code path never
executed (it iterated a condition that could never be true for a
retained assessment). No previously-valid `ModuleDecompositionSet` is
now rejected, and no previously-accepted decomposition's shape,
`module_ids`, `interfaces`, `boundary_assessment_ids`, or
`candidate_boundary_ids` changes for any input. This is a
correctness-by-construction refactor plus documentation/comment/test
corrections and two additional (structurally redundant but disclosed,
§20) defensive validation checks -- not a change to the decomposition
policy's actual, externally-observable behavior. `MODULE_DECOMPOSITION_POLICY_VERSION`
therefore remains `"module-decomposition-v1"`, per this file's own bump
criterion ("bump a constant only when the shape or policy it names
actually changes") and per this revision's own explicit instruction to
prefer retaining the version when correcting the first implementation
before release. `AGENT2_CONTRACT_VERSION`/`AGENT1_HANDOFF_VERSION` are
likewise unchanged -- no `app.agent2.types` shape changed, and Agent 1
was not touched.

## 22. Explicit non-goals

No module decomposition biological-correctness judgment (this increment
only produces a decomposition, never certifies it). No `ModelSpecification`
construction (a future Increment 8 concern -- `ModuleDecompositionSet`
is a new, separate top-level collection, never a `ModelSpecification`
itself). No Antimony generation, full or module-level. No Agent 3
mass-balance/connectivity/unit-consistency validation. No Agent 4
simulation, calibration, sensitivity analysis, or parameter fitting. No
Agent 5 biological-plausibility critique. No numeric boundary scoring,
no probability, no machine learning, no graph clustering, no spectral
method, no optimization. No alternative (conservative/aggressive/
context-specific) decomposition variant (§13) -- structurally supported,
not implemented.

## 23. Testing

`tests/agent2/test_modules.py` (37 tests) covers: an empty network
(zero modules, never an error); a single isolated reaction; every
`BoundaryLikelihood` value's decomposition-policy interpretation
(`LOW`/`VERY_LOW` never cut, `MEDIUM` preserved as a candidate and
disclosed in the module's own `assumptions`, `HIGH`/`VERY_HIGH` cut);
two-module, many-module, and disconnected-subnetwork partitioning;
deterministic `module_NNN` naming and full repeated-execution
determinism; parameter ownership, kinetic-law-assignment ownership,
enzyme-state ownership (never split across modules), and compartment
ownership (correctly spanning both sides of a transport reaction); full
provenance preservation; and construction-time rejection of duplicate
ids, dangling references, and overlapping selected/candidate boundary
ids.

**The local-cut-vs-global-connectivity invariant (§11a) is specifically
covered by four tests**, matching the four cases this revision was
written to prove: a retained `LOW`/`VERY_LOW`/`MEDIUM` edge can never
bridge two final modules and never becomes an interface
(`test_retained_edge_cannot_bridge_final_modules`); a simple selected
boundary with no alternate path does separate into two modules with
exactly one interface (`test_simple_selected_boundary_separates_into_two_modules`);
a selected boundary in a 3-reaction cycle, blocked from separating
anything by an alternate retained path, remains fully recorded in
`boundary_assessment_ids` while producing zero interfaces
(`test_selected_boundary_fails_to_separate_because_of_alternate_retained_path`);
and a `MEDIUM` boundary never becomes a cut or an interface
(`test_medium_candidate_boundary_never_becomes_an_interface`). A fifth
test directly exercises `_validate_references`' two new defensive checks
against a hand-crafted, deliberately-inconsistent input
(`test_validate_references_rejects_interface_for_a_retained_boundary`).

`tests/agent2/test_modules_scope.py` (9 tests) confirms, structurally
(via `ast`, not substring search), that `app.agent2.modules` never
imports a modeling/simulation/graph-clustering library, Agent 1's
runtime, an LLM client, or performs any database/filesystem/network
access, and never invokes simulation, fitting, or later-agent behavior
-- backed by a real, executed decomposition whose resulting types carry
no `antimony_text`/`probability`/`score` field.

## 24. Known limitations

* `kinetic_law_assignment_ids` cannot be cross-validated against
  `ModelSpecification` (§20) -- a disclosed, pre-existing gap between the
  `KineticLawSpecification`/`KineticLawAssignment` id namespaces, not
  something Increment 7 introduces or can resolve on its own.
* `ParameterSpecification.module_ids` is left unpopulated by this
  increment (§15) -- module ownership is expressed only through
  `ModuleSpecification.parameter_ids`, never by mutating/reconstructing
  the parameter itself.
* A module's `assumptions` disclose contained candidate boundaries by a
  human-readable sentence, not a structured `ModelAssumption` record --
  sufficient for this increment's local, per-module disclosure, matching
  every other structural type's own lightweight `assumptions` tuple.
* No alternative decomposition variant exists (§13); `ModuleDecompositionSet`
  supports more than one decomposition structurally, but v1 never
  produces more than one.
* Interface `assumptions` are currently always empty -- no case requiring
  a disclosed assumption on an `InterModuleBoundaryInterface` was found
  in this increment's algorithm (it never invents a boundary condition,
  so there is nothing to disclose beyond the interface's own already-
  explicit fields).
* `source_boundary_ids` (§18) is intentionally the broad "every boundary
  naming a reaction in this module" reading, not a narrower "boundaries
  that actually determined this module's final shape" reading -- the
  latter would require tracking which specific retained edges were the
  real union-find spanning-tree connections versus merely-redundant ones
  in a cycle, a distinction this package does not attempt to draw
  because `boundary_assessment_ids`/`candidate_boundary_ids`/`interfaces`
  already separately disclose that precisely.
* An earlier draft of §11 and of `decompose_network` itself incorrectly
  claimed a retained `LOW`/`MEDIUM` edge could become an
  `InterModuleBoundaryInterface` "if it happens to bridge two components
  separated by an unrelated cut." That claim was mathematically
  impossible under union-find and has been corrected (§11/§11a); the
  actual produced output was never affected, since the corresponding
  code path never executed for any input.

None of these block correctness: each is either a disclosed pre-existing
gap or an explicitly out-of-scope future extension, never a silent
wrong answer.

## 25. Readiness for Increment 8 (Antimony generation)

`ModuleDecompositionSet.decompositions[0]` (the only decomposition v1
ever produces) and `.module_specifications` carry everything Increment
8 needs to populate `ModelSpecification.module_decomposition`/
`.module_specifications`: real, validated, fully cross-referenced module
membership, inter-module interfaces with their own qualitative
likelihoods, and preserved candidate-boundary ambiguity. Increment 8
still needs to resolve the `KineticLawSpecification`/`KineticLawAssignment`
id-namespace gap named in §5/§20 when it actually constructs
`ModelSpecification.kinetic_laws` -- not attempted here, since doing so
would require design decisions (how a `KineticLawAssignment` becomes a
`KineticLawSpecification`) squarely outside Increment 7's own scope.

## 26. Final architectural rule

> The `FullNetwork` always remains authoritative. Modules are views onto
> it, never independent reconstructed models.

> A boundary's qualitative likelihood is evidence for a module cut, never
> a probability and never a guarantee.

> `MEDIUM` evidence is preserved, not discarded and not forced into a
> decision the evidence does not support.

> A selected cut is a local decision; the connected components of the
> full retained graph are the sole authority on the resulting global
> modules. A selected boundary that does not separate anything remains
> fully visible in the audit trail, never silently discarded.

> Increment 7 decomposes; it does not judge whether the decomposition is
> biologically correct, does not simulate, does not fit parameters, and
> does not generate Antimony.
