"""Identifiability-Aware Macroscopic-to-Microscopic Kinetic Reconstruction.

Converts macroscopic kinetic evidence (`kcat`, `Vmax`, `Km`, `kcat/Km`) into elementary
mass-action parameters **only when the result is actually algebraically identifiable**
from the specific combination of inputs at hand -- never by fabricating a unique
microscopic constant from a provably underdetermined system. See
`docs/15_macroscopic_to_microscopic_kinetic_reconstruction_design.md` (the design basis)
and `docs/17_macroscopic_to_microscopic_kinetic_reconstruction.md` (this increment's own
implementation notes) for the full derivation and identifiability rationale; this module
implements exactly the three genuinely identifiable/constrainable relationships that
design settled on (task's own Sec 3, "Supported derivations" A-D):

* **A. Direct `kcat`** -- not implemented here at all: `app.agent2.parameters.initializer
  .initialize_with_fallback`'s own existing top two tiers (`LITERATURE_DERIVED`/`CURATED`,
  `AI_PREDICTED`) already return immediately whenever real `kcat` evidence exists for the
  exact catalytic context, and this module's own reconstruction is only ever consulted
  when that tier chain finds a genuine, complete absence (see `resolve_kcat_with_
  reconstruction`'s own docstring) -- "use it directly, never re-derive it" is therefore
  already this package's existing behavior, unmodified.
* **B. `kcat = Vmax / [E]_total`** (`reconstruct_kcat_from_vmax_and_concentration`) --
  `IDENTIFIABLE` whenever a canonical (`nM_per_s`), non-heuristic `Vmax` and a non-zero,
  condition-matched `app.agent2.types.EnzymeConcentration` (from `app.agent2
  .quantitative_context`) both exist for the exact same protein.
* **C. `k_eff = kcat/Km`** (`reconstruct_k_eff_from_kcat_and_km`) -- `IDENTIFIABLE` only
  for a genuine two-reactant elementary mass-action encounter (`molecularity == 2`,
  dimensionally the only case `per_nMs` -- `mass_action_rate_unit(2)` -- actually matches;
  see this function's own docstring for why `molecularity == 1` is dimensionally wrong for
  this specific quantity in this codebase's own structural model, which never represents
  the enzyme itself as a species). **Never applied to a reaction with three or more
  reactants** (task's own explicit "do not apply generically to arbitrary multi-reactant
  reactions").
* **D. The `Km = (kr + kcat) / kf` constraint** (`classify_km_kcat_constraint`) --
  `PARTIALLY_CONSTRAINED`, never a point value, for the single-substrate `E + S <=> ES ->
  E + P` mechanism whenever both `Km` and `kcat` are resolved to real (non-heuristic,
  non-placeholder) values -- Berra et al. (2025)'s own explicit, quantitative finding
  (design doc §1.4): two equations, three unknowns, exactly one degree of freedom short of
  a unique `kf`/`kr` split. This module never picks a point on that curve.

**Never derives further from an already-heuristic or placeholder value** -- every function
here treats `ParameterSource.HEURISTIC_INITIALIZATION`/`PLACEHOLDER` as "no usable input,"
identical to a genuine absence of evidence, so a fabricated starting point can never be
laundered into an apparently-more-confident derived one.

Pure and deterministic: no database, no filesystem, no network access, no randomness.
"""

from __future__ import annotations

from app.agent2.parameters.initializer import Initialization
from app.agent2.parameters.types import IdentifiabilityStatus, MicroscopicConstraint
from app.agent2.types import CuratedKineticMeasurement, EnzymeConcentration, ParameterSource

#: Agent 1's own provenance marker for a GotEnzymes2-sourced measurement, mirroring
#: ``app.agent2.parameters.initializer``'s own identically-valued, identically-reasoned
#: private constant (not imported -- that module's own copy is private, and duplicating
#: this one literal string is simpler and safer than exporting a new public name for it).
_GOTENZYMES_SOURCE_LABEL = "GOTENZYMES"

#: Canonical units this module's own derivations require on their inputs/outputs -- reused
#: verbatim from the project's existing canonical-unit vocabulary
#: (``app.agent2.parameters.heuristic_defaults``), never a newly-invented unit string.
CANONICAL_UNIT_NM_PER_S = "nM_per_s"
CANONICAL_UNIT_PER_SEC = "per_sec"
CANONICAL_UNIT_PER_NMS = "per_nMs"

