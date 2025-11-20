# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the Ingenious project. ADRs document significant architectural decisions made during the development of the project, including the context, rationale, and consequences of each decision.

## What are ADRs?

Architecture Decision Records are lightweight documents that capture important architectural decisions along with their context and consequences. They help:

- **New contributors** understand why the codebase is structured the way it is
- **Future maintainers** know if designs can be safely changed
- **Team members** understand the tradeoffs made in past decisions
- **Everyone** avoid repeating past discussions and mistakes

## ADR Format

Each ADR follows a consistent format documented in [template.md](template.md):

- **Status**: Current state (Proposed, Accepted, Deprecated, Superseded)
- **Context**: The problem and constraints
- **Decision**: What was decided
- **Consequences**: Positive and negative outcomes
- **Alternatives Considered**: Other options and why they were rejected
- **References**: Supporting materials

## Index of ADRs

### Core Architecture

- [ADR-001: Dynamic Import Pattern](001-dynamic-imports.md)
  - String-based imports with namespace fallback for plugin architecture
  
- [ADR-005: Conversation Flow Plugin Architecture](005-conversation-flow-plugins.md)
  - Pluggable conversation flows with namespace discovery

### Infrastructure & Deployment

- [ADR-002: Three Database Backend Strategy](002-database-backends.md)
  - SQLite, Azure SQL, and Cosmos DB support for different environments

- [ADR-004: Optional Dependency Groups](004-dependency-groups.md)
  - Modular installation options for different use cases

### Framework Integration

- [ADR-003: Middleware Ordering](003-middleware-ordering.md)
  - RequestContext → CORS → Auth middleware stack

- [ADR-006: ConfigWrapper Service Injection](006-config-wrapper.md)
  - Proxy pattern for injecting configuration alongside services

- [ADR-007: FastAPI Dependency Injection](007-dependency-injection.md)
  - Native FastAPI DI patterns for service management

### Error Handling

- [ADR-008: Error Hierarchy Design](008-error-hierarchy.md)
  - Structured error system with categories, severity, and context

## Creating New ADRs

When making a significant architectural decision:

1. Copy `template.md` to create a new ADR with the next available number
2. Fill in all sections with clear, concise information
3. Get review from team members
4. Update this README to include the new ADR in the index
5. Reference the ADR in relevant code comments or documentation

## ADR Lifecycle

- **Proposed**: Under discussion, not yet accepted
- **Accepted**: Decision has been made and is active
- **Deprecated**: Decision is no longer recommended but may still exist in codebase
- **Superseded**: Replaced by a newer ADR (note which one)

## Further Reading

- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) by Michael Nygard
- [ADR GitHub Organization](https://adr.github.io/)
- [ADR Tools](https://github.com/npryce/adr-tools)
