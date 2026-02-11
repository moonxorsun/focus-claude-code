# Changelog

All notable changes and bug fixes for the Focus plugin.

---

## [1.4.1] - 2026-02-11

### Fixed

- **R6 confirmation skipped without focus session** - `confirm_reminder_read` and `confirm_skill_review_read` were behind the `if not focus_session_active: return` guard, causing R6 reminders to trigger but never confirm when no focus session was active. Moved confirmation logic before the guard, respecting `require_focus_session` config to match trigger logic.

---

## [1.4.0] - 2026-02-11

### Added

- **R1-R7 Behavioral Rules** - Replaced Critical Rules 1-6 with numbered behavioral norms in start/SKILL.md
  - R1: Confirm before modifying code
  - R2: Record information to focus_context.md promptly
  - R3: Don't repeat failures (3-Strike)
  - R4: Update context after modifications
  - R5: Verify commits are within Plan scope
  - R6: Read files when reminded by hooks
  - R7: Fix constraint warnings immediately
- **systemMessage Dual-Channel** - Hook output now supports both `additionalContext` (AI-visible) and `systemMessage` (user-visible terminal messages)
- **Section-Based Archive (Fallback)** - When no standard tables exist in focus_context.md, `focus_done.py` detects free-form sections (`## Heading`) and suggests archive categories
- **SKILL Review Reminder** - Independent periodic mechanism triggers AI to re-read start/SKILL.md (count-based and/or time-based, configurable)
- **Pending/Read-Confirm Mechanism** - File reminders and SKILL review set `pending=true` on trigger, only reset when AI actually reads the file
- **Two-Phase systemMessage** - Trigger shows "AI should read {file}", confirmation shows "AI has read {file}" for user visibility
- **`recite_enabled` Config Option** - Toggle objective recitation independently from other reminders

### Changed

- **start/SKILL.md** - Complete rewrite: R1-R7 rules, simplified template (only Task + Plan required), information persistence flow, Category reference
- **done/SKILL.md** - Added Category-to-archive-target mapping, section-based archive instructions
- **checkpoint/SKILL.md** - Table references replaced with generic section/free-form wording
- **Hook Short Reminders** - Now reference rule numbers: `[focus] R{n}: {description}`
- **Information Persistence Reminder** - Simplified text, references R2
- **File Reminders** - No longer inject full file content, only remind path (`[focus] R6: Please Read {file}`)
- **Constraint Warnings** - Output includes R7 reference prefix
- **install.py** - Installation messages now use systemMessage for user visibility
- **focus_context.md Template** - Only `## Task` and `## Plan` (with checkboxes) are required; all other sections are free-form

### Fixed

- **systemMessage JSON position** - `systemMessage` moved to top-level output (was incorrectly inside `hookSpecificOutput`)
- **Counter reset wiping unrelated fields** - `increment_and_check_counter` now preserves non-counter fields when resetting
- **SKILL review state file isolation** - Separated from `action_count.json` to independent `skill_review_state.json` to prevent read/write competition
- **checkpoint_session.py table dependency** - `get_recorded_content` now uses `extract_sections()` instead of hardcoded Issues/Decisions/Findings headers
- **extract_session_info.py print_summary()** - Adapted for free-form sections when no standard tables exist
- **25 items from comprehensive code review** - Dead code cleanup, bug fixes, documentation sync, configuration consistency

---

## [1.3.2] - 2026-02-10

### Fixed

- **Recover skips current session in dual mode** - When `focus_context.md` exists, `dual_source_recovery()` filtered out the current session's transcript. Removed the skip logic so recovery includes all sessions including the current one. The `list` mode (no context) branch is unchanged.

---

## [1.3.1] - 2026-02-09

### Fixed

- **snake_case_naming false positive on drive letters** - Windows drive letters (e.g. `D:`) were misidentified as PascalCase directory names. Now only checks directories within the project root, ignoring external path components like drive letters and parent directories.

---

## [1.3.0] - 2026-02-04

### Added

- **File Reminders** - Configurable time/turns-based file reminders (independent of focus session)
  - `reminders.enabled` - Enable/disable reminders globally
  - `reminders.require_focus_session` - Whether to require focus session (default: false)
  - `reminders.files[]` - Array of file configurations:
    - `file` - File path relative to project root
    - `mode` - Trigger mode: `time`, `turns`, or `both`
    - `time_minutes` - Time interval in minutes
    - `turns` - Number of conversation turns
  - State persisted in `.claude/tmp/focus/reminder_state.json`

---

## [1.2.1] - 2026-02-04

### Added

- **`require_focus_session` option** - Constraints only run during focus sessions by default (configurable)

### Fixed

- **Constraints not running without focus session** - Constraint checks were skipped when no focus session was active, now respects `require_focus_session` config
- **Incomplete cleanup on done** - Added missing session files to cleanup list (current_session_id.txt, confirm_state.json, etc.)

---

## [1.2.0] - 2026-02-04

### Added

