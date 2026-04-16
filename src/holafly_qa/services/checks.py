"""Environment check functions for the Holafly QA tool.

Pure functions — they return CheckResult objects, never print.
Used by the doctor command and pre-flight checks in other commands.
"""

import shutil
import sys
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    fix_hint: str = ""


@dataclass
class CheckReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def all_passed(self) -> bool:
        return self.failed_count == 0


def check_command_exists(command_name: str, fix_hint: str = "") -> CheckResult:
    """Check whether a command is available on the user's PATH."""
    path = shutil.which(command_name)

    if path is not None:
        return CheckResult(
            name=command_name,
            passed=True,
            detail=path,
        )

    return CheckResult(
        name=command_name,
        passed=False,
        detail="not found on PATH",
        fix_hint=fix_hint,
    )


MINIMUM_PYTHON = (3, 10)


def check_python_version() -> CheckResult:
    """Check that the running Python is 3.10 or newer."""
    current = sys.version_info
    current_str = f"{current.major}.{current.minor}.{current.micro}"
    minimum_str = f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}"

    if (current.major, current.minor) >= MINIMUM_PYTHON:
        return CheckResult(
            name="Python",
            passed=True,
            detail=current_str,
        )

    return CheckResult(
        name="Python",
        passed=False,
        detail=f"{current_str} (need {minimum_str} or newer)",
        fix_hint=f"Install Python {minimum_str}+ from python.org",
    )


def run_all_checks() -> CheckReport:
    """Run every environment check and return a combined report."""
    results = [
        check_python_version(),
        check_command_exists(
            "adb",
            fix_hint="Install Android Studio or platform-tools, then add to PATH",
        ),
        check_command_exists(
            "emulator",
            fix_hint="Install Android Studio emulator, then add to PATH",
        ),
        check_command_exists(
            "mitmweb",
            fix_hint="Install mitmproxy: pipx install mitmproxy",
        ),
    ]
    return CheckReport(results=results)