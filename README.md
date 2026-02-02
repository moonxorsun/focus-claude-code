# Focus Plugin

A single-file planning system for complex tasks, based on Manus Context Engineering principles.

## Overview

Focus uses `focus_context.md` as persistent "working memory on disk" to prevent goal drift and information loss during long AI sessions.

### Core Principles (from Manus)

1. **Filesystem as Memory** - Context window is volatile; files are persistent
2. **Attention Recitation** - Re-read plan before each decision to prevent goal drift
3. **Keep Wrong Stuff In** - Record errors in Issues table for learning
4. **Plan is Required** - Always know: goal, current phase, remaining phases

### Information Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        CONTEXT                              │
│                    (volatile, limited)                      │
└─────────────────────────┬───────────────────────────────────┘
                          │ [Information Persistence Reminder]
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   focus_context.md                          │
│              (persistent during focus)                      │
│  ┌─────────────┬──────────────┬───────────────────────┐    │
│  │   Plan      │   Findings   │   Issues              │    │
│  │  - [ ] ...  │  | Key | Val │  | Error | Resolution │    │
│  └─────────────┴──────────────┴───────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │ [/focus:done archival]
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 PROJECT DOCUMENTATION                       │
│                    (permanent)                              │
│  ┌──────────────────┬────────────────┬─────────────────┐   │
│  │ architecture.md  │ troubleshoot.md│ decisions.md    │   │
│  └──────────────────┴────────────────┴─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

| Command | Description |
|---------|-------------|
| `/focus:start` | Start a new focus session |
| `/focus:checkpoint` | Save progress mid-session |
| `/focus:done` | Complete session and archive |
| `/focus:recover` | Recover context from previous sessions |

**Typical workflow:**
1. `/focus:start` - Create planning document
2. Work on your task (hooks remind you to update the plan)
3. `/focus:done` - Complete and archive

---

## Installation

### Requirements

- Python 3.8+

### From Local Directory

**Step 1: Add local directory as marketplace**
```bash
/plugins marketplace add .claude/plugins
```

**Step 2: Install the plugin**
```bash
/plugins install focus
```

Installation scopes:
- `--user`: Global (across all projects)
- `--project`: Project-shared (synced with team)
- `--local`: Local to current project only

### Verify Installation

```bash
/plugins list
```

You should see `focus` in the list.

---

## Post-Installation

### 1. Restart Claude Code

**Important:** After first installation, restart Claude Code (exit and re-enter) to activate hooks properly.

### 2. No Parallel Sessions

> **⚠️ Warning:** This plugin does NOT support multiple Claude Code sessions using the same project directory simultaneously.
>
> When starting a new session, if you see "Unfinished focus session detected", check the "Last activity" time:
> - **Long ago** (hours/days): Safe to recover with `/focus:recover`
> - **Just now** (seconds/minutes): Another session may be active - wait or check

### 3. Recommended Permissions

To avoid manual approval prompts, add to `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python *focus-claude-code*)"
    ]
  }
}
```

### 4. Gitignore Configuration

Ensure `.claude/tmp/` is in your `.gitignore`:

```gitignore
# Claude Code temp files
.claude/tmp/
```

---

## Configuration

Focus uses a three-layer configuration system:

| Layer | Path | Purpose |
|-------|------|---------|
| Default | `scripts/config.json` (inside plugin) | Built-in defaults (read-only) |
| Project | `.claude/config/focus.json` | Project-level overrides (git tracked) |
| Local | `.claude/config/focus.local.json` | Personal overrides (gitignore) |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_FOCUS_DIR` | `.claude/tmp/focus` | Root directory for session files (relative to project root) |

### Example: Disable Confirm Before Modify

Create `.claude/config/focus.json`:
```json
{
    "start": {
        "confirm_before_modify": {
            "enabled": false
        }
    }
}
```

### Optional AI Features

Two features require the `anthropic` package (disabled by default):

| Feature | Config | Description |
|---------|--------|-------------|
| **Confirm Before Modify** | `start.confirm_before_modify.use_haiku` | Verify user confirmed modifications |
| **Omission Detection** | `checkpoint.use_haiku` | Detect unrecorded Issues/Decisions |

To enable:
```bash
pip install anthropic
export ANTHROPIC_API_KEY="your-api-key"
# Then set use_haiku: true in config
```

---

## Template Structure

```markdown
# Focus Context

