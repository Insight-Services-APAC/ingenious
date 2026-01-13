"""Utility functions for the SoCa evaluator pipeline.

This module contains helper functions for JSON processing, template rendering,
and agent execution.
"""

from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from jinja2 import Template

from ingen_prompt_tuner.conversation_flows.soca_evaluator.models import (
    AgentResult,
    PipelineState,
)
from ingen_prompt_tuner.models import AgentContribution


def clean_json_response(text: str) -> str:
    """Clean markdown formatting from JSON response."""
    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return clean.strip()


def render_template(template_str: str, variables: dict[str, Any]) -> str:
    """Render a Jinja2 template with variables."""
    template = Template(template_str)
    return template.render(**variables)


def truncate_output(output: str, max_len: int = 200) -> str:
    """Truncate output for summary display."""
    return output[:max_len] + "..." if len(output) > max_len else output


async def run_agent(
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
    model_client: Any,
    cancellation_token: CancellationToken,
) -> tuple[str, int]:
    """Run a single agent and return its response and token count."""
    agent = AssistantAgent(
        name=agent_name,
        system_message=system_prompt,
        model_client=model_client,
    )

    response = await agent.on_messages(
        messages=[TextMessage(content=user_prompt, source="user")],
        cancellation_token=cancellation_token,
    )

    chat_msg = response.chat_message
    result_text = str(chat_msg.content) if hasattr(chat_msg, "content") else "{}"

    token_count = 0
    if hasattr(chat_msg, "models_usage") and chat_msg.models_usage is not None:
        usage = chat_msg.models_usage
        token_count = getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0)

    return clean_json_response(result_text), token_count


def record_agent_result(
    state: PipelineState,
    result: AgentResult,
    phase: int,
    order: int,
    input_summary: str,
) -> None:
    """Record agent result in pipeline state."""
    state.total_tokens += result.tokens
    state.agent_contributions.append(
        AgentContribution(
            agent_name=result.display_name,
            phase=phase,
            input_summary=input_summary,
            output_summary=truncate_output(result.output),
            token_count=result.tokens,
            execution_time_ms=result.execution_time_ms,
        )
    )
    state.agents_trace_data.append(
        {
            "agent_name": result.display_name,
            "order": order,
            "input": result.user_prompt,
            "output": result.output,
            "token_usage": result.tokens,
            "system_prompt": result.system_prompt,
            "user_prompt": result.user_prompt,
        }
    )
