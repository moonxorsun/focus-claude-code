---
name: checkpoint
version: "2.0.0"
description: Save progress mid-session - archive findings, truncate logs, continue working
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - AskUserQuestion
---

## Environment

| Variable | Default |
|----------|---------|
| `CLAUDE_FOCUS_DIR` | `.claude/tmp/focus` |

Use `$CLAUDE_FOCUS_DIR` in paths. If unset, use the default `.claude/tmp/focus`.

# Checkpoint Workflow

Execute this workflow when user invokes `/focus:checkpoint`.

## Step 1: Choose Processing Mode

Ask user which mode to use:

| Mode | Description |
|------|-------------|
| **Silent** | Process all old sessions automatically |
| **Interactive** | Process only the oldest session, then pause |
| **Oldest** | Alias for Interactive |

## Step 2: Run Checkpoint Script

```bash
python "{{FOCUS_PLUGIN_ROOT}}/scripts/checkpoint_session.py" --mode=<mode> [--dry-run]
```

Options:
- `--mode=silent` - Process all old sessions
- `--mode=interactive` - Process only oldest session
- `--mode=oldest` - Same as interactive
- `--dry-run` - Show what would be done without modifying files

### What the script does:

1. **Processes sessions from old to new** (skips current session)
2. **Error detection** → writes to `pending_issues.md`
3. **Omission detection** → calls Haiku API to find unrecorded Issues/Decisions/Findings
4. **Removes processed session records** from operations.jsonl

## Step 3: Handle Omission Detection Results

The script outputs omission detection results like:

```
### Session abc12345...
[Issue] Some bug that wasn't recorded
[Decision] A decision that was made but not documented
[Finding] An insight that was discovered
```

For each item:
1. **[Issue]** → Add to `focus_context.md` Issues table
2. **[Decision]** → Add to `focus_context.md` Decisions table
3. **[Finding]** → Add to `focus_context.md` Findings table
4. **NONE** or **ERROR** → No action needed

## Step 4: Review Pending Issues

If `pending_issues.md` has items:

1. Read `.claude/tmp/focus/pending_issues.md`
2. For each issue, decide:
   - **Archive**: If it reveals a pattern → use `/focus:done` when session completes
   - **Discard**: If it's a user rejection or transient error

Format in pending_issues.md:
```markdown
### 2026-02-02T10:00:00 | Bash | error
- **Session**: abc12345
- **Command**: `some_command`
- **Error**: error message

### 2026-02-02T11:00:00 | Read | error
- **Session**: def67890
- **File**: /path/to/file.py
- **Error**: The user doesn't want to proceed...
```

## Step 5: Archive Valuable Information (Optional)

For items in Findings/Issues/Decisions tables worth persisting:

| Category | Destination |
|----------|-------------|
| Architecture | Use `/focus:done` for archival |
| Bug (unresolved) | Use `/focus:done` for archival |
| Bug (resolved) | Use `/focus:done` for archival |
| Troubleshooting | Use `/focus:done` for archival |
| AI Norm | `.claude/CLAUDE.md` |

After archiving, remove the item from focus_context.md tables.

## Step 6: Optional Git Commit

Ask user if they want to commit:

```bash
git add <archived-docs>
git commit -m "checkpoint(focus): archive findings"
```

## Step 7: Report and Continue

Summarize:
- Sessions processed
- Errors recorded to pending_issues.md
- Omissions added to focus_context.md
- Items archived to project docs

**Do NOT delete focus_context.md** - the session continues.

## Configuration

In `.claude/config/focus.json`:

```json
"checkpoint": {
    "error_detection": true,
    "omission_detection": true,
    "use_haiku": true,
    "haiku_max_tokens": 500,
    "omission_char_budget": 10000
}
```

| Option | Description |
|--------|-------------|
| `error_detection` | Enable/disable error detection |
| `omission_detection` | Enable/disable omission detection |
| `use_haiku` | If false, outputs session text for AI to analyze |
| `haiku_max_tokens` | Max tokens for Haiku response |
| `omission_char_budget` | Max chars to extract for omission analysis |
