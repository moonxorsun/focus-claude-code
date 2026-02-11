# Focus Plugin Design

This document explains the design philosophy and architecture of the Focus plugin.

---

## Background & Origin

### The Manus Acquisition

In December 2025, Meta acquired Manus AI for $2 billion. Manus achieved $100M+ revenue in just 8 months. Their competitive advantage: **Context Engineering**.

### The Problem with AI Agents

AI coding assistants like Claude Code suffer from:

| Problem | Description |
|---------|-------------|
| **Volatile Memory** | TodoWrite tool data disappears on context reset |
| **Goal Drift** | After 50+ tool calls, original goals get forgotten ("lost in the middle" effect) |
| **Hidden Errors** | Failures aren't tracked, leading to repeated mistakes |
| **Context Stuffing** | Everything crammed into context instead of stored to files |

### The Solution: Planning with Files

> "Markdown is my 'working memory' on disk. Context window = RAM (volatile, limited). Filesystem = Disk (persistent, unlimited)."
> — Manus AI

---

## Core Philosophy

### The 6 Manus Principles

See [context_engineering_notes.md](references/context_engineering_notes.md) for the original Manus principles:

1. Design Around KV-Cache
2. Mask, Don't Remove
3. Filesystem as External Memory
4. Manipulate Attention Through Recitation
5. Keep the Wrong Stuff In
6. Don't Get Few-Shotted

### Behavioral Rules (R1-R7)

Defined in `start/SKILL.md`, enforced by hook short reminders (`[focus] R{n}: ...`).

| Rule | Description | Implementation |
|------|-------------|----------------|
| R1 | Confirm before modifying code | `handle_confirm_before_modify()` + Haiku API, hook: `[focus] R1: Confirm before modifying {file}` |
| R2 | Record information promptly | `increment_and_check_counter()` weight-based reminder, full/simplified versions |
| R3 | Don't repeat failures (3-Strike) | `check_and_update_strikes()` failure detection, hook: `[focus] R3: Strike {n}/{max}` |
| R4 | Update context after modifications | PostToolUse `remind_update()`, hook: `[focus] R4: Update context \| Phases: X/Y` |
| R5 | Verify commits within Plan scope | `check_commit_in_plan()`, hook: `[focus] R5: Commit "{msg}" within Plan scope?` |
| R6 | Read files when reminded by hooks | `check_and_trigger_reminders()` + `confirm_reminder_read()`, pending/read-confirm mechanism |
| R7 | Fix constraint warnings immediately | `constraints.py` output prefixed with `[WARN] R7:` / `[REMIND] R7:` |

### Additional Mechanisms

| Mechanism | Status | Implementation |
|-----------|--------|----------------|
| Session Detection | Implemented | SessionStart hook auto-detects unfinished session |
| Attention Recitation | Implemented (default off) | PreToolUse `recite_objectives()`, `recite_enabled` config |
| SKILL Review Reminder | Implemented | `increment_and_check_skill_review()`, independent `skill_review_state.json`, pending/read-confirm |
| Session Recovery | Implemented | `/focus:recover` restores context from transcripts |
| Section-Based Archive | Implemented | `extract_sections()` fallback when no standard tables in focus_context.md |
| systemMessage Dual-Channel | Implemented | `additionalContext` (AI-visible) + `systemMessage` (user terminal) |

---

## Architecture Overview

### Information Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CONTEXT                                        │
│                          (volatile, limited)                                │
└──────────────┬────^───────────────────────────────^───────┬─────────────────┘
               │    │                               │       │
               │    │ [Hook Recite]                 │       │ [Hook Recording]
               │    │                               │       ▼
               │    │                               │  ┌────────────────────┐
               │    │             [comamand:recover]│  │ operations.jsonl   │
 [Info Persist]│    │                               │  │ (tool_use_id index)│
               ▼    │                               │  └─────────┬──────────┘
┌───────────────────┴───────┐                       │            │
│     focus_context.md      │───────────────────────┤            │ [Lookup]
│    (during session)       │                       │            ▼
│  ┌──────┬────────┬──────┐ │                       │  ┌────────────────────┐
│  │ Plan │Findings│Issues│ │                       │  │ Session Transcript │
│  └──────┴────────┴──────┘ │                       └──┤ (Claude Code JSONL)│
└─────┬─────────────────────┘                          └─────────┬──────────┘
      │                 ^                  [comamand:checkpoint] │
      │                 │                                        │
      │                 └────────────────────────────────────────┤
      │ [comamand:done]                           [auto-extract] │
      │                                                          ▼
      │                                          ┌────────────────────────────┐
      │                                          │    pending_issues.md       │
      │                                          │    (error collection)      │
      │                                          └─────────────┬──────────────┘
      │                                        [comamand:done] │
      ▼                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PROJECT DOCS (permanent)                         │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┬───────────┐  │
│  │ dev_notes.md │ changelog.md │ features.md  │development.md│ design.md │  │
│  └──────────────┴──────────────┴──────────────┴──────────────┴───────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Data Flow Summary:**

