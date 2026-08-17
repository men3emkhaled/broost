# -*- coding: utf-8 -*-
"""Last-resort diagnostics for failures that escape normal application handling."""

from __future__ import annotations

import os
import sys
import threading
import traceback
from datetime import datetime


_LOG_LOCK = threading.Lock()
_LOG_HANDLE = None
MAX_LOG_BYTES = 2 * 1024 * 1024


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log_path() -> str:
    return os.path.join(_base_dir(), "pos_runtime.log")


def _rotate_log(path: str) -> None:
    try:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_LOG_BYTES:
            previous = path + ".1"
            if os.path.exists(previous):
                os.remove(previous)
            os.replace(path, previous)
    except OSError:
        pass


def log_runtime_message(context: str, message: str) -> None:
    line = (
        f"{datetime.now().isoformat(timespec='seconds')} | {context} | "
        f"{str(message).strip()}\n"
    )
    with _LOG_LOCK:
        path = _log_path()
        _rotate_log(path)
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass


def log_exception(context: str, exc_type, exc_value, exc_traceback) -> None:
    rendered = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    ).strip()
    log_runtime_message(context, rendered)


def install_runtime_protection() -> None:
    """Record uncaught main-thread, worker-thread and native Python faults."""
    original_sys_hook = sys.excepthook

    def main_hook(exc_type, exc_value, exc_traceback):
        log_exception("unhandled-main-thread", exc_type, exc_value, exc_traceback)
        original_sys_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = main_hook

    original_thread_hook = getattr(threading, "excepthook", None)

    def thread_hook(args):
        log_exception(
            f"unhandled-worker:{getattr(args.thread, 'name', 'unknown')}",
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
        )
        if original_thread_hook:
            original_thread_hook(args)

    threading.excepthook = thread_hook

    try:
        import faulthandler

        global _LOG_HANDLE
        _LOG_HANDLE = open(_log_path(), "a", encoding="utf-8")
        faulthandler.enable(_LOG_HANDLE, all_threads=True)
    except (OSError, RuntimeError):
        pass