## Task
[Brief description]

## Plan
- [ ] Phase 1: ...
- [ ] Phase 2: ...

## Current Phase
Phase 1: [description]
- Working on: ...
- Blocked: (none)

## Findings
| Category | Discovery | Details |
|----------|-----------|---------|

## Issues
| Category | Issue | Cause | Resolution |
|----------|-------|-------|------------|

## Decisions
| Category | Decision | Rationale |
|----------|----------|-----------|
```

---

## Session Files

Focus uses temporary files in `$CLAUDE_FOCUS_DIR/` (default: `.claude/tmp/focus/`):

| File | Purpose |
|------|---------|
| `focus_context.md` | Main planning document |
| `operations.jsonl` | Operation history for recovery |
| `action_count.json` | Information Persistence counter |
| `pending_issues.md` | Auto-collected errors |
| `logs/` | Debug and error logs |

---

## Implementation Details

### File Structure

```
focus/
├── README.md                 # This file
├── scripts/                  # All Python scripts
│   ├── __init__.py           # Python package
│   ├── config.json           # Unified configuration
│   ├── focus_core.py         # Shared utilities (config, paths, helpers)
│   ├── log_utils.py          # Logging utilities
│   ├── focus_hook.py         # Unified hook handler
│   ├── recover_context.py    # Context recovery
│   └── extract_session_info.py # Session summary extraction
├── skills/
│   ├── start/
│   │   └── SKILL.md          # Main skill definition + template
│   ├── done/
│   │   └── SKILL.md          # Completion workflow
│   └── recover/
│       └── SKILL.md          # Context recovery
├── commands/
│   └── ...
└── docs/
    ├── design_guide.md
    └── references/
        └── context_engineering_notes.md
```

### Skill-Level Hooks (Auto-configured)

These hooks are defined in `skills/start/SKILL.md` and activate automatically when using `/focus:start`:

| Hook | Trigger | Action |
|------|---------|--------|
| `PreToolUse` | Write, Edit | `handle_confirm_before_modify()` - check user confirmation via Haiku API |
| `PreToolUse` | Read, Glob, Grep, WebSearch, etc. | `recite_objectives()` - inject plan summary |
| `PreToolUse` | Search tools | Information Persistence Reminder (weight-based) |
| `PostToolUse` | Write, Edit | Remind to update focus_context.md |
| `PostToolUse` | All tools | 3-Strike Error Protocol check |
| `Stop` | Session end | Check phase completion status |
| `UserPromptSubmit` | New user message | Reset confirmation state |

### Key Functions in focus_hook.py

| Function | Purpose |
|----------|---------|
| `recite_objectives()` | Extract and display Task/Plan/Current Phase summary |
| `extract_summary()` | Parse focus_context.md for summary sections |
| `increment_and_check_counter()` | Track tool usage, trigger Information Persistence Reminder |
| `check_and_update_strikes()` | 3-Strike Error Protocol - track failures and warn |
| `handle_confirm_before_modify()` | Check user confirmation before Write/Edit via Haiku API |
| `check_user_confirmation()` | Call Haiku API to verify user approved modification |
| `check_phases_complete()` | Verify all phases marked `[x]` on session end |
| `record_operation()` | Log operation IDs to operations.jsonl |

---

## See Also

- [design_guide.md](docs/design_guide.md) - Design philosophy and implementation details
- [context_engineering_notes.md](docs/references/context_engineering_notes.md) - Context Engineering study notes (based on Manus article)
