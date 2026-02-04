#!/usr/bin/env python3
"""
Checkpoint session script for /focus:checkpoint workflow.

Processes sessions from old to new:
- Detects errors → pending_issues.md
- Detects omissions via Haiku API → AI adds to focus_context.md
- Removes processed session records from operations.jsonl

Usage:
    python checkpoint_session.py --mode=silent|interactive|oldest [--dry-run]

Modes:
    silent      Process all old sessions automatically
    interactive Process only the oldest session, then pause for user
    oldest      Alias for interactive
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Fix Windows encoding (set environment variable instead of wrapping stdout)
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# Reconfigure stdout/stderr for Windows
if sys.platform == 'win32':
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from log_utils import Logger
from focus_core import (
    load_config, output_message as _output_message, flush_output,
    init_focus_env, load_operations, get_project_dir,
    get_all_session_ids_from_operations,
    get_pending_issues_count, get_pending_issues_path, append_pending_issue,
    FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE
)
import extract_session_info
from extract_session_info import (
    generate_summary, print_summary, parse_focus_context,
    build_transcript_index, find_notable_operations
)
from recover_context import filter_session_from_end

# Global logger instance (initialized in main)
logger: Logger = None

# Checkpoint config (initialized in main)
CHECKPOINT_CONFIG = {}


def output_message(tag: str, message: str, hook_event: str):
    """Print message to AI context and log to debug."""
    _output_message(tag, message, hook_event, logger)


def get_current_session_id(operations: List[Dict]) -> Optional[str]:
    """Get current session ID from latest operation."""
    for op in reversed(operations):
        sid = op.get('ids', {}).get('session_id')
        if sid:
            return sid
    return None


def get_sessions_to_process(operations: List[Dict], project_path: str) -> List[Tuple[str, Path]]:
    """Get sessions to process (oldest first, excluding current)."""
    current_sid = get_current_session_id(operations)
    all_sids = get_all_session_ids_from_operations(operations)

    project_dir = get_project_dir(project_path)
    if not project_dir:
        return []

    result = []
    for sid in all_sids:
        if sid == current_sid:
            continue
        transcript = project_dir / f"{sid}.jsonl"
        if transcript.exists():
            result.append((sid, transcript))

    return result


def call_haiku_omission_check(session_text: str, recorded_content: str) -> str:
    """Call Haiku API to check for omissions."""
    try:
        import anthropic
    except ImportError:
        logger.error("call_haiku_omission_check", "anthropic module not installed")
        return "ERROR: anthropic module not installed"

    prompt = f"""Recorded content:
{recorded_content}

---

Conversation:
{session_text}

---

Compare the recorded content with the conversation above, list potentially omitted items:
1. Issue (problem/bug/error)
2. Decision (choice/approach)
3. Finding (discovery/insight/root cause)

Format:
[Issue] Brief description
[Decision] Brief description
[Finding] Brief description

