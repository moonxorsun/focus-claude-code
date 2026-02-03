#!/usr/bin/env python3
"""
Extract session information for /focus:done workflow.

Extracts Findings/Issues/Decisions from focus_context.md and
notable operations from operations.jsonl + transcript.

Usage:
    python extract_session_info.py [project-path]
"""

import io
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Fix Windows encoding
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from log_utils import Logger
from focus_core import (
    load_config, load_json_file, output_message as _output_message, flush_output,
    find_transcript_path, get_project_dir, load_operations,
    get_session_transcripts_from_operations,
    append_pending_issue, get_pending_issues_count, get_pending_issues_path,
    FOCUS_DIR, FOCUS_CONTEXT_FILE, OPERATIONS_FILE, CLAUDE_PROJECTS_DIR
)

CONFIG = load_config()  # Default only, will be reloaded in main() with project path

# Global logger instance (initialized in main)
logger: Logger = None

# Done settings (from config.done)
DONE_CONFIG = CONFIG.get("done", {})
ERROR_PATTERNS = DONE_CONFIG.get("error_patterns", [])
EDIT_TOOLS = DONE_CONFIG.get("edit_tools", [])
REPEATED_EDIT_THRESHOLD = DONE_CONFIG.get("repeated_edit_threshold", 3)
# =============================================================================


def output_message(tag: str, message: str, hook_event: str):
    """Print message to AI context and log to debug."""
    _output_message(tag, message, hook_event, logger)


def parse_markdown_table(content: str, header_pattern: str) -> List[Dict[str, str]]:
    """Parse a markdown table following a header pattern."""
    results = []

    # Find the section
    pattern = rf"(## {header_pattern}\s*\n)(.*?)(?=\n## |\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        return results

    section = match.group(2)
    lines = section.strip().split('\n')

    # Find table
    header_line = None
    header_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('|') and '|' in line[1:]:
            header_line = line
            header_idx = i
            break

    if header_line is None or header_idx + 2 >= len(lines):
        return results

    # Parse header
    headers = [h.strip() for h in header_line.split('|')[1:-1]]

    # Skip separator line, parse data rows
    for line in lines[header_idx + 2:]:
        if not line.startswith('|'):
            break
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) == len(headers) and any(c for c in cells):
            row = {headers[i]: cells[i] for i in range(len(headers))}
            results.append(row)

    return results


