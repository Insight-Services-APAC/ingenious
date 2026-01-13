"""Agent prompt getter functions.

This module provides convenient functions to get prompts for each agent.
"""

from ingen_prompt_tuner.prompts.constants import (
    CRITERIA_EVALUATOR_SYSTEM_PROMPT,
    CRITERIA_EVALUATOR_USER_PROMPT,
    CRITERIA_GENERATOR_SYSTEM_PROMPT,
    NEXT_STEPS_SYSTEM_PROMPT,
    NEXT_STEPS_USER_PROMPT,
    SANITY_CHECK_SYSTEM_PROMPT,
    SANITY_CHECK_USER_PROMPT,
    SCORING_AGENT_SYSTEM_PROMPT,
    SCORING_AGENT_USER_PROMPT,
    SUBMISSION_EVALUATOR_SYSTEM_PROMPT,
    SUBMISSION_EVALUATOR_USER_PROMPT,
    SUMMARIZER_AGENT_SYSTEM_PROMPT,
    SUMMARIZER_AGENT_USER_PROMPT,
)
from ingen_prompt_tuner.prompts.crud import get_prompt


def get_agent_prompts(agent_name: str, revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for a specific agent.

    Args:
        agent_name: One of 'submission_evaluator', 'criteria_evaluator',
                   'next_steps', 'scoring_agent', 'summarizer_agent', 'sanity_check'
        revision: Prompt revision to use

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    agent_files = {
        "submission_evaluator": ("submission_evaluator_system.md", "submission_evaluator_user.md"),
        "criteria_evaluator": ("criteria_evaluator_system.md", "criteria_evaluator_user.md"),
        "next_steps": ("next_steps_system.md", "next_steps_user.md"),
        "scoring_agent": ("scoring_agent_system.md", "scoring_agent_user.md"),
        "summarizer_agent": ("summarizer_agent_system.md", "summarizer_agent_user.md"),
        "sanity_check": ("sanity_check_system.md", "sanity_check_user.md"),
    }

    if agent_name not in agent_files:
        raise ValueError(f"Unknown agent: {agent_name}")

    system_file, user_file = agent_files[agent_name]
    system_prompt = get_prompt(revision, system_file)
    user_prompt = get_prompt(revision, user_file)

    # Fall back to defaults if not found
    defaults = {
        "submission_evaluator": (
            SUBMISSION_EVALUATOR_SYSTEM_PROMPT,
            SUBMISSION_EVALUATOR_USER_PROMPT,
        ),
        "criteria_evaluator": (CRITERIA_EVALUATOR_SYSTEM_PROMPT, CRITERIA_EVALUATOR_USER_PROMPT),
        "next_steps": (NEXT_STEPS_SYSTEM_PROMPT, NEXT_STEPS_USER_PROMPT),
        "scoring_agent": (SCORING_AGENT_SYSTEM_PROMPT, SCORING_AGENT_USER_PROMPT),
        "summarizer_agent": (SUMMARIZER_AGENT_SYSTEM_PROMPT, SUMMARIZER_AGENT_USER_PROMPT),
        "sanity_check": (SANITY_CHECK_SYSTEM_PROMPT, SANITY_CHECK_USER_PROMPT),
    }

    system_content = system_prompt.content if system_prompt else defaults[agent_name][0]
    user_content = user_prompt.content if user_prompt else defaults[agent_name][1]

    return system_content, user_content


def get_submission_evaluator_prompts(revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for Submission Evaluator agent."""
    return get_agent_prompts("submission_evaluator", revision)


def get_criteria_evaluator_prompts(revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for Criteria Evaluator agent."""
    return get_agent_prompts("criteria_evaluator", revision)


def get_next_steps_prompts(revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for Next Steps agent."""
    return get_agent_prompts("next_steps", revision)


def get_scoring_agent_prompts(revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for Scoring Agent."""
    return get_agent_prompts("scoring_agent", revision)


def get_summarizer_agent_prompts(revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for Summarizer Agent."""
    return get_agent_prompts("summarizer_agent", revision)


def get_sanity_check_prompts(revision: str = "active") -> tuple[str, str]:
    """Get system and user prompts for Sanity Check Agent."""
    return get_agent_prompts("sanity_check", revision)


def get_criteria_generator_system_prompt(revision: str = "active") -> str:
    """Get the current criteria generator system prompt.

    This is used by the chat endpoint to get the configurable system prompt
    for criteria generation from documents.
    """
    prompt = get_prompt(revision, "criteria_generator_system.md")
    if prompt:
        return prompt.content
    return CRITERIA_GENERATOR_SYSTEM_PROMPT
