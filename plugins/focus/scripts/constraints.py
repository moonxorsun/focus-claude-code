#!/usr/bin/env python3
"""
Constraint checking module for focus plugin.

Provides configurable code quality constraints that can warn or block operations.
"""

import os
import re
from typing import Dict, Optional, Tuple


def check_line_limit(
    content: str,
    config: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Check if content exceeds line limit.

    Args:
        content: The content to check (new_string or content)
        config: Rule config with 'threshold' key

    Returns:
        (passed, message) - passed=True means no issue
    """
    threshold = config.get("threshold", 100)
    line_count = content.count('\n') + 1

    if line_count > threshold:
        return False, f"Modification exceeds {threshold} lines (actual: {line_count}), consider splitting into smaller changes"

    return True, None


def check_no_tabs(
    content: str,
    file_path: str,
    config: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Check if content contains tab characters.

    Args:
        content: The content to check
        file_path: Path to the file being modified
        config: Rule config with 'extensions' key

    Returns:
        (passed, message) - passed=True means no issue
    """
    extensions = config.get("extensions", [".gd", ".py", ".cpp", ".h", ".hpp", ".tscn", ".tres"])

    # Check if file extension matches
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in extensions:
        return True, None

    if '\t' in content:
        return False, "Tab characters detected, use spaces for indentation"

    return True, None


def check_no_backslash_path(
    command: str,
    config: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Check if command contains backslash path separators.

    Args:
        command: The bash command to check
        config: Rule config

    Returns:
        (passed, message) - passed=True means no issue
    """
    # Skip sed/awk commands (regex patterns often use backslash)
    if re.match(r'^\s*(sed|awk)\s', command):
        return True, None

    # Match backslash that is NOT part of escape sequences
    # Exclude: \n \t \r \\ \" \' \0 (and the backslash before them)
    # Strategy: remove all valid escapes, then check for remaining backslashes
    # Valid escapes: \\ \n \t \r \" \' \0
    cleaned = re.sub(r'\\\\', '', command)  # Remove \\
    cleaned = re.sub(r'\\[ntr"\'0]', '', cleaned)  # Remove \n \t \r \" \' \0

    if '\\' in cleaned:
        return False, "Backslash path detected, use forward slash / instead"

    return True, None


def check_no_powershell(
    command: str,
    config: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Check if command uses PowerShell-specific commands.

    Args:
        command: The bash command to check
        config: Rule config with 'patterns' list

    Returns:
        (passed, message) - passed=True means no issue
    """
    # Get patterns from config, with defaults
    ps_patterns = config.get("patterns", [
        r'\bGet-ChildItem\b',
        r'\bSelect-String\b',
        r'\bGet-Content\b',
        r'\bSet-Location\b',
        r'\bNew-Item\b',
        r'\bRemove-Item\b',
        r'\bWrite-Host\b',
        r'\bInvoke-WebRequest\b',
        r'\bInvoke-Expression\b',
    ])

    for pattern in ps_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False, "PowerShell commands not allowed, use Git Bash instead"

    # Check for .\script pattern (PowerShell script invocation)
    if config.get("check_dot_backslash", True):
        if re.match(r'^\s*\.\\', command):
            return False, "PowerShell commands not allowed, use Git Bash instead"

    return True, None


def check_no_bash_file_ops(
    command: str,
    config: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Check if command uses bash file operations that should use dedicated tools.

    Args:
        command: The bash command to check
        config: Rule config

    Returns:
        (passed, message) - passed=True means no issue
    """
    # Skip if heredoc is used (cat <<EOF is allowed)
    if '<<' in command:
        return True, None

    # File operation patterns and their recommended tools
    # Format: (pattern, tool_name, cmd_name)
    file_ops = [
        (r'^\s*cat\s+[^|<]', 'Read', 'cat'),
        (r'^\s*head\s', 'Read', 'head'),
        (r'^\s*tail\s', 'Read', 'tail'),
        (r'^\s*grep\s', 'Grep', 'grep'),
        (r'^\s*rg\s', 'Grep', 'rg'),
        (r'^\s*find\s+\S+\s+.*-name', 'Glob', 'find'),
    ]

    for pattern, tool, cmd in file_ops:
        if re.search(pattern, command):
            return False, f"Consider using {tool} tool instead of {cmd} command"

    # Check for grep in pipe - this is allowed, so check if grep is NOT after a pipe
    # Already handled above - grep at start of command triggers, grep after | is fine

    return True, None


def check_no_hardcoded_path(
    content: str,
    file_path: str,
    config: Dict
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if content contains hardcoded paths based on configurable rules.

    Args:
        content: The content to check
        file_path: Path to the file being modified
        config: Rule config with 'rules' list

    Returns:
        (passed, message, action) - passed=True means no issue
    """
    rules = config.get("rules", [])
    _, ext = os.path.splitext(file_path)
    ext_lower = ext.lower()

    for rule in rules:
        extensions = rule.get("extensions", [])
        if ext_lower not in extensions:
            continue

        regex = rule.get("regex", "")
        if not regex:
            continue

        if re.search(regex, content):
            message = rule.get("message", "Hardcoded path detected")
            action = rule.get("action", "warn")
            return False, message, action

    return True, None, None


def is_snake_case(name: str) -> bool:
    """Check if name follows snake_case convention."""
    return bool(re.match(r'^[a-z][a-z0-9_]*$', name))


def is_all_uppercase(name: str) -> bool:
    """Check if name is all uppercase (like LICENSE, README)."""
    return bool(re.match(r'^[A-Z][A-Z0-9_]*$', name))


def check_snake_case_naming(
    file_path: str,
    config: Dict
) -> Tuple[bool, Optional[str]]:
    """
    Check if file and directory names follow snake_case convention.

    Args:
        file_path: Path to the file being created
        config: Rule config

    Returns:
        (passed, message) - passed=True means no issue
    """
    extensions = config.get("extensions", [".gd", ".tscn", ".tres", ".py", ".cpp", ".h", ".hpp"])
    exclude_files = config.get("exclude_files", ["CLAUDE.md", "README.md", "CHANGELOG.md", "LICENSE"])
    check_dirs = config.get("check_dirs", True)

    # Normalize path separators
    normalized_path = file_path.replace("\\", "/")
    parts = normalized_path.split("/")
    filename = parts[-1] if parts else ""

    # Check if file should be excluded
    if filename in exclude_files or filename.startswith('.'):
        return True, None

    # Check file extension
    name, ext = os.path.splitext(filename)
    if ext.lower() not in extensions:
        return True, None

    # Allow all uppercase names (like LICENSE, README)
    if is_all_uppercase(name):
        return True, None

    # Check filename
    if not is_snake_case(name):
        return False, f"Filename '{filename}' does not follow snake_case convention"

    # Check directory names if enabled
    if check_dirs:
        exclude_dirs = {'.claude', '.git', '.godot', 'node_modules', '__pycache__'}
        for part in parts[:-1]:  # Exclude filename
            if not part or part in exclude_dirs or part.startswith('.'):
                continue
            # Allow all uppercase directory names
            if is_all_uppercase(part):
                continue
            if not is_snake_case(part):
                return False, f"Directory name '{part}' does not follow snake_case convention"

    return True, None


def check_constraints(
    tool_name: str,
    tool_input: Dict,
    config: Dict,
    logger=None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Run all enabled constraint checks.

    Args:
        tool_name: Name of the tool (Edit, Write, Bash)
        tool_input: Tool input parameters
        config: Full constraints config block
        logger: Optional logger instance

    Returns:
        (allowed, message, action) - allowed=False means should block/warn
        action is one of: 'remind', 'warn', 'block'
    """
    if not config.get("enabled", False):
        return True, None, None

    rules = config.get("rules", {})

    # Get content based on tool type
    content = ""
    file_path = ""
    command = ""

    if tool_name in ("Edit", "Write"):
        content = tool_input.get("new_string") or tool_input.get("content", "")
        file_path = tool_input.get("file_path", "")
    elif tool_name == "Bash":
        command = tool_input.get("command", "")

    # Check line_limit (Edit, Write)
    rule_config = rules.get("line_limit", {})
    if rule_config.get("enabled", False) and tool_name in ("Edit", "Write") and content:
        passed, message = check_line_limit(content, rule_config)
        if not passed:
            action = rule_config.get("action", "warn")
            if logger:
                logger.debug("constraints", f"line_limit triggered: {message}")
            return False, message, action

    # Check no_tabs (Edit, Write)
    rule_config = rules.get("no_tabs", {})
    if rule_config.get("enabled", False) and tool_name in ("Edit", "Write") and content:
        passed, message = check_no_tabs(content, file_path, rule_config)
        if not passed:
            action = rule_config.get("action", "block")
            if logger:
                logger.debug("constraints", f"no_tabs triggered: {message}")
            return False, message, action

    # Check no_hardcoded_path (Edit, Write)
    rule_config = rules.get("no_hardcoded_path", {})
    if rule_config.get("enabled", False) and tool_name in ("Edit", "Write") and content:
        passed, message, action = check_no_hardcoded_path(content, file_path, rule_config)
        if not passed:
            if logger:
                logger.debug("constraints", f"no_hardcoded_path triggered: {message}")
            return False, message, action

    # Check snake_case_naming (Write only)
    rule_config = rules.get("snake_case_naming", {})
    if rule_config.get("enabled", False) and tool_name == "Write" and file_path:
        passed, message = check_snake_case_naming(file_path, rule_config)
        if not passed:
            action = rule_config.get("action", "block")
            if logger:
                logger.debug("constraints", f"snake_case_naming triggered: {message}")
            return False, message, action

    # Check no_backslash_path (Bash)
    rule_config = rules.get("no_backslash_path", {})
    if rule_config.get("enabled", False) and tool_name == "Bash" and command:
        passed, message = check_no_backslash_path(command, rule_config)
        if not passed:
            action = rule_config.get("action", "warn")
            if logger:
                logger.debug("constraints", f"no_backslash_path triggered: {message}")
            return False, message, action

    # Check no_powershell (Bash)
    rule_config = rules.get("no_powershell", {})
    if rule_config.get("enabled", False) and tool_name == "Bash" and command:
        passed, message = check_no_powershell(command, rule_config)
        if not passed:
            action = rule_config.get("action", "block")
            if logger:
                logger.debug("constraints", f"no_powershell triggered: {message}")
            return False, message, action

    # Check no_bash_file_ops (Bash)
    rule_config = rules.get("no_bash_file_ops", {})
    if rule_config.get("enabled", False) and tool_name == "Bash" and command:
        passed, message = check_no_bash_file_ops(command, rule_config)
        if not passed:
            action = rule_config.get("action", "warn")
            if logger:
                logger.debug("constraints", f"no_bash_file_ops triggered: {message}")
            return False, message, action

    return True, None, None


def format_constraint_message(message: str, action: str) -> str:
    """Format constraint message with appropriate prefix."""
    if action == "block":
        return f"[BLOCK] {message}"
    elif action == "warn":
        return f"[WARN] {message}"
    else:  # remind
        return f"[REMIND] {message}"
