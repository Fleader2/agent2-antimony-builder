# Agent 2 — Antimony Builder

## Overview

Agent 2 is the second component of a multi-agent system for constructing scientifically traceable, mechanistic models of microbial metabolism.

Agent 2 consumes curated biochemical knowledge produced by **Agent 1 — Literature Curator** (a separate repository, `agent1-biochemical-curator`) and transforms it into valid **Antimony** model specifications.

Agent 2 does **not**:

- curate literature or biological database records (that is Agent 1's job),
- validate a built model's mass balance, unit consistency, or conservation laws in the full sense Agent 3 does (Agent 2 performs only minimal syntax/internal-contract checks needed to emit valid Antimony),
- simulate a model or fit parameters against experimental data (that is Agent 4's job),
- critique a model's biological plausibility — thermodynamics, missing cofactors, unsupported regulation (that is Agent 5's job).

Agent 1 is complete and frozen at its own boundary
(`agent1-biochemical-curator/docs/23_agent1_v1_scope_and_completion.md`).
Agent 2 consumes Agent 1's output through an explicit, versioned handoff
contract — it never imports Agent 1's runtime code.

---

## Canonical Workflow

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

**The complete network must be constructed before module decomposition.**
Module boundaries are heuristic judgments, not architectural or biological
truths, and may depend on topology, compartments, biochemical continuity,
kinetic-law structure, regulation, parameter magnitudes, characteristic
timescales, parameter provenance, and later Agent 4 calibration results.

## Module Decomposition and Boundary Likelihood

Every candidate module boundary is assessed with a **qualitative
likelihood** — `VERY_LOW` / `LOW` / `MEDIUM` / `HIGH` / `VERY_HIGH` — never
a fabricated numeric probability. Each assessment records its supporting
factors, opposing factors, reason codes, and an explanation.

## Full Model vs. Module Outputs

The full network and full Antimony model are **authoritative**. Module
models are **derived** representations that must remain traceable back to
the full model. Agent 2 produces both:

1. A **full Antimony model** — the canonical, complete representation.
2. **Module-specific Antimony outputs** — either a *module view* (a subset
   of the full model, not necessarily independently simulatable) or a
   *standalone module model* (independently simulatable only when explicit
   boundary-interface assumptions are declared — Agent 2 never invents a
   boundary condition silently).

## Agent 4 Feedback

Agent 4 may return calibrated parameter values, uncertainty/confidence
intervals, sensitivity, identifiability, and characteristic timescales.
Agent 2 may use that feedback to update parameter initialization/status
and to reassess module boundaries — but Agent 2 never performs the fitting
itself.

---

## Current Status

> Repository initialized; implementation begins with Increment 1.

## Roadmap

- **Increment 1** — Architecture and Core Contracts
- **Increment 2** — Whole-Network Assembly
- **Increment 3** — Kinetic Laws and Parameter Initialization
- **Increment 4** — Boundary Assessment and Module Decomposition
- **Increment 5** — ModelSpecification and Antimony Generation
- **Increment 6** — End-to-End Agent 2 Build / Syntax Contract

This roadmap describes planned scope, not a commitment to a fixed
timeline or final design for increments beyond the next one.

---

## Documentation

- `docs/01_agent2_architecture.md` — full Agent 2 architecture
- `docs/02_agent1_handoff_contract.md` — the Agent 1 → Agent 2 data contract
- `docs/03_increment_1_specification.md` — the next implementation increment

## Repository Structure

```text
agent2-antimony-builder/
├── README.md
├── CONTRIBUTING.md
├── pyproject.toml
├── docs/
├── app/
│   └── agent2/
├── tests/
│   └── agent2/
└── .cursor/
    └── rules/
```
