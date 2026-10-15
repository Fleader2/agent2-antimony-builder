"""Cross-artifact assembly and the public Increment 8 entry point.

``assemble_model_specification`` is this package's one public API: given
the validated outputs of every prior increment (``FullNetwork``,
``KineticLawAssignmentSet``, ``ParameterDeclarationSet``, optionally
``BoundaryAssessmentSet``/``ModuleDecompositionSet``), assembles one
authoritative ``ModelSpecification`` -- the complete, single source of
truth Increment 9 will serialize into Antimony. Pure and deterministic:
no database, no filesystem, no network access, no LLM, no simulation, no
fitting, no Antimony anywhere in its call graph. Never mutates any of its
inputs -- only reads them, and never recomputes a kinetic-law decision, a
parameter source, a boundary likelihood, or a module cut (Increment 8
instructions, §2: "assemble, not reinterpret").
"""

from __future__ import annotations

from app.agent2.boundaries.types import BoundaryAssessmentSet
from app.agent2.kinetics.types import KineticLawAssignment, KineticLawAssignmentSet
from app.agent2.model_specification.errors import (
    IncompatibleArtifactVersionError,
    ModelSpecificationReferenceError,
)
from app.agent2.model_specification.mapping import build_model_assumptions, materialize_kinetic_law
from app.agent2.model_specification.validation import (
    require_boundary_assessment_set,
    require_full_network,
    require_kinetic_law_assignment_set,
    require_module_decomposition_set,
    require_parameter_declaration_set,
)
from app.agent2.modularization.adapter import modularizations_from_decomposition_set
from app.agent2.modules.types import ModuleDecompositionSet
from app.agent2.parameters.types import ParameterDeclarationSet
from app.agent2.quantitative_context.types import QuantitativeContextResolutionSet
from app.agent2.types import (
    EnzymeConcentration,
    EnzymeStatePool,
    FullNetwork,
    KineticLawSpecification,
    ModelSpecification,
    ParameterSpecification,
)
from app.agent2.version import MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION


