# -*- coding: utf-8 -*-
"""Small external guard that restarts the POS after an abnormal process exit."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from datetime import datetime


MAX_RESTARTS = 3
RESTART_WINDOW_SECONDS = 120
MAX_LOG_BYTES = 2 * 1024 * 1024


def base_dir() -> str:
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)


def should_restart(exit_code: int, recent_restarts: list[float], now: float) -> bool:
    if exit_code == 0:
        return False
    recent_restarts[:] = [
        stamp for stamp in recent_restarts
        if now - stamp <= RESTART_WINDOW_SECONDS
    ]
    return len(recent_restarts) < MAX_RESTARTS


def log_guard(message: str) -> None:
    path = os.path.join(base_dir(), "pos_runtime.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_LOG_BYTES:
            previous = path + ".1"
            if os.path.exists(previous):
                os.remove(previous)
            os.replace(path, previous)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(
                f"{datetime.now().isoformat(timespec='seconds')} | process-guard | {message}\n"
            )
    except OSError:
        pass


def show_failure_message() -> None:
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "البرنامج توقف أكثر من مرة خلال دقيقتين.\n"
            "تم إيقاف إعادة التشغيل لحماية الجهاز.\n\n"
            "افتح نظام الكاشير مرة أخرى، وإذا تكرر الأمر أرسل ملف pos_runtime.log.",
            "تعذر استعادة نظام الكاشير تلقائيًا",
            0x10,
        )
    except Exception:
        pass


def main() -> int:
    app_path = os.path.join(base_dir(), "BroostPOS.exe")
    if not os.path.isfile(app_path):
        log_guard(f"missing executable: {app_path}")
        show_failure_message()
        return 2

    recent_restarts: list[float] = []
    while True:
        try:
            process = subprocess.Popen([app_path], cwd=base_dir())
            exit_code = int(process.wait())
        except OSError as exc:
            log_guard(f"could not launch POS: {exc}")
            show_failure_message()
            return 3

        now = time.monotonic()
        if not should_restart(exit_code, recent_restarts, now):
            if exit_code != 0:
                log_guard(
                    f"restart circuit opened after {len(recent_restarts)} attempts; exit={exit_code}"
                )
                show_failure_message()
            return exit_code

        recent_restarts.append(now)
        log_guard(f"POS exited abnormally with code {exit_code}; restarting")
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
