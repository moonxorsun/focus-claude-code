# Development Notes

Development findings, decisions, and internal notes from Focus plugin development.

---

## Architecture Findings

| Finding | Details |
|---------|---------|
| Information Persistence Reminder | `action_count.json` accumulates to 5 then resets |
| Transcript Structure | `tool_use` in `assistant.message.content[]`, `tool_result` in `user.message.content[]` |
| is_error Field Reliability | Claude Code only sets `is_error=True` when user rejects operation |
| Category System | Extended to 10 categories: bugs/resolved_bugs split, added external_knowledge/techniques/decisions/config |
| Code Reuse | Three scripts had 30-40% duplicate code, extracted to `focus_core.py` |
| Recover Budget Allocation | Exponential decay: newest session 50%, decreasing, unused budget carries over |
| SessionStart Hook | Moved to `hooks/hooks.json`, auto-activates on plugin install |
| Environment Variables | Use `$CLAUDE_PLUGIN_ROOT` for config.json, fallback to `__file__` for manual debug |
| Output Messages | Use `output_message(tag, msg, hook_event)` for all AI-injected messages |
| API Response Format | Changed to YES/NO, string search more robust than JSON parsing |
| Logging | Added file:line + traceback using `inspect.currentframe()` |
| Token Limits | `max_tokens` set to 50, YES/NO response only needs 1-2 tokens |
| Plugin Root Discovery | Use `focus_plugin_root.txt` file, env vars only valid in hooks context |
| Hook Output Format | Must use `hookSpecificOutput` JSON wrapper for context injection |
| Message Collection | Use `flush_output()` to avoid multi-JSON validation failures |
| **Stop Hook Limitation** | Stop hook stdout NOT visible to AI per official docs. Only users see it in Verbose mode. To inject to AI context requires `decision: "block"` which prevents stopping |
| **systemMessage** | Top-level JSON field visible to user terminal (`{event}:{tool} says: {msg}`). `additionalContext` is AI-only (system-reminder injection). Two separate channels. |
| **PostToolUseFailure** | Only triggers for infrastructure errors (Bash non-zero exit, Write ENOENT). `<tool_use_error>` business errors (Read/Edit/Glob/Grep file not found) do NOT trigger any post hook. |
| **State File Isolation** | Different features must use independent state files. Shared files cause read/write competition when multiple functions load/save in same hook call. |
| **Pending/Read-Confirm Pattern** | Set `pending=true` on trigger (don't reset counter). Only reset when AI actually reads the file (path match in PostToolUse Read). Prevents re-trigger during pending. |
| **Prompt Execution Hierarchy** | 6 levels: Hard block (sys.exit) > [REQUIRED] instructions > SKILL.md rules (R1-R7) > Soft warnings > Periodic reminders > Passive hints. Position determines authority, not wording. |
| **SKILL.md vs Hook Reminders** | SKILL.md = early context, treated as "work norms" (high authority, forgotten over time). Hook reminders = end of context, treated as "runtime signals" (low authority, never forgotten). Complementary. |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Use `$CLAUDE_PLUGIN_ROOT` for config.json | Official standard env var, consistent with hooks.json |
| Unified `output_message(tag, msg, hook_event)` | All AI injection messages handled uniformly |
| API response changed to YES/NO | JSON parsing fragile (truncation, Markdown, bracket matching) |
| Logs include file:line + traceback | `inspect.currentframe()` for call location, exception includes full traceback |
| max_tokens set to 50 | YES/NO response only needs 1-2 tokens, 50 is sufficient |
| Extract common module focus_core.py | Eliminate 30-40% duplicate code |
| Recover flow standardized | Script outputs [REQUIRED] block, forces AI to call AskUserQuestion |
| Use focus_plugin_root.txt + current_session_id.txt | Env vars only valid in hooks context, files for commands/skills |
| decay_factor/min_session_budget configurable | Let users adjust recover budget allocation |
| Parallel session limit: warn only | Cannot reliably detect if another session is active |
| Imports at top of file | Python best practice, eliminate in-function imports |
| Hook only executes when focus session active | Silent exit without focus_context.md |
| hookSpecificOutput JSON wrapper | Required for Claude Code to inject additionalContext |
| flush_output() message collection | Avoid multiple JSON outputs causing hook validation failure |
| Windows retry mechanism (3 retries, 100ms) | Handle concurrent file locking |

---

## AI Norms

| Norm | Description |
|------|-------------|
| Recover post-AI behavior | SKILL.md is guidance only, AI may improvise. Script outputs [REQUIRED] block to force AskUserQuestion |
| Scenario 2 two-step Ask flow | Without context: first ask Recover/Start new/Cancel, then ask which Session |

---

## Conventions

| Convention | Description |
|------------|-------------|
| Simple test tasks | Verify plugin basic functions without complex business logic |
| Delete debug code | log_debug.json removed after logging verified |
| Add debug logs as needed | info.log + error.log cover core flow |
| Parallel session conflict | Not supported for same directory, SessionStart shows last activity time |
| settings.json permissions simplified | Read/Grep/Glob use tool name directly |
| Bash permission patterns | `$()` subcommand substitution cannot be matched (literal string matching) |
