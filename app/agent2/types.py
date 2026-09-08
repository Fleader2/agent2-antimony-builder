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
   ``BoundaryParameterBasis``, ``KineticLawType``, ``ParticipantRole``,
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
   ``ModuleAntimonyArtifact``. Contracts only: no generator function, no
   syntax validation, no Antimony dependency exists in this increment.
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
    """One reaction-enzyme association. Exactly one of ``protein_id``/``complex_id`` is expected."""

    reaction_id: str
    protein_id: str | None = None
    complex_id: str | None = None
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
    auto-converted into a ``ParameterSpecification``.** Agent 2 must make
    that mapping decision explicitly in a future increment; until it does,
    every ``ParameterSpecification`` Agent 2 declares still uses
    ``ParameterSource.DEFAULT``/``PLACEHOLDER`` (never fabricate a
    ``CURATED`` value merely because a ``CuratedKineticMeasurement`` with a
    matching reaction/parameter type exists -- that mapping decision itself
    is Agent 2 behavior this increment does not implement).

    ``value``/``unit`` are the as-reported figures; ``normalized_value``/
    ``normalized_unit`` are ``None`` for every measurement in this handoff
    version -- Agent 1 has no unit-conversion framework yet. No field here
    is ever averaged, converted, or reinterpreted from what Agent 1
    reported.
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
    value it produced itself. Also reused by ``KineticLawSpecification
    .assignment_source`` (a kinetic law's *type* has the identical
    provenance-vs-status axis as a parameter's *value*) and by
    ``SpeciesSpecification.initialization_source``, rather than inventing
    a near-duplicate vocabulary for either.
    """

    CURATED = "CURATED"
    LITERATURE_DERIVED = "LITERATURE_DERIVED"
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
    ``protein_id``/``complex_id``/``relationship`` are copied verbatim.
    """

    association_id: str
    reaction_id: str
    protein_id: str | None = None
    complex_id: str | None = None
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
    """

    network_id: str
    name: str
    compartments: tuple[CompartmentSpecification, ...] = ()
    species: tuple[SpeciesSpecification, ...] = ()
    reactions: tuple[ReactionSpecification, ...] = ()
    enzyme_associations: tuple[ReactionEnzymeAssociation, ...] = ()
    regulatory_interactions: tuple[CuratedRegulatoryInteraction, ...] = ()
    kinetic_measurements: tuple[CuratedKineticMeasurement, ...] = ()
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
    """
    compartment_ids = {c.compartment_id for c in network.compartments}
    species_ids = {s.species_id for s in network.species}
    reaction_ids = {r.reaction_id for r in network.reactions}
    enzyme_association_ids = {e.association_id for e in network.enzyme_associations}
    regulatory_interaction_ids = {r.id for r in network.regulatory_interactions}
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
    serialization -- no expression parsing or generation occurs here
    beyond a non-blank check when a law is actually assigned. ``UNASSIGNED``
    may omit ``expression`` entirely. Reference integrity for
    ``parameter_ids``/``species_ids`` against a real parameter/species set
    is enforced later, at ``ModelSpecification`` construction -- this type
    alone has no such set to check against.
    """

    kinetic_law_id: str
    reaction_id: str
    law_type: KineticLawType
    assignment_source: ParameterSource
    expression: str | None = None
    parameter_ids: tuple[str, ...] = ()
    species_ids: tuple[str, ...] = ()
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
        if not isinstance(self.assignment_source, ParameterSource):
            raise TypeError(
                "KineticLawSpecification.assignment_source must be a ParameterSource, "
                f"got {self.assignment_source!r}"
            )
        object.__setattr__(
            self, "expression", _clean_optional_str(self.expression, field_name="expression")
        )
        if self.law_type is not KineticLawType.UNASSIGNED and self.expression is None:
            raise ValueError(
                f"KineticLawSpecification with law_type={self.law_type.value} requires a "
                "non-blank expression"
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
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


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
    """

    parameter_id: str
    name: str
    source: ParameterSource
    value: Decimal | None = None
    unit: str | None = None
    source_reference: str | None = None
    reaction_id: str | None = None
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
    """

    module_id: str
    name: str
    reaction_ids: tuple[str, ...] = ()
    species_ids: tuple[str, ...] = ()
    parameter_ids: tuple[str, ...] = ()
    kinetic_law_ids: tuple[str, ...] = ()
    boundary_interfaces: tuple[ModuleBoundaryInterface, ...] = ()
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
            "assumptions",
            "source_boundary_ids",
            "provenance_refs",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        for name in ("reaction_ids", "species_ids", "parameter_ids", "kinetic_law_ids"):
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
class ModuleDecomposition:
    """The full network's partition into modules, as of one boundary-policy version.

    References modules/boundaries by id -- never duplicates them.
    ``policy_version`` prevents a decomposition produced under one
    heuristic rule set from being silently reinterpreted under a later,
    different one. No partitioning algorithm exists in this increment.
    """

    decomposition_id: str
    name: str
    policy_version: str
    created_from_network_id: str
    module_ids: tuple[str, ...] = ()
    boundary_assessment_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    parameter_basis_summary: BoundaryParameterBasis | None = None

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
        for name in ("module_ids", "boundary_assessment_ids", "assumptions"):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        _require_unique(self.module_ids, field_name="ModuleDecomposition.module_ids")
        _require_unique(
            self.boundary_assessment_ids, field_name="ModuleDecomposition.boundary_assessment_ids"
        )
        if self.parameter_basis_summary is not None and not isinstance(
            self.parameter_basis_summary, BoundaryParameterBasis
        ):
            raise TypeError(
                "ModuleDecomposition.parameter_basis_summary must be a BoundaryParameterBasis or "
                f"None, got {self.parameter_basis_summary!r}"
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
    """
    reaction_ids = {reaction.reaction_id for reaction in spec.full_network.reactions}
    species_ids = {species.species_id for species in spec.full_network.species}
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
        if decomposition.created_from_network_id != spec.full_network.network_id:
            raise ValueError(
                "module_decomposition.created_from_network_id "
                f"({decomposition.created_from_network_id!r}) must equal "
                f"full_network.network_id ({spec.full_network.network_id!r})"
            )


# =================================================================================================
# 8. Antimony artifact contracts (contracts only -- no generation logic)
# =================================================================================================


@dataclass(frozen=True, slots=True)
class FullAntimonyArtifact:
    """The full, canonical Antimony model text -- a contract only in Increment 1.

    Construction is allowed (for tests and future contract wiring); no
    generator function, no syntax validation, and no Antimony runtime
    dependency exists anywhere in this repository.
    """

    model_id: str
    model_specification_id: str
    antimony_text: str
    generator_version: str
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

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


@dataclass(frozen=True, slots=True)
class ModuleAntimonyArtifact:
    """One module's Antimony output(s) -- a contract only in Increment 1.

    ``antimony_view`` (a subset view, not necessarily simulatable) may
    exist without ``standalone_antimony``. ``standalone_antimony`` may be
    present only when ``boundary_interfaces`` is non-empty -- the same
    structural predicate as ``ModuleSpecification
    .has_explicit_boundary_interfaces``. No boundary condition is ever
    invented to satisfy this rule; a module lacking explicit interfaces
    simply has no standalone artifact.
    """

    module_id: str
    model_specification_id: str
    generator_version: str
    antimony_view: str | None = None
    standalone_antimony: str | None = None
    boundary_interfaces: tuple[ModuleBoundaryInterface, ...] = ()
    assumptions: tuple[str, ...] = ()

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
    "BoundaryAssessment",
    "BoundaryLikelihood",
    "BoundaryParameterBasis",
    "CompartmentSourceScope",
    "CompartmentSpecification",
    "CuratedClaim",
    "CuratedCompartment",
    "CuratedCompound",
    "CuratedConfidenceSummary",
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
