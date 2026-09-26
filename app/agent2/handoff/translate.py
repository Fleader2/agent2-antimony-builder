"""Agent 1 -> Agent 2 Translation Layer.

``translate_agent1_view_to_agent2`` is this module's one public entry
point: given a raw, JSON-decoded ``dict`` shaped like Agent 1's real
``Agent1CuratedKnowledgeView`` (``app.agent1.types`` in the sibling
``agent1-biochemical-curator`` repository -- never imported here, see
below), deterministically builds this repository's own
``Agent1CuratedKnowledgeViewContract``. Replaces the uncommitted,
pilot-only translation scripts used by Real Integration Pilot 2 Run 1/Run
2 (``run_pilot2_run1.py``/``run_pilot2_run2.py``) with production code,
correcting one real defect those scripts had (see "protein_id" below).

**Why a raw ``dict``, not an Agent 1 Python object**: this repository
never imports Agent 1's runtime package, ORM models, or Python classes --
established throughout this codebase (see, for example,
``Agent1CuratedKnowledgeViewContract``'s own docstring, and
``docs/02_agent1_handoff_contract.md`` §2: "A future integration layer ...
is expected to translate a real Agent 1 ``Agent1CuratedKnowledgeView``
into this contract's shape -- most likely via serialization (e.g. JSON)
rather than an in-process Python import across repositories"). This
module *is* that integration layer, and takes exactly the input that
sentence anticipates: a plain, JSON-decoded mapping, not a live
cross-repository object. The pilot scripts' own ``sys.path.insert()``
cross-repo import hack is not repeated here, and must not be -- it was
always a pilot-only convenience, never proposed as production shape.

**No new biological inference**: every field is copied verbatim, byte-for-
byte where a value is already a string/number, or losslessly reshaped
(e.g. ``Decimal(str(x))`` for a numeric string) where the two sides use
different in-memory representations of the identical value. Nothing here
resolves a name to an id, infers a reaction from a protein/EC context,
narrows a plural field to one entry, or invents a value Agent 1 did not
supply. Where Agent 1 supplies ``None``/``()``, this translator passes
``None``/``()`` through -- it never treats "unresolved" as an error to
work around.

**Kinetic-measurement ``compound_id``** (Agent 2's field name) **is Agent
1's ``substrate_id`` verbatim, never derived from anything else** --
in particular, never derived from a SABIO-RK species label inside this
translator. Confirmed this increment (real, live Run 8 data): Agent 1
does not currently resolve a species label to a compound id for any real
kinetic measurement (``substrate_id`` is ``None`` for all 14 real SABIO-RK
measurements) -- this translator faithfully carries that absence forward
as ``compound_id=None`` rather than inventing a resolution Agent 1 itself
has not made. The intended scientific chain remains source evidence ->
Agent 1 compound resolution -> resolved ``substrate_id`` in the Agent 1
handoff -> this translation -> Agent 2's
``app.agent2.kinetics.reaction_context`` resolver -- never source
evidence -> this translator -> Agent 2 name matching. See
``docs/14_agent1_agent2_translation_layer.md`` §7 for the "does Agent 1
currently supply a resolved compound_id" finding this increment's own
inspection confirmed (no).

**Plural protein context (``protein_ids``)**: copied verbatim from
Agent 1's own ``protein_ids`` list. **``protein_id`` is also copied
verbatim from Agent 1's own ``protein_id``, never re-derived or nulled
out by this translator** -- a real, corrected defect found this
increment: the pilot scripts' own translation set ``protein_id=None``
whenever ``protein_ids`` had more than one entry, reasoning that a
single-valued field "cannot represent" multi-protein applicability. That
reasoning does not hold: Agent 1's real Run 8 handoff already reports a
non-``None`` ``protein_id`` (its own legacy, first-established-context
value) on every one of the 14 real measurements, including every one
whose ``protein_ids`` has two entries -- ``protein_id`` was never itself
ambiguous or unresolved in the source data; only ``protein_ids`` needed a
new field to exist at all. Renulling an already-resolved legacy value
during translation silently discarded real information Agent 1 had
already supplied. ``Agent2CuratedKineticMeasurement.protein_ids``'s own
``__post_init__`` already sorts and deduplicates deterministically
regardless of input order (``app.agent2.types``), so this translator
passes ``protein_ids`` through in whatever order Agent 1 supplies it,
relying on that existing invariant rather than reimplementing it here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from app.agent2.handoff.errors import MalformedHandoffPayloadError
from app.agent2.types import (
    Agent1CuratedKnowledgeViewContract,
    CuratedAllostericInteraction,
    CuratedClaim,
    CuratedCompartment,
    CuratedCompound,
    CuratedConfidenceSummary,
    CuratedEnzymeModification,
    CuratedEnzymeState,
    CuratedEnzymeStateTransition,
    CuratedEvidence,
    CuratedKineticMeasurement,
    CuratedReaction,
    CuratedReactionEnzymeAssociation,
    CuratedReactionParticipant,
    CuratedRegulatoryInteraction,
)


def _require(payload: Mapping[str, Any], key: str, *, entity: str) -> Any:
    if key not in payload:
        raise MalformedHandoffPayloadError(f"{entity} is missing required key {key!r}: {payload!r}")
    return payload[key]


def _require_list(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise MalformedHandoffPayloadError(
            f"Agent1CuratedKnowledgeView.{key} must be a list, got {type(value).__name__}"
        )
    return value


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise MalformedHandoffPayloadError(
            f"expected a decimal-parseable value, got {value!r}"
        ) from exc


def _require_decimal(value: Any, *, entity: str) -> Decimal:
    result = _decimal_or_none(value)
    if result is None:
        raise MalformedHandoffPayloadError(f"{entity} must not be None")
    return result


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _translate_compartment(raw: Mapping[str, Any]) -> CuratedCompartment:
    return CuratedCompartment(
        id=str(_require(raw, "id", entity="compartment")),
        name=str(_require(raw, "name", entity="compartment")),
    )


def _translate_compound(raw: Mapping[str, Any]) -> CuratedCompound:
    return CuratedCompound(
        id=str(_require(raw, "id", entity="compound")),
        name=str(_require(raw, "canonical_name", entity="compound")),
    )


def _translate_reaction(raw: Mapping[str, Any]) -> CuratedReaction:
    return CuratedReaction(
        id=str(_require(raw, "id", entity="reaction")),
        name=str(_require(raw, "name", entity="reaction")),
        reversible=raw.get("reversible"),
    )


def _translate_reaction_participant(raw: Mapping[str, Any]) -> CuratedReactionParticipant:
    return CuratedReactionParticipant(
        reaction_id=str(_require(raw, "reaction_id", entity="reaction_participant")),
        compound_id=str(_require(raw, "compound_id", entity="reaction_participant")),
        role=str(_require(raw, "role", entity="reaction_participant")),
        stoichiometry=_require_decimal(
            _require(raw, "stoichiometry", entity="reaction_participant"),
            entity="reaction_participant.stoichiometry",
        ),
        compartment_id=_str_or_none(raw.get("compartment_id")),
    )


def _translate_reaction_enzyme_association(
    raw: Mapping[str, Any],
) -> CuratedReactionEnzymeAssociation:
    return CuratedReactionEnzymeAssociation(
        reaction_id=str(_require(raw, "reaction_id", entity="reaction_enzyme_association")),
        protein_id=_str_or_none(raw.get("protein_id")),
        complex_id=_str_or_none(raw.get("complex_id")),
        enzyme_state_id=_str_or_none(raw.get("enzyme_state_id")),
        relationship=_str_or_none(raw.get("relationship")),
    )


def _translate_regulatory_interaction(raw: Mapping[str, Any]) -> CuratedRegulatoryInteraction:
    return CuratedRegulatoryInteraction(
        id=str(_require(raw, "id", entity="regulatory_interaction")),
        regulator_type=str(_require(raw, "regulator_type", entity="regulatory_interaction")),
        target_type=str(_require(raw, "target_type", entity="regulatory_interaction")),
        effect=str(_require(raw, "effect", entity="regulatory_interaction")),
        regulator_id=_str_or_none(raw.get("regulator_id")),
        target_id=_str_or_none(raw.get("target_id")),
    )


def _translate_kinetic_measurement(raw: Mapping[str, Any]) -> CuratedKineticMeasurement:
    protein_ids_raw = raw.get("protein_ids") or ()
    return CuratedKineticMeasurement(
        id=str(_require(raw, "kinetic_measurement_id", entity="kinetic_measurement")),
        parameter_type=str(_require(raw, "parameter_type", entity="kinetic_measurement")),
        value=_require_decimal(
            _require(raw, "value", entity="kinetic_measurement"), entity="kinetic_measurement.value"
        ),
        unit=str(_require(raw, "unit", entity="kinetic_measurement")),
        reaction_id=_str_or_none(raw.get("reaction_id")),
        # Copied verbatim -- never re-derived from protein_ids, never nulled out for an
        # "ambiguous" multi-protein case. See module docstring.
        protein_id=_str_or_none(raw.get("protein_id")),
        complex_id=_str_or_none(raw.get("complex_id")),
        # Agent 1's own field name is ``substrate_id`` -- never populated from a species
        # label by this translator. See module docstring.
        compound_id=_str_or_none(raw.get("substrate_id")),
        organism_id=_str_or_none(raw.get("organism_id")),
        publication_id=_str_or_none(raw.get("publication_id")),
        reported_parameter_type=_str_or_none(raw.get("reported_parameter_type")),
        normalized_value=_decimal_or_none(raw.get("normalized_value")),
        normalized_unit=_str_or_none(raw.get("normalized_unit")),
        strain=_str_or_none(raw.get("strain")),
        temperature_c=_decimal_or_none(raw.get("temperature_c")),
        ph=_decimal_or_none(raw.get("ph")),
        reported_rate_law=_str_or_none(raw.get("reported_rate_law")),
        source=_str_or_none(raw.get("source")),
        source_id=_str_or_none(raw.get("source_id")),
        confidence_score=_decimal_or_none(raw.get("confidence_score")),
        confidence_class=_str_or_none(raw.get("confidence_class")),
        notes=_str_or_none(raw.get("notes")),
        enzyme_state_id=_str_or_none(raw.get("enzyme_state_id")),
        # Passed through verbatim, in whatever order Agent 1 supplies -- CuratedKineticMeasurement
        # .__post_init__ already sorts/deduplicates deterministically; not reimplemented here.
        protein_ids=tuple(str(p) for p in protein_ids_raw),
    )


def _translate_enzyme_state(raw: Mapping[str, Any]) -> CuratedEnzymeState:
    return CuratedEnzymeState(
        id=str(_require(raw, "enzyme_state_id", entity="enzyme_state")),
        state_type=str(_require(raw, "state_type", entity="enzyme_state")),
        protein_id=_str_or_none(raw.get("protein_id")),
        complex_id=_str_or_none(raw.get("complex_id")),
        state_label=_str_or_none(raw.get("state_label")),
        compartment_id=_str_or_none(raw.get("compartment_id")),
        active_state=raw.get("active_state"),
        source=_str_or_none(raw.get("source")),
        source_id=_str_or_none(raw.get("source_id")),
        notes=_str_or_none(raw.get("notes")),
    )


def _translate_enzyme_modification(raw: Mapping[str, Any]) -> CuratedEnzymeModification:
    return CuratedEnzymeModification(
        id=str(_require(raw, "enzyme_modification_id", entity="enzyme_modification")),
        enzyme_state_id=str(_require(raw, "enzyme_state_id", entity="enzyme_modification")),
        modification_type=str(_require(raw, "modification_type", entity="enzyme_modification")),
        residue=_str_or_none(raw.get("residue")),
        residue_position=raw.get("residue_position"),
        site_label=_str_or_none(raw.get("site_label")),
        modifying_compound_id=_str_or_none(raw.get("modifying_compound_id")),
        stoichiometry=_decimal_or_none(raw.get("stoichiometry")),
        source=_str_or_none(raw.get("source")),
        source_id=_str_or_none(raw.get("source_id")),
        notes=_str_or_none(raw.get("notes")),
    )


def _translate_allosteric_interaction(raw: Mapping[str, Any]) -> CuratedAllostericInteraction:
    return CuratedAllostericInteraction(
        id=str(_require(raw, "allosteric_interaction_id", entity="allosteric_interaction")),
        enzyme_state_id=str(_require(raw, "enzyme_state_id", entity="allosteric_interaction")),
        ligand_compound_id=str(
            _require(raw, "ligand_compound_id", entity="allosteric_interaction")
        ),
        effect=str(_require(raw, "effect", entity="allosteric_interaction")),
        site_label=_str_or_none(raw.get("site_label")),
        mechanism=_str_or_none(raw.get("mechanism")),
        source=_str_or_none(raw.get("source")),
        source_id=_str_or_none(raw.get("source_id")),
        notes=_str_or_none(raw.get("notes")),
    )


def _translate_enzyme_state_transition(raw: Mapping[str, Any]) -> CuratedEnzymeStateTransition:
    return CuratedEnzymeStateTransition(
        id=str(_require(raw, "enzyme_state_transition_id", entity="enzyme_state_transition")),
        from_state_id=str(_require(raw, "from_state_id", entity="enzyme_state_transition")),
        to_state_id=str(_require(raw, "to_state_id", entity="enzyme_state_transition")),
        transition_type=str(_require(raw, "transition_type", entity="enzyme_state_transition")),
        reaction_id=_str_or_none(raw.get("reaction_id")),
        source=_str_or_none(raw.get("source")),
        source_id=_str_or_none(raw.get("source_id")),
        notes=_str_or_none(raw.get("notes")),
    )


def _translate_claim(raw: Mapping[str, Any]) -> CuratedClaim:
    return CuratedClaim(
        id=str(_require(raw, "id", entity="claim")),
        subject_type=str(_require(raw, "subject_type", entity="claim")),
        predicate=str(_require(raw, "predicate", entity="claim")),
        subject_id=_str_or_none(raw.get("subject_id")),
        object_type=_str_or_none(raw.get("object_type")),
        object_id=_str_or_none(raw.get("object_id")),
        value_text=_str_or_none(raw.get("value_text")),
        value_numeric=_decimal_or_none(raw.get("value_numeric")),
        unit=_str_or_none(raw.get("unit")),
    )


def _translate_evidence(raw: Mapping[str, Any]) -> CuratedEvidence:
    # Agent 1's Evidence row names a publication only by publication_id (a foreign key) --
    # Agent1CuratedKnowledgeView resolves no Publication fields (title/DOI/authors) for
    # evidence at all, so the only faithful "reference" this translator can produce is the
    # id itself, never a fabricated citation string.
    return CuratedEvidence(
        id=str(_require(raw, "id", entity="evidence")),
        claim_id=str(_require(raw, "claim_id", entity="evidence")),
        publication_reference=_str_or_none(raw.get("publication_id")),
        quoted_support=_str_or_none(raw.get("quoted_support")),
    )


def _translate_confidence_summary(raw: Mapping[str, Any]) -> CuratedConfidenceSummary:
    return CuratedConfidenceSummary(
        claim_id=str(_require(raw, "claim_id", entity="confidence_summary")),
        status=str(_require(raw, "status", entity="confidence_summary")),
        confidence_score=_decimal_or_none(raw.get("confidence_score")),
        confidence_class=_str_or_none(raw.get("confidence_class")),
    )


def translate_agent1_view_to_agent2(
    view: Mapping[str, Any],
) -> Agent1CuratedKnowledgeViewContract:
    """Deterministically translate a raw Agent 1 handoff payload into Agent 2's own contract.

    ``view`` is a JSON-decoded ``dict`` shaped exactly like Agent 1's real
    ``Agent1CuratedKnowledgeView`` (each top-level key matching that
    dataclass's own field name; each nested entry matching its own row
    type's field names) -- the same shape every pilot script's
    ``to_jsonable`` helper has produced to date, since Agent 1 has not yet
    committed a canonical serialization function of its own. No database
    access, no network access, and no import of Agent 1's Python package
    occurs here or anywhere in this module.

    Raises ``MalformedHandoffPayloadError`` for a payload missing a
    required key or shaped unlike a list where one is expected -- never
    for a legitimately absent/``None``/empty field, which is Agent 1's own
    normal "not curated"/"not yet resolved" representation and is passed
    through unchanged.
    """
    return Agent1CuratedKnowledgeViewContract(
        contract_version=str(_require(view, "contract_version", entity="handoff")),
        organism_id=_str_or_none(view.get("organism_id")),
        compartments=tuple(
            _translate_compartment(c) for c in _require_list(view, "compartments")
        ),
        compounds=tuple(_translate_compound(c) for c in _require_list(view, "compounds")),
        reactions=tuple(_translate_reaction(r) for r in _require_list(view, "reactions")),
        reaction_participants=tuple(
            _translate_reaction_participant(p)
            for p in _require_list(view, "reaction_participants")
        ),
        reaction_enzyme_associations=tuple(
            _translate_reaction_enzyme_association(a)
            for a in _require_list(view, "reaction_enzyme_associations")
        ),
        regulatory_interactions=tuple(
            _translate_regulatory_interaction(r)
            for r in _require_list(view, "regulatory_interactions")
        ),
        kinetic_measurements=tuple(
            _translate_kinetic_measurement(m) for m in _require_list(view, "kinetic_measurements")
        ),
        enzyme_states=tuple(
            _translate_enzyme_state(s) for s in _require_list(view, "enzyme_states")
        ),
        enzyme_modifications=tuple(
            _translate_enzyme_modification(m) for m in _require_list(view, "enzyme_modifications")
        ),
        allosteric_interactions=tuple(
            _translate_allosteric_interaction(a)
            for a in _require_list(view, "allosteric_interactions")
        ),
        enzyme_state_transitions=tuple(
            _translate_enzyme_state_transition(t)
            for t in _require_list(view, "enzyme_state_transitions")
        ),
        claims=tuple(_translate_claim(c) for c in _require_list(view, "claims")),
        evidence=tuple(_translate_evidence(e) for e in _require_list(view, "evidence")),
        confidence_summaries=tuple(
            _translate_confidence_summary(s) for s in _require_list(view, "confidence_summaries")
        ),
        # Agent1CuratedKnowledgeView carries no `limitations` field at all (unlike the
        # broader Agent1KnowledgePackage) -- nothing to preserve, so this is always empty,
        # matching Agent1CuratedKnowledgeViewContract's own default.
        limitations=(),
    )


__all__ = ["translate_agent1_view_to_agent2"]
