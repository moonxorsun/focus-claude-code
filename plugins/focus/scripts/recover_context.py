#!/usr/bin/env python3
"""
Context Recovery Script for focus plugin.

Recovers context from previous sessions when Claude's session restore fails.

Usage:
    python recover_context.py [project-path] [--list|--recover <session-id>]

Modes:
    --list              List recent 5 sessions with summaries
    --recover <id>      Recover context from specific session (1-5)
    (no args)           Auto-detect: if focus_context.md exists, do dual-source recovery
"""

import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Fix Windows encoding (set environment variable instead of wrapping stdout)
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# Reconfigure stdout/stderr for Windows
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from log_utils import Logger
from focus_core import (
    load_config, load_json_file, output_message as _output_message, flush_output,
    find_transcript_path, get_project_dir, load_operations,
    get_all_session_ids_from_operations, get_session_transcripts_from_operations,
    get_current_session_id, get_current_session_source,
    FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE, CLAUDE_PROJECTS_DIR
)

CONFIG = load_config()  # Default only, will be reloaded in main() with project path

# Global logger instance (initialized in main)
logger: Logger = None

# Recovery settings (from config.recover) - will be reloaded in main()
RECOVER_CONFIG = CONFIG.get("recover", {})
MAX_SESSIONS = RECOVER_CONFIG.get("max_sessions", 5)
DEFAULT_CHAR_BUDGET = RECOVER_CONFIG.get("char_budget", 50000)
LIST_CHAR_BUDGET = RECOVER_CONFIG.get("list_char_budget", 5000)
MAX_ENTRY_LENGTH = RECOVER_CONFIG.get("max_entry_length", 400)
DECAY_FACTOR = RECOVER_CONFIG.get("decay_factor", 0.5)
MIN_SESSION_BUDGET = RECOVER_CONFIG.get("min_session_budget", 1000)
NOISE_PATTERNS = RECOVER_CONFIG.get("noise_patterns", [])
FILTER_TOOLS = RECOVER_CONFIG.get("filter_tools", [])
FILTER_TOOL_CATEGORIES = RECOVER_CONFIG.get("filter_tool_categories", [])
KEY_TOOLS = RECOVER_CONFIG.get("key_tools", ["Edit", "Write", "Bash", "WebSearch"])
TOOL_CATEGORIES = RECOVER_CONFIG.get("tool_categories", {})


def output_message(tag: str, message: str, hook_event: str):
    """Print message to AI context and log to debug."""
    _output_message(tag, message, hook_event, logger)


def get_tools_to_filter() -> set:
    """Build set of tools to filter based on config."""
    tools = set(FILTER_TOOLS)
    for category in FILTER_TOOL_CATEGORIES:
        tools.update(TOOL_CATEGORIES.get(category, []))
    return tools

TOOLS_TO_FILTER = get_tools_to_filter()
# =============================================================================


def reverse_readline(filepath, buf_size=8192):
    """Generator that reads file lines in reverse order."""
    with open(filepath, 'rb') as f:
        f.seek(0, 2)  # End of file
        file_size = f.tell()

        if file_size == 0:
            return

        remaining = file_size
        buffer = b''

        while remaining > 0:
            read_size = min(buf_size, remaining)
            remaining -= read_size
            f.seek(remaining)
            chunk = f.read(read_size)
            buffer = chunk + buffer

            lines = buffer.split(b'\n')
            buffer = lines[0]  # Incomplete line at start

            for line in reversed(lines[1:]):
                if line:
                    yield line.decode('utf-8', errors='replace').rstrip('\r')

        if buffer:
            yield buffer.decode('utf-8', errors='replace').rstrip('\r')


