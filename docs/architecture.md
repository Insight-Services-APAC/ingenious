# Architecture Overview

This document describes the high-level architecture of Insight Ingenious, an enterprise-grade Python library designed for quickly setting up APIs to interact with AI Agents with comprehensive Azure service integrations and debugging capabilities.

## System Architecture

Insight Ingenious is architected as a production-ready library with enterprise-grade features including seamless Azure service integrations, robust debugging tools, and extensive customization capabilities. The system consists of the following main components:

```mermaid
graph TB
    subgraph "Client Layer"
        API_CLIENT[API Clients<br/>External Applications]
        DOCS[API Documentation<br/>Swagger/OpenAPI]
    end

    subgraph "API Gateway"
        API[FastAPI<br/>REST Endpoints]
        AUTH[Authentication<br/>& Authorization]
    end

    subgraph "Core Engine"
        AGENT_SERVICE[Agent Service<br/>Conversation Manager]
        PATTERN_SERVICE[Pattern Service<br/>Conversation Orchestrator]
        LLM_SERVICE[LLM Service<br/>Azure OpenAI Integration]
    end

    subgraph "Extension Layer"
        CUSTOM_AGENTS[Custom Agents<br/>Domain Specialists]
        PATTERNS[Conversation Patterns<br/>Workflow Templates]
        TOOLS[Custom Tools<br/>External Integrations]
    end

    subgraph "Storage Layer"
        CONFIG[Configuration<br/>Environment Variables]
        HISTORY[Chat History<br/>SQLite/Azure SQL]
        FILES[File Storage<br/>Local/Azure Blob]
    end

    subgraph "External Services"
        AZURE[Azure OpenAI<br/>GPT Models]
        EXTERNAL_API[External APIs<br/>Data Sources]
    end

    %% Client connections
    API_CLIENT --> API
    API_CLIENT --> DOCS

    %% API Gateway routing
    API --> AUTH
    AUTH --> AGENT_SERVICE

    %% Core Engine interactions
    AGENT_SERVICE --> PATTERN_SERVICE
    PATTERN_SERVICE --> LLM_SERVICE
    AGENT_SERVICE --> CUSTOM_AGENTS

    %% Extension Layer integrations
    CUSTOM_AGENTS --> PATTERNS
    PATTERNS --> TOOLS

    %% Storage Layer connections
    AGENT_SERVICE --> CONFIG
    AGENT_SERVICE --> HISTORY
    AGENT_SERVICE --> FILES

    %% External Service connections
    LLM_SERVICE --> AZURE
    TOOLS --> EXTERNAL_API

    %% Styling
    classDef clientLayer fill:#e1f5fe
    classDef apiLayer fill:#f3e5f5
    classDef coreLayer fill:#e8f5e8
    classDef extensionLayer fill:#fff3e0
    classDef storageLayer fill:#fce4ec
    classDef externalLayer fill:#f1f8e9

    class API_CLIENT,DOCS clientLayer
    class API,AUTH apiLayer
    class AGENT_SERVICE,PATTERN_SERVICE,LLM_SERVICE coreLayer
    class CUSTOM_AGENTS,PATTERNS,TOOLS extensionLayer
    class CONFIG,HISTORY,FILES storageLayer
    class AZURE,EXTERNAL_API externalLayer
```

## Core Components

### API Layer

**FastAPI Application**
- RESTful API endpoints for chat interactions
- OpenAPI/Swagger documentation
- Request/response validation with Pydantic models
- Error handling and standardized responses

**Authentication & Authorization**
- JWT token-based authentication
- Basic authentication support
- Role-based access control
- Secure credential management

### Core Engine

**Agent Service**
- Conversation management and routing
- Agent lifecycle management
- Context preservation across conversations
- Thread-safe execution

**Pattern Service**
- Conversation pattern orchestration
- Multi-agent coordination
- Workflow execution engine
- State management

**LLM Service**
- Azure OpenAI integration
- Model configuration and management
- Token usage tracking
- Response streaming support

### Extension Layer

**Custom Agents**
- Domain-specific AI agents
- Specialized task handlers
- Configurable behavior patterns
- Integration with external tools

**Conversation Patterns**
- Reusable workflow templates
- Multi-agent coordination patterns
- Sequential and parallel execution modes
- Error handling and retry logic

**Custom Tools**
- External API integrations
- Data source connectors
- Business logic plugins
- Utility functions

### Storage Layer

**Configuration Management**
- Environment-based configuration
- Pydantic settings validation
- Dynamic reconfiguration support
- Secure credential storage

**Chat History**
- Conversation persistence
- Multiple storage backends (SQLite, Azure SQL)
- Query and retrieval capabilities
- Data retention policies

**File Storage**
- Local and Azure Blob storage
- Version control for templates
- Binary file handling
- Secure access management

## Data Flow

### Request Processing Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Auth
    participant AgentService
    participant PatternService
    participant LLM
    participant Storage

    Client->>API: POST /api/v1/chat
    API->>Auth: Validate credentials
    Auth-->>API: Authentication result

    API->>AgentService: Process conversation request
    AgentService->>Storage: Load conversation history
    Storage-->>AgentService: Historical context

    AgentService->>PatternService: Execute conversation pattern
    PatternService->>LLM: Generate AI response
    LLM-->>PatternService: AI-generated content

    PatternService-->>AgentService: Pattern execution result
    AgentService->>Storage: Save conversation state
    AgentService-->>API: Conversation response

    API-->>Client: JSON response