def assemble_model_specification(
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet | None = None,
    modules: ModuleDecompositionSet | None = None,
    enzyme_concentrations: QuantitativeContextResolutionSet | None = None,
    enzyme_state_pools: tuple[EnzymeStatePool, ...] = (),
    enzyme_state_concentrations: tuple[EnzymeConcentration, ...] = (),
) -> ModelSpecification:
    """Deterministically assemble one authoritative ``ModelSpecification`` from every prior
    increment's validated output.

    Answers only "what is the complete, internally consistent model
    Agent 2 has decided on so far" -- never "is this model biologically
    correct, numerically stable, or ready to simulate" (Agent 3/4/5's
    job). See ``docs/11_model_specification_assembly.md`` §2.

    **Module Decomposition/Modularization Reconciliation increment.** ``boundaries``/
    ``modules`` are now optional (default ``None``) -- modularization is never mandatory for
    a model of either ``source_type`` (task instructions §1). When supplied, ``modules`` may
    carry zero, one, or many ``ModuleDecomposition`` records (the pre-existing
    ``_require_exactly_one_decomposition`` hard check is removed); each is converted via
    ``app.agent2.modularization.adapter.modularizations_from_decomposition_set`` into its own
    ``ModelModularization`` (plus that modularization's own modules/memberships/ports) and
    attached to ``ModelSpecification.modularizations``/``.model_modules``/
    ``.module_memberships``/``.module_ports`` -- the one, unified, stored module-related
    representation; the old ``ModuleDecomposition``/``ModuleSpecification`` objects
    themselves are never stored directly (``ModelSpecification`` no longer carries
    ``module_decomposition``/``module_specifications``/``boundary_assessments`` at all).
    Supplying ``modules`` without ``boundaries`` (or vice versa) is rejected -- the heuristic
    algorithm's own cross-artifact policy-version check (§ below) requires both together.

    ``enzyme_concentrations`` (Quantitative Context Resolution and Derived Enzyme
    Concentration increment) is optional and defaults to ``None`` -- every existing
    call site continues to construct an identical ``ModelSpecification``
    (``enzyme_concentrations=()``, no additional ``ModelAssumption`` records) with
    no change at all. When supplied, its own ``network_id`` is cross-checked against
    ``network.network_id`` (mirroring ``_require_matching_networks``'s identical
    convention for every other artifact), its ``.enzyme_concentrations`` are
    attached verbatim, and one additional ``ModelAssumption`` category is generated
    for every protein whose concentration used the 0.1 pL reference assumption (see
    ``build_model_assumptions``'s own docstring).

    ``enzyme_state_pools``/``enzyme_state_concentrations`` (Multi-Context Catalytic Rate
    Composition increment, Stage 2) are optional and default to ``()`` -- every existing
    call site continues to construct an identical ``ModelSpecification``. When supplied
    (``app.agent2.enzyme_state_dynamics``'s own output), they are attached verbatim to
    ``ModelSpecification.enzyme_state_pools``/``.enzyme_state_concentrations``, and one
    additional ``ModelAssumption`` is generated per pool (see ``build_model_assumptions``).
    ``network`` must already be the *augmented* network (``EnzymeStateDynamicsResult
    .network``) whenever ``enzyme_state_pools`` is non-empty -- this function performs no
    augmentation of its own.

    **Explicit Enzyme Concentration Representation increment.** ``network`` should likewise
    already be the enzyme-concentration-species-augmented network
    (``EnzymeConcentrationSpeciesResult.network``) whenever a ``MICHAELIS_MENTEN`` kinetic
    law's own catalytic context is expected to resolve an explicit enzyme species -- this
    function derives its own ``{(protein_id, compartment_id): species_id}`` lookup directly
    from ``network.species`` (never a separately-threaded parameter) and passes it to
    ``materialize_kinetic_law`` for every assignment. Omitted (no enzyme species in
    ``network.species``), the lookup is simply empty and every kinetic law stays
    ``LUMPED_EFFECTIVE_RATE`` -- identical to this function's own pre-increment behavior.
    """
    require_full_network(network)
    require_kinetic_law_assignment_set(kinetic_laws)
    require_parameter_declaration_set(parameters)
    if (boundaries is None) != (modules is None):
        raise ModelSpecificationReferenceError(
            "assemble_model_specification requires boundaries and modules together, or "
            f"neither -- got boundaries={boundaries!r}, modules={modules!r}"
        )
    if boundaries is not None:
        require_boundary_assessment_set(boundaries)
    if modules is not None:
        require_module_decomposition_set(modules)
    if enzyme_concentrations is not None and not isinstance(
        enzyme_concentrations, QuantitativeContextResolutionSet
    ):
        raise ModelSpecificationReferenceError(
            "assemble_model_specification requires enzyme_concentrations to be a "
            f"QuantitativeContextResolutionSet or None, got {enzyme_concentrations!r}"
        )
    if (
        enzyme_concentrations is not None
        and enzyme_concentrations.network_id != network.network_id
    ):
        raise IncompatibleArtifactVersionError(
            f"enzyme_concentrations.network_id ({enzyme_concentrations.network_id!r}) does "
            f"not match network.network_id ({network.network_id!r})"
        )

    if modules is not None:
        _require_matching_networks(network, kinetic_laws, parameters, boundaries, modules)
        _require_compatible_policy_versions(kinetic_laws, parameters, boundaries, modules)
        decompositions = modules.decompositions
    else:
        decompositions = ()

    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    parameters_by_assignment_id: dict[str, list[ParameterSpecification]] = {}
    for spec in parameters.parameter_specifications:
        if spec.kinetic_law_assignment_id is not None:
            parameters_by_assignment_id.setdefault(spec.kinetic_law_assignment_id, []).append(spec)

    # Explicit Enzyme Concentration Representation increment: derived directly from
    # ``network.species`` -- never a second, separately-threaded parameter that could drift
    # out of sync with it. ``network`` must already be the *enzyme-concentration-species-
    # augmented* network (``EnzymeConcentrationSpeciesResult.network``) whenever an explicit
    # enzyme species is expected to be injectable here; this function performs no
    # augmentation of its own (mirrors the identical, pre-existing contract for
    # ``enzyme_state_pools``/the enzyme-state-augmented network, above).
    enzyme_species_lookup = {
        (species.source_protein_id, species.compartment_id): species.species_id
        for species in network.species
        if species.source_protein_id is not None
    }
    species_by_id = {species.species_id: species for species in network.species}

    kinetic_law_specs: list[KineticLawSpecification] = []
    kinetic_law_assignments_by_kinetic_law_id: dict[str, KineticLawAssignment] = {}
    for assignment in sorted(kinetic_laws.assignments, key=lambda a: a.assignment_id):
        reaction = reactions_by_id.get(assignment.reaction_id)
        if reaction is None:
            raise ModelSpecificationReferenceError(
                f"kinetic-law assignment {assignment.assignment_id!r} references unknown "
                f"reaction {assignment.reaction_id!r}"
            )
        law_parameters = tuple(parameters_by_assignment_id.get(assignment.assignment_id, ()))
        law = materialize_kinetic_law(
            assignment,
            reaction=reaction,
            law_parameters=law_parameters,
            enzyme_species_lookup=enzyme_species_lookup,
            species_by_id=species_by_id,
        )
        kinetic_law_specs.append(law)
        kinetic_law_assignments_by_kinetic_law_id[law.kinetic_law_id] = assignment

    resolved_enzyme_concentrations = (
        enzyme_concentrations.enzyme_concentrations if enzyme_concentrations is not None else ()
    )
    # Union across every decomposition supplied (0, 1, or many -- never assuming exactly one):
    # every MEDIUM boundary any of them preserved, rather than cut, as a candidate.
    candidate_boundary_ids = tuple(
        sorted({bid for d in decompositions for bid in d.candidate_boundary_ids})
    )
    model_assumptions = build_model_assumptions(
        kinetic_laws=tuple(kinetic_law_specs),
        kinetic_law_assignments_by_kinetic_law_id=kinetic_law_assignments_by_kinetic_law_id,
        parameters=parameters.parameter_specifications,
        candidate_boundary_ids=candidate_boundary_ids,
        kinetic_measurements=network.kinetic_measurements,
        reactions=network.reactions,
        enzyme_concentrations=resolved_enzyme_concentrations,
        microscopic_constraints=parameters.microscopic_constraints,
        enzyme_state_pools=enzyme_state_pools,
    )

    model_id = f"model::{network.network_id}"
    provenance_refs = (
        *network.provenance_refs,
        *(f"module-decomposition::{d.decomposition_id}" for d in decompositions),
        f"model-specification-policy::{MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION}",
    )
    assumptions = (
        "Increment 8 assembly policy: kinetic-law assignments and parameter declarations are "
        "assembled verbatim -- no kinetic-law type or parameter source is recomputed or "
        "reinterpreted here. Module Decomposition/Modularization Reconciliation increment: "
        "when supplied, every module decomposition's own boundary likelihood/module cut is "
        "likewise assembled verbatim, converted into the unified ModelModularization "
        "representation, never reinterpreted.",
    )

    bundle = modularizations_from_decomposition_set(modules) if modules is not None else None

    model_specification = ModelSpecification(
        model_id=model_id,
        name=f"Model for {network.name}",
        full_network=network,
        organism_id=network.organism_id,
        kinetic_laws=tuple(kinetic_law_specs),
        parameters=parameters.parameter_specifications,
        assumptions=assumptions,
        model_assumptions=model_assumptions,
        enzyme_concentrations=resolved_enzyme_concentrations,
        enzyme_state_pools=enzyme_state_pools,
        enzyme_state_concentrations=enzyme_state_concentrations,
        modularizations=bundle.modularizations if bundle is not None else (),
        model_modules=bundle.model_modules if bundle is not None else (),
        module_memberships=bundle.module_memberships if bundle is not None else (),
        module_ports=bundle.module_ports if bundle is not None else (),
        provenance_refs=provenance_refs,
    )

    _validate_cross_artifact_references(model_specification, kinetic_laws=kinetic_laws)
    if modules is not None:
        _validate_module_kinetic_law_assignment_references(modules, kinetic_laws=kinetic_laws)
    return model_specification


