# Agent 2 Architecture

## 1. Purpose

Agent 2 transforms curated biochemical knowledge produced by Agent 1 into
valid Antimony model specifications. Agent 2 builds models; it does not
curate literature, validate models in the full Agent 3 sense, simulate or
fit parameters, or critique model biology.

## 2. Position in the multi-agent system

```text
Agent 1 -- Literature Curator      (separate repository: agent1-biochemical-curator)
Agent 2 -- Antimony Builder        (this repository)
Agent 3 -- Validator               (future repository/component)
Agent 4 -- Simulator               (future repository/component)
Agent 5 -- Model Critic            (future repository/component)
```

Agent 2 sits directly downstream of Agent 1 and upstream of Agent 3.

## 3. Inputs

Agent 2's sole input is `Agent1CuratedKnowledgeView` (or an equivalent,
versioned handoff structure) — see
`docs/02_agent1_handoff_contract.md`. Agent 2 never imports Agent 1's
runtime package, database models, or persistence layer, and never calls a
scientific-source connector itself.

## 4. Outputs

* A `FullNetwork` (the complete, assembled biochemical network graph)
* Kinetic-law assignments per reaction
* Parameter declarations/initializations
* Boundary assessments (qualitative likelihoods)
* A `ModuleDecomposition` and its `ModuleSpecification`s
* A `ModelSpecification` (the top-level, authoritative contract)
* A full Antimony model
* Module-specific Antimony outputs (views and, where boundary interfaces
  are explicit, standalone models)

## 5. Canonical workflow

```text
Agent1CuratedKnowledgeView
        ↓
Whole-Network Assembly
        ↓
Full Network Graph
        ↓
Kinetic-Law Assignment
        ↓
Parameter Declaration / Initialization
        ↓
Heuristic Boundary Assessment
        ↓
Module Decomposition
        ↓
ModelSpecification
        ↓
Antimony Generation
        ↓
Agent 3 validation
        ↓
Agent 4 parameter estimation + simulation
        ↘
          feedback
             ↓
Parameter Declaration / Initialization
             ↓
Boundary Reassessment / Module Revision as needed
```

## 6. Full-network-first principle

The complete network must be constructed before module decomposition
begins. Module boundaries are assessed *within* an already-complete
network, never used to justify skipping part of it. No reaction, species,
or compartment present in the curated input is silently dropped because it
does not obviously belong to a module.

## 7. Full Network Graph

The `FullNetwork` is the single authoritative graph of every species,
reaction, compartment, and enzyme association Agent 2 assembled from the
Agent 1 handoff. It is built once, before any kinetic-law assignment or
boundary assessment occurs, and every later structure (kinetic laws,
parameters, boundaries, modules) references it rather than re-deriving a
competing view of the network.

## 8. Kinetic-law assignment

Every reaction in the full network is assigned a kinetic-law structure
before boundary assessment begins — boundary heuristics may consider
kinetic-law structure as a signal (§11), so the assignment must already
exist. Kinetic-law assignment does not estimate parameter values from
experimental data; it only declares the mathematical *form* the reaction's
rate law will take.

## 9. Parameter declaration / initialization

Every kinetic law's parameters are declared and given an initial value
before boundary assessment. "Initialization" is not "fitting": an initial
value may come from a curated measurement, a literature-derived estimate,
a documented default, or an explicit placeholder — never from running a
simulation or calibration (§10, §19).

## 10. Parameter provenance

Every parameter carries a `ParameterSource` (`CURATED`/
`LITERATURE_DERIVED`/`DEFAULT`/`PLACEHOLDER`/`CALIBRATED`) describing
*where its value came from*, not how confident Agent 2 is in it. A
placeholder parameter is never presented as though it were a curated
measurement. `CALIBRATED` is reserved for a value returned by Agent 4's
feedback (§21) — Agent 2 never assigns it to a value it produced itself.

## 11. Boundary assessment

A boundary assessment evaluates one candidate module boundary between two
elements of the full network (§16 of `docs/03_increment_1_specification.md`
lists the concrete contract). It records the shared species and connecting
reactions at that boundary, a qualitative likelihood (§12), the factors
that support and oppose treating it as a real module boundary, reason
codes, an explanation, and — where relevant — the parameter-data basis for
the judgment.

## 12. BoundaryLikelihood vocabulary

```text
VERY_LOW
LOW
MEDIUM
HIGH
VERY_HIGH
```

Exactly these five qualitative values. Never a numeric probability, never
a confidence percentage — a boundary likelihood is a heuristic judgment
produced by explicit, versioned rules (`BOUNDARY_POLICY_VERSION`), not a
statistical estimate.

## 13. Module decomposition

