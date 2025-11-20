# Migration Guide

This guide helps you migrate your conversation flows to use the new patterns and avoid deprecated functionality.

## Conversation Flow Pattern Migration (v0.2.8 → v0.3.0)

### Overview

Starting with **v0.2.8**, the multi-agent service supports only the `IConversationFlow` pattern with instance methods and `ChatResponse` objects. The old static method pattern and tuple response format are deprecated and will be removed in **v0.3.0**.

### What's Deprecated?

1. **Static method pattern** - Using static methods with individual arguments
2. **Tuple response format** - Returning `(response_text, memory_summary)` tuples
3. **Individual parameter passing** - Passing `message`, `topics`, `thread_memory`, etc. as separate arguments

### Migration Steps

#### Step 1: Inherit from IConversationFlow

**Before (Deprecated):**
```python
class ConversationFlow:
    @staticmethod
    async def get_conversation_response(
        message: str,
        topics=None,
        thread_memory: str = "",
        memory_record_switch: bool = True,
        thread_chat_history=None,
    ) -> tuple[str, str]:
        # Implementation
        return (response_text, memory_summary)
```

**After (Required in v0.3.0):**
```python
from ingenious.models.chat import ChatRequest, ChatResponse
from ingenious.services.chat_services.multi_agent.service import IConversationFlow

class ConversationFlow(IConversationFlow):
    async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
        # Implementation
        return ChatResponse(
            thread_id=chat_request.thread_id,
            message_id=str(uuid.uuid4()),
            agent_response=response_text,
            token_count=token_count,
            max_token_count=max_token_count,
            memory_summary=memory_summary,
        )
```

#### Step 2: Update Constructor

**Before (Deprecated):**
```python
class ConversationFlow:
    # No __init__ needed for static methods
    pass
```

**After (Required in v0.3.0):**
```python
class ConversationFlow(IConversationFlow):
    def __init__(self, parent_multi_agent_chat_service):
        super().__init__(parent_multi_agent_chat_service)
        # Additional initialization if needed
```

#### Step 3: Access Configuration and Services

**Before (Deprecated):**
```python
import ingenious.config.config as config

class ConversationFlow:
    @staticmethod
    async def get_conversation_response(...):
        _config = config.get_config()
        model_config = _config.models[0]
```

**After (Required in v0.3.0):**
```python
class ConversationFlow(IConversationFlow):
    async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
        # Access configuration through parent service
        model_config = self._config.models[0]
        
        # Access chat history repository
        if self._chat_service:
            thread_messages = await self._chat_service.chat_history_repository.get_thread_messages(
                chat_request.thread_id
            )
```

#### Step 4: Extract Request Parameters

**Before (Deprecated):**
```python
@staticmethod
async def get_conversation_response(
    message: str,
    topics=None,
    thread_memory: str = "",
    memory_record_switch: bool = True,
    thread_chat_history=None,
):
    # Use parameters directly
    user_message = message
    topic_list = topics or []
```

**After (Required in v0.3.0):**
```python
async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
    # Extract from chat_request
    user_message = chat_request.user_prompt
    topic_list = chat_request.topic if isinstance(chat_request.topic, list) else [chat_request.topic]
    thread_memory = chat_request.thread_memory or ""
    memory_record = chat_request.memory_record if hasattr(chat_request, 'memory_record') else True
    thread_chat_history = chat_request.thread_chat_history or []
```

#### Step 5: Return ChatResponse Instead of Tuple

**Before (Deprecated):**
```python
@staticmethod
async def get_conversation_response(...) -> tuple[str, str]:
    # Process and generate response
    result = "Agent response text"
    memory_summary = "Summary for memory"
    
    # Return tuple
    return result, memory_summary
```

**After (Required in v0.3.0):**
```python
async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
    # Process and generate response
    result = "Agent response text"
    memory_summary = "Summary for memory"
    
    # Return ChatResponse object
    return ChatResponse(
        thread_id=chat_request.thread_id,
        message_id=str(uuid.uuid4()),
        agent_response=result,
        token_count=0,  # Update with actual token count if available
        max_token_count=0,  # Update with actual max tokens if available
        memory_summary=memory_summary,
    )
```

### Complete Example

Here's a complete before/after example:

**Before (Deprecated):**
```python
import logging
import uuid
from autogen_agentchat.agents import AssistantAgent
from autogen_core import EVENT_LOGGER_NAME

import ingenious.config.config as config
from ingenious.client.azure import AzureClientFactory

class ConversationFlow:
    @staticmethod
    async def get_conversation_response(
        message: str,
        topics=None,
        thread_memory: str = "",
        memory_record_switch: bool = True,
        thread_chat_history=None,
    ) -> tuple[str, str]:
        _config = config.get_config()
        model_config = _config.models[0]
        
        model_client = AzureClientFactory.create_openai_chat_completion_client(model_config)
        
        agent = AssistantAgent(
            name="assistant",
            system_message="You are a helpful assistant.",
            model_client=model_client,
        )
        
        # Process request
        response = await agent.on_messages(...)
        result = response.chat_message.content
        memory_summary = f"Processed: {message[:50]}..."
        
        await model_client.close()
        return result, memory_summary
```

**After (Required in v0.3.0):**
```python
import logging
import uuid
from autogen_agentchat.agents import AssistantAgent
from autogen_core import EVENT_LOGGER_NAME

from ingenious.client.azure import AzureClientFactory
from ingenious.models.chat import ChatRequest, ChatResponse
from ingenious.services.chat_services.multi_agent.service import IConversationFlow

class ConversationFlow(IConversationFlow):
    async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
        # Access configuration through parent service
        model_config = self._config.models[0]
        
        # Extract parameters from chat_request
        message = chat_request.user_prompt
        thread_memory = chat_request.thread_memory or ""
        
        model_client = AzureClientFactory.create_openai_chat_completion_client(model_config)
        
        agent = AssistantAgent(
            name="assistant",
            system_message="You are a helpful assistant.",
            model_client=model_client,
        )
        
        # Process request
        response = await agent.on_messages(...)
        result = response.chat_message.content
        memory_summary = f"Processed: {message[:50]}..."
        
        await model_client.close()
        
        # Return ChatResponse object
        return ChatResponse(
            thread_id=chat_request.thread_id,
            message_id=str(uuid.uuid4()),
            agent_response=result,
            token_count=0,  # Update with actual token count from LLM usage tracker
            max_token_count=0,  # Update with actual max tokens
            memory_summary=memory_summary,
        )
```

### Benefits of the New Pattern

1. **Better encapsulation** - Access to parent service and configuration through `self`
2. **Type safety** - Single `ChatRequest` parameter with well-defined structure
3. **Extensibility** - Easy to add new features without changing method signatures
4. **Consistency** - All conversation flows use the same pattern
5. **Testability** - Easier to mock and test with dependency injection

### Timeline

- **v0.2.8** (Current): Deprecation warnings added, both patterns work
- **v0.3.0** (Future): Old patterns removed, only `IConversationFlow` supported

### Need Help?

If you encounter issues during migration, please:
1. Check the example conversation flows: `knowledge_base_agent`, `sql_manipulation_agent`
2. Review the `IConversationFlow` abstract base class documentation
3. Open an issue on GitHub with your specific use case

### Reference Implementation

See these conversation flows for complete examples of the new pattern:
- `ingenious/services/chat_services/multi_agent/conversation_flows/knowledge_base_agent/knowledge_base_agent.py`
- `ingenious/services/chat_services/multi_agent/conversation_flows/sql_manipulation_agent/sql_manipulation_agent.py`
