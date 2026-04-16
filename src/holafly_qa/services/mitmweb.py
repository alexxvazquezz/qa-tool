"""mitmweb process management — start, stop, check status."""

import os
import signal
import subprocess
import time
from pathlib import Path

from holafly_qa.services.process import (
    clear_pid,
    is_process_running,
    load_pid,
    save_pid,
)

MITMWEB_PID_NAME = "mitmweb"
LOG_FILE = Path.home() / ".holafly-qa" / "mitmweb.log"


def start_mitmweb(
    port: int = 8080,
    ignore_hosts: str = ".*adyen.*",
    script: Path | None = None,
) -> int:
    """Start mitmweb in the background with the right flags.

    Spawns mitmweb detached from the current terminal so it keeps
    running after qa-tool exits. Captures stdout and stderr to a log
    file so users can debug if something goes wrong. Records the PID
    so a later 'stop' command can find and kill it.

    Args:
        port: Port for mitmproxy to listen on.
        ignore_hosts: Regex of hosts to pass through without TLS
            interception (default bypasses Adyen to avoid pinning).
        script: Optional path to a mitmproxy addon script for
            failure injection.

    Returns:
        The PID of the spawned mitmweb process.

    Raises:
        RuntimeError: If mitmweb is already running (per PID file).
        FileNotFoundError: If the mitmweb binary is not on PATH.
    """
    existing_pid = load_pid(MITMWEB_PID_NAME)
    if existing_pid is not None and is_process_running(existing_pid):
        raise RuntimeError(
            f"mitmweb is already running (PID {existing_pid}). "
            f"Run 'qa-tool mitmweb stop' first."
        )

    if existing_pid is not None:
        clear_pid(MITMWEB_PID_NAME)

    cmd = [
        "mitmweb",
        "--listen-port",
        str(port),
        "--set",
        f"ignore_hosts={ignore_hosts}",
    ]
    if script is not None:
        cmd.extend(["-s", str(script)])

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(LOG_FILE, "w")

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    save_pid(MITMWEB_PID_NAME, process.pid)
    return process.pid


def is_mitmweb_running() -> bool:
    """Return True if mitmweb is currently running per the PID file."""
    pid = load_pid(MITMWEB_PID_NAME)
    if pid is None:
        return False
    return is_process_running(pid)


def stop_mitmweb() -> bool:
    """Stop a running mitmweb process cleanly.

    Sends SIGTERM first, waits up to 5 seconds for graceful exit, then
    escalates to SIGKILL if the process is still alive. Always clears
    the PID file at the end, even if the process was already dead.

    Returns:
        True if mitmweb was running and has been stopped.
        False if mitmweb was not running (nothing to do).
    """
    pid = load_pid(MITMWEB_PID_NAME)

    if pid is None:
        return False

    if not is_process_running(pid):
        clear_pid(MITMWEB_PID_NAME)
        return False

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        clear_pid(MITMWEB_PID_NAME)
        return True

    for _ in range(50):
        if not is_process_running(pid):
            clear_pid(MITMWEB_PID_NAME)
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    clear_pid(MITMWEB_PID_NAME)
    return True