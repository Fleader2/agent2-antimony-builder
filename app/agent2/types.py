"""Agent 2 core domain contracts (Increment 1: architecture and contracts only).

Every type in this module is an immutable, self-validating data contract.
None of them is produced by any real algorithm yet -- there is no network
assembly, no kinetic-law assignment, no boundary heuristic, no module
partitioning, and no Antimony generation in this repository yet (see
``docs/03_increment_1_specification.md``, now marked implemented for its
contract scope, and ``docs/04_core_domain_contracts.md`` for the full
contract reference). Validation here is limited to structural checks
(types, non-empty required fields, uniqueness, and cross-reference
integrity) -- it never encodes a scientific or heuristic judgment.

Sections, in the order data flows through the (future) pipeline:

1. **Agent 1 handoff** -- ``Agent1CuratedKnowledgeViewContract`` and its
   nested ``Curated*`` records. Agent 2's own local, decoupled
   representation of the Agent 1 handoff
   (``docs/02_agent1_handoff_contract.md``). This module never imports
   Agent 1's runtime package.
2. **Shared enums** -- ``ParameterSource``, ``BoundaryLikelihood``,
   ``BoundaryParameterBasis``, ``KineticLawType``,
   ``KineticLawAssignmentSource`` (relocated here from
   ``app.agent2.kinetics.types`` in an Increment 8 pre-commit revision,
   still re-exported there unchanged), ``ParticipantRole``,
   ``ModuleInterfaceRole``, ``CompartmentSourceScope``. Defined early
   because later structural types reference them.
3. **Full-network structural domain** -- ``CompartmentSpecification``,
   ``SpeciesSpecification``, ``ReactionParticipantSpecification``,
   ``ReactionSpecification``, ``ReactionEnzymeAssociation``,
   ``FullNetwork``. The complete, authoritative network Agent 2 assembles
   from an ``Agent1CuratedKnowledgeViewContract``
   (``app.agent2.network.assemble_full_network``, Increment 2) -- this
   module still only defines the shape and its internal reference-
   integrity rules, never the assembly algorithm itself. **Increment 2**
   additionally attached curated regulation
   (``FullNetwork.regulatory_interactions: tuple[CuratedRegulatoryInteraction, ...]``)
   and curated kinetic measurements
   (``FullNetwork.kinetic_measurements: tuple[CuratedKineticMeasurement, ...]``)
   directly, reusing the Agent 1 handoff's own record types unchanged
   (§1) rather than inventing near-duplicate network-level mirrors --
   both are supporting evidence attached to the network, never
   reinterpreted, classified, or converted into a structural element or a
   ``ParameterSpecification``.
4. **Kinetics and parameters** -- ``KineticLawSpecification``,
   ``ParameterSpecification``. Structural declarations only: no fitting,
   no estimation, no expression evaluation.
5. **Module decomposition domain** -- ``BoundaryAssessment``,
   ``ModuleBoundaryInterface``, ``ModuleSpecification``,
   ``ModuleDecomposition``. No heuristic computation exists yet -- these
   are the contracts a future boundary-heuristic rule set will populate.
6. **ModelAssumption** -- a structured, categorized assumption record for
   cross-cutting, model-level disclosures (individual structural types
   keep their own lightweight free-text ``assumptions`` tuples for local
   disclosures; this is the additional, referenceable layer).
7. **ModelSpecification** -- the top-level, authoritative contract that
   references everything above it and enforces full internal reference
   integrity. Never performs Agent 3-level mass-balance, connectivity,
   unit-consistency, or conservation-law analysis.
8. **Antimony artifact contracts** -- ``FullAntimonyArtifact``,
   ``ModuleAntimonyArtifact``, ``AntimonyArtifactReadiness``. The
   generator itself (``app.agent2.antimony``, Increment 9) lives outside
   this module; these remain data contracts only.
9. **Agent2OutputPackage** -- the final output envelope, with its own
   cross-artifact reference-integrity rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agent2.version import AGENT2_CONTRACT_VERSION


def _require_non_empty_str(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _clean_optional_str(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str or None, got {value!r}")
    stripped = value.strip()
    return stripped or None


def _require_str_tuple(value: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


def _require_unique(ids: tuple[str, ...], *, field_name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in ids:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    if duplicates:
        raise ValueError(f"{field_name} must be unique, found duplicate(s): {sorted(duplicates)}")


def _require_known(ids: tuple[str, ...], known: set[str], *, field_name: str) -> None:
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ValueError(f"{field_name} references unknown id(s): {unknown}")


def _require_tuple_of(value: tuple, item_type: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(
            f"{field_name} must be a tuple of {item_type.__name__}, got {value!r}"
        )
    return value


def _require_decimal_or_none(value: Decimal | None, *, field_name: str) -> Decimal | None:
    if value is not None and not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal or None, got {value!r}")
    return value


def _require_bool_or_none(value: bool | None, *, field_name: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool or None, got {value!r}")
    return value


# =================================================================================================
# 1. Agent 1 handoff: local, decoupled representation
# =================================================================================================


@dataclass(frozen=True, slots=True)
class CuratedCompartment:
    """One compartment, exactly as named by Agent 1. See handoff contract §4."""

    id: str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))


@dataclass(frozen=True, slots=True)
class CuratedCompound:
    """One compound. Two compounds are never assumed distinct or identical by name alone."""

    id: str
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))


@dataclass(frozen=True, slots=True)
class CuratedReaction:
    """One reaction. ``reversible`` is ``None`` when Agent 1 did not record it -- never guessed."""

    id: str
    name: str
    reversible: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))


@dataclass(frozen=True, slots=True)
class CuratedReactionParticipant:
    """One reactant/product/modifier of a reaction.

    ``role`` never distinguishes a cofactor from any other participant --
    Agent 1 v1 does not classify cofactors separately (handoff contract §6).
    """

    reaction_id: str
    compound_id: str
    role: str
    stoichiometry: Decimal
    compartment_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        object.__setattr__(
            self, "compound_id", _require_non_empty_str(self.compound_id, field_name="compound_id")
        )
        object.__setattr__(self, "role", _require_non_empty_str(self.role, field_name="role"))
        if not isinstance(self.stoichiometry, Decimal):
            raise TypeError(
                f"CuratedReactionParticipant.stoichiometry must be a Decimal, "
                f"got {self.stoichiometry!r}"
            )


@dataclass(frozen=True, slots=True)
class CuratedReactionEnzymeAssociation:
    """One reaction-enzyme association. Exactly one of ``protein_id``/``complex_id``/
    ``enzyme_state_id`` is expected.

    **Discovered gap, fixed in Agent 2 Increment 3**: Agent 1's own
    ``ReactionEnzyme`` row gained a third, optional catalytic target,
    ``enzyme_state_id``, in Agent 1.x Increment B
    (``AGENT1_HANDOFF_VERSION`` "1.1" -> "1.2"), but this local mirror was
    not updated to carry it at the time -- Agent 1's real
    ``Agent1CuratedKnowledgeView.reaction_enzyme_associations`` exposes raw
    ``ReactionEnzyme`` rows (which already had the column), so the gap was
    only in this repository's own decoupled representation. Fixed here by
    addition, not redesign: existing two-target rows are unaffected.
    """

    reaction_id: str
    protein_id: str | None = None
    complex_id: str | None = None
    enzyme_state_id: str | None = None
    relationship: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )


@dataclass(frozen=True, slots=True)
class CuratedRegulatoryInteraction:
    """One regulatory interaction, exactly as persisted -- never assumed complete or absent.

    See handoff contract §6: Agent 1 v1's regulation pipeline is
    schema-ready, not curated end-to-end -- an empty
    ``regulatory_interactions`` tuple on the parent view means "none
    currently curated," never "no regulation exists."
    """

    id: str
    regulator_type: str
    target_type: str
    effect: str
    regulator_id: str | None = None
    target_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "regulator_type",
            _require_non_empty_str(self.regulator_type, field_name="regulator_type"),
        )
        object.__setattr__(
            self, "target_type", _require_non_empty_str(self.target_type, field_name="target_type")
        )
        object.__setattr__(self, "effect", _require_non_empty_str(self.effect, field_name="effect"))


@dataclass(frozen=True, slots=True)
class CuratedClaim:
    """One human-accepted claim. Being accepted means reviewed, not proven correct."""

    id: str
    subject_type: str
    predicate: str
    subject_id: str | None = None
    object_type: str | None = None
    object_id: str | None = None
    value_text: str | None = None
    value_numeric: Decimal | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "subject_type",
            _require_non_empty_str(self.subject_type, field_name="subject_type"),
        )
        object.__setattr__(
            self, "predicate", _require_non_empty_str(self.predicate, field_name="predicate")
        )
        if self.value_numeric is not None and not isinstance(self.value_numeric, Decimal):
            raise TypeError(
                f"CuratedClaim.value_numeric must be a Decimal or None, got {self.value_numeric!r}"
            )


@dataclass(frozen=True, slots=True)
class CuratedEvidence:
    """One evidence record supporting a curated claim."""

    id: str
    claim_id: str
    publication_reference: str | None = None
    quoted_support: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self, "claim_id", _require_non_empty_str(self.claim_id, field_name="claim_id")
        )


@dataclass(frozen=True, slots=True)
class CuratedConfidenceSummary:
    """One claim's confidence, exposed verbatim from Agent 1. Never recomputed by Agent 2."""

    claim_id: str
    status: str
    confidence_score: Decimal | None = None
    confidence_class: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "claim_id", _require_non_empty_str(self.claim_id, field_name="claim_id")
        )
        object.__setattr__(self, "status", _require_non_empty_str(self.status, field_name="status"))
        if self.confidence_score is not None and not isinstance(self.confidence_score, Decimal):
            raise TypeError(
                "CuratedConfidenceSummary.confidence_score must be a Decimal or None, "
                f"got {self.confidence_score!r}"
            )


@dataclass(frozen=True, slots=True)
class CuratedKineticMeasurement:
    """One independently-sourced kinetic measurement, exactly as curated by Agent 1.

    Added in Agent 1.x Increment A (``AGENT1_HANDOFF_VERSION`` "1.0" ->
    "1.1"). Agent 1 curates *reported* kinetic facts -- Agent 2 decides
    model usage, kinetic-law mapping, and parameter declaration (see
    ``docs/02_agent1_handoff_contract.md`` §9A). **This type is never
    auto-converted into a ``ParameterSpecification`` by anything in this
    module.** That mapping decision -- which curated measurement
    initializes which declared parameter, for which catalytic context --
    is implemented explicitly by ``app.agent2.parameters`` (Increment 5,
    Parameter Declaration / Initialization; see
    ``docs/08_parameter_declaration_initialization.md``), never implicitly
    here: a ``ParameterSpecification`` only ever receives
    ``ParameterSource.CURATED``/``LITERATURE_DERIVED`` through that
    package's own explicit, deterministic mapping policy -- never merely
    because a ``CuratedKineticMeasurement`` with a matching reaction/
    parameter type happens to exist somewhere in the handoff.

    ``value``/``unit`` are the as-reported figures; ``normalized_value``/
    ``normalized_unit`` are ``None`` for every measurement in this handoff
    version -- Agent 1 has no unit-conversion framework yet. No field here
    is ever averaged, converted, or reinterpreted from what Agent 1
    reported.

    **``protein_id`` is a legacy convenience field, not authoritative for
    protein applicability -- use ``protein_ids`` instead** (Increment: see
    the "Unresolved Kinetic Evidence Disclosure" entry below,
    ``AGENT1_HANDOFF_VERSION`` "1.2" -> "1.3"). Agent 1's own real handoff
    (Agent 1.x Increment C.6) can now legitimately report that one
    measurement is applicable to *more than one* protein (confirmed live,
    Real Integration Pilot 1 Run 7/8: yeast's real FAS1/FAS2 heterodimer,
    sharing one EC number, both independently discovering the identical
    external source record) -- ``protein_id``'s own single-value shape can
    only ever record one of them. ``protein_ids`` is the authoritative,
    deterministically-ordered, complete set; ``protein_id`` is kept
    unmodified, exactly as before, purely so existing single-protein-context
    callers/tests/catalytic-context-matching code (``app.agent2.kinetics
    .selector``, ``app.agent2.parameters.builder`` -- both operate only on
    already reaction-attributed measurements, an entirely different,
    unaffected population, and neither was changed) continue to work without
    modification. This mirrors Agent 1's own, identically-named,
    identically-reasoned ``protein_id``/``protein_ids`` split exactly (Agent
    1.x Increment C.6, ``app.agent1.types.CuratedKineticMeasurement``) --
    never invented independently here.
    """

    id: str
    parameter_type: str
    value: Decimal
    unit: str
    reaction_id: str | None = None
    protein_id: str | None = None
    complex_id: str | None = None
    compound_id: str | None = None
    organism_id: str | None = None
    publication_id: str | None = None
    reported_parameter_type: str | None = None
    normalized_value: Decimal | None = None
    normalized_unit: str | None = None
    strain: str | None = None
    temperature_c: Decimal | None = None
    ph: Decimal | None = None
    reported_rate_law: str | None = None
    source: str | None = None
    source_id: str | None = None
    confidence_score: Decimal | None = None
    confidence_class: str | None = None
    notes: str | None = None
    #: Agent 1.x Increment B (``AGENT1_HANDOFF_VERSION`` "1.1" -> "1.2").
    #: ``None`` unless this measurement was specifically reported for one
    #: defined ``CuratedEnzymeState`` -- never applicable to the parent
    #: protein/complex generally, or to any other state, when set.
    enzyme_state_id: str | None = None
    #: ``AGENT1_HANDOFF_VERSION`` "1.2" -> "1.3". **The authoritative record
    #: of every protein this measurement is applicable to** -- always a
    #: superset of ``protein_id`` (see that field's own comment above).
    #: Deterministically sorted (never input-order-dependent); never
    #: arbitrarily narrowed to one entry. When left at its default (``()``)
    #: and ``protein_id`` is set, ``__post_init__`` derives
    #: ``(protein_id,)`` automatically -- existing single-protein
    #: construction (``CuratedKineticMeasurement(protein_id=...)`` with no
    #: ``protein_ids`` argument at all) needs no change and remains fully
    #: backward compatible. Never used to infer reaction attribution by
    #: anything in this module: protein applicability is not evidence of
    #: reaction applicability (see ``docs/07_kinetic_law_assignment.md``).
    protein_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "parameter_type",
            _require_non_empty_str(self.parameter_type, field_name="parameter_type"),
        )
        if not isinstance(self.value, Decimal):
            raise TypeError(
                f"CuratedKineticMeasurement.value must be a Decimal, got {self.value!r}"
            )
        object.__setattr__(self, "unit", _require_non_empty_str(self.unit, field_name="unit"))
        object.__setattr__(
            self,
            "normalized_value",
            _require_decimal_or_none(self.normalized_value, field_name="normalized_value"),
        )
        object.__setattr__(
            self,
            "temperature_c",
            _require_decimal_or_none(self.temperature_c, field_name="temperature_c"),
        )
        object.__setattr__(self, "ph", _require_decimal_or_none(self.ph, field_name="ph"))
        object.__setattr__(
            self,
            "confidence_score",
            _require_decimal_or_none(self.confidence_score, field_name="confidence_score"),
        )
        protein_ids = _require_str_tuple(self.protein_ids, field_name="protein_ids")
        if not protein_ids and self.protein_id is not None:
            # Backward compatibility: existing single-protein construction
            # (protein_id set, protein_ids left at its default) derives the
            # one-entry authoritative set automatically -- see the field's
            # own comment above.
            protein_ids = (self.protein_id,)
        # Deterministic ordering, never input-order-dependent; deduplicated
        # defensively (Agent 1's own real data never sends duplicates, but
        # this type never trusts that without checking).
        object.__setattr__(self, "protein_ids", tuple(sorted(set(protein_ids))))


