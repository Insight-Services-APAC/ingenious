"""Criteria routes for SoCa API."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from soca.auth import get_current_user
from soca.criteria import extract_text_from_file, generate_criteria_from_text
from soca.db import db, get_templates
from soca.models import CreateCriteriaSetRequest, CriteriaSet, User

router = APIRouter(prefix="/api", tags=["criteria"])


@router.get("/criteria-sets", response_model=list[CriteriaSet])
async def list_criteria_sets(current_user: User = Depends(get_current_user)) -> list[CriteriaSet]:
    """List all criteria sets."""
    criteria_sets: list[CriteriaSet] = await db.list_criteria_sets()
    return criteria_sets


@router.get("/criteria-templates", response_model=list[CriteriaSet])
async def list_criteria_templates(
    current_user: User = Depends(get_current_user),
) -> list[CriteriaSet]:
    """List available criteria templates."""
    templates: list[CriteriaSet] = get_templates()
    return templates


@router.post("/criteria-sets", response_model=CriteriaSet)
async def create_criteria_set(
    request: CreateCriteriaSetRequest,
    current_user: User = Depends(get_current_user),
) -> CriteriaSet:
    """Create a new criteria set."""
    criteria_set = CriteriaSet(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        criteria=request.criteria,
        created_at=datetime.utcnow().isoformat() + "Z",
    )
    return await db.create_criteria_set(criteria_set)


@router.patch("/criteria-sets/{criteria_set_id}", response_model=CriteriaSet)
async def update_criteria_set(
    criteria_set_id: str,
    request: CreateCriteriaSetRequest,
    current_user: User = Depends(get_current_user),
) -> CriteriaSet:
    """Update a criteria set."""
    existing = await db.get_criteria_set(criteria_set_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Criteria set not found")

    updated = CriteriaSet(
        id=criteria_set_id,
        name=request.name,
        description=request.description,
        criteria=request.criteria,
        created_at=existing.created_at,
    )
    return await db.update_criteria_set(updated)


@router.delete("/criteria-sets/{criteria_set_id}")
async def delete_criteria_set(
    criteria_set_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a criteria set."""
    success = await db.delete_criteria_set(criteria_set_id)
    if not success:
        raise HTTPException(status_code=404, detail="Criteria set not found")
    return {"status": "deleted"}


@router.post("/criteria-sets/generate", response_model=CriteriaSet)
async def generate_criteria_set(
    file: Optional[UploadFile] = File(default=None),
    document_text: Optional[str] = Form(default=None),
    name: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
) -> CriteriaSet:
    """Generate a criteria set from document text or uploaded file using AI.

    Supports two input methods:
    1. Direct text: Pass document_text as form field
    2. File upload: Upload PDF, DOCX, or TXT file

    The AI will analyze the document and generate appropriate evaluation criteria.
    """
    # Validate that at least one input method is provided
    if not file and not document_text:
        raise HTTPException(status_code=400, detail="Either file or document_text must be provided")

    # Extract text from file if provided
    if file:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        try:
            document_text = await extract_text_from_file(
                content=content,
                content_type=file.content_type or "application/octet-stream",
                filename=file.filename or "file",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Validate extracted/provided text
    if not document_text or len(document_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Document text is too short to generate meaningful criteria",
        )

    # Call AI to generate criteria
    try:
        criteria_set = await generate_criteria_from_text(
            document_text=document_text,
            name_override=name,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Save to database
    return await db.create_criteria_set(criteria_set)
