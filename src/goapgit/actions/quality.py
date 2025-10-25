"""Quality and explainability related git actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goapgit.git.facade import GitCommandError

if TYPE_CHECKING:
    from pathlib import Path
    from goapgit.git.facade import GitFacade
    from goapgit.io.logging import StructuredLogger


def explain_range_diff(
    facade: GitFacade,
    logger: StructuredLogger,
    before_range: str,
    after_range: str,
    *,
    output_path: Path | None = None,
) -> str:
    """Run ``git range-diff`` and return its textual summary."""
    command = ["git", "range-diff", before_range, after_range]
    result = facade.run(command, check=False)
    summary = (result.stdout or "").strip()

    logger.info(
        "computed range diff",
        before=before_range,
        after=after_range,
        returncode=result.returncode,
        summary=summary,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = result.stdout or ""
        if content and not content.endswith("\n"):
            content = f"{content}\n"
        output_path.write_text(content, encoding="utf-8")

    if result.returncode != 0:
        raise GitCommandError(command, result.returncode, result.stdout or "", result.stderr or "")

    return result.stdout or ""


__all__ = ["explain_range_diff"]
