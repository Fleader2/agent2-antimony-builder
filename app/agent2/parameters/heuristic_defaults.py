"""Heuristic simulation-parameter initialization defaults.

Centralized, documented, deterministic baseline values for a parameter slot that has
neither experimental (``LITERATURE_DERIVED``/``CURATED``) nor AI-predicted evidence at all
-- never a biochemical claim of any kind, purely a numerically well-behaved starting point
for a simulator, meant to be replaced by Agent 4 calibration. See
``app.agent2.parameters.initializer.initialize_with_fallback`` for where these defaults are
actually applied, only after both real evidence tiers have been checked and found empty.

Every default in this module is derived from exactly two reference constants
(``REFERENCE_RATE_PER_SEC``/``REFERENCE_CONCENTRATION_NM``) -- change those, not any
individual default, to retune every heuristically-initialized parameter in this codebase at
once.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

CANONICAL_UNIT_NM = "nM"
CANONICAL_UNIT_PER_SEC = "per_sec"
CANONICAL_UNIT_NM_PER_S = "nM_per_s"
CANONICAL_UNIT_PER_NMS = "per_nMs"

REFERENCE_RATE_PER_SEC = Decimal("1")
"""A first-order rate constant's own default (kcat, a unimolecular mass-action k, ...) -- 1
per second is a round, numerically well-behaved order of magnitude for an ODE integrator
(neither vanishingly slow nor explosively fast relative to a typical simulated timescale of
seconds to minutes); never a claim about any real enzyme's actual turnover rate."""

REFERENCE_CONCENTRATION_NM = Decimal("1000")
"""A Km/Ki-like concentration parameter's own default (1000 nM = 1 uM) -- a common order of
magnitude for enzyme-substrate affinity in real enzymology, chosen only so a heuristically-
initialized Michaelis-Menten law saturates at a plausible substrate scale; never a claim
about any real enzyme's actual affinity. Also the reference concentration every higher-
order mass-action default below is scaled against, so every heuristically-initialized
reaction -- regardless of its own molecularity -- produces a comparable characteristic flux
at this one shared concentration (see ``mass_action_rate_default``'s own docstring)."""


class ParameterKind(StrEnum):
    """Which canonical family a parameter slot belongs to -- decided by the caller
    (``app.agent2.parameters.builder``, from the kinetic-law type and which named slot this
    is), never inferred from a parameter's own id/name string here."""

    #: Km, Ki-like concentration parameters -> nM.
    CONCENTRATION = "CONCENTRATION"
    #: kcat and other parameters that are always first-order regardless of reaction
    #: molecularity -> per_sec.
    RATE_FIRST_ORDER = "RATE_FIRST_ORDER"
    #: Vmax-like concentration/time flux parameters -> nM_per_s.
    FLUX = "FLUX"
    #: A mass-action rate constant (k, kf, or kr) whose own unit depends on the reaction's
    #: own molecularity -- per_sec (n=1), nM_per_s (n=0), per_nMs (n=2), or an algebraic
    #: nM^(1-n)*s^-1 string for any other n (never a newly-invented named canonical unit,
    #: increment instructions: "do not invent arbitrary named units now"). Requires
    #: ``molecularity`` at the call site.
    MASS_ACTION_RATE = "MASS_ACTION_RATE"
    #: No heuristic default policy exists for this slot (e.g. a Hill coefficient or an
    #: equilibrium constant -- the increment's own instructions name only concentration/
    #: first-order-rate/flux/mass-action-rate families as supported). Always resolves to
    #: ``None`` from ``heuristic_default_for_kind`` -- never an invented convention for an
    #: unsupported kind.
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class HeuristicDefault:
    """One heuristic default's value and canonical (or, for a higher-order mass-action
    rate, algebraic) unit."""

    value: Decimal
    unit: str