@dataclass(frozen=True, slots=True)
class CuratedEnzymeState:
    """One curated enzyme regulatory state, exactly as curated by Agent 1.

    Added in Agent 1.x Increment B (``AGENT1_HANDOFF_VERSION`` "1.1" ->
    "1.2"). Exactly one of ``protein_id``/``complex_id`` is expected
    (mirrors ``CuratedReactionEnzymeAssociation``'s own "expected, never
    enforced" stance -- Agent 1's own row carries a real database
    ``CHECK``, so a violation here would mean the handoff itself is
    malformed, not something this decoupled mirror re-validates). Never
    conflates the underlying protein/complex identity with the state's own
    identity -- see ``docs/02_agent1_handoff_contract.md`` §4B.
    """

    id: str
    state_type: str
    protein_id: str | None = None
    complex_id: str | None = None
    state_label: str | None = None
    compartment_id: str | None = None
    active_state: bool | None = None
    source: str | None = None
    source_id: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self, "state_type", _require_non_empty_str(self.state_type, field_name="state_type")
        )
        object.__setattr__(
            self,
            "active_state",
            _require_bool_or_none(self.active_state, field_name="active_state"),
        )


@dataclass(frozen=True, slots=True)
class CuratedEnzymeModification:
    """One curated covalent/post-translational modification, exactly as curated by Agent 1.

    Added in Agent 1.x Increment B. Always attached to one
    ``CuratedEnzymeState`` via ``enzyme_state_id``.
    """

    id: str
    enzyme_state_id: str
    modification_type: str
    residue: str | None = None
    residue_position: int | None = None
    site_label: str | None = None
    modifying_compound_id: str | None = None
    stoichiometry: Decimal | None = None
    source: str | None = None
    source_id: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "enzyme_state_id",
            _require_non_empty_str(self.enzyme_state_id, field_name="enzyme_state_id"),
        )
        object.__setattr__(
            self,
            "modification_type",
            _require_non_empty_str(self.modification_type, field_name="modification_type"),
        )
        if self.stoichiometry is not None and not isinstance(self.stoichiometry, Decimal):
            raise TypeError(
                f"CuratedEnzymeModification.stoichiometry must be a Decimal or None, "
                f"got {self.stoichiometry!r}"
            )


@dataclass(frozen=True, slots=True)
class CuratedAllostericInteraction:
    """One curated allosteric interaction, exactly as curated by Agent 1.

    Added in Agent 1.x Increment B. ``effect`` is the curated *qualitative*
    regulatory relationship only -- the quantitative kinetic consequence,
    if any, is a separate, state-specific ``CuratedKineticMeasurement``
    sharing the same ``enzyme_state_id`` (see that type's own docstring;
    the two are never conflated). ``ligand_compound_id`` is required --
    Agent 1 never hands off an allosteric interaction with an unresolved
    ligand.
    """

    id: str
    enzyme_state_id: str
    ligand_compound_id: str
    effect: str
    site_label: str | None = None
    mechanism: str | None = None
    source: str | None = None
    source_id: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "enzyme_state_id",
            _require_non_empty_str(self.enzyme_state_id, field_name="enzyme_state_id"),
        )
        object.__setattr__(
            self,
            "ligand_compound_id",
            _require_non_empty_str(self.ligand_compound_id, field_name="ligand_compound_id"),
        )
        object.__setattr__(self, "effect", _require_non_empty_str(self.effect, field_name="effect"))


@dataclass(frozen=True, slots=True)
class CuratedEnzymeStateTransition:
    """One curated transition between two enzyme regulatory states, exactly as curated by Agent 1.

    Added in Agent 1.x Increment B. ``reaction_id`` is ``None`` unless
    Agent 1's own reaction-curation pipeline already resolves the
    transition -- never fabricated.
    """

    id: str
    from_state_id: str
    to_state_id: str
    transition_type: str
    reaction_id: str | None = None
    source: str | None = None
    source_id: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "from_state_id",
            _require_non_empty_str(self.from_state_id, field_name="from_state_id"),
        )
        object.__setattr__(
            self, "to_state_id", _require_non_empty_str(self.to_state_id, field_name="to_state_id")
        )
        object.__setattr__(
            self,
            "transition_type",
            _require_non_empty_str(self.transition_type, field_name="transition_type"),
        )


@dataclass(frozen=True, slots=True)
class CuratedPublication:
    """One publication's own primary date, for kinetic-evidence recency prioritization
    only (Publication Date Handoff increment).

    Mirrors ``app.agent1.types.CuratedPublication`` field-for-field -- deliberately the
    smallest useful subset of Agent 1's own ``Publication`` row: ``id`` (matching
    ``CuratedKineticMeasurement.publication_id`` exactly, so a caller can key a
    ``publication_id -> year`` mapping directly) and ``year`` alone, never title/journal/
    authors/PMID/DOI/abstract or any other bibliographic metadata this repository has no
    use for. ``year`` is the primary publication's own year, verbatim -- never a database
    update/connector-ingestion timestamp, and never inferred from a PMID/DOI by this
    repository -- ``None`` whenever Agent 1 itself never resolved one (never fabricated
    here either).
    """

    id: str
    year: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))


@dataclass(frozen=True, slots=True)
class CuratedExperimentalContext:
    """One curated experimental/reference context, exactly as curated by Agent 1
    (Agent 1.x "Experimental Context and Quantitative Observation Framework",
    ``AGENT1_HANDOFF_VERSION`` "1.3" -> "1.4").

    Mirrors ``app.agent1.types.CuratedExperimentalContext`` field-for-field. Every
    field beyond ``id`` is optional -- Agent 1 itself never fabricates a
    medium/strain/temperature/pH/growth-phase value it was not given (see that
    type's own docstring, and ``app.models.experimental_context.ExperimentalContext``
    in the Agent 1 repository). ``classification``/``source`` are Agent 1's own
    plain strings, never re-typed as an enum here -- consistent with this module's
    established policy for every other Agent-1-sourced categorical field (e.g.
    ``CuratedReaction.reversible`` stays ``bool | None``, never re-validated against
    a closed vocabulary this side of the handoff does not own).
    """

    id: str
    organism_id: str | None = None
    strain: str | None = None
    genotype: str | None = None
    medium: str | None = None
    carbon_source: str | None = None
    temperature_c: Decimal | None = None
    ph: Decimal | None = None
    growth_phase: str | None = None
    growth_condition: str | None = None
    classification: str | None = None
    source: str | None = None
    source_id: str | None = None
    publication_id: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self, "organism_id", _clean_optional_str(self.organism_id, field_name="organism_id")
        )
        object.__setattr__(self, "strain", _clean_optional_str(self.strain, field_name="strain"))
        object.__setattr__(
            self, "genotype", _clean_optional_str(self.genotype, field_name="genotype")
        )
        object.__setattr__(self, "medium", _clean_optional_str(self.medium, field_name="medium"))
        object.__setattr__(
            self,
            "carbon_source",
            _clean_optional_str(self.carbon_source, field_name="carbon_source"),
        )
        object.__setattr__(
            self,
            "temperature_c",
            _require_decimal_or_none(self.temperature_c, field_name="temperature_c"),
        )
        object.__setattr__(self, "ph", _require_decimal_or_none(self.ph, field_name="ph"))
        object.__setattr__(
            self, "growth_phase", _clean_optional_str(self.growth_phase, field_name="growth_phase")
        )
        object.__setattr__(
            self,
            "growth_condition",
            _clean_optional_str(self.growth_condition, field_name="growth_condition"),
        )
        object.__setattr__(
            self,
            "classification",
            _clean_optional_str(self.classification, field_name="classification"),
        )
        object.__setattr__(self, "source", _clean_optional_str(self.source, field_name="source"))
        object.__setattr__(
            self, "source_id", _clean_optional_str(self.source_id, field_name="source_id")
        )
        object.__setattr__(
            self,
            "publication_id",
            _clean_optional_str(self.publication_id, field_name="publication_id"),
        )
        object.__setattr__(self, "notes", _clean_optional_str(self.notes, field_name="notes"))


@dataclass(frozen=True, slots=True)
class CuratedQuantitativeObservationDependency:
    """One input a ``CuratedQuantitativeObservation`` (that is itself ``DERIVED``)
    depends on, exactly as curated by Agent 1 (Agent 1.x "Experimental Context and
    Quantitative Observation Framework").

    Mirrors ``app.agent1.types.CuratedQuantitativeObservationDependency``
    field-for-field. Nested inside ``CuratedQuantitativeObservation.dependencies``,
    never a standalone top-level record -- carries no id of its own, consistent
    with its Agent 1 counterpart.
    """

    input_observation_id: str
    role: str | None = None
    assumption_notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_observation_id",
            _require_non_empty_str(self.input_observation_id, field_name="input_observation_id"),
        )
        object.__setattr__(self, "role", _clean_optional_str(self.role, field_name="role"))
        object.__setattr__(
            self,
            "assumption_notes",
            _clean_optional_str(self.assumption_notes, field_name="assumption_notes"),
        )


