"""Recursive Module Evaluation Orchestration domain model.

A candidate module from Agent 2's unified modularization system (``ModelModularization``/
``ModelModule``/``ModuleMembership``/``ModulePort``) can be converted into a standalone
executable Antimony submodel (the existing, unchanged
``app.agent2.antimony.generate_module_artifacts`` path) and sent, via the Harness, through
Agent 3 (simulation/diagnostics) then Agent 4 (calibration) to obtain calibration-based
evidence for that module's own ``CALIBRATION_INDEPENDENCE`` (``app.agent2.module_evaluation``)
score. **Agent 2 never calls Agent 4 (or Agent 3) directly anywhere in this package** -- it only
ever produces a ``ModuleCalibrationRequest`` (for some other caller/the Harness to route) and
parses a ``ModuleCalibrationEvaluation`` dict back (produced on the other end of that round
trip, by the Harness, never by this package, never by importing Agent 4's own Python package).

``INSUFFICIENT_DATA`` and ``BOUNDARY_INADEQUATE`` both mean *unavailable evidence* (no score is
ever fabricated for either) -- never a bad module-quality score. ``CALIBRATION_FAILED`` and
``UNIDENTIFIABLE`` are the opposite: genuine, real negative evidence about the module's own
calibration independence (the fit was attempted and did not succeed, or did succeed but could
not pin the module's own parameters down) -- these *do* count as available evidence with a low
score, exactly because fabricating nothing here would itself be a disclosure failure (silently
treating a real negative finding as "no information").
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# --- Local validation helpers (mirrors the identical pattern already used in
# app.agent2.module_evaluation.types / app.agent2.weight_space_exploration.types) -----------------


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


def _optional_decimal(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal or None, got {value!r}")
    return value


class ModuleCalibrationStatus(StrEnum):
    """One module calibration attempt's own explicit, closed outcome vocabulary (task
    instructions §3) -- never inferred by any other package from a raw Agent 4
    ``CalibrationStatus`` beyond this one, disclosed Harness-side mapping
    (``app.harness.module_calibration.map_calibration_status``)."""

    #: A fit was attempted and succeeded (or partially succeeded) -- real, available evidence,
    #: whether or not it is itself subsequently flagged by an identifiability finding.
    CALIBRATION_SUPPORTED = "CALIBRATION_SUPPORTED"
    #: A fit was attempted and did not succeed (optimization or simulation failure) -- real,
    #: available negative evidence, never "missing data."
    CALIBRATION_FAILED = "CALIBRATION_FAILED"
    #: No fit was attempted, or it could not be meaningfully attempted, for lack of evidence
    #: (no calibration dataset, too few observations) -- unavailable evidence, never a bad
    #: score.
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    #: A fit was attempted and the module's own parameters could not be practically pinned
    #: down standalone (Agent 4's own practical-identifiability diagnostics) -- real, available
    #: negative evidence.
    UNIDENTIFIABLE = "UNIDENTIFIABLE"
    #: The module itself has no explicit, eligible boundary treatment (no
    #: ``externally_controlled`` ``ModulePort``) -- detected locally from
    #: ``ModuleAntimonyArtifact`` alone, before any Harness round trip is even attempted.
    #: Unavailable evidence about calibration behavior specifically (the module was never
    #: actually simulated/fit at all) -- never a bad score, but also never silently identical
    #: to ``INSUFFICIENT_DATA`` (a *dataset* problem), since the distinction tells a future
    #: caller exactly what to fix: supply data (``INSUFFICIENT_DATA``) vs. supply an explicit
    #: boundary condition (``BOUNDARY_INADEQUATE``).
    BOUNDARY_INADEQUATE = "BOUNDARY_INADEQUATE"


#: Statuses meaning "no real calibration evidence exists" -- never fabricated into a score.
UNAVAILABLE_EVIDENCE_STATUSES: frozenset[ModuleCalibrationStatus] = frozenset(
    {ModuleCalibrationStatus.INSUFFICIENT_DATA, ModuleCalibrationStatus.BOUNDARY_INADEQUATE}
)


@dataclass(frozen=True, slots=True)
class CalibrationDatasetReference:
    """One opaque pointer to a calibration dataset/observation set -- Agent 2 never owns or
    inspects dataset content itself; only Agent 4 (via the Harness) resolves ``dataset_id``
    into real observations."""

    dataset_id: str
    description: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dataset_id", _require_non_empty_str(self.dataset_id, field_name="dataset_id")
        )
        object.__setattr__(
            self,
            "description",
            _clean_optional_str(self.description, field_name="description"),
        )
        object.__setattr__(
            self, "source", _clean_optional_str(self.source, field_name="source")
        )


@dataclass(frozen=True, slots=True)
class ModuleBoundaryPortRef:
    """One ``ModulePort``'s own minimal, plain-dict-serializable projection -- the "boundary
    inputs/outputs" a ``ModuleCalibrationRequest`` must identify (task instructions §2). Never
    a full ``ModulePort`` object (this package never imports ``app.agent2.types`` into the
    request/result contract itself, exactly like the Agent2->Agent3/Agent3->Agent4 handoffs
    carry only plain data, never a live object graph)."""

    port_id: str
    species_id: str
    #: ``ModulePortDirection.value`` (``"INPUT"``/``"OUTPUT"``/``"INPUT_OUTPUT"``) as a plain
    #: string -- decoupled from ``app.agent2.types.ModulePortDirection`` itself.
    direction: str
    externally_controlled: bool
    initial_value: Decimal | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "port_id", _require_non_empty_str(self.port_id, field_name="port_id")
        )
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        object.__setattr__(
            self, "direction", _require_non_empty_str(self.direction, field_name="direction")
        )
        if not isinstance(self.externally_controlled, bool):
            raise TypeError(
                "ModuleBoundaryPortRef.externally_controlled must be a bool, got "
                f"{self.externally_controlled!r}"
            )
        object.__setattr__(
            self,
            "initial_value",
            _optional_decimal(self.initial_value, field_name="initial_value"),
        )
        object.__setattr__(self, "unit", _clean_optional_str(self.unit, field_name="unit"))


@dataclass(frozen=True, slots=True)
class ModuleCalibrationRequest:
    """One complete, self-contained request to evaluate one module's own calibration
    independence, built entirely from Agent 2's own existing standalone-module generation path
    (``app.agent2.antimony.generate_module_artifacts``/``app.agent2.pipeline
    .build_module_downstream_handoff``) -- never sent anywhere by this package itself (task
    instructions §1: Agent 2 must not call Agent 4 directly; routing is always the Harness's own
    job).

    Identifies, per task instructions §2: ``parent_model_id`` (the parent canonical model),
    ``modularization_id``/``module_id``, ``module_handoff`` (the standalone module artifact, as
    the identical, already-filtered Agent2->Agent3 handoff dict
    ``build_module_downstream_handoff`` produces -- carrying its own ``antimony_text``, filtered
    ``species``/``reactions``/``kinetic_laws``/``parameters``, and ``antimony_symbol_map``, so a
    real calibration target can actually be resolved against it, never just a bare Antimony
    string), ``boundary_ports`` (boundary inputs/outputs), ``calibration_dataset_references``,
    and ``correlation_id``/``run_id`` (correlation/run ids).

    ``module_handoff`` is treated as an opaque, Agent2-owned plain dict here (never parsed or
    reinterpreted by this package) -- exactly the identical dict the Harness already knows how
    to hand to Agent 3 unchanged, no reshaping needed on that end either. Only ever built for a
    module that already has an eligible, executable standalone artifact (``module_handoff
    ["antimony_text"]`` is always a non-empty string here) -- an ineligible module is never
    wrapped into a request at all; see ``boundary_inadequate_evaluation`` for that case instead,
    which never needs the Harness round trip this request exists to drive.
    """

    request_id: str
    correlation_id: str
    run_id: str
    parent_model_id: str
    modularization_id: str
    module_id: str
    module_handoff: dict
    boundary_ports: tuple[ModuleBoundaryPortRef, ...]
    calibration_dataset_references: tuple[CalibrationDatasetReference, ...] = ()
    requested_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", _require_non_empty_str(self.request_id, field_name="request_id")
        )
        object.__setattr__(
            self,
            "correlation_id",
            _require_non_empty_str(self.correlation_id, field_name="correlation_id"),
        )
        object.__setattr__(
            self, "run_id", _require_non_empty_str(self.run_id, field_name="run_id")
        )
        object.__setattr__(
            self,
            "parent_model_id",
            _require_non_empty_str(self.parent_model_id, field_name="parent_model_id"),
        )
        object.__setattr__(
            self,
            "modularization_id",
            _require_non_empty_str(self.modularization_id, field_name="modularization_id"),
        )
        object.__setattr__(
            self, "module_id", _require_non_empty_str(self.module_id, field_name="module_id")
        )
        if not isinstance(self.module_handoff, dict) or not self.module_handoff.get(
            "antimony_text"
        ):
            raise ValueError(
                "ModuleCalibrationRequest.module_handoff must be a dict with a non-empty "
                f"'antimony_text' key, got {self.module_handoff!r}"
            )
        object.__setattr__(
            self,
            "boundary_ports",
            _require_tuple_of(
                self.boundary_ports, ModuleBoundaryPortRef, field_name="boundary_ports"
            ),
        )
        object.__setattr__(
            self,
            "calibration_dataset_references",
            _require_tuple_of(
                self.calibration_dataset_references,
                CalibrationDatasetReference,
                field_name="calibration_dataset_references",
            ),
        )
        object.__setattr__(
            self, "requested_at", _clean_optional_str(self.requested_at, field_name="requested_at")
        )


@dataclass(frozen=True, slots=True)
class FitQualitySummary:
    """A direct, unmodified projection of Agent 4's own ``CalibrationResult`` fit-quality
    fields -- never recomputed, never normalized here (that is
    ``calibration_adapter.score_calibration_independence``'s own, separate, disclosed job)."""

    objective_before: Decimal | None
    objective_after: Decimal | None
    total_sum_squared_residual: Decimal | None
    validation_sum_squared_residual: Decimal | None

    def __post_init__(self) -> None:
        for field_name in (
            "objective_before",
            "objective_after",
            "total_sum_squared_residual",
            "validation_sum_squared_residual",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(getattr(self, field_name), field_name=field_name),
            )


@dataclass(frozen=True, slots=True)
class IdentifiabilityFindingSummary:
    """A direct, unmodified projection of one Agent 4 ``IdentifiabilityFinding``."""

    finding_id: str
    category: str
    severity: str
    summary: str
    related_target_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "finding_id", _require_non_empty_str(self.finding_id, field_name="finding_id")
        )
        object.__setattr__(
            self, "category", _require_non_empty_str(self.category, field_name="category")
        )
        object.__setattr__(
            self, "severity", _require_non_empty_str(self.severity, field_name="severity")
        )
        object.__setattr__(
            self, "summary", _require_non_empty_str(self.summary, field_name="summary")
        )
        object.__setattr__(
            self,
            "related_target_ids",
            _require_str_tuple(self.related_target_ids, field_name="related_target_ids"),
        )


