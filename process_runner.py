"""Small cancellable subprocess runner shared by local long-running tasks."""

from __future__ import annotations

import subprocess
import tempfile
import time
from threading import Event
from typing import Sequence


class ProcessCancelled(RuntimeError):
    """The caller requested cancellation while the child process was running."""


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_process(
    command: Sequence[str],
    *,
    cwd: str,
    timeout: float,
    cancel_event: Event | None = None,
    stdin: object = subprocess.DEVNULL,
) -> subprocess.CompletedProcess[str]:
    """Run a local child process and stop it when timeout/cancellation arrives."""

    if cancel_event and cancel_event.is_set():
        raise ProcessCancelled("任务已取消。")

    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdin=stdin,
            stdout=stdout_file,
            stderr=stderr_file,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        def output() -> tuple[str, str]:
            stdout_file.seek(0)
            stderr_file.seek(0)
            return (
                stdout_file.read().decode("utf-8", errors="replace"),
                stderr_file.read().decode("utf-8", errors="replace"),
            )

        started = time.monotonic()
        while process.poll() is None:
            if cancel_event and cancel_event.is_set():
                _stop(process)
                raise ProcessCancelled("任务已取消。")
            if time.monotonic() - started >= timeout:
                _stop(process)
                stdout, stderr = output()
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
            time.sleep(0.2)

        stdout, stderr = output()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