A `ModuleDecomposition` partitions (or otherwise groups) the full
network's elements into `ModuleSpecification`s, built from the boundary
assessments already computed. It is versioned
(`policy_version`) so that a later change to the decomposition heuristic
cannot be silently confused with an earlier decomposition's result.

## 14. Module views vs. standalone modules

* **Module view** — a subset/view of the authoritative full model. Not
  necessarily independently simulatable; it exists to let a reader or
  downstream tool inspect one module without extracting a runnable model.
* **Standalone module model** — an independently simulatable
  representation. Producing one requires explicit
  `ModuleBoundaryInterface` declarations (species, role, direction,
  assumption, whether externally controlled). Agent 2 never invents a
  boundary condition to make a module "simulatable" — if the interface
  cannot be stated explicitly, no standalone model is produced for that
  module.

## 15. ModelSpecification

The top-level, immutable contract Agent 2 produces: it references the full
network's compartments/species/reactions, the kinetic-law and parameter
sets, the boundary assessments, the module decomposition and its module
specifications, plus assumptions and provenance references. It is the
single object from which both the full Antimony model and every module
Antimony output are generated.

## 16. Full Antimony output

The full Antimony model is generated directly from `ModelSpecification`
and is authoritative — it is the canonical representation of the complete
model, and every module output must remain traceable back to it.

## 17. Module Antimony output

For each module, Agent 2 may produce a module view (§14) and, where
boundary interfaces are fully explicit, a standalone module Antimony
model. Both are derived from, and traceable to, the full
`ModelSpecification` and full Antimony model — never generated
independently from a re-derived, competing network.

## 18. Agent 3 boundary

Agent 3 checks mass balance, missing species, duplicate reactions,
disconnected subnetworks, unit consistency, and conservation laws. Agent 2
performs only the minimal syntax/internal-contract checks needed to emit
structurally valid Antimony (e.g. "every referenced species exists in this
model specification") — it does not absorb Agent 3's responsibilities.

## 19. Agent 4 boundary

Agent 4 runs Tellurium/COPASI, parameter scans, sensitivity analyses,
steady-state calculations, and parameter estimation/calibration against
experimental data. Agent 2 never estimates parameters from data and never
simulates a model itself.

## 20. Agent 5 boundary

Agent 5 evaluates biological/model plausibility — thermodynamic
consistency, missing cofactors, ATP participation, experimental support
for regulation. Agent 2 never implements model criticism.

## 21. Feedback from Agent 4

Agent 4 may return calibrated parameter values, uncertainty/confidence
intervals, sensitivity, identifiability, characteristic timescales, and
parameter correlations. Agent 2 may use this feedback to update a
`ParameterSpecification`'s source (to `CALIBRATED`) and initial value, and
to rerun boundary assessment/module decomposition in light of the new
information. Agent 2 never performs the fitting that produced that
feedback.

## 22. Explicit non-goals

Agent 2 must never implement: literature curation, entity normalization,
evidence extraction, claim generation, confidence scoring, knowledge-gap
detection, experiment recommendation, mass-balance/conservation-law
validation, disconnected-subnetwork detection, unit-consistency checking
beyond what is needed to emit valid Antimony, Tellurium/COPASI execution,
parameter scans, sensitivity analysis, steady-state analysis, parameter
estimation/calibration, or model criticism (thermodynamics, cofactor
sufficiency, regulation plausibility).

## 23. Versioning / reproducibility

Three version constants anchor this contract
(`app/agent2/version.py`): `AGENT2_CONTRACT_VERSION` (this repository's own
contract shape), `AGENT1_HANDOFF_VERSION` (the expected Agent 1 handoff
contract version this repository was built against), and
`BOUNDARY_POLICY_VERSION` (the boundary-heuristic rule set version). A
`ModelSpecification`/`ModuleDecomposition` built under one
`BOUNDARY_POLICY_VERSION` is never silently reinterpreted under another.

## 24. Increment roadmap

- Increment 1 — Architecture and Core Contracts (this repository seed)
- Increment 2 — Whole-Network Assembly
- Increment 3 — Kinetic Laws and Parameter Initialization
- Increment 4 — Boundary Assessment and Module Decomposition
- Increment 5 — ModelSpecification and Antimony Generation
- Increment 6 — End-to-End Agent 2 Build / Syntax Contract

## 25. Final architectural rules

> Agent 2 builds the complete network before defining modules.

> Module boundaries are heuristic assessments, not binary truths.

> Parameter fitting belongs to Agent 4; Agent 2 only declares and
> initializes parameters.

> The full model is authoritative; module models are derived and must
> remain traceable to it.

> Agent 2 generates models. It does not curate literature, validate
> biology, simulate, or critique models.