@dataclass(frozen=True, slots=True)
class ParameterUncertaintyEstimate:
    """One fitted parameter's own uncertainty, where available. ``standard_error=None`` always
    means "Agent 4 did not expose this for this target" -- never a fabricated zero/placeholder
    (Agent 4 computes a covariance matrix internally for its own ``HIGH_CORRELATION`` finding
    but does not expose per-parameter standard errors as public data today; see
    ``docs/31_recursive_module_evaluation_orchestration.md`` §5)."""

    target_id: str
    fitted_value: Decimal
    standard_error: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_id", _require_non_empty_str(self.target_id, field_name="target_id")
        )
        if not isinstance(self.fitted_value, Decimal):
            raise TypeError(
                f"ParameterUncertaintyEstimate.fitted_value must be a Decimal, got "
                f"{self.fitted_value!r}"
            )
        object.__setattr__(
            self,
            "standard_error",
            _optional_decimal(self.standard_error, field_name="standard_error"),
        )


@dataclass(frozen=True, slots=True)
class ParameterCorrelationEstimate:
    """One pair of fitted parameters' own correlation, where available (``target_id_a <
    target_id_b``, mirroring this codebase's own canonical-pair-ordering convention)."""

    target_id_a: str
    target_id_b: str
    correlation: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_id_a",
            _require_non_empty_str(self.target_id_a, field_name="target_id_a"),
        )
        object.__setattr__(
            self,
            "target_id_b",
            _require_non_empty_str(self.target_id_b, field_name="target_id_b"),
        )
        if self.target_id_a >= self.target_id_b:
            raise ValueError(
                "ParameterCorrelationEstimate requires target_id_a < target_id_b (canonical "
                f"ordering), got ({self.target_id_a!r}, {self.target_id_b!r})"
            )
        if not isinstance(self.correlation, Decimal):
            raise TypeError(
                f"ParameterCorrelationEstimate.correlation must be a Decimal, got "
                f"{self.correlation!r}"
            )


