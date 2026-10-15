"""Weight-Space Exploration and Stable Boundary Discovery domain model.

Builds directly on the existing, unchanged Module Boundary Evaluation Framework
(`docs/27_module_boundary_evaluation_framework.md`) -- `ModelModularization`,
`evaluate_modularization`, `evaluate_modularization_under_weights`, `TopologyFilteringPolicy`,
`CriteriaWeights`. Nothing here alters canonical model semantics: every type is a derived,
on-demand analysis result, never stored on `ModelSpecification`, exactly like
`ModularizationEvaluation` itself already is.

**Why module structure, not weight choice, drives stability.** A single `ModelModularization`
has one fixed module/membership/port structure -- re-scoring it under a different
`CriteriaWeights` vector never changes which reaction or species belongs to which module, only
the resulting `overall_score`. "Which boundaries are stable across weight space" therefore
means: across every (modularization, weight-vector) pair whose own score was high enough to be
selected (§ `HighScoringSolutionPolicy`), how often does a given reaction-adjacency edge end up
cut, or a given component pair end up co-membered? A modularization that scores well under
many different weight vectors contributes its own fixed structure to that tally once per
high-scoring weight vector -- naturally weighting a robustly-favored modularization's own
boundaries more heavily than one favored only under a narrow sliver of weight space. Several
structurally distinct candidate modularizations may also be explored together, so genuinely
different boundary hypotheses -- not just different weightings of the identical one -- can be
compared for robustness.

**Recursive readiness** (not implemented here): nothing below assumes "the whole canonical
model" -- `explore_weight_space` takes an ordinary `ModelSpecification` and a tuple of
`modularization_id`s exactly like `compare_modularizations` already does. A future increment
recursing into one selected module (to discover hierarchical submodules) only needs to build a
scoped sub-`ModelSpecification`/sub-`ModelModularization` set the identical way the existing
Scoped-Build Support increment already builds a scoped `FullNetwork` -- no interface change is
anticipated.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.agent2.module_evaluation import (
    CriteriaWeights,
    ModularizationCriterion,
    ModularizationEvaluation,
)
from app.agent2.types import ModuleComponentType

# --- Local validation helpers (mirrors the identical pattern already used in
# app.agent2.module_evaluation.types / app.agent2.boundaries.types) -----------------------------


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


def _require_unit_interval(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal, got {value!r}")
    if value < 0 or value > 1:
        raise ValueError(f"{field_name} must be within [0, 1], got {value!r}")
    return value


def _require_non_negative_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an int, got {value!r}")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class WeightRange:
    """One criterion's own explicit, deterministic set of candidate raw weight levels to
    explore (task instructions §2: "support user-supplied weight grids/ranges") -- the one
    building block of a `WeightGridSpec`. ``levels`` are the *raw* (un-normalized) weights
    `CriteriaWeights.weights` would carry for this criterion; `0` is a legitimate level,
    meaning "disabled" for that one generated vector, exactly like `CriteriaWeights`'s own
    existing "zero weight disables a criterion" rule.
    """

    criterion: ModularizationCriterion
    levels: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, ModularizationCriterion):
            raise TypeError(
                f"WeightRange.criterion must be a ModularizationCriterion, got {self.criterion!r}"
            )
        if not isinstance(self.levels, tuple) or not self.levels:
            raise TypeError(
                f"WeightRange.levels must be a non-empty tuple of Decimal, got {self.levels!r}"
            )
        for level in self.levels:
            if not isinstance(level, Decimal):
                raise TypeError(f"WeightRange.levels entries must be Decimal, got {level!r}")
            if level < 0:
                raise ValueError(f"WeightRange.levels entries must be >= 0, got {level!r}")
        # Deterministic, de-duplicated, sorted -- the same levels tuple always normalizes to
        # the identical cartesian-product order regardless of how a caller happened to list
        # them.
        object.__setattr__(self, "levels", tuple(sorted(set(self.levels))))


@dataclass(frozen=True, slots=True)
class WeightGridSpec:
    """A complete, deterministic weight-grid specification -- one `WeightRange` per criterion
    to vary (task instructions §2). `generate_weight_vectors` (`.sampling`) expands this into
    every legal `CriteriaWeights` combination (the all-zero combination is always excluded,
    since `CriteriaWeights` itself requires at least one positive weight), optionally capped
    at `max_combinations` via deterministic, evenly-spaced down-sampling -- never a random
    subset, so the identical spec always explores the identical vectors.
    """

    ranges: tuple[WeightRange, ...]
    max_combinations: int | None = None
    policy_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "ranges", _require_tuple_of(self.ranges, WeightRange, field_name="ranges")
        )
        if not self.ranges:
            raise ValueError("WeightGridSpec.ranges must not be empty")
        seen: set[ModularizationCriterion] = set()
        duplicates: set[ModularizationCriterion] = set()
        for r in self.ranges:
            if r.criterion in seen:
                duplicates.add(r.criterion)
            seen.add(r.criterion)
        if duplicates:
            raise ValueError(
                "WeightGridSpec.ranges must name each criterion at most once, found "
                f"duplicate(s): {sorted(c.value for c in duplicates)}"
            )
        if self.max_combinations is not None:
            if not isinstance(self.max_combinations, int) or isinstance(
                self.max_combinations, bool
            ):
                raise TypeError(
                    "WeightGridSpec.max_combinations must be an int or None, got "
                    f"{self.max_combinations!r}"
                )
            if self.max_combinations < 1:
                raise ValueError(
                    "WeightGridSpec.max_combinations must be >= 1, got "
                    f"{self.max_combinations!r}"
                )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


class HighScoringSolutionSelectionMethod(StrEnum):
    """Which rule `select_high_scoring_solutions` (`.stability`) applies -- task instructions
    §5's own named examples, a closed, deterministic vocabulary."""

    #: The ``value`` best-scoring, available evaluations (ties broken by `evaluation_id`,
    #: ascending, for full determinism).
    TOP_N = "TOP_N"
    #: The best ``value`` fraction (``0 < value <= 1``) of available evaluations, by score.
    PERCENTILE = "PERCENTILE"
    #: Every available evaluation whose own `overall_score` is within ``value`` of the single
    #: best available score.
    WITHIN_DELTA_OF_BEST = "WITHIN_DELTA_OF_BEST"