def mass_action_rate_unit(molecularity: int) -> str:
    """The canonical (or algebraic) unit label for a mass-action rate constant of the given
    total reactant/product molecularity, per the increment's own formula:
    ``[k] = nM^(1-n) * s^-1``.

    The three orders this codebase's own canonical-unit specification names exactly get
    their canonical label (``n == 0`` -> ``nM_per_s``, ``n == 1`` -> ``per_sec``, ``n == 2``
    -> ``per_nMs``, since each is dimensionally identical to one of them); any other ``n``
    gets an algebraic string instead (e.g. ``"nM^-2 s^-1"`` for ``n == 3``) -- never a newly
    invented named canonical constant for a dimension this increment's own specification
    does not name.
    """
    if molecularity == 0:
        return CANONICAL_UNIT_NM_PER_S
    if molecularity == 1:
        return CANONICAL_UNIT_PER_SEC
    if molecularity == 2:
        return CANONICAL_UNIT_PER_NMS
    exponent = 1 - molecularity
    return f"nM^{exponent} s^-1"


def mass_action_rate_default(molecularity: int) -> HeuristicDefault:
    """The default value/unit for a mass-action rate constant of the given molecularity:
    ``k_n = REFERENCE_RATE_PER_SEC / REFERENCE_CONCENTRATION_NM ** (n - 1)``.

    Chosen so that, at exactly the reference concentration (every reactant/product at
    ``REFERENCE_CONCENTRATION_NM``), *every* heuristically-initialized mass-action reaction
    -- regardless of its own order -- produces the identical characteristic flux,
    ``REFERENCE_RATE_PER_SEC * REFERENCE_CONCENTRATION_NM`` (``nM_per_s``): a coherent,
    deterministic rationale for a specific numeric magnitude at every order, never an
    unexplained magic number chosen independently per order.
    """
    if molecularity < 0:
        raise ValueError(f"molecularity must be >= 0, got {molecularity}")
    value = REFERENCE_RATE_PER_SEC * (REFERENCE_CONCENTRATION_NM ** Decimal(1 - molecularity))
    return HeuristicDefault(value=value, unit=mass_action_rate_unit(molecularity))


def heuristic_default_for_kind(
    kind: ParameterKind, *, molecularity: int | None = None
) -> HeuristicDefault | None:
    """The centralized default for one parameter kind, or ``None`` when this kind has no
    heuristic default policy at all (e.g. a Hill coefficient or an equilibrium constant --
    the increment's own instructions name only concentration/first-order-rate/flux/mass-
    action-rate families as supported; anything else is deliberately left unresolved
    rather than assigned an invented convention).
    """
    if kind is ParameterKind.CONCENTRATION:
        return HeuristicDefault(value=REFERENCE_CONCENTRATION_NM, unit=CANONICAL_UNIT_NM)
    if kind is ParameterKind.RATE_FIRST_ORDER:
        return HeuristicDefault(value=REFERENCE_RATE_PER_SEC, unit=CANONICAL_UNIT_PER_SEC)
    if kind is ParameterKind.FLUX:
        return HeuristicDefault(
            value=REFERENCE_RATE_PER_SEC * REFERENCE_CONCENTRATION_NM,
            unit=CANONICAL_UNIT_NM_PER_S,
        )
    if kind is ParameterKind.MASS_ACTION_RATE:
        if molecularity is None:
            raise ValueError("molecularity is required for ParameterKind.MASS_ACTION_RATE")
        return mass_action_rate_default(molecularity)
    return None


__all__ = [
    "CANONICAL_UNIT_NM",
    "CANONICAL_UNIT_NM_PER_S",
    "CANONICAL_UNIT_PER_NMS",
    "CANONICAL_UNIT_PER_SEC",
    "REFERENCE_CONCENTRATION_NM",
    "REFERENCE_RATE_PER_SEC",
    "HeuristicDefault",
    "ParameterKind",
    "heuristic_default_for_kind",
    "mass_action_rate_default",
    "mass_action_rate_unit",
]
