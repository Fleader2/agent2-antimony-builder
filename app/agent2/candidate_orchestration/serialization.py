"""Plain-dict serialization for ``CandidateSearchRoundResult`` -- the one, deliberately
*narrow* contract a cross-process caller (always the Harness, running this package inside
Agent 2's own venv as a subprocess) reads back, mirroring every other Agent2<->Harness boundary
in this project (``app.agent2.module_calibration.serialization``): only what the recursive loop
driver and a human-facing provenance report actually need, never a full dump of every internal
``ModularizationEvaluation``/``CandidateModularizationBundle`` field. A caller that needs the
full in-process result keeps calling ``run_candidate_search_round`` directly in Python; this
module exists only for the subprocess boundary.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agent2.candidate_orchestration.types import CandidateSearchRoundResult
from app.agent2.modularization_search.identity import module_content_key
from app.agent2.modularization_search.types import CandidateModularizationBundle
from app.agent2.module_calibration.serialization import (
    serialize_module_calibration_evaluation,
    serialize_module_calibration_request,
)
from app.agent2.module_evaluation.types import ModularizationEvaluation


def _content_key_pairs(
    bundle: CandidateModularizationBundle, module_id: str
) -> list[list[str]]:
    """This module's own content key, as a JSON-shaped, sorted ``[[component_type,
    component_id], ...]`` list -- the one, literal token a caller (always the Harness) echoes
    back unchanged next round as this exact module's own ``calibration_evidence`` key. Never
    reconstructed by parsing the ``module_id`` string itself (fragile: a component id could, in
    principle, contain the characters that string format uses as separators)."""
    return [list(pair) for pair in sorted(module_content_key(bundle.memberships, module_id))]


def _decimal_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _candidate_summary(
    bundle: CandidateModularizationBundle, evaluation: ModularizationEvaluation
) -> dict[str, Any]:
    return {
        "candidate_id": bundle.modularization.modularization_id,
        "module_ids": sorted(m.module_id for m in bundle.modules),
        "module_count": evaluation.module_count,
        "overall_score": _decimal_str(evaluation.overall_score),
        "evaluated_weight_fraction": _decimal_str(evaluation.evaluated_weight_fraction),
        "criterion_scores": [
            {
                "criterion": cs.criterion.value,
                "available": cs.available,
                "raw_score": _decimal_str(cs.raw_score),
                "weighted_contribution": _decimal_str(cs.weighted_contribution),
                "null_reference_score": _decimal_str(cs.null_reference_score),
                "corrected_score": _decimal_str(cs.corrected_score),
            }
            for cs in evaluation.criterion_scores
        ],
    }


def serialize_round_result(round_result: CandidateSearchRoundResult) -> dict[str, Any]:
    """``CandidateSearchRoundResult`` -> the one plain dict shape a caller (always the Harness)
    reads back to drive the recursive loop and reconstruct this round's own provenance."""
    search_result = round_result.search_result
    bundles_by_candidate_id = {
        b.modularization.modularization_id: b for b in search_result.retained
    }
    evaluations_by_id = {
        ev.modularization_id: ev for ev in search_result.evaluations
    }
    degenerate_evaluations_by_id = {
        ev.modularization_id: ev for ev in search_result.degenerate_evaluations
    }
    lineage_by_id = {entry.candidate_id: entry for entry in search_result.lineage}

    def _lineage_dict(candidate_id: str) -> dict[str, Any] | None:
        entry = lineage_by_id.get(candidate_id)
        if entry is None:
            return None
        return {
            "parent_candidate_id": entry.parent_candidate_id,
            "operation": entry.operation.value,
            "generation": entry.generation,
            "affected_component_ids": list(entry.affected_component_ids),
            "affected_module_ids": list(entry.affected_module_ids),
        }

    retained = [
        {**_candidate_summary(b, evaluations_by_id[b.modularization.modularization_id]),
         "lineage": _lineage_dict(b.modularization.modularization_id)}
        for b in search_result.retained
    ]
    degenerate = [
        {
            **_candidate_summary(
                b, degenerate_evaluations_by_id[b.modularization.modularization_id]
            ),
            "lineage": _lineage_dict(b.modularization.modularization_id),
        }
        for b in search_result.degenerate
    ]

    return {
        "search_id": search_result.search_id,
        "model_id": search_result.model_id,
        "seed_candidate_id": search_result.seed_candidate_id,
        "retained": retained,
        "degenerate": degenerate,
        "rejected_count": len(search_result.rejected),
        "iterations_run": search_result.iterations_run,
        "search_policy_version": search_result.policy_version,
        "exclude_single_module_from_ranking": search_result.exclude_single_module_from_ranking,
        "search_warnings": list(search_result.warnings),
        "calibration_decisions": [
            {
                "candidate_id": d.candidate_id,
                "module_id": d.module_id,
                "content_key": _content_key_pairs(
                    bundles_by_candidate_id[d.candidate_id], d.module_id
                ),
                "outcome": d.outcome.value,
                "reason": d.reason,
                "structural_score": _decimal_str(d.structural_score),
                "rank": d.rank,
            }
            for d in round_result.calibration_decisions
        ],
        "calibration_requests": [
            {
                "content_key": _content_key_pairs(
                    bundles_by_candidate_id[envelope.decision.candidate_id],
                    envelope.decision.module_id,
                ),
                "request": serialize_module_calibration_request(envelope.request),
            }
            for envelope in round_result.calibration_requests
        ],
        "locally_resolved_evidence": [
            {
                "content_key": _content_key_pairs(
                    bundles_by_candidate_id[evaluation.modularization_id], evaluation.module_id
                ),
                "evaluation": serialize_module_calibration_evaluation(evaluation),
            }
            for evaluation in round_result.locally_resolved_evidence
        ],
        "policy_version": round_result.policy_version,
    }


__all__ = ["serialize_round_result"]
