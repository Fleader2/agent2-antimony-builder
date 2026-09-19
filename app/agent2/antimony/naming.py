"""Deterministic Agent-2-id -> Antimony-identifier mapping (Increment 9, Step 6-7).

No Python ``hash()``, no random UUID. Every mapping is a pure function of
the input ids themselves: stable across repeated generation, independent
of collection order (every ordering-sensitive step sorts explicitly
first).

Each structural category (compartments, species, reactions, parameters)
gets its own name prefix (``c_``/``s_``/``J_``/``p_``), so identifiers
from different categories can never collide with each other by
construction -- only within-category collisions (two different source ids
sanitizing to the same string) need explicit resolution, handled by
``_resolve_category``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.agent2.types import FullNetwork, ModelSpecification

#: Deliberately conservative -- not a claim of Antimony/SBML grammar completeness, only a
#: known set of words that would be confusing or unsafe as a bare identifier. Checked in
#: lowercase; a category prefix (``c_``/``s_``/``J_``/``p_``) already makes an exact
#: collision with one of these unlikely, but the check stays as a defensive backstop.
ANTIMONY_RESERVED_WORDS = frozenset(
    {
        "model",
        "end",
        "species",
        "compartment",
        "reaction",
        "const",
        "var",
        "formula",
        "function",
        "event",
        "import",
        "module",
        "unit",
        "extends",
        "in",
        "true",
        "false",
        "and",
        "or",
        "not",
        "time",
        "avogadro",
        "pi",
        "infinity",
        "nan",
    }
)

_INVALID_CHAR = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_base(raw: str) -> str:
    """Antimony-safe base string: ASCII letters/digits/underscore only, never empty, never
    starting with a digit. Unicode is transliterated where possible (stdlib
    ``unicodedata`` only, no external dependency) and dropped otherwise."""
    ascii_text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    cleaned = _INVALID_CHAR.sub("_", ascii_text)
    if not cleaned or cleaned.strip("_") == "":
        cleaned = "id"
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _build_candidate(display_basis: str, *, prefix: str) -> str:
    candidate = f"{prefix}{_sanitize_base(display_basis)}"
    if candidate.lower() in ANTIMONY_RESERVED_WORDS:
        candidate = f"{candidate}_"
    return candidate


def _resolve_category(pairs: Sequence[tuple[str, str]], *, prefix: str) -> dict[str, str]:
    """``pairs`` is ``(unique_source_id, display_basis)``. Returns ``{unique_source_id:
    antimony_id}``, collision-safe and independent of ``pairs`` iteration order: when two or
    more unique source ids sanitize to the same candidate, the one that sorts first (by its
    own unique source id) keeps the bare candidate; the rest get a deterministic ``_2``,
    ``_3``, ... suffix, in sorted order.
    """
    groups: dict[str, list[str]] = {}
    for unique_id, display_basis in pairs:
        candidate = _build_candidate(display_basis, prefix=prefix)
        groups.setdefault(candidate, []).append(unique_id)

    mapping: dict[str, str] = {}
    for candidate, colliding_ids in groups.items():
        ordered = sorted(colliding_ids)
        for index, unique_id in enumerate(ordered, start=1):
            mapping[unique_id] = candidate if index == 1 else f"{candidate}_{index}"
    return mapping


@dataclass(frozen=True)
class IdentifierMap:
    """One shared identifier map for one ``generate_antimony`` run -- built once, reused for
    the full model and every module view/standalone artifact (Increment 9 instructions, Step
    32: the same Agent 2 entity must receive the same Antimony identifier everywhere).

    **Pre-commit revision**: ``reactions`` is keyed by
    ``ReactionSpecification.reaction_id`` -- **not**
    ``KineticLawSpecification.kinetic_law_id``. A biochemical reaction and
    a catalytic kinetic contribution are not the same thing: one
    ``ReactionSpecification`` always maps to exactly one Antimony
    reaction identifier, regardless of how many ``KineticLawSpecification``
    rows (distinct catalytic contexts) reference it. A kinetic law's own
    ``kinetic_law_id`` is never itself turned into a second Antimony
    reaction identifier -- it remains a plain, non-Antimony string used
    only in comments and unresolved-metadata (see
    ``docs/12_antimony_generation.md`` §7/§11).
    """

    compartments: dict[str, str]
    species: dict[str, str]
    parameters: dict[str, str]
    reactions: dict[str, str]


def sanitize_model_name(raw: str) -> str:
    """The Antimony-safe top-level model name for a ``model <name>()`` declaration."""
    return _build_candidate(raw, prefix="m_")


def build_identifier_map(model: ModelSpecification) -> IdentifierMap:
    """Build the one shared ``IdentifierMap`` for ``model``. Pure -- reads only, never
    mutates ``model``."""
    network: FullNetwork = model.full_network
    compartments = _resolve_category(
        [(c.compartment_id, c.compartment_id) for c in network.compartments], prefix="c_"
    )
    species = _resolve_category(
        [(s.species_id, s.species_id) for s in network.species], prefix="s_"
    )
    parameters = _resolve_category(
        [(p.parameter_id, p.parameter_id) for p in model.parameters], prefix="p_"
    )
    reactions = _resolve_category(
        [(r.reaction_id, r.reaction_id) for r in network.reactions], prefix="J_"
    )
    return IdentifierMap(
        compartments=compartments,
        species=species,
        parameters=parameters,
        reactions=reactions,
    )


def all_identifiers(id_map: IdentifierMap) -> Iterable[str]:
    """Every Antimony identifier this map assigns, for the serializer's own duplicate-id
    integrity check (Increment 9 instructions, Step 36)."""
    yield from id_map.compartments.values()
    yield from id_map.species.values()
    yield from id_map.parameters.values()
    yield from id_map.reactions.values()


__all__ = [
    "ANTIMONY_RESERVED_WORDS",
    "IdentifierMap",
    "all_identifiers",
    "build_identifier_map",
    "sanitize_model_name",
]
