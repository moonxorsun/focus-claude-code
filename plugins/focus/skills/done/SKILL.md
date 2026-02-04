---
name: done
version: "1.1.0"
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
2. **Extract**: Parse Findings/Issues/Decisions from focus_context.md
3. **Archive Suggestions**: Group items by Category, match to target files
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

#### Bug Fixes (Special Handling)

For each bug fix in Issues table, evaluate:

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

## Step 5: Report

Summarize to user what was accomplished in this session.

---

# Reference

## Category Reference

The script output shows archive targets directly:
```
[Batch 1] architecture (2 items)
  Target: docs/dev_notes.md [exists]
```

Use the `Target:` path shown in script output. Do not read config files.

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
