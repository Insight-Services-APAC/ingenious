"""Prompt CRUD operations.

This module handles creating, reading, updating prompts.
"""

from ingen_prompt_tuner.models import Prompt
from ingen_prompt_tuner.prompts.constants import (
    CRITERIA_EVALUATOR_SYSTEM_PROMPT,
    CRITERIA_EVALUATOR_USER_PROMPT,
    CRITERIA_GENERATOR_SYSTEM_PROMPT,
    CRITERIA_GENERATOR_USER_PROMPT,
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

# In-memory storage for edited prompts
_edited_prompts: dict[str, dict[str, str]] = {}


def _get_base_prompts() -> list[Prompt]:
    """Get base prompt templates for SoCa 6-agent pipeline and criteria generator."""
    return [
        # Agent 1: Submission Evaluator
        Prompt(
            filename="submission_evaluator_system.md",
            description="System prompt for Submission Evaluator agent",
            content=SUBMISSION_EVALUATOR_SYSTEM_PROMPT,
            size=len(SUBMISSION_EVALUATOR_SYSTEM_PROMPT),
            tags=["system", "submission", "phase1"],
            variables=[],
        ),
        Prompt(
            filename="submission_evaluator_user.md",
            description="User prompt template for Submission Evaluator agent",
            content=SUBMISSION_EVALUATOR_USER_PROMPT,
            size=len(SUBMISSION_EVALUATOR_USER_PROMPT),
            tags=["user", "submission", "phase1"],
            variables=["submission_name", "submission_content"],
        ),
        # Agent 2: Criteria Evaluator
        Prompt(
            filename="criteria_evaluator_system.md",
            description="System prompt for Criteria Evaluator agent",
            content=CRITERIA_EVALUATOR_SYSTEM_PROMPT,
            size=len(CRITERIA_EVALUATOR_SYSTEM_PROMPT),
            tags=["system", "criteria", "phase1"],
            variables=[],
        ),
        Prompt(
            filename="criteria_evaluator_user.md",
            description="User prompt template for Criteria Evaluator agent",
            content=CRITERIA_EVALUATOR_USER_PROMPT,
            size=len(CRITERIA_EVALUATOR_USER_PROMPT),
            tags=["user", "criteria", "phase1"],
            variables=["criteria_text"],
        ),
        # Agent 3: Next Steps Agent
        Prompt(
            filename="next_steps_system.md",
            description="System prompt for Next Steps Agent",
            content=NEXT_STEPS_SYSTEM_PROMPT,
            size=len(NEXT_STEPS_SYSTEM_PROMPT),
            tags=["system", "nextsteps", "phase1"],
            variables=[],
        ),
        Prompt(
            filename="next_steps_user.md",
            description="User prompt template for Next Steps Agent",
            content=NEXT_STEPS_USER_PROMPT,
            size=len(NEXT_STEPS_USER_PROMPT),
            tags=["user", "nextsteps", "phase1"],
            variables=["submission_name", "submission_content"],
        ),
        # Agent 4: Scoring Agent
        Prompt(
            filename="scoring_agent_system.md",
            description="System prompt for Scoring Agent",
            content=SCORING_AGENT_SYSTEM_PROMPT,
            size=len(SCORING_AGENT_SYSTEM_PROMPT),
            tags=["system", "scoring", "phase2"],
            variables=[],
        ),
        Prompt(
            filename="scoring_agent_user.md",
            description="User prompt template for Scoring Agent",
            content=SCORING_AGENT_USER_PROMPT,
            size=len(SCORING_AGENT_USER_PROMPT),
            tags=["user", "scoring", "phase2"],
            variables=["submission_analysis", "criteria_analysis", "next_steps", "criteria_text"],
        ),
        # Agent 5: Summarizer Agent
        Prompt(
            filename="summarizer_agent_system.md",
            description="System prompt for Summarizer Agent",
            content=SUMMARIZER_AGENT_SYSTEM_PROMPT,
            size=len(SUMMARIZER_AGENT_SYSTEM_PROMPT),
            tags=["system", "summarizer", "phase3"],
            variables=[],
        ),
        Prompt(
            filename="summarizer_agent_user.md",
            description="User prompt template for Summarizer Agent",
            content=SUMMARIZER_AGENT_USER_PROMPT,
            size=len(SUMMARIZER_AGENT_USER_PROMPT),
            tags=["user", "summarizer", "phase3"],
            variables=["scores", "submission_name"],
        ),
        # Agent 6: Sanity Check Agent
        Prompt(
            filename="sanity_check_system.md",
            description="System prompt for Sanity Check Agent",
            content=SANITY_CHECK_SYSTEM_PROMPT,
            size=len(SANITY_CHECK_SYSTEM_PROMPT),
            tags=["system", "sanity", "phase4"],
            variables=[],
        ),
        Prompt(
            filename="sanity_check_user.md",
            description="User prompt template for Sanity Check Agent",
            content=SANITY_CHECK_USER_PROMPT,
            size=len(SANITY_CHECK_USER_PROMPT),
            tags=["user", "sanity", "phase4"],
            variables=["summary", "scores", "criteria_text"],
        ),
        # Criteria Generator (separate workflow)
        Prompt(
            filename="criteria_generator_system.md",
            description="System prompt for extracting evaluation criteria from documents",
            content=CRITERIA_GENERATOR_SYSTEM_PROMPT,
            size=len(CRITERIA_GENERATOR_SYSTEM_PROMPT),
            tags=["system", "criteria", "generator"],
            variables=[],
        ),
        Prompt(
            filename="criteria_generator_user.md",
            description="User prompt template for criteria generation from documents",
            content=CRITERIA_GENERATOR_USER_PROMPT,
            size=len(CRITERIA_GENERATOR_USER_PROMPT),
            tags=["user", "criteria", "generator"],
            variables=["document_text"],
        ),
    ]


def copy_prompts_to_revision(target_revision: str, source_revision: str) -> None:
    """Copy prompts from source revision to target revision."""
    source_prompts = get_prompts(source_revision)
    _edited_prompts[target_revision] = {}
    for prompt in source_prompts:
        _edited_prompts[target_revision][prompt.filename] = prompt.content


def get_prompts(revision: str) -> list[Prompt]:
    """Get prompts for a revision, with any edits applied."""
    prompts = []
    for base_prompt in _get_base_prompts():
        # Check if there's an edited version
        if revision in _edited_prompts and base_prompt.filename in _edited_prompts[revision]:
            edited_content = _edited_prompts[revision][base_prompt.filename]
            prompts.append(
                Prompt(
                    filename=base_prompt.filename,
                    description=base_prompt.description,
                    content=edited_content,
                    size=len(edited_content),
                    tags=base_prompt.tags,
                    variables=base_prompt.variables,
                )
            )
        else:
            prompts.append(base_prompt)
    return prompts


def get_prompt(revision: str, filename: str) -> Prompt | None:
    """Get a specific prompt with any edits applied."""
    prompts = get_prompts(revision)
    for prompt in prompts:
        if prompt.filename == filename:
            return prompt
    return None


def update_prompt(revision: str, filename: str, content: str) -> bool:
    """Update a prompt's content."""
    if revision not in _edited_prompts:
        _edited_prompts[revision] = {}
    _edited_prompts[revision][filename] = content
    return True
