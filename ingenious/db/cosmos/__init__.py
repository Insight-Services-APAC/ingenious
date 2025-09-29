import uuid
from typing import Any, Dict, List, Optional, cast

from azure.cosmos import ContainerProxy, CosmosClient, PartitionKey

from ingenious.client.azure import AzureClientFactory
from ingenious.common.enums import AuthenticationMethod
from ingenious.config import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import IChatHistoryRepository
from ingenious.errors import DatabaseQueryError
from ingenious.models.message import Message

logger = get_logger(__name__)


class cosmos_ChatHistoryRepository(IChatHistoryRepository):
    """Cosmos DB implementation of IChatHistoryRepository for managing chat history."""

    def __init__(self, config: IngeniousSettings) -> None:
        self.config = config

        if config.cosmos_service is None:
            raise ValueError("Cosmos service configuration is missing")

        try:
            self.client: CosmosClient = AzureClientFactory.create_cosmos_client(
                cosmos_config=config.cosmos_service
            )
            database_id = config.cosmos_service.database_name or "ingenious-db"
        except Exception as e:
            raise DatabaseQueryError("Failed to create CosmosClient", cause=e)

        self._create_database(database_id)
        self._create_containers()

    def _create_database(self, database_id):
        authentication_method = getattr(
            self.config.cosmos_service, "authentication_method", None
        )

        if authentication_method == AuthenticationMethod.TOKEN:
            self.database = self.client.create_database_if_not_exists(id=database_id)
        else:
            self.database = self.client.get_database_client(database_id)

    def _create_containers(self):
        authentication_method = getattr(
            self.config.cosmos_service, "authentication_method", None
        )
        if authentication_method == AuthenticationMethod.TOKEN:
            self.chat_history: ContainerProxy = (
                self.database.create_container_if_not_exists(
                    id="chat_history", partition_key=PartitionKey(path="/thread_id")
                )
            )
            self.chat_history_summary: ContainerProxy = (
                self.database.create_container_if_not_exists(
                    id="chat_history_summary",
                    partition_key=PartitionKey(path="/thread_id"),
                )
            )
            self.users: ContainerProxy = self.database.create_container_if_not_exists(
                id="users", partition_key=PartitionKey(path="/identifier")
            )
            self.threads: ContainerProxy = self.database.create_container_if_not_exists(
                id="threads", partition_key=PartitionKey(path="/id")
            )
            self.steps: ContainerProxy = self.database.create_container_if_not_exists(
                id="steps", partition_key=PartitionKey(path="/threadId")
            )
            self.elements: ContainerProxy = (
                self.database.create_container_if_not_exists(
                    id="elements", partition_key=PartitionKey(path="/threadId")
                )
            )
            self.feedbacks: ContainerProxy = (
                self.database.create_container_if_not_exists(
                    id="feedbacks", partition_key=PartitionKey(path="/threadId")
                )
            )
        else:
            self.chat_history: ContainerProxy = self.database.get_container_client(
                "chat_history"
            )
            self.chat_history_summary: ContainerProxy = (
                self.database.get_container_client("chat_history_summary")
            )
            self.users: ContainerProxy = self.database.get_container_client("users")
            self.threads: ContainerProxy = self.database.get_container_client("threads")
            self.steps: ContainerProxy = self.database.get_container_client("steps")
            self.elements: ContainerProxy = self.database.get_container_client(
                "elements"
            )
            self.feedbacks: ContainerProxy = self.database.get_container_client(
                "feedbacks"
            )

    # Utility mappers
    def _message_to_doc(self, m: Message) -> Dict[str, Any]:
        return {
            "id": m.message_id or str(uuid.uuid4()),
            "user_id": m.user_id,
            "thread_id": m.thread_id,
            "message_id": m.message_id,
            "positive_feedback": m.positive_feedback,
            "timestamp": (m.timestamp.isoformat() if m.timestamp else None),
            "role": m.role,
            "content": m.content,
            "content_filter_results": m.content_filter_results,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "tool_call_function": m.tool_call_function,
        }

    def _doc_to_message(self, d: Dict[str, Any]) -> Message:
        from datetime import datetime

        ts_val = d.get("timestamp")
        ts = datetime.fromisoformat(ts_val) if isinstance(ts_val, str) else None
        return Message(
            user_id=d.get("user_id"),
            thread_id=d.get("thread_id", ""),
            message_id=d.get("message_id"),
            positive_feedback=d.get("positive_feedback"),
            timestamp=ts,
            role=d.get("role", ""),
            content=d.get("content"),
            content_filter_results=d.get("content_filter_results"),
            tool_calls=d.get("tool_calls"),
            tool_call_id=d.get("tool_call_id"),
            tool_call_function=d.get("tool_call_function"),
        )

    # IChatHistoryRepository implementations
    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        try:
            # Resolve user identifier if possible
            user_identifier = None
            if user_id:
                try:
                    # Users are stored by identifier; different model than SQL (id is UUID)
                    # We will store user by id as identifier as a fallback
                    user = list(
                        self.users.query_items(
                            query="SELECT * FROM c WHERE c.id = @id",
                            parameters=[{"name": "@id", "value": user_id}],
                            enable_cross_partition_query=True,
                        )
                    )
                    if user:
                        user_identifier = user[0].get("identifier") or user_id
                except Exception:
                    user_identifier = user_id

            doc = {
                "id": thread_id,
                "createdAt": None if metadata is not None else None,
                "name": name
                if name is not None
                else (
                    metadata.get("name") if metadata and "name" in metadata else None
                ),
                "userId": user_id,
                "userIdentifier": user_identifier,
                "tags": tags,
                "metadata": metadata,
            }
            # Remove None values for upsert cleanliness
            doc = {k: v for k, v in doc.items() if v is not None} | {"id": thread_id}
            self.threads.upsert_item(doc)
            return ""
        except Exception as e:
            raise DatabaseQueryError("Failed to upsert thread in Cosmos", cause=e)

    async def add_message(self, message: Message) -> str:
        try:
            if not message.message_id:
                message.message_id = str(uuid.uuid4())
            doc = self._message_to_doc(message)
            self.chat_history.create_item(doc)
            return message.message_id
        except Exception as e:
            raise DatabaseQueryError("Failed to add message to Cosmos", cause=e)

    async def add_user(self, identifier: str) -> IChatHistoryRepository.User:
        try:
            user_doc = {
                "id": str(uuid.uuid4()),
                "identifier": identifier,
                "metadata": {},
                "createdAt": self.get_now_as_string(),
            }
            self.users.upsert_item(user_doc)
            from uuid import UUID as _UUID

            return IChatHistoryRepository.User(
                id=_UUID(user_doc["id"]),
                identifier=identifier,
                metadata={},
                createdAt=user_doc["createdAt"],
            )
        except Exception as e:
            raise DatabaseQueryError("Failed to add user in Cosmos", cause=e)

    async def get_user(self, identifier: str) -> IChatHistoryRepository.User | None:
        try:
            results = list(
                self.users.query_items(
                    query="SELECT * FROM c WHERE c.identifier = @identifier",
                    parameters=[{"name": "@identifier", "value": identifier}],
                    enable_cross_partition_query=True,
                )
            )
            if results:
                d = results[0]
                from uuid import UUID as _UUID

                return IChatHistoryRepository.User(
                    id=_UUID(
                        str(d.get("id") or "00000000-0000-0000-0000-000000000000")
                    ),
                    identifier=str(d.get("identifier", "")),
                    metadata=dict(d.get("metadata", {})),
                    createdAt=str(d.get("createdAt")) if d.get("createdAt") else None,
                )
            # Auto-create if not exists
            return await self.add_user(identifier)
        except Exception as e:
            raise DatabaseQueryError("Failed to get user from Cosmos", cause=e)

    async def get_message(self, message_id: str, thread_id: str) -> Message | None:
        try:
            results = list(
                self.chat_history.query_items(
                    query="SELECT TOP 1 * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if results:
                return self._doc_to_message(results[0])
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to get message from Cosmos", cause=e)

    async def get_thread_messages(self, thread_id: str) -> List[Message]:
        try:
            # Get last 5 by timestamp desc then reverse to asc
            docs = list(
                self.chat_history.query_items(
                    query=(
                        "SELECT TOP 5 c.user_id, c.thread_id, c.message_id, c.positive_feedback, c.timestamp, "
                        "c.role, c.content, c.content_filter_results, c.tool_calls, c.tool_call_id, c.tool_call_function "
                        "FROM c WHERE c.thread_id = @tid ORDER BY c.timestamp DESC"
                    ),
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            messages = [self._doc_to_message(d) for d in reversed(docs)]
            return messages
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to get thread messages from Cosmos", cause=e
            )

    def _query_threads(
        self, identifier: str, thread_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Query threads for a user, optionally filtered by thread ID."""
        if thread_id:
            return list(
                self.threads.query_items(
                    query="SELECT * FROM c WHERE c.userIdentifier = @uid AND c.id = @tid",
                    parameters=[
                        {"name": "@uid", "value": identifier},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
        return list(
            self.threads.query_items(
                query="SELECT TOP 100 * FROM c WHERE c.userIdentifier = @uid ORDER BY c.createdAt DESC",
                parameters=[{"name": "@uid", "value": identifier}],
                enable_cross_partition_query=True,
            )
        )

    def _query_steps_for_threads(
        self, thread_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Query all steps for given thread IDs."""
        steps_by_thread: Dict[str, List[Dict[str, Any]]] = {
            tid: [] for tid in thread_ids
        }
        for tid in thread_ids:
            docs = list(
                self.steps.query_items(
                    query="SELECT * FROM c WHERE c.threadId = @tid ORDER BY c.createdAt ASC",
                    parameters=[{"name": "@tid", "value": tid}],
                    enable_cross_partition_query=True,
                )
            )
            steps_by_thread[tid] = docs
        return steps_by_thread

    def _query_elements_for_threads(
        self, thread_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Query all elements for given thread IDs."""
        elements_by_thread: Dict[str, List[Dict[str, Any]]] = {
            tid: [] for tid in thread_ids
        }
        for tid in thread_ids:
            docs = list(
                self.elements.query_items(
                    query="SELECT * FROM c WHERE c.threadId = @tid",
                    parameters=[{"name": "@tid", "value": tid}],
                    enable_cross_partition_query=True,
                )
            )
            elements_by_thread[tid] = docs
        return elements_by_thread

    def _get_feedback_for_step(
        self, step_id: str, thread_id: str
    ) -> Optional[IChatHistoryRepository.FeedbackDict]:
        """Query and parse feedback for a specific step."""
        feedback_docs = list(
            self.feedbacks.query_items(
                query="SELECT * FROM c WHERE c.forId = @fid AND c.threadId = @tid",
                parameters=[
                    {"name": "@fid", "value": step_id},
                    {"name": "@tid", "value": thread_id},
                ],
                enable_cross_partition_query=True,
            )
        )
        if not feedback_docs:
            return None

        fb = feedback_docs[0]
        return IChatHistoryRepository.FeedbackDict(
            forId=str(step_id),
            id=str(fb.get("id")) if fb.get("id") else None,
            value=1 if int(fb.get("value", 0) or 0) == 1 else 0,
            comment=fb.get("comment"),
        )

    def _normalize_step_type(self, raw_type: str) -> str:
        """Normalize step type to allowed values."""
        allowed_step_types = {
            "run",
            "tool",
            "llm",
            "embedding",
            "retrieval",
            "rerank",
            "undefined",
            "user_message",
            "assistant_message",
            "system_message",
        }
        return raw_type if raw_type in allowed_step_types else "undefined"

    def _build_step_dict(
        self,
        sd: Dict[str, Any],
        tid: str,
        feedback: Optional[IChatHistoryRepository.FeedbackDict],
    ) -> IChatHistoryRepository.StepDict:
        """Build a StepDict from raw step data."""
        raw_step_type = str(sd.get("type", "undefined"))
        step_type = self._normalize_step_type(raw_step_type)

        step_dict: IChatHistoryRepository.StepDict = {
            "id": str(sd.get("id", "")),
            "name": str(sd.get("name", "")),
            "type": cast(IChatHistoryRepository.StepType, step_type),
            "threadId": str(sd.get("threadId", tid)),
            "disableFeedback": bool(sd.get("disableFeedback", False)),
            "streaming": bool(sd.get("streaming", False)),
        }

        # Add optional string fields
        for field in [
            "parentId",
            "input",
            "output",
            "createdAt",
            "start",
            "end",
            "language",
        ]:
            if sd.get(field) is not None:
                step_dict[field] = str(sd.get(field))

        # Add optional boolean fields
        for field in ["waitForAnswer", "isError"]:
            if sd.get(field) is not None:
                step_dict[field] = bool(sd.get(field))

        # Add metadata if it's a dict
        if sd.get("metadata") is not None:
            meta = sd.get("metadata")
            if isinstance(meta, dict):
                step_dict["metadata"] = meta

        # Add tags
        if sd.get("tags") is not None:
            step_dict["tags"] = sd.get("tags")

        # Add generation if it's a dict
        if sd.get("generation") is not None:
            gen = sd.get("generation")
            if isinstance(gen, dict):
                step_dict["generation"] = gen

        # Add showInput (bool or str)
        if sd.get("showInput") is not None:
            show_input = sd.get("showInput")
            if isinstance(show_input, (bool, str)):
                step_dict["showInput"] = show_input

        # Add indent (int)
        if sd.get("indent") is not None:
            _indent = sd.get("indent")
            if isinstance(_indent, (int, str)):
                try:
                    step_dict["indent"] = int(_indent)
                except Exception:
                    pass

        if feedback is not None:
            step_dict["feedback"] = feedback

        return step_dict

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str]
    ) -> Optional[List[IChatHistoryRepository.ThreadDict]]:
        try:
            threads = self._query_threads(identifier, thread_id)

            if not threads:
                return []

            thread_ids = [t["id"] for t in threads]
            steps_by_thread = self._query_steps_for_threads(thread_ids)
            elements_by_thread = self._query_elements_for_threads(thread_ids)

            result: List[IChatHistoryRepository.ThreadDict] = []
            for t in threads:
                tid = t["id"]
                # Prepare containers locally to satisfy typing (elements is Optional)
                steps_list: List[IChatHistoryRepository.StepDict] = []
                elements_list: List[IChatHistoryRepository.ElementDict] = []
                thread_dict: IChatHistoryRepository.ThreadDict = {
                    "id": str(tid),
                    "createdAt": t.get("createdAt") or self.get_now_as_string(),
                    "name": t.get("name"),
                    "userId": t.get("userId"),
                    "userIdentifier": t.get("userIdentifier"),
                    "tags": t.get("tags"),
                    "metadata": t.get("metadata"),
                    "steps": steps_list,
                    "elements": elements_list,
                }

                # Steps with feedback join (do per step)
                steps_docs = steps_by_thread.get(tid, [])
                for sd in steps_docs:
                    feedback = self._get_feedback_for_step(sd.get("id"), tid)
                    step_dict = self._build_step_dict(sd, tid, feedback)
                    steps_list.append(step_dict)

                # Elements
                for el in elements_by_thread.get(tid, []):
                    # Build ElementDict safely with defaults for required fields
                    # Validate element enums
                    raw_el_type = str(el.get("type", "text"))
                    allowed_el_types = {
                        "image",
                        "text",
                        "pdf",
                        "tasklist",
                        "audio",
                        "video",
                        "file",
                        "plotly",
                        "component",
                    }
                    if raw_el_type not in allowed_el_types:
                        raw_el_type = "text"
                    raw_display = str(el.get("display", "inline"))
                    allowed_displays = {"inline", "side", "page"}
                    if raw_display not in allowed_displays:
                        raw_display = "inline"
                    raw_size = el.get("size")
                    allowed_sizes = {"small", "medium", "large"}
                    size_val: Optional[str] = (
                        str(raw_size) if raw_size in allowed_sizes else None
                    )
                    page_val: Optional[int] = None
                    _page = el.get("page")
                    if isinstance(_page, (int, str)):
                        try:
                            page_val = int(_page)
                        except Exception:
                            page_val = None

                    el_dict: IChatHistoryRepository.ElementDict = {
                        "id": str(el.get("id", "")),
                        "threadId": str(el.get("threadId"))
                        if el.get("threadId")
                        else None,
                        "type": cast(IChatHistoryRepository.ElementType, raw_el_type),
                        "chainlitKey": el.get("chainlitKey"),
                        "url": el.get("url"),
                        "objectKey": el.get("objectKey"),
                        "name": str(el.get("name", "")),
                        "display": cast(
                            IChatHistoryRepository.ElementDisplay, raw_display
                        ),
                        "size": cast(
                            Optional[IChatHistoryRepository.ElementSize], size_val
                        ),
                        "language": el.get("language"),
                        "page": page_val,
                        "autoPlay": el.get("autoPlay"),
                        "playerConfig": el.get("playerConfig"),
                        "forId": str(el.get("forId")) if el.get("forId") else None,
                        "mime": el.get("mime"),
                    }
                    elements_list.append(el_dict)

                result.append(thread_dict)

            return result
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to get threads for user from Cosmos", cause=e
            )

    async def update_message_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        try:
            # Fetch doc, patch and replace
            items = list(
                self.chat_history.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["positive_feedback"] = positive_feedback
            self.chat_history.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to update message feedback in Cosmos", cause=e
            )

    async def update_message_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        try:
            items = list(
                self.chat_history.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["content_filter_results"] = content_filter_results
            self.chat_history.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to update message CFR in Cosmos", cause=e)

    async def update_memory_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        try:
            items = list(
                self.chat_history_summary.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["positive_feedback"] = positive_feedback
            self.chat_history_summary.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to update memory feedback in Cosmos", cause=e
            )

    async def update_memory_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        try:
            items = list(
                self.chat_history_summary.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["content_filter_results"] = content_filter_results
            self.chat_history_summary.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to update memory CFR in Cosmos", cause=e)

    async def add_memory(self, message: Message) -> str:
        try:
            if not message.message_id:
                message.message_id = str(uuid.uuid4())
            doc = self._message_to_doc(message)
            self.chat_history_summary.create_item(doc)
            return message.message_id
        except Exception as e:
            raise DatabaseQueryError("Failed to add memory to Cosmos", cause=e)

    async def get_memory(self, message_id: str, thread_id: str) -> Message | None:
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query=(
                        "SELECT TOP 1 * FROM c WHERE c.thread_id = @tid ORDER BY c.timestamp DESC"
                    ),
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            if docs:
                return self._doc_to_message(docs[0])
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to get memory from Cosmos", cause=e)

    async def update_memory(self) -> None:
        # For Cosmos, memory is already stored; no-op or could implement aggregation
        return None

    async def get_thread_memory(self, thread_id: str) -> List[Message]:
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query=(
                        "SELECT TOP 1 * FROM c WHERE c.thread_id = @tid ORDER BY c.timestamp DESC"
                    ),
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            return [self._doc_to_message(d) for d in docs]
        except Exception as e:
            raise DatabaseQueryError("Failed to get thread memory from Cosmos", cause=e)

    async def delete_thread(self, thread_id: str) -> None:
        try:
            # Delete messages
            docs = list(
                self.chat_history.query_items(
                    query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                self.chat_history.delete_item(item=d["id"], partition_key=thread_id)

            # Delete memory
            docs = list(
                self.chat_history_summary.query_items(
                    query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                self.chat_history_summary.delete_item(
                    item=d["id"], partition_key=thread_id
                )

            # Delete steps, elements, feedbacks
            for container in (self.steps, self.elements, self.feedbacks):
                docs = list(
                    container.query_items(
                        query="SELECT c.id FROM c WHERE c.threadId = @tid",
                        parameters=[{"name": "@tid", "value": thread_id}],
                        enable_cross_partition_query=True,
                    )
                )
                for d in docs:
                    container.delete_item(item=d["id"], partition_key=thread_id)

            # Delete thread metadata
            try:
                self.threads.delete_item(item=thread_id, partition_key=thread_id)
            except Exception:
                # If the item id differs, try to look it up by id
                tdocs = list(
                    self.threads.query_items(
                        query="SELECT c.id FROM c WHERE c.id = @tid",
                        parameters=[{"name": "@tid", "value": thread_id}],
                        enable_cross_partition_query=True,
                    )
                )
                for td in tdocs:
                    try:
                        self.threads.delete_item(item=td["id"], partition_key=thread_id)
                    except Exception:
                        pass

            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to delete thread in Cosmos", cause=e)

    async def delete_thread_memory(self, thread_id: str) -> None:
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                self.chat_history_summary.delete_item(
                    item=d["id"], partition_key=thread_id
                )
            return None
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to delete thread memory in Cosmos", cause=e
            )

    async def delete_user_memory(self, user_id: str) -> None:
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query="SELECT c.id, c.thread_id FROM c WHERE c.user_id = @uid",
                    parameters=[{"name": "@uid", "value": user_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                # For user memory, partition is thread-based
                thread_pk = d.get("thread_id")
                if thread_pk is None:
                    continue
                self.chat_history_summary.delete_item(
                    item=d["id"], partition_key=thread_pk
                )
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to delete user memory in Cosmos", cause=e)

    async def add_step(self, step_dict: IChatHistoryRepository.StepDict) -> str:
        try:
            if "id" not in step_dict or not step_dict["id"]:
                step_dict["id"] = str(uuid.uuid4())
            # Store as-is (JSON) with threadId partition
            body = {k: v for k, v in step_dict.items() if v is not None}
            self.steps.upsert_item(body)
            return str(step_dict["id"])
        except Exception as e:
            raise DatabaseQueryError("Failed to add step in Cosmos", cause=e)
