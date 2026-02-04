#!/usr/bin/env python3
"""Unified hook script for focus plugin."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

from log_utils import Logger
from focus_core import (
    load_config, load_json_file, atomic_write_json,
    output_message as _output_message, output_error, flush_output,
    FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE, COUNTER_FILE,
    FAILURE_COUNT_FILE, CONFIRM_STATE_FILE
)
from constraints import check_constraints, format_constraint_message

# Alias for backward compatibility (SESSION_FILE -> FOCUS_CONTEXT_FILE)
SESSION_FILE = FOCUS_CONTEXT_FILE

CONFIG = load_config()  # Default only, will be reloaded in main() with project path

# Global logger instance (initialized in main)
logger: Logger = None

# Start settings (initialized in main after config reload)
START_CONFIG = {}
THRESHOLD = 5
MAX_STRIKES = 3
ERROR_PATTERNS = []
WEIGHTS = {}
SEARCH_TOOLS = []
MODIFY_TOOLS = []
RECOMMENDATIONS = {}
ALL_CATEGORIES = ""
# =============================================================================


def output_message(tag: str, message: str, hook_event: str):
    """Print message to AI context and log to debug."""
    _output_message(tag, message, hook_event, logger)


def load_counter():
    """Load counter from JSON file."""
    if not os.path.exists(COUNTER_FILE):
        return {"counts": {}, "total_weighted": 0}
    try:
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("load_counter", e)
        return {"counts": {}, "total_weighted": 0}


def save_counter(data):
    """Save counter to JSON file."""
    atomic_write_json(COUNTER_FILE, data)


def reset_counter():
    """Reset counter to zero."""
    save_counter({"counts": {}, "total_weighted": 0})


def load_failure_counts():
    """Load failure counts from JSON file."""
    if not os.path.exists(FAILURE_COUNT_FILE):
        return {}
    try:
        with open(FAILURE_COUNT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("load_failure_counts", e)
        return {}


def save_failure_counts(data):
    """Save failure counts to JSON file."""
    atomic_write_json(FAILURE_COUNT_FILE, data)


# =============================================================================
# Read Before Decide - Confirmation State Management
# =============================================================================

def load_confirm_state():
    """Load confirmed files state."""
    try:
        if os.path.exists(CONFIRM_STATE_FILE):
            with open(CONFIRM_STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error("load_confirm_state", e)
    return {"confirmed_files": []}


def save_confirm_state(state):
    """Save confirmed files state."""
    try:
        atomic_write_json(CONFIRM_STATE_FILE, state)
    except Exception as e:
        logger.error("save_confirm_state", e)


def reset_confirm_state():
    """Reset state on new user message."""
    save_confirm_state({"confirmed_files": []})


def get_recent_messages(transcript_path, n=20):
    """Read recent N messages from transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return []

    messages = []
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-n:]:
                try:
                    data = json.loads(line)
                    msg_type = data.get('type')

                    if msg_type == 'user':
                        content = data.get('message', {}).get('content', '')
                        if isinstance(content, str) and content and not content.startswith('<'):
                            messages.append(f"USER: {content[:500]}")

                    elif msg_type == 'assistant':
                        msg_content = data.get('message', {}).get('content', [])
                        if isinstance(msg_content, list):
                            for item in msg_content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    text = item.get('text', '')[:500]
                                    if text:
                                        messages.append(f"ASSISTANT: {text}")
                except Exception as e:
                    if logger:
                        logger.debug("get_recent_messages", f"Failed to parse line: {e}")
    except Exception as e:
        logger.error("get_recent_messages", e)

    return messages


