# Custom Templates

Create and modify Jinja2 prompt templates for your agents.

## Overview

Custom templates allow you to define how agents communicate and format their responses.

## Template Structure

```jinja2
You are a {{ role }} specialized in {{ domain }}.

Context: {{ context }}
User Query: {{ user_prompt }}

Please respond with:
- Analysis of the query
- Recommended actions
- Next steps
```

For detailed template development, see the [Extension Development Guide](../development.md#extending-ingenious).
