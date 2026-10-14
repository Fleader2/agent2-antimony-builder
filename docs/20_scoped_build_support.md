# Scoped-Build Support

## 1. Purpose

This document is the canonical record of the **Workbench `ModelBuildRequest`
-> Agent 2 scoped-build** increment: how a user's build intent, captured in
the separate `mechanistic-modeling-workbench` repository, can now constrain
what Agent 2 actually builds, without moving scientific ownership out of
Agents 1-2 or breaking the existing five-agent contract architecture.

## 2. Ownership boundary (unchanged by this increment)

* **Agent 1** (`agent1-biochemical-curator`) owns biological identity and
  normalization. It is not touched by this increment at all -- Agent 1 has
  no concept of a build request and never will.
* **Workbench** (`mechanistic-modeling-workbench`) owns user build intent --
  the persisted `ModelBuildRequest` and its eight child tables. It never
  decides what a constraint *means* biologically, never resolves a raw
  identifier itself, and never copies Agent 2's executable model content
  into its own database. It only serializes what the user asked for and
  stores the warnings it gets back.
* **Integration Harness** (`agent-integration-harness`) forwards a
  `ModelBuildRequest` artifact's own file path, unread, from the Workbench
  to Agent 2's own runner, and promotes Agent 2's own reported warnings
  into its result contract. It never parses the artifact's content or
  applies any scoping itself.
* **Agent 2** (`agent2-antimony-builder`, this repository) owns executable
  model construction, including -- new in this increment -- the entire
  decision of what a `ModelBuildRequest` means for its own assembled
  network: resolution against curated identity, contradiction detection,
  and scope filtering. This is the **only** repository that contains any
  new logic from this increment.

No pathway-discovery or curation logic was added anywhere. Agent 2 still
never invents a biological mapping for an identifier it cannot resolve.

## 3. The final contract shape

`app.agent2.build_request` (this repository):

```python
class ModelBuildRequest:
    contract_version: str                              # "agent2-build-request-v1"
    model_build_request_id: str
    species: tuple[EntityReference, ...] = ()           # role: INPUT/OUTPUT/BOUNDARY/SEED
    reactions: tuple[EntityReference, ...] = ()         # role: SEED/REQUIRED/EXCLUDED
    gene_proteins: tuple[EntityReference, ...] = ()     # role: SEED/IMPORTANT
    compartments: tuple[EntityReference, ...] = ()      # no role
    regulatory_interactions: tuple[EntityReference, ...] = ()  # no role
    enzyme_states: tuple[EntityReference, ...] = ()     # no role
    pathways: tuple[PathwayReference, ...] = ()         # role: INCLUDE/EXCLUDE
    assumptions: tuple[str, ...] = ()

class EntityReference:
    role: str | None
    agent1_entity_type: str | None
    agent1_entity_id: str | None
    raw_identifier: str | None

class PathwayReference:
    role: str
    external_pathway_id: str | None
    name: str | None
```

This covers every field the originating task asked for at minimum (start/
input species, end/output species, seed reactions, seed genes/proteins,
seed metabolites, required reactions, excluded reactions, boundary
species, compartments, localization constraints*, important genes/
proteins, required regulatory interactions, required PTM/enzyme states,
included/excluded pathway scope, unresolved raw identifiers, user
assumptions) without duplicating `Agent1CuratedKnowledgeViewContract`.

*Localization constraints are carried by the Workbench's own
`ModelBuildRequestGeneProtein.localization_entity_id`/
`localization_raw_identifier` columns, serialized onto the same
`gene_proteins` entries as `EntityReference.localization_entity_id`/
`localization_raw_identifier` -- Agent 2's scoping engine does not act
on them structurally; a `gene_proteins` reference naming one produces a
disclosed `UNSUPPORTED_LOCALIZATION_CONSTRAINT` warning instead (see
§6).

