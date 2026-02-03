#!/usr/bin/env python3
"""
Unified logging utilities for focus plugin.

Log levels (cumulative):
- ERROR: Only errors, permanently retained
- INFO: Errors + info, info rotated at 1000 lines
- DEBUG: Errors + info + debug + verbose files

Usage:
    from log_utils import Logger
    logger = Logger(config, log_dir)
    logger.error("func_name", "error message")
    logger.info("func_name", "info message")
    logger.debug("func_name", "debug message")
    logger.verbose("filename", "large content")
"""

import inspect
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from typing import Optional


def _fatal_error(message: str):
    """Output fatal error in JSON format and exit. Used during early init."""
    output = {"decision": "block", "reason": f"[FATAL] {message}"}
    print(json.dumps(output))
    sys.exit(2)


class Logger:
    """Unified logger for focus plugin."""

    LEVELS = {"ERROR": 0, "INFO": 1, "DEBUG": 2}

    def __init__(self, config: dict, log_dir: str):
        logging_config = config.get("logging", {})
        self.level = self.LEVELS.get(logging_config.get("level", "INFO").upper(), 1)
        self.rotate_lines = logging_config.get("rotate_lines", 1000)
        self.log_dir = log_dir
        self.logs_dir = os.path.join(log_dir, "logs")
        self.verbose_dir = os.path.join(self.logs_dir, "verbose")

    def _ensure_dir(self, path: str) -> None:
        """Ensure directory exists."""
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def _atomic_write(self, filepath: str, content: str) -> None:
        """Atomically write content to file using temp+rename with retry."""
        max_retries = 3
        retry_delay = 0.1

        try:
            self._ensure_dir(filepath)
            dir_path = os.path.dirname(filepath) or "."
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)

                last_error = None
                for attempt in range(max_retries):
                    try:
                        os.replace(tmp_path, filepath)
                        return
                    except PermissionError as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)

                raise last_error
            except:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise
        except Exception as e:
            _fatal_error(f"_atomic_write failed: {filepath}: {e}")

    def _format_msg(self, func_name: str, msg: str) -> str:
        """Format log message with timestamp and caller location."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Get caller info: 0=_format_msg, 1=error/info/debug, 2=actual caller
        frame = inspect.currentframe()
        try:
            caller = frame.f_back.f_back  # Skip error/info/debug method
            filename = os.path.basename(caller.f_code.co_filename)
            lineno = caller.f_lineno
            return f"[{ts}] {filename}:{lineno} {func_name}: {msg}\n"
        finally:
            del frame

    def _append(self, filepath: str, content: str) -> None:
        """Atomically append content to file."""
        try:
            self._ensure_dir(filepath)
            existing = ""
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = f.read()
            self._atomic_write(filepath, existing + content)
        except Exception as e:
            _fatal_error(f"_append failed: {filepath}: {e}")

    def _append_with_rotate(self, filepath: str, content: str) -> None:
        """Atomically append content and rotate if exceeds limit."""
        try:
            self._ensure_dir(filepath)

            # Read existing lines
            lines = []
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()

            # Add new content
            lines.append(content)

            # Rotate if needed
            if len(lines) > self.rotate_lines:
                lines = lines[-self.rotate_lines:]

            # Atomic write
            self._atomic_write(filepath, "".join(lines))
        except Exception as e:
            _fatal_error(f"_append_with_rotate failed: {filepath}: {e}")

    def _overwrite(self, filepath: str, content: str) -> None:
        """Atomically overwrite file with content."""
        try:
            self._ensure_dir(filepath)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = f"===== {ts} =====\n"
            self._atomic_write(filepath, header + content)
        except Exception as e:
            _fatal_error(f"_overwrite failed: {filepath}: {e}")

    def error(self, func_name: str, msg: str) -> None:
        """Log error message with traceback. Always logged."""
        # Get traceback if in exception context
        tb = traceback.format_exc()
        if tb and tb.strip() != "NoneType: None":
            full_msg = f"{msg}\n{tb}"
        else:
            full_msg = str(msg)
        filepath = os.path.join(self.logs_dir, "error.log")
        self._append(filepath, self._format_msg(func_name, full_msg))

    def info(self, func_name: str, msg: str) -> None:
        """Log info message. Logged if level >= INFO."""
        if self.level < self.LEVELS["INFO"]:
            return
        filepath = os.path.join(self.logs_dir, "info.log")
        self._append_with_rotate(filepath, self._format_msg(func_name, msg))

    def debug(self, func_name: str, msg: str) -> None:
        """Log debug message. Logged if level >= DEBUG."""
        if self.level < self.LEVELS["DEBUG"]:
            return
        filepath = os.path.join(self.logs_dir, "debug.log")
        self._append(filepath, self._format_msg(func_name, msg))

    def verbose(self, filename: str, content: str) -> None:
        """Log verbose content to separate file. Only in DEBUG mode."""
        if self.level < self.LEVELS["DEBUG"]:
            return
        filepath = os.path.join(self.verbose_dir, f"{filename}.log")
        self._overwrite(filepath, content)