def check_user_confirmation(messages, current_file, confirmed_files):
    """Call Claude API to check if user has confirmed this file."""
    try:
        import anthropic
    except ImportError:
        logger.error("check_user_confirmation", "anthropic module not installed")
        return True, False  # (allowed, should_record)

    if not messages:
        return True, False

    context = "\n".join(messages[-15:])

    # Build prompt based on whether we have previously confirmed files
    if confirmed_files:
        prompt = f"""Previously user confirmed modifications to: [{', '.join(confirmed_files)}]
Now modifying: [{current_file}]

Is this file within the scope of the previous confirmation?

Reply only: YES or NO

Conversation:
{context}"""
    else:
        prompt = f"""Determine if user approved code modification:
1. Did the assistant propose a change, plan, or modification?
2. Did the user agree? ("yes", "ok", "sure", "go ahead", "continue", etc.)

File to modify: [{current_file}]

Reply only: YES or NO

Conversation:
{context}"""

    result_text = ""
    try:
        # Get configuration from environment
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-3-5-haiku-latest")

        # Create client with optional base_url
        if base_url:
            client = anthropic.Anthropic(base_url=base_url)
        else:
            client = anthropic.Anthropic()

        response = client.messages.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )

        if not response.content:
            logger.error("check_user_confirmation", "Empty response content from API")
            return True, False

        result_text = response.content[0].text.strip().upper()

        # Simple YES/NO parsing
        confirmed = "YES" in result_text and "NO" not in result_text[:3]
        return confirmed, confirmed

    except Exception as e:
        logger.error("check_user_confirmation", f"{e} | result_text={result_text}")
        return True, False


def handle_confirm_before_modify(stdin_data):
    """Handle PreToolUse hook - check confirmation for Write/Edit."""
    tool_name = stdin_data.get("tool_name", "")

    if tool_name not in MODIFY_TOOLS or tool_name == "Bash":
        return  # Only check Write/Edit, not Bash

    # Check config
    cbm_config = START_CONFIG.get("confirm_before_modify", {})
    if not cbm_config.get("enabled", True):
        return

    # Get file path from tool input
    tool_input = stdin_data.get("tool_input", {})
    current_file = tool_input.get("file_path", "unknown")

    use_haiku = cbm_config.get("use_haiku", True)

    if not use_haiku:
        # Reminder mode: check if Fix Protocol should be used
        # Get fix_protocol config from constraints
        constraints_config = CONFIG.get("constraints", {})
        fix_protocol_config = constraints_config.get("rules", {}).get("fix_protocol", {})

        if fix_protocol_config.get("enabled", False):
            code_extensions = fix_protocol_config.get("code_extensions",
                [".gd", ".py", ".cpp", ".h", ".hpp", ".c", ".js", ".ts", ".tsx"])
            _, ext = os.path.splitext(current_file)

            if ext.lower() in code_extensions:
                # Fix Protocol for code files
                msg = f"""[Fix Protocol] About to modify: {current_file}
Before modifying code, ensure:
1. Issue analyzed & root cause identified
2. Fix proposal presented to user
3. User confirmation received"""
            else:
                # Generic reminder for non-code files
                msg = f"[Confirm Before Modify] About to modify: {current_file}\nEnsure your execution plan has been approved by the user before proceeding."
        else:
            # Default reminder when fix_protocol is disabled
            msg = f"[Confirm Before Modify] About to modify: {current_file}\nEnsure your execution plan has been approved by the user before proceeding."

        output_message("confirm_before_modify", msg, "PreToolUse")
        return

    # Haiku mode: call API to check confirmation
    # Load state
    state = load_confirm_state()
    confirmed_files = state.get("confirmed_files", [])

    # If file already confirmed, allow directly
    if current_file in confirmed_files:
        return

    # Call API to check
    transcript_path = stdin_data.get("transcript_path")
    messages = get_recent_messages(transcript_path)

    allowed, should_record = check_user_confirmation(messages, current_file, confirmed_files)

    if allowed:
        if should_record:
            confirmed_files.append(current_file)
            save_confirm_state({"confirmed_files": confirmed_files})
    else:
        output_error(
            f"[Read Before Decide] Please propose changes for [{current_file}] and wait for user confirmation.",
            "PreToolUse",
            block=True,
            logger=logger
        )
        sys.exit(1)


