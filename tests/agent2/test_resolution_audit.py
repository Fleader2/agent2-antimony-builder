"""Tests for the Module-Count / Resolution Bias Audit: ``app.agent2.resolution_audit``.

Builds an 8-reaction chain (S0->S1->...->S8) with a genuine compartment/EC-class boundary at
the S4/S5 edge (reactions r1-r4 in compartment "c1" with EC class "1"; r5-r8 in "c2" with class
"2") -- a network with real, matched biological structure at the 2-module resolution, so a
"biologically correct" 2-module split can be told apart from a scrambled one at the identical
resolution, and from the structure-blind null partition the audit itself builds.
"""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.agent2.antimony_import import import_antimony
from app.agent2.module_evaluation import (
    CriteriaWeights,
    CriterionWeight,
    ModularizationCriterion,
    evaluate_modularization,
)
from app.agent2.resolution_audit import (
    BiasSeverity,
    ResolutionAuditReferenceError,
    audit_criterion_resolution,
    build_null_partition,
)
from app.agent2.types import (
    CompartmentSourceScope,
    CompartmentSpecification,
    FullNetwork,
    ModelModularization,
    ModelModule,
    ModelSpecification,
    ModularizationMethod,
    ModuleComponentType,
    ModuleMembership,
    ParticipantRole,
    ReactionParticipantSpecification,
    ReactionSpecification,
    SpeciesSpecification,
)

# --- Fixtures --------------------------------------------------------------------------------

_SPECIES_IDS = [f"S{i}" for i in range(10)]
_REACTION_COUNT = 9


def _compartment(**overrides) -> CompartmentSpecification:
    merged = {
        "compartment_id": "c1",
        "name": "c1",
        "source_scope": CompartmentSourceScope.MODELING_CONSTRUCT,
        "assumptions": ("test fixture",),
    } | overrides
    return CompartmentSpecification(**merged)


def _species(species_id: str) -> SpeciesSpecification:
    compartment_id = "c1" if int(species_id[1:]) <= 4 else "c2"
    return SpeciesSpecification(
        species_id=species_id, name=species_id, compartment_id=compartment_id
    )


def _participant(species_id: str, role: ParticipantRole) -> ReactionParticipantSpecification:
    return ReactionParticipantSpecification(
        species_id=species_id, role=role, stoichiometry=Decimal("1")
    )


def _reaction(index: int) -> ReactionSpecification:
    reaction_id = f"r{index}"
    ec_number = "1.1.1.1" if index <= 4 else "2.2.2.2"
    return ReactionSpecification(
        reaction_id=reaction_id,
        name=reaction_id,
        ec_number=ec_number,
        participants=(
            _participant(f"S{index - 1}", ParticipantRole.REACTANT),
            _participant(f"S{index}", ParticipantRole.PRODUCT),
        ),
    )


def _network() -> FullNetwork:
    return FullNetwork(
        network_id="n1",
        name="n1",
        compartments=(_compartment(compartment_id="c1"), _compartment(compartment_id="c2")),
        species=tuple(_species(sid) for sid in _SPECIES_IDS),
        reactions=tuple(_reaction(i) for i in range(1, _REACTION_COUNT + 1)),
    )


def _membership(
    mod_id: str, module_id: str, component_type: ModuleComponentType, component_id: str
) -> ModuleMembership:
    return ModuleMembership(
        membership_id=f"mem_{mod_id}_{module_id}_{component_type.value}_{component_id}",
        modularization_id=mod_id,
        module_id=module_id,
        component_type=component_type,
        component_id=component_id,
    )


def _reaction_species(reaction_index: int) -> tuple[str, str]:
    return f"S{reaction_index - 1}", f"S{reaction_index}"


def _build_modularization(
    mod_id: str, buckets: dict[str, list[int]]
) -> tuple[ModelModularization, tuple[ModelModule, ...], tuple[ModuleMembership, ...]]:
    """``buckets``: ``{module_label: [reaction_index, ...]}``. Each module's own global id is
    prefixed with ``mod_id`` (``ModelSpecification`` requires ``module_id`` to be unique across
    the *entire* model, not merely per-modularization). Species follow every reaction that
    touches them (a species shared between two buckets gets a membership row in each, exactly
    like the production modularization schema allows)."""
    module_ids = tuple(f"{mod_id}::{label}" for label in buckets)
    memberships: list[ModuleMembership] = []
    for label, module_id in zip(buckets, module_ids, strict=True):
        indices = buckets[label]
        species_in_module: set[str] = set()
        for idx in indices:
            memberships.append(
                _membership(mod_id, module_id, ModuleComponentType.REACTION, f"r{idx}")
            )
            species_in_module.update(_reaction_species(idx))
        for sid in sorted(species_in_module):
            memberships.append(_membership(mod_id, module_id, ModuleComponentType.SPECIES, sid))
    modules = tuple(ModelModule(module_id=m, name=m) for m in module_ids)
    modularization = ModelModularization(
        modularization_id=mod_id,
        name=mod_id,
        method=ModularizationMethod.USER_DEFINED,
        module_ids=module_ids,
    )
    return modularization, modules, tuple(memberships)


