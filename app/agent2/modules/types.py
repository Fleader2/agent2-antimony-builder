"""Module Decomposition domain model (Increment 7).

``ModuleSpecification``/``ModuleDecomposition``/``InterModuleBoundaryInterface``
(`app.agent2.types`) are reused/extended, not redesigned -- see
``docs/10_module_decomposition.md`` §5-6 and ``app.agent2.version``'s own
Increment 7 entry for exactly what was added and why. This module adds
only the one new top-level collection those pre-existing, already-
approved contracts do not carry: ``ModuleDecompositionSet``, the
collection produced by one ``decompose_network`` call.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent2.types import ModuleDecomposition, ModuleSpecification

# --- Local validation helpers (mirrors the identical pattern already used in
# app.agent2.boundaries.types / app.agent2.kinetics.types / app.agent2.parameters.types) --------


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


def _require_unique(ids: tuple[str, ...], *, field_name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in ids:
        if item in seen:
            duplicates.add(item)
        seen.add(item)
    if duplicates:
        raise ValueError(f"{field_name} must be unique, found duplicate(s): {sorted(duplicates)}")


@dataclass(frozen=True, slots=True)
class ModuleDecompositionSet:
    """Every `ModuleDecomposition` (and their `ModuleSpecification`\\ s) produced for one
    `FullNetwork` + `BoundaryAssessmentSet`.

    Increment 7 v1 always produces exactly `len(decompositions) == 1`
    (Increment 7 instructions, Step 13) -- the type itself supports more,
    structurally, for a future increment to add e.g. a conservative or
    aggressive alternative without a contract change.

    **Design note (deviation from a literal reading of Increment 7 Step
    4):** ``module_specifications`` is not in that step's own minimal
    field list, but is added here as a necessary, conservative extension:
    ``ModuleDecomposition.module_ids`` is id-only by design (mirroring
    ``ModuleDecomposition``'s own pre-existing "references... never
    duplicates them" convention), so the actual ``ModuleSpecification``
    objects must live somewhere -- here, as a sibling field, mirroring
    the identical, already-established ``ModelSpecification
    .module_decomposition`` + ``.module_specifications`` sibling
    relationship. See ``docs/10_module_decomposition.md`` §4.
    """

    network_id: str
    boundary_policy_version: str
    decomposition_policy_version: str
    decompositions: tuple[ModuleDecomposition, ...]
    module_specifications: tuple[ModuleSpecification, ...] = ()
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        for field_name in ("boundary_policy_version", "decomposition_policy_version"):
            object.__setattr__(
                self,
                field_name,
                _require_non_empty_str(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "decompositions",
            _require_tuple_of(
                self.decompositions, ModuleDecomposition, field_name="decompositions"
            ),
        )
        _require_unique(
            tuple(d.decomposition_id for d in self.decompositions),
            field_name="ModuleDecompositionSet.decompositions[].decomposition_id",
        )
        object.__setattr__(
            self,
            "module_specifications",
            _require_tuple_of(
                self.module_specifications, ModuleSpecification, field_name="module_specifications"
            ),
        )
        _require_unique(
            tuple(m.module_id for m in self.module_specifications),
            field_name="ModuleDecompositionSet.module_specifications[].module_id",
        )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = ["ModuleDecompositionSet"]