def parse_timestamp(ts_str):
    """Parse ISO timestamp to datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except Exception as e:
        logger.error("parse_timestamp", e)
        return None


def format_time(dt):
    """Format datetime as [HH:MM]."""
    if dt:
        return dt.strftime("[%H:%M]")
    return "[??:??]"


# Noise patterns for filtering non-conversational content
NOISE_XML_TAGS = [
    '<command-name>', '</command-name>',
    '<command-message>', '</command-message>',
    '<command-args>', '</command-args>',
    '<local-command-stdout>', '</local-command-stdout>',
    '<local-command-caveat>', '</local-command-caveat>',
    '<system-reminder>', '</system-reminder>',
    '<system>', '</system>',
]


def _is_noise_content(text: str) -> bool:
    """Check if text is noise (non-conversational content)."""
    if not text:
        return True
    text = text.strip()
    if not text:
        return True
    # Skip system messages
    if text.startswith('<system'):
        return True
    # Skip command-related XML tags
    for tag in NOISE_XML_TAGS:
        if tag in text:
            return True
    # Skip tool rejection messages
    if text.startswith('[Request interrupted by user'):
        return True
    # Skip pure whitespace after tag removal
    return False


def extract_valuable_content(line, truncate=True):
    """
    Extract valuable content from a JSONL line.
    Returns dict with 'time', 'type', 'content', 'formatted' or None if not valuable.

    Args:
        line: JSONL line to parse
        truncate: If True, truncate long content to MAX_ENTRY_LENGTH
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    entry_type = data.get('type')
    timestamp = parse_timestamp(data.get('timestamp', ''))

    # Skip non-message types (file-history-snapshot, etc.)
    if entry_type not in ('user', 'assistant'):
        return None

    # User message
    if entry_type == 'user':
        msg = data.get('message', {})
        content = msg.get('content', '')

        # Handle list content (tool_result appears as list)
        if isinstance(content, list):
            # Extract only text items, skip tool_result
            texts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get('type') == 'text':
                        text = item.get('text', '')
                        if text and not _is_noise_content(text):
                            texts.append(text)
                    # Skip tool_result type entirely
            if not texts:
                return None
            content = '\n'.join(texts)

        # Skip if content is not a string
        if not isinstance(content, str):
            return None
        # Skip empty or noise content
        if not content or _is_noise_content(content):
            return None

        formatted = f"{format_time(timestamp)} USER: {content}"
        return {
            'time': timestamp,
            'type': 'USER',
            'content': content,
            'formatted': formatted
        }

    # Assistant message
    elif entry_type == 'assistant':
        msg = data.get('message', {})
        content = msg.get('content', [])

        # Check for filtered tools - skip entry if only contains filtered tools
        if TOOLS_TO_FILTER and isinstance(content, list):
            tool_names = [item.get('name', '') for item in content
                         if isinstance(item, dict) and item.get('type') == 'tool_use']
            if tool_names and all(name in TOOLS_TO_FILTER for name in tool_names):
                return None

        # Extract text content
        texts = []
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get('type') == 'text':
                        text = item.get('text', '')
                        if text:
                            texts.append(text)

        if not texts:
            return None

        # Build formatted output
        combined = '\n'.join(texts)
        # Filter out noise patterns
        for noise in NOISE_PATTERNS:
            combined = combined.replace(noise, '').strip()
        # Skip if only noise remained
        if not combined:
            return None
        # Truncate long responses (only if truncate=True)
        if truncate and len(combined) > MAX_ENTRY_LENGTH:
            combined = combined[:MAX_ENTRY_LENGTH] + '...'

        formatted = f"{format_time(timestamp)} CLAUDE: {combined}"
        return {
            'time': timestamp,
            'type': 'CLAUDE',
            'content': combined,
            'formatted': formatted
        }

    return None


def filter_session_from_end(transcript_path: Path, char_budget: int = DEFAULT_CHAR_BUDGET, truncate: bool = True) -> Tuple[str, int, int]:
    """
    Read transcript from end, extract conversational content until budget exhausted.

    Args:
        transcript_path: Path to transcript JSONL file
        char_budget: Maximum characters to extract
        truncate: If True, truncate long entries

    Returns:
        Tuple of (content, chars_used, entries_skipped)
    """
    if not transcript_path or not transcript_path.exists():
        return ("No transcript found.", 0, 0)

    entries = []
    remaining = char_budget
    header_reserve = 100
    remaining -= header_reserve
    skipped = 0

    for line in reverse_readline(transcript_path):
        entry = extract_valuable_content(line, truncate=truncate)
        if entry:
            entry_len = len(entry['formatted']) + 2
            if entry_len > remaining:
                skipped += 1
                continue  # Skip this entry, try next
            if remaining <= 0:
                break
            entries.append(entry)
            remaining -= entry_len

    # Reverse to chronological order
    entries.reverse()

    if not entries:
        return ("No conversational content found in transcript.", 0, 0)

    # Build output
    first_time = entries[0]['time']
    last_time = entries[-1]['time']

    if first_time and last_time:
        header = f"=== SESSION RECOVERY ({first_time.strftime('%Y-%m-%d %H:%M')} - {last_time.strftime('%H:%M')}) ==="
    else:
        header = "=== SESSION RECOVERY ==="

    lines = [header, ""]
    for entry in entries:
        lines.append(entry['formatted'])
        lines.append("")

    used = char_budget - remaining
    return ('\n'.join(lines), used, skipped)


