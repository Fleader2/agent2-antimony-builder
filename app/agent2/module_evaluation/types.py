"""Module Boundary Evaluation Framework domain model.

**Scientific principle** (task's own explicit requirement, documented here verbatim since
every type below exists to operationalize it): *module mechanisms are evidence;
functional/contextual independence is the eventual target property.* Topology, compartment
membership, pathway annotations, regulation, dynamics, calibration behavior, etc. are
criteria contributing evidence for modularity -- none of them individually *defines* it.
``ModularizationCriterion`` is deliberately a flat, equally-weighted-by-default vocabulary of
independent evidence signals, never a single mechanism elevated to ground truth.

None of these types are ever stored on ``ModelSpecification`` -- an evaluation is always a
derived, on-demand analysis of an existing ``ModelModularization``, exactly like
``app.agent2.modularization.derivation.ModuleConnection`` is "always computed, never
persisted." This package also never alters executable whole-network semantics or
standalone-module generation (``app.agent2.antimony.generate_antimony``/
``.generate_module_artifacts`` are untouched and not imported here).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# --- Local validation helpers (mirrors the identical pattern already used in
# app.agent2.boundaries.types / app.agent2.modules.types / app.agent2.kinetics.types) ------------


def _require_non_empty_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string, got {value!r}")
    return value


def _require_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a tuple of str, got {value!r}")
    return value


def _require_tuple_of(value: object, item_type: type, *, field_name: str) -> tuple:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise TypeError(f"{field_name} must be a tuple of {item_type.__name__}, got {value!r}")
    return value


def _require_unit_interval(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal, got {value!r}")
    if value < 0 or value > 1:
        raise ValueError(f"{field_name} must be within [0, 1], got {value!r}")
    return value


class ModularizationCriterion(StrEnum):
    """One independently-inspectable evidence signal a ``ModularizationEvaluation`` scores.
    Mirrors ``ModularizationMethod``'s own closed-enum-with-reserved-future-members
    convention (``docs/22_model_modularization.md`` §2): a stable, closed vocabulary from the
    start, so a future increment adding a new producer never requires revisiting every
    already-stored evaluation's own scored-criterion set.

    Only the first four have a real producer today (``app.agent2.module_evaluation.criteria``)
    -- currently supportable from Agent 2/canonical-model information alone, per this
    increment's own scope. The remaining six are reserved vocabulary for future increments
    this task explicitly excludes from this one: genuine pathway/network membership, Agent 3
    dynamic isolation, sensitivity coherence, Agent 4 calibration independence/
    identifiability, regulatory coherence, and Agent 5 experimental validation. A future
    increment implementing one of these needs no interface change -- it only adds its own
    scoring function to ``criteria.py`` and extends the one dispatch table there.

    **Naming correction (Topology Hub/Currency Component Filtering's own corrective
    follow-up increment).** A prior increment's own ``PATHWAY_ANNOTATION_COHERENCE`` member
    was a misnomer: its one implemented producer never read genuine pathway/network
    membership data at all (Agent 1's own curated KEGG ``CuratedNetwork``/pathway data is not
    wired into Agent 2 today) -- it matched curated EC-number top-level classes only, a
    narrower, real, but differently-named signal. That member is renamed ``EC_CLASS_COHERENCE``
    (scoring formula and behavior exactly preserved, see ``criteria.score_ec_class_coherence``);
    ``PATHWAY_ANNOTATION_COHERENCE`` is re-declared below as a genuinely reserved, unimplemented
    member for the real pathway-membership signal, so a future increment that wires in that
    data never needs another conceptual rename.
    """

    #: Do module boundaries cut few of the network's own natural reaction-adjacency edges,
    #: relative to how many they keep internal? (app.agent2.module_evaluation.criteria
    #: .score_topological_separation)
    TOPOLOGICAL_SEPARATION = "TOPOLOGICAL_SEPARATION"
    #: How sparse is the *explicitly declared* cross-module interface surface (ModulePort),
    #: relative to each module's own total species membership? (.score_boundary_sparsity)
    BOUNDARY_SPARSITY = "BOUNDARY_SPARSITY"
    #: Does each module's own species membership concentrate in one compartment, or span many?
    #: (.score_compartment_coherence)
    COMPARTMENT_COHERENCE = "COMPARTMENT_COHERENCE"
    #: Do a module's own reactions share a consistent curated EC-number top-level class --
    #: the one functional-annotation signal Agent 2 already carries. Unavailable whenever no
    #: reaction in a modularization carries any EC number at all -- "where available," never
    #: fabricated. **Not** genuine pathway/network membership -- see
    #: ``PATHWAY_ANNOTATION_COHERENCE`` below for that, still-reserved, signal.
    #: (.score_ec_class_coherence)
    EC_CLASS_COHERENCE = "EC_CLASS_COHERENCE"
    #: Reserved: genuine pathway/network membership coherence, once Agent 1's own curated KEGG
    #: ``CuratedNetwork``/pathway data (``networks``/``network_pathways`` on
    #: ``Agent1KnowledgePackage``) is wired into Agent 2's ``FullNetwork``. No producer in this
    #: codebase today -- never conflate with ``EC_CLASS_COHERENCE`` above, which is a
    #: differently-scoped, already-implemented proxy signal.
    PATHWAY_ANNOTATION_COHERENCE = "PATHWAY_ANNOTATION_COHERENCE"
    #: Reserved: Agent 3's own dynamic-isolation analysis (e.g. relaxation-time separation
    #: between modules). No producer in this codebase today.
    DYNAMIC_ISOLATION = "DYNAMIC_ISOLATION"
    #: Reserved: sensitivity-coherence (do a module's own parameters dominate its own outputs'
    #: sensitivity, with little cross-module sensitivity leakage). No producer today.
    SENSITIVITY_COHERENCE = "SENSITIVITY_COHERENCE"
    #: Reserved: Agent 4's own calibration independence/practical identifiability across
    #: modules. No producer today.
    CALIBRATION_INDEPENDENCE = "CALIBRATION_INDEPENDENCE"
    #: Reserved: regulatory coherence (do regulatory interactions stay within, rather than
    #: cross, module boundaries). No producer today.
    REGULATORY_COHERENCE = "REGULATORY_COHERENCE"
    #: Reserved: Agent 5's own experimental-validation evidence for a proposed module boundary.
    #: No producer today.
    EXPERIMENTAL_VALIDATION = "EXPERIMENTAL_VALIDATION"


@dataclass(frozen=True, slots=True)
class CriterionWeight:
    """One criterion's own raw, user/configuration-supplied weight -- never normalized here
    (``CriteriaWeights`` does that deterministically, once, for the whole vector). A weight of
    exactly ``0`` is a valid, explicit way to disable a criterion (task instructions §3);
    omitting a criterion entirely from a ``CriteriaWeights.weights`` tuple means exactly the
    same thing (see that type's own ``raw_weight``/``normalized_weight`` methods)."""

    criterion: ModularizationCriterion
    weight: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, ModularizationCriterion):
            raise TypeError(
                f"CriterionWeight.criterion must be a ModularizationCriterion, got "
                f"{self.criterion!r}"
            )
        if not isinstance(self.weight, Decimal):
            raise TypeError(f"CriterionWeight.weight must be a Decimal, got {self.weight!r}")
        if self.weight < 0:
            raise ValueError(f"CriterionWeight.weight must be >= 0, got {self.weight!r}")


