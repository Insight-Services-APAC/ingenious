"""Submissions routes for SoCa API."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from soca.auth import get_current_user
from soca.criteria import extract_text_from_file
from soca.db import db
from soca.models import Submission, UpdateSubmissionRequest, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


@router.get("", response_model=list[Submission])
async def list_submissions(current_user: User = Depends(get_current_user)) -> list[Submission]:
    """List all submissions."""
    submissions: list[Submission] = await db.list_submissions()
    return submissions


@router.post("", response_model=Submission)
async def create_submission(
    file: UploadFile = File(...),
    name: Optional[str] = None,
    description: Optional[str] = None,
    current_user: User = Depends(get_current_user),
) -> Submission:
    """Upload a new submission."""
    content = await file.read()
    file_size = len(content)

    # Extract text using the comprehensive extraction function
    extracted_text = ""
    try:
        extracted_text = await extract_text_from_file(
            content=content,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename or "file",
        )
    except ValueError as e:
        # Log but don't fail - store empty text for unsupported types
        logger.warning(f"Text extraction failed: {e}")

    # For demo, store file URL as placeholder
    # In production, upload to Azure Blob Storage
    file_url = f"/files/{uuid.uuid4()}/{file.filename}"

    submission = Submission(
        id=str(uuid.uuid4()),
        name=name or file.filename or "Untitled",
        description=description,
        file_url=file_url,
        file_name=file.filename or "file",
        file_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        extracted_text=extracted_text[:10000],  # Limit text size
        uploaded_at=datetime.utcnow().isoformat() + "Z",
    )

    return await db.create_submission(submission)


@router.delete("/{submission_id}")
async def delete_submission(
    submission_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a submission."""
    success = await db.delete_submission(submission_id)
    if not success:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"status": "deleted"}


@router.patch("/{submission_id}", response_model=Submission)
async def update_submission(
    submission_id: str,
    request: UpdateSubmissionRequest,
    current_user: User = Depends(get_current_user),
) -> Submission:
    """Update a submission's metadata."""
    existing = await db.get_submission(submission_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Update only provided fields
    updated = Submission(
        id=existing.id,
        name=request.name if request.name is not None else existing.name,
        description=request.description
        if request.description is not None
        else existing.description,
        file_url=existing.file_url,
        file_name=existing.file_name,
        file_type=existing.file_type,
        file_size=existing.file_size,
        extracted_text=existing.extracted_text,
        uploaded_at=existing.uploaded_at,
    )
    return await db.update_submission(updated)
