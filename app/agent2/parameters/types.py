"""Parameter Declaration / Initialization output type (Increment 5).

`ParameterSpecification`/`ParameterSource` are reused unchanged from
`app.agent2.types` (Step 6: "do not redesign unless inspection shows an
essential missing field") -- the only extension made was one field
(`ParameterSpecification.kinetic_law_assignment_id`), added directly on
that existing type rather than here, since it belongs to the reused
contract itself. This module adds exactly one new type:
`ParameterDeclarationSet`, the collection that carries every declared
parameter for one `KineticLawAssignmentSet`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent2.types import ParameterSpecification

# --- Local validation helpers (mirrors the identical pattern already used in
# app.agent2.characterization.types / app.agent2.kinetics.types) --------------------------------


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class ParameterDeclarationSet:
    """Every `ParameterSpecification` declared for one `KineticLawAssignmentSet`.

    A reaction whose kinetic-law assignment is `UNASSIGNED` contributes no
    parameters at all (Increment 5 instructions, Step 8) -- so, unlike
    `KineticLawAssignmentSet` (which covers every reaction) or
    `NetworkCharacterization`, there is no "one entry per X" coverage
    invariant here. The invariant this type *does* enforce: every
    parameter's `kinetic_law_assignment_id` is set (structural -- every
    declared parameter belongs to exactly one kinetic-law assignment), and
    no `parameter_id` repeats. Whether that id actually names a real
    assignment in the source `KineticLawAssignmentSet` is checked by
    `declare_parameters` itself after construction (`builder.py`), not
    here -- this type alone has no assignment set to check against,
    exactly as `FullNetwork`'s own reference-integrity checks stay scoped
    to what it can itself resolve.
    """

    network_id: str
    kinetic_law_policy_version: str
    parameter_policy_version: str
    parameter_specifications: tuple[ParameterSpecification, ...]
    assumptions: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "network_id", _require_non_empty_str(self.network_id, field_name="network_id")
        )
        object.__setattr__(
            self,
            "kinetic_law_policy_version",
            _require_non_empty_str(
                self.kinetic_law_policy_version, field_name="kinetic_law_policy_version"
            ),
        )
        object.__setattr__(
            self,
            "parameter_policy_version",
            _require_non_empty_str(
                self.parameter_policy_version, field_name="parameter_policy_version"
            ),
        )
        if not isinstance(self.parameter_specifications, tuple) or any(
            not isinstance(item, ParameterSpecification) for item in self.parameter_specifications
        ):
            raise TypeError(
                "ParameterDeclarationSet.parameter_specifications must be a tuple of "
                f"ParameterSpecification, got {self.parameter_specifications!r}"
            )
        seen_ids: set[str] = set()
        for spec in self.parameter_specifications:
            if spec.kinetic_law_assignment_id is None:
                raise ValueError(
                    "ParameterDeclarationSet: every declared ParameterSpecification must set "
                    f"kinetic_law_assignment_id -- {spec.parameter_id!r} does not"
                )
            if spec.parameter_id in seen_ids:
                raise ValueError(
                    "ParameterDeclarationSet has duplicate parameter_id "
                    f"{spec.parameter_id!r}"
                )
            seen_ids.add(spec.parameter_id)
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = ["ParameterDeclarationSet"]