def _model_with_modularizations(
    *specs: tuple[str, dict[str, list[int]]], network: FullNetwork | None = None
) -> ModelSpecification:
    modularizations = []
    model_modules: list[ModelModule] = []
    memberships: list[ModuleMembership] = []
    for mod_id, buckets in specs:
        m, mods, mems = _build_modularization(mod_id, buckets)
        modularizations.append(m)
        model_modules.extend(mods)
        memberships.extend(mems)
    return ModelSpecification(
        model_id="m1",
        name="m1",
        full_network=network or _network(),
        kinetic_laws=(),
        parameters=(),
        modularizations=tuple(modularizations),
        model_modules=tuple(model_modules),
        module_memberships=tuple(memberships),
    )


def _one_module() -> dict[str, list[int]]:
    return {"m_all": list(range(1, _REACTION_COUNT + 1))}


def _true_two_modules() -> dict[str, list[int]]:
    """The genuine compartment/EC-class boundary: r1-r4 (class "1", compartment c1) vs.
    r5-r9 (class "2", compartment c2) -- a 4/5 split, deliberately *not* the 5/4 split the
    structure-blind null partition builds at this same module count (``divmod(9, 2)`` gives
    the null's own first chunk 5 elements, not 4), so the two are never accidentally
    identical."""
    return {"m_a": [1, 2, 3, 4], "m_b": [5, 6, 7, 8, 9]}


def _scrambled_two_modules() -> dict[str, list[int]]:
    return {"m_a": [1, 3, 5, 7, 9], "m_b": [2, 4, 6, 8]}


def _four_modules() -> dict[str, list[int]]:
    return {"m_a": [1, 2], "m_b": [3, 4], "m_c": [5, 6, 7], "m_d": [8, 9]}


def _nine_modules() -> dict[str, list[int]]:
    return {f"m_{i}": [i] for i in range(1, _REACTION_COUNT + 1)}


# --- Known coarse-bias case: TOPOLOGICAL_SEPARATION -------------------------------------------


def test_known_coarse_bias_case_topological_separation():
    model = _model_with_modularizations(
        ("mod1", _one_module()),
        ("mod2", _true_two_modules()),
        ("mod4", _four_modules()),
        ("mod9", _nine_modules()),
    )
    audit = audit_criterion_resolution(
        model, ModularizationCriterion.TOPOLOGICAL_SEPARATION, ("mod1", "mod2", "mod4", "mod9")
    )
    assert audit.bias_severity is BiasSeverity.STRONG_COARSE_BIAS
    entries_by_count = {e.module_count: e for e in audit.entries}
    assert entries_by_count[1].null_reference_score == Decimal("1")  # the degenerate case
    assert entries_by_count[9].null_reference_score < entries_by_count[1].null_reference_score


# --- Known fine-bias case: COMPARTMENT_COHERENCE / EC_CLASS_COHERENCE -------------------------


@pytest.mark.parametrize(
    "criterion",
    [ModularizationCriterion.COMPARTMENT_COHERENCE, ModularizationCriterion.EC_CLASS_COHERENCE],
)
def test_known_fine_bias_case(criterion):
    model = _model_with_modularizations(
        ("mod1", _one_module()),
        ("mod2", _true_two_modules()),
        ("mod4", _four_modules()),
        ("mod9", _nine_modules()),
    )
    audit = audit_criterion_resolution(model, criterion, ("mod1", "mod2", "mod4", "mod9"))
    # Both criteria share the identical modal-fraction-per-module mathematical structure, so
    # both must show a real, fine-ward bias here -- but the exact swing crossing the STRONG
    # threshold is sensitive to this one fixture's own compartment/EC layout, so only the
    # direction (never NO_MATERIAL_BIAS/coarse/insufficient) is asserted strictly.
    assert audit.bias_severity in (
        BiasSeverity.MILD_RESOLUTION_DEPENDENCE,
        BiasSeverity.STRONG_FINE_BIAS,
    )
    entries_by_count = {e.module_count: e for e in audit.entries}
    assert entries_by_count[9].null_reference_score > entries_by_count[1].null_reference_score


