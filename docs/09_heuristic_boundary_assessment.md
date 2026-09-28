# Agent 2 Heuristic Boundary Assessment Contract

## 1. Purpose

Increment 6 evaluates where module boundaries may plausibly exist in the
complete, fully-parameterized network. **Boundary assessment estimates
how plausible a modeling boundary is at a particular network interface.
It does not itself divide the network.** Boundary decisions are
heuristic and qualitative, not mathematical proofs and not
probabilities.

**Scientific definition of a module (pre-commit revision).** A module is
**not** merely a densely connected region of a graph. A module is *a
functional unit whose intrinsic behavior is largely independent of its
surrounding network*. The likelihood of a boundary should therefore
reflect **functional isolation**, not simply **structural
discontinuity**. Every heuristic in this package, and the combination
policy that reads their outcomes, is organized around that distinction
-- see §10-11 for the full rationale, and §13-27 for how it was applied
rule by rule.

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
    -> Heuristic Boundary Assessment (this increment)
    -> BoundaryAssessmentSet
    -> Module Decomposition (future Increment 7)
    -> ModelSpecification
    -> Antimony Generation
    -> Agent 3 validation
    -> Agent 4 parameter estimation + simulation
        -> calibrated feedback
            -> Parameter Declaration / Initialization
            -> Boundary Reassessment as needed
