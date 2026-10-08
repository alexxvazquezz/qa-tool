"""AAB installation via bundletool.

adb can't install an .aab directly. bundletool converts it into a
device-specific .apks archive (split APKs for the target's ABI,
density and language), then installs that archive over adb.
"""

import shutil
import subprocess
from pathlib import Path

from holafly_qa.services.apk import ApkError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BUNDLETOOL_JAR = _PROJECT_ROOT / "tools" / "bundletool.jar"
APKS_CACHE_DIR = Path.home() / ".holafly-qa" / "apks_cache"
DEBUG_KEYSTORE = Path.home() / ".android" / "debug.keystore"


class BundletoolError(ApkError):
    """Raised when a bundletool operation fails with an actionable reason."""


def get_bundletool_cmd() -> list[str]:
    """Return the command prefix for invoking bundletool.

    Prefers a `bundletool` wrapper on PATH (e.g. Homebrew), falls back
    to <project-root>/tools/bundletool.jar run with java.

    Raises:
        BundletoolError: If neither is available, or java is missing.
    """
    if shutil.which("bundletool"):
        return ["bundletool"]

    if BUNDLETOOL_JAR.exists():
        if shutil.which("java") is None:
            raise BundletoolError(
                "java not found on PATH. bundletool.jar needs Java 11+ "
                "(Android Studio ships one under its jbr/ folder)."
            )
        return ["java", "-jar", str(BUNDLETOOL_JAR)]

    raise BundletoolError(
        f"bundletool not found. Download the jar from "
        f"github.com/google/bundletool/releases and save it as {BUNDLETOOL_JAR}"
    )


def _adb_path() -> str:
    """Return the absolute adb path (bundletool can't always find it itself)."""
    adb = shutil.which("adb")
    if adb is None:
        raise BundletoolError("adb not found on PATH.")
    return adb


def _signing_args() -> list[str]:
    """Return bundletool flags to sign generated APKs with the debug key."""
    if not DEBUG_KEYSTORE.exists():
        raise BundletoolError(
            f"Debug keystore not found at {DEBUG_KEYSTORE}. Create it with:\n"
            "  keytool -genkeypair -v -keystore ~/.android/debug.keystore "
            "-storepass android -alias androiddebugkey -keypass android "
            "-keyalg RSA -keysize 2048 -validity 10000 "
            '-dname "CN=Android Debug,O=Android,C=US"'
        )
    return [
        f"--ks={DEBUG_KEYSTORE}",
        "--ks-pass=pass:android",
        "--ks-key-alias=androiddebugkey",
        "--key-pass=pass:android",
    ]


def _run(cmd: list[str], timeout: int, step: str) -> None:
    """Run a bundletool command, translating failures into BundletoolError."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise BundletoolError(f"bundletool {step} timed out after {timeout}s")

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        if "UPDATE_INCOMPATIBLE" in output:
            raise BundletoolError(
                "Installed app has a different signature. Uninstall it first "
                "(APKs built from an .aab are signed with the debug key)."
            )
        raise BundletoolError(f"bundletool {step} failed: {output}")


def build_apks(aab_path: Path, serial: str | None = None) -> Path:
    """Build a device-specific .apks archive from an .aab.

    Args:
        aab_path: Path to the .aab file.
        serial: adb serial of the target device. Required by bundletool
            when more than one device is connected.

    Returns:
        Path to the generated .apks file in ~/.holafly-qa/apks_cache/.
    """
    if not aab_path.exists():
        raise BundletoolError(f"AAB file not found: {aab_path}")

    APKS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output = APKS_CACHE_DIR / f"{aab_path.stem}.apks"

    cmd = [
        *get_bundletool_cmd(),
        "build-apks",
        f"--bundle={aab_path}",
        f"--output={output}",
        "--overwrite",
        "--connected-device",
        f"--adb={_adb_path()}",
        *_signing_args(),
    ]
    if serial:
        cmd.append(f"--device-id={serial}")

    _run(cmd, timeout=300, step="build-apks")
    return output


def install_apks(apks_path: Path, serial: str | None = None) -> None:
    """Install a .apks archive on a device via bundletool."""
    cmd = [
        *get_bundletool_cmd(),
        "install-apks",
        f"--apks={apks_path}",
        f"--adb={_adb_path()}",
    ]
    if serial:
        cmd.append(f"--device-id={serial}")

    _run(cmd, timeout=180, step="install-apks")


def install_aab(aab_path: Path, serial: str | None = None) -> None:
    """Build device APKs from an .aab and install them in one step."""
    apks = build_apks(aab_path, serial=serial)
    install_apks(apks, serial=serial)
