"""Revision ID generation utilities.

This module provides utilities for generating revision IDs, including:
- GitHub Codespaces-style funny names with UUIDs
- User-supplied name conflict resolution with incremental numbering
- Name validation and normalization
"""

import random
import re
import uuid
from typing import Final

from ingenious.core.structured_logging import get_logger

logger = get_logger(__name__)

# Constants for validation
MAX_REVISION_ID_LENGTH: Final[int] = 50
UUID_SUFFIX_LENGTH: Final[int] = 8

# Pre-compiled regex patterns for performance
_MULTIPLE_HYPHENS_PATTERN: Final[re.Pattern[str]] = re.compile(r"-+")
_INVALID_CHARS_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9-]")

# TODO: Make a cleaner approach for these word lists (e.g. external file / loader)
# GitHub Codespaces-style word lists
ADJECTIVES: Final[tuple[str, ...]] = (
    "animated",
    "bouncy",
    "clever",
    "cosmic",
    "curvy",
    "dazzling",
    "electric",
    "fluffy",
    "fuzzy",
    "glowing",
    "happy",
    "jazzy",
    "kinetic",
    "lovely",
    "magical",
    "nimble",
    "quirky",
    "radiant",
    "shiny",
    "stellar",
    "turbo",
    "vibrant",
    "witty",
    "zesty",
)

NOUNS: Final[tuple[str, ...]] = (
    "disco",
    "ninja",
    "palm",
    "quantum",
    "rainbow",
    "space",
    "unicorn",
    "velvet",
    "wizard",
    "crystal",
    "golden",
    "silver",
    "emerald",
    "diamond",
    "ruby",
    "sapphire",
    "amber",
    "pearl",
    "jade",
    "onyx",
    "copper",
    "bronze",
    "platinum",
    "titanium",
)


def generate_funny_revision_id() -> str:
    """Generate a funny revision ID in GitHub Codespaces style.

    Format: <adjective>-<noun>-<short-uuid>
    Example: "cosmic-ninja-a1b2c3d4"

    Returns:
        str: A randomly generated funny revision ID with UUID suffix
    """
    adjective = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    # Use first 'UUID_SUFFIX_LENGTH' characters of UUID for brevity
    short_uuid = str(uuid.uuid4()).replace("-", "")[:UUID_SUFFIX_LENGTH]

    return f"{adjective}-{noun}-{short_uuid}"


def resolve_user_revision_id(revision_id: str, existing_revision_ids: list[str]) -> str:
    """Resolve user-supplied revision ID conflicts by adding incremental numbers.

    If the revision_id already exists, appends -1, -2, -3, etc. until finding
    an available ID.

    Args:
        revision_id: The desired revision ID from the user
        existing_revision_ids: List of existing revision IDs to check against

    Returns:
        str: The resolved revision ID (either original or with number suffix)

    Examples:
        resolve_user_revision_id("my-workflow", ["my-workflow"]) -> "my-workflow-1"
        resolve_user_revision_id("my-workflow", ["my-workflow", "my-workflow-1"]) -> "my-workflow-2"
    """
    if not revision_id:
        raise ValueError("Revision ID cannot be empty")

    # Convert to set for O(1) membership checks
    existing_ids_set = set(existing_revision_ids)

    # Normalize the revision ID (lowercase, replace underscores with hyphens)
    normalized_id = normalize_revision_id(revision_id)

    # If the ID doesn't conflict, use it as-is (O(1) lookup)
    if normalized_id not in existing_ids_set:
        logger.debug(
            "User revision ID available",
            original_revision_id=revision_id,
            resolved_id=normalized_id,
        )
        return normalized_id

    # Use while loop with O(1) set membership checks to find next available number
    candidate_number = 1
    while f"{normalized_id}-{candidate_number}" in existing_ids_set:
        candidate_number += 1

    resolved_id = f"{normalized_id}-{candidate_number}"

    logger.debug(
        "Resolved user revision ID conflict",
        original_revision_id=revision_id,
        normalized_id=normalized_id,
        resolved_id=resolved_id,
        candidate_number=candidate_number,
    )

    return resolved_id


def normalize_revision_id(name: str) -> str:
    """Normalize a revision ID to follow consistent naming conventions.

    Rules:
    - Convert to lowercase
    - Replace underscores with hyphens
    - Remove any invalid characters (keep only alphanumeric, hyphens)
    - Ensure it doesn't start or end with a hyphen
    - Validate maximum length constraint

    Args:
        name: The revision ID to normalize

    Returns:
        str: The normalized revision ID

    Raises:
        ValueError: If the name is empty, becomes empty after normalization,
                   or exceeds maximum length
    """
    if not name or not name.strip():
        raise ValueError("Revision ID cannot be empty")

    # Convert to lowercase and replace underscores with hyphens
    normalized = name.lower().replace("_", "-")

    # Keep only alphanumeric characters and hyphens
    normalized = _INVALID_CHARS_PATTERN.sub("", normalized)

    # Remove leading/trailing hyphens and collapse multiple hyphens
    normalized = _MULTIPLE_HYPHENS_PATTERN.sub("-", normalized).strip("-")

    if not normalized:
        raise ValueError(f"Revision ID '{name}' contains no valid characters")

    # Validate maximum length constraint
    if len(normalized) > MAX_REVISION_ID_LENGTH:
        raise ValueError(
            f"Revision ID '{normalized}' exceeds maximum length of {MAX_REVISION_ID_LENGTH} characters (got {len(normalized)})"
        )

    logger.debug(
        "Normalized revision ID",
        original_name=name,
        normalized_id=normalized,
    )

    return normalized


def generate_revision_id(revision_id: str | None, existing_revision_ids: list[str]) -> str:
    """Generate a revision ID based on user input or create a funny name.

    Args:
        revision_id: Optional user-supplied revision ID
        existing_revision_ids: List of existing revision IDs to check conflicts

    Returns:
        str: The final revision ID to use

    Raises:
        ValueError: If revision_id is provided but invalid
    """
    if revision_id:
        # User provided an ID - resolve any conflicts
        return resolve_user_revision_id(revision_id, existing_revision_ids)
    else:
        # Generate a funny name (UUID makes collisions virtually impossible)
        return generate_funny_revision_id()