Deliberately named `ModelBuildRequest` on both sides of the Workbench
boundary, matching the Workbench's own name exactly -- the Workbench
chose that name specifically to avoid colliding with this repository's
own, unrelated, pre-existing `ModelSpecification` (the complete assembled
executable model). The two are never confused: this package never
imports `app.agent2.types.ModelSpecification`, and nothing in
`app.agent2.types` was renamed or altered by this increment.

`AGENT2_BUILD_REQUEST_CONTRACT_VERSION` (`"agent2-build-request-v1"`) is
this contract's own version, independent of `AGENT2_CONTRACT_VERSION`,
`AGENT2_DOWNSTREAM_CONTRACT_VERSION`, and the Workbench/harness's own
`WORKBENCH_HARNESS_CONTRACT_VERSION`/`CONTRACT_VERSION`. It is checked by
`build_request_from_dict` against any artifact it parses -- a mismatch
raises `BuildRequestContractVersionError` before anything else runs.

## 4. How it reaches Agent 2

```
Workbench                          Harness                      Agent 2
----------                         --------                     -------
ModelBuildRequest (DB)
  -> model_build_request_to_dict()
  -> write temp JSON file
  -> input_artifact_references
     ["model_build_request"] = path  ---->  forwarded unread  ---->  --build-request <path>
                                                                      -> build_request_from_dict()
                                                                      -> apply_build_request_scope()
                                                                      -> run_agent2_pipeline(..., build_request=...)
warnings <---- promoted into  <----  agent2_build_request_warning=<text>  <----  printed to stdout
RunRecord.warnings                   WorkbenchRunResult.warnings
```

See `agent-integration-harness/docs/07_workbench_harness_contract.md` and
`mechanistic-modeling-workbench/docs/03_workbench_harness_contract.md`
for each repository's own side of this wiring.

## 5. Supported constraints

* **Required/excluded reactions** -- always honored exactly: a required
  reaction is never pruned; an excluded one is always removed (unless
  also required, which is rejected as a contradiction, §7).
* **Seed/start/end/boundary species** -- any reaction touching a resolved
  species (by curated compound id) is included in the retained scope.
* **Seed/important genes and proteins** -- any reaction catalyzed by a
  resolved protein/complex id is included in the retained scope.
