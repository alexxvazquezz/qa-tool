"""Entry point for the qa-tool command-line interface."""

import typer

from holafly_qa.commands.apk_cmd import apk_app
from holafly_qa.commands.cert_cmd import cert_app
from holafly_qa.commands.doctor_cmd import doctor
from holafly_qa.commands.emulator_cmd import emulator_app
from holafly_qa.commands.init_cmd import init
from holafly_qa.commands.mitmweb_cmd import mitmweb_app
from holafly_qa.commands.inject_cmd import inject_app
from holafly_qa.commands.gui_cmd import gui

app = typer.Typer(
    name="qa-tool",
    help="QA network interception tool for the Holafly Flutter app.",
    no_args_is_help=True,
)

app.command()(init)
app.command()(doctor)
app.command()(gui)
app.add_typer(mitmweb_app, name="mitmweb")
app.add_typer(emulator_app, name="emulator")
app.add_typer(cert_app, name="cert")
app.add_typer(apk_app, name="apk")
app.add_typer(inject_app, name="inject")


@app.command()
def version() -> None:
    """Show the tool's version."""
    from holafly_qa import __version__
    typer.echo(f"qa-tool version {__version__}")


if __name__ == "__main__":
    app()