@dataclass(frozen=True, slots=True)
class CuratedQuantitativeObservation:
    """One independently-sourced quantitative observation, exactly as curated by
    Agent 1 (Agent 1.x "Experimental Context and Quantitative Observation
    Framework", ``AGENT1_HANDOFF_VERSION`` "1.3" -> "1.4").

    Mirrors ``app.agent1.types.CuratedQuantitativeObservation`` field-for-field.
    Agent 1 curates *reported* quantitative facts (protein abundance, protein/
    metabolite concentration, reaction flux, cell volume, growth rate) -- this type
    is never auto-converted into an ``EnzymeConcentration`` or any other derived
    quantity by anything in this module. That derivation (which observations
    combine, under what context-compatibility rule, with what fallback assumption)
    is implemented explicitly by ``app.agent2.quantitative_context`` (Quantitative
    Context Resolution and Derived Enzyme Concentration increment), never
    implicitly here -- mirrors ``CuratedKineticMeasurement``'s own identical
    architectural boundary with ``ParameterSpecification``.

    ``observation_type``/``evidence_class`` are Agent 1's own plain strings, never
    re-typed as a closed enum here (same policy as ``CuratedExperimentalContext``
    above). ``value``/``unit`` are the as-reported figures; ``normalized_value``/
    ``normalized_unit`` are Agent 1's own already-computed canonical-unit
    conversion (``None``/``None`` when unresolved -- never fabricated by this
    translation).

    **This increment does not add a top-level ``perturbations``/
    ``CuratedPerturbation`` mirror** -- ``perturbation_id`` below is preserved
    verbatim (Agent 1's own foreign key, exactly as every other unresolved-
    reference-type field on this contract is), but the sibling ``Perturbation``
    registry itself is deferred: no real Agent 1 data populates it yet (SGD
    reference abundance carries no perturbation), and this increment's own
    "smallest integration point" (see ``docs/16_quantitative_context_resolution.md``
    §1) does not need it. A future increment that actually consumes perturbation
    context should add it then, exactly as this one adds ``CuratedExperimentalContext``
    now.
    """

    id: str

    observation_type: str
    value: Decimal
    unit: str
    evidence_class: str

    reported_observation_type: str | None = None
    normalized_value: Decimal | None = None
    normalized_unit: str | None = None

    uncertainty: Decimal | None = None
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    measurement_method: str | None = None

    time_reference_basis: str | None = None
    time_value: Decimal | None = None
    time_unit: str | None = None
    time_canonical_s: Decimal | None = None

    experimental_context_id: str | None = None
    perturbation_id: str | None = None

    biological_replicate_id: str | None = None
    technical_replicate_id: str | None = None

    protein_id: str | None = None
    compound_id: str | None = None
    reaction_id: str | None = None
    organism_id: str | None = None
    unresolved_identity_kind: str | None = None
    unresolved_identity_text: str | None = None

    source: str | None = None
    source_id: str | None = None
    publication_id: str | None = None
    dataset_id: str | None = None

    notes: str | None = None

    #: Every input this observation depends on, when it is itself ``DERIVED`` -- see
    #: ``CuratedQuantitativeObservationDependency``. Empty for every non-``DERIVED``
    #: observation, exactly as on the Agent 1 side.
    dependencies: tuple[CuratedQuantitativeObservationDependency, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_non_empty_str(self.id, field_name="id"))
        object.__setattr__(
            self,
            "observation_type",
            _require_non_empty_str(self.observation_type, field_name="observation_type"),
        )
        if not isinstance(self.value, Decimal):
            raise TypeError(
                f"CuratedQuantitativeObservation.value must be a Decimal, got {self.value!r}"
            )
        object.__setattr__(self, "unit", _require_non_empty_str(self.unit, field_name="unit"))
        object.__setattr__(
            self,
            "evidence_class",
            _require_non_empty_str(self.evidence_class, field_name="evidence_class"),
        )
        object.__setattr__(
            self,
            "reported_observation_type",
            _clean_optional_str(
                self.reported_observation_type, field_name="reported_observation_type"
            ),
        )
        for field_name in (
            "normalized_value",
            "uncertainty",
            "lower_bound",
            "upper_bound",
            "time_value",
            "time_canonical_s",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_decimal_or_none(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "normalized_unit",
            "measurement_method",
            "time_reference_basis",
            "time_unit",
            "experimental_context_id",
            "perturbation_id",
            "biological_replicate_id",
            "technical_replicate_id",
            "protein_id",
            "compound_id",
            "reaction_id",
            "organism_id",
            "unresolved_identity_kind",
            "unresolved_identity_text",
            "source",
            "source_id",
            "publication_id",
            "dataset_id",
            "notes",
        ):
            object.__setattr__(
                self,
                field_name,
                _clean_optional_str(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "dependencies",
            _require_tuple_of(
                self.dependencies,
                CuratedQuantitativeObservationDependency,
                field_name="dependencies",
            ),
        )


@dataclass(frozen=True, slots=True)
class Agent1CuratedKnowledgeViewContract:
    """Agent 2's local, decoupled representation of the Agent 1 handoff.

    Never depends on Agent 1's Python classes -- see
    ``docs/02_agent1_handoff_contract.md`` for the full field-by-field
    contract, including what Agent 2 may and must not assume about each
    field. Already covers every category Increment 1 requires at minimum
    (compartments, compounds, reactions, reaction participants,
    reaction-enzyme associations, regulation, accepted claims/evidence,
    confidence, limitations) -- no new field was needed for Increment 1.

    **Kinetic measurements** (Agent 1.x Increment A,
    ``AGENT1_HANDOFF_VERSION`` "1.0" -> "1.1"): ``kinetic_measurements`` is
    now available as curated input -- see ``CuratedKineticMeasurement``.
    This is available *input data only*; it is never auto-converted into a
    ``ParameterSpecification`` by anything in this repository (that mapping
    decision remains unimplemented Agent 2 behavior). This closes the
    "known handoff gap" this docstring previously disclosed for Increment 1.

    **Enzyme regulatory states** (Agent 1.x Increment B,
    ``AGENT1_HANDOFF_VERSION`` "1.1" -> "1.2"): ``enzyme_states``/
    ``enzyme_modifications``/``allosteric_interactions``/
    ``enzyme_state_transitions`` are now available as curated input, plus
    ``CuratedKineticMeasurement.enzyme_state_id`` for state-specific
    measurements -- see §4B of ``docs/02_agent1_handoff_contract.md``.
    Input data only, same as kinetic measurements: nothing in this
    repository maps a ``CuratedEnzymeState`` onto a model species, and
    Whole-Network Assembly (Increment 2) was not modified to consume these
    fields (see ``docs/05_whole_network_assembly.md``).

    **Quantitative context** (Agent 1.x "Experimental Context and Quantitative
    Observation Framework", ``AGENT1_HANDOFF_VERSION`` "1.3" -> "1.4"):
    ``experimental_contexts``/``quantitative_observations`` are now available as
    curated input -- see ``CuratedExperimentalContext``/
    ``CuratedQuantitativeObservation``, and §4D of
    ``docs/02_agent1_handoff_contract.md``. Consumed, for the first time, by the
    "Quantitative Context Resolution and Derived Enzyme Concentration" increment
    (``app.agent2.quantitative_context``) -- see
    ``docs/16_quantitative_context_resolution.md``. Agent 1's own sibling
    ``perturbations``/``Perturbation`` field is deliberately **not** mirrored here
    yet (see ``CuratedQuantitativeObservation``'s own docstring) -- a disclosed,
    narrower reading of this bump, not an oversight.

    **Publication dates** (Publication Date Handoff increment, ``AGENT1_HANDOFF_VERSION``
    "1.4" -> "1.5"): ``publications`` is now available as curated input -- see
    ``CuratedPublication``. Consumed by ``app.agent2.kinetics.evidence_consolidation``'s
    own publication-recency ranking tier (previously always inert on real data for lack
    of any such field on this side of the handoff).
    """

    contract_version: str
    organism_id: str | None = None
    compartments: tuple[CuratedCompartment, ...] = ()
    compounds: tuple[CuratedCompound, ...] = ()
    reactions: tuple[CuratedReaction, ...] = ()
    reaction_participants: tuple[CuratedReactionParticipant, ...] = ()
    reaction_enzyme_associations: tuple[CuratedReactionEnzymeAssociation, ...] = ()
    regulatory_interactions: tuple[CuratedRegulatoryInteraction, ...] = ()
    kinetic_measurements: tuple[CuratedKineticMeasurement, ...] = ()
    enzyme_states: tuple[CuratedEnzymeState, ...] = ()
    enzyme_modifications: tuple[CuratedEnzymeModification, ...] = ()
    allosteric_interactions: tuple[CuratedAllostericInteraction, ...] = ()
    enzyme_state_transitions: tuple[CuratedEnzymeStateTransition, ...] = ()
    experimental_contexts: tuple[CuratedExperimentalContext, ...] = ()
    quantitative_observations: tuple[CuratedQuantitativeObservation, ...] = ()
    #: Publication Date Handoff increment, ``AGENT1_HANDOFF_VERSION`` "1.4" -> "1.5".
    #: Every publication Agent 1 itself already scoped to this run's own referenced
    #: records, reshaped to the minimal ``id``/``year`` subset -- see
    #: ``CuratedPublication``'s own docstring.
    publications: tuple[CuratedPublication, ...] = ()
    claims: tuple[CuratedClaim, ...] = ()
    evidence: tuple[CuratedEvidence, ...] = ()
    confidence_summaries: tuple[CuratedConfidenceSummary, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contract_version",
            _require_non_empty_str(self.contract_version, field_name="contract_version"),
        )
        object.__setattr__(
            self, "limitations", _require_str_tuple(self.limitations, field_name="limitations")
        )


# =================================================================================================
# 2. Shared enums
# =================================================================================================


class ParameterSource(StrEnum):
    """Where a parameter's (or a species' initial value's) value came from -- provenance/status,
    not confidence.

    ``CALIBRATED`` is reserved for a value returned by Agent 4's feedback
    (``docs/01_agent2_architecture.md`` §21); Agent 2 never assigns it to a
    value it produced itself. Also reused by
    ``SpeciesSpecification.initialization_source``, rather than inventing
    a near-duplicate vocabulary.

    **No longer reused by `KineticLawSpecification.assignment_source`**
    (Increment 8 pre-commit revision): a kinetic law's *type* provenance
    ("why was this rate-law form chosen") and a parameter's *value*
    provenance ("where did this number come from") are different axes
    that happen to share a provenance-vs-status shape but not the same
    vocabulary of answers -- see `KineticLawAssignmentSource` below for
    the dedicated enum this field now uses instead, and
    ``docs/11_model_specification_assembly.md`` §10 for the full
    rationale.

    **`AI_PREDICTED`/`HEURISTIC_INITIALIZATION`** (Heuristic Simulation
    Parameter Initialization increment): two new, distinct rungs inserted
    into the existing precedence, never confused with each other or with
    any value above them --
    ``LITERATURE_DERIVED``/``CURATED`` > ``AI_PREDICTED`` >
    ``HEURISTIC_INITIALIZATION`` > ``PLACEHOLDER``. ``AI_PREDICTED`` is a
    curated-but-non-experimental value Agent 1 itself already attributed
    to a specific reaction/protein/substrate (today, exclusively
    GotEnzymes2 predictions, ``CuratedKineticMeasurement.source ==
    "GOTENZYMES"``) -- real, attributable evidence, but never a
    laboratory measurement. ``HEURISTIC_INITIALIZATION`` is a value this
    package itself invented, from a small, centralized, documented default
    policy (``app.agent2.parameters.heuristic_defaults``), used only when
    no experimental or AI-predicted evidence exists at all -- never a
    biochemical claim of any kind, purely a numerically well-behaved
    starting point for later Agent 4 calibration.

    **`DERIVED_FROM_MACRO_KINETICS`** (Identifiability-Aware Macroscopic-
    to-Microscopic Kinetic Reconstruction increment): one more rung,
    inserted between `AI_PREDICTED` and `HEURISTIC_INITIALIZATION` --
    ``LITERATURE_DERIVED``/``CURATED`` > ``AI_PREDICTED`` >
    ``DERIVED_FROM_MACRO_KINETICS`` > ``HEURISTIC_INITIALIZATION`` >
    ``PLACEHOLDER`` (the task's own explicit ordering). A value this
    codebase itself *computed* (never merely copied) from other, already-
    resolved macroscopic evidence -- e.g. `kcat = Vmax / [E]_total`, or an
    effective second-order rate `kcat/Km` -- only when the combination is
    actually identifiable (`app.agent2.parameters.reconstruction
    .IdentifiabilityStatus.IDENTIFIABLE`), never a fabricated point value
    for a genuinely underdetermined slot (that case is preserved instead
    as a disclosed `MicroscopicConstraint`, never assigned this or any
    other numeric `ParameterSource`). Ranked below `AI_PREDICTED`
    deliberately: even when the inputs it derives from are themselves
    real (curated or AI-predicted) evidence, the derivation itself is one
    further inferential step removed from a direct measurement or
    prediction, exactly mirroring `FLUX_ABUNDANCE_CONSTRAINED_
    RECONSTRUCTION`'s identical placement in
    ``docs/15_macroscopic_to_microscopic_kinetic_reconstruction_design.md``
    §7 (this codebase's own simpler, single-tier implementation of that
    design's two-way experimental/AI-predicted split -- see
    ``docs/17_macroscopic_to_microscopic_kinetic_reconstruction.md`` §1
    for why one tier, not two, was implemented). When the derivation's own
    inputs include an AI-predicted macro-kinetic value, that dependency is
    preserved explicitly in `source_reference`/`uncertainty_text`/
    `provenance_refs` -- never silently laundered into an
    indistinguishable derived value.
    """

    CURATED = "CURATED"
    LITERATURE_DERIVED = "LITERATURE_DERIVED"
    AI_PREDICTED = "AI_PREDICTED"
    DERIVED_FROM_MACRO_KINETICS = "DERIVED_FROM_MACRO_KINETICS"
    HEURISTIC_INITIALIZATION = "HEURISTIC_INITIALIZATION"
    DEFAULT = "DEFAULT"
    PLACEHOLDER = "PLACEHOLDER"
    CALIBRATED = "CALIBRATED"


class BoundaryLikelihood(StrEnum):
    """A qualitative heuristic judgment -- never a fabricated numeric probability.

    Exactly these five values. A future boundary-heuristic rule set
    assigns one of these to each ``BoundaryAssessment``; nothing here
    computes one.
    """

    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class BoundaryParameterBasis(StrEnum):
    """Whether a ``BoundaryAssessment`` was informed by parameter data, and of what quality.

    A structural disclosure, never a numeric weight -- ``MIXED`` means the
    boundary's supporting kinetic laws/parameters span more than one of
    the other categories, not a blended score.
    """

    NONE = "NONE"
    PLACEHOLDER_ONLY = "PLACEHOLDER_ONLY"
    DEFAULT_ONLY = "DEFAULT_ONLY"
    CURATED_OR_LITERATURE = "CURATED_OR_LITERATURE"
    CALIBRATED = "CALIBRATED"
    MIXED = "MIXED"


class KineticLawType(StrEnum):
    """The structural *form/category* of a reaction's rate law -- never fitted behavior.

    ``UNASSIGNED`` is the default starting point for a reaction with no
    kinetic law decided yet. Kept deliberately minimal -- Increment 1 does
    not add complex rate-law subclasses without a current need.
    """

    MASS_ACTION = "MASS_ACTION"
    MICHAELIS_MENTEN = "MICHAELIS_MENTEN"
    HILL = "HILL"
    REVERSIBLE_MASS_ACTION = "REVERSIBLE_MASS_ACTION"
    CUSTOM = "CUSTOM"
    UNASSIGNED = "UNASSIGNED"


class KineticLawAssignmentSource(StrEnum):
    """Provenance of *the modeling decision itself* -- never a confidence score, and never a
    claim about a parameter's own numeric value.

    **Relocated here from `app.agent2.kinetics.types` in an Increment 8
    pre-commit revision** so `KineticLawSpecification.assignment_source`
    (`app.agent2.types`, the canonical, cross-cutting layer) could use it
    directly without `app.agent2.types` importing from a narrower,
    per-increment package -- the reverse of this repository's established
    dependency direction (`app.agent2.kinetics.types` already imports
    `KineticLawType` from here). `app.agent2.kinetics.types` still
    exposes the identical symbol via a re-export
    (`from app.agent2.types import KineticLawAssignmentSource`), so every
    existing `from app.agent2.kinetics.types import
    KineticLawAssignmentSource` import continues to work unchanged.

    Distinct from `ParameterSource` on purpose: `ParameterSource` answers
    "where did this numeric parameter value come from" (curated value vs.
    default vs. calibrated-by-Agent-4) -- a different axis from what this
    enum answers, "why does this reaction have *this kind* of rate-law
    structure." Reusing `ParameterSource` for both (as
    `KineticLawSpecification.assignment_source` originally did, before
    this revision) would have forced `CURATED`/`DEFAULT`/`PLACEHOLDER` to
    mean two different things depending on context -- exactly the
    ambiguity this dedicated enum exists to eliminate. See
    ``docs/07_kinetic_law_assignment.md`` §5 and
    ``docs/11_model_specification_assembly.md`` §10.
    """

    CURATED_REPORTED = "CURATED_REPORTED"
    DETERMINISTIC_STRUCTURAL = "DETERMINISTIC_STRUCTURAL"
    HEURISTIC = "HEURISTIC"
    UNASSIGNED = "UNASSIGNED"


class ParticipantRole(StrEnum):
    """A reaction participant's structural role.

    Transcribed verbatim from Agent 1's own controlled vocabulary
    (``ReactionParticipantRole`` in ``agent1-biochemical-curator``) --
    never imported, the same "vocabulary exists in two places by
    transcription, not cross-repository import" discipline Agent 1 itself
    uses pervasively for its own upper-layer enums.
    """

    REACTANT = "REACTANT"
    PRODUCT = "PRODUCT"
    MODIFIER = "MODIFIER"


class ModuleInterfaceRole(StrEnum):
    """A module boundary interface's structural role. Kept deliberately minimal."""

    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    SHARED = "SHARED"


class CompartmentSourceScope(StrEnum):
    """Whether a ``CompartmentSpecification`` traces back to a real Agent 1 record.

    ``AGENT1_CURATED`` requires ``source_entity_id``; ``MODELING_CONSTRUCT``
    forbids it and instead requires the compartment's ``assumptions`` to
    disclose why Agent 2 needed a compartment Agent 1 never curated
    (Increment 1 instructions, Step 3).
    """

    AGENT1_CURATED = "AGENT1_CURATED"
    MODELING_CONSTRUCT = "MODELING_CONSTRUCT"


# =================================================================================================
# 3. Full-network structural domain
# =================================================================================================


@dataclass(frozen=True, slots=True)
class CompartmentSpecification:
    """One compartment in the full network.

    A compartment with ``source_scope=MODELING_CONSTRUCT`` (Agent 2 needed
    it structurally; Agent 1 never curated it) must carry no
    ``source_entity_id`` and must disclose why in ``assumptions`` -- never
    silently invented (Increment 1 instructions, Step 3). No unit is ever
    invented: ``volume_unit`` is ``None`` whenever the source data did not
    supply one, never a guessed default like ``"L"``.
    """

    compartment_id: str
    name: str
    source_scope: CompartmentSourceScope
    source_entity_id: str | None = None
    initial_volume: Decimal | None = None
    volume_unit: str | None = None
    constant: bool | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "compartment_id",
            _require_non_empty_str(self.compartment_id, field_name="compartment_id"),
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        if not isinstance(self.source_scope, CompartmentSourceScope):
            raise TypeError(
                "CompartmentSpecification.source_scope must be a CompartmentSourceScope, "
                f"got {self.source_scope!r}"
            )
        object.__setattr__(
            self,
            "source_entity_id",
            _clean_optional_str(self.source_entity_id, field_name="source_entity_id"),
        )
        if (
            self.source_scope is CompartmentSourceScope.AGENT1_CURATED
            and self.source_entity_id is None
        ):
            raise ValueError(
                "CompartmentSpecification with source_scope=AGENT1_CURATED requires "
                "source_entity_id"
            )
        if (
            self.source_scope is CompartmentSourceScope.MODELING_CONSTRUCT
            and self.source_entity_id is not None
        ):
            raise ValueError(
                "CompartmentSpecification with source_scope=MODELING_CONSTRUCT must not carry "
                "source_entity_id"
            )
        object.__setattr__(
            self,
            "initial_volume",
            _require_decimal_or_none(self.initial_volume, field_name="initial_volume"),
        )
        object.__setattr__(
            self, "volume_unit", _clean_optional_str(self.volume_unit, field_name="volume_unit")
        )
        object.__setattr__(
            self, "constant", _require_bool_or_none(self.constant, field_name="constant")
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        if self.source_scope is CompartmentSourceScope.MODELING_CONSTRUCT and not self.assumptions:
            raise ValueError(
                "a MODELING_CONSTRUCT compartment must disclose why it exists in assumptions"
            )


@dataclass(frozen=True, slots=True)
class SpeciesSpecification:
    """One chemical species in the full network.

    Species identity always includes compartment context: ``compartment_id``
    is required (the same compound in two compartments is two different
    species). At most one of ``initial_amount``/``initial_concentration``
    may be set -- Increment 1 does not support a policy for reconciling
    both at once. ``constant`` (value never changes) and
    ``boundary_condition`` (not consumed/produced by reactions, but may
    still be set externally) are independent SBML-style flags, never
    conflated.
    """

    species_id: str
    name: str
    compartment_id: str
    source_compound_id: str | None = None
    initial_amount: Decimal | None = None
    initial_concentration: Decimal | None = None
    initialization_source: ParameterSource | None = None
    constant: bool | None = None
    boundary_condition: bool | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        object.__setattr__(
            self,
            "compartment_id",
            _require_non_empty_str(self.compartment_id, field_name="compartment_id"),
        )
        object.__setattr__(
            self,
            "source_compound_id",
            _clean_optional_str(self.source_compound_id, field_name="source_compound_id"),
        )
        object.__setattr__(
            self,
            "initial_amount",
            _require_decimal_or_none(self.initial_amount, field_name="initial_amount"),
        )
        object.__setattr__(
            self,
            "initial_concentration",
            _require_decimal_or_none(
                self.initial_concentration, field_name="initial_concentration"
            ),
        )
        if self.initial_amount is not None and self.initial_concentration is not None:
            raise ValueError(
                "SpeciesSpecification must not set both initial_amount and "
                "initial_concentration -- no reconciliation policy exists yet"
            )
        if self.initialization_source is not None and not isinstance(
            self.initialization_source, ParameterSource
        ):
            raise TypeError(
                "SpeciesSpecification.initialization_source must be a ParameterSource or None, "
                f"got {self.initialization_source!r}"
            )
        object.__setattr__(
            self, "constant", _require_bool_or_none(self.constant, field_name="constant")
        )
        object.__setattr__(
            self,
            "boundary_condition",
            _require_bool_or_none(self.boundary_condition, field_name="boundary_condition"),
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


@dataclass(frozen=True, slots=True)
class ReactionParticipantSpecification:
    """One reactant/product/modifier of a ``ReactionSpecification``.

    ``stoichiometry`` is required and must be positive for every role,
    including ``MODIFIER`` -- mirroring Agent 1's own
    ``reaction_participant`` schema (a database ``CHECK`` constraint
    enforces ``stoichiometry > 0`` for every role there too). Whether a
    modifier's stoichiometry *contributes* to a kinetic-law expression is
    a modeling decision for a later increment's kinetic-law assignment
    step -- this structural type only records the value, never interprets
    it. Multiplicity is preserved: nothing here deduplicates two
    participants naming the same species and role.
    """

    species_id: str
    role: ParticipantRole
    stoichiometry: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        if not isinstance(self.role, ParticipantRole):
            raise TypeError(
                f"ReactionParticipantSpecification.role must be a ParticipantRole, "
                f"got {self.role!r}"
            )
        if not isinstance(self.stoichiometry, Decimal):
            raise TypeError(
                "ReactionParticipantSpecification.stoichiometry must be a Decimal, "
                f"got {self.stoichiometry!r}"
            )
        if self.stoichiometry <= 0:
            raise ValueError(
                f"ReactionParticipantSpecification.stoichiometry must be > 0, "
                f"got {self.stoichiometry!r}"
            )


@dataclass(frozen=True, slots=True)
class ReactionSpecification:
    """One reaction in the full network.

    ``participants`` are structural inputs only -- no mass-balance,
    duplicate-reaction, or reaction-graph analysis occurs here (Agent 3's
    job). ``reversible`` is never inferred: ``None`` means Agent 1 did not
    record it. ``kinetic_law_id`` may be unresolved (``None``) at this
    stage -- kinetic-law assignment is a later increment.
    """

    reaction_id: str
    name: str
    participants: tuple[ReactionParticipantSpecification, ...] = ()
    source_reaction_id: str | None = None
    reversible: bool | None = None
    enzyme_association_ids: tuple[str, ...] = ()
    regulatory_interaction_ids: tuple[str, ...] = ()
    kinetic_law_id: str | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        object.__setattr__(
            self,
            "participants",
            _require_tuple_of(
                self.participants, ReactionParticipantSpecification, field_name="participants"
            ),
        )
        if not self.participants:
            raise ValueError(
                "ReactionSpecification requires at least one participant -- a reaction with none "
                "is not structurally meaningful (this is a completeness check, not mass-balance "
                "analysis)"
            )
        object.__setattr__(
            self,
            "source_reaction_id",
            _clean_optional_str(self.source_reaction_id, field_name="source_reaction_id"),
        )
        object.__setattr__(
            self, "reversible", _require_bool_or_none(self.reversible, field_name="reversible")
        )
        object.__setattr__(
            self,
            "enzyme_association_ids",
            _require_str_tuple(self.enzyme_association_ids, field_name="enzyme_association_ids"),
        )
        object.__setattr__(
            self,
            "regulatory_interaction_ids",
            _require_str_tuple(
                self.regulatory_interaction_ids, field_name="regulatory_interaction_ids"
            ),
        )
        object.__setattr__(
            self,
            "kinetic_law_id",
            _clean_optional_str(self.kinetic_law_id, field_name="kinetic_law_id"),
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


@dataclass(frozen=True, slots=True)
class ReactionEnzymeAssociation:
    """One reaction<->enzyme association carried into the full network, exactly as curated.

    Mirrors ``CuratedReactionEnzymeAssociation`` field-for-field, adding
    only ``association_id``. **Discovered gap** (Increment 2): Agent 1's
    handoff contract for this record carries no id of its own -- unlike
    ``CuratedRegulatoryInteraction``/``CuratedKineticMeasurement``, which
    do, and which ``FullNetwork`` therefore attaches unchanged (§ module
    docstring). Rather than changing the already-approved, cross-repository
    ``CuratedReactionEnzymeAssociation`` shape to add one,
    ``app.agent2.network`` synthesizes a stable, deterministic
    ``association_id`` at assembly time (scoped to one reaction, never
    derived from content that could collide) and this type carries it
    alongside the untouched original fields. No enzyme is ever chosen as
    preferred, and no complex/isozyme/catalytic-mechanism relationship is
    ever inferred here or by anything that constructs this type --
    ``protein_id``/``complex_id``/``enzyme_state_id``/``relationship`` are
    copied verbatim.

    **``enzyme_state_id`` added in Increment 3**, alongside the identical
    fix to ``CuratedReactionEnzymeAssociation`` (see that type's own
    docstring) -- required so catalyst characterization can distinguish
    state-specific catalysis from protein/complex-general catalysis
    (``docs/06_reaction_enzyme_state_characterization.md`` §10-12).
    """

    association_id: str
    reaction_id: str
    protein_id: str | None = None
    complex_id: str | None = None
    enzyme_state_id: str | None = None
    relationship: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "association_id",
            _require_non_empty_str(self.association_id, field_name="association_id"),
        )
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        object.__setattr__(
            self, "protein_id", _clean_optional_str(self.protein_id, field_name="protein_id")
        )
        object.__setattr__(
            self, "complex_id", _clean_optional_str(self.complex_id, field_name="complex_id")
        )
        object.__setattr__(
            self,
            "enzyme_state_id",
            _clean_optional_str(self.enzyme_state_id, field_name="enzyme_state_id"),
        )
        object.__setattr__(
            self,
            "relationship",
            _clean_optional_str(self.relationship, field_name="relationship"),
        )


@dataclass(frozen=True, slots=True)
class FullNetwork:
    """The single authoritative graph of every compartment, species, and reaction.

    Built once, before kinetic-law assignment or boundary assessment
    (Increment 1 instructions, "full-network-first"). Validates internal
    reference integrity (unique ids, every species' compartment exists,
    every reaction participant's species exists) but never performs
    Agent-3-level mass-balance, connectivity, or unit-consistency
    analysis.

    **Increment 2** added ``enzyme_associations``/``regulatory_interactions``/
    ``kinetic_measurements`` -- every curated enzyme association, curated
    regulatory interaction, and curated kinetic measurement in the source
    handoff, attached here as supporting data the structural graph carries
    forward. None of the three is a structural graph element in its own
    right (unlike compartments/species/reactions): they are never used to
    infer a species, a reaction, or a compartment, and nothing here
    chooses a preferred enzyme, interprets regulation, or converts a
    kinetic measurement into a parameter -- see
    ``docs/05_whole_network_assembly.md``.

    **Increment 3** added ``enzyme_states``/``enzyme_modifications``/
    ``allosteric_interactions``/``enzyme_state_transitions`` -- every
    curated enzyme regulatory state, modification, allosteric interaction,
    and state transition, reusing Agent 1's own
    ``CuratedEnzymeState``/``CuratedEnzymeModification``/
    ``CuratedAllostericInteraction``/``CuratedEnzymeStateTransition`` types
    unchanged (each already carries a real ``id``, unlike
    ``CuratedReactionEnzymeAssociation``, so no synthesized wrapper type
    was needed here). Attached as supporting data only -- never turned into
    a ``SpeciesSpecification``, a model reaction, or a rate law by this
    type or by ``app.agent2.network`` (that mapping is
    ``app.agent2.characterization``/a future increment's job). See
    ``docs/06_reaction_enzyme_state_characterization.md``.

    **Quantitative Context Resolution and Derived Enzyme Concentration increment**
    added ``experimental_contexts``/``quantitative_observations`` -- every curated
    experimental/reference context and quantitative observation, reusing Agent 1's
    own ``CuratedExperimentalContext``/``CuratedQuantitativeObservation`` types
    unchanged. Attached as supporting data only -- never turned into a
    ``SpeciesSpecification`` or any structural graph element by this type or by
    ``app.agent2.network``; deriving an ``EnzymeConcentration`` from them is
    ``app.agent2.quantitative_context``'s job (see
    ``docs/16_quantitative_context_resolution.md``).

    **Publication Date Handoff increment** added ``publications`` -- every curated
    publication in the source handoff, attached here as supporting data only, exactly
    like ``kinetic_measurements``/``experimental_contexts`` before it. Never turned into
    a structural graph element; consumed only by
    ``app.agent2.kinetics.evidence_consolidation.publication_years_for_network`` to
    build the ``publication_id -> year`` mapping its own recency-ranking tier uses.
    """

    network_id: str
    name: str
    compartments: tuple[CompartmentSpecification, ...] = ()
    species: tuple[SpeciesSpecification, ...] = ()
    reactions: tuple[ReactionSpecification, ...] = ()
    enzyme_associations: tuple[ReactionEnzymeAssociation, ...] = ()
    regulatory_interactions: tuple[CuratedRegulatoryInteraction, ...] = ()
    kinetic_measurements: tuple[CuratedKineticMeasurement, ...] = ()
    enzyme_states: tuple[CuratedEnzymeState, ...] = ()
    enzyme_modifications: tuple[CuratedEnzymeModification, ...] = ()
    allosteric_interactions: tuple[CuratedAllostericInteraction, ...] = ()
    enzyme_state_transitions: tuple[CuratedEnzymeStateTransition, ...] = ()
    #: Quantitative Context Resolution and Derived Enzyme Concentration increment.
    #: Every curated experimental/reference context and quantitative observation in
    #: the source handoff, attached here as supporting data -- exactly like
    #: ``kinetic_measurements``/``enzyme_states`` before them (§ module docstring),
    #: never turned into a structural graph element or an ``EnzymeConcentration`` by
    #: this type or by ``app.agent2.network`` (that derivation is
    #: ``app.agent2.quantitative_context``'s job).
    experimental_contexts: tuple[CuratedExperimentalContext, ...] = ()
    quantitative_observations: tuple[CuratedQuantitativeObservation, ...] = ()
    publications: tuple[CuratedPublication, ...] = ()
    organism_id: str | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        object.__setattr__(
            self,
            "compartments",
            _require_tuple_of(
                self.compartments, CompartmentSpecification, field_name="compartments"
            ),
        )
        object.__setattr__(
            self,
            "species",
            _require_tuple_of(self.species, SpeciesSpecification, field_name="species"),
        )
        object.__setattr__(
            self,
            "reactions",
            _require_tuple_of(self.reactions, ReactionSpecification, field_name="reactions"),
        )
        object.__setattr__(
            self,
            "enzyme_associations",
            _require_tuple_of(
                self.enzyme_associations,
                ReactionEnzymeAssociation,
                field_name="enzyme_associations",
            ),
        )
        object.__setattr__(
            self,
            "regulatory_interactions",
            _require_tuple_of(
                self.regulatory_interactions,
                CuratedRegulatoryInteraction,
                field_name="regulatory_interactions",
            ),
        )
        object.__setattr__(
            self,
            "kinetic_measurements",
            _require_tuple_of(
                self.kinetic_measurements,
                CuratedKineticMeasurement,
                field_name="kinetic_measurements",
            ),
        )
        object.__setattr__(
            self,
            "enzyme_states",
            _require_tuple_of(self.enzyme_states, CuratedEnzymeState, field_name="enzyme_states"),
        )
        object.__setattr__(
            self,
            "enzyme_modifications",
            _require_tuple_of(
                self.enzyme_modifications,
                CuratedEnzymeModification,
                field_name="enzyme_modifications",
            ),
        )
        object.__setattr__(
            self,
            "allosteric_interactions",
            _require_tuple_of(
                self.allosteric_interactions,
                CuratedAllostericInteraction,
                field_name="allosteric_interactions",
            ),
        )
        object.__setattr__(
            self,
            "enzyme_state_transitions",
            _require_tuple_of(
                self.enzyme_state_transitions,
                CuratedEnzymeStateTransition,
                field_name="enzyme_state_transitions",
            ),
        )
        object.__setattr__(
            self,
            "experimental_contexts",
            _require_tuple_of(
                self.experimental_contexts,
                CuratedExperimentalContext,
                field_name="experimental_contexts",
            ),
        )
        object.__setattr__(
            self,
            "quantitative_observations",
            _require_tuple_of(
                self.quantitative_observations,
                CuratedQuantitativeObservation,
                field_name="quantitative_observations",
            ),
        )
        object.__setattr__(
            self,
            "organism_id",
            _clean_optional_str(self.organism_id, field_name="organism_id"),
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )

        _require_unique(
            tuple(c.compartment_id for c in self.compartments),
            field_name="FullNetwork.compartments[].compartment_id",
        )
        _require_unique(
            tuple(s.species_id for s in self.species),
            field_name="FullNetwork.species[].species_id",
        )
        _require_unique(
            tuple(r.reaction_id for r in self.reactions),
            field_name="FullNetwork.reactions[].reaction_id",
        )
        _require_unique(
            tuple(e.association_id for e in self.enzyme_associations),
            field_name="FullNetwork.enzyme_associations[].association_id",
        )
        _require_unique(
            tuple(r.id for r in self.regulatory_interactions),
            field_name="FullNetwork.regulatory_interactions[].id",
        )
        _require_unique(
            tuple(k.id for k in self.kinetic_measurements),
            field_name="FullNetwork.kinetic_measurements[].id",
        )
        _require_unique(
            tuple(s.id for s in self.enzyme_states),
            field_name="FullNetwork.enzyme_states[].id",
        )
        _require_unique(
            tuple(m.id for m in self.enzyme_modifications),
            field_name="FullNetwork.enzyme_modifications[].id",
        )
        _require_unique(
            tuple(a.id for a in self.allosteric_interactions),
            field_name="FullNetwork.allosteric_interactions[].id",
        )
        _require_unique(
            tuple(t.id for t in self.enzyme_state_transitions),
            field_name="FullNetwork.enzyme_state_transitions[].id",
        )
        _require_unique(
            tuple(c.id for c in self.experimental_contexts),
            field_name="FullNetwork.experimental_contexts[].id",
        )
        _require_unique(
            tuple(o.id for o in self.quantitative_observations),
            field_name="FullNetwork.quantitative_observations[].id",
        )

        _validate_full_network_references(self)


def _validate_full_network_references(network: FullNetwork) -> None:
    """Every internal cross-reference in ``network`` must resolve. See ``FullNetwork``.

    A module-level function, mirroring
    ``_validate_model_specification_references`` -- kept out of
    ``__post_init__`` purely for readability, never called elsewhere.

    **Scoped, not exhaustive** (Increment 2): ``FullNetwork`` models
    compartments/species/reactions as first-class entities, but not
    proteins, enzyme complexes, genes, organisms, or publications --
    ``enzyme_associations[].protein_id``/``.complex_id``,
    ``kinetic_measurements[].protein_id``/``.complex_id``/
    ``.organism_id``/``.publication_id``, and any
    ``regulatory_interactions[]`` entity of a type other than
    ``"reaction"``/``"compound"`` are therefore never referentially
    validated here -- there is nothing in ``FullNetwork`` to validate them
    against. This is a disclosed limitation
    (``docs/05_whole_network_assembly.md``), not an oversight: inventing a
    check ``FullNetwork`` cannot actually perform would be worse than
    leaving it undone.

    **Increment 3** extended this scoped validation to the enzyme-state
    family: every ``enzyme_modifications[]``/``allosteric_interactions[]``
    ``.enzyme_state_id``, every ``enzyme_state_transitions[]``
    ``.from_state_id``/``.to_state_id``, every optional
    ``enzyme_associations[].enzyme_state_id``, and every optional
    ``kinetic_measurements[].enzyme_state_id`` must resolve against
    ``enzyme_states`` -- a complete registry within ``FullNetwork``, unlike
    ``compound_ids`` (§ below). ``allosteric_interactions[].ligand_compound_id``
    is checked against ``compound_ids`` only when that registry is
    non-empty -- ``compound_ids`` is derived solely from species that
    happen to participate in a curated reaction, so it is never a complete
    compound registry, and a ligand that is never itself a reaction
    participant (a common, legitimate case) must not be rejected as
    "dangling" merely because ``FullNetwork`` tracks no compounds at all
    for an otherwise-empty network.
    """
    compartment_ids = {c.compartment_id for c in network.compartments}
    species_ids = {s.species_id for s in network.species}
    reaction_ids = {r.reaction_id for r in network.reactions}
    enzyme_association_ids = {e.association_id for e in network.enzyme_associations}
    regulatory_interaction_ids = {r.id for r in network.regulatory_interactions}
    enzyme_state_ids = {s.id for s in network.enzyme_states}
    compound_ids = {
        s.source_compound_id for s in network.species if s.source_compound_id is not None
    }

    for species in network.species:
        if species.compartment_id not in compartment_ids:
            raise ValueError(
                f"FullNetwork species {species.species_id!r} references undefined "
                f"compartment {species.compartment_id!r}"
            )

    for reaction in network.reactions:
        for participant in reaction.participants:
            if participant.species_id not in species_ids:
                raise ValueError(
                    f"FullNetwork reaction {reaction.reaction_id!r} references undefined "
                    f"species {participant.species_id!r}"
                )
        _require_known(
            reaction.enzyme_association_ids,
            enzyme_association_ids,
            field_name=f"reaction {reaction.reaction_id}.enzyme_association_ids",
        )
        _require_known(
            reaction.regulatory_interaction_ids,
            regulatory_interaction_ids,
            field_name=f"reaction {reaction.reaction_id}.regulatory_interaction_ids",
        )

    for association in network.enzyme_associations:
        if association.reaction_id not in reaction_ids:
            raise ValueError(
                f"FullNetwork enzyme association {association.association_id!r} references "
                f"undefined reaction {association.reaction_id!r}"
            )
        if (
            association.enzyme_state_id is not None
            and association.enzyme_state_id not in enzyme_state_ids
        ):
            raise ValueError(
                f"FullNetwork enzyme association {association.association_id!r} references "
                f"undefined enzyme state {association.enzyme_state_id!r}"
            )

    for modification in network.enzyme_modifications:
        if modification.enzyme_state_id not in enzyme_state_ids:
            raise ValueError(
                f"FullNetwork enzyme modification {modification.id!r} references undefined "
                f"enzyme state {modification.enzyme_state_id!r}"
            )

    for interaction in network.allosteric_interactions:
        if interaction.enzyme_state_id not in enzyme_state_ids:
            raise ValueError(
                f"FullNetwork allosteric interaction {interaction.id!r} references undefined "
                f"enzyme state {interaction.enzyme_state_id!r}"
            )
        if compound_ids and interaction.ligand_compound_id not in compound_ids:
            raise ValueError(
                f"FullNetwork allosteric interaction {interaction.id!r} references undefined "
                f"ligand compound {interaction.ligand_compound_id!r}"
            )

    for transition in network.enzyme_state_transitions:
        if transition.from_state_id not in enzyme_state_ids:
            raise ValueError(
                f"FullNetwork enzyme state transition {transition.id!r} references undefined "
                f"from_state_id {transition.from_state_id!r}"
            )
        if transition.to_state_id not in enzyme_state_ids:
            raise ValueError(
                f"FullNetwork enzyme state transition {transition.id!r} references undefined "
                f"to_state_id {transition.to_state_id!r}"
            )
        if transition.reaction_id is not None and transition.reaction_id not in reaction_ids:
            raise ValueError(
                f"FullNetwork enzyme state transition {transition.id!r} references undefined "
                f"reaction {transition.reaction_id!r}"
            )

    for measurement in network.kinetic_measurements:
        if (
            measurement.enzyme_state_id is not None
            and measurement.enzyme_state_id not in enzyme_state_ids
        ):
            raise ValueError(
                f"FullNetwork kinetic measurement {measurement.id!r} references undefined "
                f"enzyme state {measurement.enzyme_state_id!r}"
            )

    for regulation in network.regulatory_interactions:
        _require_regulation_endpoint_known(
            regulation.target_type, regulation.target_id, reaction_ids, compound_ids, regulation.id
        )
        _require_regulation_endpoint_known(
            regulation.regulator_type,
            regulation.regulator_id,
            reaction_ids,
            compound_ids,
            regulation.id,
        )

    # Quantitative Context Resolution and Derived Enzyme Concentration increment:
    # experimental_contexts is a complete registry within FullNetwork (unlike
    # compound_ids above), so every observation's own experimental_context_id is
    # checked against it whenever set -- protein_id/compound_id/reaction_id/
    # organism_id are deliberately left unchecked, for the same disclosed reason
    # kinetic_measurements[].protein_id/.organism_id/.publication_id already are
    # (see this function's own docstring: FullNetwork tracks no such registry).
    experimental_context_ids = {c.id for c in network.experimental_contexts}
    for observation in network.quantitative_observations:
        if (
            observation.experimental_context_id is not None
            and observation.experimental_context_id not in experimental_context_ids
        ):
            raise ValueError(
                f"FullNetwork quantitative observation {observation.id!r} references undefined "
                f"experimental context {observation.experimental_context_id!r}"
            )


def _require_regulation_endpoint_known(
    entity_type: str,
    entity_id: str | None,
    reaction_ids: set[str],
    compound_ids: set[str],
    regulation_id: str,
) -> None:
    """Validate one regulation endpoint (regulator or target) only when its type is resolvable.

    Only ``"reaction"`` (against ``FullNetwork.reactions``) and
    ``"compound"`` (against the compound ids ``FullNetwork.species`` was
    derived from) are checked -- see
    ``_validate_full_network_references``'s own docstring for why every
    other entity type (``"protein"``, ``"gene"``, ...) is left unchecked
    rather than rejected or guessed at.
    """
    if entity_id is None:
        return
    normalized_type = entity_type.strip().lower() if entity_type else ""
    if normalized_type == "reaction" and entity_id not in reaction_ids:
        raise ValueError(
            f"FullNetwork regulatory interaction {regulation_id!r} references undefined "
            f"reaction {entity_id!r}"
        )
    if normalized_type == "compound" and entity_id not in compound_ids:
        raise ValueError(
            f"FullNetwork regulatory interaction {regulation_id!r} references undefined "
            f"compound {entity_id!r}"
        )


# =================================================================================================
# 4. Kinetics and parameters
# =================================================================================================


@dataclass(frozen=True, slots=True)
class KineticLawSpecification:
    """The declared structural form of one reaction's rate law -- not a fitted value.

    ``expression`` is a contract representation of the intended rate law
    (e.g. free-form text such as ``"k1 * A * B"``), not an Antimony
    serialization -- no expression parsing or generation occurs here at
    all. Reference integrity for ``parameter_ids``/``species_ids``
    against a real parameter/species set is enforced later, at
    ``ModelSpecification`` construction -- this type alone has no such
    set to check against.

    **``kinetic_law_type`` vs. ``expression`` -- two distinct facts, not
    one (Increment 8 pre-commit revision).** ``kinetic_law_type`` names
    the *selected law family* (e.g. Michaelis-Menten); ``expression`` is
    the *concrete algebraic representation* of that family, when one is
    actually known. **``expression`` is optional for every
    ``kinetic_law_type``, not only ``UNASSIGNED``**: a reaction can have
    a confidently-identified law family with no safely-reconstructable
    algebra yet (e.g. curated evidence identifies a multi-substrate
    Michaelis-Menten mechanism, but no single combining expression is
    justified from independently-declared parameters alone -- see
    ``docs/11_model_specification_assembly.md`` §8). That is a
    fundamentally different, stronger claim than ``UNASSIGNED``
    (``docs/04_core_domain_contracts.md`` §7: "the default starting
    point" -- no law-selection decision was made at all). Reading
    ``expression is None`` alone can therefore mean either "no law was
    ever assigned" (`law_type is UNASSIGNED`) or "a law family was
    assigned but its exact algebra remains unresolved" (`law_type` is
    anything else) -- never conflate the two; check `law_type` first. The
    pure, derived ``has_expression`` property answers "does this law
    currently carry a usable expression," independent of which case
    applies. An earlier draft of this revision stored the unresolved-
    algebra case as a string sentinel
    (``"UNRESOLVED_MULTI_SUBSTRATE_MECHANISM"``) placed directly in
    ``expression`` -- **removed**: a non-expression status marker must
    never occupy a field whose entire meaning is "the concrete algebraic
    representation." The unresolved state is disclosed instead through
    ``assumptions`` and a dedicated ``ModelAssumption`` (§16 of the same
    document), never through ``expression`` itself.

    **Increment 8 pre-commit revision** also made two earlier
    corrections, both driven by ``ModelSpecification``'s own purpose as
    the *authoritative* handoff to Antimony generation -- neither should
    require Increment 9 to parse text or rediscover a fact this type
    could simply state directly:

    * ``assignment_source`` is now ``KineticLawAssignmentSource``
      (previously ``ParameterSource``, reused by mistake -- see that
      enum's own docstring and ``docs/11_model_specification_assembly.md``
      §10). A kinetic law's *type* provenance ("why was this rate-law
      form chosen") is a different fact from a parameter's *value*
      provenance ("where did this number come from"); collapsing them
      into one vocabulary was exactly the kind of ambiguity a canonical
      contract must not carry.
    * ``enzyme_state_id``/``protein_id``/``complex_id`` are new,
      optional, mutually-exclusive fields (identical exclusivity
      semantics to ``KineticLawAssignment``'s own three-field target,
      and to ``CuratedReactionEnzymeAssociation``/
      ``ReactionEnzymeAssociation`` upstream of it) naming this law's own
      catalytic context directly. Previously this fact lived only in
      ``provenance_refs`` text (e.g. ``"catalytic-context::enzyme_state
      ::E_P"``) -- adequate for a human audit trail, but not for a
      downstream consumer that needs to *resolve* which catalytic
      context a law belongs to without parsing a string. All three
      ``None`` means the same thing it already means on
      ``KineticLawAssignment``: the reaction as a whole, no distinguishing
      catalytic identity (no catalyst known, or several catalysts
      collapsed because their evidence was identical).
    """

    kinetic_law_id: str
    reaction_id: str
    law_type: KineticLawType
    assignment_source: KineticLawAssignmentSource
    expression: str | None = None
    parameter_ids: tuple[str, ...] = ()
    species_ids: tuple[str, ...] = ()
    enzyme_state_id: str | None = None
    protein_id: str | None = None
    complex_id: str | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "kinetic_law_id",
            _require_non_empty_str(self.kinetic_law_id, field_name="kinetic_law_id"),
        )
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        if not isinstance(self.law_type, KineticLawType):
            raise TypeError(
                f"KineticLawSpecification.law_type must be a KineticLawType, got {self.law_type!r}"
            )
        if not isinstance(self.assignment_source, KineticLawAssignmentSource):
            raise TypeError(
                "KineticLawSpecification.assignment_source must be a "
                f"KineticLawAssignmentSource, got {self.assignment_source!r}"
            )
        object.__setattr__(
            self, "expression", _clean_optional_str(self.expression, field_name="expression")
        )
        object.__setattr__(
            self,
            "parameter_ids",
            _require_str_tuple(self.parameter_ids, field_name="parameter_ids"),
        )
        object.__setattr__(
            self, "species_ids", _require_str_tuple(self.species_ids, field_name="species_ids")
        )
        object.__setattr__(
            self,
            "enzyme_state_id",
            _clean_optional_str(self.enzyme_state_id, field_name="enzyme_state_id"),
        )
        object.__setattr__(
            self, "protein_id", _clean_optional_str(self.protein_id, field_name="protein_id")
        )
        object.__setattr__(
            self, "complex_id", _clean_optional_str(self.complex_id, field_name="complex_id")
        )
        target_fields = (self.enzyme_state_id, self.protein_id, self.complex_id)
        if sum(field is not None for field in target_fields) > 1:
            raise ValueError(
                "KineticLawSpecification allows at most one of enzyme_state_id/protein_id/"
                f"complex_id to be set, got enzyme_state_id={self.enzyme_state_id!r}, "
                f"protein_id={self.protein_id!r}, complex_id={self.complex_id!r}"
            )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )

    @property
    def has_expression(self) -> bool:
        """Pure, derived: does this law currently carry a usable algebraic expression?

        Independent of ``law_type`` -- ``False`` for ``UNASSIGNED`` (no
        law was ever selected) and equally ``False`` for a law whose
        family is known but whose exact algebra remains unresolved (e.g.
        a multi-substrate Michaelis-Menten assignment). Check
        ``law_type`` separately to distinguish those two cases; this
        property answers only "is `expression` currently populated."
        """
        return self.expression is not None


@dataclass(frozen=True, slots=True)
class ParameterSpecification:
    """One kinetic-law parameter: its identity, value, provenance, and bounds.

    ``value`` may be ``None`` -- a declared-but-not-yet-initialized
    parameter is a normal state, not an error. ``source`` is the sole
    authority on how to interpret ``value``: a ``PLACEHOLDER`` value must
    never be presented as though it were ``CURATED``/``CALIBRATED``, and
    Agent 2 must never assign ``CALIBRATED`` to a value it produced itself
    (only Agent 4's feedback may justify that source, in a later
    increment). No automatic parameter estimation occurs here or anywhere
    else in this repository.

    **``kinetic_law_assignment_id`` added in Increment 5** (Parameter
    Declaration / Initialization): the essential missing field found on
    inspection -- ``reaction_id`` alone cannot disambiguate a parameter
    declared for one catalytic context (e.g. one specific ``EnzymeState``)
    from a sibling context on the same reaction, and every parameter
    Increment 5 declares must trace back to exactly one
    ``app.agent2.kinetics.types.KineticLawAssignment``. See
    ``docs/08_parameter_declaration_initialization.md`` §5.
    """

    parameter_id: str
    name: str
    source: ParameterSource
    value: Decimal | None = None
    unit: str | None = None
    source_reference: str | None = None
    reaction_id: str | None = None
    kinetic_law_assignment_id: str | None = None
    module_ids: tuple[str, ...] = ()
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    uncertainty_text: str | None = None
    fixed: bool | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameter_id",
            _require_non_empty_str(self.parameter_id, field_name="parameter_id"),
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        if not isinstance(self.source, ParameterSource):
            raise TypeError(
                f"ParameterSpecification.source must be a ParameterSource, got {self.source!r}"
            )
        object.__setattr__(self, "value", _require_decimal_or_none(self.value, field_name="value"))
        object.__setattr__(self, "unit", _clean_optional_str(self.unit, field_name="unit"))
        object.__setattr__(
            self,
            "source_reference",
            _clean_optional_str(self.source_reference, field_name="source_reference"),
        )
        object.__setattr__(
            self,
            "reaction_id",
            _clean_optional_str(self.reaction_id, field_name="reaction_id"),
        )
        object.__setattr__(
            self,
            "kinetic_law_assignment_id",
            _clean_optional_str(
                self.kinetic_law_assignment_id, field_name="kinetic_law_assignment_id"
            ),
        )
        object.__setattr__(
            self, "module_ids", _require_str_tuple(self.module_ids, field_name="module_ids")
        )
        object.__setattr__(
            self,
            "lower_bound",
            _require_decimal_or_none(self.lower_bound, field_name="lower_bound"),
        )
        object.__setattr__(
            self,
            "upper_bound",
            _require_decimal_or_none(self.upper_bound, field_name="upper_bound"),
        )
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError(
                f"ParameterSpecification.lower_bound ({self.lower_bound!r}) must be <= "
                f"upper_bound ({self.upper_bound!r})"
            )
        object.__setattr__(
            self,
            "uncertainty_text",
            _clean_optional_str(self.uncertainty_text, field_name="uncertainty_text"),
        )
        object.__setattr__(self, "fixed", _require_bool_or_none(self.fixed, field_name="fixed"))
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )

    @property
    def has_value(self) -> bool:
        """Pure, deterministic: whether ``value`` is set. Never a confidence judgment."""
        return self.value is not None

    @property
    def is_placeholder(self) -> bool:
        return self.source is ParameterSource.PLACEHOLDER

    @property
    def is_calibrated(self) -> bool:
        return self.source is ParameterSource.CALIBRATED

    @property
    def is_curated(self) -> bool:
        return self.source is ParameterSource.CURATED


# =================================================================================================
# 5. Module decomposition domain
# =================================================================================================


@dataclass(frozen=True, slots=True)
class BoundaryAssessment:
    """One candidate module boundary's qualitative assessment.

    No heuristic computation exists yet -- this is the contract a future
    boundary-heuristic rule set will populate. ``parameter_basis``
    discloses, qualitatively, whether the assessment was informed by
    parameter data and of what quality (never a numeric weight).
    ``policy_version`` records which boundary-heuristic rule set (once one
    exists) produced this assessment.
    """

    boundary_id: str
    upstream_element_id: str
    downstream_element_id: str
    likelihood: BoundaryLikelihood
    explanation: str
    policy_version: str
    shared_species_ids: tuple[str, ...] = ()
    connecting_reaction_ids: tuple[str, ...] = ()
    supporting_reason_codes: tuple[str, ...] = ()
    opposing_reason_codes: tuple[str, ...] = ()
    kinetic_law_ids: tuple[str, ...] = ()
    parameter_ids: tuple[str, ...] = ()
    parameter_basis: BoundaryParameterBasis | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "boundary_id", _require_non_empty_str(self.boundary_id, field_name="boundary_id")
        )
        object.__setattr__(
            self,
            "upstream_element_id",
            _require_non_empty_str(self.upstream_element_id, field_name="upstream_element_id"),
        )
        object.__setattr__(
            self,
            "downstream_element_id",
            _require_non_empty_str(self.downstream_element_id, field_name="downstream_element_id"),
        )
        if not isinstance(self.likelihood, BoundaryLikelihood):
            raise TypeError(
                f"BoundaryAssessment.likelihood must be a BoundaryLikelihood, "
                f"got {self.likelihood!r}"
            )
        object.__setattr__(
            self, "explanation", _require_non_empty_str(self.explanation, field_name="explanation")
        )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        for name in (
            "shared_species_ids",
            "connecting_reaction_ids",
            "supporting_reason_codes",
            "opposing_reason_codes",
            "kinetic_law_ids",
            "parameter_ids",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        if self.parameter_basis is not None and not isinstance(
            self.parameter_basis, BoundaryParameterBasis
        ):
            raise TypeError(
                "BoundaryAssessment.parameter_basis must be a BoundaryParameterBasis or None, "
                f"got {self.parameter_basis!r}"
            )


@dataclass(frozen=True, slots=True)
class ModuleBoundaryInterface:
    """One explicit interface element required for a standalone module model.

    Structural only -- no simulation semantics. Agent 2 never invents a
    boundary condition silently; if this cannot be stated explicitly for a
    module, no standalone model is produced for it
    (``docs/01_agent2_architecture.md`` §14).
    """

    species_id: str
    role: ModuleInterfaceRole
    direction: str
    assumption: str
    externally_controlled: bool
    initial_value: Decimal | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        if not isinstance(self.role, ModuleInterfaceRole):
            raise TypeError(
                f"ModuleBoundaryInterface.role must be a ModuleInterfaceRole, got {self.role!r}"
            )
        object.__setattr__(
            self, "direction", _require_non_empty_str(self.direction, field_name="direction")
        )
        object.__setattr__(
            self, "assumption", _require_non_empty_str(self.assumption, field_name="assumption")
        )
        if not isinstance(self.externally_controlled, bool):
            raise TypeError(
                "ModuleBoundaryInterface.externally_controlled must be a bool, "
                f"got {self.externally_controlled!r}"
            )
        object.__setattr__(
            self,
            "initial_value",
            _require_decimal_or_none(self.initial_value, field_name="initial_value"),
        )
        object.__setattr__(self, "unit", _clean_optional_str(self.unit, field_name="unit"))


@dataclass(frozen=True, slots=True)
class ModuleSpecification:
    """One module: a named subset of the full network plus its boundary interfaces.

    Always traceable to the full model via ``source_boundary_ids`` -- a
    module is never defined independently of the ``BoundaryAssessment``\\ s
    that justified it. Requires at least one reaction (an empty module is
    not meaningful). Every id-bearing tuple is internally unique.

    **Increment 7 (Module Decomposition)** added
    ``kinetic_law_assignment_ids``, ``compartment_ids``,
    ``enzyme_state_ids``, ``interface_species_ids``, and
    ``boundary_interface_ids`` -- all references only, never duplicated
    data (``docs/10_module_decomposition.md`` §6). ``kinetic_law_ids``
    (Increment 1, referencing the not-yet-produced
    ``KineticLawSpecification.kinetic_law_id`` namespace) is deliberately
    left untouched and unpopulated by Increment 7: the kinetic-law
    decisions Increment 7 actually consumes are
    ``app.agent2.kinetics.types.KineticLawAssignment.assignment_id``
    values, a distinct id namespace, hence the separate
    ``kinetic_law_assignment_ids`` field rather than conflating the two
    (``docs/10_module_decomposition.md`` §5). ``boundary_interface_ids``
    references ``InterModuleBoundaryInterface.interface_id`` values on the
    owning ``ModuleDecomposition.interfaces`` -- a different concept from
    the pre-existing, per-species ``boundary_interfaces``
    (``ModuleBoundaryInterface``), which remains reserved for a future
    increment's standalone-Antimony boundary-condition declarations.
    """

    module_id: str
    name: str
    reaction_ids: tuple[str, ...] = ()
    species_ids: tuple[str, ...] = ()
    parameter_ids: tuple[str, ...] = ()
    kinetic_law_ids: tuple[str, ...] = ()
    kinetic_law_assignment_ids: tuple[str, ...] = ()
    compartment_ids: tuple[str, ...] = ()
    enzyme_state_ids: tuple[str, ...] = ()
    interface_species_ids: tuple[str, ...] = ()
    boundary_interfaces: tuple[ModuleBoundaryInterface, ...] = ()
    boundary_interface_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    source_boundary_ids: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "module_id", _require_non_empty_str(self.module_id, field_name="module_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        for name in (
            "reaction_ids",
            "species_ids",
            "parameter_ids",
            "kinetic_law_ids",
            "kinetic_law_assignment_ids",
            "compartment_ids",
            "enzyme_state_ids",
            "interface_species_ids",
            "boundary_interface_ids",
            "assumptions",
            "source_boundary_ids",
            "provenance_refs",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        for name in (
            "reaction_ids",
            "species_ids",
            "parameter_ids",
            "kinetic_law_ids",
            "kinetic_law_assignment_ids",
            "compartment_ids",
            "enzyme_state_ids",
            "interface_species_ids",
            "boundary_interface_ids",
        ):
            _require_unique(getattr(self, name), field_name=f"ModuleSpecification.{name}")
        if not self.reaction_ids:
            raise ValueError(
                "ModuleSpecification must reference at least one reaction -- an empty module is "
                "not meaningful"
            )
        object.__setattr__(
            self,
            "boundary_interfaces",
            _require_tuple_of(
                self.boundary_interfaces, ModuleBoundaryInterface, field_name="boundary_interfaces"
            ),
        )

    @property
    def has_explicit_boundary_interfaces(self) -> bool:
        """Pure structural predicate: at least one ``ModuleBoundaryInterface`` is declared.

        This is the same predicate used to decide whether a
        ``ModuleAntimonyArtifact.standalone_antimony`` may be produced for
        this module (never inferred any other way).
        """
        return len(self.boundary_interfaces) > 0


@dataclass(frozen=True, slots=True)
class InterModuleBoundaryInterface:
    """One explicit interface where two modules of one ``ModuleDecomposition`` meet.

    **Introduced in Increment 7 (Module Decomposition).** Distinct from
    ``ModuleBoundaryInterface`` (Increment 1), which records one
    per-species boundary-condition declaration *within* a single module
    for a future standalone-Antimony variant -- this type instead records
    the *pairwise* relationship between two modules at one boundary
    interface (Increment 7 instructions, Step 11: "upstream module,
    downstream module, shared species, boundary id, boundary likelihood,
    assumptions"). Never invents a boundary condition: ``assumptions`` may
    disclose why the interface exists, never a fabricated flux or
    concentration. ``shared_species_ids`` are references to
    ``FullNetwork.species`` only -- never duplicated or ghost species
    (``docs/10_module_decomposition.md`` §11-12).
    """

    interface_id: str
    upstream_module_id: str
    downstream_module_id: str
    boundary_id: str
    boundary_likelihood: BoundaryLikelihood
    shared_species_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "interface_id",
            _require_non_empty_str(self.interface_id, field_name="interface_id"),
        )
        object.__setattr__(
            self,
            "upstream_module_id",
            _require_non_empty_str(self.upstream_module_id, field_name="upstream_module_id"),
        )
        object.__setattr__(
            self,
            "downstream_module_id",
            _require_non_empty_str(self.downstream_module_id, field_name="downstream_module_id"),
        )
        if self.upstream_module_id == self.downstream_module_id:
            raise ValueError(
                "InterModuleBoundaryInterface.upstream_module_id and .downstream_module_id must "
                f"differ -- an interface only exists between two different modules, got "
                f"{self.upstream_module_id!r} for both"
            )
        object.__setattr__(
            self, "boundary_id", _require_non_empty_str(self.boundary_id, field_name="boundary_id")
        )
        if not isinstance(self.boundary_likelihood, BoundaryLikelihood):
            raise TypeError(
                "InterModuleBoundaryInterface.boundary_likelihood must be a BoundaryLikelihood, "
                f"got {self.boundary_likelihood!r}"
            )
        object.__setattr__(
            self,
            "shared_species_ids",
            _require_str_tuple(self.shared_species_ids, field_name="shared_species_ids"),
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )


@dataclass(frozen=True, slots=True)
class ModuleDecomposition:
    """The full network's partition into modules, as of one boundary-policy version.

    References modules/boundaries by id -- never duplicates them.
    ``policy_version`` prevents a decomposition produced under one
    heuristic rule set from being silently reinterpreted under a later,
    different one.

    **Increment 7 (Module Decomposition)** introduced the first real
    partitioning algorithm and added three fields: ``interfaces`` (every
    ``InterModuleBoundaryInterface`` where two of this decomposition's
    modules meet), ``candidate_boundary_ids`` (every boundary this policy
    deliberately did *not* cut but also did not discard -- `MEDIUM`
    evidence preserved for a future decomposition, never silently
    dropped, ``docs/10_module_decomposition.md`` §9), and ``explanation``
    (a deterministic, template-based summary of how this decomposition
    was produced, mirroring ``BoundaryAssessment.explanation``).
    ``boundary_assessment_ids`` records every boundary this policy
    actually *selected* as a cut (`HIGH`/`VERY_HIGH`) -- distinct from
    ``candidate_boundary_ids``, which are explicitly not cuts.
    """

    decomposition_id: str
    name: str
    policy_version: str
    created_from_network_id: str
    module_ids: tuple[str, ...] = ()
    boundary_assessment_ids: tuple[str, ...] = ()
    candidate_boundary_ids: tuple[str, ...] = ()
    interfaces: tuple[InterModuleBoundaryInterface, ...] = ()
    assumptions: tuple[str, ...] = ()
    parameter_basis_summary: BoundaryParameterBasis | None = None
    explanation: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decomposition_id",
            _require_non_empty_str(self.decomposition_id, field_name="decomposition_id"),
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        object.__setattr__(
            self,
            "created_from_network_id",
            _require_non_empty_str(
                self.created_from_network_id, field_name="created_from_network_id"
            ),
        )
        for name in (
            "module_ids",
            "boundary_assessment_ids",
            "candidate_boundary_ids",
            "assumptions",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        _require_unique(self.module_ids, field_name="ModuleDecomposition.module_ids")
        _require_unique(
            self.boundary_assessment_ids, field_name="ModuleDecomposition.boundary_assessment_ids"
        )
        _require_unique(
            self.candidate_boundary_ids, field_name="ModuleDecomposition.candidate_boundary_ids"
        )
        overlap = set(self.boundary_assessment_ids) & set(self.candidate_boundary_ids)
        if overlap:
            raise ValueError(
                "ModuleDecomposition.boundary_assessment_ids (selected cuts) and "
                f".candidate_boundary_ids (preserved, not cut) must be disjoint, overlap: "
                f"{sorted(overlap)}"
            )
        object.__setattr__(
            self,
            "interfaces",
            _require_tuple_of(
                self.interfaces, InterModuleBoundaryInterface, field_name="interfaces"
            ),
        )
        _require_unique(
            tuple(interface.interface_id for interface in self.interfaces),
            field_name="ModuleDecomposition.interfaces[].interface_id",
        )
        if self.parameter_basis_summary is not None and not isinstance(
            self.parameter_basis_summary, BoundaryParameterBasis
        ):
            raise TypeError(
                "ModuleDecomposition.parameter_basis_summary must be a BoundaryParameterBasis or "
                f"None, got {self.parameter_basis_summary!r}"
            )
        object.__setattr__(
            self, "explanation", _clean_optional_str(self.explanation, field_name="explanation")
        )


# =================================================================================================
# 6. ModelAssumption
# =================================================================================================


@dataclass(frozen=True, slots=True)
class ModelAssumption:
    """One structured, categorized, model-level assumption record.

    Distinct from the lightweight free-text ``assumptions: tuple[str, ...]``
    every structural type already carries for local disclosures:
    ``ModelAssumption`` is the referenceable layer for cross-cutting
    assumptions a ``ModelSpecification`` wants to name explicitly (e.g. by
    ``assumption_id`` from a boundary's ``supporting_reason_codes``). Kept
    minimal -- no free-form LLM rationale field.
    """

    assumption_id: str
    category: str
    statement: str
    related_entity_ids: tuple[str, ...] = ()
    source: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assumption_id",
            _require_non_empty_str(self.assumption_id, field_name="assumption_id"),
        )
        object.__setattr__(
            self, "category", _require_non_empty_str(self.category, field_name="category")
        )
        object.__setattr__(
            self, "statement", _require_non_empty_str(self.statement, field_name="statement")
        )
        object.__setattr__(
            self,
            "related_entity_ids",
            _require_str_tuple(self.related_entity_ids, field_name="related_entity_ids"),
        )
        object.__setattr__(self, "source", _clean_optional_str(self.source, field_name="source"))
        object.__setattr__(
            self, "reason_code", _clean_optional_str(self.reason_code, field_name="reason_code")
        )


# =================================================================================================
# 6a. Derived enzyme concentration (Quantitative Context Resolution and Derived Enzyme
# Concentration increment)
# =================================================================================================


class EnzymeConcentrationBasis(StrEnum):
    """Which precedence tier produced one ``EnzymeConcentration`` -- a qualitative
    categorical disclosure, never a numeric confidence weight (mirrors
    ``BoundaryParameterBasis``'s identical role for ``BoundaryAssessment``).

    Exactly the first five tiers of ``app.agent2.quantitative_context``'s own
    six-tier precedence order (see that package's module docstring); the sixth
    tier, "unresolved," produces no ``EnzymeConcentration`` at all and therefore
    has no member here -- see
    ``app.agent2.quantitative_context.types.QuantitativeContextResolutionOutcome``
    for how an unresolved protein is represented instead.
    """

    EXPERIMENT_SPECIFIC_CONCENTRATION = "EXPERIMENT_SPECIFIC_CONCENTRATION"
    EXPERIMENT_SPECIFIC_ABUNDANCE_AND_VOLUME = "EXPERIMENT_SPECIFIC_ABUNDANCE_AND_VOLUME"
    REFERENCE_CONCENTRATION = "REFERENCE_CONCENTRATION"
    REFERENCE_ABUNDANCE_AND_COMPATIBLE_VOLUME = "REFERENCE_ABUNDANCE_AND_COMPATIBLE_VOLUME"
    REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME = "REFERENCE_ABUNDANCE_AND_ASSUMED_VOLUME"


@dataclass(frozen=True, slots=True)
class EnzymeConcentrationDependency:
    """One input a derived ``EnzymeConcentration`` depends on -- either a real
    Agent 1 ``CuratedQuantitativeObservation`` (``observation_id`` set) or an
    explicit, disclosed modeling assumption with no underlying observation at all
    (``assumption_notes`` set, ``observation_id=None`` -- the 0.1 pL reference
    cell-volume case). At least one of the two must be set; both may be set
    together (e.g. a real cell-volume observation whose own applicability to this
    exact protein/context still carries a caveat worth stating).

    Mirrors ``app.agent1.types.CuratedQuantitativeObservationDependency``'s own
    ``role``/``assumption_notes`` shape, extended with ``observation_id`` since,
    unlike Agent 1's own record (nested only inside an already-``DERIVED``
    observation that always names real inputs), this dependency must also be able
    to represent a pure assumption with nothing to point to.
    """

    role: str
    observation_id: str | None = None
    assumption_notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _require_non_empty_str(self.role, field_name="role"))
        object.__setattr__(
            self,
            "observation_id",
            _clean_optional_str(self.observation_id, field_name="observation_id"),
        )
        object.__setattr__(
            self,
            "assumption_notes",
            _clean_optional_str(self.assumption_notes, field_name="assumption_notes"),
        )
        if self.observation_id is None and self.assumption_notes is None:
            raise ValueError(
                "EnzymeConcentrationDependency requires at least one of "
                "observation_id/assumption_notes"
            )