* **Compartments to include** -- restricts the retained scope to
  reactions whose every participant lies in an included compartment,
  except a required/seed reaction, which is exempt from this filter
  (explicit task requirement: "include required entities even when they
  would otherwise be pruned").
* **No inclusion constraint supplied at all** -- the network is returned
  unscoped (minus any excluded reactions), reproducing pre-existing
  behavior exactly.
* **User assumptions** -- preserved verbatim as free text; never
  machine-interpreted (consistent with every other free-text assumption
  field already in `app.agent2.types`).

## 6. Unsupported constraints (disclosed, not silently ignored)

* **Pathway include/exclude scope** -- `FullNetwork` carries no
  pathway-membership field on any reaction (confirmed by inspection:
  neither `CuratedReaction` nor `ReactionSpecification` has one).
  Enforcing it would require either inventing a mapping Agent 1 does not
  curate, or new pathway-discovery logic -- both explicitly out of scope.
  A non-empty `pathways` list always produces a disclosed
  `UNSUPPORTED_PATHWAY_SCOPE` warning.
* **Required regulatory interactions / PTM-enzyme states** -- these are
  "supporting data" on `FullNetwork`, never structurally filtered (in the
  unscoped case or this one); a reference that does not resolve against
  the network produces an `UNRESOLVED_*_REFERENCE` warning, but no
  structural filtering is performed based on them.
* **Localization constraints** -- carried through the contract (§3), but
  no curated entity anywhere in `FullNetwork` has a subcellular
  localization attribute to filter against. A `gene_proteins` reference
  naming `localization_entity_id`/`localization_raw_identifier` always
  produces a disclosed `UNSUPPORTED_LOCALIZATION_CONSTRAINT` warning.

## 7. Unresolved-identifier and conflict behavior

* A reference with an `agent1_entity_id` that does not match anything in
  the assembled network produces an `UNRESOLVED_*_REFERENCE` warning --
  never silently dropped, never guessed.
* A reference with only a `raw_identifier` (no resolved
  `agent1_entity_id`) always produces an `UNRESOLVED_RAW_IDENTIFIER`
  warning. Agent 2 never guesses a biological mapping from raw user text;
  a later Agent 1 resolution pass is what should resolve it.
* The same reaction named both `REQUIRED` and `EXCLUDED` raises
  `BuildRequestContradictionError` deterministically, before any scoping
  or later pipeline stage runs.
* A `ModelBuildRequest` whose own constraints resolve to zero retained
  reactions raises `BuildRequestEmptyScopeError` -- rejected rather than
  silently falling back to the unscoped network or an empty one no later
  Agent 2 stage (characterization, kinetic-law assignment, module
  decomposition, ...) is designed to handle.
* Both error types subclass `BuildRequestError` (itself a `ValueError`),
  consistent with every other `app.agent2` error hierarchy.

## 8. Backward compatibility

* `run_agent2_pipeline(agent1_handoff, build_request=None)` -- the new
  parameter defaults to `None` and reproduces the function's exact
  pre-existing behavior with no change whatsoever when omitted. Verified
  by `tests/agent2/test_pipeline.py
  ::test_no_build_request_reproduces_pre_existing_behavior_exactly`.
* `Agent2PipelineResult` gained one new field, `warnings: tuple[str,
  ...] = ()`, with a default -- every existing construction/comparison
  continues to work unchanged.
* `build_canonical_downstream_handoff`'s own dict shape is **unchanged**:
  `warnings` is never added to it. Agents 3, 4, and 5 continue to consume
  the identical, fixed downstream-handoff shape they always have.
* The harness's `input_artifact_references` was already an open
  `{name: path}` dict; recognizing one more key
  (`"model_build_request"`) required no `WORKBENCH_HARNESS_CONTRACT_VERSION`
  bump -- a request that never sets this key is unaffected byte-for-byte.
* `runners/run_agent2.py --build-request` is optional; omitting it issues
  the identical subprocess invocation this script always has.

## 9. Testing

* `tests/agent2/test_build_request_scope.py` -- unit tests for every
  scoping behavior in §5-7, against a real `FullNetwork` built by the
  real `assemble_full_network`.
* `tests/agent2/test_pipeline.py` -- integration tests proving
  `run_agent2_pipeline`'s backward compatibility, scoping-before-later-
  stages behavior, contradiction propagation, warning surfacing, and
  determinism.
* `agent-integration-harness/tests/harness/test_scoped_build_workflow.py`
  -- a real, live, subprocess-level `run_workflow` call (no mocks) using
  the harness's own synthetic ground-truth fixture, scoped to two of its
  three reactions.
* `agent-integration-harness/tests/harness/test_workbench_contracts.py`
  -- real, end-to-end canonical-entrypoint subprocess tests for both the
  "id without artifact" disclosed-warning path and the "artifact present"
  real-scoped-run path.
* `mechanistic-modeling-workbench/tests/orchestration
  /test_run_orchestrator.py::test_real_scoped_build_run_persists_model_build_request_id_and_warnings`
  -- a real, end-to-end `submit_subproject_run` call (no mocks) through
  the real harness into a real Agent 2 subprocess, proving the full
  Workbench -> Harness -> Agent 2 -> Workbench round trip.

## 10. What this increment explicitly did not do

* No new pathway-discovery or curation logic in Agent 2.
* No UI work.
* No simulation/calibration behavior changes (Agents 3-5 untouched).
* No change to Agent 1's scientific scope (Agent 1 untouched).
* No automatic model modularization.
* No change to `app.agent2.types.ModelSpecification`'s own meaning.