- **Constraints module** - 8 configurable code quality constraints with warn/block actions:
  - `line_limit` - Block modifications exceeding 100 lines (configurable threshold)
  - `no_tabs` - Block tab characters in code files
  - `no_backslash_path` - Warn on backslash paths in Bash commands
  - `no_powershell` - Block PowerShell commands (configurable patterns)
  - `no_bash_file_ops` - Warn on cat/grep/find when dedicated tools exist
  - `no_hardcoded_path` - Warn on hardcoded scene paths (configurable rules)
  - `snake_case_naming` - Block non-snake_case filenames (allows UPPERCASE)
  - `fix_protocol` - Remind Fix Protocol before modifying code files
- **Fix Protocol integration** - Code files show detailed reminder, non-code files show simple reminder
- **Configurable PowerShell patterns** - `patterns` array and `check_dot_backslash` option

### Changed

- **Restructured to multi-plugin marketplace format** - Moved plugin to `plugins/focus/` subdirectory
- **Documentation links updated** - All docs now in `plugins/focus/docs/` or root `docs/`
- **README installation commands** - Fixed marketplace name from `moonxorsun-focus-claude-code` to `focus-claude-code`
- **done/SKILL.md** - Restructured workflow to 5 clear steps (Archive → Commit → Cleanup → Report)
- **start/SKILL.md** - Simplified Completion section (now references `/focus:done`)

### Fixed

- **Cross-platform compatibility** - Improved encoding and path handling
- **Session ID mismatch in recovery** - `list_recent_sessions()` and `recover_session()` now use shared `get_filtered_sessions()` function

---

## [1.1.1] - 2026-02-03

### Fixed

- **Hook output not visible to Claude** - Must use `hookSpecificOutput` JSON wrapper for context injection
- **Multiple JSON outputs cause hook validation failure** - Added `flush_output()` message collection mode
- **Windows file locking errors** - Added retry mechanism in `_atomic_write` (3 retries, 100ms delay)
- **hook_event parameter required** - Made explicit in `output_message()` to prevent context confusion
- **recover_context.py stdout encoding** - Use platform-aware encoding configuration
- **recover_context.py newline handling** - Strip `\r\n` properly on Windows

---

## [1.1.0] - 2026-02-02

### Added

- Mid-session checkpoint (`/focus:checkpoint`)
- Exponential decay budget allocation for recover
- Skip current session in recovery
- Clean old verbose logs before writing new ones

### Fixed

- **Hooks not triggering** - SKILL.md frontmatter hooks ignored, moved to `hooks/hooks.json`
- **Windows encoding error** - Emoji in GBK console, replaced with ASCII (`[!]` `[OK]` `[!!!]`)
- **JSON file corruption** - Non-atomic writes, added `atomic_write_json()` with temp+rename
- **Recover only reads current session** - `find_transcript_path()` returns one file, now extracts all session IDs from operations
- **Budget allocation uneven** - Equal distribution wastes on old sessions, exponential decay with carry-over
- **Verbose logs sparse** - Tool results consume budget, added noise filtering
- **checkpoint stdout closed** - `io.TextIOWrapper` wrapping issue, use `PYTHONIOENCODING` env var
- **checkpoint logger uninitialized** - Module-level logger not shared, added `extract_session_info.logger = logger`
- **logs directory not created** - SKILL.md hooks invalid, `os.getcwd()` wrong directory, moved to `hooks/hooks.json` with `$CLAUDE_PROJECT_DIR`
- **hooks not activated** - SKILL.md double quotes unescaped, YAML parsing truncated strings
- **$CLAUDE_PLUGIN_ROOT undefined** - commands/skills env var undefined, SessionStart writes `plugin_root.txt`
- **load_operations parameter error** - Passed project_path (directory) instead of OPERATIONS_FILE (file path)
- **read_stdin_data JSON parse failure** - Large JSON truncated or contains illegal chars, added `extract_key_fields()` regex fallback
- **check_user_confirmation error lacks context** - Exception only logs error, no API response content, added `result_text` init
- **check_user_confirmation JSON parse failure** - API response truncated or Markdown wrapped, changed to YES/NO response + string search
- **recover/extract scripts no log output** - `main()` didn't reload CONFIG, used plugin default instead of project config

### Changed

- API response format from JSON to YES/NO for robustness
- Logs now include file:line + traceback
- max_tokens reduced to 50 (YES/NO only needs 1-2 tokens)
- Extracted common module `focus_core.py` to eliminate code duplication
- Recover flow standardized with [REQUIRED] instruction block
- SessionStart hook moved to `hooks/hooks.json` for auto-activation

---

## [1.0.0] - 2026-01-31

### Added

- Initial release
- `/focus:start` - Create focus session
- `/focus:done` - Complete and archive session
- `/focus:recover` - Recover context from previous sessions
- Information Persistence Reminder (weight-based)
- Modification Reminder (PostToolUse)
- Completion Check (Stop hook)
- 3-Strike Error Protocol
- Confirm Before Modify (Haiku API)
- Session Display (Attention Recitation)
- Three-layer configuration system
- Unified logging system