@dataclass(frozen=True, slots=True)
class HighScoringSolutionPolicy:
    """The complete, explicit, deterministic policy for which evaluated solutions contribute
    to stability calculations (task instructions §5) -- never implicit, never a hidden
    default a caller cannot inspect. An evaluation with `overall_score is None` (no available
    evidence at all, see `docs/27` §5) is never eligible under any method -- there is no score
    to rank or threshold.
    """

    method: HighScoringSolutionSelectionMethod
    value: Decimal
    policy_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.method, HighScoringSolutionSelectionMethod):
            raise TypeError(
                "HighScoringSolutionPolicy.method must be a HighScoringSolutionSelectionMethod, "
                f"got {self.method!r}"
            )
        if not isinstance(self.value, Decimal):
            raise TypeError(
                f"HighScoringSolutionPolicy.value must be a Decimal, got {self.value!r}"
            )
        if self.method is HighScoringSolutionSelectionMethod.TOP_N:
            if self.value < 1 or self.value != self.value.to_integral_value():
                raise ValueError(
                    f"HighScoringSolutionPolicy.value for TOP_N must be a positive integer "
                    f"Decimal, got {self.value!r}"
                )
        elif self.method is HighScoringSolutionSelectionMethod.PERCENTILE:
            if self.value <= 0 or self.value > 1:
                raise ValueError(
                    "HighScoringSolutionPolicy.value for PERCENTILE must be within (0, 1], got "
                    f"{self.value!r}"
                )
        else:
            if self.value < 0:
                raise ValueError(
                    "HighScoringSolutionPolicy.value for WITHIN_DELTA_OF_BEST must be >= 0, "
                    f"got {self.value!r}"
                )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


