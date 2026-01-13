"""Data models for the SoCa evaluator pipeline.

This module defines the dataclasses used by the evaluation pipeline.
"""

from dataclasses import dataclass, field
from typing import Any

from autogen_core import CancellationToken

from ingen_prompt_tuner.models import AgentContribution


@dataclass
class EvaluationContext:
    """Context data for evaluation pipeline."""

    submission_name: str
    submission_content: str
    criteria_text: str
    revision: str
    model_client: Any
    cancellation_token: CancellationToken


@dataclass
class AgentResult:
    """Result from a single agent execution."""

    output: str
    tokens: int
    agent_name: str
    display_name: str
    system_prompt: str
    user_prompt: str
    execution_time_ms: int


@dataclass
class PipelineState:
    """Mutable state for the evaluation pipeline."""

    total_tokens: int = 0
    agent_contributions: list[AgentContribution] = field(default_factory=list)
    agents_trace_data: list[dict[str, Any]] = field(default_factory=list)
