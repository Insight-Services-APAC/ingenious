# Document Chunking

Splitting documents into context-aware chunks for RAG pipelines.

## Overview

Document chunking is essential for effective Retrieval-Augmented Generation (RAG) workflows.

## Features

- Intelligent chunk boundaries
- Configurable chunk sizes
- Overlap management
- Metadata preservation

## Usage

```python
from ingenious.chunk import DocumentChunker

chunker = DocumentChunker()
chunks = chunker.chunk_document(document)
```

For more details, see the [Development Guide](../development.md).