def get_operation_key(tool_name, tool_input):
    """Get unique key for an operation (tool + file path)."""
    file_path = None
    if isinstance(tool_input, dict):
        file_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("command", "")[:50]
    return f"{tool_name}:{file_path or 'unknown'}"


def detect_failure(tool_response):
    """Check if tool response indicates a failure.
    Only check error field, not result (file content) to avoid false positives.
    """
    if not tool_response:
        return False, None

    # For dict responses, only check error field, skip result (file content)
    if isinstance(tool_response, dict):
        error_field = tool_response.get("error")
        if not error_field:
            return False, None
        error_str = str(error_field).lower()
        for pattern in ERROR_PATTERNS:
            if pattern in error_str:
                return True, error_str[:120]
        return False, None

    # For string responses, check patterns
    response_str = str(tool_response).lower()
    for pattern in ERROR_PATTERNS:
        if pattern in response_str:
            idx = response_str.find(pattern)
            snippet = response_str[max(0, idx-20):idx+100]
            return True, snippet

    return False, None


def check_and_update_strikes(tool_name, tool_input, tool_response):
    """Check for failure and update strike count. Returns strike message if any."""
    is_failure, error_snippet = detect_failure(tool_response)
    op_key = get_operation_key(tool_name, tool_input)
    counts = load_failure_counts()

    if is_failure:
        # Increment failure count
        if op_key not in counts:
            counts[op_key] = {"count": 0, "last_error": ""}
        counts[op_key]["count"] += 1
        counts[op_key]["last_error"] = error_snippet or ""
        strike = counts[op_key]["count"]
        save_failure_counts(counts)

        # Generate warning based on strike count
        if strike == 1:
            return f"""
[focus] [!] STRIKE 1/3: Operation failed
{op_key}
→ Diagnose & Fix the issue
"""
        elif strike == 2:
            return f"""
[focus] [!!] STRIKE 2/3: Same operation failed again!
{op_key}
→ MUST use Alternative Approach (NEVER repeat same action)
"""
        elif strike >= MAX_STRIKES:
            return f"""
[focus] [!!!] STRIKE 3/3: ESCALATE TO USER
{op_key}
→ Broader Rethink required
→ Ask user for guidance before proceeding
→ Record this issue in focus_context.md Issues table
"""
    else:
        # Success - reset count for this operation
        if op_key in counts:
            del counts[op_key]
            save_failure_counts(counts)

    return None


def format_source_stats(counts):
    """Format source statistics for display."""
    parts = []
    for tool, count in counts.items():
        if count > 0:
            parts.append(f"{tool}×{count}")
    return " + ".join(parts) if parts else "None"


def get_recommendations(counts):
    """Get recommended categories based on sources."""
    recs = set()
    for tool, count in counts.items():
        if count > 0 and tool in RECOMMENDATIONS:
            recs.update(RECOMMENDATIONS[tool])
    return list(recs)[:3]  # Max 3 recommendations


def should_show_full_reminder() -> bool:
    """Check if full reminder should be shown (first time or 30+ min since last)."""
    interval_minutes = START_CONFIG.get("full_reminder_interval_minutes", 30)
    data = load_counter()
    last_full = data.get("last_full_reminder")

    if not last_full:
        return True

    try:
        last_time = datetime.fromisoformat(last_full)
        if datetime.now() - last_time >= timedelta(minutes=interval_minutes):
            return True
    except (ValueError, TypeError):
        return True

    return False


def save_full_reminder_time():
    """Save current time as last full reminder time."""
    data = load_counter()
    data["last_full_reminder"] = datetime.now().isoformat()
    save_counter(data)


def extract_summary(content):
    """Extract Task, Plan, Current Phase sections for attention injection."""
    sections = []
    for header in ["## Task", "## Plan", "## Current Phase"]:
        pattern = rf"({re.escape(header)}\s*\n)(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            sections.append(match.group(1) + match.group(2).strip())
    return "\n\n".join(sections) if sections else None


