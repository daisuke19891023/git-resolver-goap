"""CLI entry point for goapgit built with Typer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

from goapgit.cli.diagnose import DiagnoseError, generate_diagnosis, report_to_json

if TYPE_CHECKING:
    from collections.abc import Sequence


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def cli_root() -> None:
    """Top-level CLI group for goapgit."""


@app.command("diagnose")
def diagnose_command(
    pretty: bool = typer.Option(default=False, help="Pretty-print JSON output."),
) -> None:
    """Inspect git configuration and repository size information."""
    try:
        report = generate_diagnosis(Path.cwd())
    except DiagnoseError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    output = report_to_json(report, pretty=pretty)
    typer.echo(output)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the goapgit CLI and return the exit status."""
    command = typer.main.get_command(app)
    try:
        command.main(args=list(argv or []), prog_name="goapgit", standalone_mode=False)
    except SystemExit as exc:  # pragma: no cover - Typer propagates exit codes via SystemExit
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI invocation
    raise SystemExit(main())