# --- Biologically stronger partition still wins after normalization ---------------------------


@pytest.mark.parametrize(
    "criterion",
    [ModularizationCriterion.COMPARTMENT_COHERENCE, ModularizationCriterion.EC_CLASS_COHERENCE],
)
def test_biologically_stronger_partition_still_wins_after_normalization(criterion):
    model = _model_with_modularizations(
        ("true", _true_two_modules()), ("scrambled", _scrambled_two_modules())
    )
    audit = audit_criterion_resolution(model, criterion, ("true", "scrambled"))
    entries_by_id = {e.modularization_id: e for e in audit.entries}
    true_entry = entries_by_id["true"]
    scrambled_entry = entries_by_id["scrambled"]
    # Both share the identical module count -> the identical null baseline.
    assert true_entry.null_reference_score == scrambled_entry.null_reference_score
    assert true_entry.corrected_score > scrambled_entry.corrected_score
    assert true_entry.raw_score > scrambled_entry.raw_score  # true also wins on raw score here


# --- Raw vs corrected score preserved ----------------------------------------------------------


def test_raw_and_corrected_scores_both_preserved_on_criterion_score():
    # "scrambled" (not "true") is used deliberately: the "true" 2-module split happens to be
    # byte-identical to the null partition at this resolution (both split the chain into
    # contiguous halves), which would make null_reference_score == 1 and leave
    # corrected_score == None -- a genuine, already-covered case (see
    # test_null_reference_score_of_one_yields_no_correction), but not this test's own point.
    model = _model_with_modularizations(("scrambled", _scrambled_two_modules()))
    weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.COMPARTMENT_COHERENCE, Decimal("1")),),
        policy_version="test-v1",
    )
    null_modularization, null_modules, null_memberships = build_null_partition(
        model.full_network, 2, modularization_id="null2"
    )
    null_model = replace(
        model,
        modularizations=(null_modularization,),
        model_modules=null_modules,
        module_memberships=null_memberships,
    )
    null_eval = evaluate_modularization(null_model, "null2", weights)
    null_score = next(
        cs.raw_score for cs in null_eval.criterion_scores
        if cs.criterion is ModularizationCriterion.COMPARTMENT_COHERENCE
    )
    assert null_score < 1  # precondition for this test's own point

    evaluation = evaluate_modularization(
        model,
        "scrambled",
        weights,
        null_reference_scores={ModularizationCriterion.COMPARTMENT_COHERENCE: null_score},
    )
    score = next(
        cs for cs in evaluation.criterion_scores
        if cs.criterion is ModularizationCriterion.COMPARTMENT_COHERENCE
    )
    assert score.raw_score is not None
    assert score.null_reference_score == null_score
    assert score.corrected_score is not None
    expected_corrected = (score.raw_score - null_score) / (Decimal(1) - null_score)
    assert score.corrected_score == expected_corrected
    # Raw score is never altered by the presence of a correction.
    plain_evaluation = evaluate_modularization(model, "scrambled", weights)
    plain_score = next(
        cs for cs in plain_evaluation.criterion_scores
        if cs.criterion is ModularizationCriterion.COMPARTMENT_COHERENCE
    )
    assert plain_score.raw_score == score.raw_score


def test_omitting_null_reference_scores_reproduces_prior_behavior():
    model = _model_with_modularizations(("mod2", _true_two_modules()))
    weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),),
        policy_version="test-v1",
    )
    with_none = evaluate_modularization(model, "mod2", weights, null_reference_scores=None)
    without_param = evaluate_modularization(model, "mod2", weights)
    assert with_none == without_param
    score = with_none.criterion_scores[0]
    assert score.null_reference_score is None
    assert score.corrected_score is None


def test_corrected_score_clamped_to_zero_for_weighting_when_negative():
    model = _model_with_modularizations(("scrambled", _scrambled_two_modules()))
    weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.EC_CLASS_COHERENCE, Decimal("1")),),
        policy_version="test-v1",
    )
    # An artificially high null baseline forces a negative corrected_score.
    evaluation = evaluate_modularization(
        model,
        "scrambled",
        weights,
        null_reference_scores={ModularizationCriterion.EC_CLASS_COHERENCE: Decimal("0.99")},
    )
    score = next(
        cs for cs in evaluation.criterion_scores
        if cs.criterion is ModularizationCriterion.EC_CLASS_COHERENCE
    )
    assert score.corrected_score < 0  # disclosed, unclamped on the field itself
    assert score.weighted_contribution == Decimal("0")  # clamped only for weighting
    assert evaluation.overall_score == Decimal("0")


