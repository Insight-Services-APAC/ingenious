import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional, Type

from autogen_agentchat.base import Response
from autogen_agentchat.messages import TextMessage
from autogen_core import (
    CancellationToken,
    FunctionCall,
    MessageContext,
    SingleThreadedAgentRuntime,
    TypeSubscription,
)
from autogen_core.logging import LLMCallEvent
from autogen_core.models import FunctionExecutionResult
from autogen_core.tools import Tool
from pydantic import BaseModel, Field, PrivateAttr

from ingenious.config import IngeniousSettings, get_config

ig_config = get_config()
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.files.files_repository import FileStorage
from ingenious.models.config import Config, ModelConfig
from ingenious.models.llm_event_kwargs import LLMEventKwargs
from ingenious.models.message import Message as ChatHistoryMessage


class AgentChat(BaseModel):
    """
    A class used to represent a chat between an agent and a user or between agents

    Attributes
    ----------
    agent_name : str
        The name of the agent.
    user_message : str
        The message sent by the user.
    system_prompt : str
        The message sent by the agent.
    """

    chat_name: str
    target_agent_name: str
    source_agent_name: str
    user_message: str
    system_prompt: str
    identifier: Optional[str] = (
        None  # Identifies the data payload associated with the chat for live chat this could be the thread id
    )
    chat_response: Optional[Response] = None
    completion_tokens: int = 0
    prompt_tokens: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    def get_execution_time(self) -> float:
        if self.end_time is None or self.start_time is None:
            return 0.0
        return self.end_time - self.start_time

    def get_execution_time_formatted(self) -> str:
        execution_time = self.get_execution_time()
        return f"{int(execution_time // 60)}:{int(execution_time % 60):02d}"

    def get_start_time_formatted(self) -> str:
        if self.start_time is None:
            return "00:00:00"
        return datetime.fromtimestamp(self.start_time).strftime("%H:%M:%S")

    def get_associated_agent_response_file_name(
        self, identifier: str, event_type: str
    ) -> str:
        return f"agent_response_{event_type}_{self.source_agent_name}_{self.target_agent_name}_{identifier.strip()}.md"


class AgentChats(BaseModel):
    """
    A class used to represent a list of AgentChats.

    Attributes
    ----------
    agent_chats : List[AgentChat]
        A list of AgentChat objects.
    """

    _agent_chats: List[AgentChat] = PrivateAttr(default_factory=list)

    def __init__(self) -> None:
        super().__init__()

    def add_agent_chat(self, agent_chat: AgentChat) -> None:
        self._agent_chats.append(agent_chat)

    def get_agent_chats(self) -> List[AgentChat]:
        return self._agent_chats

    def get_agent_chat_by_name(self, agent_name: str) -> AgentChat:
        for agent_chat in self._agent_chats:
            if (
                agent_chat.source_agent_name == agent_name
                or agent_chat.target_agent_name == agent_name
            ):
                return agent_chat
        raise ValueError(f"AgentChat with name {agent_name} not found")

    def get_agent_chats_by_name(self, agent_name: str) -> List[AgentChat]:
        agent_chats = []
        for agent_chat in self._agent_chats:
            if (
                agent_chat.source_agent_name == agent_name
                or agent_chat.target_agent_name == agent_name
            ):
                agent_chats.append(agent_chat)
        return agent_chats


class Agent(BaseModel):
    """
    A class used to represent an Agent.

    Attributes
    ----------
    agent_name : str
        The name of the agent.
    agent_model_name : str
        The name of the model associated with the agent. This should match the name defined in the environment configuration.
    agent_display_name : str
        The display name of the agent.
    agent_description : str
        A brief description of the agent.
    agent_type : str
        The type/category of the agent.
    """

    agent_name: str
    agent_model_name: str
    agent_display_name: str
    agent_description: str
    agent_type: str
    input_topics: list[str] = Field(default_factory=list)
    model: Optional[ModelConfig] = None
    system_prompt: Optional[str] = None
    log_to_prompt_tuner: bool = True
    return_in_response: bool = False
    agent_chats: list[AgentChat] = Field(default_factory=list)

    def add_agent_chat(
        self,
        content: str,
        identifier: str,
        ctx: Optional[MessageContext] = None,
        source: Optional[str] = None,
    ) -> AgentChat:
        if ctx and ctx.topic_id:
            source = ctx.topic_id.source

        agent_chat: AgentChat = AgentChat(
            chat_name=self.agent_name + "",
            target_agent_name=self.agent_name,
            source_agent_name=source,
            user_message=content,
            system_prompt=self.system_prompt,
            identifier=identifier,
            chat_response=Response(
                chat_message=TextMessage(content=content, source=source)
            ),
            start_time=datetime.now().timestamp(),
            end_time=datetime.now().timestamp() + 36000,
        )
        self.agent_chats.append(agent_chat)
        return agent_chat

    def get_agent_chat_by_source(self, source: str) -> AgentChat:
        for agent_chat in self.agent_chats:
            if agent_chat.source_agent_name == source:
                return agent_chat
        raise ValueError(f"AgentChat with source {source} not found")

    async def log(self, agent_chat: AgentChat, queue: asyncio.Queue[AgentChat]) -> None:
        if self.log_to_prompt_tuner or self.return_in_response:
            await queue.put(agent_chat)

    async def execute_tool_call(
        self,
        call: FunctionCall,
        cancellation_token: CancellationToken,
        tools: List[Tool] = [],
    ) -> FunctionExecutionResult:
        # Find the tool by name.
        tool = next((tool for tool in tools if tool.name == call.name), None)
        assert tool is not None

        # Run the tool and capture the result.
        try:
            arguments = json.loads(call.arguments)
            result = await tool.run_json(arguments, cancellation_token)
            return FunctionExecutionResult(
                call_id=call.id,
                name=call.name,
                content=tool.return_value_as_string(result),
                is_error=False,
            )
        except Exception as e:
            return FunctionExecutionResult(
                call_id=call.id, name=call.name, content=str(e), is_error=True
            )


