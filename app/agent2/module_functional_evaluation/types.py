"""Functional Modularity Criteria from Agents 3 and 4 domain model.

Converts one candidate module into a battery of deterministic perturbation targets spanning
*both* inside and outside that module, against the *whole* canonical network -- never the
module's own filtered standalone artifact: dynamic isolation and sensitivity coherence are
properties of how a module behaves *relative to its surrounding context*, which only exists in
a whole-network simulation (unlike ``CALIBRATION_INDEPENDENCE``, which legitimately evaluates
one module fully isolated). Routed through the Harness to Agent 3 (never Agent 2 calling Agent
3 directly, mirroring ``app.agent2.module_calibration``'s own identical discipline for Agent 4)
to obtain real per-species perturbation-response data, which
``app.agent2.module_evaluation.functional_adapter`` then interprets into the two separate,
previously-reserved ``DYNAMIC_ISOLATION``/``SENSITIVITY_COHERENCE`` criteria.

**Never fabricates a score.** ``FunctionalEvaluationStatus.INSUFFICIENT_TARGETS``/
``UNSUPPORTED_ANALYSIS`` both mean *unavailable evidence* (no score is ever fabricated for
either); only ``EVALUATED`` carries real, available ``perturbation_effects`` data -- which may
itself disclose a genuinely poor isolation/coherence result (real, available negative evidence,
never hidden).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# --- Local validation helpers (mirrors app.agent2.module_calibration.types' own pattern) -----


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _clean_optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None, got {value!r}")
    return value or None


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


def _require_tuple_of(value: object, item_type: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}, got {value!r}")
    return value


class FunctionalEvaluationStatus(StrEnum):
    """One module's own explicit, closed functional-evaluation outcome vocabulary (task
    instructions §6: "keep distinct: genuine poor functional isolation; insufficient data;
    unsupported analysis; numerical/infrastructure failure"). Infrastructure/numerical failures
    are deliberately *not* a member here -- they are raised as errors by the Harness
    (``ModuleFunctionalEvaluationWorkflowError``) and never reach this disclosed vocabulary at
    all, mirroring ``app.agent2.module_calibration``'s own identical discipline."""

    #: A real battery of perturbations ran and produced per-species response data -- whether
    #: that data discloses strong isolation/coherence or genuinely poor isolation/coherence,
    #: this is always real, available evidence, never missing.
    EVALUATED = "EVALUATED"
    #: Too few internal and/or external perturbation targets existed to compute a meaningful
    #: signal (e.g. a module with no internal kinetic parameters at all, or a module that
    #: covers the entire network with nothing external to compare against) -- unavailable
    #: evidence, never a bad score.
    INSUFFICIENT_TARGETS = "INSUFFICIENT_TARGETS"
    #: The whole network itself has no eligible executable artifact to simulate at all (e.g.
    #: unresolved kinetics) -- decided locally, before any Harness round trip is attempted.
    #: Unavailable evidence, never a bad score.
    UNSUPPORTED_ANALYSIS = "UNSUPPORTED_ANALYSIS"


@dataclass(frozen=True, slots=True)
class PerturbationTargetSpec:
    """One deterministic perturbation this request asks Agent 3 to run -- ``is_internal`` is
    Agent 2's own classification (whether this target's own reaction belongs to the candidate
    module being evaluated), carried through unchanged so the adapter never needs to
    re-resolve module membership from the result alone."""

    target_kind: str
    target_id: str
    fraction: Decimal
    is_internal: bool

    def __post_init__(self) -> None:
        if self.target_kind not in ("PARAMETER", "INITIAL_CONCENTRATION"):
            raise ValueError(
                "PerturbationTargetSpec.target_kind must be 'PARAMETER' or "
                f"'INITIAL_CONCENTRATION', got {self.target_kind!r}"
            )
        object.__setattr__(
            self, "target_id", _require_non_empty_str(self.target_id, field_name="target_id")
        )
        if not isinstance(self.fraction, Decimal):
            raise TypeError(
                f"PerturbationTargetSpec.fraction must be a Decimal, got {self.fraction!r}"
            )
        if not isinstance(self.is_internal, bool):
            raise TypeError(
                f"PerturbationTargetSpec.is_internal must be a bool, got {self.is_internal!r}"
            )


@dataclass(frozen=True, slots=True)
class PerturbationEffectRecord:
    """One requested target's own real, disclosed result -- always present, regardless of
    whether that one perturbation itself remained numerically stable (an unstable/failed
    individual perturbation is itself disclosed data about that one target, not a reason to
    drop it silently; the adapter decides whether to use it)."""

    target_kind: str
    target_id: str
    is_internal: bool
    simulation_status: str
    remained_numerically_stable: bool
    relative_change_by_species: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_id", _require_non_empty_str(self.target_id, field_name="target_id")
        )
        if not isinstance(self.is_internal, bool):
            raise TypeError(
                f"PerturbationEffectRecord.is_internal must be a bool, got {self.is_internal!r}"
            )
        object.__setattr__(
            self,
            "simulation_status",
            _require_non_empty_str(self.simulation_status, field_name="simulation_status"),
        )
        if not isinstance(self.remained_numerically_stable, bool):
            raise TypeError(
                "PerturbationEffectRecord.remained_numerically_stable must be a bool, got "
                f"{self.remained_numerically_stable!r}"
            )

        def _is_species_decimal_pair(item: object) -> bool:
            return (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and bool(item[0])
                and isinstance(item[1], Decimal)
            )

        if not isinstance(self.relative_change_by_species, tuple) or any(
            not _is_species_decimal_pair(item) for item in self.relative_change_by_species
        ):
            raise TypeError(
                "PerturbationEffectRecord.relative_change_by_species must be a tuple of "
                f"(species_id, Decimal) pairs, got {self.relative_change_by_species!r}"
            )


