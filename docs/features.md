# Focus Plugin Features

This document describes all features of the Focus plugin with detailed specifications.

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `/focus:start` | Start a new focus session |
| `/focus:checkpoint` | Save progress mid-session |
| `/focus:done` | Complete session and archive |
| `/focus:recover` | Recover context from previous sessions |

---

## Feature 1: Session Display (Attention Recitation)

**Purpose:** Push focus_context.md content into attention window before tool use.

**Trigger:** Every N search operations (configurable via `recite_threshold`, default: 3)

**Behavior:** Print summary (Task/Plan/Current Phase) from `focus_context.md`

**Configuration:**
```json
{
    "start": {
        "recite_threshold": 3
    }
}
```

---

## Feature 2: Information Persistence Reminder

**Purpose:** Periodically remind AI to persist valuable information from context to focus_context.md.

### Information Sources and Weights

| Source | Tools | Weight | Rationale |
|--------|-------|--------|-----------|
| Local files | Read, Glob, Grep | +1 | Code/config discovery |
| External knowledge | WebSearch, WebFetch | +2 | External info easily forgotten |
| User input | UserPromptSubmit | +2 | User-provided info important |

**Threshold:** Trigger when weighted sum >= 5 (configurable)

### Valuable Information Categories

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

### Reminder Output Format

```
[focus] Info Check (5): Read×2 + WebSearch×1 + UserPrompt×1
-> Recommended: Architecture | External Knowledge
-> Record: Findings | Issues | Decisions
-> Evaluate Plan
```

---

## Feature 3: Modification Reminder

**Purpose:** Remind to update focus_context.md after file modifications.

**Trigger:** Write, Edit, Bash operations

**Output:** `[focus] Update context`

---

## Feature 4: Confirm Before Modify

**Purpose:** Prevent AI from modifying files without user confirmation.

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
| `enabled: true, use_haiku: false` | Reminder mode: prints warning only |

**Reminder mode output:**
```
[Confirm Before Modify] About to modify: src/foo.gd
Ensure your execution plan has been approved by the user before proceeding.
```

---

## Feature 5: 3-Strike Error Protocol

**Purpose:** Track consecutive failures and force alternative approaches.

**Behavior:**
- Strike 1: Warning - note the failure
- Strike 2: Strong warning - try different approach
- Strike 3: Stop - must change strategy completely

**Configuration:**
```json
{
    "start": {
        "max_strikes": 3
    }
}
```

---

## Feature 6: Completion Check

**Purpose:** Verify all phases are complete before session ends.

**Trigger:** Stop hook (session end)

**Behavior:**
1. Count total `- [` and completed `- [x]` checkboxes
2. If all complete: Show completion workflow
3. If incomplete: Show warning + incomplete tasks

**Output when incomplete:**
```
=== Task Completion Check ===
Phases: 3 / 5 complete
WARNING: Task not complete!
- [ ] Phase 4: ...
- [ ] Phase 5: ...
```

**Important Limitation:** Per Claude Code official docs, Stop hook stdout is **NOT visible to AI** - only visible to users in Verbose mode (Ctrl+O). The warning is for user awareness, not AI guidance.

---

## Feature 7: Context Recovery (/focus:recover)

**Purpose:** Recover context from previous sessions when Claude's session restore fails.

**Trigger:** Manual command `/focus:recover`

### Scenario A: focus_context.md exists

1. Read `focus_context.md` as primary source
2. Search session JSONL for supplementary information
3. Output: Merged context recovery report

### Scenario B: focus_context.md does not exist

1. List recent sessions with filtered summaries
2. AI uses AskUserQuestion to let user select session
3. Output: Conversation context recovery report

### Recovery Optimizations

| Optimization | Description |
|--------------|-------------|
| Noise Filtering | Filters XML tags, tool_result blocks |
| Exponential Decay | Newest sessions get more budget |
| Skip Current Session | Already in context |

---

## Feature 8: Mid-Session Checkpoint (/focus:checkpoint)

**Purpose:** Save progress during long focus sessions without ending them.

**Use cases:**
- Session is getting long and context may be compacted
- Want to preserve findings before a risky operation
- Need to take a break but want to continue later

**Behavior:**
1. Generate session summary from transcript
2. Output valuable findings for archival
3. Suggest truncating verbose logs
4. Keep `focus_context.md` active

**Differences from `/focus:done`:**

| Aspect | `/focus:checkpoint` | `/focus:done` |
|--------|---------------------|---------------|
| focus_context.md | Keeps active | Deletes |
| operations.jsonl | Keeps | Deletes |
| Session state | Continues | Ends |

---

## Test Checklist

### A. Infrastructure (4/4)

| # | Feature | Script | Status |
|---|---------|--------|--------|
| A1 | Logging system | log_utils.py | error/info/debug/verbose |
| A2 | Config three-layer loading | focus_core.py | Default < Project < Local |
| A3 | ID Index recording | focus_hook.py | operations.jsonl writes tool_use_id |
| A4 | SessionStart detection | focus_hook.py | Auto-detect unfinished session |

### B. Hook Features (6/6)

| # | Feature | Trigger | Status |
|---|---------|---------|--------|
| B1 | Session Display | PreToolUse (every N searches) | recite_objectives threshold trigger |
| B2 | Information Persistence | PostToolUse (weighted) | Weight >= 5 triggers, 30min full version |
| B3 | Modification Reminder | PostToolUse (Write/Edit) | Remind to update focus_context.md |
| B4 | Confirm Before Modify | PreToolUse (Write/Edit) | Haiku API confirmation |
| B5 | 3-Strike Error Protocol | PostToolUse (failure) | Graded warnings |
| B6 | Completion Check | Stop | Check phases complete |

### C. Recover Features (5/5)

| # | Feature | Scenario | Status |
|---|---------|----------|--------|
| C1 | Dual-source recovery | focus_context.md exists | Merge context + transcript |
| C2 | List mode | focus_context.md missing | List recent 5 sessions |
| C3 | Noise filtering | All scenarios | Filter XML tags and tool_result |
| C4 | Exponential decay budget | Multi-session | Newest gets more budget |
| C5 | Skip current session | All scenarios | Current session excluded |

### D. Checkpoint Features (4/4)

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| D1 | Error detection | is_error field detection | Detect user rejection |
| D2 | Omission detection | Haiku API analysis | Output [Issue]/[Decision]/[Finding] |
| D3 | pending_issues.md | Auto-record errors | Include File/Command fields |
| D4 | Session record cleanup | Post-process deletion | Keep only current session |

### E. Done Features (3/3)

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| E1 | Session summary | Extract from transcript | Tested |
| E2 | Archive suggestions | Findings/Issues/Decisions by category | Tested |
| E3 | Cleanup session files | Delete focus_context.md etc | Tested |

### F. Full Skill Workflow (4/4)

| # | Skill | Description | Status |
|---|-------|-------------|--------|
| F1 | /focus:start | Create focus_context.md + activate hooks | Tested |
| F2 | /focus:recover | Multi-scenario recovery + AskUserQuestion | Tested |
| F3 | /focus:checkpoint | Mid-session save + continue | Tested |
| F4 | /focus:done | Archive + cleanup + end session | Tested |
