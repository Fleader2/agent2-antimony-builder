"""Quantitative Context Resolution and Derived Enzyme Concentration.

``resolve_enzyme_concentrations`` is this package's one public entry point:
given a ``FullNetwork`` (already carrying ``quantitative_observations``/
``experimental_contexts`` -- see ``app.agent2.types.FullNetwork``'s own module
docstring), deterministically derives at most one canonical-nM enzyme
concentration per protein, using the task's own fixed six-tier precedence:

    1. experiment-specific protein concentration
    2. experiment-specific protein abundance + experiment-specific cell volume
    3. reference protein concentration
    4. reference protein abundance + compatible reference cell volume
    5. reference protein abundance + explicit assumed 0.1 pL cell volume
    6. unresolved

**A tier is only ever consulted when the previous tier found a genuine,
complete absence of usable candidates** -- mirrors
``app.agent2.parameters.initializer.initialize_with_fallback``'s own,
identically-reasoned precedence policy exactly. Two or more candidates at what
would otherwise be the winning tier that *disagree* (different value, or a
different derived concentration for tiers 2/4's own abundance/volume pairs)
never silently fall through to a weaker tier and are never averaged or
arbitrarily chosen -- the protein is reported unresolved
(``QuantitativeContextReasonCode.AMBIGUOUS_CANDIDATE_OBSERVATIONS``), exactly
as disagreeing curated kinetic evidence already is by that sibling package.

**Tier 5 only ever consumes ``REFERENCE_BASELINE`` abundance, never
``EXPERIMENT_SPECIFIC``** -- this is the task's own literal precedence order,
not a simplification: an experiment-specific abundance measurement with no
matching experiment-specific (or compatible reference) cell-volume observation
stays unresolved rather than being paired with the generic 0.1 pL assumption,
which is reserved for the more broadly representative reference-baseline case.

**Derivation is protein-level only** (task Sec 6): no allocation across enzyme
states, PTM states, complexes, or isoforms is ever attempted -- the protein-id
set this function resolves against comes from
``FullNetwork.enzyme_associations[].protein_id`` (deduplicated), never from
``FullNetwork.enzyme_states``.

**An identical ``experimental_context_id`` on both sides of an abundance/cell-
volume pair is always ``EXACT_CONTEXT``, never re-derived via
``policy.classify_context_compatibility``'s own field-by-field comparison.**
That comparison is reserved for two *different* context rows; applying it to a
context compared with itself would (incorrectly) report ``CONTEXT_UNKNOWN``
whenever the row has no populated detail fields at all -- a real, common case
(SGD's own reference context reports no strain/medium/temperature/pH
whatsoever; see ``docs/16_quantitative_context_resolution.md`` §5).

Pure and deterministic: no database, no filesystem, no network access, no
randomness. Calling this function twice with the same ``FullNetwork`` always
returns an equal ``QuantitativeContextResolutionSet``.
"""

from __future__ import annotations

from decimal import Decimal

from app.agent2.quantitative_context import policy
from app.agent2.quantitative_context.types import (
    ContextCompatibility,
    QuantitativeContextReasonCode,
    QuantitativeContextResolutionOutcome,
    QuantitativeContextResolutionSet,
)
from app.agent2.quantitative_context.validation import require_full_network
from app.agent2.types import (
    CuratedExperimentalContext,
    CuratedQuantitativeObservation,
    EnzymeConcentration,
    EnzymeConcentrationBasis,
    EnzymeConcentrationDependency,
    FullNetwork,
)
from app.agent2.version import QUANTITATIVE_CONTEXT_POLICY_VERSION


def _protein_ids_from_network(network: FullNetwork) -> tuple[str, ...]:
    """Every distinct protein id this network's own catalytic structure names --
    ``ReactionEnzymeAssociation.protein_id`` (never a complex id, never inferred from an
    enzyme state alone), deterministically sorted."""
    return tuple(
        sorted(
            {
                assoc.protein_id
                for assoc in network.enzyme_associations
                if assoc.protein_id is not None
            }
        )
    )


def _context_by_id(network: FullNetwork) -> dict[str, CuratedExperimentalContext]:
    return {ctx.id: ctx for ctx in network.experimental_contexts}


