---
name: start
version: "1.0.0"
description: Single-file planning for complex tasks. Creates .claude/tmp/focus/focus_context.md. Use when starting complex multi-step tasks or research projects.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - WebFetch
  - WebSearch
---

## Environment

| Variable | Default |
|----------|---------|
| `CLAUDE_FOCUS_DIR` | `.claude/tmp/focus` |

Use `$CLAUDE_FOCUS_DIR` in paths. If unset, use the default `.claude/tmp/focus`.

# Single-File Planning

Use a single persistent markdown file as your "working memory on disk."

## FIRST: Check for Previous Session

**Before starting work**, check for unfinished session:

If `.claude/tmp/focus/focus_context.md` exists, use `/focus:recover` to restore context.

## Quick Start

Before ANY complex task:

1. **Check for existing session** (use Glob tool):
   ```
   Glob: .claude/tmp/focus/focus_context.md
   ```
   - If file found → Ask user: "Found existing focus session. Continue it, or start fresh?"
   - If not found → Proceed to step 2

2. **Ensure directory exists** (use Bash):
   ```bash
   mkdir -p .claude/tmp/focus
   ```

3. **Create `.claude/tmp/focus/focus_context.md`** using template below
4. **Re-read plan before decisions** — Refreshes goals in attention window
5. **Update after each phase** — Mark complete, log findings, track errors

> 💡 **Tip:** See [examples.md](examples.md) for focus_context.md template examples (research, bug fix, error recovery).

## File Location

```
.claude/tmp/focus/focus_context.md   # Single planning file (gitignored)
```

**IMPORTANT**: Before creating focus_context.md, ensure directory exists:
```bash
mkdir -p .claude/tmp/focus
```

> The `.claude/tmp/` directory should be gitignored. Add to `.gitignore` if not present:
> ```
> .claude/tmp/
> ```

## Template

```markdown
# Focus Context

## Task
[Brief description of what we're trying to accomplish]

## Plan
- [ ] Phase 1: ...
- [ ] Phase 2: ...
- [ ] Phase 3: ...

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

### Template Sections

| Section | Purpose | Extract for Summary |
|---------|---------|---------------------|
| Task | Goal description | ✅ Yes |
| Plan | Phase checklist | ✅ Yes |
| Current Phase | Active work + blockers | ✅ Yes |
| Findings | Architecture, Conventions, Config, External Knowledge, Techniques | No |
| Issues | Bugs, Errors with cause and resolution | No |
| Decisions | AI Norms, Design decisions with rationale | No |

### Category Values

Use these categories when adding entries to Findings/Issues/Decisions:

| Category | Description |
|----------|-------------|
| architecture | Patterns, structures, component design |
| bugs | Unresolved bugs, known issues |
| resolved_bugs | Fixed bugs with cause and solution |
| troubleshooting | Debugging processes, diagnostic steps |
| ai_norms | AI collaboration rules, workflows |
| conventions | Coding standards, naming rules |
| external_knowledge | External references, API docs, libraries |
| techniques | Implementation techniques, algorithms |
| decisions | Design decisions, architectural choices |
| config | Build system, configuration settings |

> Archive targets are configured in the plugin. Use `/focus:done` when session completes.

## Critical Rules

### 1. Create Plan First
Never start a complex task without focus_context.md. Non-negotiable.

### 2. Information Persistence Reminder
> "Weighted point system triggers reminders to persist valuable context to focus_context.md."

### 3. Read Before Decide
Before major decisions, read the plan file. Keeps goals in attention window.

### 4. Update After Act
After completing any phase:
- Mark checkbox: `- [ ]` → `- [x]`
- Update "Current Phase"
- Log findings and errors

### 5. Log ALL Errors
Every error goes in the Issues table. Prevents repetition.

### 6. Never Repeat Failures
```
if action_failed:
    next_action != same_action
```

## The 3-Strike Error Protocol

```
ATTEMPT 1: Diagnose & Fix
ATTEMPT 2: Alternative Approach (NEVER repeat same action)
ATTEMPT 3: Broader Rethink
AFTER 3 FAILURES: Escalate to User
```

## Plan Restructure Rules

When the plan needs to be completely reworked (goal change, approach failure, better solution found):

| Section | Action | Details |
|---------|--------|---------|
| Task | Review & Update | Update if goal changed |
| Plan | Rewrite | New phase list |
| Current Phase | Reset | Point to first new phase |
| Findings | Keep | Information remains valuable |
| Issues | Keep | Problems still need tracking |
| Decisions | Review each | Mark obsolete with `[OBSOLETE]` |

**Required:** Add a new Decisions entry: `Restructure Plan | [reason for restructure]`

## When to Use

**Use for:**
- Multi-step tasks (3+ steps)
- Research tasks
- Building/creating projects
- Tasks requiring organization

**Skip for:**
- Simple questions
- Single-file edits
- Quick lookups

## Why Single File?

| Aspect | 3 Files | 1 File |
|--------|---------|--------|
| Read cost | 3 tool calls | 1 tool call |
| Context | Fragmented | Unified |
| Maintenance | 3 places to update | 1 place |
| Session resume | Read 3 files | Read 1 file |

## Completion

When ALL phases are marked `[x]`, run `/focus:done` to:
1. Archive findings to project docs
2. Process pending issues
3. Cleanup session files
4. Commit changes

## Advanced Topics

- **Manus Principles:** See [context_engineering_notes.md](../../docs/references/context_engineering_notes.md)
- **Template Examples:** See [examples.md](examples.md)

## Scripts

- `scripts/focus_hook.py` — Unified hook handler (recite_objectives, check_phases_complete, etc.)
