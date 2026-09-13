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
  parameter slot, the multiple-measurement agreement policy). Also a
  *behavioral rule set* version, not a data shape.
* ``MODULE_DECOMPOSITION_POLICY_VERSION`` -- the version of the
  deterministic module-decomposition rule set (``app.agent2.modules``) a
  ``ModuleDecompositionSet`` was produced under (e.g. which
  ``BoundaryLikelihood`` values cut vs. become candidates, the
  connected-component partitioning rule). Also a *behavioral rule set*
  version, not a data shape.

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
"""

from __future__ import annotations

AGENT2_CONTRACT_VERSION = "0.6"
AGENT1_HANDOFF_VERSION = "1.2"
BOUNDARY_POLICY_VERSION = "boundary-v3"
REACTION_CHARACTERIZATION_POLICY_VERSION = "reaction-characterization-v1"
KINETIC_LAW_ASSIGNMENT_POLICY_VERSION = "kinetic-law-v2"
PARAMETER_DECLARATION_POLICY_VERSION = "parameter-declaration-v1"
MODULE_DECOMPOSITION_POLICY_VERSION = "module-decomposition-v1"

__all__ = [
    "AGENT1_HANDOFF_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "BOUNDARY_POLICY_VERSION",
    "KINETIC_LAW_ASSIGNMENT_POLICY_VERSION",
    "MODULE_DECOMPOSITION_POLICY_VERSION",
    "PARAMETER_DECLARATION_POLICY_VERSION",
    "REACTION_CHARACTERIZATION_POLICY_VERSION",
]