@dataclass(frozen=True, slots=True)
class ModuleFunctionalEvaluationRequest:
    """One complete, self-contained request to functionally evaluate one candidate module --
    never sent anywhere by this package itself (routing is always the Harness's own job).

    ``whole_network_handoff`` is the identical, unfiltered Agent2->Agent3 handoff
    (``app.agent2.pipeline.build_canonical_downstream_handoff``) the main five-agent workflow
    already sends Agent 3 -- never the module's own filtered standalone artifact (see this
    module's own docstring for why). ``baseline_request`` carries plain ``SimulationRequest``-
    shaped fields as an opaque dict (this package never imports Agent 3's own Python package).
    """

    request_id: str
    correlation_id: str
    run_id: str
    parent_model_id: str
    modularization_id: str
    module_id: str
    whole_network_handoff: dict
    baseline_request: dict
    perturbation_targets: tuple[PerturbationTargetSpec, ...]
    internal_species_ids: tuple[str, ...]
    boundary_species_ids: tuple[str, ...]
    requested_at: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "correlation_id",
            "run_id",
            "parent_model_id",
            "modularization_id",
            "module_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty_str(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.whole_network_handoff, dict) or not self.whole_network_handoff.get(
            "antimony_text"
        ):
            raise ValueError(
                "ModuleFunctionalEvaluationRequest.whole_network_handoff must be a dict with a "
                f"non-empty 'antimony_text' key, got {self.whole_network_handoff!r}"
            )
        if not isinstance(self.baseline_request, dict):
            raise TypeError(
                "ModuleFunctionalEvaluationRequest.baseline_request must be a dict, got "
                f"{self.baseline_request!r}"
            )
        object.__setattr__(
            self,
            "perturbation_targets",
            _require_tuple_of(
                self.perturbation_targets, PerturbationTargetSpec, field_name="perturbation_targets"
            ),
        )
        object.__setattr__(
            self,
            "internal_species_ids",
            _require_str_tuple(self.internal_species_ids, field_name="internal_species_ids"),
        )
        object.__setattr__(
            self,
            "boundary_species_ids",
            _require_str_tuple(self.boundary_species_ids, field_name="boundary_species_ids"),
        )
        object.__setattr__(
            self, "requested_at", _clean_optional_str(self.requested_at, field_name="requested_at")
        )


@dataclass(frozen=True, slots=True)
class ModuleFunctionalEvaluationResult:
    """The structured, functional-evidence result one Harness round trip through Agent 3
    produces for one module -- always built by the Harness (``app.harness.module_functional
    _evaluation``) or, for ``UNSUPPORTED_ANALYSIS``/``INSUFFICIENT_TARGETS``, locally by this
    package's own ``unsupported_analysis_evaluation``/``insufficient_targets_evaluation``;
    never constructed by simulating anything in this package itself.

    ``status`` other than ``EVALUATED`` requires ``perturbation_effects`` to be empty --
    unavailable evidence is never accompanied by a partial, potentially-misleading result.
    """

    evaluation_id: str
    request_id: str
    correlation_id: str
    run_id: str
    parent_model_id: str
    modularization_id: str
    module_id: str
    status: FunctionalEvaluationStatus
    policy_version: str
    perturbation_effects: tuple[PerturbationEffectRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "evaluation_id",
            "request_id",
            "correlation_id",
            "run_id",
            "parent_model_id",
            "modularization_id",
            "module_id",
            "policy_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty_str(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.status, FunctionalEvaluationStatus):
            raise TypeError(
                "ModuleFunctionalEvaluationResult.status must be a FunctionalEvaluationStatus, "
                f"got {self.status!r}"
            )
        object.__setattr__(
            self,
            "perturbation_effects",
            _require_tuple_of(
                self.perturbation_effects,
                PerturbationEffectRecord,
                field_name="perturbation_effects",
            ),
        )
        if self.status is not FunctionalEvaluationStatus.EVALUATED and self.perturbation_effects:
            raise ValueError(
                f"ModuleFunctionalEvaluationResult.status={self.status.value!r} means "
                "unavailable evidence -- perturbation_effects must be empty, never partially "
                "populated"
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
    "FunctionalEvaluationStatus",
    "ModuleFunctionalEvaluationRequest",
    "ModuleFunctionalEvaluationResult",
    "PerturbationEffectRecord",
    "PerturbationTargetSpec",
]
