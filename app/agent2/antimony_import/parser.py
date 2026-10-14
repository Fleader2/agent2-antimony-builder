"""Antimony Import increment: Antimony text -> canonical ``ModelSpecification``.

**Why real libraries, not a hand-rolled parser.** This package is this repository's first,
deliberate exception to its otherwise fully dependency-free design (see ``pyproject.toml``):
Antimony's real grammar (reaction arrows, rate-law expression syntax, event trigger/delay/
priority math, unit declarations, ...) is non-trivial, and a hand-rolled subset parser would
carry real, silent correctness risk against the actual language. ``import_antimony`` instead
uses the real ``antimony`` package (libAntimony's own Python bindings) to parse/validate
Antimony and compile it to SBML, then ``libsbml`` to walk that SBML into this repository's own
canonical representation -- never re-implementing Antimony's grammar, never guessing at a
construct's meaning from symbol names. This is confined entirely to this one package
(``app.agent2.antimony_import``); ``app.agent2.antimony`` (the generator: canonical ->
Antimony text) remains fully dependency-free and is unaffected (see
``tests/agent2/test_antimony_import_scope.py``).

**Supported constructs** (see ``docs/21_antimony_import_and_canonical_model.md`` for the full
canonical-schema reference):

* Compartments (id, name, size/volume, unit, constant).
* Species (id, name, compartment, initial amount *or* concentration, constant,
  boundary condition).
* Reactions (id, name, reactants/products with stoichiometry, reversibility, a free-form
  kinetic-law expression).
* Global parameters (id, name, value, unit).
* Assignment, rate, and algebraic rules.
* Events, with their trigger, delay, priority, ``useValuesFromTriggerTime``, and assignments.

**Unsupported constructs** -- syntactically valid Antimony/SBML this importer deliberately
rejects with a structured ``UnsupportedAntimonyConstructError`` rather than silently dropping
the construct's own semantics or guessing a substitute:

* Function definitions (``model.getNumFunctionDefinitions()``) -- a formula that calls one
  would otherwise *look* fine as opaque expression text while silently losing the function's
  actual mathematical meaning on any later export.
* ``InitialAssignment`` -- a distinct SBML construct from every rule type above (a one-time,
  not continuously-enforced, computed initial value); not in this increment's own supported-
  construct list (``docs/21_...md`` §4).
* Local, kinetic-law-scoped parameters (``KineticLaw.getNumLocalParameters()``) -- Antimony's
  own compiler already promotes an ordinarily-declared rate constant to a global parameter
  (confirmed directly), so encountering one at all signals a construct this importer has not
  verified it handles correctly.
* Any SBML package/plugin extension beyond SBML core (``comp``, ``fbc``, ...).

**Observables are never inferred from arbitrary Antimony/SBML** -- neither the core SBML
specification nor Antimony's own grammar has a native "observable" keyword (this is a PEtab/
COPASI-style convention layered on top), so a freshly-imported model's own ``observables``
tuple is always empty. See ``ModelSpecification.observables``/``ObservableSpecification`` for
how this repository's own exporter marks one well enough for *its own* importer to recover it
on a canonical -> Antimony -> canonical round trip specifically (never for third-party text).

**Never invents a biological mapping from a symbol name**: a compartment/species/parameter id
is carried through exactly as the source text spelled it -- never matched against Agent 1
entity ids, never assumed to mean any particular real-world compound/organism/reaction.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import antimony
import libsbml

from app.agent2.antimony.generator import OBSERVABLE_COMMENT_PREFIX
from app.agent2.antimony_import.errors import (
    MalformedAntimonySourceError,
    UnsupportedAntimonyConstructError,
)
from app.agent2.antimony_import.version import ANTIMONY_IMPORT_PARSER_VERSION
from app.agent2.types import (
    CompartmentSourceScope,
    CompartmentSpecification,
    EventAssignmentSpecification,
    EventSpecification,
    FullNetwork,
    KineticLawAssignmentSource,
    KineticLawSpecification,
    KineticLawType,
    ModelSourceProvenance,
    ModelSourceType,
    ModelSpecification,
    ObservableSpecification,
    ParameterSource,
    ParameterSpecification,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    RuleSpecification,
    RuleType,
    SpeciesSpecification,
)

_IMPORTED_ASSUMPTION = (
    "imported from externally-authored Antimony source; not Agent 1 curated -- see "
    "ModelSpecification.source_provenance"
)


def _library_versions() -> str:
    antimony_version = getattr(antimony, "__version__", "unknown")
    return f"antimony=={antimony_version};python-libsbml=={libsbml.getLibSBMLDottedVersion()}"


def _to_decimal(value: float) -> Decimal:
    """``Decimal(str(value))`` -- this repository's own established float->Decimal
    convention (``app.agent2.handoff.translate``), avoiding binary-float artifacts a direct
    ``Decimal(value)`` would introduce."""
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class _ParsedKineticLaw:
    kinetic_law: KineticLawSpecification
    parameter_ids_used: tuple[str, ...]


def _require_no_unsupported_constructs(model: libsbml.Model) -> None:
    if model.getNumFunctionDefinitions() > 0:
        names = [
            model.getFunctionDefinition(i).getId() for i in range(model.getNumFunctionDefinitions())
        ]
        raise UnsupportedAntimonyConstructError(
            f"model defines {model.getNumFunctionDefinitions()} function definition(s) "
            f"({names}) -- not supported by this importer (see module docstring)."
        )
    if model.getNumInitialAssignments() > 0:
        symbols = [
            model.getInitialAssignment(i).getSymbol()
            for i in range(model.getNumInitialAssignments())
        ]
        raise UnsupportedAntimonyConstructError(
            f"model defines {model.getNumInitialAssignments()} InitialAssignment(s) "
            f"({symbols}) -- not supported by this importer (see module docstring)."
        )
    for i in range(model.getNumReactions()):
        reaction = model.getReaction(i)
        law = reaction.getKineticLaw()
        if law is not None and law.getNumLocalParameters() > 0:
            raise UnsupportedAntimonyConstructError(
                f"reaction {reaction.getId()!r}'s kinetic law declares "
                f"{law.getNumLocalParameters()} local parameter(s) -- not supported by this "
                "importer (see module docstring)."
            )
    # SBML Level 3 Version 2's own core always registers one baseline "l3v2extendedmath"
    # plugin on every document, even the simplest possible model (confirmed directly) -- this
    # is not an optional package extension; only a *named* extension package (comp/fbc/qual/
    # layout/render/multi/arrays/distrib/...) is actually unsupported here.
    document = model.getSBMLDocument()
    if document is not None:
        extension_names = [
            document.getPlugin(i).getPackageName()
            for i in range(document.getNumPlugins())
            if document.getPlugin(i).getPackageName() not in ("core",)
            and "extendedmath" not in document.getPlugin(i).getPackageName()
        ]
        if extension_names:
            raise UnsupportedAntimonyConstructError(
                f"model uses SBML package extension(s) {extension_names} -- not supported by "
                "this importer (core SBML only)."
            )


def _parse_compartments(model: libsbml.Model) -> tuple[CompartmentSpecification, ...]:
    compartments = []
    for i in range(model.getNumCompartments()):
        c = model.getCompartment(i)
        compartments.append(
            CompartmentSpecification(
                compartment_id=c.getId(),
                name=c.getName() or c.getId(),
                source_scope=CompartmentSourceScope.MODELING_CONSTRUCT,
                initial_volume=_to_decimal(c.getSize()) if c.isSetSize() else None,
                volume_unit=c.getUnits() or None,
                constant=c.getConstant() if c.isSetConstant() else None,
                assumptions=(_IMPORTED_ASSUMPTION,),
            )
        )
    return tuple(compartments)


def _parse_species(model: libsbml.Model) -> tuple[SpeciesSpecification, ...]:
    species = []
    for i in range(model.getNumSpecies()):
        s = model.getSpecies(i)
        initial_amount = _to_decimal(s.getInitialAmount()) if s.isSetInitialAmount() else None
        initial_concentration = (
            _to_decimal(s.getInitialConcentration()) if s.isSetInitialConcentration() else None
        )
        species.append(
            SpeciesSpecification(
                species_id=s.getId(),
                name=s.getName() or s.getId(),
                compartment_id=s.getCompartment(),
                initial_amount=initial_amount,
                initial_concentration=initial_concentration,
                initialization_source=(
                    ParameterSource.IMPORTED
                    if initial_amount is not None or initial_concentration is not None
                    else None
                ),
                constant=s.getConstant() if s.isSetConstant() else None,
                boundary_condition=(
                    s.getBoundaryCondition() if s.isSetBoundaryCondition() else None
                ),
                assumptions=(_IMPORTED_ASSUMPTION,),
            )
        )
    return tuple(species)


def _referenced_names(node: libsbml.ASTNode) -> set[str]:
    """Every leaf symbol name ``node`` (an SBML/libsbml formula AST) references, recursively.
    Used to populate ``KineticLawSpecification.parameter_ids`` -- SBML's own ``KineticLaw``
    tracks no such list itself, and the generator (``app.agent2.antimony.generator``) only
    ever emits a parameter declaration line for a parameter some kinetic law's own
    ``parameter_ids`` actually names (confirmed directly) -- leaving this empty would silently
    drop every imported parameter declaration on any later re-export."""
    if node is None:
        return set()
    names: set[str] = set()
    if node.isName():
        names.add(node.getName())
    for i in range(node.getNumChildren()):
        names |= _referenced_names(node.getChild(i))
    return names


def _parse_reactions_and_laws(
    model: libsbml.Model, parameter_ids: set[str]
) -> tuple[tuple[ReactionSpecification, ...], tuple[KineticLawSpecification, ...]]:
    reactions = []
    kinetic_laws = []
    for i in range(model.getNumReactions()):
        r = model.getReaction(i)
        participants = []
        for j in range(r.getNumReactants()):
            ref = r.getReactant(j)
            participants.append(
                ReactionParticipantSpecification(
                    species_id=ref.getSpecies(),
                    role=ParticipantRole.REACTANT,
                    stoichiometry=_to_decimal(ref.getStoichiometry())
                    if ref.isSetStoichiometry()
                    else Decimal("1"),
                )
            )
        for j in range(r.getNumProducts()):
            ref = r.getProduct(j)
            participants.append(
                ReactionParticipantSpecification(
                    species_id=ref.getSpecies(),
                    role=ParticipantRole.PRODUCT,
                    stoichiometry=_to_decimal(ref.getStoichiometry())
                    if ref.isSetStoichiometry()
                    else Decimal("1"),
                )
            )
        # Modifiers (catalysts/regulators named in the reaction but not consumed/produced) have
        # no stoichiometric role in this canonical representation -- ``ParticipantRole`` is
        # REACTANT/PRODUCT/MODIFIER, and a bare SBML ModifierSpeciesReference carries no
        # stoichiometry at all; carried through for completeness rather than silently dropped.
        for j in range(r.getNumModifiers()):
            ref = r.getModifier(j)
            participants.append(
                ReactionParticipantSpecification(
                    species_id=ref.getSpecies(),
                    role=ParticipantRole.MODIFIER,
                    stoichiometry=Decimal("1"),
                )
            )

        kinetic_law_id = None
        law = r.getKineticLaw()
        if law is not None and law.getFormula():
            kinetic_law_id = f"kl_{r.getId()}"
            referenced = _referenced_names(law.getMath())
            kinetic_laws.append(
                KineticLawSpecification(
                    kinetic_law_id=kinetic_law_id,
                    reaction_id=r.getId(),
                    law_type=KineticLawType.IMPORTED,
                    assignment_source=KineticLawAssignmentSource.IMPORTED,
                    expression=law.getFormula(),
                    parameter_ids=tuple(sorted(referenced & parameter_ids)),
                    species_ids=tuple(p.species_id for p in participants),
                    assumptions=(_IMPORTED_ASSUMPTION,),
                )
            )

        reactions.append(
            ReactionSpecification(
                reaction_id=r.getId(),
                name=r.getName() or r.getId(),
                participants=tuple(participants),
                reversible=r.getReversible() if r.isSetReversible() else None,
                kinetic_law_id=kinetic_law_id,
                assumptions=(_IMPORTED_ASSUMPTION,),
            )
        )
    return tuple(reactions), tuple(kinetic_laws)


def _parse_parameters(model: libsbml.Model) -> tuple[ParameterSpecification, ...]:
    parameters = []
    for i in range(model.getNumParameters()):
        p = model.getParameter(i)
        parameters.append(
            ParameterSpecification(
                parameter_id=p.getId(),
                name=p.getName() or p.getId(),
                source=ParameterSource.IMPORTED,
                value=_to_decimal(p.getValue()) if p.isSetValue() else None,
                unit=p.getUnits() or None,
                # SBML's own ``constant`` attribute means "never changed during simulation by a
                # rule/event" -- a different axis entirely from Agent 4's calibration ``fixed``
                # veto (never calibratable regardless of authorization). Conflating the two
                # would be inventing a mapping the source text never actually states; always
                # left unset.
                fixed=None,
                assumptions=(_IMPORTED_ASSUMPTION,),
            )
        )
    return tuple(parameters)


_RULE_TYPE_BY_SBML_TYPECODE = {
    libsbml.SBML_ASSIGNMENT_RULE: RuleType.ASSIGNMENT,
    libsbml.SBML_RATE_RULE: RuleType.RATE,
    libsbml.SBML_ALGEBRAIC_RULE: RuleType.ALGEBRAIC,
}


def _parse_rules(model: libsbml.Model) -> tuple[RuleSpecification, ...]:
    rules = []
    for i in range(model.getNumRules()):
        rule = model.getRule(i)
        rule_type = _RULE_TYPE_BY_SBML_TYPECODE.get(rule.getTypeCode())
        if rule_type is None:
            raise UnsupportedAntimonyConstructError(
                f"rule at index {i} has unrecognized SBML type code {rule.getTypeCode()!r}."
            )
        variable = rule.getVariable() if rule_type is not RuleType.ALGEBRAIC else None
        rules.append(
            RuleSpecification(
                rule_id=f"rule_{i}_{variable}" if variable else f"rule_{i}",
                rule_type=rule_type,
                formula=rule.getFormula(),
                variable=variable or None,
                assumptions=(_IMPORTED_ASSUMPTION,),
            )
        )
    return tuple(rules)


_OBSERVABLE_COMMENT_RE = re.compile(
    rf"^{re.escape(OBSERVABLE_COMMENT_PREFIX)} id=(?P<id>\S+) "
    r"name=(?P<name>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")(?: unit=(?P<unit>\S+))?\s*$"
)
_OBSERVABLE_RULE_LINE_RE = re.compile(r"^(?P<variable>\S+)\s*:=\s*.+;")


def _recover_observables_from_comments(
    antimony_text: str, rules: tuple[RuleSpecification, ...]
) -> tuple[tuple[RuleSpecification, ...], tuple[ObservableSpecification, ...]]:
    """Recover ``ObservableSpecification`` entries this repository's own exporter marked with
    ``OBSERVABLE_COMMENT_PREFIX`` (``app.agent2.antimony.generator``) -- see that constant's
    own docstring for the full round-trip rationale. Matches only this exporter's own output:
    arbitrary, externally-authored Antimony never carries this comment, so this is always a
    no-op (``observables=()``, every rule returned unchanged) for it.
    """
    lines = antimony_text.splitlines()
    observable_by_variable: dict[str, tuple[str, str, str | None]] = {}
    for i, line in enumerate(lines):
        comment_match = _OBSERVABLE_COMMENT_RE.match(line.strip())
        if comment_match is None or i == 0:
            continue
        rule_line_match = _OBSERVABLE_RULE_LINE_RE.match(lines[i - 1].strip())
        if rule_line_match is None:
            continue
        observable_by_variable[rule_line_match["variable"]] = (
            comment_match["id"],
            ast.literal_eval(comment_match["name"]),
            comment_match["unit"],
        )

    remaining_rules: list[RuleSpecification] = []
    observables: list[ObservableSpecification] = []
    for rule in rules:
        marker = observable_by_variable.get(rule.variable) if rule.variable else None
        if marker is not None and rule.rule_type is RuleType.ASSIGNMENT:
            observable_id, name, unit = marker
            observables.append(
                ObservableSpecification(
                    observable_id=observable_id,
                    name=name,
                    formula=rule.formula,
                    unit=unit,
                    assumptions=rule.assumptions,
                )
            )
        else:
            remaining_rules.append(rule)
    return tuple(remaining_rules), tuple(observables)


def _parse_events(model: libsbml.Model) -> tuple[EventSpecification, ...]:
    events = []
    for i in range(model.getNumEvents()):
        e = model.getEvent(i)
        trigger = e.getTrigger()
        trigger_formula = (
            libsbml.formulaToString(trigger.getMath()) if trigger is not None else None
        )
        if not trigger_formula:
            raise UnsupportedAntimonyConstructError(
                f"event {e.getId() or i!r} has no usable trigger expression."
            )
        assignments = []
        for j in range(e.getNumEventAssignments()):
            ea = e.getEventAssignment(j)
            assignments.append(
                EventAssignmentSpecification(
                    variable=ea.getVariable(), formula=libsbml.formulaToString(ea.getMath())
                )
            )
        delay = e.getDelay()
        priority = e.getPriority()
        events.append(
            EventSpecification(
                event_id=e.getId() or f"event_{i}",
                trigger_formula=trigger_formula,
                assignments=tuple(assignments),
                name=e.getName() or None,
                use_values_from_trigger_time=(
                    e.getUseValuesFromTriggerTime() if e.isSetUseValuesFromTriggerTime() else None
                ),
                delay_formula=(
                    libsbml.formulaToString(delay.getMath()) if delay is not None else None
                ),
                priority_formula=(
                    libsbml.formulaToString(priority.getMath()) if priority is not None else None
                ),
                assumptions=(_IMPORTED_ASSUMPTION,),
            )
        )
    return tuple(events)


def import_antimony(antimony_text: str) -> ModelSpecification:
    """Parse ``antimony_text`` (real Antimony source) into a canonical ``ModelSpecification``.

    Raises ``MalformedAntimonySourceError`` if libAntimony itself rejects the text (its own
    error message is preserved verbatim). Raises ``UnsupportedAntimonyConstructError`` if the
    text is valid Antimony but uses a construct this importer does not support (see module
    docstring). Never raises any other exception type for a well-formed-but-unsupported input.

    The returned model's ``source_type`` is always ``ModelSourceType.IMPORTED`` and
    ``source_provenance`` always carries ``antimony_text`` verbatim, a checksum of it, this
    package's own policy version, and the real library versions used -- see
    ``ModelSourceProvenance``.
    """
    if not antimony_text.strip():
        raise MalformedAntimonySourceError(
            "antimony_text must not be empty -- libAntimony itself accepts an empty/"
            "whitespace-only string as a trivially valid, content-free module, which this "
            "importer rejects explicitly rather than producing a ModelSpecification with no "
            "source_provenance.original_antimony_text to preserve."
        )
    antimony.clearPreviousLoads()
    load_result = antimony.loadAntimonyString(antimony_text)
    if load_result < 0:
        raise MalformedAntimonySourceError(antimony.getLastError())

    module_name = antimony.getMainModuleName()
    sbml_text = antimony.getSBMLString(module_name)
    document = libsbml.readSBMLFromString(sbml_text)
    for i in range(document.getNumErrors()):
        error = document.getError(i)
        if error.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
            raise MalformedAntimonySourceError(error.getMessage())

    model = document.getModel()
    if model is None:
        raise MalformedAntimonySourceError(
            "antimony compiled to SBML with no <model> element -- empty or header-only source."
        )

    _require_no_unsupported_constructs(model)

    compartments = _parse_compartments(model)
    species = _parse_species(model)
    parameters = _parse_parameters(model)
    parameter_ids = {p.parameter_id for p in parameters}
    reactions, kinetic_laws = _parse_reactions_and_laws(model, parameter_ids)
    rules, observables = _recover_observables_from_comments(antimony_text, _parse_rules(model))
    events = _parse_events(model)

    network = FullNetwork(
        network_id=f"network_{module_name}",
        name=module_name,
        compartments=compartments,
        species=species,
        reactions=reactions,
        assumptions=(_IMPORTED_ASSUMPTION,),
    )

    provenance = ModelSourceProvenance(
        original_antimony_text=antimony_text,
        checksum=hashlib.sha256(antimony_text.encode("utf-8")).hexdigest(),
        parser_version=f"{ANTIMONY_IMPORT_PARSER_VERSION}+{_library_versions()}",
        imported_at=datetime.now(UTC).isoformat(),
    )

    return ModelSpecification(
        model_id=f"imported_{module_name}_{uuid4().hex[:12]}",
        name=module_name,
        full_network=network,
        kinetic_laws=kinetic_laws,
        parameters=parameters,
        rules=rules,
        events=events,
        observables=observables,
        source_type=ModelSourceType.IMPORTED,
        source_provenance=provenance,
        assumptions=(_IMPORTED_ASSUMPTION,),
    )


__all__ = ["import_antimony"]
