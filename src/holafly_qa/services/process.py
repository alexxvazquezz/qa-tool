"""Generic process management helpers.

Provides PID file tracking and process-alive checks so we can spawn
background processes (mitmweb, emulator) from one CLI invocation and
stop them from a later one. PID files live under ~/.holafly-qa/.
"""

from pathlib import Path
import os

PID_DIR = Path.home() / ".holafly-qa"


def get_pid_file(name: str) -> Path:
    """Return the PID file path for a named process (e.g. 'mitmweb')."""
    return PID_DIR / f"{name}.pid"


def save_pid(name: str, pid: int) -> None:
    """Write a process's PID to its named PID file."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_file = get_pid_file(name)
    pid_file.write_text(str(pid))


def load_pid(name: str) -> int | None:
    """Read a PID from a named PID file, or None if no file exists."""
    pid_file = get_pid_file(name)
    if not pid_file.exists():
        return None

    try:
        return int(pid_file.read_text().strip())
    except ValueError:
        # File exists but contains garbage (e.g. empty or corrupted)
        return None


def clear_pid(name: str) -> None:
    """Delete a named PID file. No-op if it doesn't exist."""
    pid_file = get_pid_file(name)
    if pid_file.exists():
        pid_file.unlink()

def is_process_running(pid: int) -> bool:
    """Check whether a process with the given PID is currently alive.

    Uses os.kill with signal 0, which doesn't actually send a signal —
    it's the standard Unix idiom for "does this process exist and am
    I allowed to signal it." Returns False for dead/nonexistent PIDs.
    """
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True