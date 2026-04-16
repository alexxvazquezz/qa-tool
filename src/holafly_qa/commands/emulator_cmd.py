"""Emulator commands — start, stop, wipe the Android emulator."""

import time

import typer

from holafly_qa.services.config import load_config
from holafly_qa.services.emulator import (
    is_emulator_running,
    start_emulator,
    stop_emulator,
    wait_for_boot,
    wipe_app_data,
    wipe_emulator_data,
)
from holafly_qa.services.process import load_pid

emulator_app = typer.Typer(
    name="emulator",
    help="Start, stop, or wipe the Android emulator.",
    no_args_is_help=True,
)


@emulator_app.command("start")
def start(
    no_wait: bool = typer.Option(
        False,
        "--no-wait",
        help="Return immediately without waiting for boot to complete.",
    ),
    no_proxy: bool = typer.Option(
        False,
        "--no-proxy",
        help="Launch without the mitmproxy -http-proxy flag (for normal app usage).",
    ),
    timeout: int = typer.Option(
        180,
        "--timeout",
        help="Seconds to wait for boot (ignored with --no-wait).",
    ),
) -> None:
    """Start the Android emulator with proxy-friendly flags."""
    config = load_config()

    if not config.avd_name:
        typer.echo(
            typer.style(
                "No AVD configured. Run 'qa-tool init' first.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    if is_emulator_running():
        current_pid = load_pid("emulator")
        typer.echo(
            typer.style(
                f"Emulator is already running (PID {current_pid}).",
                fg=typer.colors.YELLOW,
            )
        )
        typer.echo("Run 'qa-tool emulator stop' first if you want to restart.")
        raise typer.Exit(code=1)

    try:
        pid = start_emulator(
            avd_name=config.avd_name,
            proxy_port=config.mitm_port,
            use_proxy=not no_proxy,
        )
    except FileNotFoundError:
        typer.echo(
            typer.style(
                "emulator binary not found on PATH.",
                fg=typer.colors.RED,
            )
        )
        typer.echo("Install Android Studio and add the emulator to PATH.")
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style("✓ Emulator spawned", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  AVD:   {config.avd_name}")
    typer.echo(f"  PID:   {pid}")
    if no_proxy:
        typer.echo(f"  Proxy: disabled (--no-proxy)")
    else:
        typer.echo(f"  Proxy: 127.0.0.1:{config.mitm_port}")

    if no_wait:
        typer.echo("")
        typer.echo("Not waiting for boot (--no-wait). Use 'qa-tool status' to check.")
        return

    typer.echo("")
    typer.echo("Waiting for boot to complete (this takes ~30-60 seconds)...")

    start_time = time.monotonic()
    booted = wait_for_boot(timeout=timeout)
    elapsed = time.monotonic() - start_time

    if booted:
        typer.echo(
            typer.style(
                f"✓ Emulator ready in {elapsed:.1f}s",
                fg=typer.colors.GREEN,
                bold=True,
            )
        )
    else:
        typer.echo(
            typer.style(
                f"✗ Emulator did not finish booting within {timeout}s",
                fg=typer.colors.RED,
            )
        )
        typer.echo("Check log: ~/.holafly-qa/emulator.log")
        raise typer.Exit(code=1)


@emulator_app.command("stop")
def stop() -> None:
    """Stop the running Android emulator."""
    if not is_emulator_running():
        typer.echo(
            typer.style(
                "Emulator is not running.",
                fg=typer.colors.YELLOW,
            )
        )
        return

    typer.echo("Stopping emulator (this can take a few seconds)...")
    stopped = stop_emulator()

    if stopped:
        typer.echo(typer.style("✓ Emulator stopped", fg=typer.colors.GREEN, bold=True))
    else:
        typer.echo(
            typer.style(
                "Emulator was not running (cleaned up stale PID file).",
                fg=typer.colors.YELLOW,
            )
        )


@emulator_app.command("wipe-app")
def wipe_app(
    package: str = typer.Option(
        "com.holafly.holafly.dev",
        "--package",
        "-p",
        help="Android package name to clear (defaults to Holafly dev build).",
    ),
) -> None:
    """Clear the Holafly app's data without restarting the emulator."""
    if not is_emulator_running():
        typer.echo(
            typer.style(
                "Emulator is not running.",
                fg=typer.colors.RED,
            )
        )
        typer.echo("Run 'qa-tool emulator start' first.")
        raise typer.Exit(code=1)

    typer.echo(f"Clearing app data for {package}...")
    try:
        wipe_app_data(package_name=package)
    except RuntimeError as e:
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    typer.echo(
        typer.style(
            f"✓ App data cleared for {package}",
            fg=typer.colors.GREEN,
            bold=True,
        )
    )


@emulator_app.command("wipe-data")
def wipe_data(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
    no_proxy: bool = typer.Option(
        False,
        "--no-proxy",
        help="Relaunch without the mitmproxy -http-proxy flag.",
    ),
) -> None:
    """Factory-reset the emulator (wipes everything including the cert)."""
    config = load_config()

    if not config.avd_name:
        typer.echo(
            typer.style(
                "No AVD configured. Run 'qa-tool init' first.",
                fg=typer.colors.RED,
            )
        )
        raise typer.Exit(code=1)

    if not yes:
        typer.echo(
            typer.style(
                "⚠  This will wipe ALL emulator data:",
                fg=typer.colors.YELLOW,
                bold=True,
            )
        )
        typer.echo("   • All installed apps")
        typer.echo("   • The mitmproxy CA certificate")
        typer.echo("   • All settings, logins, and saved state")
        typer.echo("")
        confirm = typer.confirm("Continue?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(code=0)

    typer.echo("")
    typer.echo("Wiping emulator (stop → wipe → restart → boot)...")
    typer.echo("This takes 1-2 minutes.")

    start_time = time.monotonic()
    try:
        pid = wipe_emulator_data(
            avd_name=config.avd_name,
            proxy_port=config.mitm_port,
            use_proxy=not no_proxy,
        )
    except RuntimeError as e:
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        typer.echo("Check log: ~/.holafly-qa/emulator.log")
        raise typer.Exit(code=1)
    elapsed = time.monotonic() - start_time

    typer.echo("")
    typer.echo(
        typer.style(
            f"✓ Emulator wiped and ready in {elapsed:.1f}s",
            fg=typer.colors.GREEN,
            bold=True,
        )
    )
    typer.echo(f"  PID: {pid}")
    typer.echo("")
    typer.echo(
        typer.style(
            "Note: cert is gone. Run 'qa-tool cert install' to restore it.",
            fg=typer.colors.YELLOW,
        )
    )