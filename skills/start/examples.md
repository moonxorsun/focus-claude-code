# Examples: Single-File Planning in Action

## Example 1: Research Task

**User Request:** "Research the benefits of morning exercise and write a summary"

### focus_context.md
```markdown
# Focus Context

## Task
Create a research summary on the benefits of morning exercise.

## Plan
- [x] Phase 1: Create this plan
- [x] Phase 2: Search and gather sources
- [ ] Phase 3: Synthesize findings
- [ ] Phase 4: Deliver summary

## Current Phase
Phase 3: Synthesize findings
- Working on: Organizing research into coherent summary
- Blocked: (none)

## Findings
| Category | Discovery | Details |
|----------|-----------|---------|
| architecture | Physical benefits | Boosts metabolism, improves cardiovascular health |
| architecture | Mental benefits | Reduces stress, improves focus and mood |
| architecture | Harvard 2023 study | Shows 20% productivity increase |

## Issues
| Category | Issue | Cause | Resolution |
|----------|-------|-------|------------|
| | (none) | | |

## Decisions
| Category | Decision | Rationale |
|----------|----------|-----------|
| conventions | Focus on peer-reviewed sources | Ensures credibility |
```

---

## Example 2: Bug Fix Task

**User Request:** "Fix the login bug in the authentication module"

### focus_context.md
```markdown
# Focus Context

## Task
Identify and fix the bug preventing successful login.

## Plan
- [x] Phase 1: Understand the bug report
- [x] Phase 2: Locate relevant code
- [x] Phase 3: Identify root cause
- [ ] Phase 4: Implement fix
- [ ] Phase 5: Test and verify

## Current Phase
Phase 4: Implement fix
- Working on: Adding async/await to fix promise handling
- Blocked: (none)

## Findings
| Category | Discovery | Details |
|----------|-----------|---------|
| architecture | Error location | src/auth/login.ts:42 |
| resolved_bugs | Root cause | user object not awaited properly |
| architecture | Related code | validateToken() function |

## Issues
| Category | Issue | Cause | Resolution |
|----------|-------|-------|------------|
| resolved_bugs | TypeError: Cannot read 'token' of undefined | user object is Promise, need await | Add async/await |

## Decisions
| Category | Decision | Rationale |
|----------|----------|-----------|
| architecture | Add async/await | Fix the promise handling issue |
```

---

## Example 3: The Attention Recitation Pattern

**Plan is automatically injected before each tool use:**

```
[Many tool calls have happened...]
[Context is getting long...]
[Original goal might be forgotten...]

→ PreToolUse hook triggers recite_objectives()
→ Task + Plan + Current Phase injected into context
→ Goals are fresh in attention window
→ Now make the decision with clear focus
```

This is why agents can handle ~50+ tool calls without losing track. The `recite_objectives()` function acts as a "goal refresh" mechanism.

---

## Example 4: Error Recovery Pattern

### Before (Wrong)
```
Action: Read config.json
Error: File not found
Action: Read config.json  # Silent retry - BAD!
Action: Read config.json  # Another retry - BAD!
```

### After (Correct)
```
Action: Read config.json
Error: File not found

# Update focus_context.md Issues table:
| config.json not found | Missing file | Will create default config |

Action: Write config.json (default config)
Action: Read config.json
Success!
```

---

## The Unified File Advantage

All context in one place:

```markdown
# Focus Context

## Task           ← What are we doing?
## Plan           ← Where are we going?
## Current Phase  ← Where are we now? What's blocking?
## Findings       ← What have we learned? (categorized)
## Issues         ← What went wrong and how was it fixed?
## Decisions      ← What did we decide and why?
```

One `Read` call = full context recovery.

Summary extraction (`recite_objectives()`) injects only Task + Plan + Current Phase for attention refresh.
