"""Deterministic Agent-2-id -> Antimony-identifier mapping (Increment 9, Step 6-7).

**Human-Readable Antimony Naming increment.** For a ``GENERATED`` model, the *display basis*
fed into sanitization/collision-resolution below is now derived from the component's own
curated biological name where one exists (``CompartmentSpecification.name``/
``SpeciesSpecification.name``/``ReactionSpecification.name``/``ParameterSpecification.name``/
``ObservableSpecification.name``) -- never the raw canonical/Agent-1 id, which is a fallback
only, used when no meaningful name is available. For an ``IMPORTED`` model, the display basis
is still the raw id/symbol exactly as before this increment: an imported model's own
user-authored symbols are never renamed by this package (task instructions, "do not rename
user-uploaded Antimony symbols by default") -- see ``_display_basis_for_source`` below. Every
symbol's exact origin, regardless of which basis produced it, is separately recorded by
``build_symbol_provenance_map`` -- readability never costs traceability.

**Biological Display Metadata increment.** Reactions (and, by inheritance, their own
parameters) now prefer a curated gene symbol or protein name over the reaction's own curated
name when one is available, via ``_catalyst_display_basis`` -- approximately: (1) gene
symbol(s) of the reaction's associated protein(s); (2) protein/enzyme name(s), for an
associated protein with no linked gene symbol; (3) the reaction's own EC number, when neither
of the above resolves and the reaction's own curated name is also unusable; (4) the
reaction's own curated name (the pre-existing ``_biological_display_basis(r.name)`` path);
(5) the raw canonical id. This is a strict *preference order*, never a requirement: a
reaction with no curated catalyst metadata at all falls straight through to tier 4/5 exactly
as before this increment. Every gene/protein lookup reads only already-curated Agent 1 data
(``FullNetwork.genes``/``.proteins``, joined to a reaction via its own
``FullNetwork.enzyme_associations``) -- never inferred, matched, or resolved from free text.
See ``docs/24_biological_display_metadata.md``.

No Python ``hash()``, no random UUID. Every mapping is a pure function of
the input ids/names themselves: stable across repeated generation, independent
of collection order (every ordering-sensitive step sorts explicitly
first).

Each structural category (compartments, species, reactions, parameters, and -- Antimony
Import increment -- events, observables) gets its own name prefix (``c_``/``s_``/``J_``/
``p_``/``E_``/``obs_``), so identifiers from different categories can never collide with each
other by construction -- only within-category collisions (two different source ids
sanitizing to the same string) need explicit resolution, handled by ``_resolve_category``.
Rules need no category or naming of their own: a rule's own ``variable`` always names an
existing species or parameter identifier, already covered by those two maps -- a rule
automatically reads as readable as whatever its target already is.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.agent2.types import (
    AntimonySymbolProvenance,
    FullNetwork,
    ModelSourceType,
    ModelSpecification,
)

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
#: Removes bracketed/parenthetical chemical-notation detail (e.g. "[acyl-carrier protein]",
#: "(decarboxylating)") before deriving a display basis from a curated biological name --
#: this detail is real and correct, but turns a name into an unreadably long identifier if
#: sanitized verbatim. The full, untouched name is never discarded: it remains exactly as
#: curated on ``*.name`` and is never altered by this module; only the *displayed Antimony
#: symbol* is shortened.
_BRACKETED_SEGMENT = re.compile(r"\[[^\]]*\]|\([^)]*\)")
#: How many significant words a derived display basis keeps at most -- long enough that a
#: reaction's own curated name (often a full enzymatic description) stays recognizable, short
#: enough that it reads as a symbol, not a sentence.
_MAX_DISPLAY_WORDS = 6


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


def _biological_display_basis(
    name: str | None, *, max_words: int = _MAX_DISPLAY_WORDS
) -> str | None:
    """A concise, readable display basis derived from a curated biological name, or ``None``
    when ``name`` carries nothing meaningful to derive one from (the caller must then fall
    back to the raw canonical id -- this function never fabricates a name).

    Strips bracketed/parenthetical detail first (see ``_BRACKETED_SEGMENT``), splits the
    remainder into words on any non-alphanumeric boundary, and keeps at most ``max_words`` of
    them -- long enough to stay recognizable, short enough to read as a symbol. A name that is
    empty, or becomes empty after stripping (e.g. a name that was *only* a bracketed
    annotation), yields ``None``.
    """
    if not name or not name.strip():
        return None
    without_brackets = _BRACKETED_SEGMENT.sub(" ", name)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", without_brackets) if w]
    if not words:
        return None
    return "_".join(words[:max_words])


def _build_candidate(display_basis: str, *, prefix: str) -> str:
    candidate = f"{prefix}{_sanitize_base(display_basis)}"
    if candidate.lower() in ANTIMONY_RESERVED_WORDS:
        candidate = f"{candidate}_"
    return candidate


def _resolve_category(
    pairs: Sequence[tuple[str, str]], *, prefix: str
) -> tuple[dict[str, str], dict[str, str]]:
    """``pairs`` is ``(unique_source_id, display_basis)``. Returns ``({unique_source_id:
    antimony_id}, {unique_source_id: display_basis_used})``, collision-safe and independent of
    ``pairs`` iteration order: when two or more unique source ids sanitize to the same
    candidate, the one that sorts first (by its own unique source id) keeps the bare
    candidate; the rest get a deterministic ``_2``, ``_3``, ... suffix, in sorted order. The
    second return value is purely for ``build_symbol_provenance_map``'s own convenience (it
    would otherwise need to re-derive what basis produced each id).
    """
    groups: dict[str, list[str]] = {}
    basis_by_id: dict[str, str] = {}
    for unique_id, display_basis in pairs:
        candidate = _build_candidate(display_basis, prefix=prefix)
        groups.setdefault(candidate, []).append(unique_id)
        basis_by_id[unique_id] = display_basis

    mapping: dict[str, str] = {}
    for candidate, colliding_ids in groups.items():
        ordered = sorted(colliding_ids)
        for index, unique_id in enumerate(ordered, start=1):
            mapping[unique_id] = candidate if index == 1 else f"{candidate}_{index}"
    return mapping, basis_by_id


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
    #: Antimony Import increment.
    events: dict[str, str]
    observables: dict[str, str]


def sanitize_model_name(raw: str) -> str:
    """The Antimony-safe top-level model name for a ``model <name>()`` declaration."""
    return _build_candidate(raw, prefix="m_")


def _display_basis_for_source(
    model: ModelSpecification, *, canonical_id: str, biological_name: str | None
) -> str:
    """The display basis to sanitize for one component -- the one place this module decides
    between a derived, human-readable name and the raw canonical id.

    ``IMPORTED`` models always use the raw id (task instructions, "do not rename user-uploaded
    Antimony symbols by default" -- this increment "primarily fixes the GENERATED model
    path"). ``GENERATED`` models use the curated biological name when one yields a meaningful
    basis, falling back to the raw id otherwise (e.g. a parameter Agent 2 itself synthesized
    with no better name than its own slug, or a component Agent 1 curated with an empty
    name).
    """
    if model.source_type is ModelSourceType.IMPORTED:
        return canonical_id
    return _biological_display_basis(biological_name) or canonical_id


def _ec_display_basis(ec_number: str | None) -> str | None:
    """Tier 3 of the reaction naming hierarchy: a basis derived from a reaction's own
    curated EC number (e.g. ``"6.4.1.2"`` -> ``"EC_6_4_1_2"``), or ``None`` when no EC number
    is curated. Reached only when neither a catalyst-based basis (tier 1/2) nor the
    reaction's own curated name (tier 4) resolves to anything usable."""
    if not ec_number or not ec_number.strip():
        return None
    return f"EC_{_sanitize_base(ec_number)}"


def _catalyst_display_basis(network: FullNetwork, *, reaction_id: str) -> str | None:
    """Tier 1/2 of the reaction naming hierarchy: a display basis derived from the reaction's
    own curated catalyst(s), or ``None`` when none of its associated proteins resolve to a
    usable gene symbol or protein name -- the caller then falls through to this reaction's
    own curated name/EC number/raw id (tier 3/4/5), exactly as before this increment (task
    instructions, "do not require every reaction to have a gene symbol").

    For each of this reaction's own ``FullNetwork.enzyme_associations`` (Biological Display
    Metadata increment -- never an association's ``complex_id``/``enzyme_state_id``: Agent 1
    does not yet expose enzyme-complex membership, a disclosed, not-yet-implemented
    extension), prefers that catalyst's own curated gene symbol, falling back to its own
    curated protein name, falling back to skipping that one catalyst entirely (never
    skipping the whole reaction just because one of several catalysts lacks metadata).
    Multiple distinct, resolved catalyst labels are sorted and joined with ``"_"`` --
    deterministic, never an arbitrary "first one found" (task instructions, "do not require
    every reaction to have a gene symbol" + "multiple catalysts").
    """
    proteins_by_id = {p.id: p for p in network.proteins}
    genes_by_id = {g.id: g for g in network.genes}
    labels: set[str] = set()
    for association in network.enzyme_associations:
        if association.reaction_id != reaction_id or association.protein_id is None:
            continue
        protein = proteins_by_id.get(association.protein_id)
        if protein is None:
            continue
        gene = genes_by_id.get(protein.gene_id) if protein.gene_id else None
        if gene is not None and gene.symbol:
            labels.add(gene.symbol)
        elif protein.name:
            labels.add(protein.name)
    if not labels:
        return None
    return "_".join(sorted(labels))


def _protein_display_basis(network: FullNetwork, protein_id: str) -> str | None:
    """Display basis for one explicit catalytic enzyme-concentration species (Explicit
    Enzyme Concentration Representation increment): prefers that protein's own curated gene
    symbol (e.g. ``"ACC1"``, the task's own named example), falling back to the protein's own
    curated name, falling back to ``None`` when neither resolves. Mirrors
    ``_catalyst_display_basis``'s identical per-protein gene-symbol-then-name preference, but
    for exactly one already-known ``protein_id`` rather than every catalyst of a reaction."""
    proteins_by_id = {p.id: p for p in network.proteins}
    genes_by_id = {g.id: g for g in network.genes}
    protein = proteins_by_id.get(protein_id)
    if protein is None:
        return None
    gene = genes_by_id.get(protein.gene_id) if protein.gene_id else None
    if gene is not None and gene.symbol:
        return gene.symbol
    return protein.name


def _reaction_display_basis(model: ModelSpecification, network: FullNetwork, reaction) -> str:
    """The full reaction naming hierarchy (Biological Display Metadata increment): catalyst
    gene symbol/protein name (tier 1/2) > the reaction's own curated name (tier 4, via the
    pre-existing ``_display_basis_for_source``) > the reaction's own EC number (tier 3,
    reached only when the curated name itself is also unusable) > the raw canonical id
    (tier 5). ``IMPORTED`` models are unaffected -- ``_display_basis_for_source`` already
    returns the raw id unchanged for those, and this function never looks up catalyst
    metadata for one (task instructions, "this increment primarily fixes the GENERATED model
    path").
    """
    if model.source_type is ModelSourceType.IMPORTED:
        return reaction.reaction_id
    catalyst_basis = _catalyst_display_basis(network, reaction_id=reaction.reaction_id)
    if catalyst_basis:
        return catalyst_basis
    name_basis = _biological_display_basis(reaction.name)
    if name_basis:
        return name_basis
    ec_basis = _ec_display_basis(reaction.ec_number)
    if ec_basis:
        return ec_basis
    return reaction.reaction_id


def build_identifier_map(model: ModelSpecification) -> IdentifierMap:
    """Build the one shared ``IdentifierMap`` for ``model``. Pure -- reads only, never
    mutates ``model``."""
    network: FullNetwork = model.full_network

    compartments, compartment_basis = _resolve_category(
        [
            (
                c.compartment_id,
                _display_basis_for_source(
                    model, canonical_id=c.compartment_id, biological_name=c.name
                ),
            )
            for c in network.compartments
        ],
        prefix="c_",
    )

    # Species: compartment-aware disambiguation (task instructions, naming hierarchy tier 4)
    # -- the display basis folds in the *compartment's own* already-derived basis (never the
    # compartment's Antimony id, which already carries the "c_" category prefix) so that the
    # same compound in two different compartments reads as two distinct, both-readable
    # symbols (e.g. "Acetyl_CoA_cytosol" vs. "Acetyl_CoA_mitochondrial_matrix") rather than
    # colliding down to a single bare compound name with an opaque numeric suffix.
    def _species_basis(s) -> str:
        if model.source_type is ModelSourceType.IMPORTED:
            return s.species_id
        if s.source_protein_id is not None:
            # Explicit Enzyme Concentration Representation increment: an enzyme-concentration
            # species prefers its own catalyst's gene symbol/protein name (task's own named
            # example, "ACC1_c") over the generic compound/enzyme-state naming path below --
            # ``s.name`` already holds the protein's curated name, but a gene symbol (when
            # curated) is strictly more recognizable and is not otherwise reachable from a
            # bare ``SpeciesSpecification``.
            protein_basis = _protein_display_basis(network, s.source_protein_id)
            own_basis = _biological_display_basis(protein_basis) or s.species_id
        else:
            own_basis = _display_basis_for_source(
                model, canonical_id=s.species_id, biological_name=s.name
            )
        compartment_suffix = compartment_basis.get(s.compartment_id)
        if compartment_suffix and own_basis != s.species_id:
            return f"{own_basis}_{compartment_suffix}"
        return own_basis

    species, _species_basis_used = _resolve_category(
        [(s.species_id, _species_basis(s)) for s in network.species], prefix="s_"
    )

    reactions, reaction_basis = _resolve_category(
        [(r.reaction_id, _reaction_display_basis(model, network, r)) for r in network.reactions],
        prefix="J_",
    )

    # Biological Display Metadata increment: compound_id -> readable compound-name basis,
    # built from the already-assembled species (``SpeciesSpecification.source_compound_id``/
    # ``.name``) -- never a new lookup, reusing data the species pass above already read.
    # Sorted by species_id for determinism: the same compound usually names every one of its
    # own species identically regardless of compartment (``app.agent2.network.builder
    # .build_species`` sets ``name=compound.name`` for every compartment), so which one
    # "wins" in a dict-overwrite sense never actually matters in practice, but sorting keeps
    # this independent of ``network.species``'s own iteration order on principle.
    compound_display_by_id: dict[str, str] = {}
    for s in sorted(network.species, key=lambda s: s.species_id):
        if s.source_compound_id and s.source_compound_id not in compound_display_by_id:
            compound_basis = _biological_display_basis(s.name)
            if compound_basis:
                compound_display_by_id[s.source_compound_id] = compound_basis

    def _substrate_suffix(substrate_id: str | None) -> str:
        """Tier addition to parameter naming (Biological Display Metadata increment,
        e.g. the task's own ``Km_ACC1_acetyl_CoA`` example): a parameter declared for one
        specific substrate (``ParameterSpecification.substrate_id``, e.g. a Michaelis
        constant) appends that compound's own readable name -- resolved from the model's
        own already-curated species, never a new biological mapping. ``""`` (no suffix) for
        a parameter with no ``substrate_id``, or whose ``substrate_id`` does not match a
        known compound (task instructions, "do not require every reaction to have a gene
        symbol" applies identically here: a missing/unresolvable substrate name is a silent
        no-op, never an error)."""
        if not substrate_id:
            return ""
        basis = compound_display_by_id.get(substrate_id)
        return f"_{basis}" if basis else ""

    # Parameters: a parameter's own id/name already embeds its owning reaction's raw id
    # (``app.agent2.parameters.policy.build_parameter_slug``, e.g. ``"Km_<reaction_id>_..."``)
    # -- substituting that exact, already-known substring for the reaction's own readable
    # basis turns "Km_<uuid>_<protein_id>_<substrate_id>" into "Km_<reaction_name>":
    # genuinely more readable. The substitution MUST happen on the raw, still-hyphenated
    # ``p.name`` before any word-splitting -- ``_biological_display_basis`` rejoins
    # hyphen-separated hex segments with "_", so a hyphenated UUID substring (as stored in
    # ``p.reaction_id``) can never be found inside an already-word-split basis string.
    # The trailing protein-context segment is deliberately dropped from the visible symbol
    # (Agent 2 has no gene/protein *symbol* data for the catalytic context -- see
    # docs/23_human_readable_antimony_naming.md §7); any resulting collision between two
    # parameters for the same reaction (e.g. isozyme-specific Km values) is resolved, same as
    # every other category, by ``_resolve_category``'s numeric-suffix disambiguation -- the
    # full original slug remains fully recoverable via the provenance map.
    def _parameter_basis(p) -> str:
        if model.source_type is ModelSourceType.IMPORTED:
            return p.parameter_id
        raw_name = p.name or p.parameter_id
        suffix = _substrate_suffix(p.substrate_id)
        if p.reaction_id and p.reaction_id in raw_name:
            reaction_readable = reaction_basis.get(p.reaction_id)
            if reaction_readable:
                prefix = raw_name.split(p.reaction_id, 1)[0].rstrip("_") or "p"
                basis = _biological_display_basis(f"{prefix}_{reaction_readable}", max_words=8)
                return f"{basis}{suffix}" if basis else p.parameter_id
        basis = _biological_display_basis(raw_name)
        return f"{basis}{suffix}" if basis else p.parameter_id

    parameters, _parameter_basis_used = _resolve_category(
        [(p.parameter_id, _parameter_basis(p)) for p in model.parameters], prefix="p_"
    )

    events, _event_basis_used = _resolve_category(
        [
            (
                e.event_id,
                _display_basis_for_source(model, canonical_id=e.event_id, biological_name=e.name),
            )
            for e in model.events
        ],
        prefix="E_",
    )
    observables, _observable_basis_used = _resolve_category(
        [
            (
                o.observable_id,
                _display_basis_for_source(
                    model, canonical_id=o.observable_id, biological_name=o.name
                ),
            )
            for o in model.observables
        ],
        prefix="obs_",
    )
    return IdentifierMap(
        compartments=compartments,
        species=species,
        parameters=parameters,
        reactions=reactions,
        events=events,
        observables=observables,
    )


def build_symbol_provenance_map(model: ModelSpecification) -> tuple[AntimonySymbolProvenance, ...]:
    """Every Antimony symbol ``build_identifier_map(model)`` would assign, each paired with
    its full traceability record back to the exact canonical/Agent-1 origin -- see
    ``AntimonySymbolProvenance``. Deterministic, pure, and independent of
    ``build_identifier_map``'s own internal basis-tracking (recomputes rather than shares
    mutable state): calling it twice for the identical ``model`` always returns the identical
    tuple.
    """
    id_map = build_identifier_map(model)
    network = model.full_network
    records: list[AntimonySymbolProvenance] = []

    for c in network.compartments:
        records.append(
            AntimonySymbolProvenance(
                antimony_symbol=id_map.compartments[c.compartment_id],
                component_type="COMPARTMENT",
                canonical_id=c.compartment_id,
                agent1_entity_id=c.source_entity_id,
                provenance_refs=c.provenance_refs,
            )
        )
    for s in network.species:
        records.append(
            AntimonySymbolProvenance(
                antimony_symbol=id_map.species[s.species_id],
                component_type="SPECIES",
                canonical_id=s.species_id,
                # Explicit Enzyme Concentration Representation increment: an enzyme-
                # concentration species has no ``source_compound_id`` of its own -- its
                # direct Agent-1 entity is the catalytic protein it represents.
                agent1_entity_id=s.source_compound_id or s.source_protein_id,
                provenance_refs=s.provenance_refs,
            )
        )
    for r in network.reactions:
        records.append(
            AntimonySymbolProvenance(
                antimony_symbol=id_map.reactions[r.reaction_id],
                component_type="REACTION",
                canonical_id=r.reaction_id,
                agent1_entity_id=r.source_reaction_id,
                provenance_refs=r.provenance_refs,
            )
        )
    for p in model.parameters:
        records.append(
            AntimonySymbolProvenance(
                antimony_symbol=id_map.parameters[p.parameter_id],
                component_type="PARAMETER",
                canonical_id=p.parameter_id,
                agent1_entity_id=None,
                source_reference=p.source_reference,
                provenance_refs=p.provenance_refs,
            )
        )
    for e in model.events:
        records.append(
            AntimonySymbolProvenance(
                antimony_symbol=id_map.events[e.event_id],
                component_type="EVENT",
                canonical_id=e.event_id,
                provenance_refs=e.provenance_refs,
            )
        )
    for o in model.observables:
        records.append(
            AntimonySymbolProvenance(
                antimony_symbol=id_map.observables[o.observable_id],
                component_type="OBSERVABLE",
                canonical_id=o.observable_id,
                provenance_refs=o.provenance_refs,
            )
        )
    return tuple(records)


def all_identifiers(id_map: IdentifierMap) -> Iterable[str]:
    """Every Antimony identifier this map assigns, for the serializer's own duplicate-id
    integrity check (Increment 9 instructions, Step 36)."""
    yield from id_map.compartments.values()
    yield from id_map.species.values()
    yield from id_map.parameters.values()
    yield from id_map.reactions.values()
    yield from id_map.events.values()
    yield from id_map.observables.values()


__all__ = [
    "ANTIMONY_RESERVED_WORDS",
    "IdentifierMap",
    "all_identifiers",
    "build_identifier_map",
    "build_symbol_provenance_map",
    "sanitize_model_name",
]
