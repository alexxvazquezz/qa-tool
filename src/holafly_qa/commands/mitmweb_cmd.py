"""mitmweb commands — start and stop mitmproxy in the background."""

import typer

from holafly_qa.services.config import load_config
from holafly_qa.services.mitmweb import (
    LOG_FILE,
    is_mitmweb_running,
    start_mitmweb,
    stop_mitmweb,
)
from holafly_qa.services.process import load_pid

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