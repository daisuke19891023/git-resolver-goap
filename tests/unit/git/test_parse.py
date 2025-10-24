from __future__ import annotations

from pathlib import Path
import textwrap

from goapgit.core.models import ConflictType
from goapgit.git.parse import parse_conflict_markers, parse_merge_tree_conflicts


def test_parse_conflict_markers_counts_hunks(tmp_path: Path) -> None:
    """Parse a JSON conflict file and count zdiff3 hunks."""
    workspace = Path(tmp_path)
    conflict_file = workspace / "conflict.json"
    conflict_file.write_text(
        textwrap.dedent(
            """
            <<<<<<< ours
            value: 1
            ||||||| base
            value: 0
            =======
            value: 2
            >>>>>>> theirs
            <<<<<<< ours
            other
            =======
            other theirs
            >>>>>>> theirs
            """,
        ).strip(),
        encoding="utf-8",
    )

    detail = parse_conflict_markers(workspace, "conflict.json")

    assert detail.hunk_count == 2
    assert detail.ctype is ConflictType.json


def test_parse_conflict_markers_yaml_type(tmp_path: Path) -> None:
    """Detect YAML conflict file type."""
    workspace = Path(tmp_path)
    conflict_file = workspace / "conflict.yaml"
    conflict_file.write_text(
        textwrap.dedent(
            """
            <<<<<<< ours
            =======
            >>>>>>> theirs
            """,
        ).strip(),
        encoding="utf-8",
    )

    detail = parse_conflict_markers(workspace, "conflict.yaml")

    assert detail.hunk_count == 1
    assert detail.ctype is ConflictType.yaml


def test_parse_merge_tree_conflicts_extracts_paths() -> None:
    """Extract conflicting paths from merge-tree output."""
    output = textwrap.dedent(
        """
        751a4a450175b6ad2f8b86f0eed4b213927fc999
        100644 df967b96a579e45a18b8251732d16804b2e56a55 1       file.txt

        Auto-merging file.txt
        CONFLICT (content): Merge conflict in file.txt
        Auto-merging nested/path.json
        CONFLICT (content): Merge conflict in nested/path.json
        """,
    ).strip()

    conflicts = parse_merge_tree_conflicts(output)

    assert conflicts == {"file.txt", "nested/path.json"}
