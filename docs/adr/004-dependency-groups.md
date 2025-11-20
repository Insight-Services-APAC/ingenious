# ADR-004: Optional Dependency Groups

## Status

**Accepted**

**Date:** 2025-11-20

## Context

Ingenious is an enterprise-grade library with many features, but different users have different needs:

- **API developers** need just FastAPI and basic dependencies
- **AI developers** need LLM integration (autogen, openai, tiktoken)
- **Azure users** need Azure SDK packages (cosmos, search, blob storage)
- **Document processors** need PDF parsing libraries
- **ML practitioners** need embeddings and vector search

Problem: All-or-nothing installation approaches have issues:

1. **All dependencies**: ~200+ packages, slow install, conflicts, security surface
2. **Minimal only**: Missing features, hard-to-debug import errors
3. **Manual installation**: Users must know which packages to add

Requirements:
- Fast installation for basic use cases
- Clear feature-to-dependency mapping
- Ability to install only what's needed
- Combine multiple feature sets easily
- Standard Python packaging practices

## Decision

Use **optional dependency groups** in `pyproject.toml` following PEP 621:

### Core Groups (Building Blocks)

```toml
[project.optional-dependencies]
# Minimal core - 7 packages for basic functionality
core = ["aiosqlite", "fastapi-cli", "jinja2", "jsonpickle", "markdown", "pandas"]

# Authentication - 3 packages
auth = ["bcrypt", "passlib", "python-jose[cryptography]"]

# Azure cloud - 6 packages  
azure = ["azure-core", "azure-cosmos", "azure-identity", "azure-keyvault-secrets", 
         "azure-search-documents", "azure-storage-blob"]

# AI and agents - 4 packages
ai = ["ats", "autogen-agentchat", "autogen-ext", "openai", "tiktoken"]

# Database connectivity - 2 packages
database = ["pyodbc", "psutil"]

# Knowledge base - 1 package
knowledge-base = ["chromadb"]

# Document processing - 2 packages
document-processing = ["pymupdf", "azure-ai-documentintelligence"]

# ... more groups ...
```

### Combined Groups (Common Use Cases)

```toml
# Standard production setup - ~86 packages
standard = ["ingenious[core,auth,ai,database]"]

# Azure full integration - ~120 packages
azure-full = ["ingenious[standard,azure,knowledge-base,document-processing]"]

# Everything including ML - ~200+ packages
full = ["ingenious[azure-full,document-advanced,chunk,ml,dataprep,visualization]"]
```

### Installation Commands

```bash
# Just the API server (33 packages)
uv add "ingenious"

# Standard production (86 packages)
uv add "ingenious[standard]"

# Full Azure (120 packages)
uv add "ingenious[azure-full]"

# Everything (200+ packages)
uv add "ingenious[full]"

# Custom combination
uv add "ingenious[core,auth,ai]"
```

## Consequences

### Positive

- **Fast minimal install**: 33 packages vs 200+ for full install
- **Clear feature boundaries**: Obvious which group enables which features
- **Flexible combinations**: Users compose exact feature set needed
- **Standard approach**: Uses Python ecosystem conventions (PEP 621)
- **Good documentation**: Groups self-document feature dependencies
- **Security benefits**: Smaller attack surface with fewer dependencies
- **Faster CI/CD**: Can install minimal dependencies for tests
- **Cost efficiency**: Match dependencies to deployment needs

### Negative

- **Complexity**: Users must understand which groups they need
- **Documentation burden**: Must document group-to-feature mapping
- **Testing matrix**: Must test different combinations
- **Import errors at runtime**: Missing dependencies not caught at install time
- **Version conflicts**: More possible conflict scenarios
- **Support complexity**: Must debug "works with X but not Y" issues

## Group Design Principles

1. **Single purpose**: Each group enables one clear feature area
2. **Minimal overlap**: Avoid duplicating dependencies across groups
3. **Composable**: Groups can be combined without conflicts
4. **Progressive**: Start minimal, add groups as needed
5. **Named clearly**: Group name indicates what it enables
6. **Documented well**: README shows which workflows need which groups

## Usage Patterns

### New Users (Getting Started)
```bash
# Start with standard for good default experience
uv add "ingenious[standard]"
```

### Production Deployments
```bash
# Azure deployment with full features
uv add "ingenious[azure-full]"
```

### Development
```bash
# Everything for local development
uv add "ingenious[full]"
```

