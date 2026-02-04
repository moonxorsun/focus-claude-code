#!/usr/bin/env python3
"""
Focus Plugin Install Script

Replaces {{FOCUS_PLUGIN_ROOT}} placeholders with actual plugin path.
Called automatically by Claude Code's SessionStart hook.
Uses .installed marker file for idempotency.
"""
import json
import os
import glob

PLACEHOLDER = "{{FOCUS_PLUGIN_ROOT}}"
MARKER_FILE = ".installed"


def _output_json(message: str, is_error: bool = False):
    """Output message in Claude Code hook JSON format."""
    if is_error:
        output = {"decision": "block", "reason": message}
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": message
            }
        }
    print(json.dumps(output))


def get_plugin_root():
    """Get the directory containing this script."""
    return os.path.dirname(os.path.abspath(__file__))


def check_marker(plugin_root):
    """Check if marker file exists and matches current plugin_root."""
    marker_path = os.path.join(plugin_root, MARKER_FILE)
    if not os.path.exists(marker_path):
        return False
    try:
        with open(marker_path, 'r', encoding='utf-8') as f:
            stored_root = f.read().strip()
        return stored_root == plugin_root
    except Exception:
        return False


def write_marker(plugin_root):
    """Write marker file with current plugin_root."""
    marker_path = os.path.join(plugin_root, MARKER_FILE)
    try:
        with open(marker_path, 'w', encoding='utf-8') as f:
            f.write(plugin_root)
    except Exception as e:
        _output_json(f"Warning: Could not write marker file: {e}", is_error=False)


def replace_in_file(file_path, plugin_root):
    """Replace {{FOCUS_PLUGIN_ROOT}} with actual path in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if PLACEHOLDER not in content:
            return False

        new_content = content.replace(PLACEHOLDER, plugin_root)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return True
    except Exception as e:
        _output_json(f"Error processing {file_path}: {e}", is_error=True)
        return False


def main():
    plugin_root = get_plugin_root()

    if check_marker(plugin_root):
        return

    patterns = [
        os.path.join(plugin_root, "skills", "**", "*.md"),
        os.path.join(plugin_root, "commands", "*.md"),
    ]

    modified_count = 0
    for pattern in patterns:
        for file_path in glob.glob(pattern, recursive=True):
            if replace_in_file(file_path, plugin_root):
                modified_count += 1

    write_marker(plugin_root)

    if modified_count > 0:
        msg = f"""Focus plugin: {modified_count} files updated

[IMPORTANT] Tell the user: Focus plugin installed successfully!
Please restart Claude Code (exit and re-enter) to use the plugin properly."""
        _output_json(msg)


if __name__ == "__main__":
    main()
