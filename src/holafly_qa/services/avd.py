"""AVD (Android Virtual Device) discovery and management."""

import subprocess


def list_avds() -> list[str]:
    """Return the names of all Android emulator AVDs on this machine.

    Runs `emulator -list-avds` and parses its output. Each line of the
    output is one AVD name, so we split on newlines and strip blanks.

    Returns:
        List of AVD names. Empty list if no AVDs are configured OR if
        the emulator command is not installed (caller should check for
        emulator availability separately via the doctor checks).
    """
    try:
        result = subprocess.run(
            ["emulator", "-list-avds"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except FileNotFoundError:
        # emulator binary isn't on PATH
        return []
    except subprocess.CalledProcessError:
        # emulator ran but returned non-zero
        return []
    except subprocess.TimeoutExpired:
        # emulator hung (shouldn't happen for -list-avds but defend anyway)
        return []

    lines = result.stdout.strip().splitlines()
    return [line.strip() for line in lines if line.strip()]