#: Sources a reconstruction may never build further on -- a fabricated (heuristic) or
#: entirely absent (placeholder) value carries no real evidentiary weight, so treating it
#: as an input would silently launder a guess into an apparently-derived, more-confident
#: number.
_UNUSABLE_SOURCES = (ParameterSource.PLACEHOLDER, ParameterSource.HEURISTIC_INITIALIZATION)

#: The one reactant molecularity at which an effective second-order rate (``kcat/Km``,
#: canonically ``per_nMs``) is dimensionally identical to this codebase's own mass-action
#: rate-constant unit (``heuristic_defaults.mass_action_rate_unit(2) == "per_nMs"``) -- see
#: ``reconstruct_k_eff_from_kcat_and_km``'s own docstring for why ``1`` is dimensionally
#: wrong here and ``3+`` is excluded by the task's own explicit instruction.
_K_EFF_ELIGIBLE_MOLECULARITY = 2


def _canonical_vmax_candidates(
    evidence: tuple[CuratedKineticMeasurement, ...],
) -> tuple[CuratedKineticMeasurement, ...]:
    """Every ``Vmax``-kind measurement Agent 1 itself already resolved a canonical
    ``nM_per_s`` value for -- never the as-reported figure, which may be in any of several
    real, mutually-incompatible units (Agent 1.x Increment C.12's own established
    canonicalization is the sole authority here, never re-derived or guessed at by this
    module)."""
    return tuple(
        m
        for m in evidence
        if m.normalized_value is not None and m.normalized_unit == CANONICAL_UNIT_NM_PER_S
    )


def reconstruct_kcat_from_vmax_and_concentration(
    vmax_evidence: tuple[CuratedKineticMeasurement, ...],
    enzyme_concentration: EnzymeConcentration | None,
) -> Initialization | None:
    """Derivation B: ``kcat = Vmax / [E]_total`` -- exact and unique whenever both sides are
    genuinely available and condition-matched (design doc §2.1/§4).

    Returns ``None`` (`IdentifiabilityStatus.INSUFFICIENT_EVIDENCE`, left to the caller to
    classify -- this function itself returns no status object, only ``None`` or a real
    ``Initialization``, mirroring every other reconstruction helper in this module) when:

    * no ``EnzymeConcentration`` was resolved for this exact protein at all
      (``app.agent2.quantitative_context`` already enforces its own condition-matching
      policy before ever producing one -- this function trusts that verdict rather than
      re-deriving it, task Sec 5's own "under the existing compatible-reference policy");
    * the resolved concentration is exactly zero (would make ``kcat`` undefined/infinite --
      never fabricated);
    * no candidate ``Vmax`` measurement has a resolved canonical ``nM_per_s`` value;
    * two or more canonical candidates disagree (different value) -- never averaged, never
      arbitrarily chosen, exactly mirroring ``initialize_from_evidence``'s own disagreement
      policy one level down.

    When multiple canonical candidates agree, the lowest-id one is the representative
    (deterministic, mirrors ``initialize_from_evidence``). When the representative's own
    ``source`` is GotEnzymes2 (AI-predicted, non-experimental), that dependency is
    preserved explicitly in the returned ``Initialization``'s own ``uncertainty_text`` --
    never silently presented as though it were an experimental derivation.
    """
    if enzyme_concentration is None or enzyme_concentration.value == 0:
        return None

    candidates = _canonical_vmax_candidates(vmax_evidence)
    if not candidates:
        return None
    first = candidates[0]
    if any(m.normalized_value != first.normalized_value for m in candidates[1:]):
        return None

    representative = sorted(candidates, key=lambda m: m.id)[0]
    kcat_value = representative.normalized_value / enzyme_concentration.value
    is_ai_predicted = representative.source == _GOTENZYMES_SOURCE_LABEL
    all_measurement_ids = tuple(sorted(m.id for m in candidates))
    concentration_observation_ids = tuple(
        dep.observation_id
        for dep in enzyme_concentration.dependencies
        if dep.observation_id is not None
    )

    ai_note = (
        " The underlying Vmax is a GotEnzymes2 AI-predicted value, not an experimental "
        "measurement -- this derived kcat inherits that same non-experimental reliability "
        "tier, never presented as an experimental derivation."
        if is_ai_predicted
        else ""
    )
    return Initialization(
        source=ParameterSource.DERIVED_FROM_MACRO_KINETICS,
        value=kcat_value,
        unit=CANONICAL_UNIT_PER_SEC,
        source_reference=(
            f"kcat=Vmax/[E]_total: Vmax from {representative.source or 'unknown source'} "
            f"({representative.id}); [E]_total from enzyme concentration for protein "
            f"{enzyme_concentration.protein_id} (basis={enzyme_concentration.basis.value})"
        ),
        provenance_refs=(*all_measurement_ids, *concentration_observation_ids),
        uncertainty_text=(
            "Derived (DERIVED_FROM_MACRO_KINETICS) as kcat = Vmax / [E]_total from a "
            f"canonical Vmax of {representative.normalized_value} {CANONICAL_UNIT_NM_PER_S} "
            f"and an enzyme concentration of {enzyme_concentration.value} "
            f"{enzyme_concentration.unit} (basis={enzyme_concentration.basis.value})."
            + ai_note
            + " Exact and unique given these two condition-matched inputs (IDENTIFIABLE). "
            "Requires calibration."
        ),
    )


