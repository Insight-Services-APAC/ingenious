"""Multi-agent chat service core implementation."""

import asyncio
import logging
import uuid as uuid_module
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from jinja2 import Environment
from openai.types.chat import ChatCompletionMessageParam

import ingenious.config.config as ig_config

if TYPE_CHECKING:
    from ingenious.config.settings import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.files.files_repository import FileStorage
from ingenious.models.chat import ChatResponseChunk, IChatRequest, IChatResponse
from ingenious.utils.imports import import_class_with_fallback
from ingenious.utils.namespace_utils import normalize_workflow_name

logger = get_logger(__name__)


class multi_agent_chat_service:
    """Multi-agent chat service implementation using AutoGen framework.

    This service orchestrates conversations using multiple AI agents through
    the AutoGen framework. It supports dynamic loading of conversation flows,
    chat history management, and both regular and streaming responses.
    """

    config: "IngeniousSettings"
    chat_history_repository: ChatHistoryRepository
    conversation_flow: str
    openai_service: Optional[ChatCompletionMessageParam]

    def __init__(
        self,
        config: "IngeniousSettings",
        chat_history_repository: ChatHistoryRepository,
        conversation_flow: str,
    ):
        """Initialize the multi-agent chat service.

        Args:
            config: The Ingenious settings configuration containing model and service settings.
            chat_history_repository: Repository for managing persistent chat history.
            conversation_flow: The name of the conversation flow pattern to use.

        Raises:
            RuntimeError: If OpenAI service is not properly configured in the config.
        """
        self.config = config
        self.chat_history_repository = chat_history_repository
        self.conversation_flow = conversation_flow
        # Get openai_service from config if available
        if hasattr(config, "openai_service_instance"):
            self.openai_service = config.openai_service_instance  # type: ignore
        else:
            # OpenAI service should be injected via config
            raise RuntimeError(
                "OpenAI service not properly configured. Please ensure the service is initialized with proper dependencies."
            )

    async def get_chat_response(self, chat_request: IChatRequest) -> IChatResponse:
        """Process a chat request and return the agent's response.

        Args:
            chat_request: The chat request containing user prompt, conversation flow, and context.

        Returns:
            IChatResponse: The agent's response including message content and metadata.

        Raises:
            ValueError: If conversation_flow is not set in the request.
            ContentFilterError: If content filter violations are detected in thread messages.
        """
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        if isinstance(chat_request.topic, str):
            chat_request.topic = [topic.strip() for topic in chat_request.topic.split(",")]  # type: ignore

        # Initialize additional response fields - to be populated later
        chat_request.thread_chat_history = [{"role": "user", "content": ""}]  # type: ignore
        # thread_memory = ""

        # Check if thread exists
        if not chat_request.thread_id:
            chat_request.thread_id = str(uuid_module.uuid4())

        # Get thread messages & add to messages list
        thread_messages = await self.chat_history_repository.get_thread_messages(
            chat_request.thread_id
        )
        # Build thread memory from messages
        if thread_messages:
            memory_parts = []
            for msg in thread_messages[-10:]:  # Use last 10 messages
                memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
            chat_request.thread_memory = "\n".join(memory_parts)
        else:
            chat_request.thread_memory = "no existing context."

        logger.info(
            "Current memory state",
            thread_id=chat_request.thread_id,
            memory_length=len(chat_request.thread_memory or ""),
        )
        logger.debug(
            "Thread messages and memory processed",
            message_count=len(thread_messages or []),
            operation="process_thread_context",
        )

        for thread_message in thread_messages or []:
            # Validate user_id
            # if thread_message.user_id != chat_request.user_id:
            #     raise ValueError("User ID does not match thread messages.")

            # Validate content_filter_results not present
            if thread_message.content_filter_results:
                raise ContentFilterError(
                    content_filter_results=thread_message.content_filter_results
                )

            if hasattr(chat_request, "thread_chat_history") and chat_request.thread_chat_history:
                chat_request.thread_chat_history.append(  # type: ignore
                    {"role": thread_message.role, "content": thread_message.content}
                )

        try:
            # call specific agent flow here and get final response
            logger.info(
                "Starting conversation flow execution",
                conversation_flow=self.conversation_flow,
                operation="conversation_flow_start",
            )
            if not self.conversation_flow:
                self.conversation_flow = chat_request.conversation_flow
            if not self.conversation_flow:
                raise ValueError(f"conversation_flow4 not set {chat_request}")

            # Normalize workflow name to support both hyphenated and underscored formats
            normalized_flow = normalize_workflow_name(self.conversation_flow)
            module_name = f"services.chat_services.multi_agent.conversation_flows.{normalized_flow}.{normalized_flow}"
            class_name = "ConversationFlow"
            logger.debug(
                "Loading conversation flow module",
                module_name=module_name,
                class_name=class_name,
                original_workflow=self.conversation_flow,
                normalized_workflow=normalized_flow,
                operation="module_loading",
            )

            conversation_flow_service_class = import_class_with_fallback(module_name, class_name)
            logger.info(
                "Successfully loaded conversation flow class",
                class_type=str(type(conversation_flow_service_class)),
                conversation_flow=self.conversation_flow,
                operation="class_loading_success",
            )

            # Try to instantiate with new pattern first (IConversationFlow)
            try:
                # Check if it's the new pattern by trying to instantiate with parent service
                conversation_flow_service_class_instance = conversation_flow_service_class(
                    parent_multi_agent_chat_service=self
                )

                response_task = conversation_flow_service_class_instance.get_conversation_response(
                    chat_request=chat_request
                )

                agent_response = await response_task

            except TypeError as te:
                # Fall back to old pattern (static methods)
                logger.info(
                    "Using static method pattern for conversation flow",
                    conversation_flow=self.conversation_flow,
                    type_error=str(te),
                    operation="fallback_static_method",
                )

                # Try different static method signatures
                import inspect

                sig = inspect.signature(conversation_flow_service_class.get_conversation_response)
                params = list(sig.parameters.keys())
                logger.debug(
                    "Analyzing method signature",
                    parameters=params,
                    param_count=len(params),
                    operation="method_signature_analysis",
                )

                if len(params) == 1 and params[0] not in ["self", "cls"]:
                    # Single parameter - likely ChatRequest
                    logger.debug(
                        "Using single ChatRequest parameter",
                        operation="single_param_call",
                    )
                    response_task = conversation_flow_service_class.get_conversation_response(
                        chat_request
                    )
                else:
                    # Multiple parameters - individual arguments
                    logger.debug("Using individual parameters", operation="multi_param_call")
                    response_task = conversation_flow_service_class.get_conversation_response(
                        message=chat_request.user_prompt,
                        topics=chat_request.topic
                        if isinstance(chat_request.topic, list)
                        else ([chat_request.topic] if chat_request.topic else []),
                        thread_memory=getattr(chat_request, "thread_memory", ""),
                        memory_record_switch=getattr(chat_request, "memory_record", True),
                        thread_chat_history=getattr(chat_request, "thread_chat_history", []),
                    )

                logger.debug("Awaiting conversation flow response", operation="response_await")
                agent_response_tuple = await response_task
                logger.debug(
                    "Received conversation flow response",
                    response_type=str(type(agent_response_tuple)),
                    operation="response_received",
                )

                # Convert old response format to new format
                from ingenious.models.chat import ChatResponse

                logger.debug(
                    "Creating ChatResponse object",
                    uuid_module_available=uuid_module is not None,
                    operation="chat_response_creation",
                )

                # Handle different response types
                if isinstance(agent_response_tuple, ChatResponse):
                    # Already a ChatResponse object
                    logger.debug(
                        "Response is already ChatResponse format",
                        operation="response_format_check",
                    )
                    agent_response = agent_response_tuple
                elif isinstance(agent_response_tuple, tuple) and len(agent_response_tuple) == 2:
                    # Tuple response (response_text, memory_summary)
                    logger.debug(
                        "Converting tuple response to ChatResponse",
                        operation="tuple_conversion",
                    )
                    response_text, memory_summary = agent_response_tuple
                    agent_response = ChatResponse(
                        thread_id=chat_request.thread_id,
                        message_id=str(uuid_module.uuid4()),
                        agent_response=response_text,
                        token_count=0,
                        max_token_count=0,
                        memory_summary=memory_summary,
                    )
                else:
                    # Handle single response case
                    logger.debug(
                        "Converting single response to ChatResponse",
                        operation="single_response_conversion",
                    )
                    agent_response = ChatResponse(
                        thread_id=chat_request.thread_id,
                        message_id=str(uuid_module.uuid4()),
                        agent_response=str(agent_response_tuple),
                        token_count=0,
                        max_token_count=0,
                        memory_summary="",
                    )

        except Exception as e:
            logger.error(
                "Error occurred while processing conversation flow",
                conversation_flow=self.conversation_flow,
                error=str(e),
                exc_info=True,
            )
            raise e

        # Save chat history if memory_record is enabled
        if getattr(chat_request, "memory_record", True):
            try:
                # Save user message, agent response, and memory in parallel
                if chat_request.user_id and chat_request.thread_id:
                    from ingenious.models.message import Message

                    # Create message objects
                    user_message = Message(
                        user_id=chat_request.user_id,
                        thread_id=chat_request.thread_id,
                        role="user",
                        content=chat_request.user_prompt,
                    )
                    agent_message = Message(
                        user_id=chat_request.user_id,
                        thread_id=chat_request.thread_id,
                        role="assistant",
                        content=agent_response.agent_response,
                    )

                    # Prepare tasks for parallel execution
                    tasks = [
                        self.chat_history_repository.add_message(user_message),
                        self.chat_history_repository.add_message(agent_message),
                    ]

                    # Add memory task if available
                    if hasattr(agent_response, "memory_summary") and agent_response.memory_summary:
                        memory_message = Message(
                            user_id=chat_request.user_id,
                            thread_id=chat_request.thread_id,
                            role="memory_assistant",
                            content=agent_response.memory_summary,
                        )
                        tasks.append(self.chat_history_repository.add_memory(memory_message))

                    # Execute all saves in parallel
                    results = await asyncio.gather(*tasks, return_exceptions=False)

                    # Log results
                    user_message_id = results[0]
                    agent_message_id = results[1]
                    logger.info(
                        "Saved chat history in parallel",
                        user_msg_id=user_message_id,
                        agent_msg_id=agent_message_id,
                        thread_id=chat_request.thread_id,
                    )

                    if len(results) > 2:
                        memory_id = results[2]
                        logger.info(
                            "Saved memory",
                            memory_id=memory_id,
                            thread_id=chat_request.thread_id,
                        )

            except Exception as e:
                logger.error(
                    "Failed to save chat history",
                    thread_id=chat_request.thread_id,
                    user_id=chat_request.user_id,
                    error=str(e),
                    exc_info=True,
                )
                # Continue execution even if database save fails
                # This ensures the chat response is still returned to the user

        return agent_response  # type: ignore

    async def get_streaming_chat_response(
        self, chat_request: IChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Stream chat response chunks in real-time."""
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        logger.debug(
            "Starting streaming chat response",
            conversation_flow=chat_request.conversation_flow,
            thread_id=chat_request.thread_id,
        )

        normalized_flow = normalize_workflow_name(chat_request.conversation_flow)

        try:
            # Import the conversation flow class dynamically
            conversation_flow_service_class = import_class_with_fallback(
                f"services.chat_services.multi_agent.conversation_flows.{normalized_flow}.{normalized_flow}",
                "ConversationFlow",
            )

            # Check if the conversation flow supports streaming
            if hasattr(conversation_flow_service_class, "get_streaming_conversation_response"):
                # New streaming pattern - instantiate and call streaming method
                if (
                    hasattr(conversation_flow_service_class, "__init__")
                    and len(conversation_flow_service_class.__init__.__code__.co_varnames) > 1
                ):
                    conversation_flow_service_class_instance = conversation_flow_service_class(
                        parent_multi_agent_chat_service=self
                    )
                    async for chunk in conversation_flow_service_class_instance.get_streaming_conversation_response(
                        chat_request
                    ):
                        yield chunk
                else:
                    # Static method streaming pattern
                    async for (
                        chunk
                    ) in conversation_flow_service_class.get_streaming_conversation_response(
                        chat_request.user_prompt,
                        [],  # topics placeholder
                        chat_request.thread_memory or "",
                        chat_request.memory_record or True,
                        chat_request.thread_chat_history or {},
                        chat_request,
                    ):
                        yield chunk
            else:
                # Fallback: convert regular response to streaming chunks
                logger.info(
                    "Conversation flow does not support streaming, falling back to chunked response",
                    conversation_flow=chat_request.conversation_flow,
                )

                # Get regular response and convert to chunks
                response = await self.get_chat_response(chat_request)

                if response.agent_response:
                    chunk_size = 100  # Default chunk size
                    if hasattr(self.config, "web_configuration") and hasattr(
                        self.config.web_configuration, "streaming_chunk_size"
                    ):
                        chunk_size = self.config.web_configuration.streaming_chunk_size

                    content = response.agent_response

                    # Stream content in chunks
                    for i in range(0, len(content), chunk_size):
                        chunk_content = content[i : i + chunk_size]
                        yield ChatResponseChunk(
                            thread_id=response.thread_id,
                            message_id=response.message_id,
                            chunk_type="content",
                            content=chunk_content,
                            event_type=response.event_type,
                            is_final=False,
                        )

                # Send final chunk with metadata
                yield ChatResponseChunk(
                    thread_id=response.thread_id,
                    message_id=response.message_id,
                    chunk_type="final",
                    token_count=response.token_count,
                    max_token_count=response.max_token_count,
                    topic=response.topic,
                    memory_summary=response.memory_summary,
                    followup_questions=response.followup_questions,
                    event_type=response.event_type,
                    is_final=True,
                )

        except ImportError as e:
            logger.error(
                "Failed to import conversation flow for streaming",
                conversation_flow=self.conversation_flow,
                normalized_flow=normalized_flow,
                error=str(e),
                exc_info=True,
            )
            error_chunk = ChatResponseChunk(
                thread_id=chat_request.thread_id,
                message_id=str(uuid_module.uuid4()),
                chunk_type="error",
                content=f"Conversation flow not found: {self.conversation_flow}",
                is_final=True,
            )
            yield error_chunk

        except Exception as e:
            logger.error(
                "Error in streaming chat response",
                conversation_flow=self.conversation_flow,
                error=str(e),
                exc_info=True,
            )
            error_chunk = ChatResponseChunk(
                thread_id=chat_request.thread_id,
                message_id=str(uuid_module.uuid4()),
                chunk_type="error",
                content=f"An error occurred: {str(e)}",
                is_final=True,
            )
            yield error_chunk


class IConversationPattern(ABC):
    """Abstract base class for conversation pattern implementations.

    This class provides the foundation for implementing custom conversation patterns
    with built-in memory management, configuration access, and template handling.
    Legacy pattern - prefer IConversationFlow for new implementations.
    """

    _config: "IngeniousSettings"
    _memory_path: str
    _memory_file_path: str
    _memory_manager: Any

    def __init__(self) -> None:
        """Initialize the conversation pattern with configuration and memory management.

        Sets up the configuration, memory paths, and memory manager for handling
        conversation context across sessions.
        """
        super().__init__()
        self._config = ig_config.get_config()
        self._memory_path = self.GetConfig().chat_history.memory_path
        self._memory_file_path = f"{self._memory_path}/context.md"

        # Initialize memory manager for cloud storage support
        from ingenious.services.memory_manager import get_memory_manager

        self._memory_manager = get_memory_manager(self._config, self._memory_path)

    def GetConfig(self) -> "IngeniousSettings":
        """Get the current configuration settings.

        Returns:
            IngeniousSettings: The current configuration instance.
        """
        return self._config

    def Get_Models(self) -> Dict[str, Any]:
        """Get the configured language models as a dictionary.

        Returns:
            Dict[str, Any]: Dictionary containing model configurations.
        """
        return self._config.models.__dict__

    def Get_Memory_Path(self) -> str:
        """Get the path to the memory storage directory.

        Returns:
            str: The memory storage directory path.
        """
        return self._memory_path

    def Get_Memory_File(self) -> str:
        """Get the full path to the memory context file.

        Returns:
            str: The full path to the memory file (context.md).
        """
        return self._memory_file_path

    def Maintain_Memory(self, new_content: str, max_words: int = 150) -> Any:
        """Maintain memory using the MemoryManager for cloud storage support."""
        from ingenious.services.memory_manager import run_async_memory_operation

        return run_async_memory_operation(  # type: ignore
            self._memory_manager.maintain_memory(new_content, max_words)
        )

    async def write_llm_responses_to_file(
        self, response_array: List[Dict[str, Any]], event_type: str, output_path: str
    ) -> None:
        """Write LLM responses to files for a given event type.

        Args:
            response_array: List of response dictionaries containing chat_response and chat_title.
            event_type: The type of event being processed.
            output_path: The directory path where response files will be written.
        """
        fs = FileStorage(self._config)
        for res in response_array:
            make_llm_calls = True
            if make_llm_calls:
                this_response = res["chat_response"]
            else:
                this_response = "Insight not yet generated"

            await fs.write_file(
                this_response,
                f"agent_response_{event_type}_{res['chat_title']}.md",
                output_path,
            )

    @abstractmethod
    async def get_conversation_response(self, message: str, thread_memory: str) -> IChatResponse:
        """Generate a conversation response based on the message and memory context.

        Args:
            message: The user's input message.
            thread_memory: The conversation memory/history for context.

        Returns:
            IChatResponse: The generated response from the conversation pattern.
        """
        pass


class IConversationFlow(ABC):
    """Abstract base class for conversation flow implementations.

    This class provides the foundation for implementing pluggable conversation flows
    with access to the parent chat service, configuration, memory management,
    and template rendering capabilities. Preferred pattern for new implementations.
    """

    _config: "IngeniousSettings"
    _memory_path: str
    _memory_file_path: str
    _logger: logging.Logger
    _chat_service: multi_agent_chat_service
    _memory_manager: Any

    def __init__(self, parent_multi_agent_chat_service: multi_agent_chat_service) -> None:
        """Initialize the conversation flow with parent service context.

        Args:
            parent_multi_agent_chat_service: The parent multi-agent chat service instance
                providing configuration and chat history access.
        """
        super().__init__()
        # Use configuration from parent service instead of loading separately
        self._config = parent_multi_agent_chat_service.config
        self._memory_path = self.GetConfig().chat_history.memory_path
        self._memory_file_path = f"{self._memory_path}/context.md"
        self._logger = get_logger(__name__)  # type: ignore
        self._chat_service = parent_multi_agent_chat_service

        # Initialize memory manager for cloud storage support
        from ingenious.services.memory_manager import get_memory_manager

        self._memory_manager = get_memory_manager(self._config, self._memory_path)

    def GetConfig(self) -> "IngeniousSettings":
        """Get the current configuration settings.

        Returns:
            IngeniousSettings: The current configuration instance.
        """
        return self._config

    async def Get_Template(
        self, revision_id: Optional[str] = None, file_name: str = "user_prompt.md"
    ) -> str:
        """Retrieve and render a Jinja2 template from the prompt template storage.

        Args:
            revision_id: Optional revision identifier to load a specific template version.
            file_name: The name of the template file to load (default: "user_prompt.md").

        Returns:
            str: The rendered template content, or empty string if template not found.
        """
        fs = FileStorage(self._config)
        template_path = await fs.get_prompt_template_path(revision_id or "")
        content = await fs.read_file(file_name=file_name, file_path=template_path)
        if content is None:
            logger.warning(
                "Prompt template file not found",
                file_name=file_name,
                template_path=template_path,
                operation="template_file_lookup",
            )
            return ""
        env = Environment()
        template = env.from_string(content)
        return template.render()  # type: ignore

    def Get_Models(self) -> Any:
        """Get the configured language models.

        Returns:
            Any: The models configuration object.
        """
        return self._config.models

    def Get_Memory_Path(self) -> str:
        """Get the path to the memory storage directory.

        Returns:
            str: The memory storage directory path.
        """
        return self._memory_path

    def Get_Memory_File(self) -> str:
        """Get the full path to the memory context file.

        Returns:
            str: The full path to the memory file (context.md).
        """
        return self._memory_file_path

    def Maintain_Memory(self, new_content: str, max_words: int = 150) -> Any:
        """Maintain memory using the MemoryManager for cloud storage support."""
        from ingenious.services.memory_manager import run_async_memory_operation

        return run_async_memory_operation(  # type: ignore
            self._memory_manager.maintain_memory(new_content, max_words)
        )

    @abstractmethod
    async def get_conversation_response(self, chat_request: IChatRequest) -> IChatResponse:
        """Generate a conversation response based on the chat request.

        Args:
            chat_request: The chat request containing user prompt, conversation flow, and context.

        Returns:
            IChatResponse: The generated response from the conversation flow.
        """
        pass

    async def get_streaming_conversation_response(
        self, chat_request: IChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Optional streaming method. Override in subclasses to support streaming.

        Default implementation falls back to chunking the regular response.
        """
        logger.debug(
            "Streaming not implemented, falling back to chunked response",
            conversation_flow=self.__class__.__name__,
        )

        # Get regular response and convert to chunks
        response = await self.get_conversation_response(chat_request)

        if response.agent_response:
            chunk_size = 100  # Default chunk size
            if hasattr(self._config, "web_configuration") and hasattr(
                self._config.web_configuration, "streaming_chunk_size"
            ):
                chunk_size = self._config.web_configuration.streaming_chunk_size

            content = response.agent_response

            # Stream content in chunks
            for i in range(0, len(content), chunk_size):
                chunk_content = content[i : i + chunk_size]
                yield ChatResponseChunk(
                    thread_id=response.thread_id,
                    message_id=response.message_id,
                    chunk_type="content",
                    content=chunk_content,
                    event_type=response.event_type,
                    is_final=False,
                )

        # Send final chunk with metadata
        yield ChatResponseChunk(
            thread_id=response.thread_id,
            message_id=response.message_id,
            chunk_type="final",
            token_count=response.token_count,
            max_token_count=response.max_token_count,
            topic=response.topic,
            memory_summary=response.memory_summary,
            followup_questions=response.followup_questions,
            event_type=response.event_type,
            is_final=True,
        )
        pass


# Save agent response
# agent_message_id = await self.chat_history_repository.add_message(
#     Message(
#         user_id=chat_request.user_id,
#         thread_id=chat_request.thread_id,
#         role="assistant",
#         content=agent_response[0])
# )

# logger.debug("Agent response received", response_preview=str(agent_response)[:100])
# _ = await self.chat_history_repository.add_memory(
#     Message(
#         user_id=chat_request.user_id,
#         thread_id=chat_request.thread_id,
#         role="memory_assistant",
#         content=agent_response[1]),
# )
