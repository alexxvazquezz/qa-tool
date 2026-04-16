"""Doctor command — runs all environment checks and prints a report."""

import typer

from holafly_qa.services.checks import run_all_checks


def doctor() -> None:
    """Check that your environment has everything the QA tool needs."""
    report = run_all_checks()

    typer.echo("")
    typer.echo(typer.style("Holafly QA — environment check", bold=True))
    typer.echo("")

    for result in report.results:
        if result.passed:
            mark = typer.style("✓", fg=typer.colors.GREEN, bold=True)
        else:
            mark = typer.style("✗", fg=typer.colors.RED, bold=True)

        name = f"{result.name:12s}"
        typer.echo(f"  {mark}  {name} {result.detail}")

        if not result.passed and result.fix_hint:
            hint = typer.style(f"     → {result.fix_hint}", fg=typer.colors.YELLOW)
            typer.echo(hint)

    typer.echo("")
    summary = f"{report.passed_count} passed, {report.failed_count} failed"
    if report.all_passed:
        typer.echo(typer.style(summary, fg=typer.colors.GREEN))
    else:
        typer.echo(typer.style(summary, fg=typer.colors.RED))
        raise typer.Exit(code=1)