@dataclass(frozen=True, slots=True)
class EnzymeConcentration:
    """One protein's derived enzyme concentration, in canonical nM -- never a curated
    Agent 1 measurement itself, always Agent 2's own derivation (Quantitative
    Context Resolution and Derived Enzyme Concentration increment).

    Produced exclusively by
    ``app.agent2.quantitative_context.resolver.resolve_enzyme_concentrations``,
    never assembled by hand elsewhere in this repository. ``unit`` is always
    ``"nM"`` -- this type represents a concentration, never an abundance or a raw
    observation; ``basis`` names which precedence tier produced it, and
    ``dependencies`` preserves exactly what real observation(s) (or explicit
    assumption) it was derived from -- never silently discarded provenance, and
    never a rewrite of the source ``CuratedQuantitativeObservation`` itself.

    Derived at the **protein level only** (task's own explicit scope): no
    allocation across enzyme states, PTM states, complexes, or isoforms is ever
    performed here -- a protein with more than one catalytic context (multiple
    ``EnzymeState``s, a homo-/hetero-oligomeric complex) still gets exactly one
    total-protein concentration, and any state-specific allocation remains
    unresolved, deliberately, for later work.
    """

    protein_id: str
    value: Decimal
    basis: EnzymeConcentrationBasis
    policy_version: str
    unit: str = "nM"
    dependencies: tuple[EnzymeConcentrationDependency, ...] = ()
    experimental_context_id: str | None = None
    assumption_reason_codes: tuple[str, ...] = ()
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "protein_id", _require_non_empty_str(self.protein_id, field_name="protein_id")
        )
        if not isinstance(self.value, Decimal):
            raise TypeError(f"EnzymeConcentration.value must be a Decimal, got {self.value!r}")
        if self.value < 0:
            raise ValueError(f"EnzymeConcentration.value must be >= 0, got {self.value!r}")
        if not isinstance(self.basis, EnzymeConcentrationBasis):
            raise TypeError(
                f"EnzymeConcentration.basis must be an EnzymeConcentrationBasis, "
                f"got {self.basis!r}"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        if self.unit != "nM":
            raise ValueError(f"EnzymeConcentration.unit must be 'nM', got {self.unit!r}")
        object.__setattr__(
            self,
            "dependencies",
            _require_tuple_of(
                self.dependencies, EnzymeConcentrationDependency, field_name="dependencies"
            ),
        )
        object.__setattr__(
            self,
            "experimental_context_id",
            _clean_optional_str(
                self.experimental_context_id, field_name="experimental_context_id"
            ),
        )
        object.__setattr__(
            self,
            "assumption_reason_codes",
            _require_str_tuple(
                self.assumption_reason_codes, field_name="assumption_reason_codes"
            ),
        )
        object.__setattr__(self, "notes", _clean_optional_str(self.notes, field_name="notes"))


# =================================================================================================
# 7. ModelSpecification -- the top-level, authoritative contract
# =================================================================================================


@dataclass(frozen=True, slots=True)
class ModelSpecification:
    """The top-level, authoritative contract Agent 2 produces.

    References a ``FullNetwork`` plus every ``KineticLawSpecification``/
    ``ParameterSpecification``/``BoundaryAssessment``/
    ``ModuleDecomposition``/``ModuleSpecification`` derived from it, and
    enforces full internal reference integrity between them (every id one
    object names must actually exist among the others). Never performs
    Agent-3-level mass-balance, connectivity, unit-consistency, or
    conservation-law analysis -- only structural referential integrity.
    """

    model_id: str
    name: str
    full_network: FullNetwork
    organism_id: str | None = None
    kinetic_laws: tuple[KineticLawSpecification, ...] = ()
    parameters: tuple[ParameterSpecification, ...] = ()
    boundary_assessments: tuple[BoundaryAssessment, ...] = ()
    module_decomposition: ModuleDecomposition | None = None
    module_specifications: tuple[ModuleSpecification, ...] = ()
    assumptions: tuple[str, ...] = ()
    model_assumptions: tuple[ModelAssumption, ...] = ()
    #: Quantitative Context Resolution and Derived Enzyme Concentration increment.
    #: Zero or more ``EnzymeConcentration`` records, at most one per protein (see
    #: ``__post_init__``'s own uniqueness check below) -- never referenced against
    #: any ``FullNetwork`` protein registry, since ``FullNetwork`` tracks no such
    #: registry at all (the same disclosed, pre-existing limitation
    #: ``_validate_full_network_references``/``_validate_model_specification_references``
    #: already document for every other ``protein_id``-typed field).
    enzyme_concentrations: tuple[EnzymeConcentration, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    contract_version: str = AGENT2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_id", _require_non_empty_str(self.model_id, field_name="model_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        if not isinstance(self.full_network, FullNetwork):
            raise TypeError(
                f"ModelSpecification.full_network must be a FullNetwork, got {self.full_network!r}"
            )
        object.__setattr__(
            self, "organism_id", _clean_optional_str(self.organism_id, field_name="organism_id")
        )
        object.__setattr__(
            self,
            "kinetic_laws",
            _require_tuple_of(
                self.kinetic_laws, KineticLawSpecification, field_name="kinetic_laws"
            ),
        )
        object.__setattr__(
            self,
            "parameters",
            _require_tuple_of(self.parameters, ParameterSpecification, field_name="parameters"),
        )
        object.__setattr__(
            self,
            "boundary_assessments",
            _require_tuple_of(
                self.boundary_assessments, BoundaryAssessment, field_name="boundary_assessments"
            ),
        )
        if self.module_decomposition is not None and not isinstance(
            self.module_decomposition, ModuleDecomposition
        ):
            raise TypeError(
                "ModelSpecification.module_decomposition must be a ModuleDecomposition or None, "
                f"got {self.module_decomposition!r}"
            )
        object.__setattr__(
            self,
            "module_specifications",
            _require_tuple_of(
                self.module_specifications, ModuleSpecification, field_name="module_specifications"
            ),
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "model_assumptions",
            _require_tuple_of(
                self.model_assumptions, ModelAssumption, field_name="model_assumptions"
            ),
        )
        object.__setattr__(
            self,
            "enzyme_concentrations",
            _require_tuple_of(
                self.enzyme_concentrations, EnzymeConcentration, field_name="enzyme_concentrations"
            ),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        object.__setattr__(
            self,
            "contract_version",
            _require_non_empty_str(self.contract_version, field_name="contract_version"),
        )

        _require_unique(
            tuple(law.kinetic_law_id for law in self.kinetic_laws),
            field_name="ModelSpecification.kinetic_laws[].kinetic_law_id",
        )
        _require_unique(
            tuple(param.parameter_id for param in self.parameters),
            field_name="ModelSpecification.parameters[].parameter_id",
        )
        _require_unique(
            tuple(module.module_id for module in self.module_specifications),
            field_name="ModelSpecification.module_specifications[].module_id",
        )
        _require_unique(
            tuple(ec.protein_id for ec in self.enzyme_concentrations),
            field_name="ModelSpecification.enzyme_concentrations[].protein_id",
        )
        _require_unique(
            tuple(boundary.boundary_id for boundary in self.boundary_assessments),
            field_name="ModelSpecification.boundary_assessments[].boundary_id",
        )

        _validate_model_specification_references(self)


def _validate_model_specification_references(spec: ModelSpecification) -> None:
    """Every internal cross-reference in ``spec`` must resolve. See ``ModelSpecification``.

    A module-level function (not a method) purely to keep
    ``ModelSpecification.__post_init__`` readable -- it performs no
    computation ``__post_init__`` could not, and is never called from
    anywhere else.

    **Increment 7 (Module Decomposition) scope note**: ``module
    .kinetic_law_assignment_ids`` is never validated here -- unlike
    ``module.kinetic_law_ids`` (checked against ``spec.kinetic_laws``,
    the ``KineticLawSpecification`` namespace), ``ModelSpecification``
    carries no ``KineticLawAssignment`` registry to validate the
    ``KineticLawAssignment.assignment_id`` namespace against. This is a
    disclosed limitation, not an oversight -- mirroring
    ``_validate_full_network_references``'s own identical "nothing to
    validate against" precedent for fields naming an entity type
    ``FullNetwork`` does not track.
    """
    reaction_ids = {reaction.reaction_id for reaction in spec.full_network.reactions}
    species_ids = {species.species_id for species in spec.full_network.species}
    compartment_ids = {c.compartment_id for c in spec.full_network.compartments}
    enzyme_state_ids = {s.id for s in spec.full_network.enzyme_states}
    kinetic_law_ids = {law.kinetic_law_id for law in spec.kinetic_laws}
    parameter_ids = {param.parameter_id for param in spec.parameters}
    module_ids = {module.module_id for module in spec.module_specifications}
    boundary_ids = {boundary.boundary_id for boundary in spec.boundary_assessments}

    for law in spec.kinetic_laws:
        _require_known(
            (law.reaction_id,),
            reaction_ids,
            field_name=f"kinetic law {law.kinetic_law_id}.reaction_id",
        )
        _require_known(
            law.parameter_ids,
            parameter_ids,
            field_name=f"kinetic law {law.kinetic_law_id}.parameter_ids",
        )
        _require_known(
            law.species_ids, species_ids, field_name=f"kinetic law {law.kinetic_law_id}.species_ids"
        )
        # Increment 8 pre-commit revision: enzyme_state_id is a first-class catalytic-context
        # field (previously provenance text only) and FullNetwork.enzyme_states is a real,
        # complete registry to check it against -- unlike protein_id/complex_id, which name an
        # entity type FullNetwork does not track at all (the same disclosed, deliberate
        # limitation _validate_full_network_references already documents).
        if law.enzyme_state_id is not None:
            _require_known(
                (law.enzyme_state_id,),
                enzyme_state_ids,
                field_name=f"kinetic law {law.kinetic_law_id}.enzyme_state_id",
            )

    for param in spec.parameters:
        if param.reaction_id is not None:
            _require_known(
                (param.reaction_id,),
                reaction_ids,
                field_name=f"parameter {param.parameter_id}.reaction_id",
            )

    for reaction in spec.full_network.reactions:
        if reaction.kinetic_law_id is not None:
            _require_known(
                (reaction.kinetic_law_id,),
                kinetic_law_ids,
                field_name=f"reaction {reaction.reaction_id}.kinetic_law_id",
            )

    for module in spec.module_specifications:
        _require_known(
            module.reaction_ids, reaction_ids, field_name=f"module {module.module_id}.reaction_ids"
        )
        _require_known(
            module.species_ids, species_ids, field_name=f"module {module.module_id}.species_ids"
        )
        _require_known(
            module.parameter_ids,
            parameter_ids,
            field_name=f"module {module.module_id}.parameter_ids",
        )
        _require_known(
            module.kinetic_law_ids,
            kinetic_law_ids,
            field_name=f"module {module.module_id}.kinetic_law_ids",
        )
        _require_known(
            module.source_boundary_ids,
            boundary_ids,
            field_name=f"module {module.module_id}.source_boundary_ids",
        )
        _require_known(
            module.compartment_ids,
            compartment_ids,
            field_name=f"module {module.module_id}.compartment_ids",
        )
        _require_known(
            module.enzyme_state_ids,
            enzyme_state_ids,
            field_name=f"module {module.module_id}.enzyme_state_ids",
        )
        _require_known(
            module.interface_species_ids,
            species_ids,
            field_name=f"module {module.module_id}.interface_species_ids",
        )
        for interface in module.boundary_interfaces:
            _require_known(
                (interface.species_id,),
                species_ids,
                field_name=f"module {module.module_id} boundary interface species_id",
            )

    if spec.module_decomposition is not None:
        decomposition = spec.module_decomposition
        _require_known(
            decomposition.module_ids,
            module_ids,
            field_name="module_decomposition.module_ids",
        )
        _require_known(
            decomposition.boundary_assessment_ids,
            boundary_ids,
            field_name="module_decomposition.boundary_assessment_ids",
        )
        _require_known(
            decomposition.candidate_boundary_ids,
            boundary_ids,
            field_name="module_decomposition.candidate_boundary_ids",
        )
        if decomposition.created_from_network_id != spec.full_network.network_id:
            raise ValueError(
                "module_decomposition.created_from_network_id "
                f"({decomposition.created_from_network_id!r}) must equal "
                f"full_network.network_id ({spec.full_network.network_id!r})"
            )
        interface_ids = {interface.interface_id for interface in decomposition.interfaces}
        for interface in decomposition.interfaces:
            _require_known(
                (interface.upstream_module_id, interface.downstream_module_id),
                module_ids,
                field_name=f"module_decomposition interface {interface.interface_id} module ids",
            )
            _require_known(
                (interface.boundary_id,),
                boundary_ids,
                field_name=f"module_decomposition interface {interface.interface_id}.boundary_id",
            )
            _require_known(
                interface.shared_species_ids,
                species_ids,
                field_name=(
                    f"module_decomposition interface {interface.interface_id}"
                    ".shared_species_ids"
                ),
            )
        for module in spec.module_specifications:
            _require_known(
                module.boundary_interface_ids,
                interface_ids,
                field_name=f"module {module.module_id}.boundary_interface_ids",
            )


# =================================================================================================
# 8. Antimony artifact contracts
# =================================================================================================


class AntimonyArtifactReadiness(StrEnum):
    """Whether one generated Antimony artifact is actually simulatable, or only descriptive.

    Introduced in Increment 9 (Antimony Generation) -- deliberately three
    values, not a lifecycle system. ``EXECUTABLE`` means every reaction's
    kinetic law has a resolved expression with every referenced parameter
    numerically initialized, and (for a module) that
    ``standalone_antimony`` is populated. ``NON_EXECUTABLE_UNRESOLVED_KINETICS``
    means generation produced text but withheld executable status because
    at least one referenced ``KineticLawSpecification`` has no resolved
    expression, an unresolved reversibility, or a parameter with no
    numeric value -- never because Agent 9 fabricated a missing fact.
    ``VIEW_ONLY`` is reserved for a module's subset view, which is never
    claimed to be independently simulatable regardless of its own
    kinetics. Never computed by inference across artifacts -- the
    generator sets it directly from what it actually produced. See
    ``docs/12_antimony_generation.md`` §21-22.
    """

    EXECUTABLE = "EXECUTABLE"
    NON_EXECUTABLE_UNRESOLVED_KINETICS = "NON_EXECUTABLE_UNRESOLVED_KINETICS"
    VIEW_ONLY = "VIEW_ONLY"


@dataclass(frozen=True, slots=True)
class FullAntimonyArtifact:
    """The full, canonical Antimony model text.

    **Increment 9 (Antimony Generation)** added ``readiness``/
    ``unresolved_kinetic_law_ids``: the full model is always exactly one
    of ``EXECUTABLE`` (``unresolved_kinetic_law_ids`` empty) or
    ``NON_EXECUTABLE_UNRESOLVED_KINETICS`` (``unresolved_kinetic_law_ids``
    non-empty, naming exactly which ``KineticLawSpecification`` rows
    blocked full executability) -- ``VIEW_ONLY`` is not a legal value here,
    since the full model is never merely a subset view. See
    ``docs/12_antimony_generation.md`` §21.

    **Increment 9 pre-commit revision** added ``unresolved_reaction_ids``:
    a biochemical ``ReactionSpecification`` and a catalytic
    ``KineticLawSpecification`` contribution are not the same thing -- one
    reaction can carry more than one kinetic-law context (e.g. one per
    enzyme state), and Antimony generation now always emits exactly one
    Antimony reaction per ``ReactionSpecification`` (never one per
    kinetic law). ``unresolved_kinetic_law_ids`` alone cannot tell a
    downstream consumer *which reactions* are blocked without re-deriving
    the law-to-reaction mapping itself; ``unresolved_reaction_ids`` names
    those reactions directly. Populated in lockstep with
    ``unresolved_kinetic_law_ids`` under the same ``readiness`` rules --
    empty iff ``readiness is EXECUTABLE``. See
    ``docs/12_antimony_generation.md`` §7/§11a.
    """

    model_id: str
    model_specification_id: str
    antimony_text: str
    generator_version: str
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    readiness: AntimonyArtifactReadiness = AntimonyArtifactReadiness.EXECUTABLE
    unresolved_kinetic_law_ids: tuple[str, ...] = ()
    unresolved_reaction_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_id", _require_non_empty_str(self.model_id, field_name="model_id")
        )
        object.__setattr__(
            self,
            "model_specification_id",
            _require_non_empty_str(
                self.model_specification_id, field_name="model_specification_id"
            ),
        )
        object.__setattr__(
            self,
            "antimony_text",
            _require_non_empty_str(self.antimony_text, field_name="antimony_text"),
        )
        object.__setattr__(
            self,
            "generator_version",
            _require_non_empty_str(self.generator_version, field_name="generator_version"),
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        if not isinstance(self.readiness, AntimonyArtifactReadiness):
            raise TypeError(
                "FullAntimonyArtifact.readiness must be an AntimonyArtifactReadiness, "
                f"got {self.readiness!r}"
            )
        if self.readiness is AntimonyArtifactReadiness.VIEW_ONLY:
            raise ValueError(
                "FullAntimonyArtifact.readiness must not be VIEW_ONLY -- the full model is "
                "never merely a subset view"
            )
        object.__setattr__(
            self,
            "unresolved_kinetic_law_ids",
            _require_str_tuple(
                self.unresolved_kinetic_law_ids, field_name="unresolved_kinetic_law_ids"
            ),
        )
        _require_unique(
            self.unresolved_kinetic_law_ids,
            field_name="FullAntimonyArtifact.unresolved_kinetic_law_ids",
        )
        object.__setattr__(
            self,
            "unresolved_reaction_ids",
            _require_str_tuple(
                self.unresolved_reaction_ids, field_name="unresolved_reaction_ids"
            ),
        )
        _require_unique(
            self.unresolved_reaction_ids,
            field_name="FullAntimonyArtifact.unresolved_reaction_ids",
        )
        if self.readiness is AntimonyArtifactReadiness.EXECUTABLE and (
            self.unresolved_kinetic_law_ids or self.unresolved_reaction_ids
        ):
            raise ValueError(
                "FullAntimonyArtifact.readiness=EXECUTABLE requires an empty "
                "unresolved_kinetic_law_ids and an empty unresolved_reaction_ids"
            )
        if self.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS and (
            not self.unresolved_kinetic_law_ids or not self.unresolved_reaction_ids
        ):
            raise ValueError(
                "FullAntimonyArtifact.readiness=NON_EXECUTABLE_UNRESOLVED_KINETICS requires a "
                "non-empty unresolved_kinetic_law_ids and a non-empty unresolved_reaction_ids"
            )


@dataclass(frozen=True, slots=True)
class ModuleAntimonyArtifact:
    """One module's Antimony output(s).

    ``antimony_view`` (a subset view, not necessarily simulatable) may
    exist without ``standalone_antimony``. ``standalone_antimony`` may be
    present only when ``boundary_interfaces`` is non-empty -- the same
    structural predicate as ``ModuleSpecification
    .has_explicit_boundary_interfaces``. No boundary condition is ever
    invented to satisfy this rule; a module lacking explicit interfaces
    simply has no standalone artifact.

    **Increment 9 (Antimony Generation)** added ``readiness``/
    ``unresolved_kinetic_law_ids``: ``VIEW_ONLY`` (the default) requires
    ``standalone_antimony`` to be ``None``; ``EXECUTABLE`` requires
    ``standalone_antimony`` to be populated and
    ``unresolved_kinetic_law_ids`` empty;
    ``NON_EXECUTABLE_UNRESOLVED_KINETICS`` means the module's boundary
    interfaces were explicit enough to be eligible for a standalone model,
    but at least one of its kinetic laws blocked executability -- the
    standalone text is withheld (``standalone_antimony`` stays ``None``)
    rather than emitted as though it were runnable. See
    ``docs/12_antimony_generation.md`` §22-23.

    **Increment 9 pre-commit revision** added ``unresolved_reaction_ids``
    for the same reason as ``FullAntimonyArtifact``'s own identical
    addition -- a module may include a reaction whose multiple catalytic
    contexts leave its composed rate unresolved; this names the reaction
    directly rather than requiring a consumer to re-derive it from
    ``unresolved_kinetic_law_ids``. Empty whenever ``readiness`` is
    ``VIEW_ONLY``/``EXECUTABLE``; non-empty iff
    ``NON_EXECUTABLE_UNRESOLVED_KINETICS``.
    """

    module_id: str
    model_specification_id: str
    generator_version: str
    antimony_view: str | None = None
    standalone_antimony: str | None = None
    boundary_interfaces: tuple[ModuleBoundaryInterface, ...] = ()
    assumptions: tuple[str, ...] = ()
    readiness: AntimonyArtifactReadiness = AntimonyArtifactReadiness.VIEW_ONLY
    unresolved_kinetic_law_ids: tuple[str, ...] = ()
    unresolved_reaction_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "module_id", _require_non_empty_str(self.module_id, field_name="module_id")
        )
        object.__setattr__(
            self,
            "model_specification_id",
            _require_non_empty_str(
                self.model_specification_id, field_name="model_specification_id"
            ),
        )
        object.__setattr__(
            self,
            "generator_version",
            _require_non_empty_str(self.generator_version, field_name="generator_version"),
        )
        object.__setattr__(
            self,
            "antimony_view",
            _clean_optional_str(self.antimony_view, field_name="antimony_view"),
        )
        object.__setattr__(
            self,
            "standalone_antimony",
            _clean_optional_str(self.standalone_antimony, field_name="standalone_antimony"),
        )
        object.__setattr__(
            self,
            "boundary_interfaces",
            _require_tuple_of(
                self.boundary_interfaces, ModuleBoundaryInterface, field_name="boundary_interfaces"
            ),
        )
        if self.standalone_antimony is not None and not self.boundary_interfaces:
            raise ValueError(
                "ModuleAntimonyArtifact.standalone_antimony requires at least one explicit "
                "ModuleBoundaryInterface -- no boundary condition may be invented implicitly"
            )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        if not isinstance(self.readiness, AntimonyArtifactReadiness):
            raise TypeError(
                "ModuleAntimonyArtifact.readiness must be an AntimonyArtifactReadiness, "
                f"got {self.readiness!r}"
            )
        object.__setattr__(
            self,
            "unresolved_kinetic_law_ids",
            _require_str_tuple(
                self.unresolved_kinetic_law_ids, field_name="unresolved_kinetic_law_ids"
            ),
        )
        _require_unique(
            self.unresolved_kinetic_law_ids,
            field_name="ModuleAntimonyArtifact.unresolved_kinetic_law_ids",
        )
        object.__setattr__(
            self,
            "unresolved_reaction_ids",
            _require_str_tuple(
                self.unresolved_reaction_ids, field_name="unresolved_reaction_ids"
            ),
        )
        _require_unique(
            self.unresolved_reaction_ids,
            field_name="ModuleAntimonyArtifact.unresolved_reaction_ids",
        )
        if self.readiness is AntimonyArtifactReadiness.VIEW_ONLY and (
            self.standalone_antimony is not None
            or self.unresolved_kinetic_law_ids
            or self.unresolved_reaction_ids
        ):
            raise ValueError(
                "ModuleAntimonyArtifact.readiness=VIEW_ONLY requires standalone_antimony=None "
                "and empty unresolved_kinetic_law_ids/unresolved_reaction_ids"
            )
        if self.readiness is AntimonyArtifactReadiness.EXECUTABLE and (
            self.standalone_antimony is None
            or self.unresolved_kinetic_law_ids
            or self.unresolved_reaction_ids
        ):
            raise ValueError(
                "ModuleAntimonyArtifact.readiness=EXECUTABLE requires a populated "
                "standalone_antimony and empty unresolved_kinetic_law_ids/unresolved_reaction_ids"
            )
        if self.readiness is AntimonyArtifactReadiness.NON_EXECUTABLE_UNRESOLVED_KINETICS and (
            self.standalone_antimony is not None
            or not self.unresolved_kinetic_law_ids
            or not self.unresolved_reaction_ids
        ):
            raise ValueError(
                "ModuleAntimonyArtifact.readiness=NON_EXECUTABLE_UNRESOLVED_KINETICS requires "
                "standalone_antimony=None and non-empty "
                "unresolved_kinetic_law_ids/unresolved_reaction_ids"
            )


# =================================================================================================
# 9. Agent2OutputPackage -- the final output envelope
# =================================================================================================


@dataclass(frozen=True, slots=True)
class Agent2OutputPackage:
    """The complete output of one Agent 2 build.

    ``boundary_assessments``/``module_decomposition`` are convenience
    top-level copies and must be identical to
    ``model_specification.boundary_assessments``/``.module_decomposition``
    -- never independently diverging data. ``full_antimony`` must name
    this same ``model_specification``, and every ``module_artifacts`` entry
    must reference a module that actually exists in
    ``model_specification.module_specifications`` (not every module needs
    an artifact yet).
    """

    contract_version: str
    model_specification: ModelSpecification
    full_antimony: FullAntimonyArtifact
    module_artifacts: tuple[ModuleAntimonyArtifact, ...] = ()
    boundary_assessments: tuple[BoundaryAssessment, ...] = ()
    module_decomposition: ModuleDecomposition | None = None
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contract_version",
            _require_non_empty_str(self.contract_version, field_name="contract_version"),
        )
        if not isinstance(self.model_specification, ModelSpecification):
            raise TypeError(
                "Agent2OutputPackage.model_specification must be a ModelSpecification, "
                f"got {self.model_specification!r}"
            )
        if not isinstance(self.full_antimony, FullAntimonyArtifact):
            raise TypeError(
                "Agent2OutputPackage.full_antimony must be a FullAntimonyArtifact, "
                f"got {self.full_antimony!r}"
            )
        object.__setattr__(
            self,
            "module_artifacts",
            _require_tuple_of(
                self.module_artifacts, ModuleAntimonyArtifact, field_name="module_artifacts"
            ),
        )
        _require_unique(
            tuple(artifact.module_id for artifact in self.module_artifacts),
            field_name="Agent2OutputPackage.module_artifacts[].module_id",
        )
        object.__setattr__(
            self,
            "boundary_assessments",
            _require_tuple_of(
                self.boundary_assessments, BoundaryAssessment, field_name="boundary_assessments"
            ),
        )
        if self.module_decomposition is not None and not isinstance(
            self.module_decomposition, ModuleDecomposition
        ):
            raise TypeError(
                "Agent2OutputPackage.module_decomposition must be a ModuleDecomposition or None, "
                f"got {self.module_decomposition!r}"
            )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )

        if self.full_antimony.model_specification_id != self.model_specification.model_id:
            raise ValueError(
                "Agent2OutputPackage.full_antimony.model_specification_id "
                f"({self.full_antimony.model_specification_id!r}) must equal "
                f"model_specification.model_id ({self.model_specification.model_id!r})"
            )

        module_ids = {module.module_id for module in self.model_specification.module_specifications}
        for artifact in self.module_artifacts:
            if artifact.module_id not in module_ids:
                raise ValueError(
                    f"Agent2OutputPackage module artifact {artifact.module_id!r} does not "
                    "reference a module in model_specification.module_specifications"
                )
            if artifact.model_specification_id != self.model_specification.model_id:
                raise ValueError(
                    f"Agent2OutputPackage module artifact {artifact.module_id!r}'s "
                    "model_specification_id does not match model_specification.model_id"
                )

        if self.boundary_assessments != self.model_specification.boundary_assessments:
            raise ValueError(
                "Agent2OutputPackage.boundary_assessments must be identical to "
                "model_specification.boundary_assessments"
            )
        if self.module_decomposition != self.model_specification.module_decomposition:
            raise ValueError(
                "Agent2OutputPackage.module_decomposition must be identical to "
                "model_specification.module_decomposition"
            )