If nothing is omitted, return only: NONE"""

    try:
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-3-5-haiku-latest")
        max_tokens = CHECKPOINT_CONFIG.get("haiku_max_tokens", 500)

        if base_url:
            client = anthropic.Anthropic(base_url=base_url)
        else:
            client = anthropic.Anthropic()

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        if not response.content:
            return "ERROR: Empty response from API"

        return response.content[0].text.strip()

    except Exception as e:
        logger.error("call_haiku_omission_check", e)
        return f"ERROR: {e}"


def get_recorded_content(focus_context_file: str) -> str:
    """Extract recorded Issues/Decisions/Findings from focus_context.md."""
    if not os.path.exists(focus_context_file):
        return "(empty)"

    try:
        with open(focus_context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract relevant sections
        import re
        sections = []
        for header in ["## Issues", "## Decisions", "## Findings"]:
            pattern = rf"({re.escape(header)}\s*\n)(.*?)(?=\n## |\Z)"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                sections.append(match.group(1) + match.group(2).strip())

        return "\n\n".join(sections) if sections else "(empty)"
    except Exception as e:
        logger.error("get_recorded_content", e)
        return "(error reading file)"


def process_single_session(
    sid: str,
    transcript_path: Path,
    operations: List[Dict],
    project_path: str,
    focus_context_file: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Process a single session: detect errors and omissions.

    Returns:
        Dict with 'errors_count', 'omission_result', 'session_text_length'
    """
    result = {
        "sid": sid,
        "errors_count": 0,
        "omission_result": "",
        "session_text_length": 0
    }

    # Filter operations for this session
    session_ops = [op for op in operations if op.get('ids', {}).get('session_id') == sid]

    # 1. Error detection
    if CHECKPOINT_CONFIG.get("error_detection", True):
        transcript_index = build_transcript_index(transcript_path)
        notable = find_notable_operations(transcript_index, session_ops)
        errors = [n for n in notable if n.get("type") == "failed"]
        result["errors_count"] = len(errors)

        # Write errors to pending_issues
        if errors and not dry_run:
            for issue in errors:
                issue['session_id'] = sid
                append_pending_issue(issue, project_path, logger)

    # 2. Omission detection
    if CHECKPOINT_CONFIG.get("omission_detection", True):
        char_budget = CHECKPOINT_CONFIG.get("omission_char_budget", 10000)
        session_text, used, _ = filter_session_from_end(transcript_path, char_budget, truncate=False)
        result["session_text_length"] = used

        if CHECKPOINT_CONFIG.get("use_haiku", True):
            recorded = get_recorded_content(focus_context_file)
            omission_result = call_haiku_omission_check(session_text, recorded)
            result["omission_result"] = omission_result
        else:
            # No Haiku: output session text for AI to check
            result["omission_result"] = f"[AI_CHECK_REQUIRED]\n{session_text}"

    return result


def remove_processed_sessions(
    operations_file: str,
    processed_sids: List[str],
    dry_run: bool = False
) -> Dict[str, int]:
    """Remove processed session records from operations.jsonl."""
    result = {"original": 0, "removed": 0, "remaining": 0}

    if not os.path.exists(operations_file):
        return result

    operations = load_operations(operations_file, logger)
    result["original"] = len(operations)

    remaining = [op for op in operations if op.get('ids', {}).get('session_id') not in processed_sids]
    result["remaining"] = len(remaining)
    result["removed"] = result["original"] - result["remaining"]

    if not dry_run and result["removed"] > 0:
        try:
            with open(operations_file, 'w', encoding='utf-8') as f:
                for op in remaining:
                    f.write(json.dumps(op, ensure_ascii=False) + '\n')
            if logger:
                logger.info("remove_processed_sessions", f"Removed {result['removed']} records")
        except Exception as e:
            if logger:
                logger.error("remove_processed_sessions", e)

    return result


def clear_verbose_logs(focus_dir: str, dry_run: bool = False) -> List[str]:
    """
    Clear verbose log files to save space.

    Returns:
        List of cleared file names
    """
    cleared = []
    focus_path = Path(focus_dir)

    if not focus_path.exists():
        return cleared

    # Clear verbose logs (but keep error.log)
    log_patterns = ["verbose_*.log", "debug_*.log"]

    for pattern in log_patterns:
        for log_file in focus_path.glob(pattern):
            cleared.append(log_file.name)
            if not dry_run:
                try:
                    log_file.unlink()
                    logger.debug("clear_verbose_logs", f"Removed {log_file.name}")
                except Exception as e:
                    logger.error("clear_verbose_logs", e)

    return cleared