@dataclass(frozen=True, slots=True)
class CriteriaWeights:
    """One complete, deterministic weighting over ``ModularizationCriterion`` -- the task's
    own "explicit criteria-weight object" (§3).

    Deterministic normalization: a criterion's own ``normalized_weight`` is its raw weight
    divided by the sum of every *positive* raw weight in this vector -- so every nonzero-weight
    criterion's own normalized weight always sums to exactly ``1`` across the vector, and a
    zero-weight (or omitted) criterion always normalizes to exactly ``0`` ("zero weight
    disables a criterion," task §3). Comparing the identical modularization under several
    distinct ``CriteriaWeights`` instances (task §5, weight-space exploration) is simply
    calling ``evaluate_modularization`` once per instance -- this type carries no mutable or
    cached state of its own.

    At least one positive weight is required: an all-zero vector carries no comparative
    information at all and is rejected at construction, never silently producing a
    meaningless, undefined-everywhere evaluation.
    """

    weights: tuple[CriterionWeight, ...]
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "weights", _require_tuple_of(self.weights, CriterionWeight, field_name="weights")
        )
        seen: set[ModularizationCriterion] = set()
        duplicates: set[ModularizationCriterion] = set()
        for w in self.weights:
            if w.criterion in seen:
                duplicates.add(w.criterion)
            seen.add(w.criterion)
        if duplicates:
            raise ValueError(
                f"CriteriaWeights.weights must name each criterion at most once, found "
                f"duplicate(s): {sorted(c.value for c in duplicates)}"
            )
        if not any(w.weight > 0 for w in self.weights):
            raise ValueError(
                "CriteriaWeights requires at least one positive weight -- an all-zero (or "
                "empty) vector carries no comparative information"
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )

    def raw_weight(self, criterion: ModularizationCriterion) -> Decimal:
        """This criterion's own raw weight, or ``Decimal(0)`` when omitted -- omission and an
        explicit ``weight=0`` are indistinguishable from here on, by design."""
        for w in self.weights:
            if w.criterion is criterion:
                return w.weight
        return Decimal(0)

    def normalized_weight(self, criterion: ModularizationCriterion) -> Decimal:
        """This criterion's own deterministic share of the total positive weight -- always
        ``0`` for a zero/omitted criterion, always sums to ``1`` across every positive-weight
        criterion in this vector."""
        raw = self.raw_weight(criterion)
        if raw <= 0:
            return Decimal(0)
        total = sum((w.weight for w in self.weights if w.weight > 0), Decimal(0))
        return raw / total


