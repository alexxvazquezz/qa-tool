"""Init command — interactive first-run wizard."""

import questionary
import typer

from holafly_qa.services.apk import ensure_apk_dir
from holafly_qa.services.avd import list_avds
from holafly_qa.services.config import get_config_path, load_config, save_config


def init() -> None:
    """Interactive setup wizard — pick your AVD and save it to config."""
    typer.echo("")
    typer.echo(typer.style("Holafly QA — first-run setup", bold=True))
    typer.echo("")

    # Step 1: discover AVDs
    avds = list_avds()

    if not avds:
        typer.echo(typer.style("No Android emulators (AVDs) found.", fg=typer.colors.RED))
        typer.echo("")
        typer.echo("You need at least one AVD configured before using this tool.")
        typer.echo("Create one in Android Studio → Device Manager, then re-run 'qa-tool init'.")
        raise typer.Exit(code=1)

    # Step 2: load current config (if any) so we can show the existing choice
    current = load_config()
    default_choice = current.avd_name if current.avd_name in avds else avds[0]

    # Step 3: show interactive picker
    typer.echo(f"Found {len(avds)} AVD(s) on this machine.")
    typer.echo("")

    selected = questionary.select(
        "Which AVD do you use for Holafly QA testing?",
        choices=avds,
        default=default_choice,
    ).ask()

    if selected is None:
        typer.echo(typer.style("Setup cancelled.", fg=typer.colors.YELLOW))
        raise typer.Exit(code=1)

    # Step 4: save config
    current.avd_name = selected
    save_config(current)

    # Step 5: create the APK directory
    apk_dir = ensure_apk_dir()

    typer.echo("")
    typer.echo(typer.style("✓ Configuration saved", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  AVD:     {selected}")
    typer.echo(f"  Config:  {get_config_path()}")
    typer.echo(f"  APK dir: {apk_dir}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. Drop your Codemagic APK into the APK dir above")
    typer.echo("  2. Run 'qa-tool doctor' to verify your environment")
    typer.echo("  3. Run 'qa-tool emulator start' to launch the emulator")