def recite_objectives():
    """Display focus_context.md summary or log error if missing."""
    if not os.path.exists(SESSION_FILE):
        logger.error("recite_objectives", f"SESSION_FILE not found: {SESSION_FILE}")
        return
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        if content.strip():
            summary = extract_summary(content)
            if summary:
                output_message("recite", summary[:2000], "PreToolUse")
            else:
                output_message("recite", content[:2000], "PreToolUse")
        else:
            output_message("recite", "[focus] focus_context.md is empty, please add plan content", "PreToolUse")
    except Exception as e:
        logger.error("recite_objectives", e)


def increment_and_check_recite(tool):
    """Increment recite counter and trigger recite_objectives if threshold reached."""
    data = load_counter()
    recite_count = data.get("recite_count", 0) + 1
    recite_threshold = START_CONFIG.get("recite_threshold", 3)

    if recite_count >= recite_threshold:
        recite_objectives()
        data["recite_count"] = 0
    else:
        data["recite_count"] = recite_count

    save_counter(data)


def increment_and_check_counter(tool):
    """Increment action counter and remind if threshold reached."""
    data = load_counter()
    counts = data.get("counts", {})
    total = data.get("total_weighted", 0)

    # Increment
    weight = WEIGHTS.get(tool, 1)
    counts[tool] = counts.get(tool, 0) + 1
    total += weight

    # Check information persistence threshold
    if total >= THRESHOLD:
        # Build reminder message
        source_stats = format_source_stats(counts)
        recs = get_recommendations(counts)
        recs_str = " | ".join(recs) if recs else "Review your findings"

        if should_show_full_reminder():
            # Full version (first time or 30+ min since last)
            msg = f"""
[focus] Information Persistence Reminder ({total})
Sources: {source_stats}

=== Why This Matters ===
Context window is volatile. Information not recorded WILL be lost.
"Lost in the middle" effect: After many operations, goals drift.

=== What To Record ===
| Type | Example | Table |
|------|---------|-------|
| Architecture | Code structure, patterns | Findings |
| Bug/Error | Problems encountered | Issues |
| Conventions | Naming, style rules | Findings |
| External Knowledge | API docs, tutorials | Findings |
| Decisions | Approach choices, trade-offs | Decisions |
| AI Norms | User preferences, project rules | Decisions |

Recommended for this check: {recs_str}

=== Expected Actions ===
1. Review what you just learned
2. Record valuable info in Findings/Issues/Decisions tables
3. Check: Does current plan need adjustment?

=== Avoid ===
- Assuming you'll remember later (you won't)
- Skipping "minor" findings (they compound)
- Continuing without updating plan when approach changed
"""
            save_full_reminder_time()
        else:
            # Simplified version (within 30 min)
            msg = f"""
[focus] Info Check ({total}): {source_stats}
-> Recommended: {recs_str}
-> Record: Findings | Issues | Decisions
-> Evaluate Plan
"""
        output_message("info_check", msg, "PostToolUse")

        # Reset counter (but keep last_full_reminder)
        data_to_save = {"counts": {}, "total_weighted": 0}
        current_data = load_counter()
        if "last_full_reminder" in current_data:
            data_to_save["last_full_reminder"] = current_data["last_full_reminder"]
        save_counter(data_to_save)
    else:
        # Save updated counter
        data["counts"] = counts
        data["total_weighted"] = total
        save_counter(data)


def remind_update():
    """Remind to update focus_context.md after modification."""
    msg = "[focus] Update context | Revise Plan if scope changed"

    # Check phase completion status
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        total = len(re.findall(r"- \[", content))
        complete = len(re.findall(r"- \[x\]", content, re.IGNORECASE))
        if total > 0:
            msg += f" | Phases: {complete}/{total}"
            if complete == total:
                msg += " | All complete! Run /focus:done"

    output_message("remind_update", msg, "PostToolUse")