class TopologyRole(StrEnum):
    """One species' own role for ``TOPOLOGICAL_SEPARATION`` filtering only (Topology
    Hub/Currency Component Filtering increment) -- never visible to, or affecting, any other
    criterion. A role's own *default* weight is a policy choice
    (``app.agent2.module_evaluation.criteria.DEFAULT_TOPOLOGY_ROLE_WEIGHT``), never hard-coded
    into this enum itself.
    """

    #: Full, unfiltered contribution -- the default for every species with no curated-default
    #: match and no caller override.
    NORMAL = "NORMAL"
    #: A near-universal "currency" metabolite (ATP/ADP, water, protons, phosphate, ...) whose
    #: sharing between two reactions carries essentially no pathway-specific information.
    #: Hard-excluded (weight 0) by default.
    UNIVERSAL_CURRENCY = "UNIVERSAL_CURRENCY"
    #: A common redox/acyl-carrier cofactor (NAD(H), NADP(H), CoA, FAD, ...) -- less universal
    #: than a currency metabolite (its identity can genuinely matter, e.g. a redox-pathway
    #: distinction), down-weighted rather than hard-excluded by default.
    COFACTOR = "COFACTOR"
    #: A highly-reused adaptor/scaffold species (e.g. 14-3-3) -- context-dependent by nature
    #: (task instructions: "when contextually appropriate"). Never auto-detected by this
    #: package; only ever assigned by an explicit curated/per-evaluation override.
    GENERIC_ADAPTOR = "GENERIC_ADAPTOR"
    #: A species an explicit override declares hub-like for this one evaluation -- never
    #: assigned automatically: automatic degree-based detection only ever *flags* a candidate
    #: (``TopologySeparationDetail.hub_candidate_species_ids``); it never assigns this role or
    #: changes a weight by itself (task instructions §3: "must not silently exclude them by
    #: default").
    HIGH_DEGREE_HUB = "HIGH_DEGREE_HUB"
    #: Excluded for this one evaluation by explicit caller override, for a reason this package
    #: has no built-in vocabulary for (task instructions §5, context sensitivity).
    USER_EXCLUDED = "USER_EXCLUDED"


@dataclass(frozen=True, slots=True)
class TopologyRoleOverride:
    """One caller-supplied, per-evaluation override of a single species' own topology
    role/weight (task instructions §5, context sensitivity: "allow per-project/per-evaluation
    overrides so, for example, 14-3-3 can be ignored in one signaling model but treated as
    mechanistically central in another"). Always takes precedence over this package's own
    curated-name defaults and over automatic hub detection."""

    species_id: str
    role: TopologyRole
    #: ``None`` (the default) means "use this role's own default weight"
    #: (``app.agent2.module_evaluation.criteria.DEFAULT_TOPOLOGY_ROLE_WEIGHT``) -- an explicit
    #: value here overrides even that, e.g. declaring ATP ``NORMAL`` with ``weight=1`` in a
    #: model where ATP transport/signaling is itself the mechanism of interest.
    weight: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        if not isinstance(self.role, TopologyRole):
            raise TypeError(f"TopologyRoleOverride.role must be a TopologyRole, got {self.role!r}")
        if self.weight is not None:
            object.__setattr__(
                self, "weight", _require_unit_interval(self.weight, field_name="weight")
            )


