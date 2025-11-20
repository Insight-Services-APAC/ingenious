# ADR-002: Three Database Backend Strategy

## Status

**Accepted**

**Date:** 2025-11-20

## Context

Ingenious needs to support diverse deployment scenarios:

1. **Local Development**: Quick setup, minimal dependencies, no cloud resources
2. **Azure Production**: Fully managed, scalable, integrated with Azure services
3. **NoSQL Requirements**: Some use cases benefit from document storage and global distribution

Different database requirements:
- **Development**: SQLite for zero-config local development
- **Relational Production**: Azure SQL for structured data with ACID guarantees
- **Document Storage**: Cosmos DB for flexible schemas and global distribution

Common operations needed across all backends:
- Store and retrieve chat history
- Query conversations by user, session, or date
- Support filtering and pagination
- Handle concurrent access safely

Single-backend approaches have limitations:
- **SQLite-only**: Not production-ready for multi-instance deployments
- **Cloud-only**: High barrier to entry, requires cloud account for development
- **NoSQL-only**: Poor fit for relational data, query limitations

## Decision

Support **three database backends** with a unified repository interface:

1. **SQLite** - Local development and single-instance deployments
2. **Azure SQL** - Production relational database with Azure integration
3. **Cosmos DB** - NoSQL document database for flexible schemas

Architecture:
- Common `IChatHistoryRepository` interface defining all operations
- `BaseSQLRepository` shared base class for SQLite and Azure SQL
- Backend-specific implementations in separate modules
- `RepositoryFactory` for creating appropriate backend based on configuration
- Query builders (`QueryBuilder`, `SQLiteDialect`, `AzureSQLDialect`) for SQL generation
- Connection pooling for efficient resource management

```python
# Configuration-based selection
repository = RepositoryFactory.create_chat_history_repository(
    db_type=config.chat_history.database_type,
    config=config
)
```

Directory structure:
```
ingenious/db/
├── chat_history_repository.py  # IChatHistoryRepository interface
├── base_sql.py                 # BaseSQLRepository for SQL backends
├── repository_factory.py       # Factory for creating repositories
├── connection_pool.py          # Connection pooling
├── sqlite/                     # SQLite implementation
├── azuresql/                   # Azure SQL implementation
├── cosmos/                     # Cosmos DB implementation
└── query_builder/              # SQL dialect abstraction
```

## Consequences

### Positive

- **Low barrier to entry**: SQLite enables 5-minute local setup
- **Production-ready**: Azure SQL provides enterprise-grade database
- **Flexibility**: Cosmos DB for use cases needing document storage
- **Gradual adoption**: Start with SQLite, migrate to Azure SQL when ready
- **Environment parity**: Same API works across all backends
- **Cloud agnostic potential**: Pattern could extend to other cloud providers
- **Testability**: SQLite enables fast integration tests without cloud resources
- **Cost efficiency**: No cloud costs during development

### Negative

- **Maintenance burden**: Three implementations to maintain and test
- **Feature parity challenges**: Some features may not work identically across backends
- **Testing complexity**: Must test against all three backends
- **Code duplication**: Some logic duplicated across implementations
- **Cognitive overhead**: Developers must understand differences between backends
- **Migration complexity**: Moving data between backends requires custom tooling
- **Query dialect differences**: SQL differences require dialect abstraction layer
- **Cosmos DB cost**: Can be expensive for high-throughput scenarios

## Alternatives Considered

### Alternative 1: SQLite Only

**Description:** Use only SQLite for all deployments with SQLite extensions for concurrency.

**Rejected because:**
- Not suitable for multi-instance production deployments
- Limited concurrent write performance
- File-based storage complicates container deployments
- No built-in replication or high availability
- Lacks enterprise features (audit logs, advanced security)

### Alternative 2: Azure SQL Only

**Description:** Require Azure SQL for all deployments including local development.

**Rejected because:**
- High barrier to entry - requires Azure account and resources
- Costs money even for local development
- Network dependency makes offline development impossible
- Slower startup and iteration during development
- Overkill for simple use cases and demos

### Alternative 3: ORM with Multi-Backend (SQLAlchemy)

**Description:** Use SQLAlchemy ORM to abstract database differences.

**Rejected because:**
- Adds heavy dependency (~50+ packages)
- Learning curve for developers
- ORM abstractions can hide performance issues
- Doesn't help with Cosmos DB (NoSQL)
- Over-engineering for simple CRUD operations
- Migrations add complexity for library (vs application)

### Alternative 4: Cosmos DB Only

**Description:** Use Cosmos DB for all deployments with local emulator.

**Rejected because:**
- Cosmos emulator has platform limitations (Windows/Linux only)
- Emulator requires Docker on macOS
- NoSQL model is overkill for simple relational data
- Costs can be high in production
- SQL developers face steeper learning curve
- Less familiar to most developers

### Alternative 5: PostgreSQL as Third Option

**Description:** Support PostgreSQL instead of Azure SQL for open-source alternative.

**Rejected because:**
- Would need four backends (SQLite, PostgreSQL, Azure SQL, Cosmos DB)
- Azure SQL is highly compatible with PostgreSQL syntax
- Focus on Azure ecosystem for production deployments
- Could be added later if demand exists

## When to Use Each Backend

### Use SQLite when:
- Local development and testing
- Single-instance deployments
- Demos and proof-of-concepts
- Low traffic applications (<100 concurrent users)
- Embedded scenarios

### Use Azure SQL when:
- Production deployments on Azure
- Multi-instance applications requiring shared state
- Applications needing ACID transactions
- Complex relational queries
- Integration with other Azure services
- Applications requiring high availability

### Use Cosmos DB when:
- Global distribution required
- Variable schema or rapid schema evolution
- Document-oriented data model fits naturally
- Need for multi-region writes
- Applications with spiky, unpredictable traffic
- Integration with Azure Cosmos DB ecosystem

## Migration Path

Recommended progression:

1. **Start**: SQLite for local development
2. **Testing**: SQLite for CI/CD integration tests
3. **Staging**: Azure SQL for staging environment
4. **Production**: Azure SQL or Cosmos DB based on requirements
5. **Scale**: Consider Cosmos DB if global distribution needed

## Related Decisions

- [ADR-004: Optional Dependency Groups](004-dependency-groups.md) - Database group dependencies
- [ADR-007: FastAPI Dependency Injection](007-dependency-injection.md) - Repository injection

## Implementation Details

### Configuration

```bash
# SQLite
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=sqlite
INGENIOUS_CHAT_HISTORY__DATABASE_PATH=./.tmp/chat_history.db

# Azure SQL
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=azuresql
INGENIOUS_CHAT_HISTORY__CONNECTION_STRING="Server=..."

# Cosmos DB
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=cosmos
INGENIOUS_CHAT_HISTORY__ENDPOINT="https://..."
INGENIOUS_CHAT_HISTORY__KEY="..."
```

### Repository Interface

All implementations must provide:
- `create_conversation()` - Start new conversation
- `add_message()` - Add message to conversation
- `get_conversation()` - Retrieve conversation by ID
- `list_conversations()` - List with filtering and pagination
- `delete_conversation()` - Remove conversation
- Connection lifecycle management

## References

- [SQLite When To Use](https://www.sqlite.org/whentouse.html)
- [Azure SQL Database Documentation](https://learn.microsoft.com/en-us/azure/azure-sql/)
- [Azure Cosmos DB Documentation](https://learn.microsoft.com/en-us/azure/cosmos-db/)
- Code: `ingenious/db/repository_factory.py`
- Code: `ingenious/db/base_sql.py`
