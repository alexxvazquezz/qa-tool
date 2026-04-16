"""Injection rule management — load, save, activate failure scenarios.

A rule describes one failure scenario: which endpoint to intercept,
what action to take, and optionally what response to return. Rules
live in ~/.holafly-qa/injection_rules.toml and are loaded/saved by
functions in this module.

The InjectionRule dataclass is the core data model — the CLI, the
future GUI, and the rule file all share this shape.
"""

from holafly_qa.services.mitmweb import (
    is_mitmweb_running,
    start_mitmweb,
    stop_mitmweb,
)

import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
import tomli_w
import re


# Resolve project root (src/holafly_qa/services/ → up 3 levels to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RULES_FILE = _PROJECT_ROOT / "rules" / "injection_rules.toml"
SCRIPT_FILE = Path.home() / ".holafly-qa" / "current_injection.py"
ACTIVE_STATE_FILE = Path.home() / ".holafly-qa" / "active_injection.txt"


@dataclass
class InjectionRule:
    """A single failure injection scenario.

    Attributes:
        name: Unique identifier used by CLI commands (e.g. "payments_500").
        description: Human-readable label shown in list and GUI.
        endpoint: URL path pattern with glob placeholders like {uuid}.
        action: "respond" to return a fake response, "kill" to drop
            the connection mid-request.
        method: HTTP method filter ("GET", "POST", etc). Empty string
            means match any method.
        status: HTTP status code for respond actions (ignored for kill).
        body: Response body for respond actions (ignored for kill).
    """

    name: str
    description: str
    endpoint: str
    action: str
    method: str = ""
    status: int = 500
    body: str = ""


GLOB_PLACEHOLDERS = {
    "{uuid}": r"[a-f0-9\-]+",
    "{id}": r"\d+",
    "{*}": r"[^/]+",
    "{**}": r".+",
}


def glob_to_regex(pattern: str) -> str:
    """Convert a user-friendly glob pattern into a regex for path matching.

    Supports these placeholders:
      {uuid}  → matches UUIDs (hex chars and dashes)
      {id}    → matches numeric IDs
      {*}     → matches any single path segment (no slashes)
      {**}    → matches anything including slashes

    Everything else in the pattern is escaped so literal characters
    like '/', '.', '-' match themselves rather than being treated as
    regex metacharacters.

    Args:
        pattern: A glob pattern like "/customer/v1/esims/{uuid}/qr".

    Returns:
        An anchored regex string like "/customer/v1/esims/[a-f0-9\\-]+/qr$".
    """
    # Extract placeholders first so they aren't escaped as literals
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        matched = False
        for glob, regex in GLOB_PLACEHOLDERS.items():
            if pattern[i:].startswith(glob):
                parts.append(regex)
                i += len(glob)
                matched = True
                break
        if not matched:
            parts.append(re.escape(pattern[i]))
            i += 1

    # Anchor to end so "/esims/{uuid}" doesn't match "/esims/{uuid}/qr"
    return "".join(parts) + "$"

def load_rules() -> list[InjectionRule]:
    """Load all injection rules from the rules file.

    Returns an empty list if the file doesn't exist yet. This makes
    first-run handling clean — callers don't need to check file
    existence before calling.

    Returns:
        A list of InjectionRule objects, in file order.
    """
    if not RULES_FILE.exists():
        return []

    with open(RULES_FILE, "rb") as f:
        data = tomllib.load(f)

    raw_rules = data.get("rule", [])
    rules = []
    for entry in raw_rules:
        rules.append(
            InjectionRule(
                name=entry.get("name", ""),
                description=entry.get("description", ""),
                endpoint=entry.get("endpoint", ""),
                action=entry.get("action", "kill"),
                method=entry.get("method", ""),
                status=entry.get("status", 500),
                body=entry.get("body", ""),
            )
        )
    return rules


def save_rules(rules: list[InjectionRule]) -> None:
    """Save a list of injection rules to the rules file, overwriting.

    Creates the config directory if it doesn't exist. The file format
    is TOML with each rule as a [[rule]] table.

    Args:
        rules: The complete list of rules to save. Any existing rules
            in the file are replaced.
    """
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {"rule": [asdict(r) for r in rules]}

    with open(RULES_FILE, "wb") as f:
        tomli_w.dump(data, f)

