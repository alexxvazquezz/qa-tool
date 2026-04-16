"""Cert commands — install the mitmproxy CA on the running emulator."""

import typer

from holafly_qa.services.cert import CertError, install_cert
from holafly_qa.services.emulator import is_emulator_running

cert_app = typer.Typer(
    name="cert",
    help="Install the mitmproxy CA certificate on the running emulator.",
    no_args_is_help=True,
)


@cert_app.command("install")
def install() -> None:
    """Push the mitmproxy CA cert to the emulator's system trust store.

    Requires the emulator to already be running. Use:
        qa-tool emulator start
    first if it isn't.
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

    typer.echo("")
    typer.echo(typer.style("Installing cert on emulator...", bold=True))
    typer.echo("This takes 2-3 minutes (remount + reboot cycle).")
    typer.echo("")

    try:
        result = install_cert()
    except CertError as e:
        typer.echo("")
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style("✓ Certificate installed", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  Cert file: {result['cert_path']}")
    typer.echo(f"  Hash:      {result['cert_hash']}")
    typer.echo(f"  API level: {result['api_level']}")
    typer.echo("")
    typer.echo("Emulator is ready. You can now install the Holafly APK.")