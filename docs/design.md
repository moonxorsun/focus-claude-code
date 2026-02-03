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

### Implementation Status

**Completion Rate**: 8/13 = **62%** (excluding concept-only: 8/11 = **73%**)

#### Critical Rules (6)

| # | Rule | Status | Implementation |
|---|------|--------|----------------|
| 1 | Create Plan First | Implemented | SessionStart hook auto-detects unfinished session |
| 2 | Information Persistence | Implemented | `increment_and_check_counter()` weight-based reminder |
| 3 | Confirm Before Modify | Implemented | `handle_confirm_before_modify()` + Haiku API |
| 4 | Update After Act | Implemented | PostToolUse `remind_update()` reminder |
| 5 | Log ALL Errors | Implemented | operations.jsonl records all tool_use_id, checkpoint/done extracts errors from transcript |
| 6 | Never Repeat Failures | Implemented | 3-Strike forces alternative approach on 2nd failure |

#### Supplementary Rules (7)

| # | Rule | Status | Implementation |
|---|------|--------|----------------|
| 7 | 3-Strike Error Protocol | Implemented | `check_and_update_strikes()` failure detection |
| 8 | 5-Question Reboot Test | Concept | Theoretical validation method |
| 9 | Read vs Write Decision Matrix | Concept | Decision guide |
| 10 | Attention Recitation | Implemented | PreToolUse `recite_objectives()` |
| 11 | Session Catchup | Implemented | `/focus:recover` restores session context |
| 12 | Phase Completion Check | Implemented | Stop hook `check_phases_complete()` |
| 13 | Bug Archival Assessment | Partial | done skill provides guidance |

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
|   --hook pre --tool Write/Edit      -> confirm_before_modify|
|   --hook pre --tool Bash            -> recite              |
| PostToolUse:                                               |
|   --hook post --tool Read/Glob/Grep -> info_persistence    |
|   --hook post --tool WebSearch/Fetch-> info_persistence    |
|   --hook post --tool Write/Edit/Bash-> remind_update       |
|   (all tools)                       -> check_strikes       |
| Other:                                                     |
|   --hook stop                       -> check_phases_complete|
|   --hook user                       -> reset_confirm_state |
|   --hook session-start              -> check_session_start |
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

---

## See Also

- [features.md](features.md) - Detailed feature specifications
- [development.md](development.md) - Implementation details
- [context_engineering_notes.md](references/context_engineering_notes.md) - Context Engineering study notes
