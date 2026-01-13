"""ConversationFlow class for SoCa evaluation.

This module contains the main ConversationFlow class that orchestrates
the 6-agent evaluation pipeline.
"""

import json
import logging
import uuid
from typing import Any, Optional

from autogen_core import EVENT_LOGGER_NAME, CancellationToken

import ingenious.config.config as config
from ingen_prompt_tuner.conversation_flows.soca_evaluator.models import (
    EvaluationContext,
    PipelineState,
)
from ingen_prompt_tuner.conversation_flows.soca_evaluator.pipeline import (
    build_error_response,
    build_final_response,
    run_phase1,
    run_sequential_agent,
)
from ingen_prompt_tuner.prompts import (
    get_sanity_check_prompts,
    get_scoring_agent_prompts,
    get_summarizer_agent_prompts,
)
from ingenious.client.azure.builder.openai_chat_completions_client import (
    AzureOpenAIChatCompletionClientBuilder,
)
from ingenious.models.agent import LLMUsageTracker
from ingenious.models.chat import ChatRequest


class ConversationFlow:
    """Conversation flow for SoCa document evaluation using 6-agent pipeline."""

    @staticmethod
    async def get_conversation_response(
        message: str,
        topics: Optional[list[str]] = None,
        thread_memory: str = "",
        memory_record_switch: bool = True,
        thread_chat_history: Optional[list[dict[str, Any]]] = None,
        chatrequest: Optional[ChatRequest] = None,
        revision: str = "active",
    ) -> tuple[str, str, int, str]:
        """Get an evaluation response using the 6-agent pipeline."""
        if chatrequest:
            message = chatrequest.user_prompt
            _ = chatrequest.topic if chatrequest.topic else topics

        _config = config.get_config()
        model_config = _config.models[0]

        logger = logging.getLogger(EVENT_LOGGER_NAME)
        logger.setLevel(logging.INFO)
        logger.handlers = [
            LLMUsageTracker(
                agents=[
                    "submission_evaluator",
                    "criteria_evaluator",
                    "next_steps",
                    "scoring_agent",
                    "summarizer_agent",
                    "sanity_check",
                ],
                config=_config,
                chat_history_repository=None,
                revision_id=str(uuid.uuid4()),
                identifier=str(uuid.uuid4()),
                event_type="evaluation",
            )
        ]

        try:
            input_data = json.loads(message)
            submission_name = input_data.get("submission_name", "Untitled")
            submission_content = input_data.get("submission_content", message)
            criteria_text = input_data.get("criteria_text", "")
        except json.JSONDecodeError:
            submission_name = "Untitled"
            submission_content = message
            criteria_text = ""

        builder = AzureOpenAIChatCompletionClientBuilder(model_config)
        model_client = builder.build()

        ctx = EvaluationContext(
            submission_name=submission_name,
            submission_content=submission_content,
            criteria_text=criteria_text,
            revision=revision,
            model_client=model_client,
            cancellation_token=CancellationToken(),
        )
        state = PipelineState()

        try:
            submission_analysis, criteria_analysis, next_steps_output = await run_phase1(ctx, state)

            scoring_output = await run_sequential_agent(
                ctx,
                state,
                "scoring_agent",
                "Scoring Agent",
                get_scoring_agent_prompts,
                {
                    "submission_analysis": submission_analysis,
                    "criteria_analysis": criteria_analysis,
                    "next_steps": next_steps_output,
                    "criteria_text": criteria_text,
                },
                phase=2,
                order=4,
                input_summary="Combined Phase 1 outputs for scoring",
            )

            summary_output = await run_sequential_agent(
                ctx,
                state,
                "summarizer_agent",
                "Summarizer Agent",
                get_summarizer_agent_prompts,
                {"scores": scoring_output, "submission_name": submission_name},
                phase=3,
                order=5,
                input_summary="Created summary from scoring results",
            )

            sanity_output = await run_sequential_agent(
                ctx,
                state,
                "sanity_check",
                "Sanity Check Agent",
                get_sanity_check_prompts,
                {
                    "summary": summary_output,
                    "scores": scoring_output,
                    "criteria_text": criteria_text,
                },
                phase=4,
                order=6,
                input_summary="Validated evaluation for consistency",
            )

            result_json, validation_status = build_final_response(
                sanity_output, summary_output, next_steps_output, state.agent_contributions
            )
            memory_summary = f"6-agent evaluation completed. Validation: {validation_status}"

        except Exception as e:
            result_json, memory_summary = build_error_response(e, state.agent_contributions)

        finally:
            await model_client.close()

        agents_info = json.dumps(
            {
                "pipeline": "6-agent",
                "phases": 4,
                "agents": [
                    "Submission Evaluator",
                    "Criteria Evaluator",
                    "Next Steps Agent",
                    "Scoring Agent",
                    "Summarizer Agent",
                    "Sanity Check Agent",
                ],
                "total_tokens": state.total_tokens,
                "agents_trace_data": state.agents_trace_data,
            }
        )

        return result_json, memory_summary, state.total_tokens, agents_info