### CI/CD
```bash
# Minimal for unit tests
uv add "ingenious"

# Standard for integration tests  
uv add "ingenious[standard]"
```

### Custom Applications
```bash
# AI workflows without Azure
uv add "ingenious[core,auth,ai,knowledge-base]"

# Azure without AI (just data storage)
uv add "ingenious[core,azure,database]"
```

## Alternatives Considered

### Alternative 1: All Dependencies Required

**Description:** Include all dependencies in main `dependencies` list.

```toml
dependencies = [
    "fastapi", "autogen", "azure-cosmos", "chromadb", 
    "pymupdf", "sentence-transformers", ... # 200+ packages
]
```

**Rejected because:**
- 5-10 minute install time
- High chance of version conflicts
- Large security surface area
- Wastes disk space and bandwidth
- Overkill for simple use cases

### Alternative 2: Separate Packages

**Description:** Split into multiple PyPI packages:
- `ingenious-core`
- `ingenious-ai`
- `ingenious-azure`

**Rejected because:**
- Maintenance burden (multiple releases, versions)
- User confusion about which to install
- Cross-package version compatibility issues
- More complex CI/CD pipeline
- Harder to ensure feature compatibility

### Alternative 3: Install-Time Configuration

**Description:** Ask users questions during install:

```bash
pip install ingenious
> Do you want AI features? [y/n]
> Do you want Azure integration? [y/n]
```

**Rejected because:**
- Not standard in Python ecosystem
- Breaks automated deployments
- Complicates Docker builds
- Can't declaratively specify in requirements.txt

### Alternative 4: Auto-Detection at Runtime

**Description:** Detect available packages at runtime and enable features:

```python
try:
    import autogen
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
```

**Rejected because:**
- Silent failures confuse users
- No clear "what should I install?" documentation
- Hard to debug "why doesn't this work?"
- Still need guidance on what to install

### Alternative 5: Conda Environment Files

**Description:** Provide conda environment.yml files for different use cases:

```yaml
# environment-standard.yml
dependencies:
  - fastapi
  - autogen
  ...
```

**Rejected because:**
- Not all users use conda
- Still need pip support
- Duplicates dependency information
- Harder to maintain multiple files

## Migration Path

For users upgrading from all-inclusive versions:

```bash
# Old way (if it existed)
pip install ingenious  # Got everything

# New way - choose your level
uv add "ingenious[standard]"  # Good default
uv add "ingenious[azure-full]"  # Azure users
uv add "ingenious[full]"  # Match old behavior
```

## Documentation Requirements

Must document:
1. **In README**: Quick decision tree for which groups to install
2. **In docs**: Detailed table of group-to-feature mapping
3. **In workflow docs**: Which groups each workflow requires
4. **In error messages**: Suggest which group to install for missing dependencies

Example error message:
```python
raise ImportError(
    "ChromaDB not installed. Install with: uv add 'ingenious[knowledge-base]'"
)
```

## Group-to-Feature Mapping

| Group | Features Enabled | Example Use Case |
|-------|-----------------|------------------|
| *(none)* | Basic API server, CLI | API development without AI |
| `core` | Core services, SQLite, templates | Standard app development |
| `auth` | JWT authentication, user management | Secure APIs |
| `ai` | Multi-agent workflows, LLM integration | AI chatbots |
| `azure` | Azure services integration | Production on Azure |
| `database` | SQL Server connectivity | Enterprise databases |
| `knowledge-base` | Vector search, RAG | Document Q&A systems |
| `document-processing` | PDF parsing | Document analysis |
| `standard` | All common production features | Recommended starting point |
| `azure-full` | Complete Azure integration | Full Azure deployment |
| `full` | Every feature | Development, exploration |

## Related Decisions

- [ADR-001: Dynamic Import Pattern](001-dynamic-imports.md) - Handles missing optional dependencies
- [ADR-002: Three Database Backend Strategy](002-database-backends.md) - Database groups
- [ADR-005: Conversation Flow Plugin Architecture](005-conversation-flow-plugins.md) - AI group dependencies

## References

- [PEP 621 - Storing project metadata in pyproject.toml](https://peps.python.org/pep-0621/)
- [Python Packaging User Guide - Optional Dependencies](https://packaging.python.org/en/latest/specifications/core-metadata/#provides-extra-multiple-use)
- [uv Documentation](https://docs.astral.sh/uv/)
- Code: `pyproject.toml` lines 69-177