@dataclass(frozen=True, slots=True)
class BoundaryStability:
    """One reaction-adjacency edge's own recurrence as a *cut* boundary (its two reactions in
    different modules) across the high-scoring solution set.

    ``reaction_id_a < reaction_id_b`` always (canonical, deterministic pair ordering -- never
    two entries for the same unordered pair). ``cut_frequency`` is ``cut_count /
    high_scoring_solution_count`` -- the fraction of high-scoring solutions in which *both*
    reactions were covered by some module of that solution's own modularization *and* ended
    up in different modules. A solution where one or both reactions are not covered by any
    module at all never contributes to either the numerator or the denominator (this edge is
    simply inapplicable to that one solution, never counted as "not cut").
    """

    reaction_id_a: str
    reaction_id_b: str
    shared_species_ids: tuple[str, ...]
    cut_frequency: Decimal
    high_scoring_solution_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reaction_id_a",
            _require_non_empty_str(self.reaction_id_a, field_name="reaction_id_a"),
        )
        object.__setattr__(
            self,
            "reaction_id_b",
            _require_non_empty_str(self.reaction_id_b, field_name="reaction_id_b"),
        )
        if self.reaction_id_a >= self.reaction_id_b:
            raise ValueError(
                "BoundaryStability requires reaction_id_a < reaction_id_b (canonical pair "
                f"ordering), got reaction_id_a={self.reaction_id_a!r}, "
                f"reaction_id_b={self.reaction_id_b!r}"
            )
        object.__setattr__(
            self,
            "shared_species_ids",
            _require_str_tuple(self.shared_species_ids, field_name="shared_species_ids"),
        )
        object.__setattr__(
            self,
            "cut_frequency",
            _require_unit_interval(self.cut_frequency, field_name="cut_frequency"),
        )
        object.__setattr__(
            self,
            "high_scoring_solution_count",
            _require_non_negative_int(
                self.high_scoring_solution_count, field_name="high_scoring_solution_count"
            ),
        )
        if self.high_scoring_solution_count < 1:
            raise ValueError(
                "BoundaryStability.high_scoring_solution_count must be >= 1 -- a boundary "
                "inapplicable to every high-scoring solution is never reported at all"
            )


@dataclass(frozen=True, slots=True)
class ComponentCoMembershipStability:
    """One pair of canonical components' (of the identical `ModuleComponentType`) own
    co-membership recurrence across the high-scoring solution set -- the more general
    counterpart to `BoundaryStability` (meaningful for species, not only reaction-adjacency
    edges, and comparable *across different module counts* exactly because component ids are
    stable regardless of how many total modules a given modularization happens to have).

    ``component_id_a < component_id_b`` always. ``co_membership_frequency`` is
    ``co_membership_count / high_scoring_solution_count`` -- the fraction of high-scoring
    solutions in which both components were covered by some module of that solution's own
    modularization *and* shared at least one common module.
    """

    component_type: ModuleComponentType
    component_id_a: str
    component_id_b: str
    co_membership_frequency: Decimal
    high_scoring_solution_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.component_type, ModuleComponentType):
            raise TypeError(
                "ComponentCoMembershipStability.component_type must be a ModuleComponentType, "
                f"got {self.component_type!r}"
            )
        object.__setattr__(
            self,
            "component_id_a",
            _require_non_empty_str(self.component_id_a, field_name="component_id_a"),
        )
        object.__setattr__(
            self,
            "component_id_b",
            _require_non_empty_str(self.component_id_b, field_name="component_id_b"),
        )
        if self.component_id_a >= self.component_id_b:
            raise ValueError(
                "ComponentCoMembershipStability requires component_id_a < component_id_b "
                f"(canonical pair ordering), got component_id_a={self.component_id_a!r}, "
                f"component_id_b={self.component_id_b!r}"
            )
        object.__setattr__(
            self,
            "co_membership_frequency",
            _require_unit_interval(
                self.co_membership_frequency, field_name="co_membership_frequency"
            ),
        )
        object.__setattr__(
            self,
            "high_scoring_solution_count",
            _require_non_negative_int(
                self.high_scoring_solution_count, field_name="high_scoring_solution_count"
            ),
        )
        if self.high_scoring_solution_count < 1:
            raise ValueError(
                "ComponentCoMembershipStability.high_scoring_solution_count must be >= 1 -- a "
                "pair inapplicable to every high-scoring solution is never reported at all"
            )


