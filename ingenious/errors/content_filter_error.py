"""Content filter error exception.

This module defines exceptions raised when content violates content filter policies.
"""

from typing import Any, Dict, Optional

from ingenious.errors.base_error import IngeniousError
from ingenious.errors.enums import ErrorCategory, ErrorSeverity


class ContentFilterError(IngeniousError):
    """Exception raised when user message violates OpenAI content filter.

    Attributes:
        DEFAULT_MESSAGE (str): Default error message for filter violations.
        content_filter_results (Dict[str, Any]): Details about what triggered the filter.
    """

    DEFAULT_MESSAGE = (
        "The users prompt violates the content filter, please start a new conversation."
    )

    def __init__(
        self,
        message: str = DEFAULT_MESSAGE,
        content_filter_results: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """Initialize content filter error.

        Args:
            message (str): Error message, defaults to DEFAULT_MESSAGE.
            content_filter_results (Optional[Dict[str, Any]]): Filter violation details.
            **kwargs: Additional arguments passed to IngeniousError.
        """
        self.content_filter_results = content_filter_results or {}
        
        # Set context with content filter results
        context = kwargs.get("context", {})
        if isinstance(context, dict):
            context["content_filter_results"] = self.content_filter_results
            kwargs["context"] = context
        
        # Initialize IngeniousError with appropriate settings
        super().__init__(
            message,
            error_code=kwargs.get("error_code", "CONTENT_FILTER_VIOLATION"),
            category=kwargs.get("category", ErrorCategory.VALIDATION),
            severity=kwargs.get("severity", ErrorSeverity.MEDIUM),
            recoverable=kwargs.get("recoverable", False),
            user_message=kwargs.get("user_message", self.DEFAULT_MESSAGE),
            recovery_suggestion=kwargs.get(
                "recovery_suggestion",
                "Please rephrase your message to comply with content policies and start a new conversation.",
            ),
            **{k: v for k, v in kwargs.items() if k not in ["error_code", "category", "severity", "recoverable", "user_message", "recovery_suggestion", "context"]},
        )