@dataclass(frozen=True, slots=True)
class BoundarySensitivityFinding:
    """One finding about this module's own sensitivity to its boundary/initial conditions --
    today, a direct projection of Agent 4's own ``BOUND_HIT``/``LOW_SENSITIVITY``
    identifiability-finding categories (the closest existing Agent 4 signal; see
    ``docs/31_recursive_module_evaluation_orchestration.md`` §5). Never a new sensitivity
    algorithm computed by this package."""

    target_id: str
    category: str
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_id", _require_non_empty_str(self.target_id, field_name="target_id")
        )
        object.__setattr__(
            self, "category", _require_non_empty_str(self.category, field_name="category")
        )
        object.__setattr__(
            self, "summary", _require_non_empty_str(self.summary, field_name="summary")
        )


@dataclass(frozen=True, slots=True)
class ParameterStabilitySummary:
    """One fitted parameter's own stability across several replicate/context calibration runs
    -- only ever populated when a caller actually supplied more than one
    ``CalibrationDatasetReference`` and the Harness actually ran Agent 4 once per reference
    (task instructions §3: "stability ... across context/replicate conditions"). Empty
    whenever only one dataset reference was supplied -- never fabricated from a single run."""

    target_id: str
    max_relative_difference: Decimal
    compared_run_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_id", _require_non_empty_str(self.target_id, field_name="target_id")
        )
        if not isinstance(self.max_relative_difference, Decimal) or (
            self.max_relative_difference < 0
        ):
            raise ValueError(
                "ParameterStabilitySummary.max_relative_difference must be a Decimal >= 0, "
                f"got {self.max_relative_difference!r}"
            )
        if not isinstance(self.compared_run_count, int) or isinstance(
            self.compared_run_count, bool
        ):
            raise TypeError(
                "ParameterStabilitySummary.compared_run_count must be an int, got "
                f"{self.compared_run_count!r}"
            )
        if self.compared_run_count < 2:
            raise ValueError(
                "ParameterStabilitySummary.compared_run_count must be >= 2 (stability requires "
                f"at least two compared runs), got {self.compared_run_count!r}"
            )


