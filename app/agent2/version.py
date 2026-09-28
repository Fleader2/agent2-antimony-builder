"""Agent 2 version/policy markers.

These are architecture/contract-shape version markers, not claims of
scientific maturity. Bump a constant only when the shape or policy it
names actually changes.

* ``AGENT2_CONTRACT_VERSION`` -- the version of Agent 2's own output
  contracts (``app.agent2.types``: ``ModelSpecification``,
  ``ModuleDecomposition``, and the rest).
* ``AGENT1_HANDOFF_VERSION`` -- the version of the Agent 1 handoff
  contract (``docs/02_agent1_handoff_contract.md``) this repository was
  built against. Not a guarantee that every other version is compatible;
  version reconciliation is deferred (see that document's §9).
* ``BOUNDARY_POLICY_VERSION`` -- the version of the module-boundary
  heuristic rule set a ``BoundaryAssessment``/``ModuleDecomposition`` was
  produced under. No boundary heuristic rules exist yet (Increment 1 is
  contracts only) -- this constant exists so the first real rule set has
  somewhere stable to record its own version from the start.
* ``REACTION_CHARACTERIZATION_POLICY_VERSION`` -- the version of the
  deterministic reaction/enzyme-state characterization rule set
  (``app.agent2.characterization``) a ``NetworkCharacterization`` was
  produced under (e.g. the ``TRANSPORT`` classification rule, the flag/
  unresolved-feature emission rules). Distinct from
  ``AGENT2_CONTRACT_VERSION``: this versions a *behavioral rule set*, not
  a data shape.
* ``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`` -- the version of the
  deterministic kinetic-law assignment rule set
  (``app.agent2.kinetics``) a ``KineticLawAssignmentSet`` was produced
  under (e.g. the reported-rate-law text classifier, the Michaelis-Menten
  and mass-action-fallback heuristic eligibility rules). Also a
  *behavioral rule set* version, not a data shape.
* ``PARAMETER_DECLARATION_POLICY_VERSION`` -- the version of the
  deterministic parameter declaration/initialization rule set
  (``app.agent2.parameters``) a ``ParameterDeclarationSet`` was produced
  under (e.g. which curated measurement types map to which kinetic-law
  parameter slot, the multiple-measurement agreement policy, and, since
  the Heuristic Simulation Parameter Initialization increment, the
  AI-predicted/heuristic-default fallback precedence). Also a *behavioral
  rule set* version, not a data shape.
* ``HEURISTIC_INITIALIZATION_POLICY_VERSION`` -- the version of the
  centralized heuristic-default policy
  (``app.agent2.parameters.heuristic_defaults``) a
  ``ParameterSource.HEURISTIC_INITIALIZATION`` parameter's own default
  value/unit was chosen under (e.g. the reference rate/concentration
  constants, the molecularity-to-unit mapping for mass-action rate
  constants). Recorded on each such parameter's own
  ``source_reference`` (a per-parameter string, not a
  ``ParameterDeclarationSet``-level field) precisely because it can, in
  principle, change independently of the broader parameter-declaration
  rule set above -- distinct axes that happen to co-evolve today, not
  reused as a single version for both.
* ``MODULE_DECOMPOSITION_POLICY_VERSION`` -- the version of the
  deterministic module-decomposition rule set (``app.agent2.modules``) a
  ``ModuleDecompositionSet`` was produced under (e.g. which
  ``BoundaryLikelihood`` values cut vs. become candidates, the
  connected-component partitioning rule). Also a *behavioral rule set*
  version, not a data shape.
* ``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` -- the version of the
  deterministic cross-artifact assembly policy
  (``app.agent2.model_specification``) a ``ModelSpecification`` was
  produced under (e.g. the ``KineticLawAssignment`` ->
  ``KineticLawSpecification`` materialization rule, the
  ``KineticLawAssignmentSource`` -> ``ParameterSource`` bridge, the
  expression-template policy, which categories of incompleteness become
  ``ModelAssumption`` records). Also a *behavioral rule set* version, not
  a data shape -- distinct from ``AGENT2_CONTRACT_VERSION``, which
  versions ``ModelSpecification``'s own shape.
* ``ANTIMONY_GENERATION_POLICY_VERSION`` -- the version of the
  deterministic Antimony-serialization policy (``app.agent2.antimony``) a
  ``FullAntimonyArtifact``/``ModuleAntimonyArtifact`` was produced under
  (e.g. the identifier-sanitization/collision policy, the built-in
  expression-template token-substitution rule, the unresolved-kinetics/
  readiness policy, the reversibility and amount-vs-concentration
  serialization conventions). Also a *behavioral rule set* version, not a
  data shape.

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.1"`` to ``"0.2"`` in
Increment 1: ``ModelSpecification``'s shape changed in a
backward-incompatible way (flat id-tuple fields replaced by a real
``FullNetwork``/``kinetic_laws``/``parameters`` with full reference-
integrity validation). ``AGENT1_HANDOFF_VERSION``/``BOUNDARY_POLICY_VERSION``
are unchanged -- the Agent 1 handoff shape did not change, and no boundary
heuristic rule set exists yet to version.

``AGENT1_HANDOFF_VERSION`` was bumped from ``"1.0"`` to ``"1.1"`` for
Agent 1.x Increment A: Agent 1's own ``Agent1CuratedKnowledgeView`` gained
a ``kinetic_measurements`` field (``AGENT1_CONTRACT_VERSION`` "1.0" ->
"1.1" in the Agent 1 repository), so this repository's local
``Agent1CuratedKnowledgeViewContract`` was extended to match exactly (see
``docs/02_agent1_handoff_contract.md``). ``AGENT2_CONTRACT_VERSION`` is
unchanged -- no field of Agent 2's own output contracts (``FullNetwork``,
``ModelSpecification``, ...) changed shape; only the *input* handoff
contract gained a field.

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.2"`` to ``"0.3"`` in
Increment 2 (Whole-Network Assembly): ``FullNetwork`` gained
``enzyme_associations``/``regulatory_interactions``/``kinetic_measurements``,
and a new domain type, ``ReactionEnzymeAssociation``, was introduced.
Every new field has a default (`()`), so existing keyword-based
construction of ``FullNetwork`` is unaffected, but ``FullNetwork``'s own
reference-integrity validation grew three new checks -- an output-contract
shape change per this file's own bump criterion. ``AGENT1_HANDOFF_VERSION``/
``BOUNDARY_POLICY_VERSION`` are unchanged -- the Agent 1 handoff shape did
not change, and no boundary heuristic rule set exists yet.

``AGENT1_HANDOFF_VERSION`` was bumped from ``"1.1"`` to ``"1.2"`` for
Agent 1.x Increment B: Agent 1's own ``Agent1CuratedKnowledgeView`` gained
``enzyme_states``/``enzyme_modifications``/``allosteric_interactions``/
``enzyme_state_transitions`` and ``enzyme_state_id`` on
``CuratedKineticMeasurement`` (``AGENT1_CONTRACT_VERSION`` "1.1" -> "1.2"
in the Agent 1 repository), so this repository's local
``Agent1CuratedKnowledgeViewContract`` and ``CuratedKineticMeasurement``
were extended to match exactly (see `docs/02_agent1_handoff_contract.md`).
``AGENT2_CONTRACT_VERSION`` is unchanged -- no field of Agent 2's own
output contracts changed shape, and Whole-Network Assembly
(``app.agent2.network``) was not modified to consume the new fields; only
the *input* handoff contract gained fields.

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.3"`` to ``"0.4"`` in
Increment 3 (Reaction and Enzyme-State Characterization): ``FullNetwork``
gained ``enzyme_states``/``enzyme_modifications``/``allosteric_interactions``/
``enzyme_state_transitions`` (carried forward from the Increment B handoff
fields, unmodified), and both ``CuratedReactionEnzymeAssociation`` and
``ReactionEnzymeAssociation`` gained ``enzyme_state_id`` (a discovered gap
from Agent 1.x Increment B -- see their docstrings). ``FullNetwork``'s own
reference-integrity validation grew new checks for all of the above. A new
output contract package, ``app.agent2.characterization``
(``ReactionCharacterization``/``EnzymeStateCharacterization``/
``NetworkCharacterization``), was also introduced. Every new ``FullNetwork``
field has a default (``()``), so existing keyword-based construction is
unaffected, but this is still an output-contract shape change per this
file's own bump criterion. ``AGENT1_HANDOFF_VERSION`` is unchanged --
already at ``"1.2"``, matching Agent 1's current ``AGENT1_CONTRACT_VERSION``;
Agent 1 was not modified in this increment (input-only).
``REACTION_CHARACTERIZATION_POLICY_VERSION`` is introduced at
``"reaction-characterization-v1"`` for the first real characterization
rule set (catalyst/regulation/allostery/kinetic-evidence characterization,
the conservative ``TRANSPORT`` rule).

``AGENT2_CONTRACT_VERSION`` is **unchanged** at ``"0.4"`` for Increment 4
(Kinetic-Law Assignment): no field of any type in ``app.agent2.types``
changed shape -- the new ``KineticLawAssignment``/``KineticLawAssignmentSet``/
``KineticLawAssignmentSource``/``KineticLawReasonCode`` types live entirely
in the new, separate ``app.agent2.kinetics`` package and are never
constructed from or written back onto anything in ``app.agent2.types``
(``KineticLawSpecification``/``ModelSpecification`` are untouched; see
``docs/07_kinetic_law_assignment.md`` §24 for why no
``KineticLawSpecification`` is constructed in this increment). This is a
narrower reading of this file's own bump criterion than Increment 3 used
(that increment's justification partly cited "a new output-contract
package was introduced" even though the package's types lived outside
``app.agent2.types`` -- here, that broader reading is deliberately not
repeated, since the criterion's own header line scopes
``AGENT2_CONTRACT_VERSION`` to ``app.agent2.types`` shapes specifically).
``AGENT1_HANDOFF_VERSION`` is unchanged at ``"1.2"`` -- Agent 1 was not
modified in this increment (input-only).
``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`` is introduced at
``"kinetic-law-v1"`` for the first real kinetic-law assignment rule set
(curated-reported-law classification, the simple-elementary-transition
structural rule, the Michaelis-Menten and mass-action-fallback
heuristics).

``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`` was bumped from
``"kinetic-law-v1"`` to ``"kinetic-law-v2"`` in the Increment 4 revision
that formalized the tentative mass-action default policy: the narrow,
easily-disqualified ``ENZYMATIC_MECHANISM_UNKNOWN_MASS_ACTION_FALLBACK``
heuristic was replaced by a deliberately broader, always-explicitly-
tentative default (``TENTATIVE_MASS_ACTION_DEFAULT``) that now also fires
when allostery is present, when a reaction has multiple catalytic enzyme
states, or when a reaction is explicitly reversible -- each previously a
hard disqualifier that produced ``UNASSIGNED``. This is a real rule-set
*behavior* change (same inputs can now produce a different assignment),
so the policy version is bumped even though this entire increment remains
uncommitted -- the version marker tracks behavior, not git history.
``AGENT2_CONTRACT_VERSION`` is **not** bumped for this revision: no field
of any type in ``app.agent2.types`` changed shape, and the new
``KineticLawAssignment.is_tentative`` derived property and the
``KineticLawReasonCode`` additions live entirely in
``app.agent2.kinetics``, consistent with this file's already-established
narrower reading (see the entry immediately above). ``AGENT1_HANDOFF_VERSION``
is unchanged -- Agent 1 was not modified.

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.4"`` to ``"0.5"`` in
Increment 5 (Parameter Declaration / Initialization):
``ParameterSpecification`` (``app.agent2.types``) gained one field,
``kinetic_law_assignment_id`` -- the essential missing field found on
inspection (Increment 5 instructions, Step 6): ``reaction_id`` alone
cannot disambiguate a parameter declared for one catalytic context (e.g.
one specific ``EnzymeState``) from a sibling context on the same
reaction, and every parameter Increment 5 declares must trace back to
exactly one ``KineticLawAssignment``. The field has a default (``None``),
so existing keyword-based construction of ``ParameterSpecification`` is
unaffected, but this is a real ``app.agent2.types`` shape change per this
file's own bump criterion -- unlike Increment 4 (which added no field to
any ``app.agent2.types`` type), this increment does. The new
``ParameterDeclarationSet`` type itself lives in
``app.agent2.parameters``, outside ``app.agent2.types``, and so is not
independently a bump reason (consistent with the narrower reading
established for ``app.agent2.kinetics``/``app.agent2.characterization``).
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.
``PARAMETER_DECLARATION_POLICY_VERSION`` is introduced at
``"parameter-declaration-v1"`` for the first real parameter declaration
rule set (kinetic-law-type-to-parameter-slot mapping, the curated-
measurement recognition vocabulary, the multiple-measurement agreement
policy).

``BOUNDARY_POLICY_VERSION`` is **retained** at ``"boundary-v1"`` for
Increment 6 (Heuristic Boundary Assessment) -- not bumped. It was seeded
at that value back in Increment 1, before any boundary-heuristic rule set
existed, specifically so the first real rule set would have somewhere
stable to record its own version from the start (see this file's own
bullet list above). Increment 6 is that first real rule set, so
``"boundary-v1"`` is simply now actually produced by
``app.agent2.boundaries``, exactly as originally anticipated -- not a new
version superseding an old one. ``AGENT2_CONTRACT_VERSION`` is
**unchanged** at ``"0.5"``: inspection found `BoundaryAssessment`/
``BoundaryLikelihood``/``BoundaryParameterBasis`` (``app.agent2.types``)
already complete for this increment's needs (Increment 6 instructions,
Step 34 -- "reuse... do not redesign unless a genuine contradiction
exists"), so no field of any ``app.agent2.types`` type changed shape. The
new ``BoundaryAssessmentSet``/``RuleOutcome``/``RuleDirection``/
``RuleStrength``/``BoundaryReasonCode`` types live entirely in
``app.agent2.boundaries``, outside ``app.agent2.types``, consistent with
the same narrower reading already established for
``app.agent2.kinetics``/``app.agent2.characterization``.
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.

``BOUNDARY_POLICY_VERSION`` was bumped from ``"boundary-v1"`` to
``"boundary-v2"`` in the Increment 6 pre-commit scientific revision that
separated biological modularity from parameterization convenience (see
``docs/09_heuristic_boundary_assessment.md`` §10-11 for the full
rationale). This is a substantial rule-set *behavior* change: three
reason codes (``PARAMETER_SOURCE_DISCONTINUITY``,
``PLACEHOLDER_PARAMETER_REGION``, ``PARAMETERIZATION_CONTINUITY``) were
retired to permanent ``NEUTRAL``; three structural-proxy rules
(``TRANSPORT_INTERFACE``, ``BRANCH_POINT``, ``CONVERGENCE_POINT``) had
their strength ceilings lowered; ``KINETIC_LAW_DISCONTINUITY``'s ceiling
was lowered from ``STRONG`` to ``MODERATE``; ``STRONG_LOCAL_CONTINUITY``
was corrected to no longer treat mutual ``UNASSIGNED`` kinetic-law types
as a shared law; four new functional-modularity rules were added
(``SHARED_RESOURCE_COUPLING``, ``NEGATIVE_FEEDBACK_ISOLATION``,
``FEEDBACK_CROSSING_BOUNDARY``, ``IRREVERSIBLE_OUTPUT_ISOLATION``); three
deferred-principle placeholder rules were added (always ``NEUTRAL``); and
``policy.combine_outcomes``'s ``VERY_HIGH`` condition was redefined to
require at least one ``STRONG`` supporting signal (previously two)
together with no ``MODERATE``-or-stronger opposition. Same inputs can now
produce a different assessment, so the policy version is bumped even
though this entire increment remains uncommitted -- consistent with this
file's own established precedent (the
``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`` ``v1``->``v2`` bump above): the
version marker tracks behavior, not git history.
``AGENT2_CONTRACT_VERSION`` is **not** bumped for this revision: no field
of any ``app.agent2.types`` type changed shape --
``BoundaryAssessment``/``BoundaryLikelihood``/``BoundaryParameterBasis``
remain exactly as Increment 6 originally left them; only the rule catalog
in ``app.agent2.boundaries`` changed. ``AGENT1_HANDOFF_VERSION`` is
unchanged -- Agent 1 was not modified.

``BOUNDARY_POLICY_VERSION`` was bumped from ``"boundary-v2"`` to
``"boundary-v3"`` in the Increment 6 feedback-heuristic revision:
nested feedback loops are ordinary biology, and an intrinsic loop
confined to one side of a candidate interface (what makes that side a
module) is a fundamentally different kind of evidence than an extrinsic
loop crossing the interface (typically module-regulating communication
between two already-independent modules). ``NEGATIVE_FEEDBACK_ISOLATION``
was renamed ``INTRINSIC_FEEDBACK_CONFINEMENT`` and its direction flipped
from support to **oppose** (confined feedback argues for preserving that
side intact, not for cutting at its edge). ``FEEDBACK_CROSSING_BOUNDARY``
was renamed ``EXTRINSIC_FEEDBACK_CROSSING_DEFERRED`` and now always
evaluates ``NEUTRAL`` -- Agent 2 has no dynamic-simulation capability
(loop gain, response time, relaxation time, retroactivity, buffering
strength, condition-dependence) with which to confirm a boundary-crossing
loop is direct, strong, constitutive, local, and minimally regulated, so
it must not infer that judgment. Same inputs can now produce a different
assessment for any candidate touching a curated regulatory interaction,
so the policy version is bumped again even though this entire increment
remains uncommitted -- the version marker tracks behavior, not git
history. ``policy.combine_outcomes`` itself (the categorical decision
table) is **unchanged** by this revision -- only which rules feed it
changed. ``AGENT2_CONTRACT_VERSION`` is **not** bumped: no field of any
``app.agent2.types`` type changed shape; the renamed/redirected rules
live entirely in ``app.agent2.boundaries``. ``AGENT1_HANDOFF_VERSION`` is
unchanged -- Agent 1 was not modified.

``BOUNDARY_POLICY_VERSION`` is **retained at ``"boundary-v3"``** (not
bumped) for the subsequent terminology-only revision that renamed
``INTRINSIC_FEEDBACK_CONFINEMENT``/``intrinsic_feedback_confinement`` to
``INTRINSIC_FEEDBACK_ISOLATION``/``intrinsic_feedback_isolation``
(see ``docs/09_heuristic_boundary_assessment.md`` §24) and added a
heuristic-class taxonomy to that document (§11a). Unlike every prior
``BOUNDARY_POLICY_VERSION`` bump above, there is no behavior to track
here: the deterministic trigger condition, direction (``OPPOSE``), and
strength (``STRONG``) of the renamed rule are byte-identical, and
``policy.combine_outcomes`` was not touched. The only externally-visible
change is that the string ``"INTRINSIC_FEEDBACK_CONFINEMENT"`` no longer
appears in any ``BoundaryAssessment.opposing_reason_codes`` tuple and
``"INTRINSIC_FEEDBACK_ISOLATION"`` appears in its place under the
identical firing condition -- a vocabulary rename, not a policy change.
Per this file's own bump criterion ("bump a constant only when the shape
or policy it names actually changes"), no bump is warranted.
``AGENT2_CONTRACT_VERSION``/``AGENT1_HANDOFF_VERSION`` are unchanged for
the same reasons as the entry above.

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.5"`` to ``"0.6"`` in
Increment 7 (Module Decomposition): ``ModuleSpecification`` gained five
fields (``kinetic_law_assignment_ids``, ``compartment_ids``,
``enzyme_state_ids``, ``interface_species_ids``,
``boundary_interface_ids``), ``ModuleDecomposition`` gained three
(``candidate_boundary_ids``, ``interfaces``, ``explanation``), and a new
type, ``InterModuleBoundaryInterface`` (the pairwise module-to-module
interface record -- deliberately distinct from the pre-existing,
per-species ``ModuleBoundaryInterface``, which remains reserved for a
future standalone-Antimony boundary-condition declaration; see
``docs/10_module_decomposition.md`` §11), was introduced. Every new field
has a default (``()``/``None``), so existing keyword-based construction
of ``ModuleSpecification``/``ModuleDecomposition`` is unaffected, but
``_validate_model_specification_references`` grew new checks for all of
the above -- an output-contract shape change per this file's own bump
criterion. ``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not
modified (input-only).
``MODULE_DECOMPOSITION_POLICY_VERSION`` is introduced at
``"module-decomposition-v1"`` for the first real module-decomposition
rule set (`HIGH`/`VERY_HIGH` boundaries cut, `MEDIUM` preserved as
candidates, `LOW`/`VERY_LOW` never cut, connected-component
partitioning on the remaining graph).

``MODULE_DECOMPOSITION_POLICY_VERSION`` is **retained at
``"module-decomposition-v1"``** (not bumped) for the subsequent
consistency revision that corrected ``InterModuleBoundaryInterface``
creation to only ever consider selected (`HIGH`/`VERY_HIGH`)
``BoundaryAssessment``\\ s -- a retained (`LOW`/`MEDIUM`/`VERY_LOW`)
boundary's own two reactions are unconditionally unioned, so they can
never end up in different final modules, making the prior code's
broader iteration dead/impossible for anything but selected boundaries
(see ``docs/10_module_decomposition.md`` §11/§11a). This produces
byte-identical output to the prior code for every input -- the removed
code path never executed for any real decomposition -- so there is no
behavior to track: same inputs produce the same ``ModuleDecompositionSet``
before and after. Two additional, structurally redundant defensive
validation checks were also added to ``_validate_references`` (an
interface's boundary must have been selected; an interface's endpoints
must actually contain the underlying reactions), which likewise never
reject a previously-accepted decomposition. Per this file's own bump
criterion ("bump a constant only when the shape or policy it names
actually changes"), no bump is warranted; per this revision's own
explicit instruction, the first, still-uncommitted implementation is
simply corrected before release rather than versioned as a behavior
change. ``AGENT2_CONTRACT_VERSION`` is unchanged: no ``app.agent2.types``
shape changed (``InterModuleBoundaryInterface``/``ModuleDecomposition``/
``ModuleSpecification`` retain the exact fields introduced above).
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.

``AGENT2_CONTRACT_VERSION`` is **unchanged** at ``"0.6"`` for Increment 8
(ModelSpecification Assembly): inspection found ``ModelSpecification``/
``KineticLawSpecification``/``ParameterSpecification``/
``ModuleSpecification``/``ModuleDecomposition`` already complete for this
increment's needs (Increment 8 instructions' own "do not redesign
existing contracts unless a genuine contradiction exists"). Two
candidate extensions were considered and deliberately not made: (1)
``KineticLawSpecification`` gained no new field for a materialized law's
catalytic context (``enzyme_state_id``/``protein_id``/``complex_id``) --
each catalytic context already gets its own separate
``KineticLawSpecification`` row (never collapsed), and the context label
itself is fully preserved as provenance text
(``docs/11_model_specification_assembly.md`` §11-12), so a new field was
judged not genuinely required; (2) ``ReactionSpecification`` gained no
``kinetic_law_ids`` field for the one-reaction-to-many-laws case --
``ModelSpecification.kinetic_laws`` is already an unrestricted flat list
keyed by each law's own ``reaction_id``, so nothing prevents more than
one law per reaction today, and ``FullNetwork`` (this increment's
structural authority, never reconstructed) was left completely untouched
(§13-14 of the same document). ``AGENT1_HANDOFF_VERSION`` is unchanged --
Agent 1 was not modified.
``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` is introduced at
``"model-specification-v1"`` for the first real cross-artifact assembly
policy (the ``KineticLawAssignment`` -> ``KineticLawSpecification``
materialization rule and its ``assignment_source`` bridge, the
expression-template policy for built-in law types, and the four
``ModelAssumption`` categories generated deterministically from already-
disclosed incompleteness).

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.6"`` to ``"0.7"`` in an
Increment 8 pre-commit revision that reverses two of the "not genuinely
required" judgment calls in the entry immediately above, once review
found them to be genuine ambiguities a *canonical* contract must not
carry:

1. ``KineticLawSpecification.assignment_source`` changed type from
   ``ParameterSource`` to ``KineticLawAssignmentSource`` (relocated to
   ``app.agent2.types`` from ``app.agent2.kinetics.types`` in the same
   revision, still re-exported there unchanged for every existing
   import). A law's *type* provenance ("why was this rate-law form
   chosen") and a parameter's *value* provenance ("where did this number
   come from") are different questions; the field originally answered
   the wrong one, forcing ``CURATED``/``DEFAULT``/``PLACEHOLDER`` to mean
   two different things depending on context. See
   ``docs/11_model_specification_assembly.md`` §10.
2. ``KineticLawSpecification`` gained three new optional fields,
   ``enzyme_state_id``/``protein_id``/``complex_id`` (identical mutual-
   exclusivity rule to ``KineticLawAssignment``'s own target fields),
   copied verbatim from the source assignment. A materialized law's
   catalytic context was previously disclosed only as ``provenance_refs``
   text -- adequate for a human audit trail, not for a downstream
   consumer (Increment 9) that needs to *resolve* the context
   programmatically without parsing a string. See
   ``docs/11_model_specification_assembly.md`` §11.

Both are genuine public core-contract shape changes (a field's type
changed; three fields were added) per this file's own bump criterion --
unlike the Increment 7 module-decomposition consistency revision, this
one is **not** behavior-preserving: `assemble_model_specification`'s
actual output differs for the same inputs (`assignment_source` values
differ in type entirely; three new fields are now populated). Existing
keyword-based construction of ``KineticLawSpecification`` for the
*unaffected* fields is unaffected, but every existing
``assignment_source=ParameterSource...`` construction site needed
updating (none shipped -- this repository has never committed a
``KineticLawSpecification`` construction). ``AGENT1_HANDOFF_VERSION`` is
unchanged -- Agent 1 was not modified.

A third issue from the same review -- a genuinely multi-substrate
``MICHAELIS_MENTEN`` law receiving a simplified, scientifically-
unjustified combining expression -- was also corrected, but requires no
``app.agent2.types`` shape change (only the *value* the existing
``expression``/``assumptions`` fields carry): see
``docs/11_model_specification_assembly.md`` §8/§16.
``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` was bumped from
``"model-specification-v1"`` to ``"model-specification-v2"`` for the
combined behavior change across all three corrections (the
``assignment_source``/catalytic-context fields now populated
differently, and the multi-substrate Michaelis-Menten expression policy
itself changed) -- the version marker tracks behavior, not git history,
consistent with every prior pre-commit revision in this file.

``AGENT2_CONTRACT_VERSION`` is **retained at ``"0.7"``** (not bumped
again) for a second, final Increment 8 pre-commit revision that corrects
*how* the multi-substrate ``MICHAELIS_MENTEN`` case above is represented.
The entry immediately above already disclosed that case honestly instead
of asserting an unjustified equation, but did so by placing a string
status marker, ``"UNRESOLVED_MULTI_SUBSTRATE_MECHANISM"``, directly in
``KineticLawSpecification.expression`` -- itself a defect, since a field
whose entire meaning is "the concrete algebraic representation" must
never carry a non-expression value, however clearly named. This revision
removes that constant entirely and instead allows ``expression=None`` for
*any* ``law_type``, not only ``UNASSIGNED``: ``kinetic_law_type``
describes the selected law family; ``expression`` is the concrete
algebraic form when known, and is simply absent when the family is known
but the exact algebra is not (see ``docs/04_core_domain_contracts.md`` §8
and ``docs/11_model_specification_assembly.md`` §8a for the full
family-vs-algebra distinction, and §8 for why ``None`` is the correct
representation for this specific case). The unresolved state remains
disclosed exclusively through a dedicated ``ModelAssumption`` (reason
code ``MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED``), never through
``expression`` itself.

Inspection (this revision's own Step 1) found no ``app.agent2.types``
shape change is required: ``KineticLawSpecification.expression`` was
already a plain ``str | None`` field; only its own ``__post_init__``
runtime check (previously: raise if non-``UNASSIGNED`` and blank) was
relaxed, and a new pure derived property, ``has_expression`` (mirroring
``ParameterSpecification.has_value``), was added -- a property is not a
constructor field and does not change how any existing caller constructs
``KineticLawSpecification``. Nothing was added, removed, or retyped, so
per this file's own bump criterion ``AGENT2_CONTRACT_VERSION`` is not
bumped.

``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` is likewise **retained
at ``"model-specification-v2"``** (not bumped to ``"v3"``) for this
revision, by explicit instruction, even though this is a genuine
narrow exception to this file's own general "track behavior, not git
history" convention used for every ``*_POLICY_VERSION`` bump above
(including this same constant's own ``v1``->``v2`` bump two entries
above): ``assemble_model_specification``'s real output for the same
multi-substrate-``MICHAELIS_MENTEN`` inputs does differ before and after
(``expression`` changes from the sentinel string to ``None``; the
generated ``ModelAssumption.reason_code`` is renamed from
``"UNRESOLVED_MULTI_SUBSTRATE_MECHANISM"`` to
``"MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED"``), which would ordinarily
justify a bump under this file's own convention. This revision's own
instructions explicitly called for retaining the version instead,
reasoning that the entire Increment 8 policy has never been committed or
released under either ``"model-specification-v1"`` or
``"model-specification-v2"`` -- no consumer has ever observed the
sentinel-bearing behavior as a released policy version to distinguish
from its replacement, so incorporating the correction cleanly before
release avoids churn that would carry no real information. This is
recorded transparently here specifically because it deviates from
convention: a *future* correction to already-released behavior should
still bump, not treat this entry as license to skip bumps generally.
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.7"`` to ``"0.8"`` in
Increment 9 (Antimony Generation): ``FullAntimonyArtifact`` and
``ModuleAntimonyArtifact`` each gained two fields, ``readiness`` (a new
enum, ``AntimonyArtifactReadiness``) and ``unresolved_kinetic_law_ids``,
plus new ``__post_init__`` cross-field validation tying the two together
and (for ``FullAntimonyArtifact``) forbidding
``AntimonyArtifactReadiness.VIEW_ONLY``. Both new fields have defaults
(``AntimonyArtifactReadiness.EXECUTABLE``/``.VIEW_ONLY`` and ``()``
respectively), so every existing keyword-based construction in
``tests/agent2/test_output_contracts.py`` continues to construct
unchanged -- but this is still an output-contract shape change (new
fields, new validation) per this file's own bump criterion, exactly like
Increment 7's identical situation (new fields, all defaulted, still
counted as a bump). ``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1
was not modified.
``ANTIMONY_GENERATION_POLICY_VERSION`` is introduced at
``"antimony-generation-v1"`` for the first real Antimony-generation
policy (deterministic identifier sanitization/collision resolution
scoped per entity category; closed-vocabulary token substitution for
built-in expression templates, never free-text ``.replace()``; CUSTOM
laws always withheld from executable status, since no structured symbol
mapping exists for opaque curated text; a kinetic law is executable only
when its expression is resolved, every referenced parameter has a
numeric value, and the owning reaction's ``reversible`` flag is not
``None``; no serialization-only placeholder numeric value is ever
invented for a valueless parameter; a module's ``standalone_antimony`` is
generated only when its ``boundary_interfaces`` are explicit, mirroring
the pre-existing ``ModuleAntimonyArtifact`` invariant).

``AGENT2_CONTRACT_VERSION`` was bumped from ``"0.8"`` to ``"0.9"`` in an
Increment 9 pre-commit revision that corrects a modeling-semantic defect
found before this increment's first commit: a biochemical
``ReactionSpecification`` and a catalytic ``KineticLawSpecification``
contribution are not the same thing, but the first Antimony Generation
draft keyed its shared reaction-identifier map by ``kinetic_law_id``,
so a reaction with more than one catalytic-context kinetic law (e.g. one
per enzyme state, never collapsed by Increment 4) was serialized as
*multiple, stoichiometrically identical* Antimony reactions -- silently
asserting simultaneous parallel flux through the same stoichiometry,
which no upstream contract or evidence actually establishes. Corrected
to: one ``ReactionSpecification`` always serializes to exactly one
Antimony reaction; when more than one kinetic law shares a
``reaction_id``, the reaction's rate is marked unresolved
(``MULTIPLE_CATALYTIC_CONTEXTS_COMPOSITION_UNRESOLVED``) rather than
duplicated, summed, or arbitrarily chosen from among them (see
``docs/12_antimony_generation.md`` §11a for the full rationale).
``FullAntimonyArtifact``/``ModuleAntimonyArtifact`` each gained one more
field, ``unresolved_reaction_ids`` (defaulted to ``()``, so every
existing keyword-based construction continues to construct unchanged),
with ``__post_init__`` validation extending the existing
``readiness``/``unresolved_kinetic_law_ids`` cross-checks to also cover
it -- a genuine output-contract shape change per this file's own bump
criterion, independent of the behavior correction itself.
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.

``ANTIMONY_GENERATION_POLICY_VERSION`` is **retained at
``"antimony-generation-v1"``** (not bumped to ``"v2"``) for this same
revision, even though real generated output differs materially for any
``ModelSpecification`` with a multi-context reaction (previously N
stoichiometric reactions with N rates; now one reaction, rate withheld)
-- which would ordinarily justify a bump under this file's own "track
behavior, not git history" convention (the same convention that, for
example, justified ``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION``'s own
``v1``->``v2`` bump). Retained instead because Increment 9 has never been
committed or released under ``"antimony-generation-v1"`` -- no consumer
has ever observed the duplicate-reaction behavior as a released policy
version to distinguish from its correction, so incorporating the fix
cleanly before release avoids version churn that would carry no real
information, consistent with the identical precedent already recorded
above for ``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION``. A *future*
correction to already-released Antimony-generation behavior should still
bump this constant -- this entry is not license to skip bumps generally.

``AGENT1_HANDOFF_VERSION`` was bumped from ``"1.2"`` to ``"1.3"`` for the
"Unresolved Kinetic Evidence Disclosure" increment, motivated by Real
Integration Pilot 2 Run 2: Agent 1's own ``CuratedKineticMeasurement``
gained ``protein_ids`` (``AGENT1_CONTRACT_VERSION`` "1.2" -> "1.3" in the
Agent 1 repository, Increment C.6 -- confirmed live: yeast's real FAS1/FAS2
heterodimer, sharing one EC number, both independently discovering the
identical external source record, a single ``protein_id`` could only ever
record one of them), so this repository's local ``CuratedKineticMeasurement``
was extended to match exactly (see ``docs/02_agent1_handoff_contract.md``).
``AGENT2_CONTRACT_VERSION`` is unchanged, following the identical precedent
recorded above for Increment B's own ``enzyme_state_id`` addition to the
same type: no field of Agent 2's own *output* contracts changed shape;
only the input handoff mirror gained a field (``protein_id`` itself, and
every existing single-protein-context construction, is completely
unaffected -- ``protein_ids`` is derived automatically when omitted).

``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` was bumped from
``"model-specification-v2"`` to ``"model-specification-v3"`` for the same
increment: ``build_model_assumptions`` now also emits one ``ModelAssumption``
(reason code ``KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED``) per
``CuratedKineticMeasurement`` with an unresolved ``reaction_id`` -- a
materially different, observable result for the same real input (Pilot 2
Run 2's own 14 real measurements previously produced zero assumptions
about themselves; the identical input now produces 14, one per
measurement) -- the version marker tracks behavior, not git history,
consistent with this constant's own ``v1``->``v2`` bump above. No core
selector rule changed: reaction-specific kinetic evidence still requires
justified reaction attribution, no measurement is assigned to a reaction
via ``ReactionEnzyme``, spread across a protein's reactions, or given a
real-valued parameter from unresolved-reaction-context evidence.
``AGENT2_CONTRACT_VERSION`` is unchanged -- ``ModelAssumption`` itself
already had an open ``reason_code: str | None`` field; a new value that
field can carry is not a shape change, per this file's own bump criterion
(mirrors the already-recorded precedent for ``"PLACEHOLDER"``/
``"MULTI_SUBSTRATE_MM_EXPRESSION_UNRESOLVED"``, neither of which bumped
this constant either).

``REACTION_CONTEXT_RESOLUTION_POLICY_VERSION`` is introduced at
``"reaction-context-resolution-v1"`` for the "Reaction-Context Resolution
for Kinetic Evidence" increment: a new, standalone rule set
(``app.agent2.kinetics.reaction_context``) that deterministically resolves
a ``CuratedKineticMeasurement.reaction_id`` from ``None`` to exactly one
curated reaction, using only ``compound_id`` identity (never protein
identity, EC number, ``ReactionEnzyme`` membership, pathway membership, or
nearest-name matching) resolved against ``FullNetwork.species[]
.source_compound_id`` and ``ParticipantRole.REACTANT`` participation --
see ``docs/13_kinetic_measurement_reaction_context_resolution.md`` for the
full real-data inspection and matching policy. Only ``KM``/``KI`` are ever
eligible (a hard rule, not derived from which parameter types happen to
carry ``compound_id`` today); ``VMAX``/``KCAT`` are never resolved this
way. This is entirely a new, opt-in pre-processing step over a
``FullNetwork`` -- ``app.agent2.kinetics.selector.assign_kinetic_laws``
and ``app.agent2.parameters.builder`` are completely unmodified and
continue to operate only on measurements that already carry a
``reaction_id``, whether curated originally or resolved by this new step.
``AGENT2_CONTRACT_VERSION`` is unchanged: no field of any
``app.agent2.types`` type changed shape -- ``CuratedKineticMeasurement
.reaction_id``/``.compound_id`` already existed; this increment only adds
a new, separate package that may populate the former from the latter.
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.
``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` is unchanged --
``build_model_assumptions`` itself was not touched; a measurement this new
step resolves to ``UNIQUE_MATCH`` simply no longer matches that function's
own pre-existing ``reaction_id is None`` disclosure condition, exactly as
that condition was already written to handle.

``AGENT1_TRANSLATION_POLICY_VERSION`` is introduced at
``"agent1-translation-v1"`` for the "Agent 1 -> Agent 2 Translation Layer"
increment: a new, committed, deterministic translator
(``app.agent2.handoff.translate_agent1_view_to_agent2``) that replaces the
uncommitted, pilot-only translation scripts (Real Integration Pilot 2 Run
1/Run 2's own scratchpad ``build_handoff``) with production code. Field-
by-field mapping only -- no new biological inference, no name-based or
EC-based matching, no reaction inference. Corrects one real defect found
by comparing the pilot scripts against Agent 1's actual real Run 8 data:
``CuratedKineticMeasurement.protein_id`` is now copied verbatim from
Agent 1's own value, never nulled out when ``protein_ids`` has more than
one entry -- the pilot scripts' own "ambiguous -> None" reasoning did not
match reality (Agent 1's real handoff already reports a resolved, non-
``None`` legacy ``protein_id`` even when ``protein_ids`` has two entries;
only ``protein_ids`` itself was ever missing a field to exist in). Also
confirms, by direct inspection, that Agent 1 does not currently supply a
resolved kinetic ``compound_id`` (its own field name: ``substrate_id``) for
any real measurement -- this translator copies whatever value is present
verbatim and never derives one from a SABIO-RK species label or any other
text field itself; see ``docs/14_agent1_agent2_translation_layer.md`` §7.
``AGENT2_CONTRACT_VERSION`` is unchanged: no field of any
``app.agent2.types`` type changed shape -- the new package lives entirely
in ``app.agent2.handoff``, consistent with this file's own established
narrower reading for every other new package
(``app.agent2.kinetics``/``app.agent2.characterization``/
``app.agent2.kinetics.reaction_context``). ``AGENT1_HANDOFF_VERSION`` is
unchanged -- Agent 1 was not modified.

``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`` was bumped from ``"kinetic-law-v2"``
to ``"kinetic-law-v3"`` for the "Substrate-Anchored Michaelis-Menten
Eligibility Refinement" increment, motivated by Real Integration Pilot 2
Run 3: a real SABIO-RK Km was uniquely, deterministically reaction-
attributed to the real malonyl-CoA:[acp] S-malonyltransferase reaction,
but that reaction has 2 reactants and 2 products, so the pre-existing
single-substrate Michaelis-Menten heuristic
(``ENZYMATIC_SIMPLE_SUBSTRATE_PRODUCT``) never applied and every such
context fell to the tentative mass-action default, whose sole parameter
(a generic rate constant) is never populated from curated evidence by
policy -- the real Km was correctly never fabricated into it, but was
also never used at all.
``app.agent2.kinetics.selector``/``.policy`` gained a new, narrower
eligibility path, consulted only after the existing single-substrate
heuristic has already returned ineligible for the same context: a
multi-reactant reaction now receives ``MICHAELIS_MENTEN`` (reason code
``SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION``) when, and only
when, exactly one curated ``Km`` measurement is unambiguously anchored
(by resolved ``compound_id``) to exactly one of that reaction's own
reactant compounds -- never a product, never two or more candidate
reactants, never two conflicting reports for the same reactant. A
materially different, observable result for the same real input
(before this increment, the real malonyl-CoA reaction's own kinetic-law
assignment was unconditionally the tentative mass-action default) --
the version marker tracks behavior, not git history, consistent with
this constant's own ``v1``->``v2`` bump. No existing eligibility
condition was loosened: every safety check the single-substrate
heuristic already enforces (enzymatic, known catalyst, no allostery, not
curated reversible, at most one catalytic enzyme state) is required
identically here, with only the reactant/product *count* constraint
relaxed -- and only when real, unambiguous evidence justifies it.
``app.agent2.parameters.builder``/``app.agent2.model_specification
.mapping.build_expression_and_species`` were **not modified**: both
already handled an N-reactant ``MICHAELIS_MENTEN`` assignment correctly
(one Km parameter slot per reactant, populated only from a measurement
naming that exact compound; a fabricated combining algebra withheld
whenever more than one reactant participates) -- this refinement only
changes *which* reactions reach that already-correct machinery.
``AGENT2_CONTRACT_VERSION`` is unchanged: no field of any
``app.agent2.types`` type changed shape -- the new reason code lives
entirely in ``app.agent2.kinetics.types.KineticLawReasonCode``,
consistent with this file's own established narrower reading.
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified.

``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` was bumped from
``"model-specification-v3"`` to ``"model-specification-v4"`` for the same
increment: ``build_model_assumptions`` gained one new disclosure block
(the eighth-now-sorted-as-a-distinct category; see that function's own
docstring) that fires specifically for a
``SUBSTRATE_ANCHORED_MM_MULTI_REACTANT_APPROXIMATION`` assignment,
naming the specific anchored reactant compound and source measurement id
-- a materially different, observable result for the same real input
(the real malonyl-CoA reaction's ``ModelSpecification`` now carries one
additional, more specific ``ModelAssumption`` than it did before,
layered alongside the pre-existing, unmodified generic multi-substrate-
expression disclosure). No core selector rule changed: a substrate-
anchored measurement still never fabricates a value for any other
reactant, and no combining algebraic expression is asserted for a
reaction with more than one reactant.

``KINETIC_LAW_ASSIGNMENT_POLICY_VERSION`` was bumped from
``"kinetic-law-v3"`` to ``"kinetic-law-v4"`` for the "Plural Protein
Context Matching for Kinetic Evidence" increment, motivated by Real
Integration Pilot 2 Run 4: the real, uniquely reaction-attributed
malonyl-CoA ``Km`` -- already confirmed eligible for the substrate-
anchored Michaelis-Menten approximation above -- was still silently
excluded from its own reaction's kinetic-law evidence entirely, because
``app.agent2.kinetics.selector._matches_context``/``_is_untagged``
(Increment 4 code, predating Agent 1's own C.6 plural-protein-context
concept) keyed exclusively off ``CuratedKineticMeasurement``'s legacy,
non-authoritative singular ``protein_id`` field. The real reaction's own
two curated catalysts did not include the measurement's own legacy
``protein_id`` (which named a different real protein than either
catalyst), even though the measurement's authoritative ``protein_ids``
already, correctly, named one of them. ``_matches_context`` now checks
**membership** in ``protein_ids`` (never equality against the legacy
field), and ``_is_untagged`` now checks that ``protein_ids`` is empty
(never that the legacy field is ``None``) -- the smallest change that
makes catalytic-context grouping consistent with the authoritative-
plural-context principle Agent 1.x Increment C.6 and this repository's
own "Unresolved Kinetic Evidence Disclosure" increment already
established for every other consumer of this field. A materially
different, observable result for the same real input (the malonyl-CoA
measurement now reaches, and is consumed by, the substrate-anchored
Michaelis-Menten path this file's own ``v2``->``v3`` entry introduced,
where it previously reached no catalytic context's evidence at all) --
the version marker tracks behavior, not git history. Complex/enzyme-
state matching, and every other precedence rule, are unchanged.
``AGENT2_CONTRACT_VERSION`` is unchanged: no field of any
``app.agent2.types`` type changed shape -- ``CuratedKineticMeasurement
.protein_ids`` already existed and was already authoritative (see that
field's own docstring); only this package's own internal, private
matching logic changed. ``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent
1 was not modified.

``ANTIMONY_GENERATION_POLICY_VERSION`` was bumped from
``"antimony-generation-v1"`` to ``"antimony-generation-v2"`` for the
"Conservative Reversibility Default for Unresolved Reactions" increment,
motivated by Real Integration Pilot 2 Run 5: ``app.agent2.antimony
.generator._resolve_law`` no longer requires
``reaction.reversible is not None`` as a precondition for a kinetic
law's own resolution -- an otherwise fully-resolved law/reaction (every
referenced parameter has a numeric value, its expression rendered) now
reaches ``AntimonyArtifactReadiness.EXECUTABLE`` even when Agent 1's own
curated reversibility is unresolved, via the new
``app.agent2.reversibility.effective_reversible`` conservative default
(``None`` -> tentatively reversible, for model-construction purposes
only). A materially different, observable result for the same real
input (the real malonyl-CoA reaction, ``reversible=None``, whose Antimony
artifact previously carried a ``REACTION_REVERSIBILITY_UNRESOLVED``
blocking reason and now instead carries the disclosed, non-blocking
``REACTION_REVERSIBILITY_ASSUMED`` reason) -- the version marker tracks
behavior, not git history. The reaction's own curated ``reversible``
field is never mutated or rewritten; the reversible-vs-irreversible
Antimony comment (``_reversible_comment``) now reads
``"reversible(assumed)"`` specifically for this case, distinguishing it
from genuinely curated ``"reversible"``/``"irreversible"``. No reverse
rate constant, equilibrium constant, or other kinetic parameter is
fabricated by this change: a ``REVERSIBLE_MASS_ACTION`` law with a still-
unresolved ``kr`` remains ``NON_EXECUTABLE_UNRESOLVED_KINETICS``
regardless of reversibility basis, exactly as before.
``AGENT2_CONTRACT_VERSION`` is unchanged: no field of any
``app.agent2.types`` type changed shape. ``AGENT1_HANDOFF_VERSION`` is
unchanged -- Agent 1 was not modified.

``MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION`` was bumped from
``"model-specification-v4"`` to ``"model-specification-v5"`` for the same
increment: ``build_model_assumptions`` gained an eighth disclosure block
(see that function's own docstring) that fires for exactly the reactions
whose curated ``reversible`` is unresolved (``app.agent2.reversibility
.is_assumed``), naming the affected reaction id and stating plainly that
the reaction is modeled as tentatively reversible for model-construction
purposes only, never as curated biochemical fact, and that this
assumption never fabricates a reverse kinetic parameter or contributes
irreversible-output boundary evidence. A materially different, observable
result for the same real input (the real malonyl-CoA reaction's
``ModelSpecification`` now carries one additional ``ModelAssumption``,
reason code ``REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE``, layered
alongside its pre-existing, unmodified disclosures). The new function
parameter (``build_model_assumptions(..., reactions=...)``) lives outside
``app.agent2.types``, defaulted for backward compatibility, consistent
with this file's own established narrower reading: no core assembly
behavior for any other artifact changed, and
``boundaries.rules.irreversible_output_isolation`` -- confirmed by direct
inspection and by new regression tests to already check
``upstream_reversible is False`` specifically -- required no code change
at all.
``AGENT2_CONTRACT_VERSION`` is unchanged for the same reason.
``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not modified; the
underlying curated ``reversible`` value and Agent 1.x Increment C.8's own
evidence policy are untouched.

``PARAMETER_DECLARATION_POLICY_VERSION`` was bumped from
``"parameter-declaration-v1"`` to ``"parameter-declaration-v2"`` for the
Heuristic Simulation Parameter Initialization increment: a real,
observable output change for the same real input -- a parameter slot that
was unconditionally ``PLACEHOLDER`` before this increment (no experimental
evidence, and no prior concept of AI-predicted evidence at all) can now
resolve to ``ParameterSource.AI_PREDICTED`` (a real GotEnzymes2 measurement
Agent 1 already attributed to this exact reaction/context, using its own
canonical ``normalized_value``/``.normalized_unit``, Agent 1.x Increment
C.12) or ``ParameterSource.HEURISTIC_INITIALIZATION`` (a centralized,
documented default, only when no evidence of either kind exists at all).
``initialize_from_evidence`` itself also gained one real behavior change
beyond the new fallback tiers: it now excludes GotEnzymes2-sourced
measurements from its own ``LITERATURE_DERIVED``/``CURATED`` consideration
unconditionally (previously, a GotEnzymes2 measurement with no
``publication_id`` -- true of every real one -- would have been
mislabeled ``CURATED``, since this function had no way to distinguish an
AI-predicted measurement from a genuinely curated experimental one before
Agent 1.x Increment C.11 made such measurements reachable at all). Real,
disagreeing experimental or AI-predicted evidence is never overwritten by
a lower-precedence tier -- only a *genuine, complete absence* of matching
evidence at one tier ever proceeds to the next (see
``app.agent2.parameters.initializer.initialize_with_fallback``'s own
docstring for the full precedence and this specific safeguard).
``HEURISTIC_INITIALIZATION_POLICY_VERSION`` is introduced at
``"heuristic-initialization-v1"`` for the first real heuristic-default
policy (``app.agent2.parameters.heuristic_defaults``): two reference
constants (1 per second; 1000 nM) from which every default -- concentration,
first-order rate, concentration flux, and any mass-action rate constant of
any molecularity via ``[k] = nM^(1-n) * s^-1`` -- is deterministically
derived, never an unexplained magic number chosen independently per
parameter kind. ``AGENT2_CONTRACT_VERSION`` is unchanged: no field of any
``app.agent2.types`` dataclass changed shape -- ``ParameterSource`` gained
two new enum *values* (``AI_PREDICTED``, ``HEURISTIC_INITIALIZATION``),
consistent with this file's own established narrower reading (an enum
value addition is not a data-shape change, exactly as Agent 1's own
``SourceType.GOTENZYMES`` addition did not bump ``AGENT1_CONTRACT_VERSION``
either). ``AGENT1_HANDOFF_VERSION`` is unchanged -- Agent 1 was not
modified by this Agent 2 increment.
"""

