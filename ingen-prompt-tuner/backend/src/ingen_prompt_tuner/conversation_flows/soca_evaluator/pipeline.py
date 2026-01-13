"""Pipeline execution for the SoCa evaluator.

This module handles the 4-phase evaluation pipeline:
- Phase 1: Parallel analysis agents
- Phase 2: Scoring agent
- Phase 3: Summarizer agent
- Phase 4: Sanity check agent
"""

import asyncio
import json
import logging
import time
from typing import Any

from ingen_prompt_tuner.conversation_flows.soca_evaluator.models import (
    AgentResult,
    EvaluationContext,
    PipelineState,
)
from ingen_prompt_tuner.conversation_flows.soca_evaluator.utils import (
    record_agent_result,
    render_template,
    run_agent,
)
from ingen_prompt_tuner.models import (
    AgentContribution,
    CriterionResultSchema,
    EvaluationResponseSchema,
)
from ingen_prompt_tuner.prompts import (
    get_criteria_evaluator_prompts,
    get_next_steps_prompts,
    get_submission_evaluator_prompts,
)


async def run_phase1(ctx: EvaluationContext, state: PipelineState) -> tuple[str, str, str]:
    """Run Phase 1: Parallel analysis agents."""
    logging.info("Phase 1: Running parallel analysis agents")
    phase_start = time.time()

    sub_sys, sub_user = get_submission_evaluator_prompts(ctx.revision)
    crit_sys, crit_user = get_criteria_evaluator_prompts(ctx.revision)
    next_sys, next_user = get_next_steps_prompts(ctx.revision)

    sub_user_rendered = render_template(
        sub_user,
        {"submission_name": ctx.submission_name, "submission_content": ctx.submission_content},
    )
    crit_user_rendered = render_template(crit_user, {"criteria_text": ctx.criteria_text})
    next_user_rendered = render_template(
        next_user,
        {"submission_name": ctx.submission_name, "submission_content": ctx.submission_content},
    )

    results = await asyncio.gather(
        run_agent(
            "submission_evaluator",
            sub_sys,
            sub_user_rendered,
            ctx.model_client,
            ctx.cancellation_token,
        ),
        run_agent(
            "criteria_evaluator",
            crit_sys,
            crit_user_rendered,
            ctx.model_client,
            ctx.cancellation_token,
        ),
        run_agent(
            "next_steps", next_sys, next_user_rendered, ctx.model_client, ctx.cancellation_token
        ),
        return_exceptions=True,
    )

    phase_time = int((time.time() - phase_start) * 1000)
    agent_time = phase_time // 3

    agent_configs = [
        (
            "submission_evaluator",
            "Submission Evaluator",
            sub_sys,
            sub_user_rendered,
            "Analyzed submission",
        ),
        (
            "criteria_evaluator",
            "Criteria Evaluator",
            crit_sys,
            crit_user_rendered,
            "Analyzed criteria",
        ),
        ("next_steps", "Next Steps Agent", next_sys, next_user_rendered, "Analyzed improvements"),
    ]

    outputs = ["{}", "{}", "{}"]
    for i, (agent_result, agent_cfg) in enumerate(zip(results, agent_configs)):
        agent_name, display_name, sys_prompt, user_prompt, input_summary = agent_cfg

        if isinstance(agent_result, BaseException):
            logging.error(f"{agent_name} failed: {agent_result}")
            output, tokens = json.dumps({"error": str(agent_result)}), 0
        else:
            output, tokens = agent_result

        outputs[i] = output
        record_agent_result(
            state,
            AgentResult(
                output, tokens, agent_name, display_name, sys_prompt, user_prompt, agent_time
            ),
            phase=1,
            order=i + 1,
            input_summary=input_summary,
        )

    return outputs[0], outputs[1], outputs[2]