```

### Configuration Loading

```mermaid
graph LR
    ENV[Environment Variables] --> PYDANTIC[Pydantic Settings]
    PYDANTIC --> VALIDATION[Configuration Validation]
    VALIDATION --> SERVICES[Service Initialization]
    SERVICES --> READY[System Ready]

    VALIDATION -->|Validation Error| ERROR[Configuration Error]
    ERROR --> EXIT[System Exit]
```

## Security Architecture

### Authentication Flow

```mermaid
graph TB
    CLIENT[Client Request] --> AUTH_CHECK{Authentication<br/>Required?}
    AUTH_CHECK -->|No| PROCESS[Process Request]
    AUTH_CHECK -->|Yes| VALIDATE{Validate<br/>Credentials}

    VALIDATE -->|Invalid| REJECT[401 Unauthorized]
    VALIDATE -->|Valid| AUTHORIZE{Check<br/>Authorization}

    AUTHORIZE -->|Denied| FORBIDDEN[403 Forbidden]
    AUTHORIZE -->|Allowed| PROCESS

    PROCESS --> RESPONSE[Return Response]
```

### Security Features

- **Credential Management**: Environment-based secrets management
- **Input Validation**: Pydantic model validation for all inputs
- **Rate Limiting**: Request throttling and abuse prevention
- **Audit Logging**: Comprehensive request and response logging
- **Error Handling**: Secure error responses without information leakage

## Scalability Considerations

### Horizontal Scaling

- **Stateless Design**: Request processing without server-side state
- **Database Connection Pooling**: Efficient database resource management
- **Async Processing**: Non-blocking I/O for high throughput
- **Load Balancing**: Multiple instance deployment support

### Performance Optimization

- **Caching**: Response caching and template caching
- **Connection Reuse**: HTTP client connection pooling
- **Lazy Loading**: On-demand resource initialization
- **Memory Management**: Efficient resource cleanup and garbage collection

## Extension Architecture

### Extension Discovery

```mermaid
graph TB
    DISCOVERY[Extension Discovery] --> LOCAL{Local Extensions<br/>Found?}
    LOCAL -->|Yes| LOAD_LOCAL[Load Local Extensions]
    LOCAL -->|No| TEMPLATE{Template Extensions<br/>Found?}

    TEMPLATE -->|Yes| LOAD_TEMPLATE[Load Template Extensions]
    TEMPLATE -->|No| CORE[Load Core Extensions]

    LOAD_LOCAL --> VALIDATE[Validate Extensions]
    LOAD_TEMPLATE --> VALIDATE
    CORE --> VALIDATE

    VALIDATE --> REGISTER[Register Extensions]
    REGISTER --> READY[Extensions Ready]
```

### Extension Interface

All extensions implement standardized interfaces:

- **IConversationFlow**: Conversation workflow interface
- **IAgent**: Agent behavior interface
- **ITool**: Tool integration interface
- **IStorage**: Storage backend interface

## Monitoring and Observability

### Logging Architecture

```mermaid
graph LR
    APP[Application] --> STRUCT_LOG[Structured Logging]
    STRUCT_LOG --> FORMAT[JSON Formatting]
    FORMAT --> OUTPUT[Log Output]

    OUTPUT --> FILE[File Logs]
    OUTPUT --> CONSOLE[Console Logs]
    OUTPUT --> REMOTE[Remote Logging Service]
```

### Metrics and Monitoring

- **Request Metrics**: Response times, error rates, throughput
- **Resource Metrics**: Memory usage, CPU utilization, database connections
- **Business Metrics**: Conversation counts, token usage, agent performance
- **Health Checks**: System health and dependency status

## Deployment Architecture

### Single Instance Deployment

```mermaid
graph TB
    LOAD_BALANCER[Load Balancer] --> APP_INSTANCE[Ingenious Instance]
    APP_INSTANCE --> LOCAL_DB[Local SQLite]
    APP_INSTANCE --> LOCAL_FILES[Local File Storage]
    APP_INSTANCE --> AZURE_OPENAI[Azure OpenAI]
```

### Distributed Deployment

```mermaid
graph TB
    LOAD_BALANCER[Load Balancer] --> APP1[Ingenious Instance 1]
    LOAD_BALANCER --> APP2[Ingenious Instance 2]
    LOAD_BALANCER --> APPN[Ingenious Instance N]

    APP1 --> SHARED_DB[Azure SQL Database]
    APP2 --> SHARED_DB
    APPN --> SHARED_DB

    APP1 --> BLOB_STORAGE[Azure Blob Storage]
    APP2 --> BLOB_STORAGE
    APPN --> BLOB_STORAGE

    APP1 --> AZURE_OPENAI[Azure OpenAI]
    APP2 --> AZURE_OPENAI
    APPN --> AZURE_OPENAI
```

This architecture provides a solid foundation for building scalable, secure, and maintainable AI agent APIs with comprehensive Azure integrations.
