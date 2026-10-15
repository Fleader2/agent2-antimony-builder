"""Candidate Modularization Search domain model.

Search operates entirely on ``ModelModularization``/``ModelModule``/``ModuleMembership``/
``ModulePort`` bundles -- never on the canonical ``ModelSpecification`` itself, which is read
only (``full_network``/``kinetic_laws``/``parameters``, for topology/adjacency information) and
never mutated anywhere in this package. Every candidate this package produces is a
self-contained ``CandidateModularizationBundle`` a caller attaches to a model (via
``dataclasses.replace``, exactly like ``app.agent2.module_evaluation``'s own established
"ephemeral evaluation view" convention) only for the duration of one evaluation call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agent2.module_evaluation.types import ModularizationEvaluation
from app.agent2.types import ModelModularization, ModelModule, ModuleMembership, ModulePort
from app.agent2.weight_space_exploration.types import WeightSpaceExplorationResult

# --- Local validation helpers (mirrors app.agent2.module_evaluation.types /
# app.agent2.weight_space_exploration.types / app.agent2.module_calibration.types) -----------------


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


def _require_tuple_of(value: object, item_type: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}, got {value!r}")
    return value


def _require_frozenset_of_str(value: object, *, field_name: str) -> frozenset[str]:
    if not isinstance(value, frozenset) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a frozenset of str, got {value!r}")
    return value


class ProposalOperation(StrEnum):
    """One deterministic proposal operator (task instructions §2), plus ``SEED`` for the
    search's own starting point (never itself "proposed" -- it has no parent)."""

    #: The search's own starting point -- the caller-supplied modularization, unchanged.
    SEED = "SEED"
    #: Relocate one reaction (alone) from its current module to a different, already-existing
    #: module of the same candidate.
    MOVE_REACTION = "MOVE_REACTION"
    #: Explicitly declare a ``ModulePort`` pair for one species already topologically shared
    #: between two modules, where no such declared pair yet exists.
    ADD_BOUNDARY = "ADD_BOUNDARY"
    #: Remove an already-declared ``ModulePort`` pair for one species between two modules.
    REMOVE_BOUNDARY = "REMOVE_BOUNDARY"
    #: Combine two adjacent modules (sharing a real network-topology edge) into one.
    MERGE_MODULES = "MERGE_MODULES"
    #: Partition one module's own reactions into two, using its own internal topology.
    SPLIT_MODULE = "SPLIT_MODULE"
    #: Jump directly toward one end of the allowed module-count range via repeated,
    #: deterministic merge/split -- a "fast lane" alongside the strictly-local ±1 steps
    #: MERGE_MODULES/SPLIT_MODULE already provide.
    VARY_MODULE_COUNT = "VARY_MODULE_COUNT"


class BoundaryFixedState(StrEnum):
    """One species' own pinned boundary-declaration state (task instructions §3, "fixed
    boundaries") -- constrains ``ADD_BOUNDARY``/``REMOVE_BOUNDARY`` alone, never membership."""

    #: This species' own cross-module port pair must always stay declared -- REMOVE_BOUNDARY
    #: may never remove it.
    MUST_BE_DECLARED = "MUST_BE_DECLARED"
    #: This species must never gain a declared cross-module port pair -- ADD_BOUNDARY may
    #: never create one for it.
    MUST_NOT_BE_DECLARED = "MUST_NOT_BE_DECLARED"


@dataclass(frozen=True, slots=True)
class FixedBoundary:
    """One pinned boundary-declaration constraint for one species."""

    species_id: str
    state: BoundaryFixedState

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        if not isinstance(self.state, BoundaryFixedState):
            raise TypeError(
                f"FixedBoundary.state must be a BoundaryFixedState, got {self.state!r}"
            )


