"""Certificate management for Android emulator proxy interception.

Handles locating mitmproxy's CA cert, computing its subject hash,
preparing the Android-compatible hashed filename, and pushing it to
a running emulator's system trust store.
"""

import shutil
import subprocess
import time
from pathlib import Path

from holafly_qa.services.emulator import wait_for_boot

MITM_CERT_PATH = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
CACHED_CERT_DIR = Path.home() / ".holafly-qa"
HASH_RECORD_FILE = CACHED_CERT_DIR / "cert_hash.txt"


class CertError(Exception):
    """Raised when a cert operation fails with an actionable reason."""


def get_mitm_cert_path() -> Path:
    """Return the path to mitmproxy's CA certificate.

    Raises:
        CertError: If the cert file doesn't exist.
    """
    if not MITM_CERT_PATH.exists():
        raise CertError(
            f"mitmproxy CA cert not found at {MITM_CERT_PATH}. "
            "Run 'mitmweb' once to generate it, then retry."
        )
    return MITM_CERT_PATH


def compute_cert_hash(cert_path: Path) -> str:
    """Compute the subject hash of a PEM certificate using openssl."""
    try:
        result = subprocess.run(
            [
                "openssl",
                "x509",
                "-inform",
                "PEM",
                "-subject_hash_old",
                "-in",
                str(cert_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise CertError("openssl not found on PATH. Install openssl and retry.")
    except subprocess.CalledProcessError as e:
        raise CertError(f"openssl failed to read cert: {e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise CertError("openssl timed out computing cert hash")

    first_line = result.stdout.strip().splitlines()[0]
    return first_line.strip()


def prepare_hashed_cert() -> Path:
    """Ensure a current hashed cert file exists in ~/.holafly-qa/."""
    CACHED_CERT_DIR.mkdir(parents=True, exist_ok=True)

    cert = get_mitm_cert_path()
    current_hash = compute_cert_hash(cert)
    hashed_file = CACHED_CERT_DIR / f"{current_hash}.0"

    previous_hash = None
    if HASH_RECORD_FILE.exists():
        previous_hash = HASH_RECORD_FILE.read_text().strip()

    needs_regen = (
        not hashed_file.exists()
        or previous_hash != current_hash
    )

    if needs_regen:
        if previous_hash is not None and previous_hash != current_hash:
            old_file = CACHED_CERT_DIR / f"{previous_hash}.0"
            if old_file.exists():
                old_file.unlink()

        shutil.copy(cert, hashed_file)
        HASH_RECORD_FILE.write_text(current_hash)

    return hashed_file


def get_emulator_api_level() -> int:
    """Query the running emulator's Android API level via adb."""
    try:
        result = subprocess.run(
            ["adb", "shell", "getprop", "ro.build.version.sdk"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise CertError("adb not found on PATH.")
    except subprocess.CalledProcessError as e:
        raise CertError(
            f"adb failed to query emulator — is the emulator running? "
            f"({e.stderr.strip()})"
        )
    except subprocess.TimeoutExpired:
        raise CertError("adb timed out querying emulator")

    raw = result.stdout.strip()
    try:
        return int(raw)
    except ValueError:
        raise CertError(f"adb returned unexpected API level: {raw!r}")


def adb_root_and_remount() -> None:
    """Put the emulator into writable-system mode."""
    try:
        subprocess.run(
            ["adb", "root"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
    except subprocess.CalledProcessError as e:
        raise CertError(f"adb root failed: {e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise CertError("adb root timed out")

    time.sleep(2)

    try:
        result = subprocess.run(
            ["adb", "remount"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise CertError("adb remount timed out")

    output = (result.stdout + result.stderr).lower()

    if "reboot" in output and "succeed" not in output:
        try:
            subprocess.run(
                ["adb", "reboot"],
                capture_output=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            raise CertError("adb reboot timed out")

        if not wait_for_boot(timeout=180):
            raise CertError("Emulator did not reboot within 3 minutes")

        try:
            subprocess.run(
                ["adb", "root"],
                capture_output=True,
                check=True,
                timeout=15,
            )
        except subprocess.CalledProcessError as e:
            raise CertError(f"adb root failed after reboot: {e.stderr.strip()}")

        time.sleep(2)

        try:
            result = subprocess.run(
                ["adb", "remount"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise CertError("adb remount timed out after reboot")

        output = (result.stdout + result.stderr).lower()
        if "succeed" not in output and result.returncode != 0:
            raise CertError(
                f"adb remount failed after reboot: {result.stderr.strip()}"
            )


def push_cert_to_emulator(hashed_cert_path: Path) -> None:
    """Push the hashed cert to /system/etc/security/cacerts/ and chmod it."""
    target = f"/system/etc/security/cacerts/{hashed_cert_path.name}"

    try:
        subprocess.run(
            ["adb", "push", str(hashed_cert_path), target],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as e:
        raise CertError(f"adb push failed: {e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise CertError("adb push timed out")

    try:
        subprocess.run(
            ["adb", "shell", "chmod", "644", target],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except subprocess.CalledProcessError as e:
        raise CertError(f"adb chmod failed: {e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise CertError("adb chmod timed out")


def install_cert() -> dict:
    """Orchestrate the full cert install flow."""
    hashed_file = prepare_hashed_cert()
    api = get_emulator_api_level()
    adb_root_and_remount()
    push_cert_to_emulator(hashed_file)

    try:
        subprocess.run(
            ["adb", "reboot"],
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise CertError("Final adb reboot timed out")

    if not wait_for_boot(timeout=180):
        raise CertError("Emulator did not reboot within 3 minutes")

    return {
        "cert_path": str(hashed_file),
        "cert_hash": hashed_file.stem,
        "api_level": api,
        "rebooted": True,
    }