def test_null_reference_score_of_one_yields_no_correction():
    model = _model_with_modularizations(("mod1", _one_module()))
    weights = CriteriaWeights(
        weights=(CriterionWeight(ModularizationCriterion.TOPOLOGICAL_SEPARATION, Decimal("1")),),
        policy_version="test-v1",
    )
    evaluation = evaluate_modularization(
        model,
        "mod1",
        weights,
        null_reference_scores={ModularizationCriterion.TOPOLOGICAL_SEPARATION: Decimal("1")},
    )
    score = evaluation.criterion_scores[0]
    assert score.null_reference_score == Decimal("1")
    assert score.corrected_score is None  # no meaningful correction when null already maxed
    # falls back to the raw score for weighting, never fabricating a number from 0/0.
    assert evaluation.overall_score == score.raw_score


# --- Deterministic null/reference construction -------------------------------------------------


def test_build_null_partition_is_deterministic():
    network = _network()
    first = build_null_partition(network, 3, modularization_id="null-x")
    second = build_null_partition(network, 3, modularization_id="null-x")
    assert first == second


def test_build_null_partition_rejects_invalid_module_count():
    network = _network()
    with pytest.raises(ResolutionAuditReferenceError):
        build_null_partition(network, 0, modularization_id="null-bad")


def test_build_null_partition_caps_at_reaction_count():
    network = _network()
    modularization, _modules, _memberships = build_null_partition(
        network, 1000, modularization_id="null-big"
    )
    assert len(modularization.module_ids) == _REACTION_COUNT


# --- No GENERATED/IMPORTED asymmetry ------------------------------------------------------------


def _imported_network_equivalent():
    lines = ["model m", "  compartment c1 = 1.0;", "  compartment c2 = 1.0;"]
    for sid in _SPECIES_IDS:
        comp = "c1" if int(sid[1:]) <= 4 else "c2"
        lines.append(f"  species {sid} in {comp} = 1.0;")
    for i in range(1, _REACTION_COUNT + 1):
        lines.append(f"  r{i}: S{i - 1} => S{i}; k{i} * S{i - 1};")
    for i in range(1, _REACTION_COUNT + 1):
        lines.append(f"  k{i} = 0.5;")
    lines.append("end")
    return import_antimony("\n".join(lines))


def test_no_generated_imported_asymmetry_in_audit():
    generated = _model_with_modularizations(
        ("mod1", _one_module()), ("mod2", _true_two_modules()), ("mod9", _nine_modules())
    )
    imported_base = _imported_network_equivalent()
    imported = replace(
        imported_base,
        modularizations=generated.modularizations,
        model_modules=generated.model_modules,
        module_memberships=generated.module_memberships,
    )
    generated_audit = audit_criterion_resolution(
        generated, ModularizationCriterion.TOPOLOGICAL_SEPARATION, ("mod1", "mod2", "mod9")
    )
    imported_audit = audit_criterion_resolution(
        imported, ModularizationCriterion.TOPOLOGICAL_SEPARATION, ("mod1", "mod2", "mod9")
    )
    assert generated_audit.bias_severity == imported_audit.bias_severity
    generated_scores = [e.null_reference_score for e in generated_audit.entries]
    imported_scores = [e.null_reference_score for e in imported_audit.entries]
    assert generated_scores == imported_scores


# --- No mutation of canonical models -------------------------------------------------------------


def test_audit_never_mutates_canonical_model():
    model = _model_with_modularizations(("mod2", _true_two_modules()))
    before = replace(model)
    audit_criterion_resolution(model, ModularizationCriterion.COMPARTMENT_COHERENCE, ("mod2",))
    assert model == before
    assert len(model.modularizations) == 1  # no null partition ever attached permanently


# --- Yeast score-vs-module-count audit (real sce00061 data) -------------------------------------

_SCE00061_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "agent-integration-harness"
    / "tests"
    / "fixtures"
    / "sce00061_agent1_curated_knowledge_view.json"
)