def _require_matching_networks(
    network: FullNetwork,
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet,
    modules: ModuleDecompositionSet,
) -> None:
    for label, other_network_id in (
        ("kinetic_laws", kinetic_laws.network_id),
        ("parameters", parameters.network_id),
        ("boundaries", boundaries.network_id),
        ("modules", modules.network_id),
    ):
        if other_network_id != network.network_id:
            raise IncompatibleArtifactVersionError(
                f"{label}.network_id ({other_network_id!r}) does not match "
                f"network.network_id ({network.network_id!r})"
            )


def _require_compatible_policy_versions(
    kinetic_laws: KineticLawAssignmentSet,
    parameters: ParameterDeclarationSet,
    boundaries: BoundaryAssessmentSet,
    modules: ModuleDecompositionSet,
) -> None:
    """Cross-checks every shared policy-version field two artifacts both carry (Increment 8
    instructions, Step 21). ``characterization_policy_version`` (also carried by
    ``BoundaryAssessmentSet``) has no second artifact to compare it against here --
    ``NetworkCharacterization`` itself is not an Increment 8 input -- so it is preserved,
    never actively cross-checked; see docs/11 §18 for that disclosed limitation."""
    if parameters.kinetic_law_policy_version != kinetic_laws.kinetic_law_policy_version:
        raise IncompatibleArtifactVersionError(
            "parameters.kinetic_law_policy_version "
            f"({parameters.kinetic_law_policy_version!r}) does not match "
            f"kinetic_laws.kinetic_law_policy_version ({kinetic_laws.kinetic_law_policy_version!r})"
        )
    if boundaries.kinetic_law_policy_version != kinetic_laws.kinetic_law_policy_version:
        raise IncompatibleArtifactVersionError(
            "boundaries.kinetic_law_policy_version "
            f"({boundaries.kinetic_law_policy_version!r}) does not match "
            f"kinetic_laws.kinetic_law_policy_version ({kinetic_laws.kinetic_law_policy_version!r})"
        )
    if boundaries.parameter_policy_version != parameters.parameter_policy_version:
        raise IncompatibleArtifactVersionError(
            f"boundaries.parameter_policy_version ({boundaries.parameter_policy_version!r}) "
            f"does not match parameters.parameter_policy_version "
            f"({parameters.parameter_policy_version!r})"
        )
    if modules.boundary_policy_version != boundaries.boundary_policy_version:
        raise IncompatibleArtifactVersionError(
            f"modules.boundary_policy_version ({modules.boundary_policy_version!r}) does not "
            f"match boundaries.boundary_policy_version ({boundaries.boundary_policy_version!r})"
        )