def resolve_kcat_with_reconstruction(
    kcat_evidence: tuple[CuratedKineticMeasurement, ...],
    vmax_evidence: tuple[CuratedKineticMeasurement, ...],
    enzyme_concentration: EnzymeConcentration | None,
) -> Initialization | None:
    """Derivation B, pre-computed for `app.agent2.parameters.initializer
    .initialize_with_fallback`'s own new `macro_reconstruction` parameter.

    Returns ``None`` (never a fabricated stand-in) when reconstruction is not possible --
    the caller passes this straight through to `initialize_with_fallback`, which already
    treats ``None`` as "nothing to insert at this tier, proceed to heuristic" exactly like
    every other tier's own genuine-absence case. This is deliberately *not* itself the
    ``kcat`` slot's ``Initialization`` -- callers still call `initialize_with_fallback`
    with the raw ``kcat_evidence`` so Derivation A's own "direct kcat always wins, never
    re-derived" guarantee stays entirely inside that function's own existing, unmodified
    precedence chain.
    """
    return reconstruct_kcat_from_vmax_and_concentration(vmax_evidence, enzyme_concentration)


def reconstruct_k_eff_from_kcat_and_km(
    kcat_initialization: Initialization,
    km_initialization: Initialization,
    *,
    molecularity: int,
) -> Initialization | None:
    """Derivation C: the effective second-order rate ``k_eff = kcat/Km``, canonically
    ``per_nMs`` (design doc §3/§5) -- dimensionally valid **only** for a genuine two-
    reactant elementary mass-action encounter in this codebase's own structural model.

    **Why `molecularity == 2`, not `1`:** `heuristic_defaults.mass_action_rate_unit(n)`
    gives `per_sec` for `n == 1` and `per_nMs` only for `n == 2` -- `kcat/Km` is *always*
    `per_nMs` (`[per_sec]/[nM]`), so it can only ever dimensionally seed a mass-action rate
    constant whose own reactant molecularity is exactly 2. This codebase never represents
    the enzyme itself as a reaction participant/species (only curated compounds are
    species), so a single-substrate reaction's own mass-action `k` is unimolecular
    (`per_sec`) in this structural model, not bimolecular -- `kcat/Km` cannot seed it
    without a real unit mismatch. The task's own real motivating example (the malonyl-
    CoA:[acp] S-malonyltransferase reaction, 2 curated reactants) is exactly this
    `molecularity == 2` case. **Never applied for `molecularity >= 3`** (task's own
    explicit "do not apply generically to arbitrary multi-reactant reactions" --
    dimensionally, only 2 reactants ever match `per_nMs` at all).

    Returns ``None`` when either input is not itself a genuine, non-heuristic value
    (`_UNUSABLE_SOURCES`) or `molecularity != 2` -- never a fabricated approximation
    outside its one dimensionally-valid case.
    """
    if molecularity != _K_EFF_ELIGIBLE_MOLECULARITY:
        return None
    if (
        kcat_initialization.source in _UNUSABLE_SOURCES
        or km_initialization.source in _UNUSABLE_SOURCES
    ):
        return None
    if kcat_initialization.value is None or km_initialization.value is None:
        return None
    if km_initialization.value == 0:
        return None

    k_eff_value = kcat_initialization.value / km_initialization.value
    provenance_refs = tuple(
        sorted(set(kcat_initialization.provenance_refs) | set(km_initialization.provenance_refs))
    )
    derived_dependency_sources = (
        ParameterSource.AI_PREDICTED,
        ParameterSource.DERIVED_FROM_MACRO_KINETICS,
    )
    ai_note = (
        " One or both of kcat/Km feeding this derivation are themselves AI-predicted or "
        "already-derived macro-kinetic evidence, not a direct experimental measurement."
        if kcat_initialization.source in derived_dependency_sources
        or km_initialization.source in derived_dependency_sources
        else ""
    )
    return Initialization(
        source=ParameterSource.DERIVED_FROM_MACRO_KINETICS,
        value=k_eff_value,
        unit=CANONICAL_UNIT_PER_NMS,
        source_reference=(
            f"k_eff=kcat/Km ({kcat_initialization.source_reference}, "
            f"{km_initialization.source_reference})"
        ),
        provenance_refs=provenance_refs,
        uncertainty_text=(
            "Derived (DERIVED_FROM_MACRO_KINETICS) as the effective second-order rate "
            f"k_eff = kcat/Km = {kcat_initialization.value} {kcat_initialization.unit} / "
            f"{km_initialization.value} {km_initialization.unit}, valid only as an "
            "approximation for a single, genuinely bimolecular substrate-enzyme encounter "
            "-- never applied to a reaction with three or more reactants."
            + ai_note
            + " Requires calibration."
        ),
    )