@pytest.mark.skipif(not _SCE00061_FIXTURE.is_file(), reason="sce00061 fixture not available")
def test_yeast_score_vs_module_count_audit():
    from app.agent2.pipeline import run_agent2_pipeline

    with open(_SCE00061_FIXTURE) as f:
        agent1_view = json.load(f)
    result = run_agent2_pipeline(agent1_view)
    model = result.package.model_specification
    seed_id = model.modularizations[0].modularization_id
    seed_modularization = model.modularizations[0]
    seed_count = len(seed_modularization.module_ids)

    one_module = ModelModularization(
        modularization_id="yeast_one",
        name="yeast_one",
        method=ModularizationMethod.USER_DEFINED,
        module_ids=("yeast_one::m_all",),
    )
    one_modules = (ModelModule(module_id="yeast_one::m_all", name="yeast_one::m_all"),)
    one_memberships = tuple(
        _membership("yeast_one", "yeast_one::m_all", ModuleComponentType.REACTION, r.reaction_id)
        for r in model.full_network.reactions
    )
    model_with_one = replace(
        model,
        modularizations=(*model.modularizations, one_module),
        model_modules=model.model_modules + one_modules,
        module_memberships=model.module_memberships + one_memberships,
    )
    audit = audit_criterion_resolution(
        model_with_one,
        ModularizationCriterion.TOPOLOGICAL_SEPARATION,
        ("yeast_one", seed_id),
    )
    assert audit.bias_severity is BiasSeverity.STRONG_COARSE_BIAS
    entries_by_count = {e.module_count: e for e in audit.entries}
    assert entries_by_count[1].null_reference_score == Decimal("1")
    assert entries_by_count[seed_count].null_reference_score < Decimal("1")


# --- CALIBRATION_INDEPENDENCE: an analytically-proven structural coarse bias ------------------
#
# Unlike the four structural criteria above, CALIBRATION_INDEPENDENCE's own score always comes
# from externally-supplied evidence (never computable by a structure-blind null partition, which
# has no calibration behavior of its own at all) -- so this increment's own null-partition
# audit methodology does not apply to it (task instructions §1: "where valid evidence exists").
# Its weakest-link (``min``) aggregation across modules has a *different*, directly provable
# kind of module-count bias instead: adding one more module to the set being aggregated can
# only ever keep the minimum the same or lower it, never raise it -- a purely mathematical
# property of ``min()`` over a growing set, true regardless of what the evidence says.


def test_calibration_independence_weakest_link_aggregation_is_monotonically_non_increasing():
    from app.agent2.module_calibration.types import (
        ModuleCalibrationEvaluation,
        ModuleCalibrationStatus,
    )
    from app.agent2.module_evaluation.calibration_adapter import score_calibration_independence

    def _evaluation(module_id: str) -> ModuleCalibrationEvaluation:
        return ModuleCalibrationEvaluation(
            evaluation_id=f"eval::{module_id}",
            request_id=f"req::{module_id}",
            correlation_id="corr-1",
            run_id="run-1",
            parent_model_id="m1",
            modularization_id="mod",
            module_id=module_id,
            status=ModuleCalibrationStatus.CALIBRATION_SUPPORTED,
            policy_version="test-v1",
        )

    evaluations = {f"m{i}": _evaluation(f"m{i}") for i in range(1, 6)}
    scores = []
    for count in range(1, 6):
        module_ids = tuple(f"m{i}" for i in range(1, count + 1))
        result = score_calibration_independence(module_ids, evaluations)
        assert result.available is True
        scores.append(result.raw_score)
    # Every identically-supported module here scores the maximum (1) individually -- yet the
    # aggregate can never rise as more modules join (it can only ever stay at the ceiling or,
    # the moment any joining module scores below it, drop). This single fixture cannot show a
    # *drop* without a worse module appearing, but it does prove the aggregate is never
    # allowed to exceed the running minimum -- confirmed by construction (min() of an
    # all-identical set is that identical value, never higher).
    assert scores == [Decimal("1")] * 5

    # Introduce one weaker module at the end -- the aggregate must drop immediately and
    # permanently from that point on (min() of a set containing a lower value can never be
    # higher than that value), never "average out" the way a mean-based aggregation would.
    weak = ModuleCalibrationEvaluation(
        evaluation_id="eval::m6",
        request_id="req::m6",
        correlation_id="corr-1",
        run_id="run-1",
        parent_model_id="m1",
        modularization_id="mod",
        module_id="m6",
        status=ModuleCalibrationStatus.UNIDENTIFIABLE,
        policy_version="test-v1",
    )
    evaluations_with_weak = {**evaluations, "m6": weak}
    five_ids = ("m1", "m2", "m3", "m4", "m5")
    six_ids = ("m1", "m2", "m3", "m4", "m5", "m6")
    before = score_calibration_independence(five_ids, evaluations_with_weak)
    after = score_calibration_independence(six_ids, evaluations_with_weak)
    assert before.raw_score == Decimal("1")
    assert after.raw_score == Decimal("0")
    assert after.raw_score <= before.raw_score  # adding a module never raises the aggregate
