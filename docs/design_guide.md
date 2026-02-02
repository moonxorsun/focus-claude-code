# Focus Plugin Design Guide

This document serves as the comprehensive reference for the Focus plugin's design philosophy, architecture, and implementation details.

---

## Table of Contents

1. [Background & Origin](#background--origin)
2. [Core Philosophy](#core-philosophy)
3. [Architecture Overview](#architecture-overview)
4. [Feature Specifications](#feature-specifications)
5. [Implementation Details](#implementation-details)
6. [Future Roadmap](#future-roadmap)

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

### Evolution in This Project

| Version | Approach | Files |
|---------|----------|-------|
| Planning-with-Files (external) | 3-file pattern | `task_plan.md`, `findings.md`, `progress.md` |
| Focus Plugin (this project) | Single-file pattern | `$CLAUDE_FOCUS_DIR/focus_context.md` |

**Migration reason:** 3-file pattern requires 3 tool calls to read; single file is more efficient.

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

### Theory vs Practice Gap

Current implementation status: **62% (8/13)** of rules have code enforcement.

#### Critical Rules (6)

| # | Rule | Status | Implementation |
|---|------|--------|----------------|
| 1 | Create Plan First | ✅ Implemented | SessionStart hook in `hooks/hooks.json` auto-detects unfinished session |
| 2 | Information Persistence | ✅ Implemented | `increment_and_check_counter()` weight-based reminder |
| 3 | Confirm Before Modify | ✅ Implemented | `handle_confirm_before_modify()` + Haiku API confirmation |
| 4 | Update After Act | ✅ Implemented | PostToolUse `remind_update()` reminder |
| 5 | Log ALL Errors | ⚠️ Partial | Extracted from transcript on done, requires manual archival |
| 6 | Never Repeat Failures | ✅ Implemented | 3-Strike forces alternative approach on 2nd failure |

#### Supplementary Rules (7)

| # | Rule | Status | Implementation |
|---|------|--------|----------------|
| 7 | 3-Strike Error Protocol | ✅ Implemented | `check_and_update_strikes()` failure detection + graded warnings |
| 8 | 5-Question Reboot Test | ⏸️ Concept | Theoretical validation method, no code needed |
| 9 | Read vs Write Decision Matrix | ⏸️ Concept | Decision guide, no code needed |
| 10 | Attention Recitation | ✅ Implemented | PreToolUse `recite_objectives()` injects summary |
| 11 | Session Catchup (Context Recovery) | ✅ Implemented | `/focus:recover` restores session context |
| 12 | Phase Completion Check | ✅ Implemented | Stop hook `check_phases_complete()` |
| 13 | Bug Archival Assessment | ⚠️ Partial | done skill provides guidance, requires manual judgment |

#### Concept Explanations

**5-Question Reboot Test**: A validation method to check if AI's context is healthy. If AI can answer: (1) Where am I? (2) Where am I going? (3) What's the goal? (4) What have I learned? (5) What have I done? — then context management is solid. Focus implements this via `recite_objectives()` which answers questions 1-3 automatically.

**Read vs Write Decision Matrix**: A decision guide for when to read vs write files:
- Just wrote a file → Don't read (content still in context)
- Viewed image/PDF → Write immediately (multimodal content will be lost)
- Starting new phase → Read plan (refresh goals)
- After gap/interruption → Read all planning files (recover state)

**Goal:** Continue closing the gap by implementing remaining enforcement mechanisms.

---

## Architecture Overview

### Information Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        CONTEXT                              │
│                    (volatile, limited)                      │
└─────────────────────────┬───────────────────────────────────┘
                          │ [Information Persistence Reminder]
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   focus_context.md                                │
│              (persistent during focus)                      │
│  ┌─────────────┬──────────────┬───────────────────────┐    │
│  │   Plan      │   Findings   │   Errors              │    │
│  │  - [ ] ...  │  | Key | Val │  | Error | Resolution │    │
│  └─────────────┴──────────────┴───────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │ [focus:done archival]
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 PROJECT DOCUMENTATION                        │
│                    (permanent)                               │
│  ┌──────────────────┬────────────────┬─────────────────┐   │
│  │ architecture.md  │ troubleshoot.md│ known_bugs.md   │   │
│  │ CLAUDE.md        │ build_system.md│ resolved_bugs.md│   │
│  │ techniques.md    │ decisions.md   │ research/       │   │
│  └──────────────────┴────────────────┴─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Hook System

```
┌────────────────────────────────────────────────────────────┐
│                    focus_hook.py                           │
│                  (unified hook handler)                    │
├────────────────────────────────────────────────────────────┤
│  --hook pre --tool Read     → recite_objectives + count(+1)    │
│  --hook pre --tool WebSearch→ recite_objectives + count(+2)    │
│  --hook pre --tool UserPrompt→ recite_objectives + count(+3)   │
│  --hook pre --tool Write    → recite_objectives only           │
│  --hook post --tool Write   → remind_update               │
│  --hook stop                → check_phases_complete       │
└────────────────────────────────────────────────────────────┘
```

---

## Feature Specifications

### Manus "Objectives" Theory

**Core quotes:**
> "Manus is reciting its objectives into the end of the context"
> "Manus recites its goals by constantly rewriting the todo list"
> "This technique pushes the global plan into the model's recent attention span"

**Objectives - Three Elements:**
| Element | Content | Update Timing |
|---------|---------|---------------|
| **Plan** | Phase list | When plan changes |
| **Findings** | Information table | After acquiring new info |
| **Progress** | Checkbox status | After completing phase |

**Manus vs Our Implementation:**
| Aspect | Manus | Focus Plugin |
|--------|-------|--------------|
| Read timing | After each operation (just written) | PreToolUse hook |
| Write timing | constantly rewriting | Reminder-guided updates |
| Enforcement | System-forced | Reminder mechanism |

**Design Decisions:**
- "constantly rewriting" is hard to enforce, using reminder mechanism instead
- Added plan check prompt in information reminder for AI to evaluate if plan needs adjustment
- Added plan change reminder on Stop

---

### Feature 1: Session Display (PreToolUse)

**Purpose:** Push focus_context.md content into attention window before each tool use.

**Trigger:** All tool operations (Read, Glob, Grep, WebSearch, WebFetch, Write, Edit, Bash)

**Behavior:** Print summary (Task/Plan/Current Phase) from `$CLAUDE_FOCUS_DIR/focus_context.md`

---

### Feature 2: Information Persistence Reminder

**Purpose:** Periodically remind AI to persist valuable information from context to focus_context.md.

#### Information Sources and Weights

| Source | Tools | Weight | Rationale |
|--------|-------|--------|-----------|
| Local files | Read, Glob, Grep | +1 | Code/config discovery |
| External knowledge | WebSearch, WebFetch | +2 | External info easily forgotten |
| User input | UserPromptSubmit | +2 | User-provided info important |

**Threshold:** Trigger when weighted sum ≥ 5

#### Valuable Information Categories

| Category | Template Section | Archive Location |
|----------|------------------|------------------|
| Architecture | Findings | `architecture.md` |
| Conventions | Findings | `architecture.md` or `CLAUDE.md` |
| Config | Findings | `build_system.md` |
| External Knowledge | Findings | `research/` |
| Techniques | Findings | `techniques.md` |
| Bug (unresolved) | Issues | `known_bugs.md` |
| Bug (resolved) | Issues | `resolved_bugs.md` |
| Troubleshooting | Issues | `troubleshooting.md` |
| AI Norms | Decisions | `CLAUDE.md` |
| Decisions | Decisions | `decisions.md` |

#### Reminder Output Format (Scheme D)

```
[focus] Information Check (5)
Sources: Read×2 + WebSearch×1 + UserPrompt×1
Focus: Architecture | External Knowledge | AI Norms
All: Architecture|Bug|Conventions|Config|AI Norms|External Knowledge|Techniques|Decisions
⚠️ Based on new info, does the current plan need adjustment?
```

| Line | Content | Purpose |
|------|---------|---------|
| 1 | Title + weight | Indicate this is a check reminder |
| 2 | Source stats | Review what info types were gathered |
| 3 | Recommendations | Reduce cognitive load with smart suggestions |
| 4 | Full list | Prevent overlooking unexpected valuable info |
| 5 | Plan check | Prompt to evaluate if plan needs adjustment |

#### Source-to-Recommendation Mapping

| Source | Recommended Categories |
|--------|------------------------|
| Read | Architecture, Conventions |
| Glob/Grep | Architecture, Conventions |
| WebSearch/WebFetch | External Knowledge, Techniques |
| UserPrompt | AI Norms, Decisions |

---

### Feature 3: Modification Reminder (PostToolUse)

**Purpose:** Remind to update focus_context.md after file modifications.

**Trigger:** Write, Edit operations

**Output:** `[focus] If a phase is complete, please update focus_context.md`

---

### Feature 4: Completion Check (Stop)

**Purpose:** Verify all phases are complete before session ends.

**Trigger:** Stop hook (session end)

**Behavior:**
1. Count total `- [` and completed `- [x]` checkboxes
2. If all complete: Show completion workflow
3. If incomplete: Show warning + incomplete tasks + plan change reminder

**Output when incomplete:**
```
=== Task Completion Check ===
Phases: 3 / 5 complete
WARNING: Task not complete!
- [ ] Phase 4: ...
- [ ] Phase 5: ...

⚠️ If plan has changed, please update focus_context.md before ending session
```

---

### Feature 5: Context Recovery (/focus:recover)

**Purpose:** Recover context from previous sessions when Claude's session restore fails or is incomplete.

**Trigger:** Manual command `/focus:recover` (NOT automatic)

**Rationale for manual trigger:** User may start a new session for a different task; automatic recovery would be noise.

#### Scenario A: focus_context.md exists

1. Read `focus_context.md` content as primary source
2. Search session JSONL for supplementary information related to the document
3. Output: Merged context recovery report

#### Scenario B: focus_context.md does not exist

1. List recent 5 sessions with filtered summaries (5000 char budget each):
   ```
   === Recent Sessions ===

   --- Session 1 [2026-01-31 16:30] ---
   [16:25] USER: Help me fix the recovery
   [16:28] CLAUDE: Done. Config updated...

   --- Session 2 [2026-01-30 15:30] ---
   [15:20] USER: Focus plugin configuration
   [15:22] CLAUDE: Let me check...
   ```
2. AI uses AskUserQuestion to let user select session
3. Run `--recover <id>` with full budget (50000 chars)
4. Output: Conversation context recovery report

#### Recover Optimizations (2026-02-01)

**1. Noise Filtering**

Filters non-conversational content to preserve budget for valuable context:

```python
NOISE_XML_TAGS = [
    '<command-name>', '</command-name>',
    '<command-message>', '</command-message>',
    '<local-command-stdout>', '</local-command-stdout>',
    '<system-reminder>', '</system-reminder>',
]
```

| Filtered Content | Reason |
|-----------------|--------|
| `<command-name>` tags | Claude Code internal commands |
| `<system-reminder>` tags | System injected content |
| `tool_result` blocks | Tool output already processed |
| `[Request interrupted by user]` | Non-conversational |

**2. Exponential Decay Budget Allocation**

Problem: Equal budget distribution (50000/19 sessions = ~2600 chars each) wastes budget on old sessions.

Solution: Newest sessions get more budget with exponential decay:

```python
decay_factor = 0.5  # Each session gets 50% of remaining
min_session_budget = 1000  # Minimum allocation

# Process newest first
for session in reversed(sessions):
    budget_limit = remaining_budget * decay_factor
    content, used, skipped = filter_session(session, budget_limit)
    remaining_budget -= used  # Deduct actual usage, not allocated
```

| Session | Budget Limit | Actual Used | Remaining |
|---------|--------------|-------------|-----------|
| Newest | 25000 | 18000 | 32000 |
| 2nd | 16000 | 12000 | 20000 |
| 3rd | 10000 | 8000 | 12000 |
| ... | ... | ... | ... |

**Key design**: Unused budget carries over to next session.

**3. Skip Current Session**

The current session is already in AI's context window. Including it in recovery is redundant.

```python
current_session_id = get_from_latest_operation()
sessions = [s for s in sessions if s.id != current_session_id]
```

**4. Clean Old Verbose Logs**

Before writing new `dual_session_*.log` files, remove old ones to prevent stale data.

#### Design Decisions

| Decision | Rationale |
|----------|-----------|
| Manual trigger | Avoid noise when starting new unrelated tasks |
| Dual-source recovery | Reduces information loss from either source |
| Budget-based extraction | Character budget instead of line count for consistency |
| Tool filtering | Default filters all tool calls, shows only USER/CLAUDE text |
| Configurable via config.json | All parameters adjustable without code changes |
| Exponential decay | Newest sessions most relevant, deserve more budget |
| Skip current session | Already in context, recovery is redundant |
| Deduct actual usage | Unused budget carries over for better utilization |

---

### Feature 6: Mid-Session Checkpoint (/focus:checkpoint)

**Purpose:** Save progress during long focus sessions without ending them. Useful when:
- Session is getting long and context may be compacted
- Want to preserve findings before a risky operation
- Need to take a break but want to continue later

**Trigger:** Manual command `/focus:checkpoint`

**Behavior:**
1. Generate session summary from transcript (reuses `extract_session_info.py`)
2. Output valuable findings for archival
3. Suggest truncating verbose logs
4. Keep `focus_context.md` active (unlike `/focus:done` which deletes it)

**Key Differences from `/focus:done`:**

| Aspect | `/focus:checkpoint` | `/focus:done` |
|--------|---------------------|---------------|
| focus_context.md | Keeps active | Deletes |
| operations.jsonl | Keeps | Deletes |
| Session state | Continues | Ends |
| Use case | Mid-session save | Task complete |

**Implementation Notes:**
- Shares `generate_summary()` with `extract_session_info.py`
- Logger must be shared: `extract_session_info.logger = logger`
- Uses `os.environ.setdefault('PYTHONIOENCODING', 'utf-8')` for Windows encoding

---

## Implementation Details

### File Structure

```
focus/
├── scripts/                   # All Python scripts
│   ├── __init__.py            # Python package
│   ├── config.json            # Unified configuration
│   ├── focus_core.py          # Shared utilities (config, paths, helpers)
│   ├── log_utils.py           # Logging utilities
│   ├── focus_hook.py          # Unified hook handler
│   ├── recover_context.py     # Context recovery
│   ├── extract_session_info.py # Session summary extraction
│   └── checkpoint_session.py  # Mid-session checkpoint
├── docs/
│   ├── design_guide.md        # This file
│   └── references/
│       └── context_engineering_notes.md  # Context Engineering study notes
├── skills/
│   ├── start/
│   │   ├── SKILL.md           # Skill definition + hooks
│   │   └── examples.md        # focus_context.md templates
│   ├── done/
│   │   └── SKILL.md           # Completion workflow
│   ├── recover/
│   │   └── SKILL.md           # Context recovery
│   └── checkpoint/
│       └── SKILL.md           # Mid-session checkpoint
├── commands/
│   └── ...
└── README.md
```

### Counter Storage

File: `$CLAUDE_FOCUS_DIR/action_count.json`

```json
{
    "counts": {
        "Read": 2,
        "WebSearch": 1,
        "UserPrompt": 1
    },
    "total_weighted": 5
}
```

### Hook Configuration Pattern

Each tool gets its own matcher entry:

```yaml
PreToolUse:
  - matcher: "Read"
    hooks:
      - type: command
        command: "python .../focus_hook.py --hook pre --tool Read"
```

**Rationale:**
- Clear visibility of which tools are monitored
- Easy to add/remove individual tools
- Future extensibility for tool-specific behavior

---

### Configuration System

Focus plugin uses a **three-layer configuration system**:

| Layer | Path | Purpose | Git |
|-------|------|---------|-----|
| Default | `$CLAUDE_PLUGIN_ROOT/scripts/config.json` | Plugin built-in defaults | N/A (in plugin cache) |
| Project | `.claude/config/focus.json` | Project-level overrides | ✅ Tracked |
| Local | `.claude/config/focus.local.json` | Personal overrides | ❌ Gitignore |

**Merge order:** Default < Project < Local (later layers override earlier, deep merge)

#### Example: Override Confirm Before Modify

Create `.claude/config/focus.json` (only include fields you want to override):
```json
{
    "start": {
        "confirm_before_modify": {
            "enabled": true,
            "use_haiku": false
        }
    }
}
```

#### Default Configuration Reference

Full default configuration in `scripts/config.json`:

```json
{
    "logging": {
        "level": "DEBUG",
        "rotate_lines": 1000
    },
    "start": {
        "confirm_before_modify": {
            "enabled": true,
            "use_haiku": true
        },
        "threshold": 5,
        "recite_threshold": 3,
        "full_reminder_interval_minutes": 30,
        "max_strikes": 3,
        "error_patterns": [...],
        "weights": {...},
        "search_tools": [...],
        "modify_tools": [...],
        "recommendations": {...},
        "all_categories": "..."
    },
    "done": {
        "error_patterns": [...],
        "edit_tools": [...],
        "repeated_edit_threshold": 3
    },
    "recover": {
        "max_sessions": 5,
        "char_budget": 50000,
        "list_char_budget": 5000,
        "max_entry_length": 400,
        "noise_patterns": [...],
        "filter_tools": [],
        "filter_tool_categories": ["search", "modify", "task"],
        "key_tools": [...],
        "tool_categories": {...}
    }
}
```

---

### Logging System

Focus plugin uses a unified logging system in `scripts/log_utils.py`.

#### Log Levels

| Level | error.log | info.log | debug.log | verbose/* |
|-------|-----------|----------|-----------|-----------|
| ERROR | ✅ Append | ❌ | ❌ | ❌ |
| INFO | ✅ Append | ✅ Rotate | ❌ | ❌ |
| DEBUG | ✅ Append | ✅ Rotate | ✅ Append | ✅ Overwrite |

#### Log File Structure

```
$CLAUDE_FOCUS_DIR/logs/          # Default: .claude/tmp/focus/logs/
├── error.log                    # Permanent, user-cleared
├── info.log                     # Rotate at 1000 lines
├── debug.log                    # Append
└── verbose/                     # Overwrite per file
    ├── recover_session_1.log    # Session 1 summary
    ├── recover_full_summary.log # Full recovery output
    ├── dual_focus_context.log   # Dual-source context
    └── done_summary.log         # Done summary JSON
```

#### Usage

```python
from log_utils import Logger

logger = Logger(config, log_dir)
logger.info("func_name", "message")
logger.debug("func_name", "debug message")
logger.verbose("filename", "large content")
```

---

## Future Roadmap

### Implementation Progress Summary

| Category | Implemented | Partial/Manual | Concept Only | Total |
|----------|-------------|----------------|--------------|-------|
| Critical Rules (1-6) | 4 | 2 | 0 | 6 |
| Supplementary Rules (7-13) | 4 | 1 | 2 | 7 |
| **Total** | **8** | **3** | **2** | **13** |

**Completion Rate**: 8/13 = **62%** (excluding concept-only: 8/11 = **73%**)

### Low Difficulty (Ready to Implement)

- [x] SessionStart hook: Check if `focus_context.md` exists, remind user
  - **Status**: ✅ Implemented (auto-enabled via `hooks/hooks.json`)

### Medium Difficulty (Requires State Tracking)

- [x] Attention Recitation: Refresh plan before each tool use
  - **Status**: ✅ Implemented via `recite_objectives()` in PreToolUse hook
- [x] Error History: Capture tool failures, implement 3-Strike and Never Repeat
  - **Status**: ✅ Implemented via `check_and_update_strikes()` in PostToolUse hook
- [x] Confirm Before Modify: Check user confirmation before Write/Edit
  - **Status**: ✅ Implemented via `handle_confirm_before_modify()` + Haiku API (2026-02-01)
  - **Note**: "Read Before Edit" (reading file content before editing) is handled by Claude Code by default

### High Difficulty (Requires Semantic Understanding)

- [ ] Major Decision Detection: Identify when a "major decision" is being made
  - **Status**: ❌ Not implemented (requires semantic understanding)
- [ ] Bug Archival Assessment: Auto-evaluate if error should go to known_bugs.md or resolved_bugs.md
  - **Status**: ⚠️ Partial (done skill provides guidance, requires manual judgment)
- [ ] Log ALL Errors Auto-Archive: Automatically determine archive location
  - **Status**: ⚠️ Partial (extracted on done, requires manual archival)

### Remaining Work

| Priority | Item | Difficulty | Notes |
|----------|------|------------|-------|
| Low | Rule 1 Automation | Medium | Requires plugin system SessionStart support |
| Medium | Rule 5 Auto-Archive | High | Requires semantic understanding for location |
| Medium | Rule 13 Auto-Evaluate | High | Requires semantic understanding for importance |
| Low | Major Decision Detection | High | Requires identifying "major decision" semantics |

---

### Core Mechanism Details

#### Confirm Before Modify

**Purpose:** Prevent AI from modifying files without user confirmation of the execution plan.

**Note:** "Read Before Edit" (reading file content before editing) is a separate concept handled by Claude Code by default - it automatically reads files before editing them.

**Configuration:**
```json
{
    "start": {
        "confirm_before_modify": {
            "enabled": true,
            "use_haiku": true
        }
    }
}
```

| Setting | Behavior |
|---------|----------|
| `enabled: false` | Disabled completely |
| `enabled: true, use_haiku: true` | Haiku API checks if user confirmed; blocks if not |
| `enabled: true, use_haiku: false` | Reminder mode: prints warning, does not block |

**Reminder mode output:**
```
[Confirm Before Modify] About to modify: src/foo.gd
Ensure your execution plan has been approved by the user before proceeding.
```

**Haiku mode:**
- Uses `confirm_state.json` to cache confirmed files
- Calls Haiku API to check if user confirmed modification
- Resets state on `UserPromptSubmit` (new user message)

#### ID Index Mechanism

- `focus_hook.py` records `tool_use_id` to `operations.jsonl` (ID only, no content)
- `recover_context.py` / `extract_session_info.py` lookup full content from transcript via ID
- Advantage: Index file stays small, transcript is the complete data source

---

### Testing

#### Tested Features (2026-02-02)

| Feature | Script | Test Scenario | Result |
|---------|--------|---------------|--------|
| **Confirm Before Modify** | `focus_hook.py` | No confirmation → Block | ✅ Pass |
| | | Propose + Confirm + Modify → Allow | ✅ Pass |
| | | Same file again → Skip API, Allow | ✅ Pass |
| | | Confirm 2 files, modify 2nd → Allow | ✅ Pass |
| | | Confirm 1 file, modify another → Block | ✅ Pass |
| **3-Strike Protocol** | `focus_hook.py` | Consecutive failures + graded warnings | ✅ Pass |
| **ID Index Recording** | `focus_hook.py` | operations.jsonl write tool_use_id | ✅ Pass |
| **Session Recovery** | `recover_context.py` | operations.jsonl → transcript lookup | ✅ Pass |
| **Multi-Session Recovery** | `recover_context.py` | 17+ sessions, exponential budget | ✅ Pass |
| **Noise Filtering** | `recover_context.py` | XML tags, tool_result filtered | ✅ Pass |
| **Skip Current Session** | `recover_context.py` | Current session excluded from recovery | ✅ Pass |
| **Session Done** | `extract_session_info.py` | Extract operation summary from transcript | ✅ Pass |
| **Checkpoint** | `checkpoint_session.py` | Mid-session save, shared logger | ✅ Pass |
| **Logging System** | `log_utils.py` | error/info/debug/verbose output | ✅ Pass |
| **Config Loading** | `focus_core.py` | Three-layer config merge | ✅ Pass |
| **Information Persistence** | `focus_hook.py` | Weight-based reminder trigger | ✅ Pass |
| **Completion Check** | `focus_hook.py` | Stop hook phase verification | ✅ Pass |

#### Known Issues Fixed (2026-02-02)

| Issue | Cause | Resolution |
|-------|-------|------------|
| Hooks not triggering | SKILL.md frontmatter hooks ignored | Move to `hooks/hooks.json` |
| Windows encoding error | Emoji in GBK console | Replace emoji with ASCII |
| JSON file corruption | Non-atomic writes | Add `atomic_write_json()` |
| Recover only reads current session | `find_transcript_path()` returns one file | Extract all session IDs from operations |
| Budget allocation uneven | Equal distribution wastes on old sessions | Exponential decay with carry-over |
| Verbose logs sparse | Tool results consume budget | Noise filtering |
| checkpoint stdout closed | `io.TextIOWrapper` wrapping | Use `PYTHONIOENCODING` env var |
| checkpoint logger uninitialized | Module-level logger not shared | `extract_session_info.logger = logger` |

---

## References

- [Manus Context Engineering Blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Planning-with-Files Plugin](https://github.com/OthmanAdi/planning-with-files)
- [context_engineering_notes.md](references/context_engineering_notes.md) - Context Engineering study notes + Focus implementation mapping
- [examples.md](examples.md) - focus_context.md template examples
