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
"""

from __future__ import annotations

AGENT2_CONTRACT_VERSION = "0.4"
AGENT1_HANDOFF_VERSION = "1.2"
BOUNDARY_POLICY_VERSION = "boundary-v1"
REACTION_CHARACTERIZATION_POLICY_VERSION = "reaction-characterization-v1"
KINETIC_LAW_ASSIGNMENT_POLICY_VERSION = "kinetic-law-v2"

__all__ = [
    "AGENT1_HANDOFF_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "BOUNDARY_POLICY_VERSION",
    "KINETIC_LAW_ASSIGNMENT_POLICY_VERSION",
    "REACTION_CHARACTERIZATION_POLICY_VERSION",
]