@dataclass(frozen=True, slots=True)
class TopologyFilteringPolicy:
    """The complete, deterministic topology-filtering configuration for one evaluation --
    this package's own curated, name-based role defaults always apply first;
    ``overrides`` always take final precedence (task instructions: "use curated/context-
    defined roles first... allow per-project/per-evaluation overrides")."""

    overrides: tuple[TopologyRoleOverride, ...] = ()
    #: ``None`` (the default) means "use this criterion's own built-in, scope-aware default
    #: threshold" -- never disabled outright, since a hub candidate must always be flagged
    #: (never silently skipped, task §3), only never auto-excluded.
    hub_degree_threshold: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "overrides",
            _require_tuple_of(self.overrides, TopologyRoleOverride, field_name="overrides"),
        )
        seen: set[str] = set()
        duplicates: set[str] = set()
        for o in self.overrides:
            if o.species_id in seen:
                duplicates.add(o.species_id)
            seen.add(o.species_id)
        if duplicates:
            raise ValueError(
                "TopologyFilteringPolicy.overrides must name each species_id at most once, "
                f"found duplicate(s): {sorted(duplicates)}"
            )
        if self.hub_degree_threshold is not None:
            if not isinstance(self.hub_degree_threshold, int) or isinstance(
                self.hub_degree_threshold, bool
            ):
                raise TypeError(
                    "TopologyFilteringPolicy.hub_degree_threshold must be an int or None, got "
                    f"{self.hub_degree_threshold!r}"
                )
            if self.hub_degree_threshold < 1:
                raise ValueError(
                    "TopologyFilteringPolicy.hub_degree_threshold must be >= 1, got "
                    f"{self.hub_degree_threshold!r}"
                )

    def override_for(self, species_id: str) -> TopologyRoleOverride | None:
        """This species' own explicit override, or ``None`` when it was not named."""
        for o in self.overrides:
            if o.species_id == species_id:
                return o
        return None


@dataclass(frozen=True, slots=True)
class TopologyComponentFilter:
    """One species' own resolved, non-default topology-filtering treatment -- included in
    ``TopologySeparationDetail.filters`` only when it actually changed something (``role !=
    NORMAL`` or ``weight != 1``); an ordinary, unfiltered species is never listed, so this
    stays a compact, directly-actionable disclosure even on a large network."""

    species_id: str
    role: TopologyRole
    weight: Decimal
    #: ``"override"`` (an explicit ``TopologyRoleOverride`` named this species) or
    #: ``"curated_default"`` (this package's own built-in name-based classification, see
    #: ``app.agent2.module_evaluation.criteria``) -- never any other value.
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "species_id", _require_non_empty_str(self.species_id, field_name="species_id")
        )
        if not isinstance(self.role, TopologyRole):
            raise TypeError(
                f"TopologyComponentFilter.role must be a TopologyRole, got {self.role!r}"
            )
        object.__setattr__(self, "weight", _require_unit_interval(self.weight, field_name="weight"))
        if self.source not in ("override", "curated_default"):
            raise ValueError(
                "TopologyComponentFilter.source must be 'override' or 'curated_default', got "
                f"{self.source!r}"
            )


@dataclass(frozen=True, slots=True)
class TopologySeparationDetail:
    """``TOPOLOGICAL_SEPARATION``'s own extended, criterion-specific report (Topology
    Hub/Currency Component Filtering increment) -- ``None`` for every other criterion.
    ``ModularizationCriterionScore.raw_score`` for this criterion is always
    ``filtered_topology_score`` (task instructions §4: "use the filtered score for
    modularization evaluation"); this type additionally discloses the unfiltered baseline and
    exactly which components were treated differently, and why.
    """

    raw_topology_score: Decimal | None
    filtered_topology_score: Decimal | None
    filters: tuple[TopologyComponentFilter, ...] = ()
    hub_candidate_species_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.raw_topology_score is not None:
            object.__setattr__(
                self,
                "raw_topology_score",
                _require_unit_interval(self.raw_topology_score, field_name="raw_topology_score"),
            )
        if self.filtered_topology_score is not None:
            object.__setattr__(
                self,
                "filtered_topology_score",
                _require_unit_interval(
                    self.filtered_topology_score, field_name="filtered_topology_score"
                ),
            )
        object.__setattr__(
            self,
            "filters",
            _require_tuple_of(self.filters, TopologyComponentFilter, field_name="filters"),
        )
        object.__setattr__(
            self,
            "hub_candidate_species_ids",
            _require_str_tuple(
                self.hub_candidate_species_ids, field_name="hub_candidate_species_ids"
            ),
        )