def main():
    global logger, CHECKPOINT_CONFIG

    # Parse arguments
    parser = argparse.ArgumentParser(description='Checkpoint focus session')
    parser.add_argument('--mode', choices=['silent', 'interactive', 'oldest'],
                        default='interactive', help='Processing mode')
    parser.add_argument('--dry-run', action='store_true', help='Only show what would be done')
    args = parser.parse_args()

    dry_run = args.dry_run
    mode = args.mode
    project_path = os.getcwd()

    # Initialize environment
    config, focus_dir, focus_context_file, operations_file = init_focus_env(project_path)
    CHECKPOINT_CONFIG = config.get("checkpoint", {})

    # Initialize logger
    logger = Logger(config, focus_dir)
    extract_session_info.logger = logger
    logger.info("init", f"checkpoint_session.py started, mode={mode}")

    # Verify focus session is active
    if not os.path.exists(focus_context_file):
        output_message("error", "No active focus session found. Run /focus:start first.", "PostToolUse")
        sys.exit(1)

    # Load operations
    operations = load_operations(operations_file, logger)
    if not operations:
        output_message("info", "No operations recorded yet.", "PostToolUse")
        sys.exit(0)

    # Get sessions to process
    sessions = get_sessions_to_process(operations, project_path)
    if not sessions:
        output_message("info", "No old sessions to process (only current session exists).", "PostToolUse")
        sys.exit(0)

    # Determine how many sessions to process
    if mode in ['interactive', 'oldest']:
        sessions_to_process = sessions[:1]  # Only oldest
    else:  # silent
        sessions_to_process = sessions  # All old sessions

    # Header
    mode_label = "[DRY RUN] " if dry_run else ""
    output_message("checkpoint_header", "\n" + "=" * 60, "PostToolUse")
    output_message("checkpoint_header", f"{mode_label}CHECKPOINT: Processing {len(sessions_to_process)} session(s)", "PostToolUse")
    output_message("checkpoint_header", "=" * 60, "PostToolUse")

    # Process sessions
    processed_sids = []
    total_errors = 0
    omission_results = []

    for sid, transcript_path in sessions_to_process:
        output_message("session_start", f"\n--- Processing Session: {sid[:8]}... ---", "PostToolUse")

        result = process_single_session(
            sid, transcript_path, operations, project_path,
            focus_context_file, dry_run
        )

        processed_sids.append(sid)
        total_errors += result["errors_count"]

        if result["omission_result"] and result["omission_result"] != "NONE":
            omission_results.append((sid, result["omission_result"]))

        output_message("session_result", f"Errors detected: {result['errors_count']}", "PostToolUse")
        output_message("session_result", f"Text analyzed: {result['session_text_length']} chars", "PostToolUse")

    # Remove processed session records
    remove_result = remove_processed_sessions(operations_file, processed_sids, dry_run)

    # Summary
    output_message("summary", "\n" + "=" * 60, "PostToolUse")
    output_message("summary", "CHECKPOINT SUMMARY", "PostToolUse")
    output_message("summary", "=" * 60, "PostToolUse")
    output_message("summary", f"Sessions processed: {len(processed_sids)}", "PostToolUse")
    output_message("summary", f"Total errors recorded: {total_errors}", "PostToolUse")
    output_message("summary", f"Operations removed: {remove_result['removed']}", "PostToolUse")
    output_message("summary", f"Operations remaining: {remove_result['remaining']}", "PostToolUse")

    # Omission detection results
    if omission_results:
        output_message("omissions", "\n## Omission Detection Results", "PostToolUse")
        for sid, omission in omission_results:
            output_message("omissions", f"\n### Session {sid[:8]}...", "PostToolUse")
            output_message("omissions", omission, "PostToolUse")

        # Instruction for AI
        output_message("instructions", """
[REQUIRED] Based on the omission detection results above:
1. Add [Issue] items to the Issues table in focus_context.md
2. Add [Decision] items to the Decisions table in focus_context.md
3. Add [Finding] items to the Findings table in focus_context.md
4. If result is NONE or ERROR, no action needed
""", "PostToolUse")
    else:
        output_message("omissions", "\n## Omission Detection: No omissions found", "PostToolUse")

    # Clear verbose logs
    cleared_logs = clear_verbose_logs(focus_dir, dry_run)
    if cleared_logs:
        output_message("logs_cleared", f"\n## Cleared Logs: {', '.join(cleared_logs)}", "PostToolUse")

    # Pending issues count
    pending_count = get_pending_issues_count(project_path)
    if pending_count > 0:
        pending_file = get_pending_issues_path(project_path)
        output_message("pending_issues", f"\n## Pending Issues: {pending_count} items", "PostToolUse")
        output_message("pending_issues", f"Review: {pending_file}", "PostToolUse")

    logger.info("complete", f"Checkpoint complete, processed {len(processed_sids)} sessions")
    flush_output(as_json=False)


if __name__ == '__main__':
    main()