def get_transcript_path_from_operations(operations: List[Dict], project_path: str) -> Optional[Path]:
    """Get transcript path from operations or derive from session_id."""
    if not operations:
        return None

    # Get session_id from latest operation
    for op in reversed(operations):
        ids = op.get('ids', {})
        session_id = ids.get('session_id')
        if session_id:
            project_dir = get_project_dir(project_path)
            return project_dir / f"{session_id}.jsonl"
    return None


def recover_by_tool_use_id(transcript_path: Path, tool_use_id: str) -> Optional[Dict]:
    """Find tool use content by tool_use_id in transcript."""
    if not transcript_path or not transcript_path.exists():
        return None
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                if tool_use_id in line:
                    try:
                        data = json.loads(line)
                        return data
                    except json.JSONDecodeError as e:
                        logger.error("recover_by_tool_use_id.json_parse", e)
    except Exception as e:
        logger.error("recover_by_tool_use_id", e)
    return None


def get_sessions_sorted(project_path: str) -> List[Path]:
    """Get all session files sorted by modification time (newest first)."""
    transcript_path = find_transcript_path(project_path)
    if not transcript_path:
        return []
    project_dir = transcript_path.parent
    sessions = list(project_dir.glob('*.jsonl'))
    main_sessions = [s for s in sessions if not s.name.startswith('agent-')]
    return sorted(main_sessions, key=lambda p: p.stat().st_mtime, reverse=True)


def get_session_timestamp(session_file: Path) -> str:
    """Get formatted timestamp of session file."""
    mtime = session_file.stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime('%Y-%m-%d %H:%M')


def extract_last_n_lines(session_file: Path, n: int = 50) -> List[Dict]:
    """Extract last N lines from session file."""
    messages = []
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-n:]:
                try:
                    data = json.loads(line)
                    messages.append(data)
                except json.JSONDecodeError as e:
                    logger.error("extract_last_n_lines.json_parse", e)
    except Exception as e:
        logger.error("extract_last_n_lines", e)
    return messages


def summarize_session(messages: List[Dict]) -> str:
    """Generate a one-line summary of session content."""
    user_messages = []
    tool_uses = set()

    for msg in messages:
        msg_type = msg.get('type')

        if msg_type == 'user':
            content = msg.get('message', {}).get('content', '')
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        text = item.get('text', '')
                        if text and not text.startswith('<'):
                            user_messages.append(text[:100])
                        break
            elif isinstance(content, str) and not content.startswith('<'):
                user_messages.append(content[:100])

        elif msg_type == 'assistant':
            msg_content = msg.get('message', {}).get('content', [])
            if isinstance(msg_content, list):
                for item in msg_content:
                    if item.get('type') == 'tool_use':
                        tool_name = item.get('name', '')
                        if tool_name:
                            tool_uses.add(tool_name)

    # Build summary
    summary_parts = []

    # First meaningful user message
    for um in user_messages[:3]:
        clean = um.strip()
        if clean and len(clean) > 10:
            summary_parts.append(clean[:60])
            break

    # Key tools used
    key_tools = [t for t in KEY_TOOLS if t in tool_uses]
    if key_tools:
        summary_parts.append(f"[{', '.join(key_tools[:3])}]")

    return ' - '.join(summary_parts) if summary_parts else '(no summary available)'