async def run_sequential_agent(
    ctx: EvaluationContext,
    state: PipelineState,
    agent_name: str,
    display_name: str,
    get_prompts_fn: Any,
    template_vars: dict[str, Any],
    phase: int,
    order: int,
    input_summary: str,
) -> str:
    """Run a sequential agent phase."""
    logging.info(f"Phase {phase}: Running {display_name}")
    phase_start = time.time()

    sys_prompt, user_prompt = get_prompts_fn(ctx.revision)
    user_rendered = render_template(user_prompt, template_vars)

    output, tokens = await run_agent(
        agent_name, sys_prompt, user_rendered, ctx.model_client, ctx.cancellation_token
    )
    phase_time = int((time.time() - phase_start) * 1000)

    record_agent_result(
        state,
        AgentResult(
            output, tokens, agent_name, display_name, sys_prompt, user_rendered, phase_time
        ),
        phase=phase,
        order=order,
        input_summary=input_summary,
    )

    return output


def extract_next_steps(sanity_output: dict[str, Any], next_steps_output: str) -> list[str]:
    """Extract next steps from sanity check or original next steps output."""
    final_output = sanity_output.get("final_output", {})
    next_steps_list: list[str] = final_output.get("nextSteps", [])

    if next_steps_list:
        return next_steps_list

    try:
        next_data = json.loads(next_steps_output)
        improvements = next_data.get("priority_improvements", [])
        return [imp.get("recommended_action", "") for imp in improvements[:5]]
    except (json.JSONDecodeError, KeyError):
        return []


def build_final_response(
    sanity_output: str,
    summary_output: str,
    next_steps_output: str,
    agent_contributions: list[AgentContribution],
) -> tuple[str, str]:
    """Build the final evaluation response JSON."""
    try:
        sanity_data = json.loads(sanity_output)
        final_output = sanity_data.get("final_output", {})
        validation_status = sanity_data.get("validation_status", "passed")

        criterion_results = [
            CriterionResultSchema(
                criterionId=cr.get("criterionId", ""),
                score=float(cr.get("score", 0)),
                narrative=cr.get("narrative", ""),
            )
            for cr in final_output.get("criterionResults", [])
        ]

        next_steps_list = extract_next_steps(sanity_data, next_steps_output)

        eval_response = EvaluationResponseSchema(
            criterionResults=criterion_results,
            overallScore=float(final_output.get("overallScore", 0)),
            summary=final_output.get("narrative", "Evaluation completed."),
            nextSteps=next_steps_list,
            agentContributions=agent_contributions,
            validationStatus=validation_status,
        )
        return eval_response.model_dump_json(), validation_status

    except (json.JSONDecodeError, KeyError) as e:
        logging.error(f"Failed to parse sanity check output: {e}")
        return build_fallback_response(summary_output, agent_contributions)


def build_fallback_response(
    summary_output: str,
    agent_contributions: list[AgentContribution],
) -> tuple[str, str]:
    """Build fallback response when sanity check parsing fails."""
    try:
        summary_data = json.loads(summary_output)
        eval_response = EvaluationResponseSchema(
            criterionResults=[],
            overallScore=float(summary_data.get("overallScore", 0)),
            summary=summary_data.get("overall_narrative", "Evaluation completed."),
            nextSteps=[],
            agentContributions=agent_contributions,
            validationStatus="flagged",
        )
        return eval_response.model_dump_json(), "flagged"
    except (json.JSONDecodeError, KeyError):
        error_response = {
            "criterionResults": [],
            "overallScore": 0,
            "summary": "Evaluation pipeline completed but output parsing failed.",
            "nextSteps": [],
            "agentContributions": [ac.model_dump() for ac in agent_contributions],
            "validationStatus": "flagged",
        }
        return json.dumps(error_response), "flagged"


def build_error_response(
    error: Exception, agent_contributions: list[AgentContribution]
) -> tuple[str, str]:
    """Build error response when pipeline fails."""
    logging.error(f"Evaluation pipeline failed: {error}")
    error_response = {
        "criterionResults": [],
        "overallScore": 0,
        "summary": f"Evaluation pipeline failed: {str(error)}",
        "nextSteps": [],
        "agentContributions": [ac.model_dump() for ac in agent_contributions],
        "validationStatus": "error",
    }
    return json.dumps(error_response), f"Evaluation error: {str(error)[:50]}..."
