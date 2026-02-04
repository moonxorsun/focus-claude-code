#!/usr/bin/env python3
"""
Core utilities for focus plugin scripts.

Shared by: focus_hook.py, recover_context.py, extract_session_info.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from log_utils import _fatal_error

# =============================================================================
# Path Constants - Override via environment variables
# Environment variable prefix: CLAUDE_FOCUS_
# =============================================================================
FOCUS_DIR = os.environ.get("CLAUDE_FOCUS_DIR", ".claude/tmp/focus")
FOCUS_CONTEXT_FILE = os.environ.get("CLAUDE_FOCUS_CONTEXT_FILE", f"{FOCUS_DIR}/focus_context.md")
OPERATIONS_FILE = os.environ.get("CLAUDE_FOCUS_OPERATIONS_FILE", f"{FOCUS_DIR}/operations.jsonl")
COUNTER_FILE = os.environ.get("CLAUDE_FOCUS_COUNTER_FILE", f"{FOCUS_DIR}/action_count.json")
ERROR_LOG = os.environ.get("CLAUDE_FOCUS_ERROR_LOG", f"{FOCUS_DIR}/error.log")
FAILURE_COUNT_FILE = os.environ.get("CLAUDE_FOCUS_FAILURE_FILE", f"{FOCUS_DIR}/failure_count.json")
CONFIRM_STATE_FILE = os.environ.get("CLAUDE_FOCUS_CONFIRM_FILE", f"{FOCUS_DIR}/confirm_state.json")
PENDING_ISSUES_FILE = os.environ.get("CLAUDE_FOCUS_PENDING_ISSUES_FILE", f"{FOCUS_DIR}/pending_issues.md")
REMINDER_STATE_FILE = os.environ.get("CLAUDE_FOCUS_REMINDER_STATE_FILE", f"{FOCUS_DIR}/reminder_state.json")
REMINDER_STATE_FILE = os.environ.get("CLAUDE_FOCUS_REMINDER_STATE_FILE", f"{FOCUS_DIR}/reminder_state.json")
REMINDERS_CONFIG_FILE = ".claude/settings/reminders.json"

# Config file path (from plugin root, fallback to script directory)
PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', os.path.dirname(__file__))
CONFIG_FILE = (
    os.path.join(PLUGIN_ROOT, 'scripts', 'config.json')
    if os.environ.get('CLAUDE_PLUGIN_ROOT')
    else os.path.join(os.path.dirname(__file__), 'config.json')
)

# Claude projects directory
CLAUDE_PROJECTS_DIR = Path.home() / '.claude' / 'projects'


# =============================================================================
# Pure Utility Functions
# =============================================================================

def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base, returning new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_json_file(filepath) -> dict:
    """Load JSON file, return empty dict if not exists or error."""
    path = Path(filepath) if not isinstance(filepath, Path) else filepath
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        _fatal_error(f"load_json_file failed: {filepath}: {e}")


def atomic_write_json(filepath, data) -> bool:
    """Atomically write JSON to file using temp file + rename."""
    dir_path = os.path.dirname(filepath)
    os.makedirs(dir_path, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, filepath)
        return True
    except:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# =============================================================================
# Config Loading (3-layer merge)
# =============================================================================

def load_config(project_path: str = None) -> dict:
    """Load config with three-layer merge: default < project < local."""
    # Layer 1: Default config (plugin built-in)
    default_config = load_json_file(CONFIG_FILE)
    if not default_config:
        _fatal_error(f"Failed to load default config: {CONFIG_FILE}")

    if not project_path:
        return default_config

    # Layer 2: Project config (.claude/config/focus.json)
    project_config_path = Path(project_path) / ".claude" / "config" / "focus.json"
    project_config = load_json_file(project_config_path)

    # Layer 3: Local config (.claude/config/focus.local.json)
    local_config_path = Path(project_path) / ".claude" / "config" / "focus.local.json"
    local_config = load_json_file(local_config_path)

    # Merge: default < project < local
    merged = deep_merge(default_config, project_config)
    merged = deep_merge(merged, local_config)
    return merged


# =============================================================================
# Output Helper (Collect Mode)
# =============================================================================

# Global message collector - messages are collected and flushed once at script end
_pending_messages: List[str] = []
_current_hook_event: Optional[str] = None


def output_error(message: str, hook_event: str = None, block: bool = True, logger=None):
    """Output error in proper JSON format per Claude Code docs.

    For PreToolUse: Uses permissionDecision: "deny" + permissionDecisionReason
    For other hooks: Uses decision: "block" + reason

    Args:
        message: Error message
        hook_event: Hook event name (PreToolUse/PostToolUse/etc.)
        block: If True, block the action; if False, just add context
        logger: Optional logger instance
    """
    global _pending_messages, _current_hook_event

    if logger:
        logger.error("output_error", message)

    event = hook_event or _current_hook_event or "PostToolUse"

    if event == "PreToolUse":
        # PreToolUse uses hookSpecificOutput with permissionDecision
        output = {
            "hookSpecificOutput": {
                "hookEventName": event,
                "permissionDecision": "deny" if block else "allow",
                "permissionDecisionReason": message
            }
        }
    else:
        # Other hooks use top-level decision/reason
        if block:
            output = {
                "decision": "block",
                "reason": message
            }
        else:
            # Just add as context without blocking
            output = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": f"[ERROR] {message}"
                }
            }

    print(json.dumps(output))
    _pending_messages.clear()  # Clear any pending messages since we're outputting error
    _current_hook_event = None


def output_message(tag: str, message: str, hook_event: str, logger=None):
    """Collect message for later output. Call flush_output() at script end.

    Args:
        tag: Log tag for debugging
        message: Message to output
        hook_event: Hook event name (PreToolUse/PostToolUse/SessionStart/UserPromptSubmit)
        logger: Optional logger instance
    """
    global _current_hook_event

    if logger:
        logger.debug(tag, message.replace("\n", " | ")[:200])

    _pending_messages.append(message)
    _current_hook_event = hook_event


def flush_output(hook_event: str = None, as_json: bool = True):
    """Output all collected messages.

    Args:
        hook_event: Hook event name (for JSON mode)
        as_json: True = JSON format (for hooks), False = plain text (for skills)
    """
    global _pending_messages, _current_hook_event

    if not _pending_messages:
        return

    combined = "\n".join(_pending_messages)

    if as_json:
        event = hook_event or _current_hook_event or "PostToolUse"
        output = {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": combined
            }
        }
        print(json.dumps(output))
    else:
        print(combined)

    _pending_messages.clear()
    _current_hook_event = None


# =============================================================================
# Session Utilities
# =============================================================================

def find_transcript_path(project_path: str) -> Optional[Path]:
    """Find transcript path by matching project directory name."""
    p = Path(project_path).resolve()

    # Build expected prefix (drive letter + path with double dash after drive)
    parts = []
    if p.drive:
        parts.append(p.drive.replace(':', ''))
    parts.extend(p.parts[1:])  # Skip root

    # Join with single dash, then replace underscore with dash
    expected_prefix = '-'.join(parts).replace('_', '-')
    # Add extra dash after drive letter (D- -> D--)
    if p.drive:
        drive_letter = p.drive.replace(':', '')
        expected_prefix = expected_prefix.replace(f"{drive_letter}-", f"{drive_letter}--", 1)

    # Search in Claude projects directory
    if not CLAUDE_PROJECTS_DIR.exists():
        return None

    # Find matching directory
    for item in CLAUDE_PROJECTS_DIR.iterdir():
        if item.is_dir() and item.name == expected_prefix:
            # Find most recent .jsonl file
            jsonl_files = list(item.glob("*.jsonl"))
            if jsonl_files:
                # Sort by modification time, get most recent
                jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                return jsonl_files[0]

    return None


def get_project_dir(project_path: str) -> Optional[Path]:
    """Get Claude project directory for a project path."""
    p = Path(project_path).resolve()

    parts = []
    if p.drive:
        parts.append(p.drive.replace(':', ''))
    parts.extend(p.parts[1:])

    expected_prefix = '-'.join(parts).replace('_', '-')
    if p.drive:
        drive_letter = p.drive.replace(':', '')
        expected_prefix = expected_prefix.replace(f"{drive_letter}-", f"{drive_letter}--", 1)

    project_dir = CLAUDE_PROJECTS_DIR / expected_prefix
    if project_dir.exists():
        return project_dir
    return None


def load_operations(operations_file: str, logger=None) -> List[Dict]:
    """Load operations from operations.jsonl."""
    ops_path = Path(operations_file)
    operations = []
    if not ops_path.exists():
        return operations
    try:
        with open(ops_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    operations.append(json.loads(line))
                except json.JSONDecodeError as e:
                    if logger:
                        logger.error("load_operations.json_parse", e)
    except Exception as e:
        if logger:
            logger.error("load_operations", e)
    return operations


def get_all_session_ids_from_operations(operations: List[Dict]) -> List[str]:
    """Extract all unique session_ids from operations, ordered by first appearance."""
    seen = set()
    ordered = []
    for op in operations:
        sid = op.get('ids', {}).get('session_id')
        if sid and sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered


def get_session_transcripts_from_operations(
    operations: List[Dict], project_path: str
) -> List[tuple]:
    """Get all session transcript paths from operations that exist on disk."""
    session_ids = get_all_session_ids_from_operations(operations)
    project_dir = get_project_dir(project_path)
    if not project_dir:
        return []

    result = []
    for sid in session_ids:
        transcript = project_dir / f"{sid}.jsonl"
        if transcript.exists():
            result.append((sid, transcript))
    return result


def get_current_session_source() -> str:
    """
    Get current session source (startup, resume, clear, compact).

    Returns:
        Source string, or empty string if not found
    """
    source_file = os.path.join(FOCUS_DIR, 'current_session_source.txt')
    if os.path.exists(source_file):
        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    return ''


def get_current_session_id(operations: List[Dict] = None, logger=None) -> str:
    """
    Get current session ID.

    Priority:
    1. CLAUDE_SESSION_ID environment variable (set by Claude Code in hooks)
    2. Latest session_id from operations.jsonl

    Args:
        operations: Optional pre-loaded operations list
        logger: Optional logger instance

    Returns:
        Session ID string, or empty string if not found
    """
    # Try environment variable first (set by Claude Code in hooks)
    session_id = os.environ.get('CLAUDE_SESSION_ID', '')
    if session_id:
        return session_id

    # Try current_session_id.txt (written by SessionStart hook)
    session_id_file = os.path.join(FOCUS_DIR, 'current_session_id.txt')
    if os.path.exists(session_id_file):
        try:
            with open(session_id_file, 'r', encoding='utf-8') as f:
                session_id = f.read().strip()
                if session_id:
                    return session_id
        except Exception:
            pass

    # Fallback: get from operations.jsonl (latest session_id)
    if operations is None:
        operations = load_operations(OPERATIONS_FILE, logger)

    if operations:
        for op in reversed(operations):
            sid = op.get('ids', {}).get('session_id')
            if sid:
                return sid

    return ''


# =============================================================================
# Initialization Helper
# =============================================================================

def init_focus_env(project_path: str = None) -> Tuple[dict, str, str, str]:
    """
    Initialize focus environment with config and absolute paths.

    Returns:
        (CONFIG, FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE)
        All paths are absolute.
    """
    if project_path is None:
        project_path = os.getcwd()

    config = load_config(project_path)

    # Convert to absolute paths
    focus_dir = FOCUS_DIR
    focus_context_file = FOCUS_CONTEXT_FILE
    operations_file = OPERATIONS_FILE

    if not os.path.isabs(focus_dir):
        focus_dir = os.path.join(project_path, focus_dir)
    if not os.path.isabs(focus_context_file):
        focus_context_file = os.path.join(project_path, focus_context_file)
    if not os.path.isabs(operations_file):
        operations_file = os.path.join(project_path, operations_file)

    return config, focus_dir, focus_context_file, operations_file


# =============================================================================
# Pending Issues Management
# =============================================================================

def get_pending_issues_path(project_path: str = None) -> str:
    """Get absolute path to pending_issues.md."""
    if project_path is None:
        project_path = os.getcwd()
    pending_file = PENDING_ISSUES_FILE
    if not os.path.isabs(pending_file):
        pending_file = os.path.join(project_path, pending_file)
    return pending_file


def append_pending_issue(
    issue: Dict,
    project_path: str = None,
    logger=None
) -> bool:
    """
    Append a notable operation to pending_issues.md.

    Args:
        issue: Dict with keys: tool, tool_use_id, timestamp, snippet, session_id,
               file_path (optional), command (optional)
        project_path: Project root path
        logger: Optional logger instance

    Returns:
        True if successful
    """
    pending_file = get_pending_issues_path(project_path)

    # Ensure directory exists
    os.makedirs(os.path.dirname(pending_file), exist_ok=True)

    # Format the issue entry
    timestamp = issue.get('timestamp', 'unknown')
    tool = issue.get('tool', 'unknown')
    snippet = issue.get('snippet', '')[:200]
    session_id = issue.get('session_id', 'unknown')[:8]
    file_path = issue.get('file_path', '')
    command = issue.get('command', '')[:150]

    # Build entry with optional fields
    lines = [
        f"\n### {timestamp} | {tool} | error",
        f"- **Session**: {session_id}"
    ]
    if file_path:
        lines.append(f"- **File**: {file_path}")
    if command:
        lines.append(f"- **Command**: `{command}`")
    lines.append(f"- **Error**: {snippet}")

    entry = "\n".join(lines) + "\n"

    try:
        # Create file with header if not exists
        if not os.path.exists(pending_file):
            header = """# Pending Issues

