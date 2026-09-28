"""Desktop notifications.

Text is handed to AppleScript as arguments, never spliced into the script, so a quote or
backslash in a task title can't break out and run code (the old prototype had that hole).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Protocol

log = logging.getLogger(__name__)

_SCRIPT = [
    "on run argv",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "end run",
]

Runner = Callable[[Sequence[str]], int]


class Notifier(Protocol):
    def notify(self, title: str, message: str) -> bool: ...


class NullNotifier:
    def notify(self, title: str, message: str) -> bool:
        return False


def _run(args: Sequence[str]) -> int:
    # Fixed executable and script; user text travels only as argv, never as code.
    return subprocess.run(  # noqa: S603
        list(args), capture_output=True, timeout=10, check=False
    ).returncode


class MacNotifier:
    def __init__(self, runner: Runner = _run) -> None:
        self.runner = runner

    def command(self, title: str, message: str) -> list[str]:
        args = ["/usr/bin/osascript"]
        for line in _SCRIPT:
            args += ["-e", line]
        return [*args, title[:120], message[:400]]

    def notify(self, title: str, message: str) -> bool:
        if sys.platform != "darwin" or not shutil.which("osascript"):
            return False
        try:
            return self.runner(self.command(title, message)) == 0
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("notification failed: %s", exc)
            return False
