# Feature Branch Setup

Create a new feature branch with proper tracking and initial structure.

## Arguments

`$ARGUMENTS` - Required: Feature name or issue reference (e.g., "user-auth", "AB#1234", "#42")

## Process

### 1. Parse Input

Determine branch type from input:
- `AB#XXXX` or `#XXXX` → Azure DevOps work item
- `GH#XX` or just `#XX` → GitHub issue
- Plain text → Feature name

### 2. Fetch Issue Details (if applicable)

**For Azure DevOps:**
```bash
az boards work-item show --id XXXX --query "{title:fields.\"System.Title\", type:fields.\"System.WorkItemType\", description:fields.\"System.Description\"}"
```

**For GitHub:**
```bash
gh issue view XX --json title,body,labels
```

### 3. Generate Branch Name

Create branch name following convention:
- `feature/` - New functionality
- `bugfix/` - Bug fixes
- `hotfix/` - Urgent production fixes
- `refactor/` - Code improvements

Format: `{type}/{issue-id}-{short-description}`
Example: `feature/AB1234-user-authentication`

### 4. Create Branch

```bash
# Ensure main is up to date
git checkout main
git pull origin main

# Create and checkout new branch
git checkout -b {branch-name}

# Push and set upstream
git push -u origin {branch-name}
```

### 5. Link to Work Item (if applicable)

**For Azure DevOps:**
```bash
# Add branch link to work item
az boards work-item relation add --id XXXX --relation-type "ArtifactLink" --target-url "vstfs:///Git/Ref/..."
```

**For GitHub:**
- Branch name containing issue number auto-links

### 6. Generate Initial TODO List

Based on issue details, create a TODO list using TodoWrite:
- Break down the feature into implementation steps
- Include standard items: implementation, tests, documentation update

### 7. Output Summary

```
## Feature Branch Created

Branch: feature/AB1234-user-authentication
Tracking: origin/feature/AB1234-user-authentication
Based on: main (commit abc1234)

### Linked Work Item
Title: Implement user authentication
Type: User Story
Status: Active

### Initial TODOs
- [ ] Review existing auth code
- [ ] Implement authentication logic
- [ ] Add unit tests
- [ ] Update API documentation
- [ ] Create PR

Ready to start coding!
```

## Notes

- Always branch from latest main
- If branch already exists, offer to check it out instead
- Validate branch name doesn't contain invalid characters
- If no issue provided, ask for a brief description to generate branch name