> Auto-collected errors from focus session. Review during /focus:checkpoint or /focus:done.

## Unprocessed

"""
            with open(pending_file, 'w', encoding='utf-8') as f:
                f.write(header)

        # Append the issue
        with open(pending_file, 'a', encoding='utf-8') as f:
            f.write(entry)

        if logger:
            logger.debug("append_pending_issue", f"Added issue: {tool} at {timestamp}")
        return True

    except Exception as e:
        if logger:
            logger.error("append_pending_issue", e)
        return False


def get_pending_issues_count(project_path: str = None) -> int:
    """Get count of pending issues."""
    pending_file = get_pending_issues_path(project_path)
    if not os.path.exists(pending_file):
        return 0

    count = 0
    try:
        with open(pending_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('### ') and '| error' in line:
                    count += 1
    except Exception:
        pass
    return count


def clear_pending_issues(project_path: str = None, logger=None) -> bool:
    """Clear all pending issues (after processing)."""
    pending_file = get_pending_issues_path(project_path)
    if os.path.exists(pending_file):
        try:
            os.remove(pending_file)
            if logger:
                logger.info("clear_pending_issues", "Cleared pending issues")
            return True
        except Exception as e:
            if logger:
                logger.error("clear_pending_issues", e)
    return False


# =============================================================================
# File Reminders
# =============================================================================

def get_reminder_state_path(project_path: str = None) -> str:
    """Get absolute path to reminder_state.json."""
    if project_path is None:
        project_path = os.getcwd()
    state_file = REMINDER_STATE_FILE
    if not os.path.isabs(state_file):
        state_file = os.path.join(project_path, state_file)
    return state_file


def load_reminder_state(project_path: str = None, logger=None) -> Dict:
    """Load reminder state from JSON file."""
    state_file = get_reminder_state_path(project_path)
    return load_json_file(state_file)


def save_reminder_state(state: Dict, project_path: str = None, logger=None) -> bool:
    """Save reminder state to JSON file."""
    state_file = get_reminder_state_path(project_path)
    return atomic_write_json(state_file, state)


def check_and_trigger_reminders(
    config: Dict,
    project_path: str = None,
    logger=None
) -> List[Tuple[str, str]]:
    """
    Check all configured reminders and return files that should be reminded.

    Returns:
        List of (file_path, file_content) tuples for files needing reminder
    """
    import time

    if project_path is None:
        project_path = os.getcwd()

    reminders_config = config.get("reminders", {})
    if not reminders_config.get("enabled", True):
        return []

    files_config = reminders_config.get("files", [])
    if not files_config:
        return []

    state = load_reminder_state(project_path, logger)
    current_time = time.time()
    results = []
    state_changed = False

    for file_cfg in files_config:
        file_path = file_cfg.get("file", "")
        if not file_path:
            continue

        mode = file_cfg.get("mode", "both")
        time_minutes = file_cfg.get("time_minutes", 20)
        turns = file_cfg.get("turns", 15)

        # Get or init state for this file
        file_state = state.get(file_path, {"last_reminder_time": 0, "turns_since_reminder": 0})
        last_time = file_state.get("last_reminder_time", 0)
        turns_count = file_state.get("turns_since_reminder", 0) + 1  # Increment first

        should_remind = False

        # Check trigger conditions based on mode
        if mode == "time":
            elapsed_minutes = (current_time - last_time) / 60
            should_remind = elapsed_minutes >= time_minutes
        elif mode == "turns":
            should_remind = turns_count >= turns
        elif mode == "both":
            elapsed_minutes = (current_time - last_time) / 60
            should_remind = elapsed_minutes >= time_minutes or turns_count >= turns

        # First run (last_time == 0) always triggers
        if last_time == 0:
            should_remind = True

        if should_remind:
            abs_path = file_path if os.path.isabs(file_path) else os.path.join(project_path, file_path)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    results.append((file_path, content))
                except Exception as e:
                    if logger:
                        logger.error("check_reminders", f"Failed to read {file_path}: {e}")
            else:
                if logger:
                    logger.error("check_reminders", f"Reminder file not found: {file_path}")
            # Reset state regardless of file existence
            state[file_path] = {"last_reminder_time": current_time, "turns_since_reminder": 0}
            state_changed = True
        else:
            file_state["turns_since_reminder"] = turns_count
            state[file_path] = file_state
            state_changed = True

    if state_changed:
        save_reminder_state(state, project_path, logger)

    return results
