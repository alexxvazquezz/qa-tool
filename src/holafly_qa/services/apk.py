"""APK discovery and install on the running emulator."""

import os
import shutil
import subprocess
from pathlib import Path

import questionary

APK_DIR = APK_DIR = Path(__file__).resolve().parent.parent.parent.parent / "apks"


# Staging builds use the .dev package, RC/production builds the bare one
HOLAFLY_PACKAGES = ("com.holafly.holafly.dev", "com.holafly.holafly")
DEFAULT_PACKAGE = HOLAFLY_PACKAGES[0]


class ApkError(Exception):
    """Raised when an APK operation fails with an actionable reason."""


def ensure_apk_dir() -> Path:
    """Create the APK directory if it doesn't exist. Return its path."""
    APK_DIR.mkdir(parents=True, exist_ok=True)
    return APK_DIR


def find_apks_in_dir(apk_dir: Path = APK_DIR) -> list[Path]:
    """Return all .apk and .aab files in the given directory, sorted by name."""
    if not apk_dir.exists():
        return []
    return sorted([*apk_dir.glob("*.apk"), *apk_dir.glob("*.aab")])


def _adb(serial: str | None) -> list[str]:
    """Return the adb command prefix, targeting a specific device if given."""
    if serial:
        return ["adb", "-s", serial]
    return ["adb"]


def list_devices() -> list[str]:
    """Return serials of connected devices that are ready for adb commands.

    Only devices in the `device` state are returned — `unauthorized`
    and `offline` entries are skipped.

    Raises:
        ApkError: If adb is missing or times out.
    """
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise ApkError("adb not found on PATH.")
    except subprocess.TimeoutExpired:
        raise ApkError("adb devices timed out")

    serials = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def find_emulator_serial() -> str | None:
    """Return the serial of the first connected emulator, or None."""
    try:
        devices = list_devices()
    except ApkError:
        return None
    for serial in devices:
        if serial.startswith("emulator-"):
            return serial
    return None


def pick_apk(apks: list[Path]) -> Path:
    """Pick an APK from a list: one = auto, many = interactive picker.

    Raises:
        ApkError: If the list is empty.
    """
    if not apks:
        raise ApkError(
            f"No .apk or .aab files found in {APK_DIR}. "
            f"Drop your Codemagic build there and retry."
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


def uninstall_app(package_name: str, serial: str | None = None) -> bool:
    """Uninstall an app from the running emulator.

    Returns:
        True if the app was uninstalled, False if it wasn't installed
        (both are success cases — caller doesn't care which).
    """
    try:
        result = subprocess.run(
            [*_adb(serial), "uninstall", package_name],
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


def install_apk(apk_path: Path, serial: str | None = None) -> None:
    """Install an APK on the running emulator via adb install.

    Raises:
        ApkError: If the APK file doesn't exist or install fails.
    """
    if not apk_path.exists():
        raise ApkError(f"APK file not found: {apk_path}")

    try:
        result = subprocess.run(
            [*_adb(serial), "install", str(apk_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise ApkError("adb install timed out")

    combined = result.stdout + result.stderr
    if "Success" not in combined:
        raise ApkError(f"adb install failed: {combined.strip()}")


def install_app(path: Path, serial: str | None = None) -> None:
    """Install an .apk (adb) or .aab (bundletool) on the target device."""
    if path.suffix == ".aab":
        # Local import: bundletool imports ApkError from this module
        from holafly_qa.services.bundletool import install_aab

        install_aab(path, serial=serial)
    else:
        install_apk(path, serial=serial)


def _find_aapt2() -> str | None:
    """Return the aapt2 path: PATH first, then the newest SDK build-tools."""
    found = shutil.which("aapt2")
    if found:
        return found

    sdk = Path(os.environ.get("ANDROID_HOME", Path.home() / "Android" / "Sdk"))
    candidates = sorted(
        (sdk / "build-tools").glob("*/aapt2"),
        key=lambda p: [int(x) if x.isdigit() else 0 for x in p.parent.name.split(".")],
    )
    return str(candidates[-1]) if candidates else None


def get_package_name(path: Path) -> str | None:
    """Read the Android package name from an .apk or .aab file.

    Uses aapt2 for .apk files and bundletool for .aab files.

    Returns:
        The package name, or None if it can't be determined (tool
        missing, unreadable file). Callers should fall back to
        DEFAULT_PACKAGE.
    """
    if path.suffix == ".aab":
        # Local import: bundletool imports ApkError from this module
        from holafly_qa.services.bundletool import get_bundletool_cmd

        try:
            cmd = [
                *get_bundletool_cmd(),
                "dump",
                "manifest",
                f"--bundle={path}",
                "--xpath=/manifest/@package",
            ]
        except ApkError:
            return None
    else:
        aapt2 = _find_aapt2()
        if aapt2 is None:
            return None
        cmd = [aapt2, "dump", "packagename", str(path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    package = result.stdout.strip()
    if result.returncode != 0 or not package or " " in package:
        return None
    return package


def list_installed_holafly_packages(serial: str | None = None) -> list[str]:
    """Return which of HOLAFLY_PACKAGES are installed on the device.

    Returns an empty list if adb fails or times out.
    """
    try:
        result = subprocess.run(
            [*_adb(serial), "shell", "pm", "list", "packages", "com.holafly"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    installed = {
        line.removeprefix("package:").strip()
        for line in result.stdout.splitlines()
    }
    return [pkg for pkg in HOLAFLY_PACKAGES if pkg in installed]
