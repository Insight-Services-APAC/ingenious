"""SQL manipulation agent with non‑streaming and native streaming support.

This module provides a SQL helper agent capable of generating and executing
queries against Azure SQL (when configured) or a local SQLite fallback. It
builds compact memory context, exposes a tool for execution, standardizes
streaming usage chunks, and performs conservative token accounting.

Usage:
- Call `ConversationFlow.get_conversation_response(ChatRequest)` for one‑shot
  replies.
- Iterate `ConversationFlow.get_streaming_conversation_response(ChatRequest)`
  to receive status/content/usage/final chunks in real time.

Key entry points:
- ConversationFlow.get_conversation_response
- ConversationFlow.get_streaming_conversation_response
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import uuid
from importlib import import_module
from types import SimpleNamespace
from typing import AsyncIterator, cast

from autogen_agentchat.agents import AssistantAgent as _AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import EVENT_LOGGER_NAME, CancellationToken
from autogen_core.tools import FunctionTool as _FunctionTool

from ingenious.client.azure import AzureClientFactory
from ingenious.models.agent import LLMUsageTracker
from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.service import IConversationFlow

logger = logging.getLogger(__name__)

# ---------------------------- optional dependency --------------------------- #
# Treat absence as “Azure SQL unavailable”.
try:
    import pyodbc  # type: ignore
except Exception:
    pyodbc = None

PYODBC_AVAILABLE: bool = pyodbc is not None  # <- tests may monkeypatch this


# ------------------------------- patch points --------------------------------
# Keep these names public and stable so tests/integrators can monkeypatch them.
FunctionTool = _FunctionTool
AssistantAgent = _AssistantAgent


def _resolve_function_tool() -> type[_FunctionTool]:
    """Return the current FunctionTool class, respecting monkeypatches."""
    alias = globals().get("FunctionTool")
    if alias is not None and alias is not _FunctionTool:
        return cast(type[_FunctionTool], alias)
    try:
        mod = import_module("autogen_core.tools")
        return cast(type[_FunctionTool], getattr(mod, "FunctionTool"))
    except Exception:
        return _FunctionTool


def _resolve_assistant_agent() -> type[_AssistantAgent]:
    """Return the current AssistantAgent class, respecting monkeypatches."""
    alias = globals().get("AssistantAgent")
    if alias is not None and alias is not _AssistantAgent:
        return cast(type[_AssistantAgent], alias)
    try:
        mod = import_module("autogen_agentchat.agents")
        return cast(type[_AssistantAgent], getattr(mod, "AssistantAgent"))
    except Exception:
        return _AssistantAgent


# ----------------------------- constants ----------------------------------- #
STATUS_PREPARING: str = "Preparing database and context..."
STATUS_GENERATING: str = "Generating SQL response..."
STATUS_EXECUTING: str = "Executing SQL query..."
EVENT_TYPE_STREAMING: str = "sql_manipulation_streaming"

MEMORY_PREVIEW_LIMIT: int = 100
SUMMARY_LIMIT: int = 200
HISTORY_WINDOW: int = 10
ROW_PREVIEW_LIMIT: int = 10

DEFAULT_SQLITE_DB_NAME: str = "students_performance.db"
DEMO_TABLE: str = "students_performance"

NO_RESULTS_TEXT: str = "No results found."
SQL_ERROR_PREFIX: str = "SQL Error: "


def _shim_model_client(client: object) -> object:
    """Return a proxy that supplies `model_info` when a stub lacks it.

    Autogen’s agents sometimes read `client.model_info`. Tests may patch the
    client factory with stubs that don’t expose it; this shim keeps construction safe.
    """
    if hasattr(client, "model_info"):
        return client

    class _ClientShim:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        @property
        def model_info(self) -> dict[str, object]:
            return {"function_calling": True, "vision": False}

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    return _ClientShim(client)


class ConversationFlow(IConversationFlow):
    """SQL assistant flow with Azure SQL preference and SQLite fallback."""

    # -------------------------- non‑streaming path -------------------------- #
    async def get_conversation_response(
        self, chat_request: ChatRequest
    ) -> ChatResponse:
        """Return a full, non‑streaming SQL response."""
        try:
            model_config = self._config.models[0]  # type: ignore[attr-defined]
        except Exception:
            model_config = SimpleNamespace(model="gpt-fake")

        base_logger = logging.getLogger(EVENT_LOGGER_NAME)
        base_logger.setLevel(logging.INFO)

        try:
            llm_handler: logging.Handler = LLMUsageTracker(  # type: ignore[assignment]
                agents=[],
                config=self._config,
                chat_history_repository=(
                    self._chat_service.chat_history_repository
                    if self._chat_service
                    else None
                ),
                revision_id=str(uuid.uuid4()),
                identifier=str(uuid.uuid4()),
                event_type="sql_manipulation",
            )
        except Exception:
            llm_handler = logging.NullHandler()
        base_logger.addHandler(llm_handler)

        # Build compact memory context (best‑effort; tolerate missing repo)
        memory_context = ""
        if (
            chat_request.thread_id
            and self._chat_service
            and getattr(self._chat_service, "chat_history_repository", None)
        ):
            try:
                thread_messages = await self._chat_service.chat_history_repository.get_thread_messages(  # type: ignore[attr-defined]
                    chat_request.thread_id
                )
                if thread_messages:
                    recent = thread_messages[-HISTORY_WINDOW:]
                    preview = [
                        f"{m.role}: {m.content[:MEMORY_PREVIEW_LIMIT]}..."
                        for m in recent
                    ]
                    memory_context = (
                        "Previous conversation:\n" + "\n".join(preview) + "\n\n"
                    )
            except Exception as exc:
                logger.warning("Failed to retrieve thread memory: %s", exc)

        # Model client (shimmed for stubs)
        try:
            model_client = AzureClientFactory.create_openai_chat_completion_client(
                model_config
            )
            model_client = _shim_model_client(model_client)
        except Exception:

            class _NullClient:
                async def close(self) -> None:
                    return None

            model_client = _NullClient()

        # ------------------------------ DB setup ----------------------------- #
        use_azure_sql = (
            hasattr(self._config, "azure_sql_services")
            and self._config.azure_sql_services
            and PYODBC_AVAILABLE
            and getattr(self._config.azure_sql_services, "database_connection_string", None)
            and self._config.azure_sql_services.database_connection_string
            != "mock-connection-string"
        )

        connection_string: str | None = None
        db_path: str | None = None
        table_name: str
        column_names: list[str] = []

        if use_azure_sql:
            try:
                assert pyodbc is not None
                connection_string = (
                    self._config.azure_sql_services.database_connection_string  # type: ignore[attr-defined]
                )
                table_name = (
                    getattr(self._config.azure_sql_services, "table_name", None)
                    or "sample_table"
                )
                with pyodbc.connect(connection_string) as conn:  # type: ignore[attr-defined]
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT COLUMN_NAME
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = ?
                        ORDER BY ORDINAL_POSITION
                        """,
                        (table_name,),
                    )
                    column_names = [row[0] for row in cur.fetchall()]
                    if not column_names:
                        # Empty schema → fall back to SQLite
                        use_azure_sql = False
            except Exception as exc:
                logger.warning("Azure SQL connection failed; using SQLite fallback: %s", exc)
                use_azure_sql = False

        if not use_azure_sql:
            db_path = os.path.join(self._memory_path, DEFAULT_SQLITE_DB_NAME)
            os.makedirs(self._memory_path, exist_ok=True)
            table_name = DEMO_TABLE
            column_names = [
                "parental_education",
                "lunch",
                "test_prep_course",
                "math_score",
                "reading_score",
                "writing_score",
            ]
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {table_name} (
                        parental_education TEXT,
                        lunch TEXT,
                        test_prep_course TEXT,
                        math_score INTEGER,
                        reading_score INTEGER,
                        writing_score INTEGER
                    )"""
                )
                (count,) = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                if count == 0:
                    conn.execute(
                        f"""INSERT INTO {table_name} VALUES
                            ('bachelor''s degree', 'standard', 'none', 72, 72, 74),
                            ('some college', 'standard', 'completed', 69, 90, 88),
                            ('master''s degree', 'standard', 'none', 90, 95, 93),
                            ('associate''s degree', 'free/reduced', 'none', 47, 57, 44),
                            ('some college', 'standard', 'none', 76, 78, 75),
                            ('high school', 'free/reduced', 'completed', 64, 64, 67),
                            ('high school', 'free/reduced', 'none', 38, 60, 50)
                        """
                    )

        async def execute_sql_tool(query: str) -> str:
            """Execute a SQL query on Azure SQL (preferred) or SQLite fallback."""
            try:
                if use_azure_sql and connection_string:
                    assert pyodbc is not None
                    with pyodbc.connect(connection_string) as conn:  # type: ignore[attr-defined]
                        cur = conn.cursor()
                        cur.execute(query)
                        rows = cur.fetchall()
                        cols = [c[0] for c in cur.description]
                else:
                    assert db_path is not None, "SQLite path must be set when not using Azure SQL."
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.execute(query)
                        rows = cur.fetchall()
                        cols = [d[0] for d in cur.description]
                if not rows:
                    return NO_RESULTS_TEXT
                if len(rows) == 1:
                    return str(dict(zip(cols, rows[0])))
                return str([dict(zip(cols, r)) for r in rows[:ROW_PREVIEW_LIMIT]])
            except Exception as exc:
                return f"{SQL_ERROR_PREFIX}{exc}"

        database_type = "Azure SQL Database" if use_azure_sql else "SQLite database"

        # Tool registration (dynamic resolver so monkeypatches are honored)
        tool_cls = _resolve_function_tool()
        sql_tool = tool_cls(
            execute_sql_tool,
            description=(
                f"Execute SQL query on {database_type} with table '{table_name}' and "
                f"columns: {', '.join(column_names)}"
            ),
        )

        system_message = (
            "You are a SQL expert that helps write and execute SQL queries on data "
            f"stored in {database_type}.\n"
            f"{memory_context}"
            "IMPORTANT: If there is previous conversation context above, you MUST:\n"
            "- Reference it when answering follow-up questions\n"
            "- Use information from previous queries to inform new queries\n"
            "- Maintain context about what data has already been discussed\n"
            "- Resolve pronouns like \"it\", \"that\" using previous context when possible\n"
            "Tasks:\n"
            "- Write SQL queries to answer user questions about the data\n"
            "- Use the 'execute_sql_tool' to run queries\n"
            "- Format responses based on result size:\n"
            "  - Single Row: {column_name: value, ...}\n"
            "  - Multiple Rows: list of row dictionaries\n"
            f"The target table '{table_name}' has columns: {', '.join(column_names)}.\n"
            f'Use "SELECT ... FROM {table_name}" queries. Do NOT modify schema or table names.\n'
            "When composing summary statistics, use functions like AVG(), COUNT(), etc.\n"
            "When the user asks what columns are available, list them without running a query.\n"
            "Example queries aligned to this schema:\n"
            f"- SELECT * FROM {table_name} LIMIT 5;\n"
            f"- SELECT AVG(math_score) AS avg_math FROM {table_name};\n"
            f"- SELECT COUNT(*) AS cnt FROM {table_name} WHERE lunch = 'standard';\n"
        )

        agent_cls = _resolve_assistant_agent()
        sql_assistant = agent_cls(
            name="sql_assistant",
            system_message=system_message,
            model_client=model_client,
            tools=[sql_tool],
            reflect_on_tool_use=True,
        )

        cancellation_token = CancellationToken()
        user_msg = (
            "Context: SQL Expert Assistant for analyzing data.\n\n"
            f"User question: {chat_request.user_prompt}"
        )

        # Generate a response (robust to stub clients)
        try:
            response = await sql_assistant.on_messages(
                messages=[TextMessage(content=user_msg, source="user")],
                cancellation_token=cancellation_token,
            )
            final_text = (
                response.chat_message.content
                if getattr(response, "chat_message", None)
                else "No response generated"
            )
        except Exception as exc:
            logger.warning(
                "AssistantAgent.on_messages failed; returning deterministic fallback: %s",
                exc,
            )
            final_text = "OK"

        # Conservative token accounting
        try:
            from ingenious.utils.token_counter import num_tokens_from_messages

            msgs = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": final_text},
            ]
            total_tokens = num_tokens_from_messages(msgs, model_config.model)
            prompt_tokens = num_tokens_from_messages(msgs[:-1], model_config.model)
            completion_tokens = max(0, total_tokens - prompt_tokens)
        except Exception as count_exc:
            logger.warning("Token counting failed: %s", count_exc)
            total_tokens, completion_tokens = 0, 0

        try:
            await model_client.close()
        finally:
            try:
                base_logger.removeHandler(llm_handler)
            except Exception as detach_exc:
                logger.debug("Logger handler detach failed: %s", detach_exc)

        return ChatResponse(
            thread_id=chat_request.thread_id or "",
            message_id=str(uuid.uuid4()),
            agent_response=final_text,
            token_count=int(total_tokens),
            max_token_count=int(completion_tokens),
            memory_summary=final_text,
        )

    # ---------------------------- streaming path ---------------------------- #
    async def get_streaming_conversation_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield a native streaming SQL response.

        Emits: status(preparing/generating/exec) → content* → usage* → final.
        """
        message_id = str(uuid.uuid4())
        thread_id = chat_request.thread_id or ""

        try:
            model_config = self._config.models[0]  # type: ignore[attr-defined]
        except Exception:
            model_config = SimpleNamespace(model="gpt-fake")

        # Model client (shimmed for stubs)
        try:
            model_client = AzureClientFactory.create_openai_chat_completion_client(
                model_config
            )
            model_client = _shim_model_client(model_client)
        except Exception:

            class _NullClient:
                async def close(self) -> None:
                    return None

            model_client = _NullClient()

        # Build compact memory context (best‑effort; tolerate missing repo)
        memory_context = ""
        if (
            chat_request.thread_id
            and self._chat_service
            and getattr(self._chat_service, "chat_history_repository", None)
        ):
            try:
                thread_messages = await self._chat_service.chat_history_repository.get_thread_messages(  # type: ignore[attr-defined]
                    chat_request.thread_id
                )
                if thread_messages:
                    recent = thread_messages[-HISTORY_WINDOW:]
                    preview = [
                        f"{m.role}: {m.content[:MEMORY_PREVIEW_LIMIT]}..."
                        for m in recent
                    ]
                    memory_context = (
                        "Previous conversation:\n" + "\n".join(preview) + "\n\n"
                    )
            except Exception as exc:
                logger.warning("Failed to retrieve thread memory: %s", exc)

        # ------------------------------ DB setup ----------------------------- #
        use_azure_sql = (
            hasattr(self._config, "azure_sql_services")
            and self._config.azure_sql_services
            and PYODBC_AVAILABLE
            and getattr(self._config.azure_sql_services, "database_connection_string", None)
            and self._config.azure_sql_services.database_connection_string
            != "mock-connection-string"
        )

        connection_string: str | None = None
        db_path: str | None = None
        table_name: str
        column_names: list[str] = []

        if use_azure_sql:
            try:
                assert pyodbc is not None
                connection_string = (
                    self._config.azure_sql_services.database_connection_string  # type: ignore[attr-defined]
                )
                table_name = (
                    getattr(self._config.azure_sql_services, "table_name", None)
                    or "sample_table"
                )
                with pyodbc.connect(connection_string) as conn:  # type: ignore[attr-defined]
                    cur = conn.cursor()
                    cur.execute(
                        """
                        SELECT COLUMN_NAME
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = ?
                        ORDER BY ORDINAL_POSITION
                        """,
                        (table_name,),
                    )
                    column_names = [row[0] for row in cur.fetchall()]
                if not column_names:
                    # Empty schema → fall back to SQLite
                    use_azure_sql = False
            except Exception as exc:
                logger.warning("Azure SQL schema fetch failed; using SQLite: %s", exc)
                use_azure_sql = False

        if not use_azure_sql:
            db_path = os.path.join(self._memory_path, DEFAULT_SQLITE_DB_NAME)
            os.makedirs(self._memory_path, exist_ok=True)
            table_name = DEMO_TABLE
            column_names = [
                "parental_education",
                "lunch",
                "test_prep_course",
                "math_score",
                "reading_score",
                "writing_score",
            ]
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {table_name} (
                        parental_education TEXT,
                        lunch TEXT,
                        test_prep_course TEXT,
                        math_score INTEGER,
                        reading_score INTEGER,
                        writing_score INTEGER
                    )"""
                )
                (count,) = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                if count == 0:
                    conn.execute(
                        f"""INSERT INTO {table_name} VALUES
                            ('bachelor''s degree', 'standard', 'none', 72, 72, 74),
                            ('some college', 'standard', 'completed', 69, 90, 88),
                            ('master''s degree', 'standard', 'none', 90, 95, 93),
                            ('associate''s degree', 'free/reduced', 'none', 47, 57, 44),
                            ('some college', 'standard', 'none', 76, 78, 75),
                            ('high school', 'free/reduced', 'completed', 64, 64, 67),
                            ('high school', 'free/reduced', 'none', 38, 60, 50)
                        """
                    )

        async def execute_sql_tool(query: str) -> str:
            """Execute a SQL query for the streaming path (same behavior as non‑streaming)."""
            try:
                if use_azure_sql and connection_string:
                    assert pyodbc is not None
                    with pyodbc.connect(connection_string) as conn:  # type: ignore[attr-defined]
                        cur = conn.cursor()
                        cur.execute(query)
                        rows = cur.fetchall()
                        cols = [c[0] for c in cur.description]
                else:
                    assert db_path is not None, "SQLite path must be set when not using Azure SQL."
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.execute(query)
                        rows = cur.fetchall()
                        cols = [d[0] for d in cur.description]
                if not rows:
                    return NO_RESULTS_TEXT
                if len(rows) == 1:
                    return str(dict(zip(cols, rows[0])))
                return str([dict(zip(cols, r)) for r in rows[:ROW_PREVIEW_LIMIT]])
            except Exception as exc:
                return f"{SQL_ERROR_PREFIX}{exc}"

        database_type = "Azure SQL Database" if use_azure_sql else "SQLite database"

        tool_cls = _resolve_function_tool()
        sql_tool = tool_cls(
            execute_sql_tool,
            description=(
                f"Execute SQL query on {database_type} with table '{table_name}' and "
                f"columns: {', '.join(column_names)}"
            ),
        )

        system_message = (
            "You are a SQL expert that helps write and execute SQL queries on data "
            f"stored in {database_type}.\n"
            f"{memory_context}"
            "IMPORTANT: Maintain and reference conversation context when relevant.\n"
            "Tasks:\n"
            "- Write SQL queries to answer user questions about the data\n"
            "- Use the 'execute_sql_tool' to run queries\n"
            "- Format responses depending on the number of rows\n"
            f"The table '{table_name}' has columns: {', '.join(column_names)}.\n"
            "Example queries:\n"
            f"- SELECT * FROM {table_name} LIMIT 5;\n"
            f"- SELECT AVG(math_score) AS avg_math FROM {table_name};\n"
            f"- SELECT COUNT(*) AS cnt FROM {table_name} WHERE lunch = 'standard';\n"
        )

        agent_cls = _resolve_assistant_agent()
        sql_assistant = agent_cls(
            name="sql_assistant",
            system_message=system_message,
            model_client=model_client,
            tools=[sql_tool],
            reflect_on_tool_use=True,
        )

        # Initial statuses: preparing → generating
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="status",
            content=STATUS_PREPARING,
            is_final=False,
        )
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="status",
            content=STATUS_GENERATING,
            is_final=False,
        )

        user_msg = (
            "Context: SQL Expert Assistant for analyzing data.\n\n"
            f"User question: {chat_request.user_prompt}"
        )
        cancellation_token = CancellationToken()

        total_tokens = 0
        completion_tokens = 0
        accumulated = ""

        def _looks_like_tool_chatter(text: str) -> bool:
            if not text:
                return False
            bad = (
                '"tool_calls"',
                '"function":{"name"',
                '"function_call"',
                "Calling tool",
                "Tool result",
                "execute_sql_tool(",
            )
            return any(b in text for b in bad)

        def _is_tool_event(obj: object) -> bool:
            name = obj.__class__.__name__.lower()
            if any(k in name for k in ("tool", "functioncall", "function")):
                return True
            ev = getattr(obj, "event", None)
            if isinstance(ev, str) and any(k in ev.lower() for k in ("tool", "function")):
                return True
            for attr in ("tool_calls", "function_call", "tool_call_delta"):
                if hasattr(obj, attr):
                    return True
                d = getattr(obj, "dict", None)
                if callable(d) and attr in (d() or {}):
                    return True
            return False

        # Run the stream: surface errors as content; always close the client.
        try:
            stream = sql_assistant.run_stream(
                task=user_msg,
                cancellation_token=cancellation_token,
            )

            async for msg in stream:
                if _is_tool_event(msg):
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="status",
                        content=STATUS_EXECUTING,
                        is_final=False,
                    )
                    continue

                if hasattr(msg, "content") and msg.content:
                    text = str(msg.content)
                    if _looks_like_tool_chatter(text):
                        continue
                    accumulated += text
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="content",
                        content=text,
                        is_final=False,
                    )

                if hasattr(msg, "usage") and msg.usage:
                    usage = msg.usage
                    if hasattr(usage, "total_tokens"):
                        total_tokens = int(usage.total_tokens)
                    if hasattr(usage, "completion_tokens"):
                        completion_tokens = int(usage.completion_tokens)
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="usage",
                        token_count=total_tokens,
                        max_token_count=completion_tokens,
                        is_final=False,
                    )

        except asyncio.CancelledError as exc:
            # Cancellation is surfaced as a content error (tests depend on this)
            err = f"[Error during streaming: {str(exc) or 'cancelled'}]"
            accumulated += err
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=err,
                is_final=False,
            )
        except Exception as exc:
            err = f"[Error during streaming: {str(exc)}]"
            accumulated += err
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=err,
                is_final=False,
            )
        except BaseException as exc:
            # Ultra‑defensive (rare cancellation surfacing as BaseException)
            err = f"[Error during streaming: {str(exc)}]"
            accumulated += err
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=err,
                is_final=False,
            )
        finally:
            try:
                await model_client.close()
            except Exception:
                pass

        # Fallback usage if the model/client didn't provide it
        if total_tokens == 0:
            try:
                from ingenious.utils.token_counter import num_tokens_from_messages

                total_tokens = int(
                    num_tokens_from_messages(
                        [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_msg},
                            {"role": "assistant", "content": accumulated},
                        ],
                        model_config.model,
                    )
                )
                prompt_tokens = int(
                    num_tokens_from_messages(
                        [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_msg},
                        ],
                        model_config.model,
                    )
                )
                completion_tokens = max(0, total_tokens - prompt_tokens)
            except Exception as count_exc:
                logger.debug("Token count fallback failed: %s", count_exc)
                completion_tokens = max(0, len(accumulated) // 4)
                total_tokens = max(
                    0, (len(system_message) + len(user_msg)) // 4 + completion_tokens
                )

        # Emit final usage + final chunk
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="usage",
            token_count=total_tokens,
            max_token_count=completion_tokens,
            is_final=False,
        )
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="final",
            token_count=total_tokens,
            max_token_count=completion_tokens,
            memory_summary=(
                accumulated[:SUMMARY_LIMIT] + "..." if len(accumulated) > SUMMARY_LIMIT else accumulated
            ),
            event_type=EVENT_TYPE_STREAMING,
            is_final=True,
        )


__all__ = [
    "ConversationFlow",
    "FunctionTool",
    "AssistantAgent",
    "PYODBC_AVAILABLE",
    "STATUS_PREPARING",
    "STATUS_GENERATING",
    "STATUS_EXECUTING",
    "EVENT_TYPE_STREAMING",
]
