# Macroscopic-to-Microscopic Kinetic Reconstruction — Design Proposal

**STATUS: DESIGN PROPOSAL. NOT IMPLEMENTED. NOT YET REVIEWED FOR
IMPLEMENTATION.** This document is a research/design increment only, per
its own instructions. No production code was written, no test was added,
nothing was staged, committed, or pushed. If accepted, this becomes the
basis for one or more real, separately-scoped implementation increments
(§10) — it is not itself one.

## 0. Framing

Everything Agent 2 does today with real kinetic evidence is macroscopic:
`kcat`, `Km`, `Vmax`, `kcat/Km` — parameters of the *reduced*
Michaelis-Menten description of an enzyme-catalyzed reaction. Every
executable rate law Agent 2 currently generates (`MASS_ACTION`,
`REVERSIBLE_MASS_ACTION`, the executable-rate-law fallback) is,
underneath, a *mass-action* ODE system stated directly in terms of
*elementary* (microscopic) rate constants — `kf`, `kr`, and, for a
catalytic step, `kcat` itself. Today Agent 2 never bridges the two: a
Michaelis-Menten law is rendered as `kcat*S/(Km+S)` verbatim (never
decomposed into `E`, `ES`, `kf`, `kr`), and the executable fallback for a
law Agent 2 cannot express instead invents a *new*, evidence-free
mass-action approximation from heuristic defaults — never derived from
the very `Km`/`kcat`/`Vmax` evidence that may already be sitting on the
declared parameters.

This document asks: **when real macroscopic evidence (and, optionally,
abundance/concentration/flux context) is available, can Agent 2
principledly recover the underlying elementary `kf`/`kr` instead of
falling straight to a heuristic or an unrelated mass-action guess — and
if so, exactly how much of that recovery is actually justified, versus
merely convenient?** The answer, established below directly from the
literature rather than assumed, is: **partially, and only with explicit,
disclosed extra assumptions — never fully from `Km`/`kcat` alone.**

---

## 1. Paper-by-paper findings

### 1.1 Steuer, Gross, Selbig & Blasius (2006), *Structural kinetic
modeling of metabolic networks*, PNAS 103(32):11868-73.
DOI: 10.1073/pnas.0600013103. **Read in full** (open-access PMC copy).

**Directly stated by the paper:**
- Builds a local linearization (Jacobian) of a metabolic network around
  an experimentally observed **reference/operating state**: steady-state
  metabolite concentrations **S₀** and steady-state fluxes **ν(S₀)**
  satisfying **N·ν(S₀) = 0** (mass balance at steady state), where **N**
  is the stoichiometric matrix.
- The Jacobian is `J = N·[diag(ν₀)·Λ⁻¹ + θ]`, where `Λ_ij = N_ij·ν_j⁰/S_i⁰`
  depends *only* on stoichiometry and the reference fluxes/concentrations
  — no kinetic parameter appears in it at all.
- `θ` (the "saturation parameters," normalized elasticities
  `∂μ/∂x = S/(Km+S)` for a Michaelis-Menten term) is dimensionless,
  bounded (`[0,1]` for simple saturation, `[0,n]` for Hill-type
  cooperativity), and characterizes *local sensitivity*, never the
  underlying rate-law's actual `Km`/`kcat`/`kf`/`kr` values.
- Explicitly frames this as a way to study a network's *dynamical
  capabilities* (stability, bifurcations, oscillations) **without ever
  specifying full rate laws or their parameters** — the reference state
  plus bounded, biochemically-interpretable elasticities are sufficient
  for that purpose, and deliberately not sufficient (nor intended) to
  recover elementary rate constants themselves.
