"""Lightweight terminal progress helpers for long local LLM generation runs."""

from __future__ import annotations

import sys
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class ProgressTracker:
    """Print a simple progress bar after each generated scenario."""

    def __init__(self, total: int, *, label: str = "generation", enabled: bool = True, current: int = 0) -> None:
        self.total = max(total, 1)
        self.label = label
        self.enabled = enabled
        self.current = max(0, current)
        self.started = time.monotonic()
        if self.enabled:
            self.render(note="started")

    def increment(self, *, note: str = "") -> None:
        self.current += 1
        self.render(note=note)

    def render(self, *, note: str = "") -> None:
        if not self.enabled:
            return
        ratio = min(self.current / self.total, 1.0)
        width = 30
        done = int(width * ratio)
        bar = "#" * done + "-" * (width - done)
        elapsed = int(time.monotonic() - self.started)
        percent = ratio * 100
        suffix = f" | {note}" if note else ""
        print(f"[{self.label}] [{bar}] {self.current}/{self.total} ({percent:5.1f}%) elapsed={elapsed}s{suffix}", flush=True)


def run_with_heartbeat(
    label: str,
    fn: Callable[[], T],
    *,
    enabled: bool = True,
    heartbeat_seconds: int = 30,
) -> T:
    """Run a blocking callable while printing periodic heartbeat messages."""

    if not enabled:
        return fn()

    stop_event = threading.Event()
    started = time.monotonic()

    def heartbeat() -> None:
        while not stop_event.wait(max(1, heartbeat_seconds)):
            elapsed = int(time.monotonic() - started)
            print(f"[generating] {label} still running... elapsed={elapsed}s", file=sys.stderr, flush=True)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    print(f"[generating] {label} started", flush=True)
    try:
        return fn()
    finally:
        stop_event.set()
        thread.join(timeout=1)
        elapsed = int(time.monotonic() - started)
        print(f"[generating] {label} finished elapsed={elapsed}s", flush=True)