@dataclass(frozen=True, slots=True)
class ModularizationRecurrence:
    """How often one candidate modularization's own evaluations were selected as
    high-scoring, among every weight vector it was actually evaluated under -- "modularization
    recurrence/similarity" (task instructions §4). A modularization recurring near `1`
    (high-scoring under nearly every explored weight vector) is robustly favored; one
    recurring near `0` is favored only under a narrow sliver of weight space, if at all.
    """

    modularization_id: str
    module_count: int
    evaluated_count: int
    high_scoring_count: int
    recurrence_frequency: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "modularization_id",
            _require_non_empty_str(self.modularization_id, field_name="modularization_id"),
        )
        object.__setattr__(
            self,
            "module_count",
            _require_non_negative_int(self.module_count, field_name="module_count"),
        )
        object.__setattr__(
            self,
            "evaluated_count",
            _require_non_negative_int(self.evaluated_count, field_name="evaluated_count"),
        )
        object.__setattr__(
            self,
            "high_scoring_count",
            _require_non_negative_int(self.high_scoring_count, field_name="high_scoring_count"),
        )
        if self.evaluated_count < 1:
            raise ValueError("ModularizationRecurrence.evaluated_count must be >= 1")
        if self.high_scoring_count > self.evaluated_count:
            raise ValueError(
                "ModularizationRecurrence.high_scoring_count must be <= evaluated_count, got "
                f"{self.high_scoring_count!r} > {self.evaluated_count!r}"
            )
        object.__setattr__(
            self,
            "recurrence_frequency",
            _require_unit_interval(self.recurrence_frequency, field_name="recurrence_frequency"),
        )
        expected = Decimal(self.high_scoring_count) / Decimal(self.evaluated_count)
        if self.recurrence_frequency != expected:
            raise ValueError(
                "ModularizationRecurrence.recurrence_frequency must equal high_scoring_count "
                f"/ evaluated_count ({expected!r}), got {self.recurrence_frequency!r}"
            )


@dataclass(frozen=True, slots=True)
class ModuleCountStabilityGroup:
    """Boundary/co-membership stability computed *within* one specific module count alone
    (task instructions §4: "stability within a given module count") -- a strict subset of the
    high-scoring solution set, restricted to solutions whose own modularization has exactly
    this many modules.
    """

    module_count: int
    high_scoring_solution_count: int
    boundary_stability: tuple[BoundaryStability, ...] = ()
    co_membership_stability: tuple[ComponentCoMembershipStability, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "module_count",
            _require_non_negative_int(self.module_count, field_name="module_count"),
        )
        object.__setattr__(
            self,
            "high_scoring_solution_count",
            _require_non_negative_int(
                self.high_scoring_solution_count, field_name="high_scoring_solution_count"
            ),
        )
        object.__setattr__(
            self,
            "boundary_stability",
            _require_tuple_of(
                self.boundary_stability, BoundaryStability, field_name="boundary_stability"
            ),
        )
        object.__setattr__(
            self,
            "co_membership_stability",
            _require_tuple_of(
                self.co_membership_stability,
                ComponentCoMembershipStability,
                field_name="co_membership_stability",
            ),
        )


