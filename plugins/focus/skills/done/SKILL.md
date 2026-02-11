---
name: done
version: "1.2.0"
description: Complete a focus session - archive findings, commit changes, cleanup session files
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

# Focus Session Completion Workflow

Execute this workflow when user invokes `/focus:done`.

## Step 1: Run Focus Done Script

```bash
python "{{FOCUS_PLUGIN_ROOT}}/scripts/focus_done.py"
```

The script will:
1. **Checkpoint**: Process all unprocessed sessions (errors → pending_issues.md, omissions → detected)
2. **Extract**: Parse focus_context.md — table items (fast path) and `##` sections (fallback)
3. **Archive Suggestions**: Group table items by Category, or list section summaries with suggested categories
4. **Pending Issues**: Group by tool/pattern for analysis
5. **Output [REQUIRED]**: Instructions for you to follow

## Step 2: Archive Findings

Follow the `[REQUIRED]` instructions from script output.

### Archive Flow

For each archive batch:
1. Call AskUserQuestion with options: Accept / Edit destinations / Skip
2. If accepted, write items to target file (see Archive Format in Reference)
3. If target is directory, scan for best matching file
4. If file doesn't exist and `auto_create_missing_files: false`, ask user

### Section-based Archive (Fallback)

When the script outputs **section summaries** instead of table batches (because focus_context.md uses free-form content rather than standard tables), follow this flow:

1. Read focus_context.md to get the full content of each listed section
2. For each section, judge whether the content is worth archiving
3. Use the `suggested categories` from script output to map to archive targets in config
4. If no category is suggested or you're unsure about the destination, call AskUserQuestion to confirm with the user
5. Write content in a format appropriate for the target document (tables, headings, lists, etc.)

#### Bug Fixes (Special Handling)

For each bug fix found in the session, evaluate:

| Criteria | Question |
|----------|----------|
| **Easily triggered?** | Could this happen again in normal development? |
| **Hard to diagnose?** | Did it take 2+ attempts to find root cause? |
| **Non-obvious fix?** | Would another developer struggle with this? |

If ANY criteria is YES → Archive using bugs/troubleshooting format (see Archive Format below)

### Pending Issues Flow

1. Review grouped analysis from script output
2. Call AskUserQuestion: Archive patterns / Discard all / Review individually
3. If archive: write to troubleshooting target
4. Delete pending_issues.md after processing

## Step 3: Commit Changes

1. Run `git status` to check for changes
2. If changes exist, call AskUserQuestion: Commit now / Skip commit
3. If commit:
   - Stage relevant files (code changes + archived docs)
   - Create commit with descriptive message
   - Run `git status` to verify

## Step 4: Cleanup Session

1. Call AskUserQuestion to confirm cleanup
2. If confirmed, delete:
   - `.claude/tmp/focus/focus_context.md`
   - `.claude/tmp/focus/operations.jsonl`
   - `.claude/tmp/focus/action_count.json`
   - `.claude/tmp/focus/pending_issues.md`
   - `.claude/tmp/focus/current_session_id.txt`
   - `.claude/tmp/focus/current_session_source.txt`
   - `.claude/tmp/focus/focus_plugin_root.txt`
   - `.claude/tmp/focus/confirm_state.json`

## Step 5: Report

Summarize to user what was accomplished in this session.

---

# Reference

## Category Reference

**Table batches** — the script output shows archive targets directly:
```
[Batch 1] architecture (2 items)
  Target: docs/dev_notes.md [exists]
```
Use the `Target:` path shown in script output. Do not read config files.

**Section-based archive** — when script outputs section summaries, use suggested categories to map to archive targets:

| Category | Default Target |
|----------|---------------|
| architecture | `docs/design.md` |
| bugs | `docs/changelog.md` |
| resolved_bugs | `docs/changelog.md` |
| troubleshooting | `docs/dev_notes.md` |
| conventions | `docs/development.md` |
| decisions | `docs/design.md` |
| external_knowledge | `docs/dev_notes.md` |
| techniques | `docs/development.md` |
| config | `docs/development.md` |
| ai_norms | `.claude/CLAUDE.md` |

Actual targets are configured in `.claude/config/focus.json` (see Configuration below). If unsure, call AskUserQuestion.

## Archive Format

**For architecture.md:**
```markdown
### [Pattern/Component Name]
[Description of the pattern or finding]
```

**For bugs/troubleshooting:**
```markdown
| Symptom | Root Cause | Fix | Prevention |
|---------|------------|-----|------------|
| [Error] | [Why] | [How to fix] | [How to avoid] |
```

**For CLAUDE.md:**
```markdown
### [Rule Name]
[Description of the AI collaboration rule]
```

## Configuration

Archive settings in `.claude/config/focus.json`:

```json
{
  "done": {
    "archive": {
      "auto_create_missing_files": false,
      "batch_size": 5,
      "targets": {
        "architecture": "docs/dev_notes.md",
        "bugs": "docs/changelog.md",
        "resolved_bugs": "docs/changelog.md",
        "troubleshooting": "docs/dev_notes.md",
        "ai_norms": ".claude/CLAUDE.md",
        "conventions": "docs/dev_notes.md"
      }
    }
  }
}
```
