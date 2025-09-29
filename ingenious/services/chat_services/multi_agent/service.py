import logging
import uuid as uuid_module
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from jinja2 import Environment
from openai.types.chat import ChatCompletionMessageParam

import ingenious.config.config as ig_config

if TYPE_CHECKING:
    from ingenious.models.config import Config
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.files.files_repository import FileStorage
from ingenious.models.chat import ChatResponseChunk, IChatRequest, IChatResponse
from ingenious.utils.namespace_utils import (
    import_class_with_fallback,
    normalize_workflow_name,
)

logger = get_logger(__name__)


def _resolve_streaming_chunk_size(config: Any, default: int = 100) -> int:
    """Best-effort lookup for streaming chunk size across config variants."""

    def _extract(candidate: Any) -> Optional[int]:
        size = getattr(candidate, "streaming_chunk_size", None)
        return size if isinstance(size, int) and size > 0 else None

    for attr in ("web_configuration", "web"):
        candidate = getattr(config, attr, None)
        if candidate is not None:
            value = _extract(candidate)
            if value is not None:
                return value

    if isinstance(config, Mapping):
        for key in ("web_configuration", "web"):
            if key in config and config[key] is not None:
                value = _extract(config[key])
                if value is not None:
                    return value

    return default


class multi_agent_chat_service:
    config: "Config"
    chat_history_repository: ChatHistoryRepository
    conversation_flow: str
    openai_service: Optional[ChatCompletionMessageParam]

    def __init__(
        self,
        config: "Config",
        chat_history_repository: ChatHistoryRepository,
        conversation_flow: str,
    ):
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

    async def _prepare_chat_request(self, chat_request: IChatRequest) -> IChatRequest:
        """Prepare and validate the chat request."""
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        if isinstance(chat_request.topic, str):
            chat_request.topic = [
                topic.strip() for topic in chat_request.topic.split(",")
            ]  # type: ignore

        # Initialize additional response fields
        chat_request.thread_chat_history = [{"role": "user", "content": ""}]  # type: ignore

        # Ensure thread ID exists
        if not chat_request.thread_id:
            chat_request.thread_id = str(uuid_module.uuid4())

        return chat_request

    async def _build_thread_memory(self, chat_request: IChatRequest) -> List[Any]:
        """Build thread memory from chat history."""
        thread_messages = await self.chat_history_repository.get_thread_messages(
            chat_request.thread_id
        )

        # Build memory summary from recent messages
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

        return thread_messages

    async def _process_thread_messages(
        self, chat_request: IChatRequest, thread_messages: List[Any]
    ) -> None:
        """Process and validate thread messages."""
        for thread_message in thread_messages or []:
            # Validate content_filter_results not present
            if thread_message.content_filter_results:
                raise ContentFilterError(
                    content_filter_results=thread_message.content_filter_results
                )

            if (
                hasattr(chat_request, "thread_chat_history")
                and chat_request.thread_chat_history
            ):
                chat_request.thread_chat_history.append(  # type: ignore
                    {"role": thread_message.role, "content": thread_message.content}
                )

    async def get_chat_response(self, chat_request: IChatRequest) -> IChatResponse:
        # Prepare and validate the request
        chat_request = await self._prepare_chat_request(chat_request)

        # Build thread memory and get messages
        thread_messages = await self._build_thread_memory(chat_request)

        # Process thread messages
        await self._process_thread_messages(chat_request, thread_messages)

        # Load and execute the conversation flow
        conversation_flow_class = self._load_conversation_flow_class(chat_request)
        agent_response = await self._execute_conversation_flow(
            conversation_flow_class, chat_request
        )

        # Save chat history if enabled
        await self._save_chat_history(chat_request, agent_response)

        return agent_response

    def _load_conversation_flow_class(self, chat_request: IChatRequest) -> Any:
        """Load the conversation flow class dynamically."""
        # Ensure conversation flow is set
        if not self.conversation_flow:
            self.conversation_flow = chat_request.conversation_flow
        if not self.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        logger.info(
            "Starting conversation flow execution",
            conversation_flow=self.conversation_flow,
            operation="conversation_flow_start",
        )

        # Normalize workflow name to support both formats
        normalized_flow = normalize_workflow_name(self.conversation_flow)

        # Check if built-in workflows are disabled and this is a built-in workflow
        builtin_workflows = {
            "classification_agent",
            "knowledge_base_agent",
            "sql_manipulation_agent",
        }

        if (
            not self.config.chat_service.enable_builtin_workflows
            and normalized_flow in builtin_workflows
        ):
            raise ValueError(
                f"Built-in workflow '{self.conversation_flow}' is disabled. "
                f"Set INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=true to enable built-in workflows, "
                f"or use a custom workflow from ingenious_extensions."
            )

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

        conversation_flow_class = import_class_with_fallback(module_name, class_name)

        logger.info(
            "Successfully loaded conversation flow class",
            class_type=str(type(conversation_flow_class)),
            conversation_flow=self.conversation_flow,
            operation="class_loading_success",
        )

        return conversation_flow_class

    async def _execute_new_pattern(
        self, conversation_flow_class: Any, chat_request: IChatRequest
    ) -> Any:
        """Execute conversation flow using new IConversationFlow pattern."""
        # Instantiate with parent service
        instance = conversation_flow_class(parent_multi_agent_chat_service=self)
        response_task = instance.get_conversation_response(chat_request=chat_request)
        return await response_task

    async def _execute_static_pattern(
        self, conversation_flow_class: Any, chat_request: IChatRequest
    ) -> Any:
        """Execute conversation flow using static method pattern."""
        import inspect

        logger.info(
            "Using static method pattern for conversation flow",
            conversation_flow=self.conversation_flow,
            operation="fallback_static_method",
        )

        # Analyze method signature
        sig = inspect.signature(conversation_flow_class.get_conversation_response)
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
                "Using single ChatRequest parameter", operation="single_param_call"
            )
            response_task = conversation_flow_class.get_conversation_response(
                chat_request
            )
        else:
            # Multiple parameters - individual arguments
            logger.debug("Using individual parameters", operation="multi_param_call")
            response_task = conversation_flow_class.get_conversation_response(
                message=chat_request.user_prompt,
                topics=chat_request.topic
                if isinstance(chat_request.topic, list)
                else ([chat_request.topic] if chat_request.topic else []),
                thread_memory=getattr(chat_request, "thread_memory", ""),
                memory_record_switch=getattr(chat_request, "memory_record", True),
                thread_chat_history=getattr(chat_request, "thread_chat_history", []),
            )

        logger.debug("Awaiting conversation flow response", operation="response_await")
        return await response_task

    def _convert_response_format(
        self, response_tuple: Any, chat_request: IChatRequest
    ) -> Any:
        """Convert various response formats to ChatResponse."""
        from ingenious.models.chat import ChatResponse

        logger.debug(
            "Received conversation flow response",
            response_type=str(type(response_tuple)),
            operation="response_received",
        )

        # Already a ChatResponse object
        if isinstance(response_tuple, ChatResponse):
            logger.debug(
                "Response is already ChatResponse format",
                operation="response_format_check",
            )
            return response_tuple

        # Tuple response (response_text, memory_summary)
        if isinstance(response_tuple, tuple) and len(response_tuple) == 2:
            logger.debug(
                "Converting tuple response to ChatResponse",
                operation="tuple_conversion",
            )
            response_text, memory_summary = response_tuple
            return ChatResponse(
                thread_id=chat_request.thread_id,
                message_id=str(uuid_module.uuid4()),
                agent_response=response_text,
                token_count=0,
                max_token_count=0,
                memory_summary=memory_summary,
            )

        # Handle single response case
        logger.debug(
            "Converting single response to ChatResponse",
            operation="single_response_conversion",
        )
        return ChatResponse(
            thread_id=chat_request.thread_id,
            message_id=str(uuid_module.uuid4()),
            agent_response=str(response_tuple),
            token_count=0,
            max_token_count=0,
            memory_summary="",
        )

    async def _execute_conversation_flow(
        self, conversation_flow_class: Any, chat_request: IChatRequest
    ) -> Any:
        """Execute the conversation flow with appropriate pattern."""
        try:
            # Try new pattern first (IConversationFlow)
            return await self._execute_new_pattern(
                conversation_flow_class, chat_request
            )
        except TypeError as te:
            # Fall back to old pattern (static methods)
            logger.debug(
                "Falling back to static pattern",
                type_error=str(te),
                operation="pattern_fallback",
            )
            response_tuple = await self._execute_static_pattern(
                conversation_flow_class, chat_request
            )
            return self._convert_response_format(response_tuple, chat_request)

    async def _save_chat_history(
        self, chat_request: IChatRequest, agent_response: Any
    ) -> None:
        """Save chat history to repository if memory_record is enabled."""
        if not getattr(chat_request, "memory_record", True):
            return

        if not (chat_request.user_id and chat_request.thread_id):
            return

        try:
            from ingenious.models.message import Message

            # Save user message
            user_message_id = await self.chat_history_repository.add_message(
                Message(
                    user_id=chat_request.user_id,
                    thread_id=chat_request.thread_id,
                    role="user",
                    content=chat_request.user_prompt,
                )
            )
            logger.info(
                "Saved user message",
                message_id=user_message_id,
                thread_id=chat_request.thread_id,
            )

            # Save agent response
            agent_message_id = await self.chat_history_repository.add_message(
                Message(
                    user_id=chat_request.user_id,
                    thread_id=chat_request.thread_id,
                    role="assistant",
                    content=agent_response.agent_response,
                )
            )
            logger.info(
                "Saved agent message",
                message_id=agent_message_id,
                thread_id=chat_request.thread_id,
            )

            # Save memory summary if available
            if (
                hasattr(agent_response, "memory_summary")
                and agent_response.memory_summary
            ):
                memory_id = await self.chat_history_repository.add_memory(
                    Message(
                        user_id=chat_request.user_id,
                        thread_id=chat_request.thread_id,
                        role="memory_assistant",
                        content=agent_response.memory_summary,
                    )
                )
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
            if hasattr(
                conversation_flow_service_class, "get_streaming_conversation_response"
            ):
                # New streaming pattern - instantiate and call streaming method
                if (
                    hasattr(conversation_flow_service_class, "__init__")
                    and len(
                        conversation_flow_service_class.__init__.__code__.co_varnames
                    )
                    > 1
                ):
                    conversation_flow_service_class_instance = (
                        conversation_flow_service_class(
                            parent_multi_agent_chat_service=self
                        )
                    )
                    async for chunk in conversation_flow_service_class_instance.get_streaming_conversation_response(
                        chat_request
                    ):
                        yield chunk
                else:
                    # Static method streaming pattern
                    async for chunk in conversation_flow_service_class.get_streaming_conversation_response(
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
                    chunk_size = _resolve_streaming_chunk_size(self.config)

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
    _config: "Config"
    _memory_path: str
    _memory_file_path: str
    _memory_manager: Any

    def __init__(self) -> None:
        super().__init__()
        self._config = ig_config.get_config()
        self._memory_path = self.GetConfig().chat_history.memory_path
        self._memory_file_path = f"{self._memory_path}/context.md"

        # Initialize memory manager for cloud storage support
        from ingenious.services.memory_manager import get_memory_manager

        self._memory_manager = get_memory_manager(self._config, self._memory_path)

    def GetConfig(self) -> "Config":
        return self._config

    def Get_Models(self) -> Dict[str, Any]:
        return self._config.models.__dict__

    def Get_Memory_Path(self) -> str:
        return self._memory_path

    def Get_Memory_File(self) -> str:
        return self._memory_file_path

    def Maintain_Memory(self, new_content: str, max_words: int = 150) -> Any:
        """
        Maintain memory using the MemoryManager for cloud storage support.
        """
        from ingenious.services.memory_manager import run_async_memory_operation

        return run_async_memory_operation(  # type: ignore
            self._memory_manager.maintain_memory(new_content, max_words)
        )

    async def write_llm_responses_to_file(
        self, response_array: List[Dict[str, Any]], event_type: str, output_path: str
    ) -> None:
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
    async def get_conversation_response(
        self, message: str, thread_memory: str
    ) -> IChatResponse:
        pass


class IConversationFlow(ABC):
    _config: "Config"
    _memory_path: str
    _memory_file_path: str
    _logger: logging.Logger
    _chat_service: multi_agent_chat_service
    _memory_manager: Any

    def __init__(
        self, parent_multi_agent_chat_service: multi_agent_chat_service
    ) -> None:
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

    def GetConfig(self) -> "Config":
        return self._config

    async def Get_Template(
        self, revision_id: Optional[str] = None, file_name: str = "user_prompt.md"
    ) -> str:
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
        env = Environment(autoescape=True)
        template = env.from_string(content)
        return template.render()  # type: ignore

    def Get_Models(self) -> Any:
        return self._config.models

    def Get_Memory_Path(self) -> str:
        return self._memory_path

    def Get_Memory_File(self) -> str:
        return self._memory_file_path

    def Maintain_Memory(self, new_content: str, max_words: int = 150) -> Any:
        """
        Maintain memory using the MemoryManager for cloud storage support.
        """
        from ingenious.services.memory_manager import run_async_memory_operation

        return run_async_memory_operation(  # type: ignore
            self._memory_manager.maintain_memory(new_content, max_words)
        )

    @abstractmethod
    async def get_conversation_response(
        self, chat_request: IChatRequest
    ) -> IChatResponse:
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
            chunk_size = _resolve_streaming_chunk_size(self._config)

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
