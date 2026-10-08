"""APK commands — install the Holafly APK or AAB on the emulator or a device."""

from pathlib import Path

import questionary
import typer

from holafly_qa.services.apk import (
    DEFAULT_PACKAGE,
    ApkError,
    find_apks_in_dir,
    get_package_name,
    install_app,
    list_devices,
    pick_apk,
    uninstall_app,
)

apk_app = typer.Typer(
    name="apk",
    help="Install the Holafly APK or AAB on the emulator or a connected device.",
    no_args_is_help=True,
)


@apk_app.command("install")
def install(
    path: Path = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to a specific .apk or .aab file (overrides auto-discovery).",
    ),
    package: str = typer.Option(
        None,
        "--package",
        help="Android package name to uninstall before install. "
        f"Default: read from the file, else {DEFAULT_PACKAGE}.",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        help="Don't uninstall the existing version first.",
    ),
    device: str = typer.Option(
        None,
        "--device",
        "-s",
        help="adb serial of the target device (see 'adb devices'). "
        "Prompts if several are connected.",
    ),
) -> None:
    """Install the Holafly APK or AAB on the emulator or a USB device.

    By default, looks in the apks/ folder for .apk and .aab files. If
    there's exactly one, uses it. If there are multiple, asks you to pick.
    Pass --path to specify a different file. .aab files are converted
    to device-specific APKs with bundletool.
    """
    try:
        devices = list_devices()
    except ApkError as e:
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    if not devices:
        typer.echo(typer.style("No device connected.", fg=typer.colors.RED))
        typer.echo(
            "Start the emulator with 'qa-tool emulator start', or plug in a "
            "phone with USB debugging enabled and accept the prompt."
        )
        raise typer.Exit(code=1)

    # Figure out which device to target
    if device is not None:
        if device not in devices:
            typer.echo(
                typer.style(
                    f"✗ Device '{device}' is not connected.",
                    fg=typer.colors.RED,
                )
            )
            typer.echo(f"Connected: {', '.join(devices)}")
            raise typer.Exit(code=1)
        serial = device
    elif len(devices) == 1:
        serial = devices[0]
    else:
        serial = questionary.select(
            "Multiple devices connected. Install on which one?",
            choices=devices,
        ).ask()
        if serial is None:
            raise typer.Exit(code=1)

    # Figure out which file to install
    if path is not None:
        apk_path = path
    else:
        apks = find_apks_in_dir()
        try:
            apk_path = pick_apk(apks)
        except ApkError as e:
            typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
            raise typer.Exit(code=1)

    if package is None:
        package = get_package_name(apk_path) or DEFAULT_PACKAGE

    typer.echo("")
    typer.echo(typer.style("Installing app...", bold=True))
    typer.echo(f"  File: {apk_path.name}")
    typer.echo(f"  Package: {package}")
    typer.echo(f"  Device: {serial}")

    # Uninstall existing version unless --keep
    if not keep:
        typer.echo(f"  Uninstalling existing {package} (if any)...")
        try:
            was_installed = uninstall_app(package, serial=serial)
        except ApkError as e:
            typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
            raise typer.Exit(code=1)

        if was_installed:
            typer.echo("    (removed previous version)")

    # Install the new build
    if apk_path.suffix == ".aab":
        typer.echo("  Building device APKs with bundletool (~30-60s)...")
    else:
        typer.echo("  Installing (this takes a few seconds)...")
    try:
        install_app(apk_path, serial=serial)
    except ApkError as e:
        typer.echo("")
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style("✓ Installed", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  Package: {package}")
    typer.echo(f"  Device: {serial}")