| Flow | Trigger | Strategy | Description |
|------|---------|----------|-------------|
| Context → focus_context.md | Info Persistence Reminder | Weight ≥ 5 (Read=1, Web=2, User=2) | AI records findings/issues/decisions |
| focus_context.md → Context | Hook Recite | Every 3 searches (`recite_threshold`) | Attention Recitation: inject Plan/Phase to prevent goal drift |
| Context → operations.jsonl | Hook Recording | Every tool use | Record tool_use_id for session tracking |
| operations.jsonl → Transcript | Lookup | On recover/checkpoint | Find transcript files by session_id |
| focus_context.md + Transcript → Context | /focus:recover | Manual command | Restore context directly to AI |
| Transcript → focus_context.md | /focus:checkpoint | Manual command, Haiku optional | Omission detection, AI updates focus_context.md |
| Transcript → pending_issues.md | auto-extract | On checkpoint | Automatically extract errors (no AI involved) |
| focus_context.md → PROJECT DOCS | /focus:done | Manual command | Archive findings/issues/decisions to permanent docs |
| pending_issues.md → PROJECT DOCS | /focus:done | Manual command | Archive collected errors to permanent docs |

> **Note:** See [token-costs.md](token-costs.md) for detailed token costs, API costs, and configuration options.

### Hook System

```
+------------------------------------------------------------+
|                    focus_hook.py                           |
|                  (unified hook handler)                    |
+------------------------------------------------------------+
| PreToolUse:                                                |
|   --hook pre --tool Read/Glob/Grep  -> recite + count      |
|   --hook pre --tool WebSearch/Fetch -> recite + count      |
|   --hook pre --tool Write/Edit      -> constraints + confirm|
|   --hook pre --tool Bash            -> constraints + recite |
| PostToolUse:                                               |
|   --hook post --tool Read           -> confirm_reminder     |
|                                     -> confirm_skill_review |
|   --hook post --tool Read/Glob/Grep -> info_persistence    |
|                                     -> skill_review_check  |
|   --hook post --tool WebSearch/Fetch-> info_persistence    |
|                                     -> skill_review_check  |
|   --hook post --tool Write/Edit/Bash-> remind_update       |
|   --hook post --tool Bash           -> commit_check        |
|   (all tools)                       -> check_strikes       |
| Other:                                                     |
|   --hook stop                       -> record_operation    |
|   --hook user                       -> reset_confirm_state |
|                                     -> file_reminders (R6) |
|   --hook session-start              -> check_session_start |
+------------------------------------------------------------+
         |
         v (constraints module)
+------------------------------------------------------------+
|                    constraints.py                          |
|              (optional code quality checks)                |
+------------------------------------------------------------+
| Edit/Write:                                                |
|   check_line_limit      -> block if > threshold lines      |
|   check_no_tabs         -> block tab characters            |
|   check_no_hardcoded_path -> warn on hardcoded paths       |
|   check_snake_case_naming -> block non-snake_case (Write)  |
| Bash:                                                      |
|   check_no_backslash_path -> warn on backslash paths       |
|   check_no_powershell     -> block PowerShell commands     |
|   check_no_bash_file_ops  -> warn on cat/grep/find         |
| Integration:                                               |
|   fix_protocol          -> remind Fix Protocol (code files)|
+------------------------------------------------------------+
```

**Hook Coverage:**

| Hook Type | Tools Covered |
|-----------|---------------|
| PreToolUse | Read, Glob, Grep, WebSearch, WebFetch, Write, Edit, Bash |
| PostToolUse | Read, Glob, Grep, WebSearch, WebFetch, Write, Edit, Bash |
| Stop | (global) |
| UserPromptSubmit | (global) |
| SessionStart | (global) |

**Stop Hook Limitation:**

Per Claude Code official docs, Stop hook stdout is **NOT visible to AI** - only visible to users in Verbose mode (Ctrl+O).

**Workaround implemented:** Phase completion check is included in `remind_update()` (PostToolUse), so AI sees `[focus] Update context | Phases: X/Y` after every modification. The Stop hook `check_phases_complete()` is redundant but kept for user visibility.

### File Structure

```
focus/
├── README.md                 # Quick start guide
├── scripts/                  # All Python scripts
│   ├── config.json           # Default configuration
│   ├── focus_core.py         # Shared utilities
│   ├── log_utils.py          # Logging utilities
│   ├── constraints.py        # Code quality constraint checks
│   ├── focus_hook.py         # Unified hook handler
│   ├── recover_context.py    # Context recovery
│   ├── extract_session_info.py
│   └── checkpoint_session.py
├── skills/
│   ├── start/SKILL.md
│   ├── done/SKILL.md
│   ├── recover/SKILL.md
│   └── checkpoint/SKILL.md
├── hooks/
│   └── hooks.json            # Hook definitions
└── docs/
    ├── design.md             # This file
    ├── features.md           # Feature specifications
    ├── development.md        # Implementation details
    ├── dev_notes.md          # Development notes
    └── changelog.md          # Version history
```

### Recovery Architecture

| Aspect | Detail |
|--------|--------|
| Dual mode (context exists) | Includes all sessions from operations.jsonl, including current session |
| List mode (no context) | Uses `get_filtered_sessions()` with smart filtering (excludes current for startup/clear, keeps for resume) |

---

## See Also

- [features.md](features.md) - Detailed feature specifications
- [development.md](development.md) - Implementation details
- [context_engineering_notes.md](references/context_engineering_notes.md) - Context Engineering study notes
