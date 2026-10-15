"""Weight-Space Exploration and Stable Boundary Discovery.

Builds on the existing, unchanged Module Boundary Evaluation Framework
(`app.agent2.module_evaluation`) to systematically explore combinations of modularization-
criterion weights and identify module boundaries/modularizations that remain stable across
reasonable weighting assumptions. See `docs/30_weight_space_exploration_and_stable_boundary_
discovery.md` for the full design.

Public API: `explore_weight_space` (`exploration`); `generate_weight_vectors`,
`uniform_weight_grid` (`sampling`); `select_high_scoring_solutions`,
`compute_boundary_stability`, `compute_co_membership_stability`,
`compute_modularization_recurrence` (`stability`); `WeightRange`, `WeightGridSpec`,
`HighScoringSolutionSelectionMethod`, `HighScoringSolutionPolicy`, `BoundaryStability`,
`ComponentCoMembershipStability`, `ModularizationRecurrence`, `ModuleCountStabilityGroup`,
`WeightSpaceExplorationResult` (`types`); `WeightSpaceExplorationError`,
`WeightSpaceExplorationReferenceError` (`errors`).
"""

from __future__ import annotations

from app.agent2.weight_space_exploration.errors import (
    WeightSpaceExplorationError,
    WeightSpaceExplorationReferenceError,
)
from app.agent2.weight_space_exploration.exploration import explore_weight_space
from app.agent2.weight_space_exploration.sampling import (
    generate_weight_vectors,
    uniform_weight_grid,
)
from app.agent2.weight_space_exploration.stability import (
    compute_boundary_stability,
    compute_co_membership_stability,
    compute_modularization_recurrence,
    select_high_scoring_solutions,
)
from app.agent2.weight_space_exploration.types import (
    BoundaryStability,
    ComponentCoMembershipStability,
    HighScoringSolutionPolicy,
    HighScoringSolutionSelectionMethod,
    ModularizationRecurrence,
    ModuleCountStabilityGroup,
    WeightGridSpec,
    WeightRange,
    WeightSpaceExplorationResult,
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
    "WeightSpaceExplorationError",
    "WeightSpaceExplorationReferenceError",
    "WeightSpaceExplorationResult",
    "compute_boundary_stability",
    "compute_co_membership_stability",
    "compute_modularization_recurrence",
    "explore_weight_space",
    "generate_weight_vectors",
    "select_high_scoring_solutions",
    "uniform_weight_grid",
]