def list_recent_sessions(project_path: str) -> None:
    """List recent sessions with filtered summaries (smart filtering based on source)."""
    logger.info("list_recent_sessions", f"Listing sessions for {project_path}")

    # Get current session info
    current_session_id = get_current_session_id(logger=logger)
    current_source = get_current_session_source()

    # Smart filtering: only exclude current session for startup/clear (new sessions)
    # Keep current session for resume/compact (user may want to recover history)
    exclude_current = current_source in ('startup', 'clear', '')

    all_sessions = get_sessions_sorted(project_path)
    if exclude_current and current_session_id:
        sessions = [s for s in all_sessions if s.stem != current_session_id][:MAX_SESSIONS]
        logger.debug("list_recent_sessions", f"Excluded current session ({current_source}): {current_session_id[:8]}...")
    else:
        sessions = all_sessions[:MAX_SESSIONS]
        logger.debug("list_recent_sessions", f"Kept current session ({current_source}): {current_session_id[:8] if current_session_id else 'unknown'}...")

    if not sessions:
        output_message("list_sessions", "No recent sessions found.", "PostToolUse")
        logger.info("list_recent_sessions", "No sessions found")
        return

    parts = ["\n=== Recent Sessions ===\n"]

    # Collect session info for Step 2 options
    session_options = []

    for i, session in enumerate(sessions, 1):
        timestamp = get_session_timestamp(session)
        logger.debug("list_recent_sessions", f"Processing session {i}: {session.name}")
        content, used, skipped = filter_session_from_end(session, LIST_CHAR_BUDGET)
        logger.verbose(f"recover_session_{i}", content)
        parts.append(f"--- Session {i} [{timestamp}] ---")
        parts.append(content)
        parts.append(f"[Budget: {used}/{LIST_CHAR_BUDGET} used, {skipped} skipped]")
        parts.append("")

        # Extract summary for Step 2 options
        messages = extract_last_n_lines(session, 50)
        summary = summarize_session(messages)
        session_options.append((i, timestamp, summary))

    logger.info("list_recent_sessions", f"Listed {len(sessions)} sessions")
    parts.append("=" * 40)

    # Build Step 2 options string (max 4 options for AskUserQuestion)
    MAX_ASK_OPTIONS = 4
    step2_options = []
    total_sessions = len(session_options)
    has_more = total_sessions > MAX_ASK_OPTIONS

    # When <= 4 sessions: show all directly
    # When > 4 sessions: show first 3 + "More..."
    if has_more:
        display_count = MAX_ASK_OPTIONS - 1
    else:
        display_count = total_sessions

    for i, timestamp, summary in session_options[:display_count]:
        desc = summary[:80] + "..." if len(summary) > 80 else summary
        is_current = sessions[i-1].stem == current_session_id if current_session_id else False
        label_suffix = " (Current)" if is_current else ""
        step2_options.append(f'  {i}. Label: "Session {i} ({timestamp}){label_suffix}", Description: "{desc}"')

    if has_more:
        step2_options.append(f'  {display_count + 1}. Label: "More...", Description: "Enter session number ({display_count + 1}-{total_sessions}) in Other"')

    # [REQUIRED] directive for AI - Step 1
    parts.append("""
[REQUIRED] Step 1: Call AskUserQuestion with exactly these options:
- Header: "Recovery"
- Question: "No active focus session found. What would you like to do?"
- Options:
  1. Label: "Recover history", Description: "Choose from recent sessions listed above"
  2. Label: "Start new", Description: "Begin a new focus session with /focus:start"
  3. Label: "Cancel", Description: "Do nothing"
""")

    # [REQUIRED] directive for AI - Step 2 (conditional)
    parts.append(f"""
[REQUIRED] Step 2 (ONLY if user chose "Recover history"): Call AskUserQuestion with:
- Header: "Session"
- Question: "Which session would you like to recover?"
- Options:
{chr(10).join(step2_options)}

Then run: python "{os.path.abspath(__file__)}" --recover <N>
""")

    output_message("list_sessions", "\n".join(parts), "PostToolUse")


