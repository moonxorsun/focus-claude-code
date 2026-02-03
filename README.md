# Focus Plugin

A single-file planning system for complex tasks, based on Manus Context Engineering principles.

## Overview

Focus uses `focus_context.md` as persistent "working memory on disk" to prevent goal drift and information loss during long AI sessions.

### Core Principles (from Manus)

1. **Filesystem as Memory** - Context window is volatile; files are persistent
2. **Attention Recitation** - Re-read plan before each decision to prevent goal drift
3. **Keep Wrong Stuff In** - Record errors in Issues table for learning
4. **Plan is Required** - Always know: goal, current phase, remaining phases

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

## Features

| Feature | Description | Trigger |
|---------|-------------|---------|
| **Attention Recitation** | Inject Task/Plan/Phase into context | Every N searches (default: 3) |
| **Information Persistence** | Remind to record findings | Weight sum >= 5 |
| **Modification Reminder** | Remind to update focus_context.md | After Write/Edit/Bash |
| **Confirm Before Modify** | Check user confirmation before edits | Before Write/Edit |
| **3-Strike Error Protocol** | Force alternative approach after failures | Consecutive failures |
| **Completion Check** | Verify all phases complete | Session end |
| **Context Recovery** | Restore context from previous sessions | `/focus:recover` |
| **Mid-Session Checkpoint** | Save progress without ending session | `/focus:checkpoint` |

See [features.md](docs/features.md) for detailed specifications.

### Information Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CONTEXT                                        │
│                          (volatile, limited)                                │
└──────────────┬────^───────────────────────────^───────┬─────────────────────┘
               │    │                               │       │
               │    │ [Hook Recite]                 │       │ [Hook Recording]
               │    │                               │       ▼
               │    │                               │  ┌────────────────────┐
               │    │             [command:recover] │  │ operations.jsonl   │
 [Info Persist]│    │                               │  │ (tool_use_id index)│
               ▼    │                               │  └─────────┬──────────┘
┌───────────────────┴───────┐                       │            │
│     focus_context.md      │───────────────────────┤            │ [Lookup]
│    (during session)       │                       │            ▼
│  ┌──────┬────────┬──────┐ │                       │  ┌────────────────────┐
│  │ Plan │Findings│Issues│ │                       │  │ Session Transcript │
│  └──────┴────────┴──────┘ │                       └──┤ (Claude Code JSONL)│
└─────┬─────────────────────┘                          └─────────┬──────────┘
      │                 ^                  [command:checkpoint]  │
      │                 │                                        │
      │                 └────────────────────────────────────────┤
      │ [command:done]                               [auto-extract]
      │                                                          ▼
      │                                          ┌────────────────────────────┐
      │                                          │    pending_issues.md       │
      │                                          │    (error collection)      │
      │                                          └─────────────┬──────────────┘
      │                                        [command:done]  │
      ▼                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PROJECT DOCS (permanent)                         │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┬───────────┐  │
│  │ dev_notes.md │ changelog.md │ features.md  │development.md│ design.md │  │
│  └──────────────┴──────────────┴──────────────┴──────────────┴───────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

For detailed data flow descriptions, see [design.md](docs/design.md).

---

## Installation

### Requirements

- Python 3.8+

### From GitHub (Recommended)

**Step 1: Add GitHub repository as marketplace**
```bash
/plugins marketplace add github:<YOUR_USERNAME>/focus-claude-code
```

**Step 2: Install the plugin**
```bash
/plugins install focus
```

Installation scopes:
- `--user`: Global (across all projects)
- `--project`: Project-shared (synced with team)
- `--local`: Local to current project only

### From Local Directory

If you have cloned the repository locally:

**Step 1: Add local directory as marketplace**
```bash
/plugins marketplace add /path/to/focus-claude-code
```

**Step 2: Install the plugin**
```bash
/plugins install focus
```

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

> **Warning:** This plugin does NOT support multiple Claude Code sessions using the same project directory simultaneously.
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

---

## Token Costs

| Operation | Context Tokens | External API |
|-----------|----------------|--------------|
| Normal session (per hour) | ~500-1000 | None |
| Each Write/Edit (with Haiku) | ~20 | ~50-100 |
| /focus:checkpoint | ~100 | 0-500 (optional) |
| /focus:recover | ~500-2000 | None |

**Note:** Haiku API features are disabled by default. See [token-costs.md](docs/token-costs.md) for tuning strategies.

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

## Documentation

| Document | Description |
|----------|-------------|
| [design.md](docs/design.md) | Design philosophy and architecture |
| [features.md](docs/features.md) | Feature specifications and test cases |
| [development.md](docs/development.md) | Implementation details, hooks, and functions |
| [dev_notes.md](docs/dev_notes.md) | Development findings and decisions |
| [changelog.md](docs/changelog.md) | Version history |
| [context_engineering_notes.md](docs/references/context_engineering_notes.md) | Context Engineering study notes (Manus) |