class Agents(BaseModel):
    """
    A class used to represent a list of Agents.

    Attributes
    ----------
    agents : List[Agent]
        A list of Agent objects.
    """

    _agents: List[Agent]

    def __init__(self, agents: List[Agent], config: Config):
        super().__init__()
        self._agents = agents
        for agent in self._agents:
            for model in config.models:
                if model.model == agent.agent_model_name:
                    agent.model = model
                    break
            if not agent.model:
                raise ValueError(
                    f"Model {agent.agent_model_name} not found in environment configuration"
                )

    def get_agents(self) -> List[Agent]:
        return self._agents

    def get_agents_for_prompt_tuner(self) -> List[Agent]:
        return [agent for agent in self._agents if agent.log_to_prompt_tuner]

    def get_agent_by_name(self, agent_name: str) -> Agent:
        for agent in self._agents:
            if agent.agent_name == agent_name:
                return agent
        raise ValueError(f"Agent with name {agent_name} not found")

    async def register_agent(
        self,
        ag_class: Type[Any],
        runtime: SingleThreadedAgentRuntime,
        agent_name: str,
        data_identifier: str,
        next_agent_topic: str,
        tools: List[Tool] = [],
    ) -> None:
        agent = self.get_agent_by_name(agent_name=agent_name)
        reg_agent = await ag_class.register(
            runtime=runtime,
            type=agent.agent_name,
            factory=lambda: ag_class(
                agent=agent,
                data_identifier=data_identifier,
                next_agent_topic=next_agent_topic,
                tools=tools,
            ),
        )
        await runtime.add_subscription(
            TypeSubscription(topic_type=agent_name, agent_type=reg_agent.type)
        )


class AgentMessage(BaseModel):
    content: str


