"""Parsing utilities for git output and conflict markers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from goapgit.core.models import ConflictDetail, ConflictType

if TYPE_CHECKING:
    from goapgit.git.facade import GitFacade


def parse_conflict_markers(repo_path: Path, path: str) -> ConflictDetail:
    """Inspect a conflicted file and estimate hunk count and conflict type."""
    root = Path(repo_path)
    file_path = root / path
    hunk_count = 0
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.startswith("<<<<<<<"):
                    hunk_count += 1
    except OSError:
        hunk_count = 0
    conflict_type = _detect_conflict_type(path)
    return ConflictDetail(path=path, hunk_count=hunk_count, ctype=conflict_type)


def _detect_conflict_type(path: str) -> ConflictType:
    lowered = path.lower()
    if lowered.endswith(".json"):
        return ConflictType.json
    if lowered.endswith((".yaml", ".yml")):
        return ConflictType.yaml
    if lowered.endswith(".lock"):
        return ConflictType.lock
    return ConflictType.text


def parse_merge_tree_conflicts(output: str) -> set[str]:
    """Parse `git merge-tree --write-tree` output into a conflict set."""
    conflicts: set[str] = set()
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("CONFLICT") and " in " in stripped:
            _, path = stripped.rsplit(" in ", 1)
            conflicts.add(path.strip())
    return conflicts


def predict_merge_conflicts(
    facade: GitFacade, ours: str, theirs: str,
) -> set[str]:
    """Run git merge-tree and predict the conflicted paths."""
    result = facade.run(
        ["git", "merge-tree", "--write-tree", ours, theirs],
        capture_output=True,
        check=False,
    )
    stdout = result.stdout or ""
    return parse_merge_tree_conflicts(stdout)


__all__ = [
    "parse_conflict_markers",
    "parse_merge_tree_conflicts",
    "predict_merge_conflicts",
]
