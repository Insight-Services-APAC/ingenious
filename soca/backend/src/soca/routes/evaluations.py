"""Evaluations routes for SoCa API."""

import csv
import io
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from soca.auth import get_current_user
from soca.config import settings
from soca.db import db
from soca.evaluations import run_evaluation
from soca.models import (
    CreateEvaluationRequest,
    CriteriaSet,
    Evaluation,
    EvaluationStatus,
    Submission,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("", response_model=list[Evaluation])
async def list_evaluations(current_user: User = Depends(get_current_user)) -> list[Evaluation]:
    """List all evaluations."""
    evaluations: list[Evaluation] = await db.list_evaluations()
    return evaluations


@router.get("/{evaluation_id}", response_model=Evaluation)
async def get_evaluation(
    evaluation_id: str,
    current_user: User = Depends(get_current_user),
) -> Evaluation:
    """Get a specific evaluation."""
    evaluation = await db.get_evaluation(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation


@router.post("", response_model=Evaluation)
async def create_evaluation(
    request: CreateEvaluationRequest,
    current_user: User = Depends(get_current_user),
) -> Evaluation:
    """Create a new evaluation."""
    # Get criteria set name
    criteria_set = await db.get_criteria_set(request.criteria_set_id)
    criteria_set_name = criteria_set.name if criteria_set else None

    evaluation = Evaluation(
        id=str(uuid.uuid4()),
        name=request.name,
        status=EvaluationStatus.DRAFT,
        submission_ids=request.submission_ids,
        criteria_set_id=request.criteria_set_id,
        criteria_set_name=criteria_set_name,
        results=[],
        created_at=datetime.utcnow().isoformat() + "Z",
    )
    return await db.create_evaluation(evaluation)


@router.post("/{evaluation_id}/run", response_model=Evaluation)
async def run_evaluation_endpoint(
    evaluation_id: str,
    current_user: User = Depends(get_current_user),
) -> Evaluation:
    """Run an evaluation."""
    evaluation = await db.get_evaluation(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Run evaluation synchronously
    result = await run_evaluation(evaluation_id)
    if not result:
        raise HTTPException(status_code=500, detail="Evaluation failed")

    return result


async def _get_export_context(
    evaluation_id: str,
) -> tuple[Evaluation, dict[str, Submission], dict[str, Any], Optional[CriteriaSet]]:
    """Get evaluation and related data for export."""
    evaluation = await db.get_evaluation(evaluation_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    submissions_map: dict[str, Submission] = {}
    for sid in evaluation.submission_ids:
        sub = await db.get_submission(sid)
        if sub:
            submissions_map[sid] = sub

    criteria_set = await db.get_criteria_set(evaluation.criteria_set_id)
    criteria_map: dict[str, Any] = {}
    if criteria_set:
        criteria_map = {c.id: c for c in criteria_set.criteria}

    return evaluation, submissions_map, criteria_map, criteria_set


def _build_json_export(
    evaluation: Evaluation,
    submissions_map: dict[str, Submission],
    criteria_map: dict[str, Any],
) -> str:
    """Build JSON export content."""
    results_list: list[dict[str, Any]] = []
    for result in evaluation.results:
        sub = submissions_map.get(result.submission_id)
        criteria_scores = [
            {
                "criterion": criteria_map[cr.criterion_id].name
                if cr.criterion_id in criteria_map
                else cr.criterion_id,
                "score": cr.score,
                "narrative": cr.narrative,
            }
            for cr in result.criterion_results
        ]
        results_list.append(
            {
                "submission": sub.name if sub else result.submission_id,
                "overallScore": result.overall_score,
                "summary": result.summary,
                "criteriaScores": criteria_scores,
            }
        )

    export_data: dict[str, Any] = {
        "evaluation": {
            "id": evaluation.id,
            "name": evaluation.name,
            "status": evaluation.status.value,
            "criteriaSet": evaluation.criteria_set_name,
            "createdAt": evaluation.created_at,
            "completedAt": evaluation.completed_at,
        },
        "results": results_list,
    }
    return json.dumps(export_data, indent=2)


def _build_csv_export(
    evaluation: Evaluation,
    submissions_map: dict[str, Submission],
    criteria_set: Optional[CriteriaSet],
) -> str:
    """Build CSV export content."""
    output = io.StringIO()
    writer = csv.writer(output)

    criteria_names = [c.name for c in criteria_set.criteria] if criteria_set else []
    header = ["Rank", "Submission", "Overall Score"] + criteria_names + ["Summary"]
    writer.writerow(header)

    sorted_results = sorted(evaluation.results, key=lambda r: r.overall_score, reverse=True)

    for rank, result in enumerate(sorted_results, 1):
        sub = submissions_map.get(result.submission_id)
        row: list[Any] = [rank, sub.name if sub else result.submission_id, result.overall_score]

        score_map = {cr.criterion_id: cr.score for cr in result.criterion_results}
        if criteria_set:
            row.extend(score_map.get(c.id, "") for c in criteria_set.criteria)
        row.append(result.summary)
        writer.writerow(row)

    return output.getvalue()


@router.get("/{evaluation_id}/export/{format}")
async def export_evaluation(
    evaluation_id: str,
    format: str,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export evaluation results in specified format."""
    evaluation, submissions_map, criteria_map, criteria_set = await _get_export_context(
        evaluation_id
    )

    if format == "json":
        content = _build_json_export(evaluation, submissions_map, criteria_map)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{evaluation.name}.json"'},
        )

    if format == "csv":
        content = _build_csv_export(evaluation, submissions_map, criteria_set)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{evaluation.name}.csv"'},
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.delete("/{evaluation_id}")
async def delete_evaluation(
    evaluation_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an evaluation and its associated traces in Prompt Tuner."""
    success = await db.delete_evaluation(evaluation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    # Delete associated traces in Prompt Tuner (graceful degradation on failure)
    traces_deleted = 0
    prompt_tuner_url = settings.ingenious_api_url or "http://localhost:8002"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{prompt_tuner_url}/api/traces/by-thread/{evaluation_id}",
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                traces_deleted = data.get("deleted_count", 0)
                logger.info(f"Deleted {traces_deleted} traces for evaluation {evaluation_id}")
            else:
                logger.warning(
                    f"Failed to delete traces for evaluation {evaluation_id}: "
                    f"status {response.status_code}"
                )
    except Exception as e:
        logger.warning(f"Could not delete traces for evaluation {evaluation_id}: {e}")

    return {"status": "deleted", "traces_deleted": traces_deleted}
