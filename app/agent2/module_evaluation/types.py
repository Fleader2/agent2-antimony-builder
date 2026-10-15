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

    The first four have a real producer from Agent 2/canonical-model information alone
    (``app.agent2.module_evaluation.criteria``). ``DYNAMIC_ISOLATION``/``SENSITIVITY_
    COHERENCE`` (Functional Modularity Criteria from Agents 3 and 4 increment) and
    ``CALIBRATION_INDEPENDENCE`` (Recursive Module Evaluation Orchestration increment) each
    have a real producer too, but only ever computed when a caller supplies the corresponding
    external evidence (``functional_evaluation_evidence``/``calibration_evidence``) -- never
    computed from the canonical model alone, and never appearing in ``criterion_scores`` at
    all when that evidence is omitted (see ``app.agent2.module_evaluation.functional_adapter``/
    ``.calibration_adapter``). The remaining three are still-reserved vocabulary for future
    increments: genuine pathway/network membership, regulatory coherence, and Agent 5
    experimental validation. A future increment implementing one of these needs no interface
    change -- it only adds its own scoring function and extends the relevant dispatch table.

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
    #: Does a candidate module behave relatively independently of its surrounding context --
    #: does an internal perturbation mostly stay internal (little spillover), do the module's
    #: own outputs mostly ignore external perturbations (little external dependence), and do
    #: its own declared boundary ports actually absorb most of whatever cross-module influence
    #: does exist? Computed from real Agent 3 whole-network perturbation evidence (Functional
    #: Modularity Criteria from Agents 3 and 4 increment); unavailable unless a caller supplies
    #: ``functional_evaluation_evidence``. (app.agent2.module_evaluation.functional_adapter
    #: .score_dynamic_isolation)
    DYNAMIC_ISOLATION = "DYNAMIC_ISOLATION"
    #: Do a module's own components share a coherent internal sensitivity *pattern* (similar
    #: profiles of which species respond to which internal perturbations), and is that pattern
    #: genuinely distinct from how an external perturbation's own profile looks -- i.e. does
    #: the declared boundary actually separate two weakly-coupled sensitivity groups? Computed
    #: from the identical Agent 3 perturbation evidence ``DYNAMIC_ISOLATION`` uses, interpreted
    #: as pattern similarity rather than effect magnitude; unavailable unless a caller supplies
    #: ``functional_evaluation_evidence``. (.score_sensitivity_coherence)
    SENSITIVITY_COHERENCE = "SENSITIVITY_COHERENCE"
    #: Agent 4's own calibration independence/practical identifiability across modules.
    #: Computed from real Agent 4 evidence (Recursive Module Evaluation Orchestration
    #: increment); unavailable unless a caller supplies ``calibration_evidence``.
    #: (app.agent2.module_evaluation.calibration_adapter.score_calibration_independence)
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


class CalibrationAggregationMethod(StrEnum):
    """One explicit, closed policy for aggregating several modules' own per-module
    ``CALIBRATION_INDEPENDENCE`` contributions into one modularization-level score
    (Calibration-Independence Aggregation increment, task instructions §1) -- replaces the
    single, previously hard-coded weakest-link (``min()``) policy. Never inferred implicitly
    from the number of modules or from any other criterion."""

    #: Weakest-link: the minimum per-module score. Proven (Module-Count / Resolution Bias
    #: Audit increment) to be inherently, monotonically non-increasing as module count grows --
    #: retained here as an explicit, strict diagnostic choice, never the default search-ranking
    #: policy (task instructions §3).
    MINIMUM = "MINIMUM"
    #: The (optionally per-module-weighted) arithmetic mean of every per-module score.
    #: Unbiased in expectation with respect to module count for a fixed per-module quality
    #: distribution (``E[mean(X_1..X_n)] = E[X]``, constant in ``n``) -- the chosen default
    #: (task instructions §3).
    WEIGHTED_MEAN = "WEIGHTED_MEAN"
    #: A disclosed lower quantile (``policy.quantile``) of the per-module score distribution --
    #: less sensitive to one single worst-scoring module than ``MINIMUM``, but still not fully
    #: count-invariant.
    LOWER_QUANTILE = "LOWER_QUANTILE"
    #: The fraction of modules whose own score is ``>= policy.threshold`` -- "what proportion
    #: of this modularization's modules are acceptable," never a continuous blend of scores.
    FRACTION_ABOVE_THRESHOLD = "FRACTION_ABOVE_THRESHOLD"


