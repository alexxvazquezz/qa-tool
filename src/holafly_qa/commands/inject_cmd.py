"""Inject commands — manage and activate failure injection rules."""

import questionary
import typer

from holafly_qa.services.injection import (
    InjectionRule,
    add_rule,
    get_active_injection,
    get_rule,
    load_rules,
    remove_rule,
    start_injection,
    stop_injection,
)

inject_app = typer.Typer(
    name="inject",
    help="Manage and activate failure injection rules.",
    no_args_is_help=True,
)


@inject_app.command("list")
def list_rules() -> None:
    """Show all configured injection rules."""
    rules = load_rules()
    active = get_active_injection()

    if not rules:
        typer.echo(
            typer.style(
                "No rules defined. Run 'qa-tool inject add' to create one.",
                fg=typer.colors.YELLOW,
            )
        )
        return

    typer.echo("")
    typer.echo(typer.style("Injection rules:", bold=True))
    typer.echo("")

    for rule in rules:
        marker = "●" if rule.name == active else " "
        color = typer.colors.GREEN if rule.name == active else None

        name_display = typer.style(
            f"{marker} {rule.name}",
            fg=color,
            bold=(rule.name == active),
        )
        typer.echo(f"  {name_display}")
        typer.echo(f"      {rule.description}")

        method_display = rule.method or "ANY"
        if rule.action == "respond":
            typer.echo(f"      {method_display} {rule.endpoint} → {rule.status}")
        else:
            typer.echo(f"      {method_display} {rule.endpoint} → kill")
        typer.echo("")

    if active:
        typer.echo(
            typer.style(
                f"Active: {active}",
                fg=typer.colors.GREEN,
                bold=True,
            )
        )
    else:
        typer.echo("No rule currently active.")


@inject_app.command("start")
def start(rule_name: str = typer.Argument(..., help="Name of the rule to activate.")) -> None:
    """Activate a rule — restart mitmweb with the rule's failure script."""
    try:
        rule = start_injection(rule_name)
    except ValueError as e:
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style(f"✓ Injection active: {rule.name}", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  {rule.description}")
    typer.echo(f"  {rule.method or 'ANY'} {rule.endpoint}")
    if rule.action == "respond":
        typer.echo(f"  Action: respond with HTTP {rule.status}")
    else:
        typer.echo(f"  Action: kill connection")
    typer.echo("")
    typer.echo("Run 'qa-tool inject stop' to deactivate.")


@inject_app.command("stop")
def stop() -> None:
    """Deactivate the current injection — mitmweb returns to normal."""
    stopped = stop_injection()

    if stopped:
        typer.echo(
            typer.style(
                f"✓ Stopped injection: {stopped}",
                fg=typer.colors.GREEN,
                bold=True,
            )
        )
    else:
        typer.echo(
            typer.style(
                "No injection was active.",
                fg=typer.colors.YELLOW,
            )
        )


@inject_app.command("status")
def status() -> None:
    """Show which rule is currently active, if any."""
    active = get_active_injection()

    if active is None:
        typer.echo("No injection active.")
        return

    rule = get_rule(active)
    if rule is None:
        typer.echo(
            typer.style(
                f"Active rule '{active}' is no longer in the rules file.",
                fg=typer.colors.YELLOW,
            )
        )
        return

    typer.echo("")
    typer.echo(typer.style(f"● Active: {rule.name}", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"  {rule.description}")
    typer.echo(f"  {rule.method or 'ANY'} {rule.endpoint}")
    if rule.action == "respond":
        typer.echo(f"  Action: respond with HTTP {rule.status}")
    else:
        typer.echo(f"  Action: kill connection")


@inject_app.command("add")
def add() -> None:
    """Interactive wizard to create a new injection rule."""
    typer.echo("")
    typer.echo(typer.style("New injection rule", bold=True))
    typer.echo("")

    name = questionary.text(
        "Rule name (short identifier, e.g. 'payments_500'):",
        validate=lambda x: len(x) > 0 or "Name cannot be empty",
    ).ask()
    if name is None:
        raise typer.Exit(code=1)

    if get_rule(name) is not None:
        typer.echo(typer.style(f"✗ Rule '{name}' already exists.", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    description = questionary.text("Description (what this rule does):").ask()
    if description is None:
        raise typer.Exit(code=1)

    endpoint = questionary.text(
        "Endpoint path (supports {uuid}, {id}, {*}, {**}):",
        validate=lambda x: x.startswith("/") or "Endpoint must start with /",
    ).ask()
    if endpoint is None:
        raise typer.Exit(code=1)

    method = questionary.select(
        "HTTP method:",
        choices=["ANY", "GET", "POST", "PUT", "DELETE", "PATCH"],
    ).ask()
    if method is None:
        raise typer.Exit(code=1)
    if method == "ANY":
        method = ""

    action = questionary.select(
        "What should happen when a request matches?",
        choices=[
            "respond — return a fake HTTP response",
            "kill — drop the connection",
        ],
    ).ask()
    if action is None:
        raise typer.Exit(code=1)
    action = action.split(" ")[0]

    status_code = 500
    body = ""
    if action == "respond":
        status_str = questionary.text(
            "HTTP status code:",
            default="500",
            validate=lambda x: x.isdigit() or "Must be a number",
        ).ask()
        if status_str is None:
            raise typer.Exit(code=1)
        status_code = int(status_str)

        body = questionary.text(
            "Response body (JSON, or leave empty):",
            default='{"error": "Internal Server Error"}',
        ).ask()
        if body is None:
            raise typer.Exit(code=1)

    new_rule = InjectionRule(
        name=name,
        description=description,
        endpoint=endpoint,
        action=action,
        method=method,
        status=status_code,
        body=body,
    )

    try:
        add_rule(new_rule)
    except ValueError as e:
        typer.echo(typer.style(f"✗ {e}", fg=typer.colors.RED))
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo(typer.style(f"✓ Rule '{name}' added", fg=typer.colors.GREEN, bold=True))
    typer.echo(f"Run 'qa-tool inject start {name}' to activate it.")


@inject_app.command("remove")
def remove(
    name: str = typer.Argument(..., help="Name of the rule to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a rule from the rules file."""
    rule = get_rule(name)
    if rule is None:
        typer.echo(typer.style(f"Rule '{name}' not found.", fg=typer.colors.YELLOW))
        raise typer.Exit(code=1)

    if not yes:
        typer.echo(f"About to remove: {rule.name} — {rule.description}")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(code=0)

    remove_rule(name)
    typer.echo(typer.style(f"✓ Rule '{name}' removed", fg=typer.colors.GREEN, bold=True))