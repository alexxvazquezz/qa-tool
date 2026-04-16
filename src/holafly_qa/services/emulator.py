"""Emulator process management — start, stop, boot detection, wipe."""

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

EMULATOR_PID_NAME = "emulator"
LOG_FILE = Path.home() / ".holafly-qa" / "emulator.log"


def start_emulator(
    avd_name: str,
    proxy_port: int = 8080,
    gpu: str = "host",
    cores: int = 4,
    memory: int = 4096,
    use_proxy: bool = True,
) -> int:
    """Spawn the Android emulator in the background with required flags."""
    existing_pid = load_pid(EMULATOR_PID_NAME)
    if existing_pid is not None and is_process_running(existing_pid):
        raise RuntimeError(
            f"Emulator is already running (PID {existing_pid}). "
            f"Run 'qa-tool emulator stop' first."
        )

    if existing_pid is not None:
        clear_pid(EMULATOR_PID_NAME)

    cmd = [
        "emulator",
        "-avd",
        avd_name,
        "-writable-system",
        "-gpu",
        gpu,
        "-no-snapshot",
        "-cores",
        str(cores),
        "-memory",
        str(memory),
    ]
    if use_proxy:
        cmd.extend(["-http-proxy", f"127.0.0.1:{proxy_port}"])

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(LOG_FILE, "w")

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    save_pid(EMULATOR_PID_NAME, process.pid)
    return process.pid


def wait_for_boot(timeout: int = 120) -> bool:
    """Poll adb until Android reports boot completion."""
    try:
        subprocess.run(
            ["adb", "wait-for-device"],
            check=True,
            timeout=timeout,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return False

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                ["adb", "shell", "getprop", "sys.boot_completed"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip() == "1":
                time.sleep(2)
                return True
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass

        time.sleep(1)

    return False


def is_emulator_running() -> bool:
    """Return True if the emulator is currently running per the PID file."""
    pid = load_pid(EMULATOR_PID_NAME)
    if pid is None:
        return False
    return is_process_running(pid)


def stop_emulator() -> bool:
    """Stop a running emulator cleanly.

    Tries three approaches in order:
      1. `adb emu kill` — graceful Android shutdown
      2. SIGTERM to the QEMU process — polite kill
      3. SIGKILL to the QEMU process — forceful kill
    """
    pid = load_pid(EMULATOR_PID_NAME)

    if pid is None:
        return False

    if not is_process_running(pid):
        clear_pid(EMULATOR_PID_NAME)
        return False

    try:
        subprocess.run(
            ["adb", "emu", "kill"],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    for _ in range(100):
        if not is_process_running(pid):
            clear_pid(EMULATOR_PID_NAME)
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        clear_pid(EMULATOR_PID_NAME)
        return True

    for _ in range(50):
        if not is_process_running(pid):
            clear_pid(EMULATOR_PID_NAME)
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    clear_pid(EMULATOR_PID_NAME)
    return True


def wipe_app_data(package_name: str = "com.holafly.holafly.dev") -> None:
    """Clear an app's data on the running emulator without restarting."""
    if not is_emulator_running():
        raise RuntimeError(
            "Emulator is not running. Run 'qa-tool emulator start' first."
        )

    try:
        result = subprocess.run(
            ["adb", "shell", "pm", "clear", package_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"pm clear failed: {e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("pm clear timed out")

    if "Success" not in result.stdout:
        raise RuntimeError(
            f"pm clear returned unexpected output: {result.stdout.strip()}"
        )


def wipe_emulator_data(
    avd_name: str,
    proxy_port: int = 8080,
    gpu: str = "host",
    cores: int = 4,
    memory: int = 4096,
    use_proxy: bool = True,
    boot_timeout: int = 180,
) -> int:
    """Stop the emulator, wipe all data, restart with a clean slate."""
    if is_emulator_running():
        stop_emulator()

    cmd = [
        "emulator",
        "-avd",
        avd_name,
        "-wipe-data",
        "-writable-system",
        "-gpu",
        gpu,
        "-no-snapshot",
        "-cores",
        str(cores),
        "-memory",
        str(memory),
    ]
    if use_proxy:
        cmd.extend(["-http-proxy", f"127.0.0.1:{proxy_port}"])

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = open(LOG_FILE, "w")

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    save_pid(EMULATOR_PID_NAME, process.pid)

    if not wait_for_boot(timeout=boot_timeout):
        raise RuntimeError(
            f"Emulator did not finish booting within {boot_timeout}s after wipe"
        )

    return process.pid