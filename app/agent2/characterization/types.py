"""Reaction and Enzyme-State Characterization domain contracts (Increment 3).

Describes *what kind of biochemical/modeling situation* each reaction and
catalytic enzyme state represents -- never *which* mathematical rate law
applies. See ``docs/06_reaction_enzyme_state_characterization.md`` for the
full contract.

Every type here is a frozen dataclass, structurally validated only (types,
non-empty required fields, no cross-``FullNetwork`` reference checks --
``FullNetwork`` itself already guarantees internal consistency before
characterization ever runs, per
``app.agent2.characterization.characterization``'s own docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


def _require_non_empty_str(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


class ReactionClass(StrEnum):
    """A deliberately small, qualitative *structural* category -- never a mathematical choice.

    Assigned only when deterministically identifiable from explicit
    curated structure (Increment 3 instructions, Step 9) -- ``UNKNOWN`` is
    the default, never an inferred guess. A reaction may belong to more
    than one class at once (``ReactionCharacterization.reaction_classes``
    is a tuple, never a single field forcing an arbitrary precedence --
    Step 22).
    """

    ENZYMATIC = "ENZYMATIC"
    TRANSPORT = "TRANSPORT"
    EXCHANGE = "EXCHANGE"
    SPONTANEOUS = "SPONTANEOUS"
    STATE_TRANSITION = "STATE_TRANSITION"
    UNKNOWN = "UNKNOWN"


class CharacterizationFlag(StrEnum):
    """A controlled vocabulary of facts relevant to later kinetic-law assignment.

    Deliberately excludes anything that implies a mathematical decision
    (no ``USE_MICHAELIS_MENTEN``, ``USE_HILL``, ``USE_MASS_ACTION``,
    ``FAST``, ``SLOW``, ... -- Increment 3 instructions, Step 10). A flag
    only ever states a structural fact this package can determine
    deterministically from ``FullNetwork``.
    """

    HAS_CATALYST = "HAS_CATALYST"
    MULTIPLE_CATALYSTS = "MULTIPLE_CATALYSTS"
    STATE_SPECIFIC_CATALYSIS = "STATE_SPECIFIC_CATALYSIS"
    HAS_REGULATION = "HAS_REGULATION"
    HAS_ALLOSTERY = "HAS_ALLOSTERY"
    HAS_MODIFIED_ENZYME_STATE = "HAS_MODIFIED_ENZYME_STATE"
    HAS_STATE_TRANSITION = "HAS_STATE_TRANSITION"
    HAS_KINETIC_MEASUREMENTS = "HAS_KINETIC_MEASUREMENTS"
    HAS_STATE_SPECIFIC_KINETICS = "HAS_STATE_SPECIFIC_KINETICS"
    HAS_REPORTED_RATE_LAW = "HAS_REPORTED_RATE_LAW"
    REVERSIBILITY_KNOWN = "REVERSIBILITY_KNOWN"
    REVERSIBILITY_UNKNOWN = "REVERSIBILITY_UNKNOWN"
    MULTIPLE_COMPARTMENTS = "MULTIPLE_COMPARTMENTS"
    PARTICIPANT_MODIFIERS_PRESENT = "PARTICIPANT_MODIFIERS_PRESENT"


class UnresolvedFeature(StrEnum):
    """A controlled vocabulary of facts a later stage may need but that curated input lacks.

    Every member means **"not represented in curated input,"** never
    **"does not exist biologically"** (Increment 3 instructions, Step 11,
    Step 23) -- this distinction is load-bearing: Agent 1's regulation
    pipeline is known-incomplete, so the absence of a
    ``RegulatoryInteraction`` never means an enzyme is unregulated, only
    that no curated regulatory fact for it exists yet.
    """

    NO_CATALYST_INFORMATION = "NO_CATALYST_INFORMATION"
    CATALYST_STATE_UNSPECIFIED = "CATALYST_STATE_UNSPECIFIED"
    NO_KINETIC_MEASUREMENTS = "NO_KINETIC_MEASUREMENTS"
    NO_STATE_SPECIFIC_KINETICS = "NO_STATE_SPECIFIC_KINETICS"
    NO_REPORTED_RATE_LAW = "NO_REPORTED_RATE_LAW"
    REVERSIBILITY_UNKNOWN = "REVERSIBILITY_UNKNOWN"
    REGULATION_CONTEXT_INCOMPLETE = "REGULATION_CONTEXT_INCOMPLETE"
    ENZYME_STATE_CONTEXT_INCOMPLETE = "ENZYME_STATE_CONTEXT_INCOMPLETE"
    PARTICIPANT_CONTEXT_INCOMPLETE = "PARTICIPANT_CONTEXT_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ReactionCharacterization:
    """The complete modeling-facing characterization of one reaction.

    Describes number of substrates/products, catalyst form, state
    specificity, allostery, regulation, reversibility, and curated-data
    availability -- **never** a kinetic law, a parameter, a boundary
    likelihood, a module id, or Antimony text (Increment 3 instructions,
    Step 8, Step 27-29; enforced structurally, see
    ``tests/agent2/test_characterization_scope.py``).

    Every "set-like" id tuple (``catalyst_association_ids``,
    ``catalytic_protein_ids``, ``catalytic_complex_ids``,
    ``catalytic_enzyme_state_ids``, ``regulation_ids``,
    ``allosteric_interaction_ids``, ``enzyme_state_ids``,
    ``enzyme_state_transition_ids``, ``kinetic_measurement_ids``,
    ``state_specific_kinetic_measurement_ids``,
    ``reported_rate_law_measurement_ids``) is sorted -- biological
    identity here has no ordering, so sorting guarantees two
    equal-by-value ``FullNetwork``\\ s characterize identically regardless
    of the order their own tuples happen to store things in (Increment 3
    instructions, Step 30, Step 41). ``participant_species_ids``/
    ``reactant_species_ids``/``product_species_ids``/
    ``modifier_species_ids`` instead **preserve** the reaction's own
    curated participant order -- that ordering came from Agent 1's own
    stoichiometric listing and is semantically meaningful, so it is never
    resorted.
    """

    reaction_id: str
    reaction_name: str

    participant_species_ids: tuple[str, ...]
    reactant_species_ids: tuple[str, ...]
    product_species_ids: tuple[str, ...]
    modifier_species_ids: tuple[str, ...]

    reversible: bool | None

    reaction_classes: tuple[ReactionClass, ...]

    catalyst_association_ids: tuple[str, ...]
    catalytic_protein_ids: tuple[str, ...]
    catalytic_complex_ids: tuple[str, ...]
    catalytic_enzyme_state_ids: tuple[str, ...]

    regulation_ids: tuple[str, ...]

    allosteric_interaction_ids: tuple[str, ...]
    enzyme_state_ids: tuple[str, ...]
    enzyme_state_transition_ids: tuple[str, ...]

    kinetic_measurement_ids: tuple[str, ...]
    state_specific_kinetic_measurement_ids: tuple[str, ...]
    reported_rate_law_measurement_ids: tuple[str, ...]

    characterization_flags: tuple[CharacterizationFlag, ...]
    unresolved_features: tuple[UnresolvedFeature, ...]

    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        object.__setattr__(
            self,
            "reaction_name",
            _require_non_empty_str(self.reaction_name, field_name="reaction_name"),
        )
        for field_name in (
            "participant_species_ids",
            "reactant_species_ids",
            "product_species_ids",
            "modifier_species_ids",
            "catalyst_association_ids",
            "catalytic_protein_ids",
            "catalytic_complex_ids",
            "catalytic_enzyme_state_ids",
            "regulation_ids",
            "allosteric_interaction_ids",
            "enzyme_state_ids",
            "enzyme_state_transition_ids",
            "kinetic_measurement_ids",
            "state_specific_kinetic_measurement_ids",
            "reported_rate_law_measurement_ids",
            "provenance_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_str_tuple(getattr(self, field_name), field_name=field_name),
            )
        if self.reversible is not None and not isinstance(self.reversible, bool):
            raise TypeError(
                f"ReactionCharacterization.reversible must be a bool or None, "
                f"got {self.reversible!r}"
            )
        if not isinstance(self.reaction_classes, tuple) or any(
            not isinstance(c, ReactionClass) for c in self.reaction_classes
        ):
            raise TypeError(
                "ReactionCharacterization.reaction_classes must be a tuple of ReactionClass, "
                f"got {self.reaction_classes!r}"
            )
        if not isinstance(self.characterization_flags, tuple) or any(
            not isinstance(f, CharacterizationFlag) for f in self.characterization_flags
        ):
            raise TypeError(
                "ReactionCharacterization.characterization_flags must be a tuple of "
                f"CharacterizationFlag, got {self.characterization_flags!r}"
            )
        if not isinstance(self.unresolved_features, tuple) or any(
            not isinstance(f, UnresolvedFeature) for f in self.unresolved_features
        ):
            raise TypeError(
                "ReactionCharacterization.unresolved_features must be a tuple of "
                f"UnresolvedFeature, got {self.unresolved_features!r}"
            )


@dataclass(frozen=True, slots=True)
class EnzymeStateCharacterization:
    """The complete modeling-facing characterization of one catalytic ``EnzymeState``.

    Exists to avoid duplicating a state's own detail across every
    reaction it catalyzes (Increment 3 instructions, Step 25) --
    ``ReactionCharacterization.catalytic_enzyme_state_ids`` references
    these by id rather than embedding them. Never turns the state into a
    ``SpeciesSpecification`` -- that modeling transformation is a future
    increment's job (Step 13).
    """

    enzyme_state_id: str
    parent_protein_id: str | None
    parent_complex_id: str | None
    state_type: str
    compartment_id: str | None

    modification_ids: tuple[str, ...]
    allosteric_interaction_ids: tuple[str, ...]
    transition_ids: tuple[str, ...]
    catalytic_reaction_ids: tuple[str, ...]
    kinetic_measurement_ids: tuple[str, ...]

    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enzyme_state_id",
            _require_non_empty_str(self.enzyme_state_id, field_name="enzyme_state_id"),
        )
        object.__setattr__(
            self, "state_type", _require_non_empty_str(self.state_type, field_name="state_type")
        )
        for field_name in (
            "modification_ids",
            "allosteric_interaction_ids",
            "transition_ids",
            "catalytic_reaction_ids",
            "kinetic_measurement_ids",
            "provenance_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_str_tuple(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True, slots=True)
class NetworkCharacterization:
    """The complete characterization of one ``FullNetwork``.

    No modules, no kinetic laws, no parameters, no Antimony (Increment 3
    instructions, Step 24) -- ``reaction_characterizations``/
    ``enzyme_state_characterizations`` are both sorted by their own id for
    determinism, mirroring ``ReactionCharacterization``'s own id-tuple
    sorting policy.
    """

    network_id: str
    reaction_characterizations: tuple[ReactionCharacterization, ...]
    enzyme_state_characterizations: tuple[EnzymeStateCharacterization, ...]
    characterization_policy_version: str
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        object.__setattr__(
            self,
            "characterization_policy_version",
            _require_non_empty_str(
                self.characterization_policy_version, field_name="characterization_policy_version"
            ),
        )
        if not isinstance(self.reaction_characterizations, tuple) or any(
            not isinstance(r, ReactionCharacterization) for r in self.reaction_characterizations
        ):
            raise TypeError(
                "NetworkCharacterization.reaction_characterizations must be a tuple of "
                f"ReactionCharacterization, got {self.reaction_characterizations!r}"
            )
        if not isinstance(self.enzyme_state_characterizations, tuple) or any(
            not isinstance(s, EnzymeStateCharacterization)
            for s in self.enzyme_state_characterizations
        ):
            raise TypeError(
                "NetworkCharacterization.enzyme_state_characterizations must be a tuple of "
                f"EnzymeStateCharacterization, got {self.enzyme_state_characterizations!r}"
            )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        reaction_ids = tuple(r.reaction_id for r in self.reaction_characterizations)
        if len(reaction_ids) != len(set(reaction_ids)):
            raise ValueError(
                "NetworkCharacterization.reaction_characterizations contains a duplicate "
                "reaction_id"
            )
        enzyme_state_ids = tuple(s.enzyme_state_id for s in self.enzyme_state_characterizations)
        if len(enzyme_state_ids) != len(set(enzyme_state_ids)):
            raise ValueError(
                "NetworkCharacterization.enzyme_state_characterizations contains a duplicate "
                "enzyme_state_id"
            )


__all__ = [
    "CharacterizationFlag",
    "EnzymeStateCharacterization",
    "NetworkCharacterization",
    "ReactionCharacterization",
    "ReactionClass",
    "UnresolvedFeature",
]
