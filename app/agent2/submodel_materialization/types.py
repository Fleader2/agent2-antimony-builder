"""Canonical Submodel Materialization domain model: lineage/provenance (task instructions §4)
and disclosed unresolved-dependency records (§3: "reject or disclose unresolved dependencies;
never silently drop them").

Boundary semantics (§2) reuse ``app.agent2.types.ModulePort``/``ModulePortDirection``/
``ModulePortRole`` verbatim -- that type already carries every role this increment's own list
names (input/output/input-output/externally-controlled/shared-pool), so
``BoundaryTreatmentRecord`` below is only a disclosure-friendly summary of a retained port's own
already-existing facts, never a new boundary vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from app.agent2.types import ModulePortDirection, ModulePortRole

if TYPE_CHECKING:
    from app.agent2.types import ModelSpecification


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class BoundaryTreatmentRecord:
    """One retained ``ModulePort``'s own boundary facts, disclosed verbatim as part of
    lineage -- never fabricated, never a new role/direction vocabulary."""

    species_id: str
    direction: ModulePortDirection
    role: ModulePortRole | None
    externally_controlled: bool
    initial_value: Decimal | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        if not isinstance(self.direction, ModulePortDirection):
            raise TypeError(
                "BoundaryTreatmentRecord.direction must be a ModulePortDirection, got "
                f"{self.direction!r}"
            )
        if self.role is not None and not isinstance(self.role, ModulePortRole):
            raise TypeError(
                f"BoundaryTreatmentRecord.role must be a ModulePortRole or None, got {self.role!r}"
            )
        if not isinstance(self.externally_controlled, bool):
            raise TypeError(
                "BoundaryTreatmentRecord.externally_controlled must be a bool, got "
                f"{self.externally_controlled!r}"
            )
        if self.initial_value is not None and not isinstance(self.initial_value, Decimal):
            raise TypeError(
                "BoundaryTreatmentRecord.initial_value must be a Decimal or None, got "
                f"{self.initial_value!r}"
            )


@dataclass(frozen=True, slots=True)
class UnresolvedDependencyDisclosure:
    """One rule/event/observable excluded from the materialized submodel because its own
    formula (or, for a rule, its ``variable``) references a parent-model id outside the
    retained closure -- disclosed, never silently dropped (task instructions §3).

    ``component_type`` is one of ``"RULE"``/``"EVENT"``/``"OBSERVABLE"`` (a plain string, not
    ``ModuleComponentType`` -- the excluded component was never retained by any
    ``ModuleMembership`` row, so there is no membership-row component_type to reuse)."""

    component_type: str
    component_id: str
    referenced_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.component_type not in ("RULE", "EVENT", "OBSERVABLE"):
            raise ValueError(
                "UnresolvedDependencyDisclosure.component_type must be one of 'RULE'/'EVENT'/"
                f"'OBSERVABLE', got {self.component_type!r}"
            )
        object.__setattr__(
            self,
            "component_id",
            _require_non_empty_str(self.component_id, field_name="component_id"),
        )
        object.__setattr__(
            self,
            "referenced_ids",
            _require_str_tuple(self.referenced_ids, field_name="referenced_ids"),
        )
        object.__setattr__(self, "reason", _require_non_empty_str(self.reason, field_name="reason"))


@dataclass(frozen=True, slots=True)
class SubmodelMaterializationLineage:
    """Exact traceability back to the parent model (task instructions §4) -- every id recorded
    here names a real component of the *parent* model (reaction/species/parameter/compartment
    ids) or of the *submodel* (its own modularization_id/module_id), never a fabricated or
    renamed identity."""

    parent_model_id: str
    parent_modularization_id: str
    parent_module_id: str
    submodel_modularization_id: str
    submodel_module_id: str
    retained_reaction_ids: tuple[str, ...]
    retained_species_ids: tuple[str, ...]
    retained_parameter_ids: tuple[str, ...]
    retained_compartment_ids: tuple[str, ...]
    explicit_enzyme_species_ids: tuple[str, ...]
    retained_rule_ids: tuple[str, ...]
    retained_event_ids: tuple[str, ...]
    retained_observable_ids: tuple[str, ...]
    boundary_treatments: tuple[BoundaryTreatmentRecord, ...]
    materialization_policy_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "parent_model_id",
            "parent_modularization_id",
            "parent_module_id",
            "submodel_modularization_id",
            "submodel_module_id",
            "materialization_policy_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty_str(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "retained_reaction_ids",
            "retained_species_ids",
            "retained_parameter_ids",
            "retained_compartment_ids",
            "explicit_enzyme_species_ids",
            "retained_rule_ids",
            "retained_event_ids",
            "retained_observable_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_str_tuple(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.boundary_treatments, tuple) or any(
            not isinstance(item, BoundaryTreatmentRecord) for item in self.boundary_treatments
        ):
            raise TypeError(
                "SubmodelMaterializationLineage.boundary_treatments must be a tuple of "
                f"BoundaryTreatmentRecord, got {self.boundary_treatments!r}"
            )
        if not self.retained_reaction_ids:
            raise ValueError(
                "SubmodelMaterializationLineage.retained_reaction_ids must be non-empty -- a "
                "submodel with zero reactions is never meaningful"
            )


@dataclass(frozen=True, slots=True)
class SubmodelMaterializationResult:
    """The materialized submodel plus its own full, disclosed lineage -- the public return
    shape of ``materialize_submodel``."""

    submodel: ModelSpecification
    submodel_modularization_id: str
    submodel_module_id: str
    lineage: SubmodelMaterializationLineage
    unresolved_dependencies: tuple[UnresolvedDependencyDisclosure, ...]

    def __post_init__(self) -> None:
        from app.agent2.types import ModelSpecification

        if not isinstance(self.submodel, ModelSpecification):
            raise TypeError(
                "SubmodelMaterializationResult.submodel must be a ModelSpecification, got "
                f"{self.submodel!r}"
            )
        object.__setattr__(
            self,
            "submodel_modularization_id",
            _require_non_empty_str(
                self.submodel_modularization_id, field_name="submodel_modularization_id"
            ),
        )
        object.__setattr__(
            self,
            "submodel_module_id",
            _require_non_empty_str(self.submodel_module_id, field_name="submodel_module_id"),
        )
        if not isinstance(self.lineage, SubmodelMaterializationLineage):
            raise TypeError(
                "SubmodelMaterializationResult.lineage must be a SubmodelMaterializationLineage, "
                f"got {self.lineage!r}"
            )
        if not isinstance(self.unresolved_dependencies, tuple) or any(
            not isinstance(item, UnresolvedDependencyDisclosure)
            for item in self.unresolved_dependencies
        ):
            raise TypeError(
                "SubmodelMaterializationResult.unresolved_dependencies must be a tuple of "
                f"UnresolvedDependencyDisclosure, got {self.unresolved_dependencies!r}"
            )


__all__ = [
    "BoundaryTreatmentRecord",
    "SubmodelMaterializationLineage",
    "SubmodelMaterializationResult",
    "UnresolvedDependencyDisclosure",
]
