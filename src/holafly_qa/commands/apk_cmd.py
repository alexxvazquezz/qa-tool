"""APK commands — install the Holafly APK on the running emulator."""

from pathlib import Path

import typer

from holafly_qa.services.apk import (
    APK_DIR,
    ApkError,
    find_apks_in_dir,
    install_apk,
    pick_apk,
    uninstall_app,
)
from holafly_qa.services.emulator import is_emulator_running

apk_app = typer.Typer(
    name="apk",
    help="Install the Holafly APK on the running emulator.",
    no_args_is_help=True,
)

DEFAULT_PACKAGE = "com.holafly.holafly.dev"


@apk_app.command("install")
def install(
    path: Path = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to a specific APK file (overrides auto-discovery).",
    ),
    package: str = typer.Option(
        DEFAULT_PACKAGE,
        "--package",
        help="Android package name to uninstall before install.",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        help="Don't uninstall the existing version first.",
    ),
) -> None:
    """Install the Holafly APK on the running emulator.

    By default, looks in ~/.holafly-qa/apks/ for .apk files. If there's
    exactly one, uses it. If there are multiple, asks you to pick.
    Pass --path to specify a different file.
    """
    if not is_emulator_running():
        typer.echo(
            typer.style(
                "Emulator is not running.",
                fg=typer.colors.RED,
            )
        )
        typer.echo("Run 'qa-tool emulator start' first.")
        raise typer.Exit(code=1)

    # Figure out which APK to install
    if path is not None:
        apk_path = path
    else:
        apks = find_apks_in_dir()
        try:
            apk_path = pick_apk(apks)
        except ApkError as e:
            typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
            raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style("Installing APK...", bold=True))
    typer.echo(f"  File: {apk_path.name}")

    # Uninstall existing version unless --keep
    if not keep:
        typer.echo(f"  Uninstalling existing {package} (if any)...")
        try:
            was_installed = uninstall_app(package)
        except ApkError as e:
            typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
            raise typer.Exit(code=1)

        if was_installed:
            typer.echo("    (removed previous version)")

    # Install the new APK
    typer.echo("  Installing (this takes a few seconds)...")
    try:
        install_apk(apk_path)
    except ApkError as e:
        typer.echo("")
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style("✓ APK installed", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  Package: {package}")
    typer.echo("")
    typer.echo("Open the Holafly app on the emulator to start testing.")