@dataclass(frozen=True, slots=True)
class ModularizationCriterionScore:
    """One criterion's own fully-inspectable evaluated result for one modularization --
    always present for every criterion ``app.agent2.module_evaluation.criteria`` currently
    implements, *regardless* of that criterion's own weight (task instructions: "each
    criterion must remain separately inspectable" -- weight only ever gates the *weighted*
    contribution, never whether the raw score itself is computed and reported).

    ``available=False`` means the required evidence does not exist for this modularization
    today (never a fabricated placeholder number): ``raw_score``/``weighted_contribution`` are
    then both ``None``, and ``explanation`` states exactly what evidence was missing.
    """

    criterion: ModularizationCriterion
    available: bool
    raw_score: Decimal | None
    raw_weight: Decimal
    normalized_weight: Decimal
    weighted_contribution: Decimal | None
    explanation: str
    warnings: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    #: Topology Hub/Currency Component Filtering increment: ``TOPOLOGICAL_SEPARATION``'s own
    #: extended report (raw vs. filtered score, exactly which components were filtered and
    #: why). Always ``None`` for every other criterion -- this is the one, disclosed exception
    #: to this type's otherwise fully generic, criterion-agnostic shape.
    detail: TopologySeparationDetail | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, ModularizationCriterion):
            raise TypeError(
                "ModularizationCriterionScore.criterion must be a ModularizationCriterion, "
                f"got {self.criterion!r}"
            )
        if not isinstance(self.available, bool):
            raise TypeError(
                f"ModularizationCriterionScore.available must be a bool, got {self.available!r}"
            )
        if self.available:
            if self.raw_score is None:
                raise ValueError(
                    "ModularizationCriterionScore.raw_score must not be None when available"
                )
            object.__setattr__(
                self,
                "raw_score",
                _require_unit_interval(self.raw_score, field_name="raw_score"),
            )
        elif self.raw_score is not None:
            raise ValueError(
                "ModularizationCriterionScore.raw_score must be None when not available -- "
                "never a fabricated score for missing evidence"
            )
        if not isinstance(self.raw_weight, Decimal) or self.raw_weight < 0:
            raise ValueError(
                f"ModularizationCriterionScore.raw_weight must be a Decimal >= 0, got "
                f"{self.raw_weight!r}"
            )
        object.__setattr__(
            self,
            "normalized_weight",
            _require_unit_interval(self.normalized_weight, field_name="normalized_weight"),
        )
        expected_contribution_present = self.available and self.normalized_weight > 0
        if expected_contribution_present and self.weighted_contribution is None:
            raise ValueError(
                "ModularizationCriterionScore.weighted_contribution must not be None when "
                "the criterion is available and its normalized_weight is positive"
            )
        if not expected_contribution_present and self.weighted_contribution is not None:
            raise ValueError(
                "ModularizationCriterionScore.weighted_contribution must be None when the "
                "criterion is unavailable or its normalized_weight is zero"
            )
        if self.weighted_contribution is not None:
            object.__setattr__(
                self,
                "weighted_contribution",
                _require_unit_interval(
                    self.weighted_contribution, field_name="weighted_contribution"
                ),
            )
        object.__setattr__(
            self, "explanation", _require_non_empty_str(self.explanation, field_name="explanation")
        )
        object.__setattr__(
            self, "warnings", _require_str_tuple(self.warnings, field_name="warnings")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        if self.detail is not None:
            if not isinstance(self.detail, TopologySeparationDetail):
                raise TypeError(
                    "ModularizationCriterionScore.detail must be a TopologySeparationDetail "
                    f"or None, got {self.detail!r}"
                )
            if self.criterion is not ModularizationCriterion.TOPOLOGICAL_SEPARATION:
                raise ValueError(
                    "ModularizationCriterionScore.detail is only ever set for the "
                    f"TOPOLOGICAL_SEPARATION criterion, got criterion={self.criterion.value!r}"
                )


@dataclass(frozen=True, slots=True)
class ModularizationEvaluation:
    """Everything ``evaluate_modularization`` produces for one ``ModelModularization`` under
    one ``CriteriaWeights`` vector -- the task's own ``ModularizationEvaluation`` return type
    (§4), with every field that section requires.

    ``overall_score`` is ``None`` exactly when ``evaluated_weight_fraction == 0`` (not one
    positive-weight criterion had available evidence) -- never a fabricated number computed
    from nothing. When some, but not all, positive-weight criteria are available,
    ``overall_score`` is the sum of only the *available* criteria's own weighted contributions
    -- deliberately **not** renormalized among just the available subset, so the number never
    silently changes meaning (the same raw weights always mean the same thing); the resulting
    possible shortfall from the nominal total weight is exactly what
    ``evaluated_weight_fraction`` discloses, honestly, every time.

    **Stability-preparation note** (task §7 -- not implemented here, only prepared for):
    this type's own ``modularization_id``/``module_count``/``criterion_scores`` are already a
    clean, directly-comparable, serializable snapshot. A future increment measuring how often
    similar module boundaries recur across many ``CriteriaWeights`` vectors (via
    ``evaluate_modularization_under_weights``) needs no new type here -- it only needs to
    collect and compare many of these across weight space.
    """

    evaluation_id: str
    modularization_id: str
    module_count: int
    criterion_scores: tuple[ModularizationCriterionScore, ...]
    weights: CriteriaWeights
    overall_score: Decimal | None
    evaluated_weight_fraction: Decimal
    policy_version: str
    warnings: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluation_id",
            _require_non_empty_str(self.evaluation_id, field_name="evaluation_id"),
        )
        object.__setattr__(
            self,
            "modularization_id",
            _require_non_empty_str(self.modularization_id, field_name="modularization_id"),
        )
        if not isinstance(self.module_count, int) or isinstance(self.module_count, bool):
            raise TypeError(
                f"ModularizationEvaluation.module_count must be an int, got {self.module_count!r}"
            )
        if self.module_count < 0:
            raise ValueError(
                f"ModularizationEvaluation.module_count must be >= 0, got {self.module_count!r}"
            )
        object.__setattr__(
            self,
            "criterion_scores",
            _require_tuple_of(
                self.criterion_scores,
                ModularizationCriterionScore,
                field_name="criterion_scores",
            ),
        )
        seen: set[ModularizationCriterion] = set()
        duplicates: set[ModularizationCriterion] = set()
        for cs in self.criterion_scores:
            if cs.criterion in seen:
                duplicates.add(cs.criterion)
            seen.add(cs.criterion)
        if duplicates:
            raise ValueError(
                "ModularizationEvaluation.criterion_scores must name each criterion at most "
                f"once, found duplicate(s): {sorted(c.value for c in duplicates)}"
            )
        if not isinstance(self.weights, CriteriaWeights):
            raise TypeError(
                f"ModularizationEvaluation.weights must be a CriteriaWeights, got "
                f"{self.weights!r}"
            )
        object.__setattr__(
            self,
            "evaluated_weight_fraction",
            _require_unit_interval(
                self.evaluated_weight_fraction, field_name="evaluated_weight_fraction"
            ),
        )
        if self.evaluated_weight_fraction == 0 and self.overall_score is not None:
            raise ValueError(
                "ModularizationEvaluation.overall_score must be None when "
                "evaluated_weight_fraction is 0 -- never a fabricated score from zero "
                "available evidence"
            )
        if self.evaluated_weight_fraction > 0 and self.overall_score is None:
            raise ValueError(
                "ModularizationEvaluation.overall_score must not be None when "
                "evaluated_weight_fraction is positive"
            )
        if self.overall_score is not None:
            object.__setattr__(
                self,
                "overall_score",
                _require_unit_interval(self.overall_score, field_name="overall_score"),
            )
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )
        object.__setattr__(
            self, "warnings", _require_str_tuple(self.warnings, field_name="warnings")
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _require_str_tuple(self.provenance_refs, field_name="provenance_refs"),
        )


__all__ = [
    "CriteriaWeights",
    "CriterionWeight",
    "ModularizationCriterion",
    "ModularizationCriterionScore",
    "ModularizationEvaluation",
    "TopologyComponentFilter",
    "TopologyFilteringPolicy",
    "TopologyRole",
    "TopologyRoleOverride",
    "TopologySeparationDetail",
]