def parse_focus_context(file_path: str) -> Dict[str, Any]:
    """Extract Findings/Issues/Decisions tables from focus_context.md."""
    result = {
        "findings": [],
        "issues": [],
        "decisions": [],
        "plan_status": {"total": 0, "completed": 0, "phases": []}
    }

    if not os.path.exists(file_path):
        return result

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error("parse_focus_context", e)
        return result

    # Parse tables
    result["findings"] = parse_markdown_table(content, "Findings")
    result["issues"] = parse_markdown_table(content, "Issues")
    result["decisions"] = parse_markdown_table(content, "Decisions")

    # Parse plan checkboxes
    plan_match = re.search(r"## Plan\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    if plan_match:
        plan_section = plan_match.group(1)
        checkboxes = re.findall(r"- \[([ xX])\] (.+)", plan_section)
        for checked, text in checkboxes:
            is_complete = checked.lower() == 'x'
            result["plan_status"]["phases"].append({
                "text": text.strip(),
                "complete": is_complete
            })
            result["plan_status"]["total"] += 1
            if is_complete:
                result["plan_status"]["completed"] += 1

    return result


def build_transcript_index(transcript_path: Path) -> Dict[str, Dict]:
    """Build index of transcript entries by tool_use_id for efficient lookup.

    Returns dict mapping tool_use_id to:
        - tool_name: str
        - input: dict (file_path, command, etc.)
        - content: str (result content)
        - is_error: bool
    """
    index = {}
    if not transcript_path or not transcript_path.exists():
        return index

    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    msg_type = data.get('type')
                    message = data.get('message', {})
                    content = message.get('content', []) if isinstance(message, dict) else []

                    if not isinstance(content, list):
                        continue

                    # tool_use is in assistant.message.content[]
                    if msg_type == 'assistant':
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'tool_use':
                                tool_use_id = c.get('id')
                                if tool_use_id:
                                    index[tool_use_id] = {
                                        'tool_name': c.get('name', ''),
                                        'input': c.get('input', {}),
                                        'content': '',
                                        'is_error': False
                                    }

                    # tool_result is in user.message.content[]
                    elif msg_type == 'user':
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'tool_result':
                                tool_use_id = c.get('tool_use_id')
                                if tool_use_id:
                                    if tool_use_id in index:
                                        index[tool_use_id]['content'] = c.get('content', '')
                                        index[tool_use_id]['is_error'] = c.get('is_error', False)
                                    else:
                                        index[tool_use_id] = {
                                            'tool_name': '',
                                            'input': {},
                                            'content': c.get('content', ''),
                                            'is_error': c.get('is_error', False)
                                        }
                except json.JSONDecodeError as e:
                    logger.error("build_transcript_index.json_parse", e)
    except Exception as e:
        logger.error("build_transcript_index", e)

    return index


def find_notable_operations(transcript_index: Dict[str, Dict], operations: List[Dict]) -> List[Dict]:
    """
    Find notable operations:
    - Failed tool calls (error in response)
    - Repeated operations (same file edited multiple times)
    """
    notable = []
    file_edit_counts: Dict[str, int] = {}

    for op in operations:
        ids = op.get('ids', {})
        tool_name = ids.get('tool_name')
        tool_use_id = ids.get('tool_use_id')

        if not tool_use_id:
            continue

        # Get from index (O(1) lookup)
        result = transcript_index.get(tool_use_id)
        if not result:
            continue

        # Extract file_path and command from input
        tool_input = result.get('input', {})
        file_path = tool_input.get('file_path', '')
        command = tool_input.get('command', '')

        # Check for errors using is_error field (set by Claude Code)
        is_error = result.get('is_error', False)
        if is_error:
            result_content = result.get('content', '')
            issue = {
                "type": "failed",
                "tool": tool_name,
                "tool_use_id": tool_use_id,
                "timestamp": op.get('ts'),
                "snippet": str(result_content)[:300]
            }
            if file_path:
                issue["file_path"] = file_path
            if command:
                issue["command"] = command[:200]
            notable.append(issue)

        # Track file edits
        if tool_name in EDIT_TOOLS:
            edit_path = file_path or ids.get('file_path') or op.get('file_path', '')
            if edit_path:
                file_edit_counts[edit_path] = file_edit_counts.get(edit_path, 0) + 1

    # Report repeated edits
    for file_path, count in file_edit_counts.items():
        if count >= REPEATED_EDIT_THRESHOLD:
            notable.append({
                "type": "repeated_edit",
                "file": file_path,
                "count": count,
                "note": "Multiple edits may indicate iteration or debugging"
            })

    return notable


def get_session_times(operations: List[Dict]) -> Dict[str, str]:
    """Get session start and end times."""
    times = {"start": None, "end": None}

    if operations:
        times["start"] = operations[0].get('ts')
        times["end"] = operations[-1].get('ts')

    return times


def count_operations_by_tool(operations: List[Dict]) -> Dict[str, int]:
    """Count operations by tool name."""
    counts = {}
    for op in operations:
        tool = op.get('ids', {}).get('tool_name', 'Unknown')
        if tool:
            counts[tool] = counts.get(tool, 0) + 1
    return counts


def generate_summary(project_path: str) -> Dict[str, Any]:
    """Generate complete session information summary."""
    logger.info("generate_summary", f"Generating summary for {project_path}")
    focus_file = os.path.join(project_path, FOCUS_CONTEXT_FILE)
    ops_file = os.path.join(project_path, OPERATIONS_FILE)

    # Parse focus context
    context = parse_focus_context(focus_file)
    logger.debug("generate_summary", f"Parsed context: {len(context.get('findings', []))} findings, {len(context.get('issues', []))} issues")

    # Load operations
    operations = load_operations(ops_file)
    logger.debug("generate_summary", f"Loaded {len(operations)} operations")

    # Get all session transcripts from operations
    session_transcripts = get_session_transcripts_from_operations(operations, project_path)
    logger.debug("generate_summary", f"Found {len(session_transcripts)} sessions")

    # Build combined transcript index from all sessions
    transcript_index = {}
    transcript_paths = []
    for sid, transcript_path in session_transcripts:
        if transcript_path:
            transcript_paths.append(str(transcript_path))
            index = build_transcript_index(transcript_path)
            transcript_index.update(index)
    logger.debug("generate_summary", f"Built transcript index with {len(transcript_index)} entries")

    # Find notable operations
    notable = find_notable_operations(transcript_index, operations)

    # Auto-write notable operations to pending_issues.md
    if notable:
        # Get session_id from first operation with one
        default_session = ''
        for op in operations[-10:]:  # Check recent operations
            sid = op.get('ids', {}).get('session_id')
            if sid:
                default_session = sid
                break

        for issue in notable:
            issue['session_id'] = issue.get('session_id', default_session)
            append_pending_issue(issue, project_path, logger)

    # Build summary
    summary = {
        "session": {
            "times": get_session_times(operations),
            "total_operations": len(operations),
            "by_tool": count_operations_by_tool(operations),
            "transcript_count": len(session_transcripts),
            "transcripts": transcript_paths
        },
        "plan_status": context["plan_status"],
        "findings": context["findings"],
        "issues": context["issues"],
        "decisions": context["decisions"],
        "notable_operations": notable
    }

    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    """Print summary in human-readable format."""
    logger.info("print_summary", "Printing session summary")

    # Log full summary to verbose
    import json as json_module
    logger.verbose("done_summary", json_module.dumps(summary, indent=2, ensure_ascii=False, default=str))

    parts = []
    parts.append("=" * 60)
    parts.append("SESSION INFORMATION SUMMARY")
    parts.append("=" * 60)

    # Session info
    session = summary["session"]
    parts.append(f"\n## Session")
    parts.append(f"Operations: {session['total_operations']}")
    parts.append(f"Start: {session['times'].get('start', 'N/A')}")
    parts.append(f"End: {session['times'].get('end', 'N/A')}")

    if session['by_tool']:
        tools_str = ", ".join(f"{k}x{v}" for k, v in session['by_tool'].items())
        parts.append(f"Tools: {tools_str}")

    # Plan status
    plan = summary["plan_status"]
    parts.append(f"\n## Plan Status: {plan['completed']}/{plan['total']} complete")
    for phase in plan["phases"]:
        status = "[x]" if phase["complete"] else "[ ]"
        parts.append(f"  {status} {phase['text']}")

    # Findings
    if summary["findings"]:
        parts.append(f"\n## Findings ({len(summary['findings'])} items)")
        for f in summary["findings"]:
            parts.append(f"  - [{f.get('Type', 'N/A')}] {f.get('Discovery', 'N/A')}")

    # Issues
    if summary["issues"]:
        parts.append(f"\n## Issues ({len(summary['issues'])} items)")
        for i in summary["issues"]:
            parts.append(f"  - {i.get('Issue', 'N/A')}: {i.get('Resolution', 'N/A')}")

    # Decisions
    if summary["decisions"]:
        parts.append(f"\n## Decisions ({len(summary['decisions'])} items)")
        for d in summary["decisions"]:
            parts.append(f"  - {d.get('Decision', 'N/A')}")

    # Notable operations
    if summary["notable_operations"]:
        parts.append(f"\n## Notable Operations ({len(summary['notable_operations'])} items)")
        for n in summary["notable_operations"]:
            if n["type"] == "failed":
                parts.append(f"  - [FAILED] {n['tool']}: {n.get('snippet', '')[:100]}...")
            elif n["type"] == "repeated_edit":
                parts.append(f"  - [REPEATED] {n['file']} edited {n['count']} times")

    # Pending issues (for done workflow)
    pending_count = get_pending_issues_count()
    if pending_count > 0:
        pending_file = get_pending_issues_path()
        parts.append(f"\n## Pending Issues: {pending_count} items")
        parts.append(f"  Review and process before completing session: {pending_file}")

    parts.append("\n" + "=" * 60)

    output_message("session_summary", "\n".join(parts), "PostToolUse")

    # Also output JSON for programmatic use
    json_output = "\n## JSON Output\n" + json.dumps(summary, indent=2, ensure_ascii=False, default=str)
    output_message("session_json", json_output, "PostToolUse")


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
    logger.info("init", "extract_session_info.py started")

    summary = generate_summary(project_path)
    print_summary(summary)
    flush_output(as_json=False)


if __name__ == '__main__':
    main()