- Underdetermination is handled by **statistical ensemble sampling**:
  every unknown saturation parameter is drawn from its physiologically
  plausible interval, and conclusions (e.g. "oscillations require
  feedback cooperativity ≥ 2") are reported as properties that hold
  *robustly across the whole sampled ensemble*, never as a single
  point-estimate answer.

**My synthesis:** this paper does not attempt microscopic reconstruction
at all — it is the strongest illustration in this set of *why* a
reference state (flux + concentration at one experimentally grounded
operating point) is powerful even when it under-determines everything
else: it converts an intractable "unknown rate law" problem into a
tractable "bounded elasticity" problem. Its core technique — **decouple
what the reference state alone determines (Λ) from what still needs an
assumption (θ), and never silently collapse the latter to one arbitrary
value** — is exactly the discipline this design proposal adopts for
`kf`/`kr` reconstruction in §3/§6.

### 1.2 Pimentel, Santos-Navarro, Dewasme & Vande Wouwer (2025), *Robust
Reaction Rate Estimation with Application to Mammalian Cell Cultures*,
IFAC-PapersOnLine 59-6:451-456. DOI: 10.1016/j.ifacol.2025.07.187.
**Read in full** (open-access author PDF).

**Directly stated by the paper:** a method for estimating the *time
evolution of macroscopic reaction rates* `φ_j(t)` (fluxes, in the
bioprocess-engineering sense — e.g. glycolysis rate, lactate-consumption
rate) from noisy, sparse *concentration* measurements, **without
numerical differentiation** of those measurements (differentiation of
noisy data is flagged, citing prior work, as "ill-posed" and
noise-amplifying). It solves a regularized nonlinear least-squares
problem parameterizing the unknown rate trajectories directly (optionally
via a compact Hermite-spline basis for scalability), combining a
measurement-fit term, a smoothness penalty, and optional
*biologically-inspired* penalty terms (e.g. "these two rates should not
both be active at once"). It requires the stoichiometric matrix as a
prior (obtainable by PCA-type methods) and validates on synthetic data
mimicking a real mammalian-cell protein-production process.
**It never addresses `Km`/`kcat`/`Vmax` or elementary `kf`/`kr` at all**
— its output is macroscopic flux trajectories, explicitly offered as
"a brick in the modeling pipeline" that a *separate*, later step (fitting
Monod/Haldane/Contois-type laws, or the enzyme-level methods of §1.3/1.4)
would use to get kinetic parameters.

**My synthesis:** this paper is not about microscopic reconstruction and
does not claim to be. Its relevance here is narrower and purely
methodological: it is a credible, robust way to obtain the **net
steady-state (or time-resolved) flux** that reference-state methods
(§1.1) and reconstruction methods (§1.4) both need as an input, when that
flux is not already known from FBA or direct enzyme-assay data — i.e. it
is one credible *source* for one of the task's named systems-level
inputs ("genome-scale/FBA fluxes"), not itself a reconstruction method
for elementary rate constants. It should not be over-cited as doing more
than it does.

### 1.3 Vega-Ramon, Hardacre & Zhang (2025), *Extracting microkinetic
insights from macroscopic measurements: A power law modelling framework
for catalytic reaction mechanism analysis*, Chemical Engineering Science
318:122215. DOI: 10.1016/j.ces.2025.122215.
**Full text and abstract could not be retrieved** — the ScienceDirect
page and the DOI redirect both returned HTTP 403 (bot-blocked) despite
the article being confirmed CC-BY open access via Crossref/Unpaywall/
Semantic Scholar (title, authors, journal, volume, OA license all
independently confirmed; abstract text was not exposed by any of those
metadata APIs either).

**What can be stated directly (bibliographic only):** title, authors,
venue, and CC-BY license, confirmed via three independent metadata
services (Crossref, Unpaywall, Semantic Scholar).

**My synthesis (explicitly inference, not a reading of this paper):**
the same three-author group published a directly-abstracted companion
paper in the same year in the AIChE Journal — *"Cracking the physical
insight of power law models: Bridging the gap between macroscopic
kinetics and surface coverages"* (confirmed abstract: develops analytical
expressions linking empirical power-law reaction orders and apparent
activation energies to the *fractional surface coverage* of
non-observable reaction intermediates, for **gas-phase heterogeneous
catalysis** — validated on an in-silico water-gas-shift case study).
Given the near-identical title/theme/author set and 2025 co-publication,
the CES paper almost certainly belongs to the same research program:
inverting an empirical macroscopic rate expression (power law, not
Michaelis-Menten) to recover microscopic/mechanistic information
(surface-intermediate coverage / elementary-step character) for
**heterogeneous catalytic** reaction mechanisms — a different physical
domain (solid-catalyst surface chemistry) from enzyme mass-action
kinetics in solution.

**Why this still belongs in this design, with an explicit caveat:** the
*general principle* — that a macroscopic, empirically-fit rate expression
constrains but does not by itself determine the underlying elementary
mechanism, and that recovering more requires an explicit reference
condition plus a committed mechanistic ansatz — transfers directly and
is used in §3/§6. **The specific equations do not transfer**
(power-law reaction orders and surface coverages have no direct
analogue in enzyme `E+S⇌ES→E+P` mass action) and none are used here.
This paper is *not* relied upon for any specific reconstruction formula
in this document.

### 1.4 Berra, Sommariva, Piana & Caviglia (2025), *From Michaelis–Menten
parameters to microscopic rate constants: an inversion approach for
enzyme kinetics*, bioRxiv 2025.10.23.684102. **Read in full**
(bioRxiv HTML full text). **This is the single most directly relevant
paper of the four, and does the closest thing to what this design
proposes.**

**Directly stated by the paper:**
- States the mechanism exactly as this task's own §2:
  `E + S ⇌(kf,kr) C → (kcat) E + P`, four coupled ODEs, reducible under
  the quasi-steady-state assumption (QSSA) to the standard MM equation.
- States the identifiability problem **explicitly and quantitatively**:
  *"the rates kf, kr, and kcat cannot be determined algebraically from
  Vmax and Km, since only two equations are available for three
  unknowns."* With total enzyme concentration `e0` known,
  `kcat = Vmax/e0` is immediately solved, leaving exactly **one
  remaining equation** (`Km = (kr+kcat)/kf`) for **two remaining
  unknowns** (`kf`, `kr`) — a genuine, quantified 1-degree-of-freedom
  underdetermination, not a vague qualitative claim.
- Cites the one prior general method for this ("the Lambda approximation
  method") as showing *"high arbitrariness and a significant
  reconstruction error"* — i.e. an existing naive-reconstruction approach
  is documented in the literature as unreliable, reinforcing why this
  design explicitly refuses to silently pick a point solution (task's own
  instruction, and this paper's own stated motivation).
- Its own resolution strategy: derives a new, exact identity (their
  eq. 11) linking `kf`, `kr` to the *time-dependent* substrate
  concentration `s(t)` (not merely its steady-state value), approximates
  `s(t)` by numerically solving the ordinary MM equation from `Km`/`kcat`,
  and combines that "fundamental equation" with the MM constraint
  equation (`Km=(kr+kcat)/kf`) into a **regularized least-squares**
  problem, solved for a *range* of assumed initial conditions
  (`s₀ ∈ [Km/5, 1.5·Km]`, `e₀ ∈ [Km/50, 0.5·Km]`, sampled by Latin
  Hypercube) and reported as the **geometric mean** across that ensemble
  — an explicit uncertainty-averaging strategy, not a single confident
  number.
- **Sensitivity analysis, stated directly and load-bearing for this
  design's identifiability claims:** the substrate trajectory `s(t)` is
  *far* more sensitive to `kf` than to `kr` ("s appears significantly
  more influenced by kf than by kr, a pattern consistently observed in
  multiple cases"). Numerical validation across 50 reconstructions
  confirms: `kf` is recovered close to its true order of magnitude;
  `kr` reconstruction is *"noticeably less accurate... as expected from
  the results of sensitivity analysis"* and the paper explicitly warns
  *"the assignment of a precise numerical value to kr... should be done
  with caution."*
- Requires: `Km`, `kcat` (or `Vmax` + `e0`), and — critically — either a
  measured or an MM-model-approximated **time-resolved substrate
  trajectory** (or, absent real time-course data, the QSSA-derived
  approximation to one, which itself requires assumed initial
  concentrations). It does **not** use fluxes or FBA at all.
- **Units used are exactly this project's own canonical units**: `kf` in
  `nM⁻¹ s⁻¹` (= `per_nMs`), `kr`/`kcat` in `s⁻¹` (= `per_sec`),
  concentrations in `nM`. Confirmed directly from the paper's own
  notation, not inferred.

**My synthesis:** this paper is the load-bearing source for §2/§3/§6
below. It establishes, with a real quantitative demonstration, exactly
the shape of the problem this design must solve: `Km`+`kcat` alone are
provably insufficient (1 DOF short); one additional, qualitatively
different piece of information (here, transient trajectory shape) can
close that gap for `kf` specifically, but **not reliably for `kr`**, and
even then only through a regularized fit, never a closed-form algebraic
solution, and never without disclosing the assumed initial conditions the
fit depended on.

---

## 2. Elementary mechanisms: derived relationships

### 2.1 Irreversible single-substrate mechanism (the task's own baseline)

```text
E + S <=(kf,kr)=> ES --(kcat)--> E + P
```

ODEs (concentrations `e,s,c,p` in nM; `kf` in `per_nMs`; `kr`,`kcat` in
`per_sec`; confirmed against Berra et al. eq. 3-6):

```text
ds/dt = -kf*e*s + kr*c
de/dt = -kf*e*s + (kr+kcat)*c
dc/dt =  kf*e*s - (kr+kcat)*c
dp/dt =  kcat*c
```

Conservation laws (no reactant/enzyme destroyed): `s+c+p = s0` (constant),
`e+c = e0` (constant, `e0` = total protein/enzyme abundance).

Under the QSSA (`e0 ≪ Km` region, or more precisely `dc/dt≈0`):

```text
c ≈ e0*s/(Km+s)                     Km = (kr+kcat)/kf
v  = kcat*c = Vmax*s/(Km+s)         Vmax = kcat*e0
```

**Derived (this document, standard biochemistry, confirmed dimensionally
consistent in §5):**

| Known | Solve for | Result |
|---|---|---|
| `Vmax`, `e0` | `kcat` | `kcat = Vmax/e0` — **exact, unique** |
| `Km`, `kcat`, one more independent equation | `kf` (given `kr`), or vice versa | `kf = (kr+kcat)/Km` — exact **given kr**, but `kr` itself has no second independent macroscopic equation from `Km`/`kcat` alone |
| `Km`, `kcat` **only** | `kf`, `kr` jointly | **Underdetermined by exactly 1 degree of freedom** — every `(kf,kr)` pair on the curve `kf·Km = kr+kcat` is equally consistent with the macroscopic data. This is Berra et al.'s own explicit finding (§1.4), re-derived here from first principles, not merely quoted. |

### 2.2 Reversible single-substrate/single-product extension (my own
derivation — "reversible extensions where justified," task §2)

```text
E + S <=(kf1,kr1)=> ES <=(kf2,kr2)=> E + P
```

This is the standard reversible ("Haldane") Michaelis-Menten mechanism.
Its macroscopic reduction (standard enzymology, e.g. Cornish-Bowden) has
*two* MM-like descriptions, one per direction (`Vmax_f`, `Km_S` for the
forward reaction; `Vmax_r`, `Km_P` for the reverse), related by the
**Haldane relationship**:

```text
Keq = (Vmax_f * Km_P) / (Vmax_r * Km_S)
```

`Keq` is the reaction's thermodynamic equilibrium constant — a quantity
*independent* of any enzyme (it depends only on the reactants'
standard-state free energies, e.g. from `ΔG°′` estimates such as
eQuilibrator). **This is a genuine, principled fifth macroscopic-adjacent
constraint** beyond the four enzymological parameters
(`Vmax_f`,`Km_S`,`Vmax_r`,`Km_P`) themselves, and — unlike a flux/
concentration reference point (§4) — it constrains the *microscopic*
rate constants directly, not merely the macroscopic ones, **provided the
two-step reversible mechanism above is the correct one and `Keq` is
independently trustworthy**. With 4 microscopic unknowns (`kf1,kr1,kf2,
kr2`), 2 correspondingly independent macroscopic constraints (`Km_S`,
`Km_P`) plus a `Vmax`-derived `kcat`-equivalent pair and the Haldane
constraint, this mechanism is **closer to fully determined** than the
irreversible case is — but still requires the same class of extra
assumption (a committed elementary-step topology) the task warns against
adopting silently, and this design does not claim it is exactly
determined in general without deriving that explicitly per case (see
§9, unresolved question 3).

**Scope boundary (explicit, per task §7 "do not redesign unrelated
architecture"):** multi-substrate elementary decomposition (ordered,
random, ping-pong) is **out of scope for this design increment**. Agent 2
today has no elementary-mass-action representation for any mechanism at
all — the executable-rate-law fallback increment deliberately uses only
the *generic* mass-action form for multi-substrate cases, precisely
because no single combining algebra is scientifically justified without
committing to a specific multi-substrate topology (documented in
`docs/11_model_specification_assembly.md` §8, unchanged by this
proposal). This design's own single-substrate scope is a strict subset
of what would eventually need this same discipline applied to
multi-substrate mechanisms — named here as future work (§10), not solved.

---

## 3. Identifiability table

`✓✓` = uniquely determined (exact); `~` = partially constrained (bounded,
not pinned to one value, or reliable only in order of magnitude); `✗` =
effectively underdetermined given that input set alone.

| Available inputs | `kcat` | `kf` | `kr` | Notes |
|---|:---:|:---:|:---:|---|
| `Km` only | ✗ | ✗ | ✗ | No macroscopic-to-microscopic bridge at all. |
| `Km`, `kcat` (no `e0`, no flux, no trajectory) | — (given) | ✗ | ✗ | 1 equation (`Km=(kr+kcat)/kf`), 2 unknowns — the family of solutions is a 1-parameter curve, never a point. **Never silently collapse this to a single value** (task §6, Berra et al.'s own explicit warning against the "Lambda approximation"). |
| `Km`, `Vmax`, `e0` (protein abundance) | ✓✓ | ✗ | ✗ | `kcat=Vmax/e0` exact. `kf`,`kr` still only constrained to the same 1-parameter curve as above — abundance alone does not resolve the split. |
| `Km`, `kcat`/`Vmax`, `e0`, **+ transient concentration trajectory** (measured, or QSSA-approximated per Berra et al.) | ✓✓ | **~ (good)** | **~ (poor — order of magnitude at best)** | The one method in this literature set that actually attempts the split. `kf` is well-identified because `s(t)` is highly sensitive to it; `kr` is not, by the same sensitivity analysis. Requires an assumed/sampled initial condition `(s0,e0)` and a regularized fit — an inverse problem, not algebra. |
| `Km_S`, `Km_P`, `Vmax_f`, `Vmax_r`, `e0`, **+ independently known `Keq`** (reversible 2-step mechanism, §2.2) | ✓✓ (both directions) | **~ / ✓✓ under committed topology** | **~ / ✓✓ under committed topology** | Genuinely more constrained than the irreversible case (Haldane relationship is a real, mechanism-linking equation, not just a macroscopic ratio) — but only under an explicitly committed 2-step topology; not derived here as unconditionally exact (§9). |
| `Km`, `kcat`, `e0` + **steady-state reference concentration `S_ref` + steady-state flux `J_ref`** (FBA or measured), reaction operating in its **saturating** regime (`S_ref ≳ Km`) | — (given) | ✗ | ✗ | A *consistency check* on `Km`/`kcat`/`e0` (does `Vmax·S_ref/(Km+S_ref) ≈ J_ref`?), **not new information toward the `kf`/`kr` split** — derived here explicitly (§4). Confirms or flags inconsistency in the *macroscopic* parameters; says nothing new about elementary rates. |
| `Km`, `kcat`, `e0` + `S_ref`, `J_ref`, reaction in its **linear/unsaturated** regime (`S_ref ≪ Km`) | — (given) | ✗ (only the lumped `kcat/Km` ratio is re-confirmed, never `kf` alone) | ✗ | Derived here (§4): in this regime `v≈(kcat·e0/Km)·S_ref`, and `kcat/Km = kf·kcat/(kr+kcat)` is *already* fully determined by `Km`,`kcat` alone — the reference point adds no new independent equation for `kf` vs `kr` individually. It **can**, however, solve for an unknown `e0` if `Km`,`kcat` are otherwise known from an independent source (e.g. AI-predicted `kcat`) — a genuinely useful, different use of the same data. |
| Direct microscopic measurement of `kf`/`kr` (rare; e.g. stopped-flow/SPR literature value) | ✓✓ | ✓✓ | ✓✓ | The only case with zero remaining degrees of freedom by construction — trivially top of the evidence hierarchy (§4/§7). |

**Governing principle, stated once and applied everywhere in this
document:** *two* macroscopic numbers (`Km`, one of
`kcat`/`Vmax`/`kcat/Km`) can never algebraically determine *three*
microscopic numbers (`kf`,`kr`,`kcat`). Every path in this table that
reaches `kf`/`kr` individually does so by adding a **qualitatively
different** third piece of information (a transient trajectory, an
independent thermodynamic constant, or a direct measurement) — never by
manipulating `Km`/`kcat` harder.

---

## 4. Flux and abundance handling (task §4)

**Protein abundance (`e0`) converts `Vmax ↔ kcat`, exactly, always:**
`kcat = Vmax/e0` (equivalently `Vmax = kcat·e0`). This is the one
completely reliable, assumption-free use of abundance data. It requires
`e0` and the macroscopic parameter to be **condition-matched**: the same
organism, same protein/isozyme identity (never summed across isozymes
unless the measurement itself is isozyme-agnostic), same compartment,
and, ideally, the same physiological/growth condition the `Vmax` was
measured or predicted under. **Never** apply a `Vmax`/abundance pair
across two different catalytic contexts (mirrors Agent 2's own existing
`enzyme_state_id`/`protein_id`/`complex_id` catalytic-context
discipline, unchanged by this proposal).

**Metabolite concentrations define a reference state**, exactly as in
Steuer et al. (§1.1): a self-consistent snapshot `(S_ref, all other
relevant concentrations)` at which the reaction is known (or assumed) to
be operating. This reference state is a *precondition* for the two flux
uses below, not itself a source of new elementary-rate information.

**FBA/genome-scale flux can constrain, never by itself prove,
microscopic kinetics** (task's own explicit instruction, and directly
derived in §3's last two table rows):
- In the **saturating** regime, a reference flux is a **consistency
  check** on already-declared `Km`/`kcat`/`e0` — useful for flagging a
  parameter set that is thermodynamically/kinetically implausible, never
  for deriving a new `kf`/`kr` split.
- In the **linear** regime, a reference flux **can** solve for an
  unknown `e0` given an independently-sourced `Km`,`kcat` (e.g. an
  AI-predicted `kcat/Km`) — genuinely useful, and the one legitimate
  "flux → new number" path this design recommends, clearly scoped to
  solving for **abundance**, never for `kf`/`kr` individually.
- **FBA flux is never classified as experimental kinetic evidence**
  (task's explicit instruction, §3 of this document, restated for
  emphasis): it is a structural/optimization-derived quantity, several
  inferential steps removed from a direct kinetic measurement, and must
  carry its own, weaker provenance tag (§7) whenever it contributes to a
  reconstructed value.

**Explicit condition-matching requirements (task §4), stated once for
all three uses above:** organism identity; protein/isozyme identity
(never pooled across isozymes sharing one EC number, mirroring Agent
1.x Increment C.11's own GotEnzymes2 exact-identity anchor); reaction/
compartment identity; and, where flux is involved, a stated or assumed
steady state at the specific reference concentration used. Any
reconstruction that cannot state which condition its abundance/
concentration/flux figure came from must not proceed past the
"partially constrained" tier (§6).

---

## 5. Canonical units and dimensional consistency

No new unit vocabulary is required — every quantity in §2-§4 already
maps onto Agent 2's existing canonical system
(`app.agent2.parameters.heuristic_defaults`), confirmed dimensionally
below (this is a genuinely reassuring finding, not assumed):

| Quantity | Canonical unit | Dimensional check |
|---|---|---|
| `s, e, c, p` (concentrations), `Km`, `Km_S`, `Km_P`, `S_ref` | `nM` | base unit |
| `kr`, `kcat`, `kf1`/`kr1`/`kf2`/`kr2` (unimolecular steps) | `per_sec` | `s⁻¹` |
| `kf` (bimolecular association step) | `per_nMs` | `nM⁻¹ s⁻¹`; `Km=(kr+kcat)/kf` → `[per_sec]/[per_nMs] = nM` ✓ |
| `Vmax`, reference flux `J_ref` | `nM_per_s` | `Vmax=kcat·e0` → `[per_sec]·[nM] = nM_per_s` ✓ |
| `kcat/Km` (specificity constant) | `per_nMs` | `[per_sec]/[nM] = per_nMs` ✓ — dimensionally identical to a bimolecular `kf`, which is exactly why it alone can never distinguish `kf` from `kr` (§3) |
| A hypothetical trimolecular elementary step (not needed by §2's mechanisms, listed for completeness) | `nM⁻² s⁻¹`, algebraic | matches `mass_action_rate_unit(molecularity=3)` already implemented |
| `Keq` (Haldane, §2.2) | dimensionless (ratio of like-dimensioned `Vmax·Km` products) | `[nM_per_s · nM] / [nM_per_s · nM]` cancels exactly |

Every equation used or derived in §2-§4 was checked against this table;
none requires an algebraic unit outside `{nM, per_sec, nM_per_s,
per_nMs}` or the existing algebraic-higher-order formula. **Berra et
al.'s own paper independently uses this exact unit convention** (§1.4) —
strong external corroboration that this is the right unit system for
this problem, not merely a project-internal convention being forced onto
unrelated literature.

---

## 6. Reconstruction strategy — deterministic decision tree

Applied **per catalytic context** (the same `enzyme_state_id`/
`protein_id`/`complex_id` granularity Agent 2 already uses), per
elementary parameter slot (`kf`, `kr`, and, where applicable, per-step
constants for the reversible extension):

```text
1. DIRECT_MICROSCOPIC_MEASUREMENT available for this exact slot,
   this exact catalytic context?
     YES -> use verbatim. STOP. (No fallback tier below is ever
            consulted -- mirrors the existing "genuine absence only"
            precedence rule in initialize_with_fallback.)
     NO  -> continue.

2. Is kcat resolvable exactly?
     Vmax (CURATED/LITERATURE_DERIVED/AI_PREDICTED) AND
     condition-matched protein abundance e0 available?
       YES -> kcat = Vmax / e0.  Record as DERIVED_FROM_EXPERIMENTAL_
              MACRO_KINETICS (or ..._AI_PREDICTED_MACRO_KINETICS if
              Vmax/kcat itself came from GotEnzymes2), with e0's own
              provenance also recorded (never silently merged).
       NO  -> kcat itself is the directly-reported CURATED/LITERATURE_
              DERIVED/AI_PREDICTED value (today's existing behavior,
              unchanged) -- proceed to step 3 with kcat fixed either way.

3. Is Km available (experimental or AI-predicted) for this context?
     NO  -> nothing to reconstruct from; go straight to step 7 for
            EVERY elementary slot.
     YES -> continue. Km is retained on the declared parameter set
            exactly as today (never overwritten, never consumed
            silently) regardless of what follows.

4. Is a genuinely independent third constraint available for this
   exact context -- one of:
     (a) a measured or curated TIME-RESOLVED substrate/product
         trajectory (not merely a point value) -- enables the
         Berra-et-al.-style inversion (kf: usable estimate; kr:
         order-of-magnitude only, never reported with false
         precision -- see step 5);
     (b) an independently-sourced thermodynamic equilibrium constant
         Keq for a reaction whose reversible 2-step topology
         (E+S<=>ES<=>E+P) is itself justified -- enables the Haldane-
         constrained reconstruction of Sec 2.2 (scope-limited: only
         for reactions where that specific topology is asserted, never
         inferred silently for an arbitrary reversible reaction);
     (c) a condition-matched reference concentration S_ref together
         with a reference flux J_ref in the CONFIRMED LINEAR regime
         (S_ref << Km) and an independently-known kcat/Km -- enables
         solving for an unknown e0 only (never kf/kr directly, per
         Sec 3/4)?
       YES (a or b) -> solve the resulting (regularized, never exact-
              algebraic) system for kf (and, with much lower
              confidence, kr). Record as FLUX/ABUNDANCE_CONSTRAINED_
              RECONSTRUCTION with the specific extra constraint used
              named in provenance. Go to step 6.
       YES (c only) -> solve for e0 only; return to step 2 with the
              newly-derived e0. Never treat this branch as having
              resolved kf/kr.
       NO  -> go to step 5.

5. Km and kcat known, no third constraint:
     kf and kr remain on the 1-parameter curve kf*Km = kr + kcat
     (Sec 2.1/3). Do NOT silently pick a point on this curve.
     Two disclosed, non-arbitrary options, both legitimate, neither
     silent:
       (i)  leave kf, kr as an explicit UNRESOLVED_DEGREE_OF_FREEDOM
            pair and fall through to step 7 for both (safest default);
       (ii) if a project-wide, explicitly-versioned convention for
            resolving this one specific degree of freedom is later
            adopted (e.g. "assume kr negligible relative to kcat for
            an irreversible reaction," a real, commonly-used
            simplifying approximation in enzymology) -- apply it only
            as an explicitly-named, versioned policy decision, never
            as an implicit numeric default indistinguishable from
            HEURISTIC_INITIALIZATION. This design does not adopt (ii)
            now (Sec 9, unresolved question 1) -- (i) is the only
            behavior this proposal actually recommends shipping.

6. Every slot solved in steps 2/4 is recorded with its own tier from
   the hierarchy (Sec 7) and its own disclosed uncertainty text
   (explicitly weaker for kr than for kf when step 4(a) was used --
   never presented with the same confidence).

7. Any slot not resolved by 1-6 falls through to today's existing
   heuristic_defaults / initialize_with_fallback machinery, completely
   unchanged, tagged HEURISTIC_INITIALIZATION exactly as today.
```

This is a strict, order-preserving **refinement** of the existing
4-tier `initialize_with_fallback` waterfall (Increment: Heuristic
Simulation Parameter Initialization) — it inserts new, more specific
tiers *between* "real macroscopic evidence" and "heuristic default,"
and never changes the existing top (`LITERATURE_DERIVED`/`CURATED`) or
bottom (`HEURISTIC_INITIALIZATION`/`PLACEHOLDER`) behavior.

---

## 7. Evidence hierarchy

```text
DIRECT_MICROSCOPIC_MEASUREMENT
> DERIVED_FROM_EXPERIMENTAL_MACRO_KINETICS
> DERIVED_FROM_AI_PREDICTED_MACRO_KINETICS
> FLUX_ABUNDANCE_CONSTRAINED_RECONSTRUCTION
> HEURISTIC_INITIALIZATION
> PLACEHOLDER
```

(`PLACEHOLDER` was implicit in the task's own sketch but is retained
explicitly, matching Agent 2's own existing bottom tier.)

Precedence rule, restated from the existing codebase's own established
principle (Increment: Heuristic Simulation Parameter Initialization) and
applied identically here: **a lower tier is consulted only when the
tier above it found a genuine, complete absence of applicable input for
that exact slot — never when applicable input exists but is merely
weaker or disagrees.** Disagreement at any tier is a disclosed,
terminal fact about that slot (e.g. two independently-derived
`kf` estimates that disagree), never silently resolved by falling to a
lower tier.

`FLUX_ABUNDANCE_CONSTRAINED_RECONSTRUCTION` sits **below** both macro-
kinetics tiers (experimental and AI-predicted) and **above** heuristic
initialization, per the task's own ordering — reflecting that it adds
real, condition-matched information (§4) but is always at least one
inferential step further from a direct measurement than even an
AI-predicted `Km`/`kcat` value. **FBA flux alone is never, at any tier,
classified as experimental kinetic evidence** (task's explicit
instruction) — every contribution flux makes travels through this named
`FLUX_ABUNDANCE_CONSTRAINED_RECONSTRUCTION` tier or is rejected, never
disguised as `CURATED`/`LITERATURE_DERIVED`.

---

## 8. Interaction with current Agent 2 (task §7 — no unrelated redesign)

- **Kinetic-law selection** (`app.agent2.kinetics`): **unchanged**. This
  proposal does not alter which `KineticLawType` a reaction is assigned.
  It only affects *how a `MICHAELIS_MENTEN` (or, for the reversible
  extension, a future explicitly-elementary variant) law's declared
  parameters are initialized*, exactly at the point
  `app.agent2.parameters.builder._declare_michaelis_menten` already
  initializes `kcat`/`Km` today.
- **Parameter declaration** (`app.agent2.parameters`): this is the
  actual insertion point. `_declare_michaelis_menten` (and, if the
  reversible extension is ever implemented, a new declare function
  mirroring `_declare_reversible_mass_action`) would additionally
  attempt the decision tree of §6 for reactions whose kinetic law is
  `MICHAELIS_MENTEN` and whose evidence includes a resolvable `Km`+
  `kcat`/`Vmax` pair, **before** the existing `initialize_with_fallback`
  call — never replacing it, since every branch of §6 that fails to
  resolve a slot explicitly falls through to it (§6 step 7).
- **AI-predicted evidence**: reused, not duplicated. `Vmax`/`kcat`
  reconstruction (§6 step 2) already accepts a GotEnzymes2-sourced
  macroscopic value exactly as `initialize_from_ai_predicted_evidence`
  does today; this proposal's own new tier
  (`DERIVED_FROM_AI_PREDICTED_MACRO_KINETICS`) exists specifically so a
  value *derived from* an AI-predicted macro-parameter is never
  reported with the same confidence as the AI prediction itself, nor
  confused with a directly experimental derivation.
- **Heuristic initialization**: entirely unchanged as the final
  fallback (§6 step 7, §7). This proposal is additive above it, never a
  replacement.
- **Executable fallback laws**: directly relevant, and a natural second
  use of this same machinery. Today's fallback (Increment: Executable
  Rate-Law Fallback) invents a *generic*, evidence-free mass-action `k`/
  `kf`/`kr` for a law Agent 2 cannot otherwise express. If that same
  reaction *already* has a resolvable `Km`/`kcat` on its (unused, but
  preserved) `MICHAELIS_MENTEN` parameters, a future increment could let
  the fallback's own `kf`/`kr` be seeded by this design's §6 procedure
  **instead of** the pure heuristic default — never changing the
  fallback's own generic mass-action *form*, only which tier its
  numbers come from. **This document does not implement that**; it is
  named explicitly in §10 as a natural, separately-scoped follow-on.
- **`ModelSpecification` provenance**: no new field is proposed on
  `ParameterSpecification`/`KineticLawSpecification` — every new tier
  in §7 is a new `ParameterSource` enum *value* (an additive,
  non-shape-changing change under this codebase's own established
  "narrower reading" versioning convention, exactly like
  `AI_PREDICTED`/`HEURISTIC_INITIALIZATION` before it), carried on the
  existing `source`/`source_reference`/`uncertainty_text`/
  `provenance_refs` fields. A reconstructed `kf` derived from a
  transient-trajectory fit would record, in `provenance_refs`, every
  input value's own id (the `Km` measurement, the `kcat`/`Vmax`
  measurement, the abundance record, and — new — a reference to which
  reconstruction method/assumption set was used), never collapsing that
  audit trail into a single opaque number.
- **Future Agent 4 calibration**: unaffected in kind, improved in
  starting point. Every tier this proposal introduces is still,
  explicitly, a *starting value* Agent 4 may refine — never
  `CALIBRATED`. The `kr` slot in particular (§3, §6 step 5) should be
  flagged in its own `uncertainty_text` as the *least* reliable starting
  point in the entire hierarchy below direct measurement, specifically
  so a future Agent 4 sensitivity/calibration pass prioritizes it first
  — mirroring how `is_tentative` already flags `TENTATIVE_MASS_ACTION_
  DEFAULT` assignments for prioritized scrutiny today.

---

## 9. Real sce00061 applicability (task §8 — no unclaimed coverage)

Grounded directly in this session's own real Pilot 2 Run 7 evaluation
(fresh, live Agent 1 run; see
`artifacts/pilots/yeast_fatty_acid_pilot2_run_7/25_pilot_report.md` in
`agent1-biochemical-curator`) — not assumed:

- **216 real kinetic measurements** exist (58 BRENDA, 144 GotEnzymes2,
  14 SABIO-RK), overwhelmingly `KM`/`KCAT`/`KCAT_OVER_KM`/`VMAX` — i.e.
  exactly the macroscopic vocabulary this design addresses.
- **Reaction classes that could benefit immediately, if kinetic-law
  assignment ever routes them to `MICHAELIS_MENTEN`:** any reaction with
  both a resolvable `Km` and a resolvable `kcat`/`Vmax` for the same
  catalytic context reaches §6 step 3 today already — real Run 7 data
  confirms this combination exists (e.g. protein `69ad1416-...` has both
  a real BRENDA `Km` and multiple `KCAT`/`KCAT_OVER_KM` `GOTENZYMES`
  records for the same EC number). **Without further data, every one of
  these can only ever reach §6 step 5** ("`kf`,`kr` on an unresolved
  curve") — genuinely useful (a real, non-arbitrary constraint,
  disclosed as such) but explicitly **not** a full `kf`/`kr` split.
- **Where protein abundance/FBA flux would add information, concretely:**
  abundance would let step 2 solve `kcat` *exactly* wherever only `Vmax`
  (not `kcat`) is reported, and — in the linear-regime case (§3/§4) —
  could let a future FBA/flux integration solve for `e0` itself where
  abundance is not directly curated at all (which is `sce00061`'s actual
  situation today, see below).
- **What additional data would still be required — stated honestly,
  not assumed available:**
  1. **Protein abundance/proteomics.** Agent 1 has **no connector or
     schema field for protein copy number/abundance today** (confirmed:
     no such field exists on `CuratedKineticMeasurement` or any Agent 1
     model; searched directly, not assumed). Without it, `kcat=Vmax/e0`
     (§6 step 2) can only ever apply to the subset of `sce00061`
     measurements that already report `kcat` directly (many BRENDA/
     GotEnzymes2 records do) — real but incomplete coverage.
  2. **Time-resolved kinetic trajectories, or an independently-sourced
     Keq.** Agent 1 curates *point* kinetic values (one `Km`, one
     `kcat`, etc. per record) — **never a time series** — so the
     Berra-et-al. reconstruction path (§6 step 4a) has **no real input
     to run on for any `sce00061` reaction today**, confirmed by
     inspecting the real Run 7 handoff's own `CuratedKineticMeasurement`
     shape. A thermodynamic `Keq` source (§6 step 4b) is not curated by
     Agent 1 either (no BRENDA/eQuilibrator-style thermodynamics
     connector exists).
  3. **Genome-scale/FBA flux integration.** Neither Agent 1 nor Agent 2
     consumes an FBA model or flux distribution anywhere today —
     confirmed by inspecting both codebases' connector/module lists.
     This is an entirely new data source, not a gap in an existing one.

**Honest bottom line for `sce00061` today:** this design's `kcat`-from-
abundance path (§6 step 2) and its "disclosed, unresolved `kf`/`kr`
curve" outcome (§6 step 5) are **immediately applicable** the moment
kinetic-law assignment routes a reaction with both `Km` and `kcat`
evidence to `MICHAELIS_MENTEN` — which, per the real Run 7 finding
(`25_pilot_report.md` §4), is currently **rare** (only 1/38 reactions
reached `MICHAELIS_MENTEN` in that fresh run, and it had zero attached
measurements). The full `kf`/`kr` split (§6 step 4) is **not
achievable for any real `sce00061` reaction today** without new Agent 1
data sources (abundance, trajectories, or thermodynamics) that do not
yet exist. This is stated as a limitation, not a criticism — exactly the
kind of claim the task instructs this document not to overstate.

---

## 10. Unresolved scientific questions

1. Should this codebase ever adopt a *named, versioned* simplifying
   convention for the residual `kf`/`kr` degree of freedom (§6 step
   5(ii)) — e.g. "assume the reverse (`ES→E+S`) step is negligible
   relative to the catalytic step for an irreversible reaction" (a real,
   textbook-recognized approximation, not invented here) — or should
   that curve always stay explicitly unresolved indefinitely? This
   design deliberately takes no position and ships only the
   never-silent default (§6 step 5(i)).
2. How should `kr`'s explicitly weaker reliability (§1.4, §3) be
   represented in `ModelSpecification` — a distinct `ParameterSource`
   value from `kf`'s (e.g. a "..._LOW_CONFIDENCE" suffix tier), or the
   same tier with a strictly worded `uncertainty_text`? This document
   recommends the latter as the smaller change (§8) but does not decide
   it.
3. Is the reversible-mechanism Haldane path (§2.2) exactly determined in
   general, or only under further, currently-unstated regularity
   conditions? A full determinacy proof for that 4-unknown/5-constraint
   system was not attempted in this design increment and should precede
   any implementation of §2.2.
4. Where would a `Keq`/thermodynamic-constant connector (needed for §6
   step 4b) actually source its data from for real yeast reactions
   (eQuilibrator's API, BRENDA's own equilibrium-constant field, or
   another source) — not investigated here, and a real prerequisite
   before step 4b could ever fire on real data.
5. Paper 3's actual content (§1.3) remains unconfirmed beyond
   bibliographic metadata. If it later proves to contain a directly
   transferable equation (unlikely given the heterogeneous-catalysis
   domain, but not verified), this document's §2/§6 would need revisiting.

---

## 11. Recommended implementation increments (smallest-first)

1. **`kcat = Vmax/e0` exact solve** (§6 step 2 only), gated on a new,
   explicit protein-abundance field/connector existing on the Agent 1
   side first (currently absent — this increment is blocked on that
   Agent 1 prerequisite, not implementable in Agent 2 alone yet).
2. **New `ParameterSource` tiers** (`DERIVED_FROM_EXPERIMENTAL_MACRO_
   KINETICS`, `DERIVED_FROM_AI_PREDICTED_MACRO_KINETICS`,
   `FLUX_ABUNDANCE_CONSTRAINED_RECONSTRUCTION`) plumbed through
   `app.agent2.types`/`app.agent2.boundaries.policy` exactly as prior
   additive tiers were (no contract-version bump expected, per §8) —
   useful scaffolding even before any reconstruction logic exists.
3. **The disclosed-unresolved-curve behavior** (§6 step 5(i)) as a pure
   *disclosure* increment: for any `MICHAELIS_MENTEN` context with both
   `Km` and `kcat` resolved, add a `ModelAssumption` stating the
   `kf·Km=kr+kcat` relationship and that no unique split is currently
   asserted — genuinely useful documentation of existing evidence with
   **zero new numeric behavior**, and the safest possible first step.
4. **Linear-regime abundance-from-flux solve** (§4, §6 step 4c) once (a)
   is available and a flux source (even a single manually-supplied
   reference flux, not necessarily full FBA) exists.
5. **Transient-trajectory-based `kf` (and disclosed-low-confidence `kr`)
   reconstruction** (§6 step 4a, following Berra et al.'s own algorithm)
   — the largest, most novel increment, and explicitly blocked on Agent
   1 gaining a time-resolved kinetic-measurement capability it does not
   have today.
6. **Reversible 2-step / Haldane reconstruction** (§2.2, §6 step 4b) —
   blocked on unresolved question 3 (determinacy proof) and unresolved
   question 4 (a `Keq` data source), in that order.
7. **Wiring the executable-rate-law fallback to prefer this design's
   reconstructed `kf`/`kr` over its own heuristic default** (§8) — a
   small, purely-additive change once (2)-(3) exist, deliberately listed
   last since it depends on several of the above already existing.

---

## Answer

> **What is the safest implementable strategy for converting available
> macro-kinetic, abundance, concentration, and flux information into
> microscopic mass-action parameters without overstating identifiability?**

**Solve only what is actually algebraically or statistically identifiable
from the *specific* combination of inputs at hand, one parameter slot at
a time, and disclose every remaining degree of freedom explicitly rather
than resolving it — never treat two macroscopic numbers (`Km` and
`kcat`/`Vmax`/`kcat·Km⁻¹`) as sufficient to fix three microscopic ones
(`kf`,`kr`,`kcat`), because they provably are not (§2.1, independently
confirmed by Berra et al.).** Concretely: use abundance to solve `kcat`
exactly wherever it is condition-matched and available; use flux only as
a consistency check in the saturating regime or as an abundance-solver in
the confirmed linear regime, never as a `kf`/`kr` solver; attempt a real
`kf`/`kr` split only when a genuinely independent third constraint exists
(a transient trajectory or an independently-sourced thermodynamic
constant), and even then report `kf` and `kr` with visibly different
confidence, since the underlying sensitivity of the system to each is
itself asymmetric; and let every unresolved slot fall through, exactly as
today, to an explicitly-labeled heuristic default rather than a
disguised guess. This is the same discipline this codebase's own
`initialize_with_fallback` precedence chain already enforces for
`LITERATURE_DERIVED`/`AI_PREDICTED`/`HEURISTIC_INITIALIZATION` — this
design extends that discipline one layer deeper (into the elementary
rate constants themselves) rather than replacing it.