```

Agent 1 is input-only for this increment; nothing in
`agent1-biochemical-curator` was modified to implement it or this
revision.

## 3. Input contracts

`assess_boundaries(network: FullNetwork, characterization: NetworkCharacterization, kinetic_laws: KineticLawAssignmentSet, parameters: ParameterDeclarationSet) -> BoundaryAssessmentSet`
-- unchanged by this revision. `FullNetwork` additionally supplies
`regulatory_interactions` (used by the new feedback rules, §24-25) and
each reaction's own `reversible` flag (used by `irreversible_output_isolation`,
§26) -- both already present on the pre-existing contract, no extension
needed.

## 4. Output contract

`BoundaryAssessmentSet` -- unchanged (`network_id`,
`characterization_policy_version`, `kinetic_law_policy_version`,
`parameter_policy_version`, `boundary_policy_version`, `assessments`,
`assumptions`, `provenance_refs`).

## 5. Boundary candidate identity

Unchanged. One candidate, and one resulting `BoundaryAssessment`, per
ordered `(upstream_reaction_id, downstream_reaction_id)` pair actually
connected by at least one shared species. `boundary_id =
f"boundary::{upstream}::{downstream}"`, deterministic, never a UUID.

## 6. `BoundaryLikelihood`

Reused unchanged: `VERY_LOW`/`LOW`/`MEDIUM`/`HIGH`/`VERY_HIGH`. Never a
numeric score, percentage, or confidence interval anywhere in this
package's types or logic.

## 7. Heuristic rule model

Unchanged design. Each rule in `rules.py` is a pure function
`CandidateFacts -> RuleOutcome`; `rules.ALL_RULES` is a fixed, documented,
order-irrelevant tuple, now nineteen functions (previously twelve -- see
§10 for the reorganization). `CandidateFacts` (the internal
assessor/rules collaboration bundle) dropped six fields this revision
(`upstream_parameter_sources`/`downstream_parameter_sources`/
`upstream_all_placeholder`/`downstream_all_placeholder`/
`upstream_any_curated`/`downstream_any_curated`) that no rule reads
anymore once the parameterization-convenience rules were retired (§20),
and gained six new ones (`upstream_reversible`/`downstream_reversible`,
`upstream_catalytic_ids`/`downstream_catalytic_ids`,
`confined_inhibitory_feedback`, `crossing_regulatory_interaction`) for
the new functional-modularity rules (§23-26).

## 8. Supporting versus opposing evidence

Unchanged. Every `BoundaryAssessment` carries both
`supporting_reason_codes` and `opposing_reason_codes`.

## 9. Rule strength

Unchanged vocabulary (`WEAK`/`MODERATE`/`STRONG`), but its *distribution*
across the rule catalog changed substantially this revision -- see §10.

## 10. Structural proxies versus functional modularity (the core revision)

The pre-revision catalog conflated two different kinds of evidence:

* **Structural/topological facts** (compartment transitions, transport
  classification, branch points, convergence points, enzyme-state
  transitions, kinetic-law-type differences) *correlate* with functional
  modularity but do not themselves confirm it. Two reactions can sit in
  different compartments, or be classified differently by Increment 3's
  own structural rules, while still being tightly, dynamically coupled.
* **Functional facts** (a confirmed regulatory feedback loop confined to
  one side or crossing the interface, a shared limiting catalytic
  resource, an explicitly curated irreversible step) speak *directly* to
  whether the two sides behave independently.

**Revision applied:** every structural-proxy rule's strength ceiling was
lowered to `MODERATE` (§13-19), so that no amount of accumulated
structural discontinuity can, by itself, produce `BoundaryLikelihood
.VERY_HIGH` anymore (§12). `STRONG` support is now reachable *only*
through `irreversible_output_isolation` (§26); `STRONG` opposition
through `intrinsic_feedback_isolation` (§24) and the pre-existing
`strong_local_continuity` opposition rule (§22, itself a *structural*
continuity argument, but one this revision re-examined and found still
defensible as a primary source of `LOW`/`VERY_LOW` -- see that section
for why it was retained at `STRONG` rather than downgraded). A later,
separate feedback-heuristic revision (§24-25a) additionally recast which
*kind* of feedback evidence counts, and in which direction -- see below.

## 11. Parameterization convenience is not biological evidence

A second, related conflation existed: whether two reactions were
*curated with the same kind of parameter provenance* (both `CURATED`,
one `PLACEHOLDER` and the other not, etc.) was previously treated as
weak evidence for or against a boundary. **This is never evidence of
biological modularity.** Which measurements Agent 1 happened to curate
is a fact about *our current knowledge state*, not about the organism.
Two reactions curated identically might be biologically unrelated; two
reactions with wildly different curation completeness might be one
tightly coupled unit.

**Revision applied:** `parameter_source_discontinuity`,
`placeholder_parameter_region`, and `parameterization_continuity` are
retired to **permanently return `NEUTRAL`** (§20). They remain in
`BoundaryReasonCode` and as callable functions -- deleted from nothing --
so the distinction itself, and the fact that this package once conflated
it, stays visible and testable
(`tests/agent2/test_boundaries.py::test_parameter_source_discontinuity_never_appears_in_any_reason_codes`).
The underlying fact is still disclosed, but only through
`BoundaryAssessment.parameter_basis` (an explicit audit field, §28-29),
never through boundary-likelihood evidence.

## 11a. Heuristic-class taxonomy (structural / functional / dynamic)

For documentation and future extensibility -- **not** as an input to
`policy.combine_outcomes`, which reads only each rule's `RuleDirection`/
`RuleStrength` and never consults which class a reason code belongs to
-- every reason code in the current catalog also belongs to one of three
conceptual classes. This taxonomy is orthogonal to, and answers a
different question than, the "structural proxy vs. functional
modularity" strength-ceiling design in §10: §10 governs *which rules may
reach `STRONG`*; this taxonomy instead asks *what kind of fact does this
rule describe*. The two do not line up member-for-member (see the
`IRREVERSIBLE_OUTPUT_ISOLATION` note below), and that is expected --
they are independent classifications serving independent purposes.

**STRUCTURAL** -- describe physical/network organization:

* `COMPARTMENT_TRANSITION` (§13)
* `TRANSPORT_INTERFACE` (§14)
* `BRANCH_POINT` (§15)
* `CONVERGENCE_POINT` (§16)
* `ENZYME_STATE_TRANSITION` (§17)
* `IRREVERSIBLE_OUTPUT_ISOLATION` (§26) -- classified structural *here*
  because reversibility is itself a structural/kinetic-modeling property
  (a curated boolean flag on the reaction), not a regulatory-organization
  fact, even though §10's strength-ceiling design treats it as a
  functional-modularity rule (it is one of only two rules that may reach
  `STRONG`).
* `HIGH_CONNECTIVITY_CONTINUITY` (§21)
* `STRONG_LOCAL_CONTINUITY` (§22)

**FUNCTIONAL** -- describe biological/modeling behavior or regulatory
organization:

* `SHARED_RESOURCE_COUPLING` (§23)
* `INTRINSIC_FEEDBACK_ISOLATION` (§24)
* `EXTRINSIC_FEEDBACK_CROSSING_DEFERRED` (§25) -- functional in subject
  matter (regulatory organization), but behaves like a DYNAMIC-deferred
  rule today (always `NEUTRAL`) because Agent 2 cannot yet supply the
  evidence it would need to act; see "Future Dynamic Refinement" (§25b).
* `CURATED_REGULATORY_CONTEXT_CHANGE` (§18)
* `KINETIC_LAW_DISCONTINUITY` (§19)
* `PARAMETER_SOURCE_DISCONTINUITY` (§20)
* `PLACEHOLDER_PARAMETER_REGION` (§20)
* `PARAMETERIZATION_CONTINUITY` (§20)

**DYNAMIC** -- require simulation/calibration data this package does not
have; deferred by design:

* Implemented today as permanent-`NEUTRAL` placeholder rules (§27):
  `RELAXATION_TIME_INVARIANCE_DEFERRED`, `CONTEXT_REUSABILITY_DEFERRED`,
  `STABLE_FUNCTIONAL_ROLE_DEFERRED`.
* **Not implemented** -- named here only for future extensibility, with
  no reason code, no rule function, and no computation of any kind
  introduced by this revision: retroactivity, signal attenuation,
  dynamic buffering, sensitivity structure, and parameter correlation
  (dynamic coupling). These remain purely descriptive documentation
  entries until a later agent can supply the underlying dynamic
  evidence; adding real rules for them is out of scope for Increment 6.

**Structural discontinuity is not equivalent to functional modularity.**
Structural rules are proxies: they correlate with modularity but do not
confirm it, which is why §10 caps every one of them at `MODERATE`.
Functional isolation -- confirmed regulatory confinement, resource
coupling, curated irreversibility -- is the scientific target this
package is actually trying to approximate. Dynamic evidence from Agent 4
(loop gain, relaxation time, retroactivity, dynamic buffering) will
eventually provide stronger, direct tests of modularity than any static
structural or functional proxy can; until then, this package is explicit
about evaluating proxies for functional modularity, not modularity
itself (§1, §38).

## 12. Combination policy

`policy.combine_outcomes` -- a fully enumerated, explicit categorical
decision table, never a hidden numeric weighted sum:

1. No supporting evidence at all, and at least one `STRONG` opposing
   signal -> `VERY_LOW`.
2. No supporting evidence at all otherwise -> `LOW` -- the conservative
   default for a "weakly connected interface": never assume a boundary
   merely because nothing else was said about it.
3. **(Revision)** At least one `STRONG` supporting signal, and no
   `MODERATE`-or-stronger opposition -> `VERY_HIGH`. Under the current
   catalog, `STRONG` support is reachable *only* through
   `irreversible_output_isolation` (§26) -- never through accumulated
   structural proxies, and, since the feedback-heuristic revision (§25a),
   no longer through confined feedback either (that evidence now opposes
   a boundary, §24). This is the direct fix for the pre-revision
   behavior, where `VERY_HIGH` could be reached by merely stacking
   several structural discontinuities (e.g. transport + compartment
   transition + branch point) with no genuine isolation evidence.
4. At least one `STRONG` supporting signal (not already resolved to
   `VERY_HIGH` because of `MODERATE`-or-stronger opposition), or
   two-or-more `MODERATE`-or-stronger supporting signals, and no
   `STRONG` opposition -> `HIGH`.
5. Supporting evidence exists but is entirely weak, and there is
   `MODERATE`-or-stronger opposition -> `LOW`.
6. Anything else with at least one supporting signal -> `MEDIUM`.

Genuine conflicting strong evidence (e.g. a curated irreversible step
*and* a regulatory loop confirmed crossing the same interface) is never
forced toward an extreme likelihood -- branch 3 and 4 both require the
*absence* of meaningful opposition, so such a case correctly falls to
`MEDIUM` (branch 6). See
`tests/agent2/test_boundaries.py::test_combination_table_strong_support_plus_strong_oppose_falls_to_medium`.

## 13. Compartment-transition heuristic

* **Reason code:** `COMPARTMENT_TRANSITION`. **Direction:** support.
  **Strength:** `MODERATE` (unchanged).
* **Biological rationale:** physical compartmentalization is a
  classical, genuine isolation mechanism in cell biology -- distinct
  compartments genuinely have distinct volumes, concentrations, and
  often distinct enzyme complements.
* **Implementation:** fires when the two reactions' own full participant
  compartment sets differ -- never when merely comparing the *shared*
  species' compartment (which can never differ across a genuinely shared
  species, since species identity embeds compartment). In practice this
  fires on edges adjacent to a multi-compartment reaction.
* **Limitations:** does not confirm retroactivity insulation by itself
  -- a compartment boundary can still be tightly, reversibly coupled via
  fast exchange. Kept at `MODERATE`, never promoted to a functional-
  isolation-grade signal.
* **Future improvements:** could be strengthened if this package ever
  gains access to curated transport kinetics (e.g. an explicitly slow,
  rate-limiting transporter would be stronger isolation evidence than a
  fast, near-equilibrium one) -- not available today.

## 14. Transport heuristic

* **Reason code:** `TRANSPORT_INTERFACE`. **Direction:** support.
  **Strength:** `MODERATE` (**revised down from `STRONG`**).
* **Biological rationale:** an explicit `ReactionClass.TRANSPORT`
  classification (Increment 3's own conservative, deterministic rule)
  marks a genuine compartment-crossing step.
* **Implementation:** fires when either side is `ReactionClass.TRANSPORT`.
* **Limitations (why downgraded):** transport alone does not confirm
  retroactivity insulation -- a transporter can still be tightly,
  reversibly coupled to both sides via near-equilibrium exchange. Under
  the pre-revision catalog, this was one of the two rules (with
  `compartment_transition`) that could combine to reach `VERY_HIGH`
  without any genuine functional-isolation evidence; that is exactly the
  failure mode this revision corrects.
* **Future improvements:** as §13.

## 15. Branch-point heuristic

* **Reason code:** `BRANCH_POINT`. **Direction:** support. **Strength:**
  `WEAK` (**revised down from `MODERATE`**).
* **Biological rationale:** a branch point is sometimes a natural place
  to consider a module boundary (e.g. a metabolite branching into
  distinct downstream pathways), per classical pathway-mapping
  convention.
* **Implementation:** fires when a shared species is consumed by more
  than one reaction. Pure structural topology; never an inferred
  pathway name.
* **Limitations (why downgraded):** purely topological -- the branches
  could still be tightly co-regulated (e.g. shared allosteric control
  over both fates), so this is weaker evidence of functional
  independence than its original strength implied.
* **Future improvements:** could be corroborated by checking whether the
  branches are independently regulated (today's `curated_regulatory_context_change`,
  §18, is a weak, separate signal for that) -- not combined into this
  rule to keep each rule's condition simple and auditable (Step 9's own
  "do not make each rule directly assign the final likelihood").

## 16. Convergence heuristic

* **Reason code:** `CONVERGENCE_POINT`. **Direction:** support.
  **Strength:** `WEAK` (**revised down from `MODERATE`**), for the
  identical reason as §15: pure topology, not functional evidence.
* **Implementation:** fires when a shared species is produced by more
  than one reaction.
* **Future improvements:** as §15.

## 17. Enzyme-state-transition heuristic

* **Reason code:** `ENZYME_STATE_TRANSITION`. **Direction:** support.
  **Strength:** `MODERATE` (**reconsidered, retained**).
* **Biological rationale:** a regulatory-state change (phosphorylation,
  ligand binding, etc.) is more biologically specific than pure
  topology.
* **Implementation:** fires when either side is directly referenced by a
  curated `EnzymeStateTransition` (Increment 3's
  `ReactionClass.STATE_TRANSITION`).
* **Limitations:** still does not itself confirm the two catalytic forms
  behave independently -- never automatically splits regulatory states
  into separate modules on its own.
* **Future improvements:** none identified; this is already a
  reasonably specific structural signal for the data available.

## 18. Regulatory-context heuristic

* **Reason code:** `CURATED_REGULATORY_CONTEXT_CHANGE` (never
  `REGULATION_PRESENT_VS_ABSENT`). **Direction:** support. **Strength:**
  `WEAK` (**reconsidered, retained**).
* **Biological rationale:** an asymmetry in curated regulation/allostery
  across an interface is a weak hint of a regulatory boundary.
* **Implementation:** fires when exactly one side has curated
  `regulation_ids`/`allosteric_interaction_ids`.
* **Limitations:** absence on one side is never treated as biological
  absence -- only as "no curated fact available" (Agent 1's regulation
  pipeline is known-incomplete). Deliberately weak for this reason.
* **Future improvements:** none identified; already appropriately
  conservative.

## 19. Kinetic-law-discontinuity heuristic

* **Reason code:** `KINETIC_LAW_DISCONTINUITY`. **Direction:** support.
  **Strength:** `WEAK` or `MODERATE` (**ceiling lowered from `STRONG`**).
* **Biological rationale:** none, directly -- a kinetic-law *type*
  difference (e.g. `MASS_ACTION` vs `MICHAELIS_MENTEN`) is a modeling-
  form artifact reflecting how Agent 2 chose to represent each
  reaction's rate law, not a biological claim of independence.
* **Implementation:** fires when the two sides' assigned
  `KineticLawType` sets differ (and neither is merely the trivial "both
  `UNASSIGNED`" case, which is not a difference at all). Strength is the
  *weaker* of the two sides' own assignment confidence
  (`rules.weaker_strength`) -- collapsed to a 2-level `WEAK`/`MODERATE`
  output (never `STRONG`): a discontinuity next to a tentative default
  or an `UNASSIGNED` law remains `WEAK`; one between two well-supported
  curated/structural laws is `MODERATE`, never higher.
* **Limitations:** retained as support evidence because a genuine,
  confidently-assigned mechanistic difference is still *some* signal,
  but explicitly capped so it can never carry functional-isolation-grade
  weight.
* **Future improvements:** none identified.

## 20. Parameter-source heuristics (retired to permanent `NEUTRAL`)

`parameter_source_discontinuity`, `placeholder_parameter_region`, and
`parameterization_continuity` all **always return `NEUTRAL`** as of this
revision (see §11 for the rationale). Individually:

* **`PARAMETER_SOURCE_DISCONTINUITY`** (previously: support, `WEAK`, on
  a `ParameterSource`-set difference between sides). Retired: which
  measurements exist is a knowledge-state fact, not a biological one.
* **`PLACEHOLDER_PARAMETER_REGION`** (previously: support, `WEAK`, when
  one side is entirely `PLACEHOLDER` and the other has curated values).
  Retired for the identical reason -- a knowledge gap is not evidence
  the two sides function independently.
* **`PARAMETERIZATION_CONTINUITY`** (previously: oppose, `MODERATE`, on
  matching parameter-source *and* kinetic-law sets). Retired for the
  identical reason; its kinetic-law-sameness component is already
  covered, on genuinely structural grounds, by `strong_local_continuity`
  (§22).
* **Future improvements:** none anticipated for boundary-likelihood
  purposes. A future increment could reactivate these under a clearly-
  labeled, separate "calibration convenience" disclosure (e.g. for
  Increment 7 to prioritize which candidate modules are cheapest to
  parameterize independently) -- a genuinely different question from
  "is this a real functional boundary," which is why the vocabulary was
  kept rather than deleted.

## 21. High-connectivity species

* **Reason code:** `HIGH_CONNECTIVITY_CONTINUITY`. **Direction:**
  oppose. **Strength:** `MODERATE` (**reconsidered, retained**).
* **Biological rationale:** a species touched by many reactions (a
  "currency metabolite" such as ATP/NADH in spirit, though never
  identified by name) is a classical example of a poor module anchor --
  it couples otherwise-independent processes, a network-scale form of
  resource coupling (§23).
* **Implementation:** fires when any shared species is touched
  (produced or consumed) by strictly more than
  `assessor._HIGH_CONNECTIVITY_THRESHOLD = 3` distinct reactions -- a
  small, fixed, documented integer count, never a percentage of network
  size and never a per-compound-name list.
* **Deferred alternative considered:** a dedicated *supporting*
  `HIGH_CONNECTIVITY_SHARED_SPECIES` code (using the identical
  connectivity signal to argue *for* a boundary) was considered and
  deliberately not added -- using the same structural fact as both
  supporting and opposing evidence on the same candidate would be
  self-contradictory noise, not the "complex reasoning" this package
  aims for (§8). Only the opposing framing (a hub is a poor anchor) is
  implemented.
* **Future improvements:** a real, curated currency-metabolite
  classification (rather than a connectivity-count proxy) would be more
  precise, but Agent 1 does not yet curate one; hard-coding a metabolite
  name list was explicitly rejected as unscientific.

## 22. Strong-local-continuity heuristic

* **Reason code:** `STRONG_LOCAL_CONTINUITY`. **Direction:** oppose.
  **Strength:** `STRONG` (**reconsidered, retained, with one
  correction**).
* **Biological rationale:** when a reaction pair shares a compartment,
  shares a *meaningfully assigned* kinetic-law form, has no branch or
  convergence, and is not a transport step, that is a demanding,
  conjunctive argument that the interface is an ordinary internal chain
  link, not a boundary.
* **Implementation:** requires *all* of: same compartment set; same
  kinetic-law type set, **and that set is not merely `{UNASSIGNED}` on
  both sides**; no branch; no convergence; neither side transport.
* **Correction made during this revision:** the pre-revision "same law"
  condition counted two reactions that both simply have *no* assigned
  law (`UNASSIGNED`) as "sharing a law" -- mutual absence of information
  masquerading as continuity evidence, exactly the failure mode this
  revision exists to correct (discovered via smoke-testing before any
  test was written; see
  `tests/agent2/test_boundaries.py::test_strong_local_continuity_requires_a_meaningfully_shared_law_not_mutual_unassigned`).
* **Why retained at `STRONG` rather than downgraded:** unlike the other
  structural proxies, this rule's conjunctive, all-or-nothing structure
  already makes it demanding; it remains the primary source of
  `LOW`/`VERY_LOW` outcomes, and genuine conflicting evidence (this rule
  firing alongside a real functional-isolation signal) is not specially
  excluded -- `policy.combine_outcomes` already resolves that
  conservatively toward `MEDIUM` (§12) rather than an extreme
  likelihood, so no further weakening was judged necessary.
* **Future improvements:** none identified.

## 23. Shared-resource coupling (new)

* **Reason code:** `SHARED_RESOURCE_COUPLING`. **Direction:** oppose.
  **Strength:** `MODERATE`.
* **Biological rationale:** if two reactions are catalyzed by the same
  protein, complex, or enzyme state, they compete for the same limiting
  catalytic resource -- a textbook form of coupling that argues against
  treating them as independent modules.
* **Implementation:** fires when the two sides' catalytic identity sets
  (`catalytic_protein_ids` ∪ `catalytic_complex_ids` ∪
  `catalytic_enzyme_state_ids`, from `ReactionCharacterization`)
  intersect.
* **Limitations:** only detects catalyst-sharing, not other limiting
  resources (a shared cofactor pool, a shared scaffold protein) the
  task's own framing also names -- those are not currently represented
  in a form this package can resolve deterministically.
* **Future improvements:** extend to shared cofactor/substrate coupling
  if and when Agent 1 curates a resolvable, closed vocabulary for
  "limiting" cofactors/scaffolds distinguishable from ordinary
  participants.

## 24. Intrinsic-feedback-isolation heuristic

* **Reason code:** `INTRINSIC_FEEDBACK_ISOLATION` (renamed twice: from
  `NEGATIVE_FEEDBACK_ISOLATION` in the feedback-heuristic revision below,
  then from `INTRINSIC_FEEDBACK_CONFINEMENT` in a later terminology-only
  revision -- see "Naming: confinement vs. isolation" below).
  **Direction:** oppose (**revised from support**). **Strength:**
  `STRONG`.
* **Biological rationale:** feedback confined entirely within one side
  of a proposed boundary is *intrinsic* feedback -- direct, local, and
  (as far as it is curated) constitutive. Nested feedback loops are
  ordinary biology, and an inner loop of exactly this kind is usually
  what *defines* a module in the first place (a classical example is
  end-product inhibition of a pathway's own committed step). Evidence of
  an intact intrinsic loop therefore argues for **preserving** that
  side's isolation -- i.e. against introducing more boundary structure
  right at its edge -- not for treating this specific interface as a
  confirmed cut point. See "Nested Feedback Loops" below for the full
  conceptual distinction and why this direction was revised.
* **Naming: confinement vs. isolation.** The rule and reason code were
  originally named `intrinsic_feedback_confinement`/
  `INTRINSIC_FEEDBACK_CONFINEMENT`. That name described a *geometric*
  fact -- where the interaction sits relative to the interface -- but the
  scientific concept this rule actually targets is not mere spatial
  confinement: it is that local, direct, strong negative feedback can
  provide *functional isolation* by reducing retroactivity and
  preserving intrinsic module behavior. "Isolation" names that functional
  consequence directly, so the rule and reason code were renamed to
  `intrinsic_feedback_isolation`/`INTRINSIC_FEEDBACK_ISOLATION`. This was
  a naming/documentation-only change: the deterministic trigger,
  direction (`OPPOSE`), and strength (`STRONG`) below are unchanged from
  the prior name, and `BOUNDARY_POLICY_VERSION` was **not** bumped for it
  (§37).
* **Preserving the local circuit (what `OPPOSE` does *not* mean).** This
  rule opposes placing **a boundary inside the locally isolated circuit**
  that the confined feedback interaction defines -- it is an argument for
  preserving that self-regulated circuit's integrity. It is **not** an
  argument that the two candidate reactions should necessarily be merged
  into one module, and it must never be read that way: Agent 2 does not
  decide module membership or perform any merge here (that is
  Increment 7's job, out of scope for this package entirely). "Oppose a
  boundary at this interface" and "these reactions form one module" are
  different claims; this rule only makes the first one.
* **Implementation:** a curated `CuratedRegulatoryInteraction` is
  "confined" when its `regulator_id` (recognized only when
  `regulator_type` normalizes to `"COMPOUND"`) touches one candidate
  reaction's own participants (by `source_compound_id`) but not the
  other's, its `target_id` (recognized only when `target_type`
  normalizes to `"REACTION"`) is the reaction on that *same* side, and
  its `effect` normalizes to a recognized inhibitory marker
  (`"INHIBITION"`/`"INHIBITOR"`/`"NEGATIVE"`). Fires `STRONG` opposition
  only then.
* **Expected common case:** `NEUTRAL`. Agent 1's regulation pipeline is
  known-incomplete, `regulator_type`/`target_type` are open strings (not
  a closed Agent 1 vocabulary), and `regulator_id`/`target_id` are
  optional -- most curated interactions will not resolve to identifiable
  compound/reaction ids on both a recognized type *and* a determinable
  side. This is expected and acceptable (Increment 6's own instruction:
  "insufficient information exists... acceptable"), never treated as "no
  feedback exists."
* **Limitations:** resolves a regulator's "side" only against the two
  *candidate* reactions' own direct participants -- never the broader
  network -- so a regulator produced two reactions upstream of the
  candidate, for instance, resolves to neither side and yields `NEUTRAL`
  rather than a guess. Cannot distinguish a genuinely tight,
  constitutive loop from a weaker or conditional one -- see "Future
  Dynamic Refinement" below.
* **Future improvements:** a broader, network-wide side-resolution (e.g.
  "produced anywhere within a tentative module boundary") belongs to
  Increment 7, which actually reasons about module extents; this
  increment deliberately stays local to one candidate interface. Loop
  strength/directness itself awaits Agent 4 (see "Future Dynamic
  Refinement").

## 25. Extrinsic-feedback-crossing heuristic (always `NEUTRAL`)

* **Reason code:** `EXTRINSIC_FEEDBACK_CROSSING_DEFERRED` (renamed from
  `FEEDBACK_CROSSING_BOUNDARY`). **Direction:** always `NEUTRAL`
  (**revised from oppose**). **Strength:** none.
* **Biological rationale:** a regulatory loop that crosses a proposed
  interface -- its regulator on one side, its target on the other -- is
  **not**, by itself, evidence the two sides should be merged. Nested
  feedback loops are ordinary biology: a loop spanning a module boundary
  is frequently *extrinsic*, module-*regulating* communication (e.g. a
  downstream module signaling demand back to an upstream one), not proof
  the two sides are one functional unit. See "Nested Feedback Loops"
  below.
* **Implementation:** the same resolution machinery as §24 still
  computes `crossing_regulatory_interaction` (`regulator_id` resolves to
  one side, `target_id`'s own reaction to the *other*), but the rule
  function deliberately never branches on it -- it always returns
  `NEUTRAL`, regardless of the underlying `effect`'s sign. This is not
  an oversight: only a boundary-crossing loop additionally confirmed
  direct, strong, constitutive, local, and minimally regulated would be
  legitimate grounds to oppose a boundary, and Agent 2 has no
  dynamic-simulation capability with which to confirm any of that (no
  loop gain, response time, relaxation time, retroactivity, buffering
  strength, or condition-dependence estimate -- see "Future Dynamic
  Refinement"). Fabricating that judgment from static structure alone
  would misrepresent what this package actually knows.
* **Why the fact is still computed:** keeping
  `crossing_regulatory_interaction` computed and available (rather than
  deleting the detection outright) lets a future revision -- once Agent 4
  can supply the missing dynamic evidence -- reactivate this rule without
  reworking the underlying resolution logic, mirroring the precedent
  already set for the retired parameterization-convenience codes (§20).
* **Why no inference is made, spelled out.** Even once a crossing
  interaction is confirmed *structurally*, Agent 2 currently cannot
  determine whether it is:
  * direct (vs. mediated through additional signaling components),
  * strong (vs. weak),
  * constitutive (vs. condition-dependent),
  * regulated (vs. minimally regulated),
  * adaptive (vs. fixed),
  * dynamically isolating (buffers one side from the other), or
  * dynamically coupling (transmits perturbations between sides) --

  and any one of these could change whether the interaction is
  legitimate evidence against a boundary. This is a concise, deterministic
  explanation of an epistemic limit, not an invented measurement: no
  dynamic quantity above is estimated or approximated anywhere in this
  package. `NEUTRAL` is the honest answer to "not enough information,"
  not a placeholder for a hidden default.
* **Limitations:** as §24 (candidate-local resolution only).
* **Future improvements:** see "Future Dynamic Refinement" below.

## 25a. Nested Feedback Loops

Biological signaling and metabolic networks commonly contain **nested**
feedback loops, and this package's feedback rules (§24-25) are organized
around that structure rather than treating every regulatory loop as
equally informative about modularity:

* **Module-defining (intrinsic) feedback.** An inner feedback loop
  confined entirely within one side of a candidate interface -- direct,
  local, and (as far as curated) constitutive -- is usually what makes
  that region a functional module in the first place. Classic end-product
  inhibition of a pathway's own committed step is the textbook example:
  the loop's existence is part of *why* the pathway behaves as one
  self-regulating unit. `intrinsic_feedback_isolation` (§24) treats
  this as evidence to **preserve**, not cut through -- it opposes
  introducing a boundary at the edge of an already self-regulated region.
* **Module-regulating (extrinsic) feedback.** An outer feedback loop that
  crosses a module boundary commonly exists to *regulate* the behavior of
  an already-independent module from outside it -- communication between
  modules, not evidence they are one module. A downstream module
  signaling its own demand back to an upstream supply module is a typical
  case. `extrinsic_feedback_crossing` (§25) therefore does not treat a
  crossing loop as evidence against a boundary.
* **Why they must not be conflated.** Treating every regulatory loop
  identically -- as the pre-revision catalog did, opposing a boundary
  whenever *any* feedback crossed it -- would systematically penalize
  ordinary, healthy module-regulating communication and reward the
  absence of curated regulatory data (a known-incomplete curation
  pipeline) as if it were evidence of independence. The intrinsic/
  extrinsic distinction lets this package instead encode the correct
  biological asymmetry: an *inner* loop argues for keeping its enclosing
  region intact; an *outer*, crossing loop is presumptively normal
  inter-module signaling until proven otherwise.

## 25b. Future Dynamic Refinement

Agent 2 currently has no dynamic-simulation capability: it cannot
estimate loop gain, response time, relaxation time, retroactivity,
buffering strength, or dynamic sensitivity, and it cannot determine
whether a given feedback interaction is constitutive or condition-
dependent. `extrinsic_feedback_crossing` (§25) is therefore deliberately
conservative -- always `NEUTRAL` -- rather than guessing at any of these
properties from static curated structure.

Agent 4 (parameter estimation and simulation) is expected to eventually
be able to estimate exactly these quantities. Once it can, a future
revision may allow a boundary-crossing feedback loop to legitimately
oppose a boundary -- but only when it is additionally confirmed direct,
strong, constitutive, local, and minimally regulated (Increment 6
feedback-heuristic revision's own Rule 3); never inferred from structure
alone. At that point these heuristics can become evidence-driven rather
than purely structural, and `intrinsic_feedback_isolation` (§24) could
likewise be refined from "confined, therefore presumed constitutive" to
a genuinely measured constitutive/conditional distinction.

## 26. Irreversible output isolation (new)

* **Reason code:** `IRREVERSIBLE_OUTPUT_ISOLATION`. **Direction:**
  support. **Strength:** `STRONG`.
* **Biological rationale:** an irreversible, committed step insulates
  whatever precedes it from downstream retroactivity by construction --
  downstream demand cannot propagate backward through a step that
  cannot run in reverse. Proteolysis, an irreversible covalent
  modification, or simply a strongly favorable equilibrium are all
  biological instances of this.
* **Implementation:** fires when the *upstream* reaction of the
  candidate (the one feeding the interface) is explicitly curated
  `reversible=False`. `NEUTRAL` when `reversible` is `True` or
  unrecorded (`None`) -- never guessed. **("Conservative Reversibility
  Default for Unresolved Reactions" increment, confirmatory, no code
  change here)**: this file's own §4 critical invariant already held
  before `app.agent2.reversibility` existed -- only *explicitly curated*
  irreversibility (`reversible is False`) may contribute this evidence.
  The new "assumed reversible" model-construction default
  (`app.agent2.reversibility.effective_reversible`, used only by
  Antimony generation and `ModelSpecification.model_assumptions`, see
  `docs/12_antimony_generation.md` §13) is never consulted here; an
  unresolved `reversible` reaction remains `NEUTRAL` for this rule
  exactly as before, locked in by regression tests in
  `tests/agent2/test_boundaries.py`.
* **Limitations:** cannot distinguish *why* a reaction is irreversible
  (proteolysis vs. an irreversible modification vs. a favorable
  equilibrium) -- `ReactionSpecification.reversible` is a single
  boolean, not a mechanism classification. All three collapse to the
  same evidence here.
* **Future improvements:** if Agent 1 ever curates a mechanism-specific
  irreversibility classification (e.g. distinguishing proteolytic
  cleavage from a simple thermodynamically-favored step), this rule
  could be split or its strength further differentiated.

## 27. Deferred principles (new; always `NEUTRAL`)

Three biological modularity principles are real, but this package
cannot yet evaluate them from static curated structure alone. Rather
than fabricate a heuristic, each is a dedicated, clearly-documented rule
that **always returns `NEUTRAL`**:

* **`RELAXATION_TIME_INVARIANCE_DEFERRED`** (`relaxation_time_invariance`)
  -- whether a module's internal relaxation time is invariant to (much
  faster than) perturbations from its surroundings is a genuine
  functional-modularity criterion, but evaluating it requires dynamical
  simulation. **Deferred to Agent 4.**
* **`CONTEXT_REUSABILITY_DEFERRED`** (`context_reusability`) -- whether a
  candidate module's behavior is reusable/composable across different
  surrounding biological contexts cannot be assessed from one curated
  network alone; it requires comparison across multiple organisms/
  conditions Agent 1 does not yet curate in a comparable form.
  **Deferred pending that curated data.**
* **`STABLE_FUNCTIONAL_ROLE_DEFERRED`** (`stable_functional_role`) --
  whether a candidate module performs a stable, identifiable functional
  role (e.g. "switch," "oscillator," "amplifier") independent of context
  is a dynamical-systems classification this package cannot make from
  static structure. **Deferred to a later agent characterizing dynamical
  behavior.**

These three are included in `rules.ALL_RULES` (so their permanent-
`NEUTRAL` behavior is itself tested and auditable,
`tests/agent2/test_boundaries.py::test_deferred_principles_always_neutral`)
rather than omitted -- the vocabulary documents what this package
*cannot yet* do, expected to become active once the named later-agent
capability exists.

## 28. `BoundaryParameterBasis`

`NONE`/`PLACEHOLDER_ONLY`/`DEFAULT_ONLY`/`CURATED_OR_LITERATURE`/
`CALIBRATED`/`MIXED`, computed from the actual set of `ParameterSource`
values involved on both sides. This is the *only* place parameter
provenance is disclosed on a `BoundaryAssessment` after this revision --
never through `supporting_reason_codes`/`opposing_reason_codes` (§11,
§20).

**Heuristic Simulation Parameter Initialization increment:**
`compute_parameter_basis` (`app.agent2.boundaries.policy`) now treats the
new `ParameterSource.HEURISTIC_INITIALIZATION` identically to the
pre-existing `ParameterSource.DEFAULT` for this classification -- a set
containing only `DEFAULT` and/or `HEURISTIC_INITIALIZATION` values still
resolves to `DEFAULT_ONLY`, never `PLACEHOLDER_ONLY`/`MIXED`. Both are
values Agent 2 invented itself from its own policy, never real evidence
-- conceptually identical for this qualitative disclosure, even though
they remain two distinct `ParameterSource` values everywhere else. A
practical consequence: a candidate boundary whose only reactions are bare
state-transition-shaped `MASS_ACTION` reactions with no curated evidence
at all -- previously `PLACEHOLDER_ONLY` -- is now `DEFAULT_ONLY`, since
those reactions' rate constants are heuristically initialized rather than
left as bare placeholders (see
`tests/agent2/test_boundaries.py::test_placeholder_only_region_gives_default_only_basis`).
`ParameterSource.AI_PREDICTED` is deliberately left unhandled here (it
falls through to the safe `MIXED` classification) -- a separate design
question this increment did not need to resolve.

## 29. Audit/provenance

Unchanged. Every `BoundaryAssessment` lists sorted `kinetic_law_ids`/
`parameter_ids` from both sides' reactions.

## 30. Reassessment after Agent 4 calibration

Unchanged. `boundary_id` is a pure function of structural reaction ids
only -- stable across two `assess_boundaries` calls with different
`ParameterDeclarationSet` inputs, while `likelihood`/reason codes/
`parameter_basis`/`explanation` may legitimately vary.

## 31. Determinism

Unchanged guarantees. Candidates are generated from producer/consumer
*sets*; the final `assessments` tuple is sorted; every id-tuple is
`tuple(sorted(...))`; rule evaluation order never affects the result.

## 32. Validation

Unchanged. `require_full_network`/`require_network_characterization`/
`require_kinetic_law_assignment_set`/`require_parameter_declaration_set`
confirm input types; `assess_boundaries` raises `BoundaryReferenceError`
on `network_id` mismatch or an unresolvable reference;
`BoundaryAssessmentSet.__post_init__` rejects duplicate `boundary_id`;
`RuleOutcome.__post_init__` enforces `strength` set if and only if
`direction` is not `NEUTRAL`.

## 33. Explicit non-goals

Unchanged. No `ModuleSpecification`/`ModuleDecomposition`/module id/cut
set/partition/clustering; no steady-state/sensitivity/flux/timescale/
parameter-identifiability calculation; no mass-balance/disconnected-
subnetwork/conservation-law/unit-consistency validation (Agent 3); no
thermodynamic-plausibility/cofactor/biological-realism judgment
(Agent 5). No numeric boundary scoring, no machine learning, no
probabilistic model, no graph clustering was introduced by this
revision either.

## 34. Handoff to Increment 7

Unchanged. `BoundaryAssessmentSet` gives Increment 7 every candidate
interface's qualitative likelihood, full supporting/opposing reasoning
(now more precisely separating structural proxies, retired
parameterization-convenience codes, and functional-modularity evidence),
and law/parameter provenance -- a decision this increment deliberately
never makes itself.

## 35. Testing

`tests/agent2/test_boundaries.py` (55 tests) covers: candidate
generation; every structural-proxy heuristic at its revised strength;
the `strong_local_continuity` mutual-`UNASSIGNED` correction; the three
retired parameterization-convenience codes never appearing in any
assessment under any tested scenario; the four functional-modularity
rules, including their `NEUTRAL`-when-unresolvable behavior (unrecognized
`regulator_type`, missing `target_id`, a regulator external to both
sides); the feedback-heuristic revision specifically --
`intrinsic_feedback_isolation` opposing (not supporting) a boundary
when confined inhibitory feedback is confirmed, and
`extrinsic_feedback_crossing` always returning `NEUTRAL` regardless of
whether a crossing interaction is confirmed and regardless of its effect
sign (both through a realistic scenario and a direct unit call over
`crossing_regulatory_interaction=True/False`); the terminology-only
rename to `INTRINSIC_FEEDBACK_ISOLATION`, including an enum/function-
level test that the old `INTRINSIC_FEEDBACK_CONFINEMENT`/
`intrinsic_feedback_confinement` names no longer exist anywhere; the
three deferred principles always returning `NEUTRAL` (both through
realistic scenarios and a direct unit call); every `BoundaryLikelihood`
value, including the revised `VERY_HIGH` condition and a direct unit
test of `policy.combine_outcomes` for combinations difficult to isolate
through a full curated scenario; reassessment stability; and
determinism. `tests/agent2/test_boundaries_scope.py` (9 tests) covers
structural scope-safety (§33), re-verified passing unmodified after all
three revisions.

## 36. Known limitations

* "Weakly connected interface" has no dedicated rule -- it is the
  natural fallback of `policy.combine_outcomes` itself.
* An enzyme-state transition or regulatory interaction with no shared-
  species connectivity between the two candidate reactions generates no
  candidate at all -- candidate generation remains anchored strictly to
  mass-transfer connectivity.
* `intrinsic_feedback_isolation`/`extrinsic_feedback_crossing` resolve
  a regulator's "side" only against the two candidate reactions' own
  direct participants, never the broader network (§24-25).
* `extrinsic_feedback_crossing` cannot yet act on a boundary-crossing
  loop at all, however direct or constitutive it may actually be --
  always `NEUTRAL` until Agent 4 can supply dynamic evidence (§25b).
* `intrinsic_feedback_isolation` treats every confined inhibitory
  interaction as equally "intrinsic" -- it cannot yet distinguish a
  genuinely tight, constitutive loop from a weaker or conditional one
  (§25b).
* `irreversible_output_isolation` cannot distinguish *why* a reaction is
  irreversible (§26).
* `shared_catalyst_coupling` detects only catalyst-sharing, not other
  forms of limiting-resource competition (shared cofactor pools,
  scaffolds) the underlying principle also names (§23).
* The high-connectivity threshold (§21) and every rule's strength
  assignment remain fixed, documented constants chosen for conservatism,
  not derived from the network's own statistical distribution.
* The three deferred principles (§27) are placeholders by design, not
  implementations -- they contribute nothing until a later agent exists.

None of these block correctness: each routes the affected candidates
toward `NEUTRAL`/conservative outcomes rather than a wrong answer.

## 37. Versioning

`BOUNDARY_POLICY_VERSION` bumped `"boundary-v1"` -> `"boundary-v2"` for
this pre-commit scientific revision: the rule catalog's actual behavior
changed substantially (three rules retired to permanent `NEUTRAL`, three
downgraded in strength, one corrected, four new rules, three deferred
placeholders, and the `VERY_HIGH` combination condition redefined) before
either version was ever committed -- consistent with this repository's
established precedent (`KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`'s own
`v1`->`v2` bump during Increment 4's pre-commit revision): the version
marker tracks behavior, not git history. `AGENT2_CONTRACT_VERSION` is
**unchanged**: no field of any `app.agent2.types` type changed shape
(`BoundaryAssessment`/`BoundaryLikelihood`/`BoundaryParameterBasis`
remain untouched, exactly as the original Increment 6 implementation
left them). `AGENT1_HANDOFF_VERSION` is unchanged -- Agent 1 was not
modified.

`BOUNDARY_POLICY_VERSION` bumped again, `"boundary-v2"` -> `"boundary-v3"`,
for the feedback-heuristic revision (§24-25b): `NEGATIVE_FEEDBACK_ISOLATION`
was renamed `INTRINSIC_FEEDBACK_CONFINEMENT` and its direction flipped
from support to oppose; `FEEDBACK_CROSSING_BOUNDARY` was renamed
`EXTRINSIC_FEEDBACK_CROSSING_DEFERRED` and now always evaluates
`NEUTRAL`. Same inputs can now produce a different assessment for any
candidate touching a curated regulatory interaction, so the policy
version is bumped even though this increment remains uncommitted -- the
version marker tracks behavior, not git history.
`policy.combine_outcomes` itself (the categorical decision table) was
**not** modified by this revision -- only which rules feed it changed.
`AGENT2_CONTRACT_VERSION` is **unchanged**: the renamed/redirected rules
live entirely in `app.agent2.boundaries`, not `app.agent2.types`.
`AGENT1_HANDOFF_VERSION` is unchanged -- Agent 1 was not modified.

`BOUNDARY_POLICY_VERSION` is **retained at `"boundary-v3"`** (not
bumped) for the subsequent terminology revision that renamed
`INTRINSIC_FEEDBACK_CONFINEMENT`/`intrinsic_feedback_confinement` to
`INTRINSIC_FEEDBACK_ISOLATION`/`intrinsic_feedback_isolation` (§24) and
added the heuristic-class taxonomy (§11a). This is a deliberate
departure from the "bump on any behavior change" pattern used for the
two entries above, justified because there genuinely is no behavior
change to track: the deterministic trigger condition, direction
(`OPPOSE`), and strength (`STRONG`) of the renamed rule are byte-
identical to before, `policy.combine_outcomes` was not touched, and the
taxonomy added to §11a is documentation-only and is never consulted by
`combine_outcomes` or any rule. The only externally-visible effect is
that the string `"INTRINSIC_FEEDBACK_CONFINEMENT"` no longer appears in
any `BoundaryAssessment.opposing_reason_codes` tuple and
`"INTRINSIC_FEEDBACK_ISOLATION"` appears in its place under the
identical firing condition -- a vocabulary rename, not a policy change,
so per this file's own bump criterion ("bump a constant only when the
shape or policy it names actually changes") no bump is warranted.
`AGENT2_CONTRACT_VERSION` and `AGENT1_HANDOFF_VERSION` are unchanged for
the same reasons already given above.

## 38. Final architectural rule

> Boundary assessments are qualitative heuristic judgments, not
> probabilities and not final partitions.

> A module is a functional unit whose intrinsic behavior is largely
> independent of its surrounding network -- not merely a densely
> connected region of a graph. Agent 2 currently evaluates structural
> proxies for that functional independence, not functional modularity
> itself; where a rule can instead evaluate the biological definition
> directly (isolation, coupling, feedback), it does.

> The full network remains authoritative.

> Increment 6 evaluates candidate interfaces; Increment 7 decides how
> those assessments are used to construct module decompositions.

> Parameter fitting and dynamic timescale analysis remain the
> responsibility of Agent 4.