def _resolve_direct_concentration_tier(
    protein_id: str,
    candidates: tuple[CuratedQuantitativeObservation, ...],
    *,
    basis: EnzymeConcentrationBasis,
    policy_version: str,
) -> QuantitativeContextResolutionOutcome | None:
    """Tiers 1/3: a directly-usable ``PROTEIN_CONCENTRATION`` observation, already in nM.

    Returns ``None`` when ``candidates`` is empty -- a genuine absence, the caller falls
    through to the next tier. Returns an ``AMBIGUOUS_CANDIDATE_OBSERVATIONS`` outcome
    (never ``None``) when two or more candidates disagree -- this is the final word for
    this protein, never a fallthrough.
    """
    if not candidates:
        return None
    values = {policy.usable_concentration_nm(o) for o in candidates}
    if len(values) > 1:
        return QuantitativeContextResolutionOutcome(
            protein_id=protein_id,
            unresolved_reason_code=QuantitativeContextReasonCode.AMBIGUOUS_CANDIDATE_OBSERVATIONS.value,
            unresolved_explanation=(
                f"{len(candidates)} candidate protein-concentration observations for "
                f"protein {protein_id!r} report different nM values "
                f"({sorted(str(v) for v in values)}); no value was chosen."
            ),
        )
    representative = sorted(candidates, key=lambda o: o.id)[0]
    value = policy.usable_concentration_nm(representative)
    assert value is not None  # guaranteed by the membership check building `candidates`
    concentration = EnzymeConcentration(
        protein_id=protein_id,
        value=value,
        basis=basis,
        policy_version=policy_version,
        dependencies=(
            EnzymeConcentrationDependency(
                role="concentration_input", observation_id=representative.id
            ),
        ),
        experimental_context_id=representative.experimental_context_id,
        notes=(
            f"Direct protein concentration from observation {representative.id!r} "
            f"(evidence_class={representative.evidence_class})."
        ),
    )
    return QuantitativeContextResolutionOutcome(protein_id=protein_id, concentration=concentration)


def _resolve_abundance_volume_tier(
    protein_id: str,
    abundance_candidates: tuple[CuratedQuantitativeObservation, ...],
    volume_candidates: tuple[CuratedQuantitativeObservation, ...],
    *,
    contexts: dict[str, CuratedExperimentalContext],
    basis: EnzymeConcentrationBasis,
    policy_version: str,
) -> QuantitativeContextResolutionOutcome | None:
    """Tiers 2/4: derive from every *compatible* (abundance, cell-volume) pair -- an
    incompatible pair (task Sec 5: "do not combine incompatible experiment contexts") is
    silently excluded from consideration here, never itself a reason to stop; only two or
    more *compatible* pairs producing genuinely different derived concentrations stop the
    resolution as ambiguous.

    Returns ``None`` when no compatible pair exists at all (including when one or both
    candidate lists are empty) -- the caller falls through to the next tier.
    """
    if not abundance_candidates or not volume_candidates:
        return None

    pairs: list[
        tuple[
            CuratedQuantitativeObservation,
            CuratedQuantitativeObservation,
            Decimal,
            ContextCompatibility,
        ]
    ] = []
    for abundance_obs in abundance_candidates:
        abundance_context_id = abundance_obs.experimental_context_id
        abundance_context = (
            contexts.get(abundance_context_id) if abundance_context_id is not None else None
        )
        abundance_value = policy.usable_abundance_molecules_per_cell(abundance_obs)
        assert abundance_value is not None
        for volume_obs in volume_candidates:
            volume_context_id = volume_obs.experimental_context_id
            if abundance_context_id is not None and abundance_context_id == volume_context_id:
                # The identical experimental_context_id on both sides is, by definition, the
                # identical curated context row -- never re-derived via field-by-field
                # comparison, which would otherwise (incorrectly) report CONTEXT_UNKNOWN for a
                # context row with no populated detail fields at all (a real, common case: SGD's
                # own reference context reports no strain/medium/temperature/pH whatsoever).
                compatibility = ContextCompatibility.EXACT_CONTEXT
            else:
                volume_context = (
                    contexts.get(volume_context_id) if volume_context_id is not None else None
                )
                compatibility = policy.classify_context_compatibility(
                    abundance_context, volume_context
                )
            if compatibility not in policy.COMBINABLE_CONTEXT_COMPATIBILITY:
                continue
            volume_value = policy.usable_cell_volume_pl(volume_obs)
            assert volume_value is not None
            derived = policy.derive_concentration_nm(
                abundance_molecules_per_cell=abundance_value, cell_volume_pl=volume_value
            )
            pairs.append((abundance_obs, volume_obs, derived, compatibility))

    if not pairs:
        return None

    distinct_values = {derived for _, _, derived, _ in pairs}
    if len(distinct_values) > 1:
        return QuantitativeContextResolutionOutcome(
            protein_id=protein_id,
            unresolved_reason_code=QuantitativeContextReasonCode.AMBIGUOUS_CANDIDATE_OBSERVATIONS.value,
            unresolved_explanation=(
                f"{len(pairs)} compatible abundance/cell-volume combinations for protein "
                f"{protein_id!r} produce different derived concentrations "
                f"({sorted(str(v) for v in distinct_values)}); no value was chosen."
            ),
        )

    abundance_obs, volume_obs, derived, compatibility = sorted(
        pairs, key=lambda p: (p[0].id, p[1].id)
    )[0]
    concentration = EnzymeConcentration(
        protein_id=protein_id,
        value=derived,
        basis=basis,
        policy_version=policy_version,
        dependencies=(
            EnzymeConcentrationDependency(role="abundance_input", observation_id=abundance_obs.id),
            EnzymeConcentrationDependency(
                role="cell_volume_input", observation_id=volume_obs.id
            ),
        ),
        experimental_context_id=abundance_obs.experimental_context_id,
        notes=(
            f"Derived from abundance observation {abundance_obs.id!r} and cell-volume "
            f"observation {volume_obs.id!r} (context compatibility: {compatibility.value})."
        ),
    )
    return QuantitativeContextResolutionOutcome(protein_id=protein_id, concentration=concentration)