@dataclass(frozen=True, slots=True)
class CalibrationAggregationPolicy:
    """The complete, explicit configuration for one ``CalibrationAggregationMethod`` (task
    instructions §1) -- never a bare enum value alone, since ``LOWER_QUANTILE``/
    ``FRACTION_ABOVE_THRESHOLD`` each require one further, disclosed parameter, and
    ``WEIGHTED_MEAN`` optionally accepts explicit per-module weights (uniform weight ``1`` for
    any module not named in ``module_weights`` -- an unweighted mean when ``module_weights`` is
    left empty, never a hidden default weighting scheme)."""

    method: CalibrationAggregationMethod
    quantile: Decimal | None = None
    threshold: Decimal | None = None
    module_weights: tuple[tuple[str, Decimal], ...] = ()
    policy_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.method, CalibrationAggregationMethod):
            raise TypeError(
                "CalibrationAggregationPolicy.method must be a CalibrationAggregationMethod, "
                f"got {self.method!r}"
            )
        if self.method is CalibrationAggregationMethod.LOWER_QUANTILE:
            if self.quantile is None:
                raise ValueError(
                    "CalibrationAggregationPolicy.quantile is required for LOWER_QUANTILE"
                )
            object.__setattr__(
                self, "quantile", _require_unit_interval(self.quantile, field_name="quantile")
            )
            if self.quantile == 0:
                raise ValueError(
                    "CalibrationAggregationPolicy.quantile must be > 0 for LOWER_QUANTILE, got 0"
                )
        elif self.quantile is not None:
            raise ValueError(
                "CalibrationAggregationPolicy.quantile must be None unless method is "
                f"LOWER_QUANTILE, got method={self.method!r}, quantile={self.quantile!r}"
            )
        if self.method is CalibrationAggregationMethod.FRACTION_ABOVE_THRESHOLD:
            if self.threshold is None:
                raise ValueError(
                    "CalibrationAggregationPolicy.threshold is required for "
                    "FRACTION_ABOVE_THRESHOLD"
                )
            object.__setattr__(
                self, "threshold", _require_unit_interval(self.threshold, field_name="threshold")
            )
        elif self.threshold is not None:
            raise ValueError(
                "CalibrationAggregationPolicy.threshold must be None unless method is "
                f"FRACTION_ABOVE_THRESHOLD, got method={self.method!r}, "
                f"threshold={self.threshold!r}"
            )
        if self.module_weights and self.method is not CalibrationAggregationMethod.WEIGHTED_MEAN:
            raise ValueError(
                "CalibrationAggregationPolicy.module_weights must be empty unless method is "
                f"WEIGHTED_MEAN, got method={self.method!r}"
            )
        cleaned_weights: list[tuple[str, Decimal]] = []
        seen_module_ids: set[str] = set()
        for item in self.module_weights:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
                or not isinstance(item[1], Decimal)
                or item[1] <= 0
            ):
                raise TypeError(
                    "CalibrationAggregationPolicy.module_weights must be a tuple of "
                    f"(non-empty module_id str, positive Decimal weight) pairs, got {item!r}"
                )
            if item[0] in seen_module_ids:
                raise ValueError(
                    "CalibrationAggregationPolicy.module_weights must not repeat a module_id, "
                    f"got a duplicate {item[0]!r}"
                )
            seen_module_ids.add(item[0])
            cleaned_weights.append(item)
        object.__setattr__(self, "module_weights", tuple(cleaned_weights))
        object.__setattr__(
            self,
            "policy_version",
            _require_non_empty_str(self.policy_version, field_name="policy_version"),
        )


