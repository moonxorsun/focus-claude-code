# Focus Plugin Development Guide

This document covers implementation details for developers and contributors.

---

## Configuration System

Focus uses a **three-layer configuration system**:

| Layer | Path | Purpose | Git |
|-------|------|---------|-----|
| Default | `$CLAUDE_PLUGIN_ROOT/scripts/config.json` | Plugin built-in defaults | N/A |
| Project | `.claude/config/focus.json` | Project-level overrides | Tracked |
| Local | `.claude/config/focus.local.json` | Personal overrides | Ignored |

**Merge order:** Default < Project < Local (later layers override earlier, deep merge)

### Example: Override Confirm Before Modify

Create `.claude/config/focus.json`:
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

### Default Configuration Reference

```json
{
    "logging": {
        "level": "INFO",
        "rotate_lines": 1000
    },
    "start": {
        "confirm_before_modify": {
            "enabled": true,
            "use_haiku": false
        },
        "threshold": 5,
        "recite_threshold": 3,
        "full_reminder_interval_minutes": 30,
        "max_strikes": 3,
        "weights": {
            "Read": 1, "Glob": 1, "Grep": 1,
            "WebSearch": 2, "WebFetch": 2,
            "UserPrompt": 2
        },
        "search_tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
        "modify_tools": ["Write", "Edit", "Bash"]
    },
    "recover": {
        "max_sessions": 5,
        "char_budget": 50000,
        "decay_factor": 0.5,
        "min_session_budget": 1000
    }
}
```

---

## Logging System

Focus uses a unified logging system in `scripts/log_utils.py`.

### Log Levels

| Level | error.log | info.log | debug.log | verbose/* |
|-------|-----------|----------|-----------|-----------|
| ERROR | Append | - | - | - |
| INFO | Append | Rotate | - | - |
| DEBUG | Append | Rotate | Append | Overwrite |

### Log File Structure

```
$CLAUDE_FOCUS_DIR/logs/
├── error.log                    # Permanent, user-cleared
├── info.log                     # Rotate at 1000 lines
├── debug.log                    # Append
└── verbose/                     # Overwrite per file
    ├── recover_session_1.log
    ├── recover_full_summary.log
    └── done_summary.log
```

### Usage

```python
from log_utils import Logger

logger = Logger(config, log_dir)
logger.info("func_name", "message")
logger.debug("func_name", "debug message")
logger.verbose("filename", "large content")
```

---

## Session Files

Focus uses temporary files in `$CLAUDE_FOCUS_DIR/` (default: `.claude/tmp/focus/`):

| File | Purpose |
|------|---------|
| `focus_context.md` | Main planning document |
| `operations.jsonl` | Operation history for recovery |
| `action_count.json` | Information Persistence counter |
| `pending_issues.md` | Auto-collected errors |
| `confirm_state.json` | Confirmed files cache |
| `focus_plugin_root.txt` | Plugin root path |
| `current_session_id.txt` | Current session ID |

---

## Hook System

### Hook Configuration

Hooks are defined in `hooks/hooks.json`:

```json
{
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Read",
                "hooks": [{
                    "type": "command",
                    "command": "python \"$CLAUDE_PLUGIN_ROOT/scripts/focus_hook.py\" --hook pre --tool Read"
                }]
            }
        ]
    }
}
```

### Hook Output Format

**Critical:** Hook output must use `hookSpecificOutput` wrapper for Claude Code context injection:

```json
{
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse:Read",
        "additionalContext": "[focus] Your message here"
    }
}
```

Use `flush_output()` to collect multiple messages and output a single JSON:

```python
from focus_core import output_message, flush_output

output_message("tag1", "message1", "PostToolUse:Read", logger)
output_message("tag2", "message2", "PostToolUse:Read", logger)
flush_output("PostToolUse:Read", logger)  # Outputs single JSON with all messages
```

---

## Key Functions

### focus_hook.py

| Function | Purpose |
|----------|---------|
| `recite_objectives()` | Extract and display Task/Plan/Current Phase summary |
| `increment_and_check_counter()` | Track tool usage, trigger Information Persistence Reminder |
| `check_and_update_strikes()` | 3-Strike Error Protocol |
| `handle_confirm_before_modify()` | Check user confirmation before Write/Edit |
| `check_phases_complete()` | Verify all phases marked `[x]` on session end |
| `record_operation()` | Log operation IDs to operations.jsonl |

### focus_core.py

| Function | Purpose |
|----------|---------|
| `load_config()` | Three-layer config merge |
| `output_message()` | Collect messages for AI injection |
| `flush_output()` | Output collected messages as JSON |
| `atomic_write_json()` | Safe JSON file writing with retry |
| `get_focus_dir()` | Get focus directory path |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_FOCUS_DIR` | `.claude/tmp/focus` | Root directory for session files |
| `CLAUDE_PLUGIN_ROOT` | (auto) | Plugin installation path (set by Claude Code) |
| `CLAUDE_PROJECT_DIR` | (auto) | Project root path (set by Claude Code) |

---

## ID Index Mechanism

- `focus_hook.py` records `tool_use_id` to `operations.jsonl` (ID only, no content)
- `recover_context.py` / `extract_session_info.py` lookup full content from transcript via ID
- Advantage: Index file stays small, transcript is the complete data source

---

## Windows Considerations

### File Locking

Windows may hold file locks during concurrent access. Use retry mechanism:

```python
def _atomic_write(path, content, retries=3, delay=0.1):
    for attempt in range(retries):
        try:
            # Write to temp file, then rename
            temp_path = path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, path)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
```

### Encoding

Set `PYTHONIOENCODING=utf-8` for proper Unicode handling:

```python
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
```

---

## Testing

Run hook manually for debugging:

```bash
python scripts/focus_hook.py --hook pre --tool Read
python scripts/focus_hook.py --hook post --tool Write
python scripts/focus_hook.py --hook stop
```

Check logs:
```bash
cat .claude/tmp/focus/logs/debug.log
cat .claude/tmp/focus/logs/error.log
```