def check_commit_in_plan(command: str):
    """Check if a git commit was made and remind to verify it's in Plan."""
    if not command or "git commit" not in command.lower():
        return

    # Extract commit message from command
    commit_msg = ""
    # Match -m "message" or -m 'message' (but not heredoc style)
    match = re.search(r'-m\s+["\']([^"\']+)["\']', command)
    if match and "$(cat" not in match.group(1):
        commit_msg = match.group(1)[:60]  # Truncate to 60 chars
    else:
        # Match heredoc style: -m "$(cat <<'EOF' or <<EOF
        match = re.search(r"<<'?EOF'?\s*\n(.+?)\nEOF", command, re.DOTALL)
        if match:
            commit_msg = match.group(1).strip().split('\n')[0][:60]

    if commit_msg:
        msg = f'[focus] Commit: "{commit_msg}" | Is this within current Plan? Revise if needed'
    else:
        msg = "[focus] Commit detected | Is this within current Plan? Revise if needed"

    output_message("commit_check", msg, "PostToolUse")
    """Check if all phases are complete."""
    if not os.path.exists(SESSION_FILE):
        return

    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    total = len(re.findall(r"- \[", content))
    complete = len(re.findall(r"- \[x\]", content, re.IGNORECASE))

    if total == 0:
        return

    if complete == total:
        msg = f"""=== Task Completion Check ===
Phases: {complete} / {total} complete

[OK] ALL PHASES COMPLETE!

Execute Completion Workflow:
1. Run /focus:done to archive findings and cleanup
2. Commit code changes
3. Notify user"""
        output_message("phases_complete", msg, "PostToolUse")
    else:
        incomplete = re.findall(r"- \[ \].*", content)
        tasks_str = "\n".join(incomplete[:3])
        msg = f"""=== Task Completion Check ===
Phases: {complete} / {total} complete
WARNING: Task not complete!
{tasks_str}

[!] If plan has changed, please update focus_context.md before ending session"""
        output_message("phases_incomplete", msg, "PostToolUse")


def extract_key_fields(raw: str):
    """Extract key fields from malformed JSON using regex."""
    import re
    result = {}

    # Extract session_id
    match = re.search(r'"session_id"\s*:\s*"([^"]+)"', raw)
    if match:
        result['session_id'] = match.group(1)

    # Extract tool_use_id
    match = re.search(r'"tool_use_id"\s*:\s*"([^"]+)"', raw)
    if match:
        result['tool_use_id'] = match.group(1)

    # Extract tool_name
    match = re.search(r'"tool_name"\s*:\s*"([^"]+)"', raw)
    if match:
        result['tool_name'] = match.group(1)

    # Extract hook_event_name
    match = re.search(r'"hook_event_name"\s*:\s*"([^"]+)"', raw)
    if match:
        result['hook_event_name'] = match.group(1)

    return result if result else None


def read_stdin_data():
    """Read and parse stdin JSON data."""
    try:
        raw = sys.stdin.read()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.debug("read_stdin_data", f"JSON parse failed, using regex fallback: {e}")
            return extract_key_fields(raw)
    except Exception as e:
        logger.error("read_stdin_data", e)
    return None


def record_operation(stdin_data, hook_type):
    """Record operation to operations.jsonl (index only, no full data)."""
    if not stdin_data:
        return

    try:
        ids = {
            "session_id": stdin_data.get("session_id"),
            "tool_use_id": stdin_data.get("tool_use_id"),
            "event": stdin_data.get("hook_event_name"),
            "tool_name": stdin_data.get("tool_name")
        }

        record = {
            "ts": datetime.now().isoformat(),
            "hook_type": hook_type,
            "ids": ids
        }

        os.makedirs(os.path.dirname(OPERATIONS_FILE), exist_ok=True)
        # Atomic append: read existing, append, atomic write
        existing = ""
        if os.path.exists(OPERATIONS_FILE):
            with open(OPERATIONS_FILE, "r", encoding="utf-8") as f:
                existing = f.read()
        new_line = json.dumps(record, ensure_ascii=False) + "\n"
        # Use temp file + rename for atomic write
        import tempfile
        dir_path = os.path.dirname(OPERATIONS_FILE) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(existing + new_line)
            os.replace(tmp_path, OPERATIONS_FILE)
        except:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
    except Exception as e:
        logger.error("record_operation", e)


