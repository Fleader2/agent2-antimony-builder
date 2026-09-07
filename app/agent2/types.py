"""Agent 2 core domain contracts (Increment 1: architecture and contracts only).

Every type in this module is an immutable, self-validating data contract.
None of them is produced by any real algorithm yet -- there is no network
assembly, no kinetic-law assignment, no boundary heuristic, and no
Antimony generation in this repository yet (see
``docs/03_increment_1_specification.md``). Validation here is limited to
structural checks (types, non-empty required fields) -- it never encodes a
scientific or heuristic judgment.

Three groups of types, in the order data flows through the (future)
pipeline:

1. ``Agent1CuratedKnowledgeViewContract`` and its nested ``Curated*``
   records -- Agent 2's own local, decoupled representation of the Agent 1
   handoff (``docs/02_agent1_handoff_contract.md``). This module never
   imports Agent 1's runtime package.
2. ``BoundaryLikelihood``, ``ParameterSource``, ``BoundaryAssessment``,
   ``ModuleBoundaryInterface``, ``ModuleSpecification``,
   ``ModuleDecomposition`` -- the module-decomposition domain.
3. ``ModelSpecification`` -- the top-level, authoritative contract that
   references everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


def _require_non_empty_str(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


# --- Agent 1 handoff: local, decoupled representation -------------------------------------------


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
class Agent1CuratedKnowledgeViewContract:
    """Agent 2's local, decoupled representation of the Agent 1 handoff.

    Never depends on Agent 1's Python classes -- see
    ``docs/02_agent1_handoff_contract.md`` for the full field-by-field
    contract, including what Agent 2 may and must not assume about each
    field.
    """

    contract_version: str
    organism_id: str | None = None
    compartments: tuple[CuratedCompartment, ...] = ()
    compounds: tuple[CuratedCompound, ...] = ()
    reactions: tuple[CuratedReaction, ...] = ()
    reaction_participants: tuple[CuratedReactionParticipant, ...] = ()
    reaction_enzyme_associations: tuple[CuratedReactionEnzymeAssociation, ...] = ()
    regulatory_interactions: tuple[CuratedRegulatoryInteraction, ...] = ()
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


# --- Module decomposition domain -----------------------------------------------------------------


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


class ParameterSource(StrEnum):
    """Where a parameter's value came from -- provenance/status, not confidence.

    ``CALIBRATED`` is reserved for a value returned by Agent 4's feedback
    (``docs/01_agent2_architecture.md`` §21); Agent 2 never assigns it to a
    value it produced itself.
    """

    CURATED = "CURATED"
    LITERATURE_DERIVED = "LITERATURE_DERIVED"
    DEFAULT = "DEFAULT"
    PLACEHOLDER = "PLACEHOLDER"
    CALIBRATED = "CALIBRATED"


@dataclass(frozen=True, slots=True)
class BoundaryAssessment:
    """One candidate module boundary's qualitative assessment.

    No heuristic computation exists yet -- this is the contract a future
    boundary-heuristic rule set will populate. ``parameter_basis`` is an
    optional free-text pointer to the parameter-data basis for the
    judgment, when one exists.
    """

    boundary_id: str
    upstream_element_id: str
    downstream_element_id: str
    likelihood: BoundaryLikelihood
    explanation: str
    shared_species_ids: tuple[str, ...] = ()
    connecting_reaction_ids: tuple[str, ...] = ()
    supporting_reason_codes: tuple[str, ...] = ()
    opposing_reason_codes: tuple[str, ...] = ()
    parameter_basis: str | None = None

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
        for name in (
            "shared_species_ids",
            "connecting_reaction_ids",
            "supporting_reason_codes",
            "opposing_reason_codes",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))


@dataclass(frozen=True, slots=True)
class ModuleBoundaryInterface:
    """One explicit interface element required for a standalone module model.

    Structural only -- no simulation semantics. Agent 2 never invents a
    boundary condition silently; if this cannot be stated explicitly for a
    module, no standalone model is produced for it
    (``docs/01_agent2_architecture.md`` §14).
    """

    species_id: str
    role: str
    direction: str
    assumption: str
    externally_controlled: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        object.__setattr__(self, "role", _require_non_empty_str(self.role, field_name="role"))
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


@dataclass(frozen=True, slots=True)
class ModuleSpecification:
    """One module: a named subset of the full network plus its boundary interfaces.

    Always traceable to the full model via ``source_boundary_ids`` -- a
    module is never defined independently of the ``BoundaryAssessment``\\ s
    that justified it.
    """

    module_id: str
    name: str
    species_ids: tuple[str, ...] = ()
    reaction_ids: tuple[str, ...] = ()
    parameter_ids: tuple[str, ...] = ()
    boundary_interfaces: tuple[ModuleBoundaryInterface, ...] = ()
    assumptions: tuple[str, ...] = ()
    source_boundary_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "module_id", _require_non_empty_str(self.module_id, field_name="module_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        for name in (
            "species_ids",
            "reaction_ids",
            "parameter_ids",
            "assumptions",
            "source_boundary_ids",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        if not isinstance(self.boundary_interfaces, tuple) or any(
            not isinstance(item, ModuleBoundaryInterface) for item in self.boundary_interfaces
        ):
            raise TypeError(
                "ModuleSpecification.boundary_interfaces must be a tuple of "
                f"ModuleBoundaryInterface, got {self.boundary_interfaces!r}"
            )


@dataclass(frozen=True, slots=True)
class ModuleDecomposition:
    """The full network's partition into modules, as of one boundary-policy version.

    ``policy_version`` prevents a decomposition produced under one
    heuristic rule set from being silently reinterpreted under a later,
    different one.
    """

    decomposition_id: str
    name: str
    policy_version: str
    module_ids: tuple[str, ...] = ()
    boundary_assessment_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

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
        for name in ("module_ids", "boundary_assessment_ids", "assumptions"):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))


# --- Top-level model contract ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModelSpecification:
    """The top-level, authoritative contract Agent 2 produces.

    References the full network's own elements plus every
    ``BoundaryAssessment``/``ModuleDecomposition``/``ModuleSpecification``
    derived from it. Both the full Antimony model and every module
    Antimony output are generated from this one object -- no generation
    logic exists yet (``docs/03_increment_1_specification.md``).
    """

    model_id: str
    name: str
    full_network_id: str
    organism_id: str | None = None
    compartment_ids: tuple[str, ...] = ()
    species_ids: tuple[str, ...] = ()
    reaction_ids: tuple[str, ...] = ()
    kinetic_law_ids: tuple[str, ...] = ()
    parameter_ids: tuple[str, ...] = ()
    boundary_assessments: tuple[BoundaryAssessment, ...] = ()
    module_decomposition: ModuleDecomposition | None = None
    module_specifications: tuple[ModuleSpecification, ...] = ()
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_id", _require_non_empty_str(self.model_id, field_name="model_id")
        )
        object.__setattr__(self, "name", _require_non_empty_str(self.name, field_name="name"))
        object.__setattr__(
            self,
            "full_network_id",
            _require_non_empty_str(self.full_network_id, field_name="full_network_id"),
        )
        for name in (
            "compartment_ids",
            "species_ids",
            "reaction_ids",
            "kinetic_law_ids",
            "parameter_ids",
            "assumptions",
            "provenance_refs",
        ):
            object.__setattr__(self, name, _require_str_tuple(getattr(self, name), field_name=name))
        if not isinstance(self.boundary_assessments, tuple) or any(
            not isinstance(item, BoundaryAssessment) for item in self.boundary_assessments
        ):
            raise TypeError(
                "ModelSpecification.boundary_assessments must be a tuple of BoundaryAssessment, "
                f"got {self.boundary_assessments!r}"
            )
        if self.module_decomposition is not None and not isinstance(
            self.module_decomposition, ModuleDecomposition
        ):
            raise TypeError(
                "ModelSpecification.module_decomposition must be a ModuleDecomposition or None, "
                f"got {self.module_decomposition!r}"
            )
        if not isinstance(self.module_specifications, tuple) or any(
            not isinstance(item, ModuleSpecification) for item in self.module_specifications
        ):
            raise TypeError(
                "ModelSpecification.module_specifications must be a tuple of ModuleSpecification, "
                f"got {self.module_specifications!r}"
            )


__all__ = [
    "Agent1CuratedKnowledgeViewContract",
    "BoundaryAssessment",
    "BoundaryLikelihood",
    "CuratedClaim",
    "CuratedCompartment",
    "CuratedCompound",
    "CuratedConfidenceSummary",
    "CuratedEvidence",
    "CuratedReaction",
    "CuratedReactionEnzymeAssociation",
    "CuratedReactionParticipant",
    "CuratedRegulatoryInteraction",
    "ModelSpecification",
    "ModuleBoundaryInterface",
    "ModuleDecomposition",
    "ModuleSpecification",
    "ParameterSource",
]
