"""GUI command — launch the Textual TUI."""

import typer

from holafly_qa.gui.app import run as run_gui


def gui() -> None:
    """Launch the Holafly QA console (Textual TUI)."""
    run_gui()