def check_session_start(stdin_data: dict = None):
    """Check for existing focus session on session start."""
    # Save CLAUDE_PLUGIN_ROOT for commands to use
    # __file__ is in scripts/, CLAUDE_PLUGIN_ROOT should be parent (focus/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', os.path.dirname(script_dir))
    if plugin_root:
        os.makedirs(FOCUS_DIR, exist_ok=True)
        plugin_root_file = os.path.join(FOCUS_DIR, 'focus_plugin_root.txt')
        try:
            with open(plugin_root_file, 'w', encoding='utf-8') as f:
                f.write(plugin_root)
            # Write current session_id and source from stdin JSON
            session_id = stdin_data.get('session_id', '') if stdin_data else ''
            source = stdin_data.get('source', '') if stdin_data else ''
            if session_id:
                session_id_file = os.path.join(FOCUS_DIR, 'current_session_id.txt')
                with open(session_id_file, 'w', encoding='utf-8') as f:
                    f.write(session_id)
            if source:
                source_file = os.path.join(FOCUS_DIR, 'current_session_source.txt')
                with open(source_file, 'w', encoding='utf-8') as f:
                    f.write(source)
        except Exception as e:
            if logger:
                logger.error("check_session_start", e)

    if os.path.exists(SESSION_FILE):
        # Get last activity time
        try:
            mtime = os.path.getmtime(SESSION_FILE)
            from datetime import datetime
            last_activity = datetime.fromtimestamp(mtime)
            now = datetime.now()
            delta = now - last_activity

            # Format time ago
            if delta.days > 0:
                time_ago = f"{delta.days} day(s) ago"
            elif delta.seconds >= 3600:
                hours = delta.seconds // 3600
                time_ago = f"{hours} hour(s) ago"
            elif delta.seconds >= 60:
                minutes = delta.seconds // 60
                time_ago = f"{minutes} minute(s) ago"
            else:
                time_ago = "just now"

            time_str = last_activity.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = "unknown"
            time_ago = "unknown"

        msg = f"""
[focus] [!] Unfinished focus session detected!
Last activity: {time_str} ({time_ago})
- If this is YOUR session to recover: /focus:recover
- If another session is using it: do nothing or wait
"""
        output_message("session_start", msg, "SessionStart")


