"""RFC 7807 Problem Details model for standardized error responses.

This module provides the ProblemDetail model following RFC 7807 specification
for HTTP API problem details. It ensures consistent, machine-readable error
responses across the application.

Reference: https://tools.ietf.org/html/rfc7807
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs.

    Attributes:
        type: URI reference identifying the problem type. When dereferenced,
            it should provide human-readable documentation.
        title: Short, human-readable summary of the problem type.
        status: HTTP status code for this occurrence of the problem.
        detail: Human-readable explanation specific to this occurrence.
        instance: URI reference identifying the specific occurrence.
        correlation_id: Request correlation ID for tracing across systems.
        timestamp: ISO 8601 timestamp when the error occurred.
        recoverable: Whether the error can potentially be recovered from.
        recovery_suggestion: Suggestion for how to recover from this error.
    """

    type: str = Field(
        ...,
        description="URI reference identifying the problem type",
        examples=["https://docs.ingenious.dev/errors/VALIDATION_ERROR"],
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the problem type",
        examples=["ValidationError"],
    )
    status: int = Field(
        ...,
        description="HTTP status code for this occurrence",
        ge=400,
        le=599,
        examples=[400],
    )
    detail: Optional[str] = Field(
        None,
        description="Human-readable explanation specific to this occurrence",
        examples=["conversation_flow is required"],
    )
    instance: Optional[str] = Field(
        None,
        description="URI reference identifying the specific occurrence",
        examples=["/api/v1/chat"],
    )
    correlation_id: Optional[str] = Field(
        None,
        description="Request correlation ID for tracing",
        examples=["abc123-def456"],
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when the error occurred",
        examples=["2025-01-15T10:30:00Z"],
    )
    recoverable: Optional[bool] = Field(
        None,
        description="Whether this error can potentially be recovered from",
        examples=[True],
    )
    recovery_suggestion: Optional[str] = Field(
        None,
        description="Suggestion for how to recover from this error",
        examples=["Check the API documentation and ensure all required fields are provided"],
    )

    class Config:
        """Pydantic model configuration."""

        json_schema_extra = {
            "example": {
                "type": "https://docs.ingenious.dev/errors/VALIDATION_ERROR",
                "title": "ValidationError",
                "status": 400,
                "detail": "conversation_flow is required",
                "instance": "/api/v1/chat",
                "correlation_id": "abc123-def456",
                "timestamp": "2025-01-15T10:30:00Z",
                "recoverable": True,
                "recovery_suggestion": "Provide the conversation_flow field in your request",
            }
        }