def _resolve_assumed_volume_tier(
    protein_id: str,
    abundance_candidates: tuple[CuratedQuantitativeObservation, ...],
    *,
    assumed_cell_volume_pl: Decimal,
    policy_version: str,
) -> QuantitativeContextResolutionOutcome | None:
    """Tier 5: reference abundance + the explicit assumed cell volume (never a curated
    measurement). Returns ``None`` when ``abundance_candidates`` is empty."""
    if not abundance_candidates:
        return None
    values = {policy.usable_abundance_molecules_per_cell(o) for o in abundance_candidates}
    if len(values) > 1:
        return QuantitativeContextResolutionOutcome(
            protein_id=protein_id,
            unresolved_reason_code=QuantitativeContextReasonCode.AMBIGUOUS_CANDIDATE_OBSERVATIONS.value,
            unresolved_explanation=(
                f"{len(abundance_candidates)} reference abundance observations for "
                f"protein {protein_id!r} report different values "
                f"({sorted(str(v) for v in values)}); no value was chosen."
            ),
        )
    representative = sorted(abundance_candidates, key=lambda o: o.id)[0]
    abundance_value = policy.usable_abundance_molecules_per_cell(representative)
    assert abundance_value is not None
    derived = policy.derive_concentration_nm(
        abundance_molecules_per_cell=abundance_value, cell_volume_pl=assumed_cell_volume_pl
    )
    concentration = EnzymeConcentration(
        protein_id=protein_id,
        value=derived,
        basis=EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME,
        policy_version=policy_version,
        dependencies=(
            EnzymeConcentrationDependency(role="abundance_input", observation_id=representative.id),
            EnzymeConcentrationDependency(
                role="cell_volume_input",
                assumption_notes=(
                    "No compatible cell-volume observation available; assumed reference "
                    f"yeast cell volume of {assumed_cell_volume_pl} pL."
                ),
            ),
        ),
        experimental_context_id=representative.experimental_context_id,
        assumption_reason_codes=(
            QuantitativeContextReasonCode.REFERENCE_CELL_VOLUME_ASSUMED.value,
        ),
        notes=(
            f"Derived from reference abundance observation {representative.id!r} using an "
            f"explicit assumed cell volume of {assumed_cell_volume_pl} pL "
            "(REFERENCE_CELL_VOLUME_ASSUMED) -- never a curated cell-volume measurement."
        ),
    )
    return QuantitativeContextResolutionOutcome(protein_id=protein_id, concentration=concentration)