@dataclass(frozen=True, slots=True)
class CalibrationIndependenceDetail:
    """``CALIBRATION_INDEPENDENCE``'s own extended, criterion-specific report (Recursive Module
    Evaluation Orchestration increment; extended by the Calibration-Independence Aggregation
    increment) -- ``None`` for every other criterion, mirroring ``TopologySeparationDetail``'s
    identical, one-disclosed-exception pattern.

    ``module_ids_with_evidence``/``module_ids_missing_evidence`` disclose exactly which modules
    of the modularization contributed real calibration evidence and which did not (never
    silently averaged away) -- see ``app.agent2.module_evaluation.calibration_adapter`` for the
    pluggable aggregation policy these support. ``statuses_by_module_id`` names each
    evidence-bearing module's own ``ModuleCalibrationStatus.value``.

    ``aggregation_method``/``per_module_scores``/``mean_score``/``min_score``/``max_score``/
    ``unavailable_module_count`` (Calibration-Independence Aggregation increment) disclose
    exactly how ``raw_score`` was computed and never hide a weak module behind the aggregate:
    ``per_module_scores`` always lists *every* evidence-bearing module's own individual score,
    regardless of which aggregation method produced the single aggregate number, and regardless
    of whether the aggregate itself is available at all (a modularization with some, but not
    all, modules missing evidence still discloses the scores of the modules that do have it).
    """

    module_ids_with_evidence: tuple[str, ...] = ()
    module_ids_missing_evidence: tuple[str, ...] = ()
    statuses_by_module_id: tuple[tuple[str, str], ...] = ()
    aggregation_method: CalibrationAggregationMethod | None = None
    per_module_scores: tuple[tuple[str, Decimal], ...] = ()
    mean_score: Decimal | None = None
    min_score: Decimal | None = None
    max_score: Decimal | None = None
    unavailable_module_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "module_ids_with_evidence",
            _require_str_tuple(
                self.module_ids_with_evidence, field_name="module_ids_with_evidence"
            ),
        )
        object.__setattr__(
            self,
            "module_ids_missing_evidence",
            _require_str_tuple(
                self.module_ids_missing_evidence, field_name="module_ids_missing_evidence"
            ),
        )

        def _is_str_pair(item: object) -> bool:
            return (
                isinstance(item, tuple) and len(item) == 2 and all(isinstance(x, str) for x in item)
            )

        if not isinstance(self.statuses_by_module_id, tuple) or any(
            not _is_str_pair(item) for item in self.statuses_by_module_id
        ):
            raise TypeError(
                "CalibrationIndependenceDetail.statuses_by_module_id must be a tuple of "
                f"(module_id, status) str pairs, got {self.statuses_by_module_id!r}"
            )
        if self.aggregation_method is not None and not isinstance(
            self.aggregation_method, CalibrationAggregationMethod
        ):
            raise TypeError(
                "CalibrationIndependenceDetail.aggregation_method must be a "
                f"CalibrationAggregationMethod or None, got {self.aggregation_method!r}"
            )

        def _is_module_score_pair(item: object) -> bool:
            return (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and bool(item[0])
                and isinstance(item[1], Decimal)
            )

        if not isinstance(self.per_module_scores, tuple) or any(
            not _is_module_score_pair(item) for item in self.per_module_scores
        ):
            raise TypeError(
                "CalibrationIndependenceDetail.per_module_scores must be a tuple of "
                f"(module_id, Decimal score) pairs, got {self.per_module_scores!r}"
            )
        for field_name in ("mean_score", "min_score", "max_score"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(
                    f"CalibrationIndependenceDetail.{field_name} must be a Decimal or None, "
                    f"got {value!r}"
                )
        if (
            not isinstance(self.unavailable_module_count, int)
            or isinstance(self.unavailable_module_count, bool)
            or self.unavailable_module_count < 0
        ):
            raise ValueError(
                "CalibrationIndependenceDetail.unavailable_module_count must be a "
                f"non-negative int, got {self.unavailable_module_count!r}"
            )


@dataclass(frozen=True, slots=True)
class DynamicIsolationDetail:
    """``DYNAMIC_ISOLATION``'s own extended, criterion-specific report (Functional Modularity
    Criteria from Agents 3 and 4 increment) -- every per-module raw metric Agent 2's own
    ``app.agent2.module_evaluation.functional_adapter.score_dynamic_isolation`` derives from
    real Agent 3 perturbation evidence, preserved alongside the single normalized ``[0, 1]``
    score (task instructions §2: "return a normalized score plus raw metrics and provenance").

    ``per_module_boundary_capture_fraction`` only ever names a module for which it was actually
    computable (a module with no declared ``ModulePort`` at all has no boundary to measure
    capture against) -- never fabricated for one with none.
    """

    module_ids_with_evidence: tuple[str, ...] = ()
    module_ids_missing_evidence: tuple[str, ...] = ()
    per_module_scores: tuple[tuple[str, Decimal], ...] = ()
    per_module_spillover_ratio: tuple[tuple[str, Decimal], ...] = ()
    per_module_external_dependence_ratio: tuple[tuple[str, Decimal], ...] = ()
    per_module_boundary_capture_fraction: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "module_ids_with_evidence",
            _require_str_tuple(
                self.module_ids_with_evidence, field_name="module_ids_with_evidence"
            ),
        )
        object.__setattr__(
            self,
            "module_ids_missing_evidence",
            _require_str_tuple(
                self.module_ids_missing_evidence, field_name="module_ids_missing_evidence"
            ),
        )

        def _is_module_decimal_pair(item: object) -> bool:
            return (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and bool(item[0])
                and isinstance(item[1], Decimal)
            )

        for field_name in (
            "per_module_scores",
            "per_module_spillover_ratio",
            "per_module_external_dependence_ratio",
            "per_module_boundary_capture_fraction",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or any(not _is_module_decimal_pair(i) for i in value):
                raise TypeError(
                    f"DynamicIsolationDetail.{field_name} must be a tuple of (module_id, "
                    f"Decimal) pairs, got {value!r}"
                )


@dataclass(frozen=True, slots=True)
class SensitivityCoherenceDetail:
    """``SENSITIVITY_COHERENCE``'s own extended, criterion-specific report (Functional
    Modularity Criteria from Agents 3 and 4 increment) -- mirrors ``DynamicIsolationDetail``'s
    own disclosure convention for the identical reason."""

    module_ids_with_evidence: tuple[str, ...] = ()
    module_ids_missing_evidence: tuple[str, ...] = ()
    per_module_scores: tuple[tuple[str, Decimal], ...] = ()
    per_module_within_module_coherence: tuple[tuple[str, Decimal], ...] = ()
    per_module_across_boundary_coherence: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "module_ids_with_evidence",
            _require_str_tuple(
                self.module_ids_with_evidence, field_name="module_ids_with_evidence"
            ),
        )
        object.__setattr__(
            self,
            "module_ids_missing_evidence",
            _require_str_tuple(
                self.module_ids_missing_evidence, field_name="module_ids_missing_evidence"
            ),
        )

        def _is_module_decimal_pair(item: object) -> bool:
            return (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and bool(item[0])
                and isinstance(item[1], Decimal)
            )

        for field_name in (
            "per_module_scores",
            "per_module_within_module_coherence",
            "per_module_across_boundary_coherence",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or any(not _is_module_decimal_pair(i) for i in value):
                raise TypeError(
                    f"SensitivityCoherenceDetail.{field_name} must be a tuple of (module_id, "
                    f"Decimal) pairs, got {value!r}"
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
    #: why). Recursive Module Evaluation Orchestration increment: ``CALIBRATION_INDEPENDENCE``'s
    #: own extended report (``CalibrationIndependenceDetail``) joins this as the only other
    #: disclosed exception to this type's otherwise fully generic, criterion-agnostic shape --
    #: ``None`` for every other criterion.
    detail: TopologySeparationDetail | CalibrationIndependenceDetail | None = None
    #: Module-Count / Resolution Bias Audit increment. ``null_reference_score`` is this one
    #: criterion's own score for a deterministic, structure-blind partition matched to this
    #: modularization's own module count (``app.agent2.resolution_audit``) -- ``None`` unless a
    #: caller explicitly supplied one (``evaluate_modularization``'s own ``null_reference_
    #: scores`` parameter; omitting it, the default, leaves both fields ``None`` and reproduces
    #: every pre-existing behavior exactly). ``corrected_score`` is ``(raw_score -
    #: null_reference_score) / (1 - null_reference_score)`` -- "how much of the possible
    #: improvement over the resolution-matched blind baseline did this real partition actually
    #: capture," deliberately **not** clamped to ``[0, 1]`` here (a real partition that scores
    #: *worse* than a blind one is itself a genuine, disclosed negative finding, never hidden by
    #: clamping) -- ``evaluate_modularization`` clamps only the value it feeds into ``weighted_
    #: contribution``/``overall_score``, never this field. ``None`` when ``null_reference_score``
    #: is itself ``>= 1`` (the blind baseline already achieves the maximum possible score at
    #: this resolution -- no correction is meaningful). The original ``raw_score`` above is
    #: always preserved unchanged alongside both.
    null_reference_score: Decimal | None = None
    corrected_score: Decimal | None = None

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
            if isinstance(self.detail, TopologySeparationDetail):
                if self.criterion is not ModularizationCriterion.TOPOLOGICAL_SEPARATION:
                    raise ValueError(
                        "ModularizationCriterionScore.detail (TopologySeparationDetail) is "
                        "only ever set for the TOPOLOGICAL_SEPARATION criterion, got "
                        f"criterion={self.criterion.value!r}"
                    )
            elif isinstance(self.detail, CalibrationIndependenceDetail):
                if self.criterion is not ModularizationCriterion.CALIBRATION_INDEPENDENCE:
                    raise ValueError(
                        "ModularizationCriterionScore.detail (CalibrationIndependenceDetail) "
                        "is only ever set for the CALIBRATION_INDEPENDENCE criterion, got "
                        f"criterion={self.criterion.value!r}"
                    )
            elif isinstance(self.detail, DynamicIsolationDetail):
                if self.criterion is not ModularizationCriterion.DYNAMIC_ISOLATION:
                    raise ValueError(
                        "ModularizationCriterionScore.detail (DynamicIsolationDetail) is "
                        "only ever set for the DYNAMIC_ISOLATION criterion, got "
                        f"criterion={self.criterion.value!r}"
                    )
            elif isinstance(self.detail, SensitivityCoherenceDetail):
                if self.criterion is not ModularizationCriterion.SENSITIVITY_COHERENCE:
                    raise ValueError(
                        "ModularizationCriterionScore.detail (SensitivityCoherenceDetail) is "
                        "only ever set for the SENSITIVITY_COHERENCE criterion, got "
                        f"criterion={self.criterion.value!r}"
                    )
            else:
                raise TypeError(
                    "ModularizationCriterionScore.detail must be a TopologySeparationDetail, "
                    "a CalibrationIndependenceDetail, a DynamicIsolationDetail, a "
                    f"SensitivityCoherenceDetail, or None, got {self.detail!r}"
                )
        if self.null_reference_score is not None:
            if not self.available:
                raise ValueError(
                    "ModularizationCriterionScore.null_reference_score must be None when the "
                    "criterion itself is not available -- a null baseline is only ever "
                    "meaningful alongside a real, available score to compare it against"
                )
            object.__setattr__(
                self,
                "null_reference_score",
                _require_unit_interval(
                    self.null_reference_score, field_name="null_reference_score"
                ),
            )
        if self.corrected_score is not None:
            if self.null_reference_score is None:
                raise ValueError(
                    "ModularizationCriterionScore.corrected_score must be None when "
                    "null_reference_score is None -- never a correction with nothing to "
                    "correct against"
                )
            if not isinstance(self.corrected_score, Decimal):
                raise TypeError(
                    "ModularizationCriterionScore.corrected_score must be a Decimal or None, "
                    f"got {self.corrected_score!r}"
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
                f"ModularizationEvaluation.weights must be a CriteriaWeights, got {self.weights!r}"
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
    "CalibrationAggregationMethod",
    "CalibrationAggregationPolicy",
    "CalibrationIndependenceDetail",
    "CriteriaWeights",
    "CriterionWeight",
    "DynamicIsolationDetail",
    "ModularizationCriterion",
    "ModularizationCriterionScore",
    "ModularizationEvaluation",
    "SensitivityCoherenceDetail",
    "TopologyComponentFilter",
    "TopologyFilteringPolicy",
    "TopologyRole",
    "TopologyRoleOverride",
    "TopologySeparationDetail",
]
