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

## Step 2: Follow [REQUIRED] Instructions

The script output contains `[REQUIRED]` instructions. Follow them exactly.

### Archive Flow

For each archive batch:
1. Call AskUserQuestion with options: Accept / Edit destinations / Skip
2. If accepted, write items to target file
3. If target is directory, scan for best matching file
4. If file doesn't exist and `auto_create_missing_files: false`, ask user

### Pending Issues Flow

1. Review grouped analysis
2. Call AskUserQuestion: Archive patterns / Discard all / Review individually
3. If archive: write to troubleshooting.md
4. Delete pending_issues.md after processing

### Cleanup Flow

1. Call AskUserQuestion to confirm cleanup
2. If confirmed, delete:
   - `.claude/tmp/focus/focus_context.md`
   - `.claude/tmp/focus/operations.jsonl`
   - `.claude/tmp/focus/action_count.json`
   - `.claude/tmp/focus/pending_issues.md`

## Category Reference

When items have Category field, they map to archive targets:

| Category | Default Target | Description |
|----------|----------------|-------------|
| architecture | docs/development/architecture.md | Patterns, structures |
| bugs | docs/development/known_bugs.md | Unresolved bugs, known issues |
| resolved_bugs | docs/development/resolved_bugs.md | Fixed bugs with cause and solution |
| troubleshooting | docs/development/troubleshooting.md | Debugging processes |
| ai_norms | .claude/CLAUDE.md | AI collaboration rules |
| conventions | docs/development/ | Coding standards |
| external_knowledge | docs/research/ | External references, libraries |
| techniques | docs/development/techniques.md | Implementation techniques |
| decisions | docs/development/decisions.md | Design decisions |
| config | docs/development/build_system.md | Build system settings |

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
        "architecture": "docs/development/architecture.md",
        "bugs": "docs/development/known_bugs.md",
        "resolved_bugs": "docs/development/resolved_bugs.md",
        "troubleshooting": "docs/development/troubleshooting.md",
        "ai_norms": ".claude/CLAUDE.md",
        "conventions": "docs/development/"
      }
    }
  }
}
```
