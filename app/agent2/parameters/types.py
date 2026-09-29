"""Parameter Declaration / Initialization output type (Increment 5).

`ParameterSpecification`/`ParameterSource` are reused unchanged from
`app.agent2.types` (Step 6: "do not redesign unless inspection shows an
essential missing field") -- the only extension made was one field
(`ParameterSpecification.kinetic_law_assignment_id`), added directly on
that existing type rather than here, since it belongs to the reused
contract itself. This module adds exactly one new type:
`ParameterDeclarationSet`, the collection that carries every declared
parameter for one `KineticLawAssignmentSet`.

**Identifiability-Aware Macroscopic-to-Microscopic Kinetic Reconstruction
increment**: adds `IdentifiabilityStatus` and `MicroscopicConstraint`, plus
one new field on `ParameterDeclarationSet` (`microscopic_constraints`).
Neither type is promoted to `app.agent2.types` -- they are policy-internal
to this package's own reconstruction logic (`app.agent2.parameters
.reconstruction`), exactly mirroring `KineticLawAssignment`/
`KineticLawReasonCode` staying in `app.agent2.kinetics.types` rather than
`app.agent2.types` (this codebase's own established "narrower reading" of
what counts as a public output-contract shape change).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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


class IdentifiabilityStatus(StrEnum):
    """Whether one candidate macroscopic-to-microscopic derivation is actually solvable
    from the specific combination of inputs at hand (Identifiability-Aware Macroscopic-to-
    Microscopic Kinetic Reconstruction increment) -- never a confidence score, a strict
    categorical classification only.

    Only `IDENTIFIABLE` may ever produce a `ParameterSource.DERIVED_FROM_MACRO_KINETICS`
    numeric value. `PARTIALLY_CONSTRAINED` is preserved exclusively as a
    `MicroscopicConstraint` (never a point value). `UNDERDETERMINED`/
    `INCOMPATIBLE_CONTEXT`/`INSUFFICIENT_EVIDENCE` never produce anything at all beyond the
    existing, unmodified fall-through to `HEURISTIC_INITIALIZATION`/`PLACEHOLDER`.
    """

    #: A unique, exact algebraic solution exists from the inputs at hand (e.g.
    #: `kcat = Vmax / [E]_total` with a condition-matched, non-zero `[E]_total`).
    IDENTIFIABLE = "IDENTIFIABLE"
    #: A real, non-trivial constraint relates the unknowns (e.g. `kf*Km = kr + kcat`), but
    #: the available inputs are provably one or more equations short of a unique point
    #: solution -- see `app.agent2.parameters.reconstruction`'s own module docstring
    #: (Berra et al. 2025's own explicit finding, `docs/15_macroscopic_to_microscopic_
    #: kinetic_reconstruction_design.md` §1.4/§3).
    PARTIALLY_CONSTRAINED = "PARTIALLY_CONSTRAINED"
    #: No constraint at all is available for this slot from the inputs at hand (e.g. only
    #: `Km` is known, with no `kcat`/`Vmax` at all) -- distinct from `PARTIALLY_CONSTRAINED`,
    #: which names a real, if incomplete, relationship.
    UNDERDETERMINED = "UNDERDETERMINED"
    #: Candidate inputs exist but do not share a compatible protein/reaction/substrate/
    #: experimental context (task Sec 5) -- never combined regardless of what a
    #: derivation would otherwise compute from them.
    INCOMPATIBLE_CONTEXT = "INCOMPATIBLE_CONTEXT"
    #: No candidate input exists for this slot at all (e.g. no `Vmax` evidence, or no
    #: resolved enzyme concentration) -- the ordinary, common, non-error case.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class MicroscopicConstraint:
    """One disclosed, unresolved relationship among elementary rate constants that
    macroscopic evidence constrains but does not uniquely determine.

    Never assigns a numeric value to any of the constrained unknowns -- see
    `IdentifiabilityStatus.PARTIALLY_CONSTRAINED`'s own docstring. `known_parameter_ids`
    names every already-declared `ParameterSpecification` (e.g. `kcat`, `Km`) the
    constraint expression references; `unresolved_parameter_names` names the elementary
    unknowns (`kf`/`kr`) this codebase does *not* declare a `ParameterSpecification` for at
    all here (declaring an unused, unconstrained placeholder parameter for an unknown a
    `MICHAELIS_MENTEN` law's own expression never references would misrepresent it as a
    real declared simulation parameter).
    """

    reaction_id: str
    kinetic_law_assignment_id: str
    status: IdentifiabilityStatus
    constraint_expression: str
    known_parameter_ids: tuple[str, ...]
    unresolved_parameter_names: tuple[str, ...]
    explanation: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reaction_id", _require_non_empty_str(self.reaction_id, field_name="reaction_id")
        )
        object.__setattr__(
            self,
            "kinetic_law_assignment_id",
            _require_non_empty_str(
                self.kinetic_law_assignment_id, field_name="kinetic_law_assignment_id"
            ),
        )
        if not isinstance(self.status, IdentifiabilityStatus):
            raise TypeError(
                f"MicroscopicConstraint.status must be an IdentifiabilityStatus, "
                f"got {self.status!r}"
            )
        if self.status not in (
            IdentifiabilityStatus.PARTIALLY_CONSTRAINED,
            IdentifiabilityStatus.UNDERDETERMINED,
        ):
            raise ValueError(
                "MicroscopicConstraint.status must be PARTIALLY_CONSTRAINED or "
                f"UNDERDETERMINED (a resolved or inapplicable slot has no constraint to "
                f"record) -- got {self.status!r}"
            )
        object.__setattr__(
            self,
            "constraint_expression",
            _require_non_empty_str(
                self.constraint_expression, field_name="constraint_expression"
            ),
        )
        object.__setattr__(
            self,
            "known_parameter_ids",
            _require_str_tuple(self.known_parameter_ids, field_name="known_parameter_ids"),
        )
        object.__setattr__(
            self,
            "unresolved_parameter_names",
            _require_str_tuple(
                self.unresolved_parameter_names, field_name="unresolved_parameter_names"
            ),
        )
        object.__setattr__(
            self, "explanation", _require_non_empty_str(self.explanation, field_name="explanation")
        )


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

    `microscopic_constraints` (Identifiability-Aware Macroscopic-to-
    Microscopic Kinetic Reconstruction increment): every disclosed,
    unresolved elementary-rate-constant relationship found while declaring
    parameters -- never a point value, always accompanies (never replaces)
    the already-declared `kcat`/`Km` (or similar) parameters it references.
    """

    network_id: str
    kinetic_law_policy_version: str
    parameter_policy_version: str
    parameter_specifications: tuple[ParameterSpecification, ...]
    microscopic_constraints: tuple[MicroscopicConstraint, ...] = ()
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
        if not isinstance(self.microscopic_constraints, tuple) or any(
            not isinstance(item, MicroscopicConstraint) for item in self.microscopic_constraints
        ):
            raise TypeError(
                "ParameterDeclarationSet.microscopic_constraints must be a tuple of "
                f"MicroscopicConstraint, got {self.microscopic_constraints!r}"
            )
        object.__setattr__(
            self, "assumptions", _require_str_tuple(self.assumptions, field_name="assumptions")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = ["IdentifiabilityStatus", "MicroscopicConstraint", "ParameterDeclarationSet"]
