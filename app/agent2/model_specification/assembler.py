"""Cross-artifact assembly and the public Increment 8 entry point.

``assemble_model_specification`` is this package's one public API: given
the validated outputs of every prior increment (``FullNetwork``,
``KineticLawAssignmentSet``, ``ParameterDeclarationSet``,
``BoundaryAssessmentSet``, ``ModuleDecompositionSet``), assembles one
authoritative ``ModelSpecification`` -- the complete, single source of
truth Increment 9 will serialize into Antimony. Pure and deterministic:
no database, no filesystem, no network access, no LLM, no simulation, no
fitting, no Antimony anywhere in its call graph. Never mutates any of its
five inputs -- only reads them, and never recomputes a kinetic-law
decision, a parameter source, a boundary likelihood, or a module cut
(Increment 8 instructions, §2: "assemble, not reinterpret").
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
    boundaries: BoundaryAssessmentSet,
    modules: ModuleDecompositionSet,
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
    """
    require_full_network(network)
    require_kinetic_law_assignment_set(kinetic_laws)
    require_parameter_declaration_set(parameters)
    require_boundary_assessment_set(boundaries)
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

    _require_matching_networks(network, kinetic_laws, parameters, boundaries, modules)
    _require_compatible_policy_versions(kinetic_laws, parameters, boundaries, modules)
    decomposition = _require_exactly_one_decomposition(modules)

    reactions_by_id = {r.reaction_id: r for r in network.reactions}
    parameters_by_assignment_id: dict[str, list[ParameterSpecification]] = {}
    for spec in parameters.parameter_specifications:
        if spec.kinetic_law_assignment_id is not None:
            parameters_by_assignment_id.setdefault(spec.kinetic_law_assignment_id, []).append(spec)

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
        law = materialize_kinetic_law(assignment, reaction=reaction, law_parameters=law_parameters)
        kinetic_law_specs.append(law)
        kinetic_law_assignments_by_kinetic_law_id[law.kinetic_law_id] = assignment

    resolved_enzyme_concentrations = (
        enzyme_concentrations.enzyme_concentrations if enzyme_concentrations is not None else ()
    )
    model_assumptions = build_model_assumptions(
        kinetic_laws=tuple(kinetic_law_specs),
        kinetic_law_assignments_by_kinetic_law_id=kinetic_law_assignments_by_kinetic_law_id,
        parameters=parameters.parameter_specifications,
        candidate_boundary_ids=decomposition.candidate_boundary_ids,
        kinetic_measurements=network.kinetic_measurements,
        reactions=network.reactions,
        enzyme_concentrations=resolved_enzyme_concentrations,
        microscopic_constraints=parameters.microscopic_constraints,
        enzyme_state_pools=enzyme_state_pools,
    )

    model_id = f"model::{network.network_id}::{decomposition.decomposition_id}"
    provenance_refs = (
        *network.provenance_refs,
        f"module-decomposition::{decomposition.decomposition_id}",
        f"model-specification-policy::{MODEL_SPECIFICATION_ASSEMBLY_POLICY_VERSION}",
    )
    assumptions = (
        "Increment 8 assembly policy: kinetic-law assignments, parameter declarations, "
        "boundary assessments, and the module decomposition are assembled verbatim -- no "
        "kinetic-law type, parameter source, boundary likelihood, or module cut is "
        "recomputed or reinterpreted here.",
    )

    model_specification = ModelSpecification(
        model_id=model_id,
        name=f"Model for {network.name}",
        full_network=network,
        organism_id=network.organism_id,
        kinetic_laws=tuple(kinetic_law_specs),
        parameters=parameters.parameter_specifications,
        boundary_assessments=boundaries.assessments,
        module_decomposition=decomposition,
        module_specifications=modules.module_specifications,
        assumptions=assumptions,
        model_assumptions=model_assumptions,
        enzyme_concentrations=resolved_enzyme_concentrations,
        enzyme_state_pools=enzyme_state_pools,
        enzyme_state_concentrations=enzyme_state_concentrations,
        provenance_refs=provenance_refs,
    )

    _validate_cross_artifact_references(
        model_specification, kinetic_laws=kinetic_laws, modules=modules
    )
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


def _require_exactly_one_decomposition(modules: ModuleDecompositionSet):
    if len(modules.decompositions) != 1:
        raise ModelSpecificationReferenceError(
            "assemble_model_specification requires exactly one ModuleDecomposition under the "
            f"current v1 decomposition policy, got {len(modules.decompositions)}"
        )
    return modules.decompositions[0]


def _validate_cross_artifact_references(
    model_specification: ModelSpecification,
    *,
    kinetic_laws: KineticLawAssignmentSet,
    modules: ModuleDecompositionSet,
) -> None:
    """Defensive backstop for the two cross-references ``ModelSpecification``'s own
    construction-time validation cannot check (it carries no ``KineticLawAssignment`` registry
    to check the ``assignment_id`` namespace against -- see that type's own docstring note and
    ``docs/11_model_specification_assembly.md`` §19): every declared parameter's
    ``kinetic_law_assignment_id``, and every module's ``kinetic_law_assignment_ids``, must
    resolve against the real, original ``KineticLawAssignmentSet``. Should never trigger given
    a correct implementation -- mirrors the identical post-construction pattern already
    established in ``app.agent2.boundaries``/``app.agent2.kinetics``/``app.agent2.parameters``/
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

    for module in modules.module_specifications:
        unknown = sorted(set(module.kinetic_law_assignment_ids) - assignment_ids)
        if unknown:
            raise ModelSpecificationReferenceError(
                f"module {module.module_id!r}.kinetic_law_assignment_ids references unknown "
                f"id(s): {unknown}"
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


__all__ = ["assemble_model_specification"]
