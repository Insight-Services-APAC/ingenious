"""Token limit exceeded error exception.

This module defines exceptions raised when token limits are exceeded during chat operations.
"""

from ingenious.errors.base_error import IngeniousError
from ingenious.errors.enums import ErrorCategory, ErrorSeverity


class TokenLimitExceededError(IngeniousError):
    """Exception raised when user has exceeded OpenAI token limit.

    Attributes:
        DEFAULT_MESSAGE (str): Default error message for token limit exceeded.
        max_context_length (int): Maximum allowed context length.
        requested_tokens (int): Number of tokens requested.
        prompt_tokens (int): Number of tokens in prompt.
        completion_tokens (int): Number of tokens in completion.
    """

    DEFAULT_MESSAGE = "This chat has exceeded the token limit, please start a new conversation."

    def __init__(
        self,
        message: str = DEFAULT_MESSAGE,
        max_context_length: int = 0,
        requested_tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        **kwargs,
    ) -> None:
        """Initialize token limit exceeded error.

        Args:
            message (str): Error message, defaults to DEFAULT_MESSAGE.
            max_context_length (int): Maximum allowed context length.
            requested_tokens (int): Number of tokens requested.
            prompt_tokens (int): Number of tokens in prompt.
            completion_tokens (int): Number of tokens in completion.
            **kwargs: Additional arguments passed to IngeniousError.
        """
        self.max_context_length = max_context_length
        self.requested_tokens = requested_tokens
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        
        # Set context with token information
        context = kwargs.get("context", {})
        if isinstance(context, dict):
            context.update({
                "max_context_length": max_context_length,
                "requested_tokens": requested_tokens,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            })
            kwargs["context"] = context
        
        # Initialize IngeniousError with appropriate settings
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "TOKEN_LIMIT_EXCEEDED"),
            category=kwargs.get("category", ErrorCategory.RESOURCE),
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            recoverable=kwargs.get("recoverable", False),
            user_message=kwargs.get("user_message", self.DEFAULT_MESSAGE),
            recovery_suggestion=kwargs.get(
                "recovery_suggestion",
                "Please start a new conversation or reduce the length of your messages.",
            ),
            **{k: v for k, v in kwargs.items() if k not in ["error_code", "category", "severity", "recoverable", "user_message", "recovery_suggestion", "context"]},
        )