from __future__ import annotations

AGENT2_CONTRACT_VERSION = "0.9"
AGENT1_HANDOFF_VERSION = "1.3"
BOUNDARY_POLICY_VERSION = "boundary-v3"
REACTION_CHARACTERIZATION_POLICY_VERSION = "reaction-characterization-v1"
KINETIC_LAW_ASSIGNMENT_POLICY_VERSION = "kinetic-law-v4"
PARAMETER_DECLARATION_POLICY_VERSION = "parameter-declaration-v2"
HEURISTIC_INITIALIZATION_POLICY_VERSION = "heuristic-initialization-v1"
MODULE_DECOMPOSITION_POLICY_VERSION = "module-decomposition-v1"
MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION = "model-specification-v5"
ANTIMONY_GENERATION_POLICY_VERSION = "antimony-generation-v2"
REACTION_CONTEXT_RESOLUTION_POLICY_VERSION = "reaction-context-resolution-v1"
AGENT1_TRANSLATION_POLICY_VERSION = "agent1-translation-v1"

__all__ = [
    "AGENT1_HANDOFF_VERSION",
    "AGENT1_TRANSLATION_POLICY_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "ANTIMONY_GENERATION_POLICY_VERSION",
    "BOUNDARY_POLICY_VERSION",
    "HEURISTIC_INITIALIZATION_POLICY_VERSION",
    "KINETIC_LAW_ASSIGNMENT_POLICY_VERSION",
    "MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION",
    "MODULE_DECOMPOSITION_POLICY_VERSION",
    "PARAMETER_DECLARATION_POLICY_VERSION",
    "REACTION_CHARACTERIZATION_POLICY_VERSION",
    "REACTION_CONTEXT_RESOLUTION_POLICY_VERSION",
]