def render_script(rule: InjectionRule) -> str:
    """Generate a mitmproxy addon script from an injection rule.

    The returned string is valid Python source code that defines a
    `request` hook mitmproxy will call for every request. The hook
    matches the rule's endpoint regex, checks the method filter, and
    applies the configured action.

    Args:
        rule: The rule to render into an addon script.

    Returns:
        Python source code as a string, ready to write to a file.

    Raises:
        ValueError: If the rule's action is not "respond" or "kill".
    """
    if rule.action not in ("respond", "kill"):
        raise ValueError(
            f"Unknown action {rule.action!r} in rule {rule.name!r}. "
            f"Expected 'respond' or 'kill'."
        )

    regex = glob_to_regex(rule.endpoint)

    if rule.action == "respond":
        action_code = f"""        flow.response = http.Response.make(
            {rule.status},
            {rule.body!r}.encode(),
            {{"Content-Type": "application/json"}},
        )"""
    else:  # kill
        action_code = "        flow.kill()"

    if rule.method:
        method_check = f'    if flow.request.method != {rule.method!r}:\n        return\n'
    else:
        method_check = ""

    return f'''"""Auto-generated injection script for rule: {rule.name}
{rule.description}
"""
import re

from mitmproxy import http

PATTERN = re.compile({regex!r})


def request(flow: http.HTTPFlow) -> None:
{method_check}    if re.search(PATTERN, flow.request.path):
{action_code}
'''

def start_injection(rule_name: str) -> InjectionRule:
    """Activate an injection rule by restarting mitmweb with its script.

    Looks up the rule by name, generates the mitmproxy addon script,
    writes it to SCRIPT_FILE, stops any running mitmweb, and starts
    a fresh mitmweb with the script loaded via -s.

    Args:
        rule_name: The `name` field of the rule to activate.

    Returns:
        The InjectionRule that was activated, for display purposes.

    Raises:
        ValueError: If no rule with that name exists.
    """
    rules = load_rules()
    match = next((r for r in rules if r.name == rule_name), None)

    if match is None:
        available = ", ".join(r.name for r in rules) or "(none)"
        raise ValueError(
            f"No rule named {rule_name!r}. Available: {available}"
        )

    # Generate and write the addon script
    script_source = render_script(match)
    SCRIPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCRIPT_FILE.write_text(script_source)

    # Stop any running mitmweb so we can restart with the script
    if is_mitmweb_running():
        stop_mitmweb()

    # Start mitmweb with the script loaded
    start_mitmweb(script=SCRIPT_FILE)

    # Record what's active
    ACTIVE_STATE_FILE.write_text(rule_name)

    return match

def stop_injection() -> str | None:
    """Deactivate any running injection rule.

    Restarts mitmweb without the -s script flag, so traffic flows
    through normally. Clears the active state file.

    Returns:
        The name of the rule that was stopped, or None if no rule
        was active.
    """
    # Read what was active (for the return value and user feedback)
    active_name: str | None = None
    if ACTIVE_STATE_FILE.exists():
        active_name = ACTIVE_STATE_FILE.read_text().strip() or None
        ACTIVE_STATE_FILE.unlink()

    # Restart mitmweb without the script
    if is_mitmweb_running():
        stop_mitmweb()
        start_mitmweb()  # No script argument this time

    return active_name

def get_active_injection() -> str | None:
    """Return the name of the currently active injection rule, or None."""
    if not ACTIVE_STATE_FILE.exists():
        return None
    name = ACTIVE_STATE_FILE.read_text().strip()
    return name or None

def get_rule(name: str) -> InjectionRule | None:
    """Return a rule by name, or None if not found."""
    for rule in load_rules():
        if rule.name == name:
            return rule
    return None


def add_rule(rule: InjectionRule) -> None:
    """Add a new rule to the rules file.

    Raises:
        ValueError: If a rule with the same name already exists.
    """
    rules = load_rules()
    if any(r.name == rule.name for r in rules):
        raise ValueError(f"A rule named {rule.name!r} already exists.")
    rules.append(rule)
    save_rules(rules)


def remove_rule(name: str) -> bool:
    """Remove a rule by name.

    Returns:
        True if the rule was found and removed, False if it didn't exist.
    """
    rules = load_rules()
    filtered = [r for r in rules if r.name != name]
    if len(filtered) == len(rules):
        return False
    save_rules(filtered)
    return True