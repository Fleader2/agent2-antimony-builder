"""Deterministic dependency closure for one module's own retained reactions (task instructions
§3).

Computed fresh from the module's own ``REACTION`` ``ModuleMembership`` rows and the parent
model's reaction/kinetic-law/species/parameter registries -- never trusted from any pre-existing
``SPECIES``/``PARAMETER`` ``ModuleMembership`` rows a candidate happens to already carry. Those
rows are not a reliable closure for a search-generated candidate: ``app.agent2.antimony.generator
.generate_module_artifacts`` already documents (and falls back around) the fact that a search-
generated module's own ``PARAMETER`` memberships may be absent entirely. Recomputing from
reactions alone is the one authoritative, deterministic source.

Rules/events/observables are a disclosed, heuristic identifier-token scan only -- never real
parsing. ``app.agent2.types`` documents ``RuleSpecification.formula``/``EventSpecification
.trigger_formula``/``ObservableSpecification.formula`` as opaque text, "never parsed into an AST
or evaluated," and ``RuleSpecification.variable`` as "deliberately never checked against
FullNetwork's species/compartment ids." This module honors that: it never raises because a
formula or variable fails to resolve, and never claims the scan is a real cross-reference check
-- a rule/event/observable whose scan finds a reference outside the retained closure is simply
excluded and disclosed (see ``UnresolvedDependencyDisclosure``), never rejected as invalid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent2.submodel_materialization.types import UnresolvedDependencyDisclosure
from app.agent2.types import ModelSpecification

#: Deliberately permissive -- matches more than a real Antimony/SBML identifier grammar would.
#: Under-matching (missing a real reference, so a rule gets wrongly excluded or wrongly
#: retained) is the dangerous failure mode here, not over-matching a token that never was a
#: real id at all (which only ever makes this scan *more* conservative about exclusion, and is
#: harmless since an unknown token is simply not found in ``known_parent_ids`` either way).
_IDENTIFIER_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokens(*texts: str | None) -> frozenset[str]:
    found: set[str] = set()
    for text in texts:
        if text:
            found.update(_IDENTIFIER_TOKEN.findall(text))
    return frozenset(found)


@dataclass(frozen=True, slots=True)
class DependencyClosureResult:
    """Every parent-model component id the retained reactions require for executable
    semantics, plus the disclosed rule/event/observable retention decision."""

    reaction_ids: frozenset[str]
    species_ids: frozenset[str]
    parameter_ids: frozenset[str]
    kinetic_law_ids: frozenset[str]
    compartment_ids: frozenset[str]
    enzyme_state_ids: frozenset[str]
    explicit_enzyme_species_ids: frozenset[str]
    retained_rule_ids: frozenset[str]
    retained_event_ids: frozenset[str]
    retained_observable_ids: frozenset[str]
    unresolved_dependencies: tuple[UnresolvedDependencyDisclosure, ...]


def compute_dependency_closure(
    model: ModelSpecification, reaction_ids: frozenset[str]
) -> DependencyClosureResult:
    """Compute the full closure for exactly ``reaction_ids`` (already confirmed, by the
    caller, to be every ``REACTION`` ``ModuleMembership`` of the module being materialized).

    Raises ``ValueError`` only when ``reaction_ids`` names a reaction that does not exist in
    ``model.full_network.reactions`` at all -- should be impossible given
    ``ModelSpecification``'s own reference-integrity validation, but defensively checked
    (task instructions §3: "reject ... unresolved dependencies; never silently drop them").
    Every other structural gap (a kinetic law naming an unknown parameter, say) is left for
    the final ``ModelSpecification`` construction's own, already-complete reference validation
    to reject loudly -- never silently re-validated here.
    """
    reactions_by_id = {r.reaction_id: r for r in model.full_network.reactions}
    missing = sorted(reaction_ids - set(reactions_by_id))
    if missing:
        raise ValueError(
            f"compute_dependency_closure: reaction_ids {missing} do not exist in "
            "model.full_network.reactions"
        )
    reactions = tuple(reactions_by_id[rid] for rid in sorted(reaction_ids))

    species_ids: set[str] = {p.species_id for r in reactions for p in r.participants}

    laws = tuple(law for law in model.kinetic_laws if law.reaction_id in reaction_ids)
    kinetic_law_ids = frozenset(law.kinetic_law_id for law in laws)
    parameter_ids: set[str] = {pid for law in laws for pid in law.parameter_ids}
    species_ids |= {sid for law in laws for sid in law.species_ids}

    explicit_enzyme_species_ids: set[str] = set()
    enzyme_state_ids: set[str] = set()
    for law in laws:
        if law.protein_id is None and law.enzyme_state_id is None:
            continue
        for species in model.full_network.species:
            matched = (
                law.protein_id is not None and species.source_protein_id == law.protein_id
            ) or (
                law.enzyme_state_id is not None
                and species.source_enzyme_state_id == law.enzyme_state_id
            )
            if matched:
                explicit_enzyme_species_ids.add(species.species_id)
                if species.source_enzyme_state_id is not None:
                    enzyme_state_ids.add(species.source_enzyme_state_id)
        if law.enzyme_state_id is not None:
            enzyme_state_ids.add(law.enzyme_state_id)
    species_ids |= explicit_enzyme_species_ids

    species_by_id = {s.species_id: s for s in model.full_network.species}
    compartment_ids: set[str] = {
        species_by_id[sid].compartment_id for sid in species_ids if sid in species_by_id
    }

    known_parent_ids = (
        {r.reaction_id for r in model.full_network.reactions}
        | {s.species_id for s in model.full_network.species}
        | {p.parameter_id for p in model.parameters}
        | {c.compartment_id for c in model.full_network.compartments}
    )
    retained_ids = species_ids | parameter_ids | reaction_ids | compartment_ids

    retained_rule_ids: set[str] = set()
    retained_event_ids: set[str] = set()
    retained_observable_ids: set[str] = set()
    unresolved: list[UnresolvedDependencyDisclosure] = []

    for rule in model.rules:
        referenced = _tokens(rule.formula, rule.variable) & known_parent_ids
        out_of_scope = sorted(referenced - retained_ids)
        if out_of_scope:
            unresolved.append(
                UnresolvedDependencyDisclosure(
                    component_type="RULE",
                    component_id=rule.rule_id,
                    referenced_ids=tuple(out_of_scope),
                    reason=(
                        "rule formula/variable references parent-model id(s) outside this "
                        "module's own retained dependency closure"
                    ),
                )
            )
        else:
            retained_rule_ids.add(rule.rule_id)

    for event in model.events:
        assignment_tokens = (
            frozenset().union(*(_tokens(a.variable, a.formula) for a in event.assignments))
            if event.assignments
            else frozenset()
        )
        referenced = (
            _tokens(event.trigger_formula, event.delay_formula, event.priority_formula)
            | assignment_tokens
        ) & known_parent_ids
        out_of_scope = sorted(referenced - retained_ids)
        if out_of_scope:
            unresolved.append(
                UnresolvedDependencyDisclosure(
                    component_type="EVENT",
                    component_id=event.event_id,
                    referenced_ids=tuple(out_of_scope),
                    reason=(
                        "event trigger/delay/priority/assignment formula references "
                        "parent-model id(s) outside this module's own retained dependency "
                        "closure"
                    ),
                )
            )
        else:
            retained_event_ids.add(event.event_id)

    for observable in model.observables:
        referenced = _tokens(observable.formula) & known_parent_ids
        out_of_scope = sorted(referenced - retained_ids)
        if out_of_scope:
            unresolved.append(
                UnresolvedDependencyDisclosure(
                    component_type="OBSERVABLE",
                    component_id=observable.observable_id,
                    referenced_ids=tuple(out_of_scope),
                    reason=(
                        "observable formula references parent-model id(s) outside this "
                        "module's own retained dependency closure"
                    ),
                )
            )
        else:
            retained_observable_ids.add(observable.observable_id)

    return DependencyClosureResult(
        reaction_ids=frozenset(reaction_ids),
        species_ids=frozenset(species_ids),
        parameter_ids=frozenset(parameter_ids),
        kinetic_law_ids=kinetic_law_ids,
        compartment_ids=frozenset(compartment_ids),
        enzyme_state_ids=frozenset(enzyme_state_ids),
        explicit_enzyme_species_ids=frozenset(explicit_enzyme_species_ids),
        retained_rule_ids=frozenset(retained_rule_ids),
        retained_event_ids=frozenset(retained_event_ids),
        retained_observable_ids=frozenset(retained_observable_ids),
        unresolved_dependencies=tuple(unresolved),
    )


__all__ = ["DependencyClosureResult", "compute_dependency_closure"]