def _validate_cross_artifact_references(
    model_specification: ModelSpecification,
    *,
    kinetic_laws: KineticLawAssignmentSet,
) -> None:
    """Defensive backstop for the one cross-reference ``ModelSpecification``'s own
    construction-time validation cannot check (it carries no ``KineticLawAssignment`` registry
    to check the ``assignment_id`` namespace against -- see that type's own docstring note and
    ``docs/11_model_specification_assembly.md`` §19): every declared parameter's
    ``kinetic_law_assignment_id`` must resolve against the real, original
    ``KineticLawAssignmentSet``. Should never trigger given a correct implementation -- mirrors
    the identical post-construction pattern already established in
    ``app.agent2.boundaries``/``app.agent2.kinetics``/``app.agent2.parameters``/
    ``app.agent2.modules``.
    """
    assignment_ids = {a.assignment_id for a in kinetic_laws.assignments}

    for spec in model_specification.parameters:
        if (
            spec.kinetic_law_assignment_id is not None
            and spec.kinetic_law_assignment_id not in assignment_ids
        ):
            raise ModelSpecificationReferenceError(
                f"parameter {spec.parameter_id!r} references unknown kinetic_law_assignment_id "
                f"{spec.kinetic_law_assignment_id!r}"
            )

    # Step 22's "every final kinetic law maps to the expected assignment": trivially true by
    # construction (materialize_kinetic_law derives kinetic_law_id deterministically from the
    # assignment it was built from), re-checked here for the same defensive-backstop reasons.
    for law in model_specification.kinetic_laws:
        assignment_id = law.kinetic_law_id.removeprefix("kinetic-law::")
        if assignment_id not in assignment_ids:
            raise ModelSpecificationReferenceError(
                f"kinetic law {law.kinetic_law_id!r} does not map to any known "
                "KineticLawAssignment"
            )


def _validate_module_kinetic_law_assignment_references(
    modules: ModuleDecompositionSet,
    *,
    kinetic_laws: KineticLawAssignmentSet,
) -> None:
    """Every ``ModuleSpecification.kinetic_law_assignment_ids`` (the heuristic decomposition
    algorithm's own intermediate output -- never stored on ``ModelSpecification`` itself,
    see that type's own docstring) must resolve against the real, original
    ``KineticLawAssignmentSet``. Should never trigger given a correct implementation."""
    assignment_ids = {a.assignment_id for a in kinetic_laws.assignments}
    for module in modules.module_specifications:
        unknown = sorted(set(module.kinetic_law_assignment_ids) - assignment_ids)
        if unknown:
            raise ModelSpecificationReferenceError(
                f"module {module.module_id!r}.kinetic_law_assignment_ids references unknown "
                f"id(s): {unknown}"
            )


__all__ = ["assemble_model_specification"]