def _resolve_one_protein(
    protein_id: str,
    *,
    observations: tuple[CuratedQuantitativeObservation, ...],
    contexts: dict[str, CuratedExperimentalContext],
    experiment_volumes: tuple[CuratedQuantitativeObservation, ...],
    reference_volumes: tuple[CuratedQuantitativeObservation, ...],
    assumed_cell_volume_pl: Decimal,
    policy_version: str,
) -> QuantitativeContextResolutionOutcome:
    protein_observations = tuple(o for o in observations if o.protein_id == protein_id)
    concentration_observations = tuple(
        o for o in protein_observations if policy.usable_concentration_nm(o) is not None
    )
    abundance_observations = tuple(
        o
        for o in protein_observations
        if policy.usable_abundance_molecules_per_cell(o) is not None
    )

    tier1 = tuple(
        o
        for o in concentration_observations
        if o.evidence_class == policy.EVIDENCE_CLASS_EXPERIMENT_SPECIFIC
    )
    outcome = _resolve_direct_concentration_tier(
        protein_id,
        tier1,
        basis=EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_CONCENTRATION,
        policy_version=policy_version,
    )
    if outcome is not None:
        return outcome

    tier2_abundance = tuple(
        o
        for o in abundance_observations
        if o.evidence_class == policy.EVIDENCE_CLASS_EXPERIMENT_SPECIFIC
    )
    outcome = _resolve_abundance_volume_tier(
        protein_id,
        tier2_abundance,
        experiment_volumes,
        contexts=contexts,
        basis=EnzymeConcentrationBasis.EXPERIMENT_SPECIFIC_ABUNDANCE_AND_VOLUME,
        policy_version=policy_version,
    )
    if outcome is not None:
        return outcome

    tier3 = tuple(
        o
        for o in concentration_observations
        if o.evidence_class == policy.EVIDENCE_CLASS_REFERENCE_BASELINE
    )
    outcome = _resolve_direct_concentration_tier(
        protein_id,
        tier3,
        basis=EnzymeConcentrationBasis.REFERENCE_CONCENTRATION,
        policy_version=policy_version,
    )
    if outcome is not None:
        return outcome

    tier4_abundance = tuple(
        o
        for o in abundance_observations
        if o.evidence_class == policy.EVIDENCE_CLASS_REFERENCE_BASELINE
    )
    outcome = _resolve_abundance_volume_tier(
        protein_id,
        tier4_abundance,
        reference_volumes,
        contexts=contexts,
        basis=EnzymeConcentrationBasis.REFERENCE_ABUNDANCE_AND_COMPATIBLE_VOLUME,
        policy_version=policy_version,
    )
    if outcome is not None:
        return outcome

    outcome = _resolve_assumed_volume_tier(
        protein_id,
        tier4_abundance,
        assumed_cell_volume_pl=assumed_cell_volume_pl,
        policy_version=policy_version,
    )
    if outcome is not None:
        return outcome

    return QuantitativeContextResolutionOutcome(
        protein_id=protein_id,
        unresolved_reason_code=QuantitativeContextReasonCode.PROTEIN_CONCENTRATION_UNRESOLVED.value,
        unresolved_explanation=(
            f"No usable protein concentration, or protein-abundance-plus-cell-volume "
            f"combination (real or assumed), exists for protein {protein_id!r}."
        ),
    )


def resolve_enzyme_concentrations(
    network: FullNetwork,
    *,
    protein_ids: tuple[str, ...] | None = None,
    assumed_cell_volume_pl: Decimal = policy.DEFAULT_ASSUMED_CELL_VOLUME_PL,
    policy_version: str = QUANTITATIVE_CONTEXT_POLICY_VERSION,
) -> QuantitativeContextResolutionSet:
    """Resolve one ``EnzymeConcentration`` (or a disclosed unresolved reason) for every
    protein in ``protein_ids`` -- defaulting to every protein
    ``network.enzyme_associations`` names (see ``_protein_ids_from_network``) when
    ``protein_ids`` is omitted.

    ``assumed_cell_volume_pl`` defaults to the task's own 0.1 pL reference assumption
    (``policy.DEFAULT_ASSUMED_CELL_VOLUME_PL``) but is an explicit parameter, never a
    hidden constant, so a future increment covering a different organism's own
    documented reference cell volume needs no code change here.
    """
    require_full_network(network)
    if not isinstance(assumed_cell_volume_pl, Decimal):
        raise TypeError(
            f"assumed_cell_volume_pl must be a Decimal, got {assumed_cell_volume_pl!r}"
        )

    resolved_protein_ids = (
        tuple(sorted(set(protein_ids)))
        if protein_ids is not None
        else _protein_ids_from_network(network)
    )
    contexts = _context_by_id(network)

    experiment_volumes = tuple(
        o
        for o in network.quantitative_observations
        if o.evidence_class == policy.EVIDENCE_CLASS_EXPERIMENT_SPECIFIC
        and policy.usable_cell_volume_pl(o) is not None
    )
    reference_volumes = tuple(
        o
        for o in network.quantitative_observations
        if o.evidence_class == policy.EVIDENCE_CLASS_REFERENCE_BASELINE
        and policy.usable_cell_volume_pl(o) is not None
    )

    outcomes = tuple(
        _resolve_one_protein(
            protein_id,
            observations=network.quantitative_observations,
            contexts=contexts,
            experiment_volumes=experiment_volumes,
            reference_volumes=reference_volumes,
            assumed_cell_volume_pl=assumed_cell_volume_pl,
            policy_version=policy_version,
        )
        for protein_id in resolved_protein_ids
    )

    return QuantitativeContextResolutionSet(
        network_id=network.network_id, policy_version=policy_version, outcomes=outcomes
    )


__all__ = ["resolve_enzyme_concentrations"]