@dataclass(frozen=True, slots=True)
class WeightSpaceExplorationResult:
    """Everything `explore_weight_space` (`.exploration`) produces: every (modularization,
    weight-vector) evaluation actually computed, plus the derived stability analysis over
    whichever subset `high_scoring_policy` selected. Never declares one solution "correct"
    (task instructions §6) -- no field here ranks, picks, or marks a modularization/weight
    vector as the answer; `modularization_recurrence`/`boundary_stability`/
    `co_membership_stability` are descriptive measures only, for a caller (today) or a future
    Workbench UI/recursive increment to interpret.

    "Evaluated modularizations," "scores," and "module counts" (task instructions §6) are
    never duplicated as separate top-level fields -- they are already present, per evaluation,
    on `evaluations` (`ModularizationEvaluation.modularization_id`/`.overall_score`/
    `.module_count`), the single source of truth this result's own stability fields are
    derived from.
    """

    exploration_id: str
    model_id: str
    weight_vectors: tuple[CriteriaWeights, ...]
    evaluations: tuple[ModularizationEvaluation, ...]
    high_scoring_policy: HighScoringSolutionPolicy
    high_scoring_evaluation_ids: tuple[str, ...]
    modularization_recurrence: tuple[ModularizationRecurrence, ...] = ()
    boundary_stability: tuple[BoundaryStability, ...] = ()
    co_membership_stability: tuple[ComponentCoMembershipStability, ...] = ()
    ambiguous_boundaries: tuple[BoundaryStability, ...] = ()
    ambiguous_co_memberships: tuple[ComponentCoMembershipStability, ...] = ()
    ambiguous_band_low: Decimal = Decimal("0.25")
    ambiguous_band_high: Decimal = Decimal("0.75")
    by_module_count: tuple[ModuleCountStabilityGroup, ...] = ()
    policy_version: str = ""
    warnings: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "exploration_id",
            _require_non_empty_str(self.exploration_id, field_name="exploration_id"),
        )
        object.__setattr__(
            self, "model_id", _require_non_empty_str(self.model_id, field_name="model_id")
        )
        object.__setattr__(
            self,
            "weight_vectors",
            _require_tuple_of(self.weight_vectors, CriteriaWeights, field_name="weight_vectors"),
        )
        if not self.weight_vectors:
            raise ValueError("WeightSpaceExplorationResult.weight_vectors must not be empty")
        object.__setattr__(
            self,
            "evaluations",
            _require_tuple_of(
                self.evaluations, ModularizationEvaluation, field_name="evaluations"
            ),
        )
        if not isinstance(self.high_scoring_policy, HighScoringSolutionPolicy):
            raise TypeError(
                "WeightSpaceExplorationResult.high_scoring_policy must be a "
                f"HighScoringSolutionPolicy, got {self.high_scoring_policy!r}"
            )
        object.__setattr__(
            self,
            "high_scoring_evaluation_ids",
            _require_str_tuple(
                self.high_scoring_evaluation_ids, field_name="high_scoring_evaluation_ids"
            ),
        )
        known_evaluation_ids = {e.evaluation_id for e in self.evaluations}
        unknown = sorted(set(self.high_scoring_evaluation_ids) - known_evaluation_ids)
        if unknown:
            raise ValueError(
                "WeightSpaceExplorationResult.high_scoring_evaluation_ids references unknown "
                f"evaluation_id(s): {unknown}"
            )
        object.__setattr__(
            self,
            "modularization_recurrence",
            _require_tuple_of(
                self.modularization_recurrence,
                ModularizationRecurrence,
                field_name="modularization_recurrence",
            ),
        )
        object.__setattr__(
            self,
            "boundary_stability",
            _require_tuple_of(
                self.boundary_stability, BoundaryStability, field_name="boundary_stability"
            ),
        )
        object.__setattr__(
            self,
            "co_membership_stability",
            _require_tuple_of(
                self.co_membership_stability,
                ComponentCoMembershipStability,
                field_name="co_membership_stability",
            ),
        )
        object.__setattr__(
            self,
            "ambiguous_boundaries",
            _require_tuple_of(
                self.ambiguous_boundaries, BoundaryStability, field_name="ambiguous_boundaries"
            ),
        )
        object.__setattr__(
            self,
            "ambiguous_co_memberships",
            _require_tuple_of(
                self.ambiguous_co_memberships,
                ComponentCoMembershipStability,
                field_name="ambiguous_co_memberships",
            ),
        )
        object.__setattr__(
            self,
            "ambiguous_band_low",
            _require_unit_interval(self.ambiguous_band_low, field_name="ambiguous_band_low"),
        )
        object.__setattr__(
            self,
            "ambiguous_band_high",
            _require_unit_interval(self.ambiguous_band_high, field_name="ambiguous_band_high"),
        )
        if self.ambiguous_band_low > self.ambiguous_band_high:
            raise ValueError(
                "WeightSpaceExplorationResult.ambiguous_band_low must be <= "
                f"ambiguous_band_high, got {self.ambiguous_band_low!r} > "
                f"{self.ambiguous_band_high!r}"
            )
        object.__setattr__(
            self,
            "by_module_count",
            _require_tuple_of(
                self.by_module_count, ModuleCountStabilityGroup, field_name="by_module_count"
            ),
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
    "BoundaryStability",
    "ComponentCoMembershipStability",
    "HighScoringSolutionPolicy",
    "HighScoringSolutionSelectionMethod",
    "ModularizationRecurrence",
    "ModuleCountStabilityGroup",
    "WeightGridSpec",
    "WeightRange",
    "WeightSpaceExplorationResult",
]