class LLMUsageTracker(logging.Handler):
    def __init__(
        self,
        agents: Agents,
        config: IngeniousSettings,
        chat_history_repository: ChatHistoryRepository,
        revision_id: str,
        identifier: str,
        event_type: str,
    ) -> None:
        """Logging handler that tracks the number of tokens used in the prompt and completion."""
        super().__init__()
        self._prompt_tokens = 0
        self._agents = agents
        self._completion_tokens = 0
        self._queue: List[AgentChat] = []
        self._config = config
        self._chat_history_database: ChatHistoryRepository = chat_history_repository
        self._revision_id: str = revision_id
        self._identifier: str = identifier
        self._event_type: str = event_type

    @property
    def tokens(self) -> int:
        return self._prompt_tokens + self._completion_tokens

    @property
    def prompt_tokens(self) -> int:
        return self._prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self._completion_tokens

    def reset(self) -> None:
        self._prompt_tokens = 0
        self._completion_tokens = 0

    async def write_llm_responses_to_file(self, file_prefixes: List[str] = []) -> None:
        for agent_chat in self._queue:
            agent = self._agents.get_agent_by_name(agent_chat.target_agent_name)
            if agent.log_to_prompt_tuner:
                fs = FileStorage(self._config)
                output_path = await fs.get_output_path(self._revision_id)
                content = agent_chat.model_dump_json()
                temp_file_prefixes = file_prefixes.copy()
                temp_file_prefixes.append("agent_response")
                temp_file_prefixes.append(self._event_type)
                temp_file_prefixes.append(agent_chat.source_agent_name)
                temp_file_prefixes.append(agent_chat.target_agent_name)
                temp_file_prefixes.append(self._identifier)
                await fs.write_file(
                    content, f"{'_'.join(temp_file_prefixes)}.md", output_path
                )

    # TODO: Implement this function
    async def write_llm_responses_to_repository(
        self, user_id: str, thread_id: str, message_id: str
    ) -> None:
        for agent_chat in self._queue:
            agent = self._agents.get_agent_by_name(agent_chat.target_agent_name)
            if agent.log_to_prompt_tuner:
                fs = FileStorage(self._config)
                output_path = await fs.get_output_path(self._revision_id)
                content = agent_chat.model_dump_json()
                await fs.write_file(
                    content,
                    f"agent_response_{self._event_type}_{agent_chat.source_agent_name}_{agent_chat.target_agent_name}_{self._identifier}.md",
                    output_path,
                )

                message: ChatHistoryMessage = ChatHistoryMessage(
                    user_id=user_id,
                    thread_id=thread_id,
                    message_id=message_id,
                    role="agent_chat",
                    # Get the item from the queue where chat_name = "summary"
                    content=agent_chat.model_dump_json(),
                    content_filter_results=None,
                    tool_calls=None,
                    tool_call_id=None,
                    tool_call_function=None,
                )

                await self._chat_history_database.add_message(message=message)

    async def post_chats_to_queue(self, target_queue: asyncio.Queue[AgentChat]) -> None:
        for agent_chat in self._queue:
            agent = self._agents.get_agent_by_name(agent_chat.target_agent_name)
            await agent.log(agent_chat, target_queue)

    def _extract_agent_identifiers(
        self, agent_id: Optional[str]
    ) -> Optional[tuple[str, str]]:
        """Extract agent name and source name from agent_id."""
        if not agent_id:
            return None
        parts = agent_id.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1]
        return None

    def _find_agent(self, agent_name: str) -> Optional[Any]:
        """Find agent by name, handling both Agents object and list."""
        if hasattr(self._agents, "get_agent_by_name"):
            try:
                return self._agents.get_agent_by_name(agent_name)
            except ValueError:
                pass
        return None

    def _extract_response_content(
        self, choices: Optional[List[Any]]
    ) -> tuple[str, bool]:
        """Extract response content and determine if chat should be added."""
        response = ""
        add_chat = True

        if not choices:
            return response, add_chat

        for choice in choices:
            if choice.message:
                if choice.message.content:
                    response += choice.message.content + "\n\n"
                if choice.message.tool_calls:
                    add_chat = False

        return response, add_chat

    def _extract_system_messages(self, messages: Optional[List[Any]]) -> str:
        """Extract and join system messages."""
        if not messages:
            return ""
        return "\n\n".join(
            r.content for r in messages if r and r.role == "system" and r.content
        )

    def _extract_user_messages(self, messages: Optional[List[Any]]) -> str:
        """Extract and join user messages."""
        if not messages:
            return ""
        return "\n\n".join(
            r.content for r in messages if r and r.role == "user" and r.content
        )

    def _append_tool_messages(
        self, user_input: str, messages: Optional[List[Any]]
    ) -> str:
        """Append tool messages to user input."""
        if not messages:
            return user_input

        tool_messages = [m for m in messages if m and m.role == "tool"]
        if not tool_messages:
            return user_input

        result = user_input + "\n\n---\n\n# Tool Messages\n\n"
        for msg in tool_messages:
            if msg.content:
                result += f"{msg.content}\n\n"
        return result

    def _update_agent_chat(
        self,
        agent: Any,
        source_name: str,
        response: str,
        system_input: str,
        user_input: str,
        event: LLMCallEvent,
        add_chat: bool,
    ) -> None:
        """Update agent-specific chat data."""
        chat = agent.get_agent_chat_by_source(source=source_name)
        chat.chat_response = Response(
            chat_message=TextMessage(content=response, source=source_name)
        )
        chat.prompt_tokens = event.prompt_tokens
        chat.completion_tokens = event.completion_tokens
        chat.system_prompt = system_input
        chat.user_message = user_input
        chat.end_time = datetime.now().timestamp()
        if add_chat:
            self._queue.append(chat)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit the log record."""
        try:
            if not isinstance(record.msg, LLMCallEvent):
                return

            event: LLMCallEvent = record.msg
            kwargs: LLMEventKwargs = LLMEventKwargs.model_validate(event.kwargs)

            # Extract agent identifiers
            identifiers = self._extract_agent_identifiers(kwargs.agent_id)
            if not identifiers:
                return
            agent_name, source_name = identifiers

            # Find agent
            agent = self._find_agent(agent_name)

            # Extract response and check if chat should be added
            response, add_chat = self._extract_response_content(
                kwargs.response.choices if kwargs.response else None
            )

            # Extract message inputs
            system_input = self._extract_system_messages(kwargs.messages)
            user_input = self._extract_user_messages(kwargs.messages)
            user_input = self._append_tool_messages(user_input, kwargs.messages)

            # Update token counts
            self._prompt_tokens += event.prompt_tokens
            self._completion_tokens += event.completion_tokens

            # Update agent-specific data if available
            if agent:
                self._update_agent_chat(
                    agent,
                    source_name,
                    response,
                    system_input,
                    user_input,
                    event,
                    add_chat,
                )

        except Exception as e:
            print(f"Failed to emit log record :{e}")
            self.handleError(record)


class IProjectAgents(ABC):
    def __init__(self) -> None:
        pass

    @abstractmethod
    def Get_Project_Agents(self, config: Config) -> Agents:
        pass
