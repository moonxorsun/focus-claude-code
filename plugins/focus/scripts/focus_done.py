#!/usr/bin/env python3
"""
Focus Done script for /focus:done workflow.

Orchestrates the complete focus session closure:
1. Checkpoint: Process all unprocessed sessions (errors + omissions)
2. Extract: Parse Findings/Issues/Decisions from focus_context.md
3. Archive: Generate archive suggestions by category
4. Pending Issues: Group analysis and suggestions
5. Output [REQUIRED] instructions for AI

Usage:
    python focus_done.py [--dry-run]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Fix Windows encoding
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from log_utils import Logger
from focus_core import (
    load_config, output_message as _output_message, flush_output,
    init_focus_env, load_operations, get_project_dir,
    get_all_session_ids_from_operations, get_current_session_id,
    get_session_transcripts_from_operations,
    FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE, PENDING_ISSUES_FILE
)
from checkpoint_session import (
    process_single_session, remove_processed_sessions
)
from extract_session_info import parse_focus_context, generate_summary
import extract_session_info

CONFIG = load_config()
logger: Logger = None

# Archive config (from config.done.archive)
DONE_CONFIG = CONFIG.get("done", {})
ARCHIVE_CONFIG = DONE_CONFIG.get("archive", {})
BATCH_SIZE = ARCHIVE_CONFIG.get("batch_size", 5)
AUTO_CREATE = ARCHIVE_CONFIG.get("auto_create_missing_files", False)
ARCHIVE_TARGETS = ARCHIVE_CONFIG.get("targets", {})


def output_message(tag: str, message: str, hook_event: str):
    """Print message to AI context and log to debug."""
    _output_message(tag, message, hook_event, logger)


# =============================================================================
# Checkpoint Integration
# =============================================================================

def run_checkpoint_silent(project_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """Run checkpoint in silent mode to process all old sessions."""
    result = {
        "sessions_processed": 0,
        "total_errors": 0,
        "total_omissions": 0,
        "session_details": []
    }

    operations = load_operations(OPERATIONS_FILE, logger)
    if not operations:
        return result

    # Get all session IDs except current
    all_sids = get_all_session_ids_from_operations(operations)
    current_sid = get_current_session_id(operations, logger)
    old_sids = [sid for sid in all_sids if sid != current_sid]

    if not old_sids:
        return result

    focus_context_file = os.path.join(project_path, FOCUS_CONTEXT_FILE)

    # Get transcript paths for sessions (returns list of (sid, path) tuples)
    transcripts_list = get_session_transcripts_from_operations(operations, project_path)
    transcripts = {sid: path for sid, path in transcripts_list}

    processed_sids = []

    for sid in old_sids:
        transcript_path = transcripts.get(sid)
        if not transcript_path:
            continue

        session_result = process_single_session(
            sid, transcript_path, operations, project_path, focus_context_file, dry_run
        )
        if session_result:
            result["sessions_processed"] += 1
            result["total_errors"] += session_result.get("errors_count", 0)
            if session_result.get("omission_result"):
                result["total_omissions"] += 1
            result["session_details"].append({
                "session_id": sid[:8],
                "errors": session_result.get("errors_count", 0),
                "has_omissions": bool(session_result.get("omission_result"))
            })
            processed_sids.append(sid)

    # Remove processed sessions from operations.jsonl
    if processed_sids and not dry_run:
        remove_processed_sessions(OPERATIONS_FILE, processed_sids, dry_run)

    return result


# =============================================================================
# Extract Integration
# =============================================================================

def extract_focus_context(project_path: str) -> Dict[str, Any]:
    """Extract Findings/Issues/Decisions from focus_context.md."""
    focus_context_file = os.path.join(project_path, FOCUS_CONTEXT_FILE)
    context_data = parse_focus_context(focus_context_file)

    # Get task description from file
    task = ""
    if os.path.exists(focus_context_file):
        try:
            with open(focus_context_file, 'r', encoding='utf-8') as f:
                content = f.read()
            task_match = re.search(r"## Task\s*\n(.+?)(?=\n## |\Z)", content, re.DOTALL)
            if task_match:
                task = task_match.group(1).strip()
        except Exception:
            pass

    return {
        "task": task,
        "findings": context_data.get("findings", []),
        "issues": context_data.get("issues", []),
        "decisions": context_data.get("decisions", []),
        "plan_status": context_data.get("plan_status", {})
    }


# =============================================================================
# Archive Suggestions
# =============================================================================

def group_items_by_category(
    findings: List[Dict],
    issues: List[Dict],
    decisions: List[Dict]
) -> Dict[str, List[Dict]]:
    """Group all items by their Category field."""
    grouped = defaultdict(list)

    for item in findings:
        cat = item.get("Category", "").lower().strip()
        if cat:
            grouped[cat].append({"type": "finding", **item})

    for item in issues:
        cat = item.get("Category", "").lower().strip()
        if cat:
            grouped[cat].append({"type": "issue", **item})

    for item in decisions:
        cat = item.get("Category", "").lower().strip()
        if cat:
            grouped[cat].append({"type": "decision", **item})

    return dict(grouped)


def get_archive_target(category: str, project_path: str) -> Tuple[str, bool]:
    """Get archive target path for a category.

    Returns:
        (target_path, is_directory)
    """
    target = ARCHIVE_TARGETS.get(category, "")
    if not target:
        return "", False

    full_path = os.path.join(project_path, target)
    is_dir = target.endswith("/")

    return full_path, is_dir


def generate_archive_batches(
    grouped: Dict[str, List[Dict]],
    project_path: str
) -> List[Dict[str, Any]]:
    """Generate archive batches for confirmation."""
    batches = []
    batch_num = 0

    for category, items in grouped.items():
        target_path, is_dir = get_archive_target(category, project_path)

        # Split into batches if too many items
        for i in range(0, len(items), BATCH_SIZE):
            batch_items = items[i:i + BATCH_SIZE]
            batch_num += 1

            batches.append({
                "batch_num": batch_num,
                "category": category,
                "items": batch_items,
                "target_path": target_path,
                "is_directory": is_dir,
                "exists": os.path.exists(target_path) if target_path else False
            })

    return batches


# =============================================================================
# Pending Issues Analysis
# =============================================================================

def parse_pending_issues(project_path: str) -> List[Dict[str, Any]]:
    """Parse pending_issues.md into structured list."""
    pending_file = os.path.join(project_path, PENDING_ISSUES_FILE)
    issues = []

    if not os.path.exists(pending_file):
        return issues

    try:
        with open(pending_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse each issue block (### timestamp | tool | type)
        pattern = r"### (\d{4}-\d{2}-\d{2}T[\d:]+) \| (\w+) \| (\w+)\n(.*?)(?=\n### |\Z)"
        matches = re.findall(pattern, content, re.DOTALL)

        for timestamp, tool, issue_type, body in matches:
            issue = {
                "timestamp": timestamp,
                "tool": tool,
                "type": issue_type,
                "body": body.strip()
            }

            # Extract file/command from body
            file_match = re.search(r"\*\*File\*\*: `([^`]+)`", body)
            cmd_match = re.search(r"\*\*Command\*\*: `([^`]+)`", body)
            if file_match:
                issue["file"] = file_match.group(1)
            if cmd_match:
                issue["command"] = cmd_match.group(1)

            issues.append(issue)

    except Exception as e:
        if logger:
            logger.error("parse_pending_issues", e)

    return issues


def group_pending_issues(issues: List[Dict]) -> List[Dict[str, Any]]:
    """Group pending issues by tool and pattern."""
    groups = []

    # Group by tool first
    by_tool = defaultdict(list)
    for issue in issues:
        by_tool[issue["tool"]].append(issue)

    for tool, tool_issues in by_tool.items():
        if tool == "Bash":
            # Further group by command prefix
            by_prefix = defaultdict(list)
            for issue in tool_issues:
                cmd = issue.get("command", "")
                prefix = cmd.split()[0] if cmd else "unknown"
                by_prefix[prefix].append(issue)

            for prefix, prefix_issues in by_prefix.items():
                groups.append({
                    "tool": tool,
                    "subgroup": prefix,
                    "issues": prefix_issues,
                    "count": len(prefix_issues)
                })
        elif tool in ("Read", "Edit", "Write"):
            # Group by file
            by_file = defaultdict(list)
            for issue in tool_issues:
                file_path = issue.get("file", "unknown")
                by_file[file_path].append(issue)

            for file_path, file_issues in by_file.items():
                groups.append({
                    "tool": tool,
                    "subgroup": file_path,
                    "issues": file_issues,
                    "count": len(file_issues)
                })
        else:
            groups.append({
                "tool": tool,
                "subgroup": None,
                "issues": tool_issues,
                "count": len(tool_issues)
            })

    return groups


# =============================================================================
# Output Generation
# =============================================================================

def print_checkpoint_summary(result: Dict[str, Any]):
    """Print checkpoint phase summary."""
    lines = [
        "\n--- Checkpoint Summary ---",
        f"Sessions processed: {result['sessions_processed']}",
        f"Errors detected: {result['total_errors']}",
        f"Omissions detected: {result['total_omissions']}"
    ]
    output_message("checkpoint_summary", "\n".join(lines), "PostToolUse")


def print_session_summary(context: Dict[str, Any]):
    """Print session summary."""
    task = context.get('task', 'N/A')
    task_line = f"Task: {task[:100]}..." if len(task) > 100 else f"Task: {task}"
    plan = context.get("plan_status", {})

    lines = [
        "\n--- Session Summary ---",
        task_line,
        f"Completed phases: {plan.get('completed', 0)}/{plan.get('total', 0)}",
        f"\nFindings: {len(context.get('findings', []))} items",
        f"Issues: {len(context.get('issues', []))} items",
        f"Decisions: {len(context.get('decisions', []))} items"
    ]
    output_message("session_summary", "\n".join(lines), "PostToolUse")


def print_archive_batches(batches: List[Dict[str, Any]]):
    """Print archive suggestions."""
    lines = ["\n--- Archive Suggestions ---"]

    if not batches:
        lines.append("No items with Category field found.")
        output_message("archive_batches", "\n".join(lines), "PostToolUse")
        return

    for batch in batches:
        status = "[EXISTS]" if batch["exists"] else "[CREATE]"
        dir_indicator = " (scan dir)" if batch["is_directory"] else ""

        lines.append(f"\n[Batch {batch['batch_num']}] {batch['category']} ({len(batch['items'])} items)")
        lines.append(f"  Target: {batch['target_path']}{dir_indicator} {status}")

        for item in batch["items"]:
            item_type = item.get("type", "item")
            if item_type == "finding":
                lines.append(f"    - {item.get('Discovery', 'N/A')[:60]}")
            elif item_type == "issue":
                lines.append(f"    - {item.get('Issue', 'N/A')[:60]}")
            elif item_type == "decision":
                lines.append(f"    - {item.get('Decision', 'N/A')[:60]}")

    output_message("archive_batches", "\n".join(lines), "PostToolUse")


def print_pending_issues_analysis(groups: List[Dict[str, Any]]):
    """Print pending issues grouped analysis."""
    lines = []

    if not groups:
        lines.append("\n--- Pending Issues Analysis ---")
        lines.append("No pending issues to process.")
        output_message("pending_issues", "\n".join(lines), "PostToolUse")
        return

    total = sum(g["count"] for g in groups)
    lines.append(f"\n--- Pending Issues Analysis ({total} items) ---")

    for i, group in enumerate(groups, 1):
        subgroup = f" - {group['subgroup']}" if group["subgroup"] else ""
        lines.append(f"\n[Group {i}] {group['tool']}{subgroup} ({group['count']} items)")

        # Show sample issues
        for issue in group["issues"][:3]:
            error_preview = issue.get("body", "")[:50].replace("\n", " ")
            lines.append(f"    - {error_preview}...")

        if group["count"] > 3:
            lines.append(f"    ... and {group['count'] - 3} more")

    output_message("pending_issues", "\n".join(lines), "PostToolUse")


def print_required_instructions(
    batches: List[Dict[str, Any]],
    pending_groups: List[Dict[str, Any]],
    has_incomplete_phases: bool
):
    """Print [REQUIRED] instructions for AI."""
    lines = [
        "\n" + "=" * 50,
        "[REQUIRED] Follow these steps exactly:",
        "=" * 50
    ]

    step = 1

    # Incomplete phases warning
    if has_incomplete_phases:
        lines.append(f"\n{step}. VERIFY: Some phases are incomplete. Call AskUserQuestion:")
        lines.append('   - Question: "Some phases are not marked complete. Proceed with session closure?"')
        lines.append('   - Options: ["Proceed anyway", "Cancel and continue working"]')
        step += 1

    # Archive batches
    if batches:
        lines.append(f"\n{step}. ARCHIVE: For each batch above, call AskUserQuestion:")
        lines.append('   - Header: "Archive"')
        lines.append('   - Question: "Archive these items to [target]?"')
        lines.append('   - Options: ["Accept", "Edit destinations", "Skip all"]')
        lines.append("   After confirmation, write items to target files.")
        step += 1

    # Pending issues
    if pending_groups:
        lines.append(f"\n{step}. PENDING ISSUES: Analyze groups and call AskUserQuestion:")
        lines.append('   - Header: "Pending Issues"')
        lines.append('   - Question: "How to handle these pending issues?"')
        lines.append('   - Options: ["Archive patterns to troubleshooting", "Discard all", "Review individually"]')
        step += 1

    # Commit
    lines.append(f"\n{step}. COMMIT: Check for uncommitted changes and commit if needed.")
    step += 1

    # Cleanup
    lines.append(f"\n{step}. CLEANUP: Call AskUserQuestion:")
    lines.append('   - Header: "Cleanup"')
    lines.append('   - Question: "Delete focus session files?"')
    lines.append('   - Options: ["Yes, cleanup all", "No, keep files"]')
    lines.append("   If confirmed, delete:")
    lines.append(f"     - {FOCUS_DIR}/focus_context.md")
    lines.append(f"     - {FOCUS_DIR}/operations.jsonl")
    lines.append(f"     - {FOCUS_DIR}/action_count.json")
    lines.append(f"     - {FOCUS_DIR}/pending_issues.md")
    lines.append(f"     - {FOCUS_DIR}/current_session_id.txt")
    lines.append(f"     - {FOCUS_DIR}/current_session_source.txt")
    lines.append(f"     - {FOCUS_DIR}/focus_plugin_root.txt")
    lines.append(f"     - {FOCUS_DIR}/confirm_state.json")
    step += 1

    # Report
    lines.append(f"\n{step}. REPORT: Summarize to user what was accomplished.")

    output_message("required_instructions", "\n".join(lines), "PostToolUse")


# =============================================================================
# Main
# =============================================================================

def main():
    global logger, CONFIG, DONE_CONFIG, ARCHIVE_CONFIG, BATCH_SIZE, AUTO_CREATE, ARCHIVE_TARGETS

    parser = argparse.ArgumentParser(description='Complete focus session')
    parser.add_argument('--dry-run', action='store_true', help='Only show what would be done')
    args = parser.parse_args()

    dry_run = args.dry_run
    project_path = os.getcwd()

    # Reload config with project path
    CONFIG = load_config(project_path)
    DONE_CONFIG = CONFIG.get("done", {})
    ARCHIVE_CONFIG = DONE_CONFIG.get("archive", {})
    BATCH_SIZE = ARCHIVE_CONFIG.get("batch_size", 5)
    AUTO_CREATE = ARCHIVE_CONFIG.get("auto_create_missing_files", False)
    ARCHIVE_TARGETS = ARCHIVE_CONFIG.get("targets", {})

    # Initialize logger
    init_focus_env(project_path)
    log_dir = os.path.join(project_path, FOCUS_DIR)
    logger = Logger(CONFIG.get("logging", {}), log_dir)

    # Share logger with extract_session_info
    extract_session_info.logger = logger

    header = "=== FOCUS SESSION COMPLETION ==="
    if dry_run:
        header += "\n[DRY-RUN MODE]"
    output_message("focus_done_header", header, "PostToolUse")

    # 1. Checkpoint phase
    checkpoint_result = run_checkpoint_silent(project_path, dry_run)
    print_checkpoint_summary(checkpoint_result)

    # 2. Extract phase
    context = extract_focus_context(project_path)
    print_session_summary(context)

    # 3. Archive suggestions
    grouped = group_items_by_category(
        context.get("findings", []),
        context.get("issues", []),
        context.get("decisions", [])
    )
    batches = generate_archive_batches(grouped, project_path)
    print_archive_batches(batches)

    # 4. Pending issues analysis
    pending_issues = parse_pending_issues(project_path)
    pending_groups = group_pending_issues(pending_issues)
    print_pending_issues_analysis(pending_groups)

    # 5. Check for incomplete phases
    plan_status = context.get("plan_status", {})
    has_incomplete = plan_status.get("completed", 0) < plan_status.get("total", 0)

    # 6. Print [REQUIRED] instructions
    print_required_instructions(batches, pending_groups, has_incomplete)
    flush_output(as_json=False)


if __name__ == "__main__":
    main()