__all__ = [
    "Agent1CuratedKnowledgeViewContract",
    "Agent2OutputPackage",
    "AntimonyArtifactReadiness",
    "BoundaryAssessment",
    "BoundaryLikelihood",
    "BoundaryParameterBasis",
    "CompartmentSourceScope",
    "CompartmentSpecification",
    "CuratedAllostericInteraction",
    "CuratedClaim",
    "CuratedCompartment",
    "CuratedCompound",
    "CuratedConfidenceSummary",
    "CuratedEnzymeModification",
    "CuratedEnzymeState",
    "CuratedEnzymeStateTransition",
    "CuratedEvidence",
    "CuratedKineticMeasurement",
    "CuratedReaction",
    "CuratedReactionEnzymeAssociation",
    "CuratedReactionParticipant",
    "CuratedRegulatoryInteraction",
    "FullAntimonyArtifact",
    "FullNetwork",
    "KineticLawSpecification",
    "KineticLawType",
    "ModelAssumption",
    "ModelSpecification",
    "ModuleAntimonyArtifact",
    "ModuleBoundaryInterface",
    "ModuleDecomposition",
    "ModuleInterfaceRole",
    "ModuleSpecification",
    "ParameterSource",
    "ParameterSpecification",
    "ParticipantRole",
    "ReactionEnzymeAssociation",
    "ReactionParticipantSpecification",
    "ReactionSpecification",
    "SpeciesSpecification",
]
