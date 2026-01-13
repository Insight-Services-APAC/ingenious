# Remove Unnecessary Files

Identify and remove cruft files that shouldn't be in the repository.

**Important**: This command only reports files that are NOT already in .gitignore. Properly ignored files are excluded from results.

## Process

### 1. Scan for Cruft Files (Excluding Gitignored)

For each search, filter out gitignored files using:
```bash
find ... | while read f; do git check-ignore -q "$f" || echo "$f"; done
```

**AI-Generated Reports:**
```bash
find . -type f \( \
  -name "VALIDATION_REPORT*.md" \
  -o -name "ANALYSIS_REPORT*.md" \
  -o -name "QUALITY_REPORT*.md" \
  -o -name "REVIEW_REPORT*.md" \
  -o -name "DEBT_REPORT*.md" \
  -o -name "COVERAGE_REPORT*.md" \
  -o -name "*_REPORT.md" \
  -o -name "report*.md" \
  -o -name "claude_*.md" \
  -o -name "ai_*.md" \
\) -not -path "./.git/*" -not -path "./tmp/*" -not -path "./.tmp/*" 2>/dev/null \
| while read f; do git check-ignore -q "$f" || echo "$f"; done
```

**Temporary/Development Files:**
```bash
find . -type f \( \
  -name "*.tmp" \
  -o -name "*.temp" \
  -o -name "*.bak" \
  -o -name "*.backup" \
  -o -name "*.orig" \
  -o -name "*.swp" \
  -o -name "*.swo" \
  -o -name "*~" \
  -o -name ".DS_Store" \
  -o -name "Thumbs.db" \
  -o -name "desktop.ini" \
\) -not -path "./.git/*" -not -path "./node_modules/*" -not -path "./.venv/*" 2>/dev/null \
| while read f; do git check-ignore -q "$f" || echo "$f"; done
```

**Log Files Outside tmp:**
```bash
find . -type f \( \
  -name "*.log" \
  -o -name "*.logs" \
  -o -name "debug*.txt" \
  -o -name "error*.txt" \
\) -not -path "./.git/*" -not -path "./tmp/*" -not -path "./.tmp/*" -not -path "./logs/*" -not -path "./node_modules/*" -not -path "./.venv/*" 2>/dev/null \
| while read f; do git check-ignore -q "$f" || echo "$f"; done
```

**Test/Coverage Artifacts Outside tmp:**
```bash
find . \( -type f -o -type d \) \( \
  -name "test_output*.json" \
  -o -name "test_results*.xml" \
  -o -name "coverage*.xml" \
  -o -name "junit*.xml" \
  -o -name ".coverage" \
  -o -name "htmlcov" \
  -o -name ".pytest_cache" \
\) -not -path "./.git/*" -not -path "./tmp/*" -not -path "./.tmp/*" -not -path "./node_modules/*" -not -path "./.venv/*" 2>/dev/null \
| while read f; do git check-ignore -q "$f" || echo "$f"; done
```

**Orphaned Config/Draft Files:**
```bash
find . -type f \( \
  -name "*.draft" \
  -o -name "*.wip" \
  -o -name "scratch*.py" \
  -o -name "scratch*.js" \
  -o -name "scratch*.ts" \
  -o -name "test_scratch*" \
  -o -name "temp_*" \
  -o -name "tmp_*" \
\) -not -path "./.git/*" -not -path "./tmp/*" -not -path "./.tmp/*" -not -path "./node_modules/*" -not -path "./.venv/*" 2>/dev/null \
| while read f; do git check-ignore -q "$f" || echo "$f"; done
```

**Database Files in Unexpected Locations:**
```bash
find . -maxdepth 2 -type f \( \
  -name "*.db" \
  -o -name "*.sqlite" \
  -o -name "*.sqlite3" \
\) -not -path "./.git/*" -not -path "./.tmp/*" -not -path "./tmp/*" 2>/dev/null \
| while read f; do git check-ignore -q "$f" || echo "$f"; done
```

### 2. For Each File Found, Collect Metadata

```bash
# Get file size
ls -lh "$file" | awk '{print $5}'

# Get last modified date
stat -f "%Sm" -t "%Y-%m-%d" "$file"  # macOS
# stat -c "%y" "$file" | cut -d' ' -f1  # Linux

# Check if tracked by git
git ls-files --error-unmatch "$file" 2>/dev/null && echo "tracked" || echo "untracked"
```

### 3. Present Results

Only show files that are:
- NOT in .gitignore
- Either tracked (shouldn't be) or untracked (should be removed or added to .gitignore)

```
## Cruft Scan Results

Found X files not covered by .gitignore:

### Should Remove (untracked cruft)
| File | Size | Last Modified | Action |
|------|------|---------------|--------|
| ./server.log | 16KB | 2024-01-10 | Delete or add to .gitignore |

### Should Not Be Tracked (committed cruft)
| File | Size | Last Modified | Action |
|------|------|---------------|--------|
| ./VALIDATION_REPORT.md | 12KB | 2024-01-08 | git rm and add pattern to .gitignore |

### No cruft found
If no files match, report: "Repository is clean - no cruft files found outside .gitignore"
```

### 4. Interactive Cleanup

Use AskUserQuestion with options:
- "Remove all and update .gitignore" - Delete files and add patterns to prevent recurrence
- "Remove files only" - Delete files without updating .gitignore
- "Update .gitignore only" - Add patterns but keep files (for manual review)
- "Select individually" - Go through each file
- "Skip" - Take no action

### 5. Execute Cleanup

For approved deletions:
```bash
# For untracked files - just delete
rm -rf <file_or_dir>

# For tracked files - remove from git and filesystem
git rm -r <file_or_dir>
```

### 6. Update .gitignore (if selected)

Suggest patterns based on what was found:
```bash
# Append to .gitignore if not already present
grep -q "pattern" .gitignore || echo "pattern" >> .gitignore
```

Common patterns to add:
- `*_REPORT.md` - AI-generated reports
- `*.log` - Log files
- `.coverage` - Coverage data
- `htmlcov/` - Coverage HTML reports
- `.DS_Store` - macOS cruft
- `*.db` - SQLite databases (if not intentional)

### 7. Summary

```
## Cleanup Summary

Deleted: X files/directories (Y MB)
Added to .gitignore: N patterns

Deleted:
- ./server.log (16 KB)
- ./htmlcov/ (17 MB)

Added to .gitignore:
- *.log
- htmlcov/
```

## Safety Rules

- NEVER remove files in src/, lib/, or other code directories without explicit confirmation
- NEVER remove package.json, pyproject.toml, or config files
- NEVER remove README.md, CLAUDE.md, or intentional documentation
- NEVER remove files modified in the last hour (might be work in progress)
- Always show what will be removed BEFORE doing it
- Require explicit confirmation for tracked files (they were committed for a reason)
- When in doubt, suggest adding to .gitignore rather than deleting

## Arguments

- `$ARGUMENTS` - Optional:
  - `dry-run` - Only show what would be removed, don't delete anything
  - `auto` - Remove all untracked cruft without asking (still confirms tracked files)
  - `gitignore-only` - Only suggest .gitignore additions, don't delete
  - Custom pattern to search for (e.g., `*.bak`)
