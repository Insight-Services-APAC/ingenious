# Custom Agents

Learn how to create specialized AI agents for specific tasks in Ingenious.

## Overview

Custom agents allow you to create specialized AI assistants that handle specific domains or workflows.

## Creating a Custom Agent

```python
from ingenious.services.chat_services.multi_agent.conversation_flows.i_conversation_flow import IConversationFlow

class MyCustomAgent(IConversationFlow):
    def get_conversation_response(self, user_prompt: str, **kwargs) -> str:
        # Implement your custom logic here
        return "Custom response"
```

For detailed implementation examples, see the [Extension Development Guide](../development.md#extending-ingenious).