def main():
    global logger, CONFIG, START_CONFIG, THRESHOLD, MAX_STRIKES, ERROR_PATTERNS, WEIGHTS, SEARCH_TOOLS, MODIFY_TOOLS, RECOMMENDATIONS, ALL_CATEGORIES
    global FOCUS_DIR, SESSION_FILE, COUNTER_FILE, OPERATIONS_FILE, FAILURE_COUNT_FILE, CONFIRM_STATE_FILE

    # Use cwd directly - Claude Code always runs from project root
    project_path = os.getcwd()

    # Reload config with project path (enables project/local overrides)
    CONFIG = load_config(project_path)
    START_CONFIG = CONFIG.get("start", {})
    THRESHOLD = START_CONFIG.get("threshold", 5)
    MAX_STRIKES = START_CONFIG.get("max_strikes", 3)
    ERROR_PATTERNS = START_CONFIG.get("error_patterns", [])
    WEIGHTS = START_CONFIG.get("weights", {})
    SEARCH_TOOLS = START_CONFIG.get("search_tools", [])
    MODIFY_TOOLS = START_CONFIG.get("modify_tools", [])
    RECOMMENDATIONS = START_CONFIG.get("recommendations", {})
    ALL_CATEGORIES = START_CONFIG.get("all_categories", "")

    # Convert to absolute paths (only if relative)
    if not os.path.isabs(FOCUS_DIR):
        FOCUS_DIR = os.path.join(project_path, FOCUS_DIR)
    if not os.path.isabs(SESSION_FILE):
        SESSION_FILE = os.path.join(project_path, SESSION_FILE)
    if not os.path.isabs(COUNTER_FILE):
        COUNTER_FILE = os.path.join(project_path, COUNTER_FILE)
    if not os.path.isabs(OPERATIONS_FILE):
        OPERATIONS_FILE = os.path.join(project_path, OPERATIONS_FILE)
    if not os.path.isabs(FAILURE_COUNT_FILE):
        FAILURE_COUNT_FILE = os.path.join(project_path, FAILURE_COUNT_FILE)
    if not os.path.isabs(CONFIRM_STATE_FILE):
        CONFIRM_STATE_FILE = os.path.join(project_path, CONFIRM_STATE_FILE)

    parser = argparse.ArgumentParser(description="Focus plugin hook handler")
    parser.add_argument("--hook", required=True, choices=["pre", "post", "stop", "user", "session-start"])
    parser.add_argument("--tool", default=None)
    args = parser.parse_args()

    # Initialize logger instance
    logger = Logger(CONFIG, FOCUS_DIR)
    logger.info("init", "focus_hook.py started")

    # Check if focus session is active
    focus_session_active = os.path.exists(SESSION_FILE)

    # Map hook type to event name for flush_output
    hook_event_map = {"session-start": "SessionStart", "pre": "PreToolUse", "post": "PostToolUse", "user": "UserPromptSubmit"}
    hook_event = hook_event_map.get(args.hook, None)

    try:
        # session-start always runs (for detection and reminders)
        if args.hook == "session-start":
            stdin_data = read_stdin_data()
            check_session_start(stdin_data)
            return

        # Other hooks only run when focus session is active
        if not focus_session_active:
            logger.debug("main", "No active focus session, skipping hook")
            return

        # Read stdin for operation recording
        stdin_data = read_stdin_data()

        if args.hook == "pre":
            # Constraint checks (runs regardless of focus session)
            if stdin_data:
                constraints_config = CONFIG.get("constraints", {})
                tool_name = stdin_data.get("tool_name", args.tool or "")
                tool_input = stdin_data.get("tool_input", {})

                allowed, message, action = check_constraints(
                    tool_name, tool_input, constraints_config, logger
                )

                if not allowed and message:
                    formatted_msg = format_constraint_message(message, action)
                    if action == "block":
                        output_error(formatted_msg, "PreToolUse", block=True, logger=logger)
                        sys.exit(1)
                    else:
                        # warn or remind - just output message, don't block
                        output_message("constraint", formatted_msg, "PreToolUse")

            # Confirm Before Modify - check confirmation for Write/Edit
            if stdin_data:
                handle_confirm_before_modify(stdin_data)

            # Recite objectives (threshold-based)
            if args.tool in SEARCH_TOOLS:
                increment_and_check_recite(args.tool)

        elif args.hook == "post":
            # 3-Strike Error Protocol
            if stdin_data:
                tool_name = stdin_data.get("tool_name")
                tool_input = stdin_data.get("tool_input")
                tool_response = stdin_data.get("tool_response")
                strike_msg = check_and_update_strikes(tool_name, tool_input, tool_response)
                if strike_msg:
                    output_message("strike", strike_msg, "PostToolUse")

            record_operation(stdin_data, "PostToolUse")

            # Information Persistence Reminder (after acquiring info)
            if args.tool in SEARCH_TOOLS:
                increment_and_check_counter(args.tool)

            # Modification Reminder (after Write/Edit)
            if args.tool in MODIFY_TOOLS:
                remind_update()

            # Commit Check (after Bash with git commit)
            if args.tool == "Bash" and stdin_data:
                tool_input = stdin_data.get("tool_input", {})
                command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
                check_commit_in_plan(command)

        elif args.hook == "user":
            reset_confirm_state()  # Read Before Decide: reset on new user message
            record_operation(stdin_data, "UserPromptSubmit")

        elif args.hook == "stop":
            record_operation(stdin_data, "Stop")

    finally:
        # Always flush collected messages as single JSON output
        if hook_event:
            flush_output(hook_event)


if __name__ == "__main__":
    main()
