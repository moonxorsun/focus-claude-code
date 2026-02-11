---
name: start
version: "2.0.0"
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

## Quick Start

1. **Check for existing session** (use Glob):
   - If `.claude/tmp/focus/focus_context.md` exists → Ask user: "Found existing focus session. Continue it (use `/focus:recover`), or start fresh?"
   - If not found → Proceed

2. **Ensure directory exists**: `mkdir -p .claude/tmp/focus`

3. **Create `.claude/tmp/focus/focus_context.md`** using template below

4. **Update after each phase** — Mark complete, record valuable information

> See [examples.md](examples.md) for template examples.

## Template

```markdown
# Focus: [short title]

## Task
[Brief description of what we're trying to accomplish]

## Plan
- [ ] Phase 1: ...
- [ ] Phase 2: ...
- [ ] Phase 3: ...

```

**Optional sections** — add any `## Section` freely. Common examples:

```markdown
## Findings
[Architecture patterns, conventions, external knowledge, techniques discovered]

## Issues
[Bugs encountered, root causes, resolutions]

## Decisions
[Design decisions with rationale, approach trade-offs]
```

Format within sections is free — use tables, lists, prose, whatever fits. The `/focus:done` workflow detects all `##` sections and suggests archive destinations.

### Category Reference

These categories guide what information is worth recording, and map to `/focus:done` archive targets:

| Category | What to record |
|----------|---------------|
| architecture | Patterns, structures, component design |
| bugs | Unresolved bugs, known issues |
| resolved_bugs | Fixed bugs with root cause and solution |
| troubleshooting | Debugging processes, diagnostic steps |
| conventions | Coding standards, naming rules |
| external_knowledge | External references, API docs, libraries |
| techniques | Implementation techniques, algorithms |
| decisions | Design decisions, architectural choices |
| config | Build system, configuration settings |
| ai_norms | AI collaboration rules, behavioral norms |

## Information Persistence

Session context is volatile — it disappears when the conversation ends. Record valuable information to focus_context.md so it survives across sessions.

```
Session (volatile) → focus_context.md (persistent) → Project docs (permanent)
      ↑ R2                                               ↑ /focus:done
```

**What to record:**
- Findings that would be hard to rediscover
- Bug root causes and fixes
- Design decisions with rationale
- Environment quirks or workarounds

**When to record:**
- After discovering something non-obvious
- After resolving a difficult bug
- After making a design decision
- When hook reminders prompt you (R2)

## Behavioral Rules (R1–R7)

These rules govern your behavior during a focus session. Hook reminders reference them by number.

### R1. Confirm Before Modify
Explain your approach before modifying code. Wait for user confirmation. For batch modifications, first confirmation covers the batch.

### R2. Record Valuable Information
Record findings, issues, and decisions to focus_context.md promptly. Don't wait — session context is volatile.

### R3. Never Repeat Failures
If an action fails, try a different approach. After 3 consecutive failures on the same problem, escalate to the user.

### R4. Update Context After Changes
After Write/Edit operations, check whether Plan checkboxes or other sections need updating.

### R5. Commit Within Plan Scope
Before `git commit`, verify the changes are within the current Plan scope. Don't commit unrelated changes.

### R6. Read When Reminded
When a hook reminder says `[focus] R6: Please Read {file}`, read that file immediately.

### R7. Fix Constraint Warnings
When a hook outputs `[WARN]`, correct the issue in your next action.

## Plan Restructure

When the plan needs reworking (goal change, approach failure, better solution found):

1. Update **Task** if the goal changed
2. Rewrite **Plan** with new phases
3. Keep **Findings/Issues** — information remains valuable
4. Review **Decisions** — mark obsolete ones with `[OBSOLETE]`
5. Record the restructure reason in the document

## When to Use

**Use for:**
- Multi-step tasks (3+ steps)
- Research tasks
- Building/creating projects

**Skip for:**
- Simple questions
- Single-file edits
- Quick lookups

## Completion

When ALL phases are marked `[x]`, run `/focus:done` to:
1. Archive findings to project docs
2. Process pending issues
3. Cleanup session files
4. Commit changes