def recover_session(project_path: str, session_id: int) -> None:
    """Recover context from specific session using filtered extraction."""
    logger.info("recover_session", f"Recovering session {session_id}")
    sessions = get_sessions_sorted(project_path)[:MAX_SESSIONS]

    if session_id < 1 or session_id > len(sessions):
        output_message("recover_error", f"Error: Invalid session ID. Choose 1-{len(sessions)}", "PostToolUse")
        logger.error("recover_session", f"Invalid session ID: {session_id}")
        return

    session_file = sessions[session_id - 1]
    timestamp = get_session_timestamp(session_file)
    logger.debug("recover_session", f"Session file: {session_file}")

    # Use filtered extraction
    content, used, skipped = filter_session_from_end(session_file, DEFAULT_CHAR_BUDGET)
    logger.verbose("recover_full_summary", content)

    msg = f"""
=== CONTEXT RECOVERY ===
Session: {session_file.stem}
Last activity: {timestamp}

{content}
[Budget: {used}/{DEFAULT_CHAR_BUDGET} used, {skipped} skipped]

--- END RECOVERY ---

[REQUIRED] This is historical context only. No active focus session exists.
You MUST inform the user: "To start a new focus session based on this context, run /focus:start"
"""
    output_message("recover_session", msg, "PostToolUse")
    logger.info("recover_session", f"Recovery complete, {len(msg)} chars")