def classify_km_kcat_constraint(
    kcat_initialization: Initialization,
    km_initialization: Initialization,
    *,
    reaction_id: str,
    kinetic_law_assignment_id: str,
    kcat_parameter_id: str,
    km_parameter_id: str,
) -> MicroscopicConstraint | None:
    """Derivation D: preserve ``Km = (kr + kcat) / kf`` as an explicit, disclosed
    constraint -- never a chosen ``(kf, kr)`` point (Berra et al. 2025, design doc §1.4/
    §2.1/§3: two equations, three unknowns, exactly one degree of freedom short).

    Applies only to the single-substrate `E + S <=> ES -> E + P` mechanism (the caller is
    responsible for calling this only when `reactant_compound_ids` has exactly one entry --
    the multi-substrate case has no single-`Km` elementary mechanism this constraint even
    names, design doc §2.2's own explicit multi-substrate scope exclusion).

    Returns ``None`` (nothing to disclose) when either `kcat`/`Km` is itself not a genuine,
    non-heuristic value -- there is no real constraint worth naming when one side is
    already a fabricated/absent placeholder.
    """
    if (
        kcat_initialization.source in _UNUSABLE_SOURCES
        or km_initialization.source in _UNUSABLE_SOURCES
    ):
        return None
    if kcat_initialization.value is None or km_initialization.value is None:
        return None

    return MicroscopicConstraint(
        reaction_id=reaction_id,
        kinetic_law_assignment_id=kinetic_law_assignment_id,
        status=IdentifiabilityStatus.PARTIALLY_CONSTRAINED,
        constraint_expression="kf * Km = kr + kcat",
        known_parameter_ids=(kcat_parameter_id, km_parameter_id),
        unresolved_parameter_names=("kf", "kr"),
        explanation=(
            f"kcat ({kcat_initialization.value} {kcat_initialization.unit}) and Km "
            f"({km_initialization.value} {km_initialization.unit}) are both resolved to "
            "real (non-heuristic) values for this single-substrate catalytic context, "
            "which constrains the elementary rate constants kf/kr to the curve "
            "kf * Km = kr + kcat -- but two macroscopic numbers can never algebraically "
            "determine three microscopic ones (Berra, Sommariva, Piana & Caviglia 2025). "
            "No unique (kf, kr) point is asserted; neither is declared as a "
            "ParameterSpecification by this codebase. A future increment could resolve "
            "kf (and, with much lower confidence, kr) given a genuinely independent third "
            "constraint (a transient concentration trajectory or an independently-sourced "
            "thermodynamic equilibrium constant) -- not attempted here."
        ),
    )


__all__ = [
    "classify_km_kcat_constraint",
    "reconstruct_k_eff_from_kcat_and_km",
    "reconstruct_kcat_from_vmax_and_concentration",
    "resolve_kcat_with_reconstruction",
]
