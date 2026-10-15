# Topology Hub/Currency Component Filtering for Module Evaluation

## 1. Goal and scope

`TOPOLOGICAL_SEPARATION` (`docs/27_module_boundary_evaluation_framework.md` §4) builds its
own derived reaction-adjacency graph from `FullNetwork` alone: two reactions are "adjacent"
whenever they share at least one species. That document's own disclosed limitation was that
this simplest-possible rule does not special-case ubiquitous "currency" metabolites (ATP,
water, CoA, ...), which can make a real metabolic network's own adjacency graph far denser --
and the resulting score correspondingly lower -- than the network's true pathway structure
would suggest. This increment closes that gap, for `TOPOLOGICAL_SEPARATION` alone.

**The canonical model is never altered.** Filtering only ever changes which weight one
specific criterion function assigns to an edge of its own *derived* graph -- `FullNetwork`,
`ModelModularization`, and every other criterion are completely untouched.

## 2. `TopologyRole`

A closed, six-value vocabulary (`app.agent2.module_evaluation.types.TopologyRole`):

| Role | Meaning | Default weight | Auto-assigned? |
| --- | --- | --- | --- |
| `NORMAL` | Full, unfiltered contribution | `1` | yes (the fallback) |
| `UNIVERSAL_CURRENCY` | Near-universal currency metabolite (ATP/ADP, water, protons, phosphate, ...) | `0` (hard-exclude) | yes, by curated name |
| `COFACTOR` | Common redox/acyl-carrier cofactor (NAD(H), NADP(H), CoA, FAD, ...) | `0.3` (down-weight) | yes, by curated name |
| `GENERIC_ADAPTOR` | Highly-reused adaptor/scaffold (e.g. 14-3-3) | `0.3` (down-weight) | **never** -- override only |
| `HIGH_DEGREE_HUB` | Caller declares a species hub-like for this evaluation | `0.3` (down-weight) | **never** -- override only (automatic detection only *flags*, §4) |
| `USER_EXCLUDED` | Excluded for a reason this package has no built-in vocabulary for | `0` (hard-exclude) | never -- override only |

Default weights (`app.agent2.module_evaluation.criteria.DEFAULT_TOPOLOGY_ROLE_WEIGHT`) are a
disclosed policy choice, not part of the enum itself, and are themselves overridable per
species (§3).

## 3. Filtering policy and precedence

For every species that connects at least one edge of the derived graph, its own role/weight
is resolved in this order:

1. **An explicit, per-evaluation override** (`TopologyRoleOverride` in
   `TopologyFilteringPolicy.overrides`) -- always wins. A caller may specify any role, and
   optionally any weight (omitting the weight uses that role's own default).
2. **This package's own curated, name-based default** (`_curated_default_role`): an *exact*,
   case-insensitive match against a species' own curated `name` against two fixed lists
   (`_UNIVERSAL_CURRENCY_NAMES`, `_COFACTOR_NAMES`) covering the task's own named examples
   (ATP/ADP/GTP/.../water/protons/phosphate; NAD(H)/NADP(H)/CoA/FAD/common vitamins).
   **Exact match, never substring** -- "Acetyl_CoA" is never mistaken for bare "CoA".
3. **`NORMAL`, weight `1`** -- the fallback when neither of the above applies.

An edge connecting two reactions that share more than one species takes the **maximum**
weight among every shared species -- a genuinely pathway-specific shared species is never
diluted just because the same two reactions also happen to share a currency metabolite.

**`GENERIC_ADAPTOR` is never auto-detected by name** (task §1: "when contextually
appropriate"): a species like 14-3-3 only ever gets this role via an explicit override,
because whether a reused adaptor/scaffold is mechanistically relevant is inherently
model-specific (§5 below).

## 4. Hub detection -- flag, never auto-exclude

A species connecting at least `hub_degree_threshold` of this modularization's own member
reactions (default: `max(4, member_reaction_count // 3)`, overridable via
`TopologyFilteringPolicy.hub_degree_threshold`) is added to
`TopologySeparationDetail.hub_candidate_species_ids` -- **purely informational**. This never
changes that species' own resolved role or weight (task §3: "degree-based hub detection may
flag candidates, but must not silently exclude them by default"). A caller who reviews the
flagged candidates may then choose to add an explicit `TopologyRoleOverride` naming
`HIGH_DEGREE_HUB` (or any other role) for one of them -- closing the loop from
detection -> disclosure -> informed, explicit decision.

## 5. Context sensitivity

`TopologyFilteringPolicy`/`TopologyRoleOverride` are supplied per call to
`evaluate_modularization`/`evaluate_modularization_under_weights`/`compare_modularizations`
(never a global, model-wide setting) -- the task's own named example is honored directly: a
caller scores a signaling model with `TopologyRoleOverride("protein_14_3_3",
TopologyRole.GENERIC_ADAPTOR)` to down-weight it there, and omits that override (or declares
it `NORMAL`) when scoring a different model where that same species is mechanistically
central. Verified directly by test
(`test_user_override_can_restore_normal_weight_for_a_curated_currency_species`,
`test_generic_adaptor_down_weighted_only_via_explicit_override`).

## 6. Raw vs. filtered score reporting

`ModularizationCriterionScore.raw_score` for `TOPOLOGICAL_SEPARATION` is always the
**filtered** score (task §4: "use the filtered score for modularization evaluation") --
unchanged in meaning from `docs/27`'s own contract, so nothing about *using* this criterion's
output in a weighted `overall_score` changes. The new `ModularizationCriterionScore.detail:
TopologySeparationDetail | None` field (`None` for every other criterion) additionally
discloses:

- `raw_topology_score`: the pre-filtering baseline (every edge weight `1`, exactly
  `docs/27`'s own original formula).
- `filtered_topology_score`: the weighted score actually used (`None`, with `available=False`
  on the surrounding `CriterionResult`, when every edge's own weight filtered to exactly `0`
  -- a genuine "no connectivity signal survived filtering" outcome, never silently reported as
  either a perfect or a zero score).
- `filters`: every species whose role/weight was *not* the plain default (`NORMAL`/`1`) --
  its resolved `role`, `weight`, and `source` (`"override"` or `"curated_default"`). An
  ordinary, unfiltered species is never listed, keeping this compact even on a large network.
- `hub_candidate_species_ids`: every degree-flagged candidate (§4), independent of `filters`.

## 7. Example: before/after on the real yeast lipid-biosynthesis organism

Running `evaluate_modularization` on the real, live yeast organism's heuristic
(`TOPOLOGICAL`) modularization, with default filtering and no overrides:

```text
raw_topology_score:       0.236...
filtered_topology_score:  0.419...
```

9 species were filtered -- `CO2`/`H2O`/`ATP`/`ADP`/`AMP`/`NH3`/`diphosphate` as
`UNIVERSAL_CURRENCY` (weight `0`), and 2 more as `COFACTOR` (weight `0.3`), all via
`source="curated_default"`. 3 species were additionally flagged in
`hub_candidate_species_ids` (disclosed, not auto-excluded). The filtered score very nearly
doubles the raw one -- directly confirming the task's own stated problem (ubiquitous
components artificially destroying a topology score) and this increment's own fix.

## 8. Tests

`tests/agent2/test_module_evaluation.py` (new section): raw score diluted by pure
currency-sharing; ATP-like currency exclusion by default; cofactor down-weighting (not
hard exclusion); generic-adaptor down-weighting *only* via explicit override (confirmed
absent without one); user override restoring full weight (recovers the identical raw score);
user override hard-excluding a component the default policy would not (`USER_EXCLUDED`);
high-degree hub flagged but never auto-excluded; deterministic repeated evaluation;
no mutation of the canonical model; GENERATED/IMPORTED symmetry (identical filtering result
for the identical reaction/species shape under either origin).

## 9. Remaining limitations

- The curated name lists are **exact-match only** (§3) -- a non-standard spelling (e.g.
  "adenosine triphosphate" instead of "ATP") is not recognized automatically; an explicit
  override is always the authoritative fallback for exactly this case.
- `GENERIC_ADAPTOR`/`HIGH_DEGREE_HUB`/`USER_EXCLUDED` have no automatic producer at all by
  design (§1/§4) -- a future increment could add a curated, cross-referenced (e.g. UniProt/
  ChEBI-anchored) default list for common adaptor proteins specifically, but this increment
  deliberately does not attempt it (no reliable, generically-available identifier exists on
  `SpeciesSpecification` to anchor such a list today).
- The default hub-degree threshold (`max(4, member_reaction_count // 3)`) is a simple,
  disclosed heuristic, not derived from any statistical analysis of real degree
  distributions -- always overridable via `TopologyFilteringPolicy.hub_degree_threshold`.
- No weight-space exploration or new module-discovery algorithm was implemented (explicitly
  out of scope for this increment) -- `TopologyFilteringPolicy` composes with the pre-existing
  `evaluate_modularization_under_weights` exactly as documented in `docs/27` §7, held fixed
  across every weight vector tried.
