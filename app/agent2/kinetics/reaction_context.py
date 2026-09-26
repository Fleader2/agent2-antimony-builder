"""Kinetic-Measurement Reaction-Context Resolution.

Real Integration Pilot 2 Run 2 found that every real SABIO-RK kinetic
measurement Agent 1 curates for yeast fatty-acyl-CoA synthase (FAS1/FAS2,
EC 2.3.1.86) arrives with ``reaction_id=None`` -- correctly preserved,
correctly disclosed (the "Unresolved Kinetic Evidence Disclosure"
increment's ``KINETIC_MEASUREMENT_REACTION_CONTEXT_UNRESOLVED``
``ModelAssumption``), but never usable by kinetic-law/parameter
assignment. This module asks a narrower question: for which of those
measurements does the *source evidence itself* -- not protein identity,
not the EC number, not ``ReactionEnzyme`` membership, not pathway
membership, not nearest-name matching -- deterministically establish
exactly one curated reaction?

**Core rule**: protein applicability is not reaction applicability. A
measurement is assigned a ``reaction_id`` only when
``resolve_kinetic_measurement_reaction_context`` finds *exactly one*
curated reaction structurally compatible with the measurement's own
resolved compound identity and parameter semantics
(``ReactionContextMatchResult.UNIQUE_MATCH``). Every other outcome leaves
the measurement's ``reaction_id`` untouched at ``None`` -- the existing
"Unresolved Kinetic Evidence Disclosure" ``ModelAssumption`` continues to
cover it exactly as before; this module changes nothing about that
disclosure path.

**Only evidence used**: ``CuratedKineticMeasurement.compound_id`` (the one
field the handoff contract already carries for "which compound this
parameter was measured with respect to") resolved, by *exact* id equality
(never fuzzy/nearest-name matching), against ``FullNetwork.species[]
.source_compound_id``, then against which reactions use that species (or
one of its compartment-instances) with ``ParticipantRole.REACTANT``.
Real, live SABIO-RK inspection (this increment) found ``compound_id``
analogues only ever populated for ``KM``/``KI`` (a Michaelis or
inhibition constant is intrinsically a property of one named ligand);
``VMAX``/``KCAT`` never carry one (they describe the overall catalytic
turnover, not one elementary step) -- see
``docs/13_kinetic_measurement_reaction_context_resolution.md`` §1 for the
full real-data inspection this restriction is based on.
``_COMPOUND_ANCHORED_PARAMETER_TYPES`` encodes this as a hard rule, not an
incidental consequence of today's data being empty: even if a future
source populated ``compound_id`` on a ``VMAX``/``KCAT`` row, this module
must not treat it as reaction-discriminating evidence.

**Not performed here** (out of scope for this increment): reversibility
curation, kinetic fitting, unit conversion, new SABIO-RK parsing, enzyme-
complex inference, and no change whatsoever to
``app.agent2.kinetics.selector``/``app.agent2.parameters.builder`` --
both continue to operate only on measurements that already carry a
``reaction_id`` (whether curated originally or resolved here), an
entirely unmodified code path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from enum import StrEnum

from app.agent2.kinetics.validation import require_full_network
from app.agent2.types import CuratedKineticMeasurement, FullNetwork, ParticipantRole

#: Parameter types for which one named compound is intrinsically the
#: measured ligand (a binding/inhibition constant), never the overall
#: catalytic-turnover parameters (``VMAX``/``KCAT``) -- see module
#: docstring. Deliberately a hard allow-list, not derived from whether
#: ``compound_id`` happens to be populated.
_COMPOUND_ANCHORED_PARAMETER_TYPES = frozenset({"KM", "KI"})


class ReactionContextMatchResult(StrEnum):
    """Conservative matching-result vocabulary for reaction-context resolution.

    Only ``UNIQUE_MATCH`` may ever produce a ``reaction_id`` assignment.
    """

    #: Exactly one curated reaction is structurally compatible with the
    #: measurement's resolved compound identity and parameter semantics.
    UNIQUE_MATCH = "UNIQUE_MATCH"
    #: Two or more curated reactions are compatible; the source evidence
    #: does not discriminate between them, so none is chosen.
    MULTIPLE_COMPATIBLE = "MULTIPLE_COMPATIBLE"
    #: The measurement's resolved compound identity does not appear as a
    #: ``REACTANT`` of any curated reaction (including because the
    #: compound itself is not curated at all).
    NO_MATCH = "NO_MATCH"
    #: The source does not supply evidence this module can search with at
    #: all (no ``compound_id``, or a parameter type never anchored to one
    #: named compound) -- distinct from ``NO_MATCH``, which means the
    #: search ran and found zero candidates.
    INSUFFICIENT_SOURCE_EVIDENCE = "INSUFFICIENT_SOURCE_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ReactionContextResolution:
    """One measurement's reaction-context matching outcome, with its exact evidence trail.

    Produced for every ``CuratedKineticMeasurement`` in the source
    ``FullNetwork`` whose ``reaction_id`` is ``None`` -- a measurement
    that already carries a ``reaction_id`` is not this module's concern
    and never appears here.
    """

    measurement_id: str
    result: ReactionContextMatchResult
    matched_reaction_id: str | None = None
    candidate_reaction_ids: tuple[str, ...] = ()
    compound_id: str | None = None
    parameter_type: str = ""
    evidence: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.result, ReactionContextMatchResult):
            raise TypeError(
                "ReactionContextResolution.result must be a ReactionContextMatchResult, "
                f"got {self.result!r}"
            )
        if self.result is ReactionContextMatchResult.UNIQUE_MATCH:
            if self.matched_reaction_id is None:
                raise ValueError(
                    "ReactionContextResolution with result=UNIQUE_MATCH requires a "
                    "non-None matched_reaction_id"
                )
            if len(self.candidate_reaction_ids) != 1:
                raise ValueError(
                    "ReactionContextResolution with result=UNIQUE_MATCH requires exactly one "
                    f"candidate_reaction_ids entry, got {self.candidate_reaction_ids!r}"
                )
        elif self.matched_reaction_id is not None:
            raise ValueError(
                f"ReactionContextResolution.matched_reaction_id must be None unless "
                f"result=UNIQUE_MATCH, got result={self.result!r}, "
                f"matched_reaction_id={self.matched_reaction_id!r}"
            )


def _species_by_compound_id(network: FullNetwork) -> dict[str, set[str]]:
    species_ids_by_compound: dict[str, set[str]] = defaultdict(set)
    for species in network.species:
        if species.source_compound_id is not None:
            species_ids_by_compound[species.source_compound_id].add(species.species_id)
    return species_ids_by_compound


def _reactant_reactions_by_species(network: FullNetwork) -> dict[str, set[str]]:
    reactions_by_species: dict[str, set[str]] = defaultdict(set)
    for reaction in network.reactions:
        for participant in reaction.participants:
            if participant.role is ParticipantRole.REACTANT:
                reactions_by_species[participant.species_id].add(reaction.reaction_id)
    return reactions_by_species


def _resolve_one(
    measurement: CuratedKineticMeasurement,
    *,
    species_ids_by_compound: dict[str, set[str]],
    reactant_reactions_by_species: dict[str, set[str]],
) -> ReactionContextResolution:
    if (
        measurement.parameter_type not in _COMPOUND_ANCHORED_PARAMETER_TYPES
        or measurement.compound_id is None
    ):
        return ReactionContextResolution(
            measurement_id=measurement.id,
            result=ReactionContextMatchResult.INSUFFICIENT_SOURCE_EVIDENCE,
            compound_id=measurement.compound_id,
            parameter_type=measurement.parameter_type,
            evidence=(
                f"parameter_type={measurement.parameter_type!r} is not compound-anchored, "
                "or compound_id is None -- no deterministic species identity to search with"
                if measurement.compound_id is None
                else f"parameter_type={measurement.parameter_type!r} is never treated as "
                "anchored to one elementary reaction, regardless of compound_id"
            ),
        )

    species_ids = species_ids_by_compound.get(measurement.compound_id, set())
    candidate_reaction_ids: set[str] = set()
    for species_id in species_ids:
        candidate_reaction_ids |= reactant_reactions_by_species.get(species_id, set())
    candidates_sorted = tuple(sorted(candidate_reaction_ids))

    if not candidates_sorted:
        return ReactionContextResolution(
            measurement_id=measurement.id,
            result=ReactionContextMatchResult.NO_MATCH,
            candidate_reaction_ids=(),
            compound_id=measurement.compound_id,
            parameter_type=measurement.parameter_type,
            evidence=(
                f"compound_id={measurement.compound_id!r} is not a REACTANT of any curated "
                "reaction (including because it is not a curated compound at all)"
            ),
        )
    if len(candidates_sorted) == 1:
        return ReactionContextResolution(
            measurement_id=measurement.id,
            result=ReactionContextMatchResult.UNIQUE_MATCH,
            matched_reaction_id=candidates_sorted[0],
            candidate_reaction_ids=candidates_sorted,
            compound_id=measurement.compound_id,
            parameter_type=measurement.parameter_type,
            evidence=(
                f"compound_id={measurement.compound_id!r} is a REACTANT of exactly one curated "
                f"reaction, {candidates_sorted[0]!r} (parameter_type="
                f"{measurement.parameter_type!r})"
            ),
        )
    return ReactionContextResolution(
        measurement_id=measurement.id,
        result=ReactionContextMatchResult.MULTIPLE_COMPATIBLE,
        candidate_reaction_ids=candidates_sorted,
        compound_id=measurement.compound_id,
        parameter_type=measurement.parameter_type,
        evidence=(
            f"compound_id={measurement.compound_id!r} is a REACTANT of {len(candidates_sorted)} "
            f"curated reactions ({', '.join(candidates_sorted)}) -- not discriminable from "
            "source evidence alone"
        ),
    )


def resolve_kinetic_measurement_reaction_context(
    network: FullNetwork,
) -> tuple[ReactionContextResolution, ...]:
    """Deterministically classify every unresolved kinetic measurement's reaction context.

    Only ``network.kinetic_measurements`` entries with ``reaction_id is
    None`` are considered -- a measurement Agent 1 (or an earlier resolve)
    already attributed to a reaction is untouched and produces no
    resolution here. Order-independent: measurements are processed in
    ``measurement.id`` order and every intermediate lookup uses sets, so
    the result does not depend on ``network.kinetic_measurements``'
    input order.
    """
    require_full_network(network)
    species_ids_by_compound = _species_by_compound_id(network)
    reactant_reactions_by_species = _reactant_reactions_by_species(network)

    return tuple(
        _resolve_one(
            measurement,
            species_ids_by_compound=species_ids_by_compound,
            reactant_reactions_by_species=reactant_reactions_by_species,
        )
        for measurement in sorted(network.kinetic_measurements, key=lambda m: m.id)
        if measurement.reaction_id is None
    )


def apply_resolved_reaction_context(
    network: FullNetwork, resolutions: tuple[ReactionContextResolution, ...]
) -> FullNetwork:
    """Return a new ``FullNetwork`` with every ``UNIQUE_MATCH`` measurement's ``reaction_id`` set.

    Every other field of ``network`` -- including every other measurement,
    every reaction, every species -- is carried forward unchanged.
    Non-``UNIQUE_MATCH`` resolutions are not applied: those measurements
    keep ``reaction_id=None``, exactly as the "Unresolved Kinetic Evidence
    Disclosure" increment's ``build_model_assumptions`` already expects.
    Never touches ``value``/``unit``/any other field -- only ``reaction_id``.
    """
    require_full_network(network)
    matched_reaction_id_by_measurement_id = {
        resolution.measurement_id: resolution.matched_reaction_id
        for resolution in resolutions
        if resolution.result is ReactionContextMatchResult.UNIQUE_MATCH
    }
    if not matched_reaction_id_by_measurement_id:
        return network

    updated_measurements = tuple(
        replace(
            measurement, reaction_id=matched_reaction_id_by_measurement_id[measurement.id]
        )
        if measurement.id in matched_reaction_id_by_measurement_id
        else measurement
        for measurement in network.kinetic_measurements
    )
    return replace(network, kinetic_measurements=updated_measurements)


__all__ = [
    "ReactionContextMatchResult",
    "ReactionContextResolution",
    "apply_resolved_reaction_context",
    "resolve_kinetic_measurement_reaction_context",
]