@dataclass(frozen=True, slots=True)
class ModuleCalibrationEvaluation:
    """The structured, calibration-based module-quality result a Harness round trip through
    Agent 3 then Agent 4 produces for one module (task instructions §3) -- always built by the
    Harness (``app.harness.module_calibration``) or, for ``BOUNDARY_INADEQUATE``, locally by
    ``boundary_inadequate_evaluation`` below; never constructed by simulating or fitting
    anything in this package itself.

    ``status in UNAVAILABLE_EVIDENCE_STATUSES`` (``INSUFFICIENT_DATA``/``BOUNDARY_INADEQUATE``)
    requires every evidence field below to be empty/``None`` -- unavailable evidence is never
    accompanied by a partial, potentially-misleading number. ``CALIBRATION_FAILED``/
    ``UNIDENTIFIABLE``/``CALIBRATION_SUPPORTED`` carry no such restriction: each is real,
    available evidence that may legitimately come with partial findings.
    """

    evaluation_id: str
    request_id: str
    correlation_id: str
    run_id: str
    parent_model_id: str
    modularization_id: str
    module_id: str
    status: ModuleCalibrationStatus
    policy_version: str
    fit_quality: FitQualitySummary | None = None
    identifiability_findings: tuple[IdentifiabilityFindingSummary, ...] = ()
    parameter_uncertainty: tuple[ParameterUncertaintyEstimate, ...] = ()
    parameter_correlations: tuple[ParameterCorrelationEstimate, ...] = ()
    boundary_sensitivity_findings: tuple[BoundarySensitivityFinding, ...] = ()
    parameters_requiring_external_context: tuple[str, ...] = ()
    parameter_stability: tuple[ParameterStabilitySummary, ...] = ()
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
        if not isinstance(self.status, ModuleCalibrationStatus):
            raise TypeError(
                "ModuleCalibrationEvaluation.status must be a ModuleCalibrationStatus, got "
                f"{self.status!r}"
            )
        if self.fit_quality is not None and not isinstance(self.fit_quality, FitQualitySummary):
            raise TypeError(
                "ModuleCalibrationEvaluation.fit_quality must be a FitQualitySummary or None, "
                f"got {self.fit_quality!r}"
            )
        object.__setattr__(
            self,
            "identifiability_findings",
            _require_tuple_of(
                self.identifiability_findings,
                IdentifiabilityFindingSummary,
                field_name="identifiability_findings",
            ),
        )
        object.__setattr__(
            self,
            "parameter_uncertainty",
            _require_tuple_of(
                self.parameter_uncertainty,
                ParameterUncertaintyEstimate,
                field_name="parameter_uncertainty",
            ),
        )
        object.__setattr__(
            self,
            "parameter_correlations",
            _require_tuple_of(
                self.parameter_correlations,
                ParameterCorrelationEstimate,
                field_name="parameter_correlations",
            ),
        )
        object.__setattr__(
            self,
            "boundary_sensitivity_findings",
            _require_tuple_of(
                self.boundary_sensitivity_findings,
                BoundarySensitivityFinding,
                field_name="boundary_sensitivity_findings",
            ),
        )
        object.__setattr__(
            self,
            "parameters_requiring_external_context",
            _require_str_tuple(
                self.parameters_requiring_external_context,
                field_name="parameters_requiring_external_context",
            ),
        )
        object.__setattr__(
            self,
            "parameter_stability",
            _require_tuple_of(
                self.parameter_stability,
                ParameterStabilitySummary,
                field_name="parameter_stability",
            ),
        )
        object.__setattr__(
            self, "warnings", _require_str_tuple(self.warnings, field_name="warnings")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        if self.status in UNAVAILABLE_EVIDENCE_STATUSES:
            has_any_evidence = (
                self.fit_quality is not None
                or self.identifiability_findings
                or self.parameter_uncertainty
                or self.parameter_correlations
                or self.boundary_sensitivity_findings
                or self.parameter_stability
            )
            if has_any_evidence:
                raise ValueError(
                    f"ModuleCalibrationEvaluation.status={self.status.value!r} means unavailable "
                    "evidence -- every fit-quality/identifiability/uncertainty/correlation/"
                    "sensitivity/stability field must be empty, never partially populated"
                )


__all__ = [
    "UNAVAILABLE_EVIDENCE_STATUSES",
    "BoundarySensitivityFinding",
    "CalibrationDatasetReference",
    "FitQualitySummary",
    "IdentifiabilityFindingSummary",
    "ModuleBoundaryPortRef",
    "ModuleCalibrationEvaluation",
    "ModuleCalibrationRequest",
    "ModuleCalibrationStatus",
    "ParameterCorrelationEstimate",
    "ParameterStabilitySummary",
    "ParameterUncertaintyEstimate",
]
