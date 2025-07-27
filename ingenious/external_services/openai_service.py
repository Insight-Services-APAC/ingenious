import re
from typing import Optional

from azure.identity import DefaultAzureCredential
from openai import NOT_GIVEN, AzureOpenAI, BadRequestError
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

from ingenious.core.structured_logging import get_logger
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError

logger = get_logger(__name__)


class OpenAIService:
    def __init__(
        self, 
        azure_endpoint: str, 
        api_key: Optional[str], 
        api_version: str, 
        open_ai_model: str,
        use_managed_identity: bool = False
    ):
        if use_managed_identity:
            # Use managed identity authentication
            credential = DefaultAzureCredential()
            self.client = AzureOpenAI(
                azure_endpoint=azure_endpoint, 
                azure_ad_token_provider=lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token,
                api_version=api_version
            )
        else:
            # Use API key authentication
            if not api_key:
                raise ValueError("API key is required when not using managed identity")
            self.client = AzureOpenAI(
                azure_endpoint=azure_endpoint, 
                api_key=api_key, 
                api_version=api_version
            )
        self.model = open_ai_model

    async def generate_response(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam] | None = None,
        tool_choice: str | dict[str, object] | None = None,
        json_mode=False,
    ) -> ChatCompletionMessage:
        logger.debug(
            "Generating OpenAI response",
            model=self.model,
            message_count=len(messages),
            has_tools=tools is not None,
            json_mode=json_mode,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or NOT_GIVEN,
                tool_choice=tool_choice or ("auto" if tools else NOT_GIVEN),
                response_format={"type": "json_object"} if json_mode else NOT_GIVEN,
                temperature=0.2,
            )
            return response.choices[0].message
        except BadRequestError as error:
            # Log the error with structured context
            logger.error(
                "OpenAI API request failed",
                error_type="BadRequestError",
                error_code=error.code,
                error_message=error.message,
                model=self.model,
                exc_info=True,
            )

            # Default to the general message from the exception
            message = error.message

            # Check if the body is a dictionary and refine the message if possible
            if isinstance(error.body, dict):
                message = error.body.get("message", message)

                # Check for content filter specific errors
                if error.code == "content_filter" and "innererror" in error.body:
                    content_filter_results = error.body["innererror"].get(
                        "content_filter_result", {}
                    )
                    raise ContentFilterError(message, content_filter_results)

                # Check for token limit errors
                token_error_pattern = (
                    r"This model's maximum context length is (\d+) tokens, "
                    r"however you requested (\d+) tokens \((\d+) in your prompt; "
                    r"(\d+) for the completion\). Please reduce your prompt; or "
                    r"completion length."
                )
                token_error_match = re.match(token_error_pattern, message)
                if token_error_match:
                    (
                        max_context_length,
                        requested_tokens,
                        prompt_tokens,
                        completion_tokens,
                    ) = token_error_match.groups()
                    raise TokenLimitExceededError(
                        message=message,
                        max_context_length=int(max_context_length),
                        requested_tokens=int(requested_tokens),
                        prompt_tokens=int(prompt_tokens),
                        completion_tokens=int(completion_tokens),
                    )

            raise Exception(message)
        except Exception as e:
            logger.exception(e)
            raise