@dataclass(frozen=True, slots=True)
class SearchConstraints:
    """Every hard constraint candidate generation must never violate (task instructions §3).
    Generation-time, never post-hoc: an operator that cannot produce a constraint-respecting
    proposal for a given input simply produces none -- a violating candidate is never
    generated and then discarded, since discarding-after-the-fact would still have required
    constructing the very ``ModuleMembership``/``ModulePort`` rows a hard constraint forbids.

    All fields default to "no constraint" (an empty default never restricts anything) --
    omitting ``constraints`` entirely reproduces an unconstrained search exactly.
    """

    #: Groups of component ids that must always share one module -- "reactions/species that
    #: must remain together."
    must_stay_together: tuple[frozenset[str], ...] = ()
    #: Groups of component ids that must never all share one module (any two members of one
    #: group found in the same module is a violation).
    forbidden_together: tuple[frozenset[str], ...] = ()
    #: Component ids that must remain a member of *some* module for the whole search -- never
    #: become unassigned ("required module membership").
    required_module_component_ids: frozenset[str] = frozenset()
    #: Component ids that must never become a member of *any* module ("forbidden module
    #: membership") -- every operator skips them entirely.
    excluded_component_ids: frozenset[str] = frozenset()
    #: Pinned boundary-declaration states (task instructions §3, "fixed boundaries").
    fixed_boundaries: tuple[FixedBoundary, ...] = ()
    #: Minimum/maximum reaction-membership count per module (``None`` means unbounded).
    min_module_size: int | None = None
    max_module_size: int | None = None
    #: Minimum/maximum total module count across the whole candidate (``None`` means
    #: unbounded).
    min_module_count: int | None = None
    max_module_count: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "must_stay_together",
            tuple(
                _require_frozenset_of_str(g, field_name="must_stay_together[]")
                for g in self.must_stay_together
            ),
        )
        object.__setattr__(
            self,
            "forbidden_together",
            tuple(
                _require_frozenset_of_str(g, field_name="forbidden_together[]")
                for g in self.forbidden_together
            ),
        )
        object.__setattr__(
            self,
            "required_module_component_ids",
            _require_frozenset_of_str(
                self.required_module_component_ids, field_name="required_module_component_ids"
            ),
        )
        object.__setattr__(
            self,
            "excluded_component_ids",
            _require_frozenset_of_str(
                self.excluded_component_ids, field_name="excluded_component_ids"
            ),
        )
        object.__setattr__(
            self,
            "fixed_boundaries",
            _require_tuple_of(self.fixed_boundaries, FixedBoundary, field_name="fixed_boundaries"),
        )
        for field_name, value in (
            ("min_module_size", self.min_module_size),
            ("max_module_size", self.max_module_size),
            ("min_module_count", self.min_module_count),
            ("max_module_count", self.max_module_count),
        ):
            invalid = not isinstance(value, int) or isinstance(value, bool) or value < 1
            if value is not None and invalid:
                raise ValueError(
                    f"SearchConstraints.{field_name} must be a positive int or None, got "
                    f"{value!r}"
                )
        if (
            self.min_module_size is not None
            and self.max_module_size is not None
            and self.min_module_size > self.max_module_size
        ):
            raise ValueError(
                "SearchConstraints.min_module_size must be <= max_module_size, got "
                f"{self.min_module_size!r} > {self.max_module_size!r}"
            )
        if (
            self.min_module_count is not None
            and self.max_module_count is not None
            and self.min_module_count > self.max_module_count
        ):
            raise ValueError(
                "SearchConstraints.min_module_count must be <= max_module_count, got "
                f"{self.min_module_count!r} > {self.max_module_count!r}"
            )


@dataclass(frozen=True, slots=True)
class SearchPolicy:
    """The complete, explicit, deterministic bound on how much search this one call performs
    (task instructions §4) -- never unbounded combinatorial search."""

    max_iterations: int
    max_candidates_per_iteration: int
    beam_width: int
    allowed_operations: tuple[ProposalOperation, ...]
    policy_version: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_iterations", self.max_iterations),
            ("max_candidates_per_iteration", self.max_candidates_per_iteration),
            ("beam_width", self.beam_width),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"SearchPolicy.{field_name} must be a positive int, got {value!r}")
        object.__setattr__(
            self,
            "allowed_operations",
            _require_tuple_of(
                self.allowed_operations, ProposalOperation, field_name="allowed_operations"
            ),
        )
        if not self.allowed_operations:
            raise ValueError("SearchPolicy.allowed_operations must be non-empty")
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


@dataclass(frozen=True, slots=True)
class CandidateModularizationBundle:
    """One complete, self-contained candidate -- never attached to any ``ModelSpecification``
    by this package itself; a caller attaches it (``dataclasses.replace``) only for the
    duration of one evaluation call, exactly like ``app.agent2.module_evaluation``'s own
    existing convention for an ephemeral evaluation view."""

    modularization: ModelModularization
    modules: tuple[ModelModule, ...]
    memberships: tuple[ModuleMembership, ...]
    ports: tuple[ModulePort, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.modularization, ModelModularization):
            raise TypeError(
                "CandidateModularizationBundle.modularization must be a ModelModularization, "
                f"got {self.modularization!r}"
            )
        object.__setattr__(
            self, "modules", _require_tuple_of(self.modules, ModelModule, field_name="modules")
        )
        object.__setattr__(
            self,
            "memberships",
            _require_tuple_of(self.memberships, ModuleMembership, field_name="memberships"),
        )
        object.__setattr__(
            self, "ports", _require_tuple_of(self.ports, ModulePort, field_name="ports")
        )


