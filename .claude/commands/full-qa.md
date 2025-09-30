# Master Prompt

**Branch:** `to-stable`

---

## General Rules (apply throughout)

- Always use `az cli` to check if resources already exist in the resource group **ingen-test** before provisioning.
  - If the resource exists, retrieve keys/permissions.
  - Only provision the cheapest viable resource in **ingen-test** if missing. Do not use resources from other resource groups. Only use **ingen-test**.

- Always check that docs align with your actual setup experience.
  - Update only if incomplete, inaccurate, or missing.

- **You are allowed to debug Ingenious library code if blocked.**

- Commit Ingenious code changes incrementally in small, focused commits.

- Never commit `test_dir/` or `ingenious_extensions`.
  - Make sure to create `ingenious_extensions` in `test_dir/` and not as part of the Ingenious codebase.

- You are allowed to change database/resource credentials to achieve your goals.

---

## Sequential Steps

### Step 0 — Bootstrap
1. Create `test_dir/` and `cd test_dir/`.
2. Follow `README.md` fully to bring up the environment. **BUT install Ingenious from source (this codebase) instead of PyPI.**
3. Use `az` with resource group **ingen-test**.
4. Before provisioning anything, check if resources exist and retrieve access. Provision only if missing.
5. Do not commit `test_dir/`.

---

### Step 1 — Local Docs
- Verify that `README.md` and `docs/` match the local setup experience.
- Update with gotchas, fixes, and debug steps from `test_dir/` if needed.
- Keep examples terse and copy/pasteable.

---

### Step 2 — Authentication (Basic + JWT)
- Ensure Basic Auth and JWT Auth both work locally.
- Add minimal code changes and concise configuration examples if needed.
- Validate with `curl`.
- Update `docs/auth.md` or `README.md` only if missing or inaccurate.

---

### Step 3 — Azure SQL + Blob Integration
- Within `test_dir/`, add and test:
  1. Azure SQL for chat history persistence
  2. Azure Blob for prompt storage

- Use `az cli` to check or provision.
- Validate the bike-insights workflow with SQL + Blob enabled via `curl`.
- Update `docs/guides/complete-azure-deployment.md` if needed.

**Note:** You are allowed to change database/resource credentials to achieve your goals.
_Do not use special characters in the UID or password for the DB._

---

### Step 4 — Cosmos DB Integration
- Validate Cosmos DB integration within `test_dir/`.
- Use `az cli` to check or provision Cosmos DB.
- Retrieve keys/permissions if it exists.
- Verify workflows with Cosmos DB using `curl`.
- Update `docs/guides/cosmos-db-deployment.md` if needed.

---

### Step 5 — Knowledge-Base Agent with Azure AI Search
- Validate that the knowledge-base-agent works with Azure AI Search.
- Use `az cli` to check or provision Azure AI Search.
- Retrieve keys/permissions if it exists.
- Verify with queries against the agent.
- Update `docs/guides/azure-ai-search-deployment.md` if needed.

---

### Step 6 — Transition Local → Azure Docs
- Check if `docs/guides/complete-azure-deployment.md` explains moving from local to Azure SQL + Blob.
- If not, add/update with:
  - Env var table
  - `az cli` one-liners (with check-before-provision guidance)
  - Minimal provisioning instructions
  - `curl` verification snippets

---

### Step 7 — Custom Workflow (with Auth)
- Create a custom workflow in Ingenious.
- Validate end-to-end execution with Basic + JWT Auth.
- Update `docs/guides/custom-workflows.md` if needed.
- Include config/code examples and `curl` commands.

---

### Step 8 — Full API + Prompt Testing
- Systematically test all `prompts/` (i.e., routes containing `prompt/` or `prompts/` as part of the route) API endpoints.
- For each `prompts/` endpoint, run a `curl` command.

---

## Constraints
- Never commit `test_dir/` or `ingenious_extensions`.
- Only use resources from **ingen-test**.

---

## Terminator
**DO NOT STOP UNTIL THIS FULL TASK IS COMPLETED.**

---

## Keyword
**ULTRATHINK**
