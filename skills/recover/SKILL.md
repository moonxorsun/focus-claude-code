---
name: recover
version: "2.0.0"
description: Recover context from previous sessions. Use when Claude's session restore fails or when resuming work after interruption.
user-invocable: true
allowed-tools:
  - Read
  - Bash
  - AskUserQuestion
  - Skill
---

## Environment

| Variable | Default |
|----------|---------|
| `CLAUDE_FOCUS_DIR` | `.claude/tmp/focus` |

Use `$CLAUDE_FOCUS_DIR` in paths. If unset, use the default `.claude/tmp/focus`.

# Context Recovery

Recover context from previous sessions when Claude's automatic session restore fails or is incomplete.

## CRITICAL: Follow Script Output Exactly

This skill uses a **script-driven flow**. You MUST:
1. Run the script
2. Read the `[REQUIRED]` directive in the output
3. Execute exactly what the directive says (usually AskUserQuestion)
4. Based on user's choice, run the next script or skill

**DO NOT** improvise, skip steps, or ask different questions than specified.

## Flow

### Step 1: Run Recovery Script

```bash
python "{{FOCUS_PLUGIN_ROOT}}/scripts/recover_context.py"
```

### Step 2: Follow the [REQUIRED] Directive

The script output ends with a `[REQUIRED]` block. Execute it exactly.

#### Scenario A: focus_context.md EXISTS

Script outputs dual-source recovery + directive to ask:
- **Continue task** → Start working from Current Phase
- **Complete session** → Run `/focus:done`
- **Restart** → Delete context, run `/focus:start`
- **Cancel** → Do nothing, end skill

#### Scenario B: focus_context.md NOT EXISTS

Script outputs session list + directive to ask:
- **Recover history** → Proceed to Step 3
- **Start new** → Run `/focus:start`
- **Cancel** → Do nothing, end skill

### Step 3: (If user chose "Recover history")

Follow the `[REQUIRED] Step 2` directive from script output exactly.

The script provides pre-formatted options (max 4):
- Sessions 1-3 (or 1-4 if total ≤ 4)
- "More..." option if > 4 sessions (user enters number in "Other")

**DO NOT filter or modify the options** - the script handles smart filtering:
- `startup`/`clear` sessions: current session excluded
- `resume`/`compact` sessions: current session included

After user selects, run:
```bash
python "{{FOCUS_PLUGIN_ROOT}}/scripts/recover_context.py" --recover <N>
```

After recovery, inform user they can run `/focus:start` to create a new focus session.

## Implementation Notes

- Session JSONL files: `~/.claude/projects/{project-path}/`
- Default budget: 50,000 characters
- Configuration: `.claude/config/focus.json`
