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
"""

from __future__ import annotations

AGENT2_CONTRACT_VERSION = "0.3"
AGENT1_HANDOFF_VERSION = "1.2"
BOUNDARY_POLICY_VERSION = "boundary-v1"

__all__ = [
    "AGENT1_HANDOFF_VERSION",
    "AGENT2_CONTRACT_VERSION",
    "BOUNDARY_POLICY_VERSION",
]
