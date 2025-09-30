# Prompt: Generate, Commit, and Push with Git

## Instructions

1. **Security Check: Scan for secrets**
    - **CRITICAL**: Before committing, scan all staged files for potential secrets:
      - API keys, tokens, passwords
      - Private keys, certificates
      - Connection strings, database credentials
      - AWS/Azure/GCP credentials
      - Environment files (.env, .env.local, etc.)
      - Configuration files with sensitive data
    - Use `git diff --cached` to review staged changes
    - Check for patterns like:
      - `API_KEY=`, `PASSWORD=`, `SECRET=`, `TOKEN=`
      - Private key headers (BEGIN RSA PRIVATE KEY, etc.)
      - Base64-encoded strings that might be credentials
    - **If secrets are found**: Remove them immediately, use environment variables or secret management instead
    - **NEVER commit or push files containing secrets**

2. **Assess the scope of changes**
    - If there are extensive changes, break them into logical groups
    - Each commit should represent a cohesive set of related changes
    - Consider grouping by: feature, bug fix, refactoring, documentation, tests

3. **Write a concise and descriptive git commit message**
    - Summarize the changes made.
    - Use the imperative mood (e.g., "Add feature", "Fix bug", "Update docs").
    - Keep the first line under 72 characters.
    - **NEVER include emojis in commit messages**
    - **Maintain a concise, professional tone**
    - **DO NOT add attribution footers** (e.g., no "Generated with Claude Code" or "Co-Authored-By: Claude")

4. **Commit your changes**
    - For small changes:
      ```sh
      git add .
      git commit -m "<your commit message>"
      ```
    - For extensive changes, commit incrementally:
      ```sh
      git add <specific files or directories>
      git commit -m "<specific commit message>"
      # Repeat for each logical group
      ```

5. **Push your commits to the remote repository**
    ```sh
    git push
    ```

## Examples

### Single Commit (Small Changes)
1. **Commit message:**
    ```
    Add user authentication to login endpoint
    ```

2. **Commands:**
    ```sh
    git add .
    git commit -m "Add user authentication to login endpoint"
    git push
    ```

### Multiple Commits (Extensive Changes)
1. **Incremental commits:**
    ```sh
    # Commit core functionality first
    git add src/auth/
    git commit -m "Add authentication service and middleware"

    # Commit tests separately
    git add tests/auth/
    git commit -m "Add authentication tests"

    # Commit documentation
    git add docs/auth.md
    git commit -m "Add authentication documentation"

    # Push all commits
    git push
    ```
