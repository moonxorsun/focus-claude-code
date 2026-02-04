# Context Engineering Notes

> **Personal study notes** summarizing key concepts from Manus AI's blog post.
> This is NOT the original article - it's a condensed reference with Focus plugin implementation notes.
>
> Original source: https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
> Retrieved: 2026-01-31 | © Manus AI / Meta

---

## Introduction

Manus prioritizes "context engineering" to remain "orthogonal to the underlying models." They use "Stochastic Graduate Descent" to refine these principles.

---

## The 6 Core Principles

### Principle 1: KV-Cache Optimization

The "KV-cache hit rate" is THE single most important metric for production AI agents.

**Key Stats:**
- ~100:1 input-to-output token ratio
- Cached tokens: $0.30/MTok vs Uncached: $3/MTok (10x difference!)

**Best Practices:**
- Keep prefixes "stable" by avoiding timestamps
- Ensure "append-only" and "deterministic" serialization
- Use manual "cache breakpoints" if frameworks require them

---

### Principle 2: Mask, Don't Remove (Logit Masking)

Avoid dynamic tool changes that break caches. Instead, Manus "masks the token logits during decoding" using "response prefill" to restrict "action selection" via a "state machine."

> Don't dynamically remove tools (breaks KV-cache). Use logit masking instead.

---

### Principle 3: Filesystem as External Memory

> "Markdown is my 'working memory' on disk."

The "file system as the ultimate context" provides "unlimited" and "persistent" storage. Agents read and write files as "externalized memory" to circumvent token limits and performance degradation.

```
Context Window = RAM (volatile, limited)
Filesystem = Disk (persistent, unlimited)
```

---

### Principle 4: Manipulate Attention Through Recitation

> "Creates and updates todo.md throughout tasks to push global plan into model's recent attention span."

The agent manages focus by updating a "todo.md file." This process of "reciting its objectives" prevents "lost-in-the-middle" goal drift during long tasks.

**Problem:** After ~50 tool calls, models forget original goals ("lost in the middle" effect).

**Solution:** Re-read the plan file before each decision. Goals appear in the attention window.

---

### Principle 5: Keep the Wrong Stuff In

> "Leave the wrong turns in the context."

Do not scrub errors; "Erasing failure removes evidence." Keeping "wrong turns" in the log helps the AI's "internal beliefs" adapt through "error recovery."

- Failed actions with stack traces let model implicitly update beliefs
- Reduces mistake repetition
- Error recovery is "one of the clearest signals of TRUE agentic behavior"

---

### Principle 6: Don't Get Few-Shotted (Avoiding Mimicry)

> "Uniformity breeds fragility."

To prevent repetitive "rhythms," Manus adds "structured variation" and "controlled randomness." The rule is: "don't few-shot yourself into a rut."

Introduce controlled variation to avoid drift and hallucination.

---

## The 3 Context Engineering Strategies

### Strategy 1: Context Reduction (Compaction)

```
Tool calls have TWO representations:
├── FULL: Raw tool content (stored in filesystem)
└── COMPACT: Reference/file path only

RULES:
- Apply compaction to STALE (older) tool results
- Keep RECENT results FULL
```

---

### Strategy 2: Context Isolation (Multi-Agent)

```
┌─────────────────────────────────┐
│         PLANNER AGENT           │
├─────────────────────────────────┤
│       KNOWLEDGE MANAGER         │
├─────────────────────────────────┤
│      EXECUTOR SUB-AGENTS        │
└─────────────────────────────────┘
```

---

### Strategy 3: Context Offloading

- Use <20 atomic functions total
- Store full results in filesystem, not context
- Progressive disclosure: load information only as needed

---

## Critical Constraints

1. **Plan is Required:** Agent must ALWAYS know: goal, current phase, remaining phases
2. **Files are Memory:** Context = volatile. Filesystem = persistent.
3. **Never Repeat Failures:** If action failed, next action MUST be different

---

## Key Quotes

> "Context window = RAM (volatile, limited). Filesystem = Disk (persistent, unlimited)."

> "if action_failed: next_action != same_action"

> "Error recovery is one of the clearest signals of TRUE agentic behavior."

> "KV-cache hit rate is THE single most important metric for production AI agents."

---

## Application in Focus Plugin

### Principles Mapping

| Manus Principle | Status | Focus Plugin Implementation |
|-----------------|--------|----------------------------|
| KV-Cache Optimization | ❌ N/A | Claude Code managed service, no control |
| Mask, Don't Remove | ❌ N/A | No access to logit masking |
| Filesystem as Memory | ✅ Implemented | `focus_context.md` + `operations.jsonl` |
| Attention Recitation | ✅ Implemented | `recite_objectives()` + `extract_summary()` in PreToolUse |
| Keep Wrong Stuff In | ✅ System-handled | Claude Code retains errors in context; Issues table for persistence |
| Don't Get Few-Shotted | ❌ Not implemented | Needs structured variation in prompts |

### Strategies Mapping

| Manus Strategy | Status | Notes |
|----------------|--------|-------|
| Context Reduction | ✅ System-handled | Claude Code auto-compacts; `extract_summary()` for plan |
| Context Isolation | ❌ N/A | Multi-agent architecture, beyond plugin scope |
| Context Offloading | ⚠️ Partial | File storage works, but no on-demand loading |

### Constraints Mapping

| Manus Constraint | Status | Implementation |
|------------------|--------|----------------|
| Plan is Required | ✅ Implemented | SessionStart hook in `hooks/hooks.json` auto-detects unfinished focus session |
| Files are Memory | ✅ Implemented | focus_context.md + operations.jsonl |
| Never Repeat Failures | ✅ Implemented | 3-Strike Error Protocol: PostToolUse detects failures, counts per operation, warns at Strike 2 to use alternative approach |

---

*This document is for personal reference only. Copyright belongs to Manus AI.*
