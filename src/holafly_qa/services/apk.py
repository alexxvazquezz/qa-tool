"""APK discovery and install on the running emulator."""

import subprocess
from pathlib import Path

import questionary

APK_DIR = APK_DIR = Path(__file__).resolve().parent.parent.parent.parent / "apks"


class ApkError(Exception):
    """Raised when an APK operation fails with an actionable reason."""


def ensure_apk_dir() -> Path:
    """Create the APK directory if it doesn't exist. Return its path."""
    APK_DIR.mkdir(parents=True, exist_ok=True)
    return APK_DIR


def find_apks_in_dir(apk_dir: Path = APK_DIR) -> list[Path]:
    """Return all .apk files in the given directory, sorted by name."""
    if not apk_dir.exists():
        return []
    return sorted(apk_dir.glob("*.apk"))


def pick_apk(apks: list[Path]) -> Path:
    """Pick an APK from a list: one = auto, many = interactive picker.

    Raises:
        ApkError: If the list is empty.
    """
    if not apks:
        raise ApkError(
            f"No APKs found in {APK_DIR}. "
            f"Drop your Codemagic APK there and retry."
        )

    if len(apks) == 1:
        return apks[0]

    choices = [apk.name for apk in apks]
    selected_name = questionary.select(
        f"Multiple APKs found. Which one?",
        choices=choices,
        default=choices[-1],  # Last alphabetically = usually newest build
    ).ask()

    if selected_name is None:
        raise ApkError("APK selection cancelled.")

    return APK_DIR / selected_name


def uninstall_app(package_name: str) -> bool:
    """Uninstall an app from the running emulator.

    Returns:
        True if the app was uninstalled, False if it wasn't installed
        (both are success cases — caller doesn't care which).
    """
    try:
        result = subprocess.run(
            ["adb", "uninstall", package_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise ApkError("adb uninstall timed out")

    if "Success" in result.stdout:
        return True

    # "Unknown package" or similar — not installed, not an error
    return False


def install_apk(apk_path: Path) -> None:
    """Install an APK on the running emulator via adb install.

    Raises:
        ApkError: If the APK file doesn't exist or install fails.
    """
    if not apk_path.exists():
        raise ApkError(f"APK file not found: {apk_path}")

    try:
        result = subprocess.run(
            ["adb", "install", str(apk_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ApkError("adb install timed out")

    combined = result.stdout + result.stderr
    if "Success" not in combined:
        raise ApkError(f"adb install failed: {combined.strip()}")