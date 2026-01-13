# Docker Setup

Create or improve Dockerfile and .dockerignore for this project, then build and test locally.

## When to Use

- When containerizing a new project
- To improve existing Docker configuration
- For optimizing build performance

## Arguments

Usage: `/docker-setup [target-dir] [--runtime python|node|go]`

- `target-dir` - Directory to create Docker files in (default: current directory)
- `--runtime` - Primary runtime (default: auto-detect)

If `$ARGUMENTS` is provided, use it as target directory or runtime.

## Steps

### 1. Analyze Project Structure

Detect project type and requirements:

```bash
# Check for existing Docker files
ls Dockerfile .dockerignore docker-compose.yml 2>/dev/null

# Detect project type
ls pyproject.toml requirements.txt setup.py 2>/dev/null  # Python
ls package.json 2>/dev/null                               # Node.js
ls go.mod 2>/dev/null                                     # Go
```

### 2. Create or Update Dockerfile

**Python (uv):**
```dockerfile
FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Set environment
ENV PATH="/app/.venv/bin:$PATH"

# Run application
CMD ["python", "-m", "your_app"]
```

**Python (FastAPI):**
```dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Node.js:**
```dockerfile
FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build --if-present

CMD ["node", "dist/index.js"]
```

### 3. Create .dockerignore

Include common patterns:

```
# Version control
.git
.gitignore

# Dependencies
node_modules/
.venv/
venv/
__pycache__/

# Build artifacts
dist/
build/
*.egg-info/
.coverage
htmlcov/

# IDE and editors
.vscode/
.idea/
*.swp

# Environment files
.env
.env.*
!.env.example

# Docker files
Dockerfile*
docker-compose*

# Test artifacts
.pytest_cache/
.mypy_cache/

# Documentation
*.md
docs/

# Temporary files
*.log
*.tmp
.tmp/
```

### 4. Ensure Docker is Running

```bash
# macOS with colima
colima start 2>/dev/null || true

# Verify Docker
docker info >/dev/null 2>&1 && echo "Docker is running"
```

### 5. Build Docker Image

```bash
docker build -t <project-name>:dev .
```

### 6. Test the Image

```bash
# Run the container
docker run -it --rm -p 8000:8000 <project-name>:dev

# Verify it responds
curl http://localhost:8000/health
```

### 7. Debug and Iterate

If issues are found:
1. Check logs in container
2. Update Dockerfile
3. Rebuild and retest

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Build fails | Missing dependencies | Check COPY statements, ensure files exist |
| Image too large | Dev dependencies | Use multi-stage build, slim base |
| Port not accessible | Port not exposed | Add EXPOSE and -p flag |
| Permission errors | File ownership | Use non-root user in Dockerfile |

## Success Criteria

- Dockerfile created with best practices
- .dockerignore excludes unnecessary files
- Image builds successfully
- Container runs and responds correctly
- Image size is reasonable
