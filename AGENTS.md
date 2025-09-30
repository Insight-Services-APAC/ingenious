# Repository Guidelines

## Project Structure & Module Organization
Core library code lives in `ingenious/`, grouped by domain (for example, `ingenious/services/` for runtime services and `ingenious/api/routes/` for HTTP endpoints). Configuration models sit in `ingenious/config/`, while reusable utilities are in `ingenious/utils/`. Unit and integration tests reside under `tests/`, mirroring the package layout (`tests/unit/test_api_routes.py`, `tests/services/...`). Documentation assets and site configuration live in `docs/` and `mkdocs.yml`.

## Build, Test, and Development Commands
- `uv run python -m pytest`: run the full test suite with coverage rules from `pyproject.toml`.
- `uv run ruff check`: lint the codebase using the enforced Ruff ruleset.
- `uv run ruff format`: apply repository formatting standards.
- `uv build`: create a distributable package for release validation.
Use `uv lock` after modifying dependencies to refresh the lockfile.

## Coding Style & Naming Conventions
Python code uses 4-space indentation, type hints where practical, and descriptive snake_case for functions, variables, and filenames (`chat_service.py`, `get_chat_response`). Public classes use PascalCase. Ruff handles linting and formatting; avoid manual stylistic tweaks that conflict with its defaults. Keep modules small and focused—new FastAPI routes belong under `ingenious/api/routes/`, and shared helpers go in `ingenious/utils/`.

## Testing Guidelines
Pytest is the standard framework, with discovery configured for `test_*.py` files inside `tests/`. Coverage must stay above the `--cov-fail-under=20` threshold defined in `pyproject.toml`. Targeted checks (e.g., `uv run python -m pytest tests/unit/test_api_routes.py`) are encouraged before pushing. Write fixtures in `tests/conftest.py` when multiple test modules share setup.

## Commit & Pull Request Guidelines
Commit messages follow conventional prefixes seen in history (`feat:`, `fix:`, `chore:`, `refactor:`) and describe the change succinctly. Group unrelated work into separate commits. Pull requests should include: a clear summary of the change, any relevant issue links, test evidence (`uv run python -m pytest` output), and screenshots or logs when touching user-facing behavior. Keep PRs focused and request review from maintainers owning the affected package paths.

## Configuration Tips
Local development expects at least one model configured via environment variables such as `INGENIOUS_MODELS__0__API_KEY` and `INGENIOUS_MODELS__0__BASE_URL`. Store secrets in `.env` (ignored by Git) and duplicate `.env.example` when setting up a fresh workspace.
