"""mitmweb commands — start, stop, and throttle mitmproxy in the background."""

import typer

from holafly_qa.services.config import load_config
from holafly_qa.services.mitmweb import (
    LOG_FILE,
    is_mitmweb_running,
    start_mitmweb,
    stop_mitmweb,
)
from holafly_qa.services.process import load_pid
from holafly_qa.services.throttle import (
    THROTTLE_PRESETS,
    clear_throttle,
    get_active_throttle,
    set_throttle,
)

mitmweb_app = typer.Typer(
    name="mitmweb",
    help="Start or stop the mitmproxy web UI.",
    no_args_is_help=True,
)


@mitmweb_app.command("start")
def start(
    port: int = typer.Option(
        None,
        "--port",
        "-p",
        help="Port to listen on (defaults to config value).",
    ),
) -> None:
    """Start mitmweb in the background with Adyen bypass enabled."""
    config = load_config()
    effective_port = port if port is not None else config.mitm_port

    if is_mitmweb_running():
        current_pid = load_pid("mitmweb")
        typer.echo(
            typer.style(
                f"mitmweb is already running (PID {current_pid}).",
                fg=typer.colors.YELLOW,
            )
        )
        typer.echo("Run 'qa-tool mitmweb stop' first if you want to restart.")
        raise typer.Exit(code=1)

    try:
        pid = start_mitmweb(port=effective_port)
    except FileNotFoundError:
        typer.echo(
            typer.style(
                "mitmweb binary not found on PATH.",
                fg=typer.colors.RED,
            )
        )
        typer.echo("Install mitmproxy: pipx install mitmproxy")
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style("✓ mitmweb started", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  PID:    {pid}")
    typer.echo(f"  Proxy:  127.0.0.1:{effective_port}")
    typer.echo(f"  Web UI: http://127.0.0.1:8081")
    active_throttle = get_active_throttle()
    if active_throttle:
        params = THROTTLE_PRESETS[active_throttle]
        label = params["label"] if params else active_throttle  # type: ignore[index]
        typer.echo(
            f"  Throttle: "
            + typer.style(label, fg=typer.colors.YELLOW, bold=True)
        )
    typer.echo(f"  Log:    {LOG_FILE}")


@mitmweb_app.command("stop")
def stop() -> None:
    """Stop the background mitmweb process."""
    if not is_mitmweb_running():
        typer.echo(
            typer.style(
                "mitmweb is not running.",
                fg=typer.colors.YELLOW,
            )
        )
        # Not an error — just informational
        return

    stopped = stop_mitmweb()

    if stopped:
        typer.echo(typer.style("✓ mitmweb stopped", fg=typer.colors.GREEN, bold=True))
    else:
        typer.echo(
            typer.style(
                "mitmweb was not running (cleaned up stale PID file).",
                fg=typer.colors.YELLOW,
            )
        )


@mitmweb_app.command("throttle")
def throttle(
    preset: str = typer.Argument(
        help="Speed preset: full (disable), lte, hsdpa, umts, edge, gsm",
    ),
) -> None:
    """Set network throttle on mitmproxy. Use 'full' to disable.

    When mitmweb is running it will be restarted automatically with
    the new throttle setting. If mitmweb is stopped, the setting is
    saved and applied on the next 'mitmweb start'.

    Available presets:
      full   — no throttle (disable)
      lte    — ~58 Mbps / 50ms latency
      hsdpa  — ~14.4 Mbps / 100ms latency
      umts   — ~1.9 Mbps / 200ms latency  (3G)
      edge   — ~118 Kbps / 400ms latency
      gsm    — ~9.6 Kbps / 750ms latency
    """
    if preset not in THROTTLE_PRESETS:
        valid = ", ".join(THROTTLE_PRESETS.keys())
        typer.echo(
            typer.style(
                f"✗ Unknown preset {preset!r}. Valid: {valid}",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    running = is_mitmweb_running()

    try:
        if preset == "full":
            previous = clear_throttle()
            if previous:
                typer.echo(
                    typer.style(
                        f"✓ Throttle cleared (was {previous})",
                        fg=typer.colors.GREEN,
                        bold=True,
                    )
                )
            else:
                typer.echo(
                    typer.style("✓ No throttle was active", fg=typer.colors.GREEN)
                )
        else:
            set_throttle(preset)
            params = THROTTLE_PRESETS[preset]
            label = params["label"]  # type: ignore[index]
            typer.echo(
                typer.style(
                    f"✓ Throttle set to {label}",
                    fg=typer.colors.GREEN,
                    bold=True,
                )
            )
    except ValueError as e:
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    if running:
        typer.echo("  mitmweb restarted with updated throttle")
    else:
        typer.echo("  mitmweb is not running — setting saved for next start")