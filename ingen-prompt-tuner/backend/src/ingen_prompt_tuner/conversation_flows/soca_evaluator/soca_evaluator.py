"""SoCa evaluator conversation flow implementation with 6-agent pipeline.

This module provides a conversation flow for evaluating submissions against
criteria using a multi-agent pipeline:

Phase 1 (Parallel):
  - Submission Evaluator: Analyzes submission content
  - Criteria Evaluator: Parses criteria into rubrics
  - Next Steps Agent: Identifies improvement areas

Phase 2 (Sequential):
  - Scoring Agent: Scores against criteria using Phase 1 outputs

Phase 3 (Sequential):
  - Summarizer Agent: Creates executive summary

Phase 4 (Sequential):
  - Sanity Check Agent: Validates consistency and completeness
"""

# Re-export the ConversationFlow class for backward compatibility
from ingen_prompt_tuner.conversation_flows.soca_evaluator.flow import ConversationFlow

# Re-export models for any direct imports
from ingen_prompt_tuner.conversation_flows.soca_evaluator.models import (
    AgentResult,
    EvaluationContext,
    PipelineState,
)

__all__ = [
    "ConversationFlow",
    "EvaluationContext",
    "AgentResult",
    "PipelineState",
]
