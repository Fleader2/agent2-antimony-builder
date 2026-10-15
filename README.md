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

> Increment 1 (Architecture and Core Contracts) through Increment 9
> (Antimony Generation) are implemented. See `docs/04_core_domain_contracts.md`,
> `docs/05_whole_network_assembly.md`,
> `docs/06_reaction_enzyme_state_characterization.md`,
> `docs/07_kinetic_law_assignment.md`,
> `docs/08_parameter_declaration_initialization.md`,
> `docs/09_heuristic_boundary_assessment.md`,
> `docs/10_module_decomposition.md`,
> `docs/11_model_specification_assembly.md`, and
> `docs/12_antimony_generation.md`.
>
> **Five-Agent Workflow V1 Hardening increment:** Increment 10
> (End-to-End Agent 2 Build / Syntax Contract) is implemented as
> `app.agent2.pipeline.run_agent2_pipeline` — the one official,
> already-tested entrypoint that chains every increment above in the
> correct order (including the two-pass enzyme-state-dynamics wiring),
> given a serialized Agent 1 handoff. See
> `docs/19_canonical_orchestration_entrypoint.md`, and
> `scripts/run_agent2_pipeline.py` for the CLI wrapper. It emits the one
> canonical downstream contract, `AGENT2_DOWNSTREAM_CONTRACT_VERSION =
> "agent2-downstream-v1"`, consumed unchanged by Agent 3, Agent 4, and
> Agent 5 — see the sibling `five-agent-integration-harness` repository's
> `docs/00_five_agent_workflow_v1_architecture.md` for the full Version 1
> system map (tagged `v1.0.0`).
>
> **Scoped-Build Support increment:** `run_agent2_pipeline` now accepts
> an optional `build_request: app.agent2.build_request.ModelBuildRequest
> | None` parameter — the Workbench's own user build intent, carried
> through the integration harness, never duplicating Agent 1's own
> curated-knowledge contract. Omitting it reproduces this function's
> exact pre-existing behavior with no change whatsoever. See
> `docs/20_scoped_build_support.md` for the full contract, supported/
> unsupported constraints, and cross-repository wiring.
>
> **Antimony Import increment:** Agent 2 now supports a second entry path into the same
> canonical `ModelSpecification`/`FullNetwork` representation — real, live Antimony/SBML
> parsing (`app.agent2.antimony_import.import_antimony`), with new `rules`/`events`/
> `observables`/`source_type`/`source_provenance` fields. `antimony`/`python-libsbml` are
> this repository's first, deliberate runtime dependencies, confined entirely to that one
> package. `generate_antimony` (the existing, unchanged entry point) now also serializes
> rules/events/observables and fixes a reversibility-arrow correctness bug found while
> building the semantic round trip. `agent2-downstream-v1` is unchanged. See
> `docs/21_antimony_import_and_canonical_model.md` for the full design, supported/unsupported
> constructs, and round-trip guarantees.
>
> **Model Modularization increment:** a new, additive, derived layer
> (`ModelModularization`/`ModelModule`/`ModuleMembership`/`ModulePort`) lets any number of
> independent module decompositions coexist on top of the same canonical model — never
> mandatory, never moving a species/reaction/parameter/rule/event/observable out of
> `FullNetwork`/`ModelSpecification`, never altering Antimony export or the downstream
> handoff. Separate from, and never touching, the pre-existing, single-decomposition
> `ModuleSpecification`/`ModuleDecomposition` system. Automatic module discovery
> (topological/functional/dynamic/sensitivity-based) is reserved vocabulary only — not
> implemented. See `docs/22_model_modularization.md` for the full design.
>
> **Human-Readable Antimony Naming and Provenance Separation increment:** generated Antimony
> symbols (compartments/species/reactions/parameters/events/observables) now prefer each
> component's own curated biological name over its raw internal id — a UUID-derived symbol is
> a fallback only, used when no meaningful name is available. Deterministic, collision-safe,
> compartment-aware species disambiguation; a new structured provenance map
> (`AntimonySymbolProvenance`/`build_symbol_provenance_map`, carried on
> `FullAntimonyArtifact.symbol_provenance`) replaces the verbose UUID chains that used to
> crowd reaction-line comments. Imported-model symbols are never renamed. No executable
> semantics or module behavior changed.
>
> This increment also discovered and fixed a real cross-repository contract gap: Agents 3,
> 4, and 5 each independently re-implemented Agent 2's *old* id-only Antimony-symbol
> derivation rule rather than reading it from Agent 2, and silently broke the moment that
> rule changed. Fixed by making Antimony symbol assignment unambiguously Agent-2-owned data
> — `AGENT2_DOWNSTREAM_CONTRACT_VERSION` bumped `"agent2-downstream-v1"` ->
> `"agent2-downstream-v2"`, adding one new field, `antimony_symbol_map`, to
> `build_canonical_downstream_handoff`; every other field is unchanged. Agents 3/4/5 each had
> their own independent re-derivation module removed and now read this field directly — see
> those sibling repositories' own `docs/02_*_contract.md` for the details on their side of
> this change. See `docs/23_human_readable_antimony_naming.md` for the full naming hierarchy,
> collision rules, and verification against the real yeast lipid-biosynthesis model.
>
> **Agent 1 → Agent 2 Biological Display Metadata Contract increment:** Agent 1's handoff
> gained two new, additive fields — `genes`/`proteins` (raw, already-curated `Gene`/`Protein`
> rows) — plus `ec_number` on `CuratedReaction`, bumping `AGENT1_HANDOFF_VERSION` `"1.5"` ->
> `"1.7"`. A reaction's own Antimony symbol now prefers its curated catalyst's gene symbol or
> protein name over its curated name when one is available (e.g. the real yeast acetyl-CoA
> carboxylase reaction, catalyzed by both `ACC1` and `HFA1`, becomes `J_ACC1_HFA1`), falling
> back through EC number / curated name / raw id exactly as before when no catalyst metadata
> is curated. A substrate-specific parameter now also appends its substrate's readable
> compound name (e.g. `Km_ACC1_acetyl_CoA`). `AGENT2_DOWNSTREAM_CONTRACT_VERSION` is
> unchanged (`"agent2-downstream-v2"`) — only the symbol *values* improve, not the downstream
> shape. See `docs/24_biological_display_metadata.md`.
>
> **Explicit Enzyme Concentration Representation increment:** a single-substrate
> Michaelis-Menten rate law no longer silently lumps catalytic enzyme abundance into its own
> `kcat` — a new `app.agent2.enzyme_concentration_species` package materializes one explicit
> catalytic-enzyme species (`source_protein_id` set, named by gene symbol, e.g. `s_ACC1_cytosol`)
> per distinct, resolvable (protein, compartment) catalytic context, drawing on the
> already-resolved `EnzymeConcentration` data the Quantitative Context Resolution increment
> produced but never previously consumed. That expression now renders
> `kcat * E * S / (Km + S)` instead of `kcat * S / (Km + S)` whenever a catalyst resolves,
> tagged `KineticLawRateScope.EXPLICIT_ENZYME_CONCENTRATION`; every other law family
> (mass-action, reversible mass-action, Hill, multi-substrate Michaelis-Menten) stays
> `LUMPED_EFFECTIVE_RATE` for now — single-substrate Michaelis-Menten is simply the first
> kinetic-law family for which Agent 2 currently performs this decomposition, a current
> implementation limitation rather than a permanent scientific restriction (this codebase has
> no real decomposition basis for those other rate constants *today*; see
> `docs/25_explicit_enzyme_concentration_representation.md` §9 for the extensions this leaves
> for later work). An enzyme with known identity but unresolved concentration still gets an explicit
> species, with no fabricated numeric value. `AGENT2_CONTRACT_VERSION` bumped `"0.13"` ->
> `"0.14"`; `AGENT2_DOWNSTREAM_CONTRACT_VERSION` bumped `"agent2-downstream-v2"` ->
> `"agent2-downstream-v3"` (two purely additive downstream fields — Agents 3/4/5 synced their
> own identical version constants in step). See
> `docs/25_explicit_enzyme_concentration_representation.md`.
>
> **Module Decomposition/Modularization Reconciliation increment:** the old, GENERATED-only,
> build-time `ModuleSpecification`/`ModuleDecomposition`/`BoundaryAssessment` system
> (Increments 1/6/7) is reconciled with the newer, origin-agnostic Model Modularization layer
> (`ModelModularization`/`ModelModule`/`ModuleMembership`/`ModulePort`) into one, unified,
> stored representation for a model of either source type. `ModelSpecification` lost
> `boundary_assessments`/`module_decomposition`/`module_specifications` entirely (confirmed
> zero downstream consumers); the old heuristic boundary/connected-component algorithm is
> unchanged and still runs by default for a `GENERATED` build, but its output is now converted
> into the unified representation instead. Modularization is never mandatory (zero, one, or
> many may coexist on the same model, none marked canonical), and a new, explicit, opt-in
> `app.agent2.antimony.generate_module_artifacts(model, modularization_id)` is the one entry
> point for module-view/standalone-submodel Antimony generation — reusing the old rendering
> machinery rather than duplicating it, and working identically for a `GENERATED` or
> `IMPORTED` model. `AGENT2_CONTRACT_VERSION` bumped `"0.14"` -> `"0.15"`;
> `AGENT2_DOWNSTREAM_CONTRACT_VERSION` is unchanged — modules/boundaries were never part of
> that contract. See
> `docs/26_module_decomposition_modularization_reconciliation.md`.
>
> **Module Boundary Evaluation Framework increment:** scores an existing modularization
> against multiple, independently-inspectable evidence criteria rather than defining
> modularity by one mechanism such as topology — "module mechanisms are evidence;
> functional/contextual independence is the eventual target property." New package
> `app.agent2.module_evaluation` implements four criteria from Agent 2/canonical-model
> information alone (topological separation, boundary sparsity, compartment coherence, and
> an EC-number-class-coherence criterion — originally misnamed "pathway annotation
> coherence," corrected in a later increment below), each always computed and reported
> regardless of weight; six more (genuine pathway/network membership, Agent 3 dynamic
> isolation, sensitivity coherence, Agent 4 calibration independence, regulatory coherence,
> Agent 5 experimental validation) are reserved vocabulary for future increments.
> `CriteriaWeights` is explicit,
> user/configuration-supplied, and deterministically normalized (zero weight disables a
> criterion). `evaluate_modularization` never fabricates a score for unavailable evidence,
> `evaluate_modularization_under_weights`/`compare_modularizations` support weight-space
> exploration and multi-modularization comparison — neither ever picks a winner. Works
> identically for a `GENERATED` or `IMPORTED` model; alters no executable whole-network or
> standalone-module-generation behavior, and no version constant other than the new
> `MODULE_EVALUATION_POLICY_VERSION` changes. See
> `docs/27_module_boundary_evaluation_framework.md`.
>
> **Topology Hub/Currency Component Filtering increment:** prevents ubiquitous components
> (ATP/ADP, water, protons, phosphate, common cofactors) from artificially destroying the
> `TOPOLOGICAL_SEPARATION` criterion's own score. A new `TopologyRole` vocabulary
> (`NORMAL`/`UNIVERSAL_CURRENCY`/`COFACTOR`/`GENERIC_ADAPTOR`/`HIGH_DEGREE_HUB`/
> `USER_EXCLUDED`) resolves each species' own filtering weight — curated name-based defaults
> first (currency metabolites hard-excluded, common cofactors down-weighted), an explicit,
> per-evaluation `TopologyRoleOverride` always taking final precedence (so e.g. 14-3-3 can be
> down-weighted in one signaling model but treated as central in another). Degree-based hub
> detection only ever flags a candidate for disclosure — never auto-excludes it. Both the raw
> (unfiltered) and filtered scores are always reported, together with exactly which
> components were filtered and why; the filtered score alone feeds the weighted evaluation.
> Verified on the real yeast organism: default filtering raises `TOPOLOGICAL_SEPARATION` from
> `0.236` to `0.419`. Affects only `TOPOLOGICAL_SEPARATION`'s own internal computation — no
> version constant changes at all. See
> `docs/28_topology_hub_currency_component_filtering.md`.
>
> **`EC_CLASS_COHERENCE` naming correction:** the criterion the two increments above named
> `PATHWAY_ANNOTATION_COHERENCE` never read genuine pathway/network-membership data — it only
> ever matched curated EC-number top-level classes. Renamed `EC_CLASS_COHERENCE` (scoring
> formula and behavior byte-for-byte unchanged); `PATHWAY_ANNOTATION_COHERENCE` is re-declared
> as a genuinely reserved, unimplemented criterion for the real pathway-membership signal
> (Agent 1's own curated KEGG `CuratedNetwork`/pathway data, still not wired into Agent 2), so
> a future increment implementing it needs no further conceptual rename. No version constant
> changes. See `docs/29_ec_class_coherence_naming_correction.md`.
>
> **Weight-Space Exploration and Stable Boundary Discovery increment:** builds on the
> unchanged Module Boundary Evaluation Framework to systematically explore combinations of
> modularization-criterion weights and identify module boundaries/modularizations that remain
> stable across reasonable weighting assumptions. New package
> `app.agent2.weight_space_exploration` deterministically expands a `WeightGridSpec` into every
> legal `CriteriaWeights` combination (`generate_weight_vectors`/`uniform_weight_grid`),
> evaluates every `(modularization_id, weight_vector)` pair (`explore_weight_space`, reusing
> `evaluate_modularization` unchanged), selects the high-scoring subset under an explicit
> `HighScoringSolutionPolicy` (`TOP_N`/`PERCENTILE`/`WITHIN_DELTA_OF_BEST`), and derives
> boundary-recurrence, module-co-membership, and modularization-recurrence stability measures
> over that subset — never forcing an unstable solution into a single consensus, never
> declaring one solution "correct." Results are preserved separately per modularization and
> module count. No existing type's stored shape changes; no version constant changes other than
> the new `WEIGHT_SPACE_EXPLORATION_POLICY_VERSION`. See
> `docs/30_weight_space_exploration_and_stable_boundary_discovery.md`.

## Roadmap

- **Increment 1** — Architecture and Core Contracts (implemented)
- **Increment 2** — Whole-Network Assembly (implemented)
- **Increment 3** — Reaction and Enzyme-State Characterization (implemented)
- **Increment 4** — Kinetic-Law Assignment (implemented)
- **Increment 5** — Parameter Declaration / Initialization (implemented)
- **Increment 6** — Heuristic Boundary Assessment (implemented)
- **Increment 7** — Module Decomposition (implemented)
- **Increment 8** — ModelSpecification Assembly (implemented)
- **Increment 9** — Antimony Generation (implemented)
- **Increment 10** — End-to-End Agent 2 Build / Syntax Contract (implemented, as `run_agent2_pipeline`)
- **Scoped-Build Support** — Workbench `ModelBuildRequest` → Agent 2 scoped builds (implemented)
- **Antimony Import** — real Antimony/SBML parsing into the canonical representation, with semantic round-trip (implemented)
- **Model Modularization** — a derived, additive, multi-decomposition module layer on top of the canonical model (implemented)
- **Human-Readable Antimony Naming and Provenance Separation** — curated-name-based Antimony symbols, deterministic collision resolution, and a structured symbol-provenance map (implemented)
- **Agent 1 → Agent 2 Biological Display Metadata Contract** — curated gene symbol/protein name/EC number naming tiers for reactions and parameters (implemented)
- **Explicit Enzyme Concentration Representation in Kinetic Models** — explicit catalytic-enzyme species, injected into single-substrate Michaelis-Menten rate expressions (implemented)
- **Module Decomposition/Modularization Reconciliation** — the old build-time module-decomposition system and the newer general model-modularization system unified into one, origin-agnostic representation, with executable-submodel export reusing the old rendering machinery (implemented)
- **Module Boundary Evaluation Framework** — multi-criteria, explicitly-weighted scoring of a candidate modularization, with extension points for future Agent 3/4/5-driven criteria (implemented)
- **Topology Hub/Currency Component Filtering** — curated-role-based, context-overridable filtering of ubiquitous currency/cofactor species out of the topology-separation criterion (implemented)
- **`EC_CLASS_COHERENCE` Naming Correction** — renamed the misnamed `PATHWAY_ANNOTATION_COHERENCE` criterion to accurately reflect its EC-number-class basis, and reserved the original name for genuine future pathway-membership scoring (implemented)
- **Weight-Space Exploration and Stable Boundary Discovery** — deterministic weight-grid sampling, multi-candidate-modularization evaluation, and boundary/co-membership/modularization-recurrence stability measures over the high-scoring solution set (implemented)

This roadmap describes implemented scope; Version 2 planning is tracked
separately and has not begun.

---

## Documentation

- `docs/01_agent2_architecture.md` — full Agent 2 architecture
- `docs/02_agent1_handoff_contract.md` — the Agent 1 → Agent 2 data contract
- `docs/03_increment_1_specification.md` — Increment 1's historical specification (implemented)
- `docs/04_core_domain_contracts.md` — the canonical, current-state domain contract reference
- `docs/05_whole_network_assembly.md` — Increment 2 (Whole-Network Assembly), implemented
- `docs/06_reaction_enzyme_state_characterization.md` — Increment 3 (Reaction and Enzyme-State Characterization), implemented
- `docs/07_kinetic_law_assignment.md` — Increment 4 (Kinetic-Law Assignment), implemented
- `docs/08_parameter_declaration_initialization.md` — Increment 5 (Parameter Declaration / Initialization), implemented
- `docs/09_heuristic_boundary_assessment.md` — Increment 6 (Heuristic Boundary Assessment), implemented
- `docs/10_module_decomposition.md` — Increment 7 (Module Decomposition), implemented
- `docs/11_model_specification_assembly.md` — Increment 8 (ModelSpecification Assembly), implemented
- `docs/12_antimony_generation.md` — Increment 9 (Antimony Generation), implemented
- `docs/19_canonical_orchestration_entrypoint.md` — Increment 10, the canonical `run_agent2_pipeline` entrypoint and downstream contract, implemented
- `docs/20_scoped_build_support.md` — Scoped-Build Support increment: the Workbench `ModelBuildRequest` → Agent 2 contract, ownership boundary, supported/unsupported constraints, and cross-repository wiring, implemented
- `docs/21_antimony_import_and_canonical_model.md` — Antimony Import increment: the canonical model schema additions, import/export flow, supported/unsupported constructs, and semantic round-trip guarantees, implemented
- `docs/22_model_modularization.md` — Model Modularization increment: the modularization schema, shared-species/cross-module-connection behavior, multiple-decomposition support, and the Antimony/downstream-handoff compatibility guarantee, implemented
- `docs/23_human_readable_antimony_naming.md` — Human-Readable Antimony Naming and Provenance Separation increment: the naming hierarchy, collision rules, provenance-map design, generated-vs-imported naming behavior, and fallback behavior, implemented
- `docs/24_biological_display_metadata.md` — Agent 1 → Agent 2 Biological Display Metadata Contract increment: the new gene/protein/EC-number handoff fields, the ownership boundary, the extended reaction/parameter naming preference order, and fallback behavior, implemented
- `docs/25_explicit_enzyme_concentration_representation.md` — Explicit Enzyme Concentration Representation increment: the new enzyme-concentration species package, the single-substrate Michaelis-Menten injection scope and its scientific justification, naming, contract/version changes, and the real-data regression, implemented
- `docs/26_module_decomposition_modularization_reconciliation.md` — Module Decomposition/Modularization Reconciliation increment: which old types were retained/adapted/removed, the adapter, the unified standalone-submodel export entry point, GENERATED/IMPORTED symmetry, and contract/version changes, implemented
- `docs/27_module_boundary_evaluation_framework.md` — Module Boundary Evaluation Framework increment: the scientific principle, the four implemented criteria, missing-evidence/weighting policy, weight-space exploration, GENERATED/IMPORTED symmetry, and extension points for future Agent 3/4/5 criteria, implemented
- `docs/28_topology_hub_currency_component_filtering.md` — Topology Hub/Currency Component Filtering increment: the TopologyRole vocabulary, default filtering policy, curated/context override precedence, hub-flagging-never-auto-excludes behavior, raw-vs-filtered reporting, and the real-data before/after example, implemented
- `docs/29_ec_class_coherence_naming_correction.md` — `EC_CLASS_COHERENCE` Naming Correction increment: why `PATHWAY_ANNOTATION_COHERENCE` was renamed, confirmation that scoring behavior/weighting/symmetry/downstream contracts are all unchanged, and how genuine pathway coherence is now reserved for future implementation, implemented
- `docs/30_weight_space_exploration_and_stable_boundary_discovery.md` — Weight-Space Exploration and Stable Boundary Discovery increment: the weight-grid/high-scoring-solution-policy API, boundary/co-membership/modularization-recurrence stability definitions, module-count handling, recursive-readiness design, and example results, implemented

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