def dual_source_recovery(project_path: str) -> None:
    """Recover from focus_context.md and session JSONL with filtered extraction."""
    logger.info("dual_source_recovery", f"Starting dual-source recovery for {project_path}")
    focus_file = Path(project_path) / FOCUS_CONTEXT_FILE

    parts = ["\n=== DUAL-SOURCE CONTEXT RECOVERY ===\n"]

    # Source 1: focus_context.md
    parts.append("--- SOURCE 1: focus_context.md ---\n")
    try:
        with open(focus_file, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug("dual_source_recovery", f"focus_context.md: {len(content)} chars")
        logger.verbose("dual_focus_context", content)
        parts.append(content[:3000])
        if len(content) > 3000:
            parts.append("\n... (truncated)")
    except Exception as e:
        parts.append(f"Error reading focus_context.md: {e}")
        logger.error("dual_source_recovery", f"Failed to read focus_context.md: {e}")

    # Source 2: operations.jsonl
    parts.append("\n--- SOURCE 2: operations.jsonl ---\n")
    operations = load_operations(OPERATIONS_FILE, logger)
    if operations:
        logger.debug("dual_source_recovery", f"operations: {len(operations)} total")
        parts.append(f"Total operations recorded: {len(operations)}")

        # Show recent operations summary
        recent_ops = operations[-20:]
        tool_counts = {}
        for op in recent_ops:
            tool_name = op.get('ids', {}).get('tool_name', 'Unknown')
            if tool_name:
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

        if tool_counts:
            parts.append(f"Recent tools: {', '.join(f'{k}x{v}' for k, v in tool_counts.items())}")
    else:
        parts.append("No operations recorded yet.")

    # Source 3: Session JSONL with filtered extraction (all sessions from operations)
    parts.append("\n--- SOURCE 3: Session JSONL (filtered) ---\n")

    session_transcripts = get_session_transcripts_from_operations(operations, project_path)
    if session_transcripts:
        parts.append(f"Found {len(session_transcripts)} sessions in this focus period\n")

        # Clear old dual_session_*.log files before writing new ones
        verbose_dir = Path(FOCUS_DIR) / "logs" / "verbose"
        if verbose_dir.exists():
            for old_log in verbose_dir.glob("dual_session_*.log"):
                try:
                    old_log.unlink()
                    logger.debug("clear_old_logs", f"Removed {old_log.name}")
                except Exception as e:
                    logger.error("clear_old_logs", e)

        # Exponential decay budget allocation: newest sessions get more budget
        # Each session gets half of remaining budget, unused portion carries over
        total_budget = DEFAULT_CHAR_BUDGET
        min_session_budget = MIN_SESSION_BUDGET
        decay_factor = DECAY_FACTOR

        # Skip current session (newest one) - AI already has this context
        current_session_id = get_current_session_id(operations, logger)

        # Reverse to process newest first (transcripts are oldest-first)
        session_transcripts_reversed = list(reversed(session_transcripts))

        # Filter out current session
        if current_session_id:
            session_transcripts_reversed = [
                (sid, t) for sid, t in session_transcripts_reversed
                if sid != current_session_id
            ]
            logger.debug("skip_current_session", f"Skipped current session: {current_session_id[:8]}...")

        # Process sessions: allocate budget dynamically based on actual usage
        remaining_budget = total_budget
        session_results = []  # (sid, content, used, budget_limit, skipped)

        for i, (sid, transcript) in enumerate(session_transcripts_reversed):
            if remaining_budget <= 0:
                break

            # Calculate budget for this session: half of remaining (or all if below threshold)
            if remaining_budget <= min_session_budget:
                budget_limit = remaining_budget
            else:
                budget_limit = int(remaining_budget * decay_factor)

            # Process session
            content, used, skipped = filter_session_from_end(transcript, budget_limit)

            # Deduct actual usage (not allocated budget)
            remaining_budget -= used

            session_results.append((sid, content, used, budget_limit, skipped, remaining_budget))

        # Display in chronological order (oldest first)
        session_results.reverse()

        for i, (sid, content, used, budget_limit, skipped, remaining_after) in enumerate(session_results):
            budget_line = f"[Budget: {used}/{budget_limit} used, {remaining_after}/{total_budget} total remaining, {skipped} skipped]"
            parts.append(f"--- Session {i+1}/{len(session_results)}: {sid[:8]}... ---")
            logger.verbose(f"dual_session_{i+1}", content + "\n\n" + budget_line)
            parts.append(content)
            parts.append(budget_line)
            parts.append("")
    else:
        # Fallback to find_transcript_path if no operations
        transcript_path = find_transcript_path(project_path)
        if transcript_path:
            logger.debug("dual_source_recovery", f"Transcript: {transcript_path}")
            parts.append(f"Transcript: {transcript_path.name}")
            fallback_budget = DEFAULT_CHAR_BUDGET // 2
            content, used, skipped = filter_session_from_end(transcript_path, fallback_budget)
            logger.verbose("dual_session_summary", content)
            parts.append(content)
            parts.append(f"[Budget: {used}/{fallback_budget} used, {skipped} skipped]")
        else:
            parts.append("No transcript found.")

    parts.append("\n--- END RECOVERY ---\n")

    # [REQUIRED] directive for AI
    parts.append("""
[REQUIRED] You MUST call AskUserQuestion with exactly these options:
- Header: "Next Step"
- Question: "How would you like to proceed with this focus session?"
- Options:
  1. Label: "Continue task", Description: "Resume working from Current Phase"
  2. Label: "Complete session", Description: "Task is done, run /focus:done to archive"
  3. Label: "Restart", Description: "Abandon current task, start fresh with /focus:start"
  4. Label: "Cancel", Description: "Do nothing, just wanted to view context"
""")

    output_message("dual_recovery", "\n".join(parts), "PostToolUse")


def main():
    global logger, CONFIG, FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE

    # Use cwd directly - Claude Code always runs from project root
    project_path = os.getcwd()

    # Reload config with project path (merges project config)
    CONFIG = load_config(project_path)

    # Convert to absolute paths (only if relative)
    if not os.path.isabs(FOCUS_DIR):
        FOCUS_DIR = os.path.join(project_path, FOCUS_DIR)
    if not os.path.isabs(FOCUS_CONTEXT_FILE):
        FOCUS_CONTEXT_FILE = os.path.join(project_path, FOCUS_CONTEXT_FILE)
    if not os.path.isabs(OPERATIONS_FILE):
        OPERATIONS_FILE = os.path.join(project_path, OPERATIONS_FILE)

    # Initialize logger instance
    logger = Logger(CONFIG, FOCUS_DIR)
    logger.info("init", "recover_context.py started")

    # Parse mode
    mode = None
    session_id = None

    for i, arg in enumerate(sys.argv):
        if arg == '--list':
            mode = 'list'
        elif arg == '--recover' and i + 1 < len(sys.argv):
            mode = 'recover'
            try:
                session_id = int(sys.argv[i + 1])
            except ValueError:
                output_message("recover_error", "Error: --recover requires a number (1-5)", "PostToolUse")
                return

    # Auto-detect mode if not specified
    if mode is None:
        focus_file = Path(project_path) / FOCUS_CONTEXT_FILE
        if focus_file.exists():
            mode = 'dual'
        else:
            mode = 'list'

    # Execute
    if mode == 'list':
        list_recent_sessions(project_path)
    elif mode == 'recover':
        recover_session(project_path, session_id)
    elif mode == 'dual':
        dual_source_recovery(project_path)

    flush_output(as_json=False)


if __name__ == '__main__':
    main()
