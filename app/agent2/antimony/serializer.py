"""Pure text-rendering primitives: number/stoichiometry formatting and closed-vocabulary
kinetic-law expression substitution (Increment 9, Step 21).

Nothing here decides *whether* a law is executable (that policy lives in
``app.agent2.antimony.generator``) -- this module only renders already-
decided facts into Antimony-safe text. No expression is ever parsed,
evaluated, or mathematically simplified.
"""

from __future__ import annotations

import re
from decimal import Decimal

from app.agent2.antimony.errors import UnresolvedKineticExpressionError
from app.agent2.antimony.naming import IdentifierMap
from app.agent2.types import KineticLawSpecification, KineticLawType

#: Every character a rendered built-in expression may legally contain after substitution:
#: Antimony-safe identifier characters plus the fixed operators/parens/whitespace every
#: built-in template in ``app.agent2.model_specification.mapping.build_expression_and_species``
#: is built from (`` * ``, `` / ``, `` + ``, `` - ``, ``^``, ``()``).
_ALLOWED_RENDERED_EXPRESSION_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_ ()+-*/^."
)


def format_decimal(value: Decimal) -> str:
    """Render a ``Decimal`` exactly as Antimony would expect a numeric literal -- no
    scientific notation surprises, no fabricated precision. Integral values render without a
    trailing ``.0`` (``Decimal("2")`` -> ``"2"``, not ``"2.0"``) purely for readability;
    the underlying value is never rounded or altered."""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value, "f")


def format_stoichiometry(value: Decimal, antimony_species_id: str) -> str:
    """``"2 s_glucose"`` if stoichiometry != 1, else the bare species id -- never rewritten,
    never defaulted; ``value`` is always the exact ``Decimal`` already declared upstream."""
    if value == 1:
        return antimony_species_id
    return f"{format_decimal(value)} {antimony_species_id}"


def substitute_identifiers(expression: str, *, token_map: dict[str, str]) -> str:
    """Exact, closed-vocabulary token substitution -- never a blanket free-text ``.replace()``.

    ``token_map`` must contain exactly the raw ids (species_ids/parameter_ids) that may
    legitimately appear inside ``expression``: every built-in expression template
    (``app.agent2.model_specification.mapping.build_expression_and_species``) is built purely
    by joining these tokens with fixed operators/parens/whitespace, so an exact-match
    substitution over that closed vocabulary can never mis-rewrite anything else. Longest
    token first, so a token that is a substring of another token is never partially matched.
    """
    if not token_map:
        return expression
    tokens_longest_first = sorted(token_map, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(token) for token in tokens_longest_first))
    return pattern.sub(lambda match: token_map[match.group(0)], expression)


def render_kinetic_law_expression(
    law: KineticLawSpecification, id_map: IdentifierMap
) -> str | None:
    """Render ``law.expression`` into Antimony-safe identifiers, or ``None`` when there is
    nothing safe to render.

    Returns ``None`` (never fabricates a replacement) when:

    * ``law.expression`` is itself ``None`` (``UNASSIGNED``, or an unresolved
      multi-substrate Michaelis-Menten law -- Increment 9 instructions, Step 17-18);
    * ``law.law_type`` is ``CUSTOM`` -- the curated text has no structured symbol mapping
      this package can safely substitute into (Step 20); the raw text is never guessed at,
      never rewritten, and never emitted as though it were executable Antimony.
    """
    if law.expression is None:
        return None
    if law.law_type is KineticLawType.CUSTOM:
        return None
    token_map: dict[str, str] = {}
    for species_id in law.species_ids:
        token_map[species_id] = id_map.species[species_id]
    for parameter_id in law.parameter_ids:
        token_map[parameter_id] = id_map.parameters[parameter_id]
    rendered = substitute_identifiers(law.expression, token_map=token_map)
    _require_closed_vocabulary(rendered, law=law)
    return rendered


def _require_closed_vocabulary(rendered: str, *, law: KineticLawSpecification) -> None:
    """Serializer-integrity backstop (Increment 9 instructions, Step 36): every character of
    a rendered built-in expression must come from the fixed, known-safe character set. Should
    never fail given a valid ``ModelSpecification`` -- every raw token was drawn from
    ``law.species_ids``/``law.parameter_ids`` and substituted exactly."""
    stray = sorted({ch for ch in rendered if ch not in _ALLOWED_RENDERED_EXPRESSION_CHARS})
    if stray:
        raise UnresolvedKineticExpressionError(
            f"kinetic law {law.kinetic_law_id!r} rendered an Antimony expression containing "
            f"unexpected character(s) {stray!r} -- expected only substituted species_ids/"
            "parameter_ids joined by the fixed built-in-template operators"
        )


__all__ = [
    "format_decimal",
    "format_stoichiometry",
    "render_kinetic_law_expression",
    "substitute_identifiers",
]
