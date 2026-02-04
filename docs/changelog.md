# Changelog

All notable changes and bug fixes for the Focus plugin.

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
