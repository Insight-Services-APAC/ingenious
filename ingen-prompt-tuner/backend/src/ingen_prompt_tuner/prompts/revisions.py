"""Revision management for prompts.

This module handles creation and retrieval of prompt revisions.
"""

from datetime import datetime

from ingen_prompt_tuner.models import Revision

# In-memory revision storage
_revisions: dict[str, Revision] = {
    "active": Revision(
        id="active",
        name="active",
        created_at="2024-01-15T10:00:00Z",
        prompt_count=14,  # 12 for 6 agents + 2 for criteria generator
    ),
}


def get_revisions() -> list[Revision]:
    """Get all revisions."""
    return list(_revisions.values())


def get_revision(revision_id: str) -> Revision | None:
    """Get a specific revision by ID."""
    return _revisions.get(revision_id)


def revision_exists(revision_id: str) -> bool:
    """Check if a revision exists."""
    return revision_id in _revisions


def create_revision(name: str, copy_from: str | None = None) -> Revision:
    """Create a new revision, optionally copying prompts from an existing revision.

    Args:
        name: Name for the new revision
        copy_from: Optional revision ID to copy prompts from

    Returns:
        The newly created Revision

    Raises:
        ValueError: If revision already exists
    """
    from ingen_prompt_tuner.prompts.crud import copy_prompts_to_revision

    # Check if revision already exists
    if name in _revisions:
        raise ValueError(f"Revision '{name}' already exists")

    # Create the new revision
    new_revision = Revision(
        id=name,
        name=name,
        created_at=datetime.utcnow().isoformat() + "Z",
        prompt_count=14,  # 12 for 6 agents + 2 for criteria generator
    )
    _revisions[name] = new_revision

    # Copy prompts from source revision if specified
    if copy_from and copy_from in _revisions:
        copy_prompts_to_revision(name, copy_from)

    return new_revision