@dataclass(frozen=True, slots=True)
class CandidateLineage:
    """Why one candidate exists (task instructions §6) -- recorded for *every* candidate the
    search ever generates, retained or not, so a rejection can still be explained in terms of
    its own real parent/operation."""

    candidate_id: str
    parent_candidate_id: str | None
    operation: ProposalOperation
    affected_component_ids: tuple[str, ...]
    affected_module_ids: tuple[str, ...]
    generation: int
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_non_empty_str(self.candidate_id, field_name="candidate_id"),
        )
        if self.parent_candidate_id is not None:
            object.__setattr__(
                self,
                "parent_candidate_id",
                _require_non_empty_str(
                    self.parent_candidate_id, field_name="parent_candidate_id"
                ),
            )
        if not isinstance(self.operation, ProposalOperation):
            raise TypeError(
                f"CandidateLineage.operation must be a ProposalOperation, got {self.operation!r}"
            )
        object.__setattr__(
            self,
            "affected_component_ids",
            _require_str_tuple(
                self.affected_component_ids, field_name="affected_component_ids"
            ),
        )
        object.__setattr__(
            self,
            "affected_module_ids",
            _require_str_tuple(self.affected_module_ids, field_name="affected_module_ids"),
        )
        invalid_generation = (
            not isinstance(self.generation, int)
            or isinstance(self.generation, bool)
            or self.generation < 0
        )
        if invalid_generation:
            raise ValueError(
                f"CandidateLineage.generation must be a non-negative int, got {self.generation!r}"
            )
        if self.operation is ProposalOperation.SEED and self.parent_candidate_id is not None:
            raise ValueError("CandidateLineage: SEED must have parent_candidate_id=None")
        if self.operation is not ProposalOperation.SEED and self.parent_candidate_id is None:
            raise ValueError(
                f"CandidateLineage: operation={self.operation.value!r} requires a real "
                "parent_candidate_id"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


@dataclass(frozen=True, slots=True)
class RejectedCandidate:
    """One candidate a proposal operator *could* have produced, or did produce, but which was
    never retained -- always paired with a human-readable reason, never silently dropped."""

    candidate_id: str
    parent_candidate_id: str
    operation: ProposalOperation
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_non_empty_str(self.candidate_id, field_name="candidate_id"),
        )
        object.__setattr__(
            self,
            "parent_candidate_id",
            _require_non_empty_str(
                self.parent_candidate_id, field_name="parent_candidate_id"
            ),
        )
        if not isinstance(self.operation, ProposalOperation):
            raise TypeError(
                f"RejectedCandidate.operation must be a ProposalOperation, got {self.operation!r}"
            )
        object.__setattr__(
            self, "reason", _require_non_empty_str(self.reason, field_name="reason")
        )


@dataclass(frozen=True, slots=True)
class CandidateModularizationSearchResult:
    """Everything one ``search_candidate_modularizations`` call produces (task instructions
    §7). Never declares one retained candidate "correct" -- every score/stability measure is
    reported for the caller (or a future Workbench UI) to compare, exactly like
    ``ModularizationEvaluation``/``WeightSpaceExplorationResult`` already do."""

    search_id: str
    model_id: str
    seed_candidate_id: str
    retained: tuple[CandidateModularizationBundle, ...]
    evaluations: tuple[ModularizationEvaluation, ...]
    weight_space_result: WeightSpaceExplorationResult | None
    lineage: tuple[CandidateLineage, ...]
    rejected: tuple[RejectedCandidate, ...]
    search_policy: SearchPolicy
    iterations_run: int
    policy_version: str
    warnings: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "search_id", _require_non_empty_str(self.search_id, field_name="search_id")
        )
        object.__setattr__(
            self, "model_id", _require_non_empty_str(self.model_id, field_name="model_id")
        )
        object.__setattr__(
            self,
            "seed_candidate_id",
            _require_non_empty_str(self.seed_candidate_id, field_name="seed_candidate_id"),
        )
        object.__setattr__(
            self,
            "retained",
            _require_tuple_of(
                self.retained, CandidateModularizationBundle, field_name="retained"
            ),
        )
        object.__setattr__(
            self,
            "evaluations",
            _require_tuple_of(
                self.evaluations, ModularizationEvaluation, field_name="evaluations"
            ),
        )
        if self.weight_space_result is not None and not isinstance(
            self.weight_space_result, WeightSpaceExplorationResult
        ):
            raise TypeError(
                "CandidateModularizationSearchResult.weight_space_result must be a "
                f"WeightSpaceExplorationResult or None, got {self.weight_space_result!r}"
            )
        object.__setattr__(
            self, "lineage", _require_tuple_of(self.lineage, CandidateLineage, field_name="lineage")
        )
        object.__setattr__(
            self,
            "rejected",
            _require_tuple_of(self.rejected, RejectedCandidate, field_name="rejected"),
        )
        if not isinstance(self.search_policy, SearchPolicy):
            raise TypeError(
                "CandidateModularizationSearchResult.search_policy must be a SearchPolicy, "
                f"got {self.search_policy!r}"
            )
        if (
            not isinstance(self.iterations_run, int)
            or isinstance(self.iterations_run, bool)
            or self.iterations_run < 0
        ):
            raise ValueError(
                "CandidateModularizationSearchResult.iterations_run must be a non-negative "
                f"int, got {self.iterations_run!r}"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        object.__setattr__(
            self, "warnings", _require_str_tuple(self.warnings, field_name="warnings")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = [
    "BoundaryFixedState",
    "CandidateLineage",
    "CandidateModularizationBundle",
    "CandidateModularizationSearchResult",
    "FixedBoundary",
    "ProposalOperation",
    "RejectedCandidate",
    "SearchConstraints",
    "SearchPolicy",
]
