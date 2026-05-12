"""Network throttle management — simulate slow connections via mitmproxy delay addon."""

from pathlib import Path

from holafly_qa.services.mitmweb import is_mitmweb_running, start_mitmweb, stop_mitmweb

_STATE_DIR = Path.home() / ".holafly-qa"
THROTTLE_STATE_FILE = _STATE_DIR / "active_throttle.txt"
THROTTLE_SCRIPT_FILE = _STATE_DIR / "current_throttle.py"

# preset name → {"kbps": float, "latency_ms": float, "label": str} | None
THROTTLE_PRESETS: dict[str, dict | None] = {
    "full":  None,
    "lte":   {"kbps": 58_000.0, "latency_ms": 50.0,  "label": "LTE (~58 Mbps)"},
    "hsdpa": {"kbps": 14_400.0, "latency_ms": 100.0, "label": "HSDPA (~14.4 Mbps)"},
    "umts":  {"kbps": 1_920.0,  "latency_ms": 200.0, "label": "UMTS/3G (~1.9 Mbps)"},
    "edge":  {"kbps": 118.0,    "latency_ms": 400.0, "label": "EDGE (~118 Kbps)"},
    "gsm":   {"kbps": 9.6,      "latency_ms": 750.0, "label": "GSM (~9.6 Kbps)"},
}


def render_throttle_script(kbps: float, latency_ms: float) -> str:
    """Generate a mitmproxy addon script that simulates bandwidth throttling.

    Each response is delayed by a base latency plus the time it would take
    to transfer the response body at the given bandwidth. Delay is capped at
    30 seconds to keep QA flows usable even on very slow presets.

    Args:
        kbps: Simulated bandwidth in kilobits per second.
        latency_ms: Base round-trip latency in milliseconds.

    Returns:
        Python source for a valid mitmproxy addon file.
    """
    bytes_per_sec = kbps * 1000.0 / 8.0
    base_delay = latency_ms / 1000.0
    return f'''"""Auto-generated throttle addon — {kbps:.1f} kbps / {latency_ms:.0f}ms latency."""
import asyncio

_BYTES_PER_SEC = {bytes_per_sec}
_BASE_DELAY = {base_delay}
_MAX_DELAY = 30.0


class ThrottleAddon:
    async def response(self, flow):
        if flow.response and flow.response.content:
            size = len(flow.response.content)
            bw_delay = size / _BYTES_PER_SEC
            total = min(_BASE_DELAY + bw_delay, _MAX_DELAY)
            await asyncio.sleep(total)


addons = [ThrottleAddon()]
'''


def get_active_throttle() -> str | None:
    """Return the active throttle preset name, or None if no throttling is active."""
    if not THROTTLE_STATE_FILE.exists():
        return None
    preset = THROTTLE_STATE_FILE.read_text().strip()
    if preset not in THROTTLE_PRESETS or preset == "full":
        return None
    return preset


def set_throttle(preset: str) -> None:
    """Activate a throttle preset, restarting mitmweb if it is running.

    Passing "full" is equivalent to calling clear_throttle().

    Args:
        preset: One of the keys in THROTTLE_PRESETS.

    Raises:
        ValueError: If preset is not a recognised key.
    """
    if preset not in THROTTLE_PRESETS:
        valid = ", ".join(THROTTLE_PRESETS.keys())
        raise ValueError(f"Unknown throttle preset {preset!r}. Valid: {valid}")

    if preset == "full":
        clear_throttle()
        return

    params = THROTTLE_PRESETS[preset]
    assert params is not None
    kbps: float = params["kbps"]
    latency_ms: float = params["latency_ms"]

    script_source = render_throttle_script(kbps, latency_ms)
    THROTTLE_SCRIPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    THROTTLE_SCRIPT_FILE.write_text(script_source)
    THROTTLE_STATE_FILE.write_text(preset)

    if is_mitmweb_running():
        stop_mitmweb()
        start_mitmweb()


def clear_throttle() -> str | None:
    """Remove any active throttle, restarting mitmweb if it is running.

    Returns:
        The preset name that was cleared, or None if no throttle was active.
    """
    previous = get_active_throttle()

    if THROTTLE_STATE_FILE.exists():
        THROTTLE_STATE_FILE.unlink()
    if THROTTLE_SCRIPT_FILE.exists():
        THROTTLE_SCRIPT_FILE.unlink()

    if is_mitmweb_running():
        stop_mitmweb()
        start_mitmweb()

    return previous
