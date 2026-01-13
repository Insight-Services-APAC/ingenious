"""Prompts module for managing AI agent prompts.

This module defines the 6-agent evaluation pipeline prompts:
1. Submission Evaluator - Analyzes submission content
2. Criteria Evaluator - Parses evaluation criteria
3. Next Steps Agent - Identifies improvement areas
4. Scoring Agent - Scores against criteria
5. Summarizer Agent - Creates evaluation summary
6. Sanity Check Agent - Validates consistency
"""

# Re-export constants
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

# Re-export CRUD functions
from ingen_prompt_tuner.prompts.crud import (
    get_prompt,
    get_prompts,
    update_prompt,
)

# Re-export getter functions
from ingen_prompt_tuner.prompts.getters import (
    get_agent_prompts,
    get_criteria_evaluator_prompts,
    get_criteria_generator_system_prompt,
    get_next_steps_prompts,
    get_sanity_check_prompts,
    get_scoring_agent_prompts,
    get_submission_evaluator_prompts,
    get_summarizer_agent_prompts,
)

# Re-export revision functions
from ingen_prompt_tuner.prompts.revisions import (
    create_revision,
    get_revision,
    get_revisions,
    revision_exists,
)

__all__ = [
    # Constants
    "SUBMISSION_EVALUATOR_SYSTEM_PROMPT",
    "SUBMISSION_EVALUATOR_USER_PROMPT",
    "CRITERIA_EVALUATOR_SYSTEM_PROMPT",
    "CRITERIA_EVALUATOR_USER_PROMPT",
    "NEXT_STEPS_SYSTEM_PROMPT",
    "NEXT_STEPS_USER_PROMPT",
    "SCORING_AGENT_SYSTEM_PROMPT",
    "SCORING_AGENT_USER_PROMPT",
    "SUMMARIZER_AGENT_SYSTEM_PROMPT",
    "SUMMARIZER_AGENT_USER_PROMPT",
    "SANITY_CHECK_SYSTEM_PROMPT",
    "SANITY_CHECK_USER_PROMPT",
    "CRITERIA_GENERATOR_SYSTEM_PROMPT",
    "CRITERIA_GENERATOR_USER_PROMPT",
    # Revision functions
    "get_revisions",
    "get_revision",
    "revision_exists",
    "create_revision",
    # CRUD functions
    "get_prompts",
    "get_prompt",
    "update_prompt",
    # Getter functions
    "get_agent_prompts",
    "get_submission_evaluator_prompts",
    "get_criteria_evaluator_prompts",
    "get_next_steps_prompts",
    "get_scoring_agent_prompts",
    "get_summarizer_agent_prompts",
    "get_sanity_check_prompts",
    "get_criteria_generator_system_prompt",
]
