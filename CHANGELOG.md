# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.8] - 2025-11-20

### Deprecated

- **Multi-agent conversation flow patterns**: The following patterns are now deprecated and will be removed in v0.3.0:
  - Static method pattern for conversation flows (using `@staticmethod` with individual parameters)
  - Tuple response format `(response_text, memory_summary)` - use `ChatResponse` objects instead
  - Individual parameter passing (`message`, `topics`, `thread_memory`, etc.) - use `ChatRequest` parameter instead
  
  **Migration Required**: All conversation flows should inherit from `IConversationFlow` and implement instance methods that accept `ChatRequest` and return `ChatResponse` objects. See `docs/MIGRATION.md` for detailed migration instructions.

- **Deprecation warnings added**: When old patterns are detected, `DeprecationWarning` messages will be logged with migration instructions.

### Added

- `docs/MIGRATION.md`: Comprehensive migration guide for updating conversation flows to the new pattern
- Deprecation warnings in `multi_agent_chat_service` when legacy patterns are detected

### Changed

- Enhanced logging in `multi_agent_chat_service` to clearly indicate when deprecated patterns are being used

### Documentation

- Added migration guide with complete before/after examples
- Updated documentation to emphasize `IConversationFlow` as the preferred pattern

## [0.2.7] - Previous Release

(Prior changelog entries would be added here as the project evolves)

---

## Migration Timeline

- **v0.2.8** (Current): Deprecation warnings added. Both old and new patterns work.
- **v0.3.0** (Future - Breaking Change): Old patterns will be removed. Only `IConversationFlow` pattern supported.

## Categories

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** in case of vulnerabilities
