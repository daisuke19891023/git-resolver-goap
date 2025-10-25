"""Git merge driver for structured JSON documents."""

from __future__ import annotations

import argparse
import importlib
import json
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from collections.abc import Callable, Sequence as TypingSequence

_MISSING = object()

_YamlFactory = Callable[..., Any]
_yaml_module = None
try:  # pragma: no cover - optional dependency
    _yaml_module = importlib.import_module("ruamel.yaml")
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _yaml_factory: _YamlFactory | None = None
else:  # pragma: no cover - optional dependency
    _yaml_factory = cast("_YamlFactory | None", getattr(_yaml_module, "YAML", None))


class _YamlLoader(Protocol):
    def load(self, stream: Any) -> Any:  # pragma: no cover - protocol definition
        """Load a YAML document."""


class MergeError(RuntimeError):
    """Raised when a structured merge cannot be completed cleanly."""


@dataclass(slots=True)
class MergeInputs:
    """Container for merge driver file paths."""

    base: Path
    current: Path
    other: Path


def merge_structured_documents(inputs: MergeInputs) -> bool:
    """Merge JSON documents, updating ``inputs.current`` on success."""
    original = inputs.current.read_text(encoding="utf-8")
    try:
        base = _load_document(inputs.base)
        current = _load_document(inputs.current)
        other = _load_document(inputs.other)
        merged = _merge_values(base, current, other)
    except MergeError:
        inputs.current.write_text(original, encoding="utf-8")
        return False
    except Exception as exc:  # pragma: no cover - safety net
        inputs.current.write_text(original, encoding="utf-8")
        message = "failed to load structured documents"
        raise MergeError(message) from exc

    _write_document(inputs.current, merged)
    return True


def main(argv: TypingSequence[str] | None = None) -> int:
    """Entry point for the git merge driver."""
    parser = argparse.ArgumentParser(description="GOAPGit JSON merge driver")
    parser.add_argument("base", help="Path to the common ancestor file")
    parser.add_argument("current", help="Path to the current branch file")
    parser.add_argument("other", help="Path to the other branch file")
    args = parser.parse_args(list(argv) if argv is not None else None)

    inputs = MergeInputs(Path(args.base), Path(args.current), Path(args.other))
    try:
        success = merge_structured_documents(inputs)
    except MergeError:
        return 1
    return 0 if success else 1


def _load_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        if _yaml_factory is None:
            message = f"invalid JSON document: {path}"
            raise MergeError(message) from error
        yaml_loader = cast("_YamlLoader", _yaml_factory(typ="safe"))
        data = yaml_loader.load(text)
        return _normalise(data)


def _write_document(path: Path, data: Any) -> None:
    normalised = _normalise(data)
    formatted = json.dumps(normalised, indent=2, ensure_ascii=False, sort_keys=False)
    path.write_text(f"{formatted}\n", encoding="utf-8")


def _normalise(value: Any) -> Any:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[Any, Any]", value)
        ordered: OrderedDict[str, Any] = OrderedDict()
        for key, nested in mapping.items():
            ordered[str(key)] = _normalise(nested)
        return ordered
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[Any]", value)
        return [_normalise(item) for item in sequence]
    return value


def _merge_values(base: Any, ours: Any, theirs: Any) -> Any:
    if _equal(ours, theirs):
        return ours
    if base is not _MISSING and _equal(base, ours):
        return theirs
    if base is not _MISSING and _equal(base, theirs):
        return ours
    if isinstance(ours, Mapping) and isinstance(theirs, Mapping):
        ours_map = cast("Mapping[str, Any]", ours)
        theirs_map = cast("Mapping[str, Any]", theirs)
        if isinstance(base, Mapping):
            base_map = cast("Mapping[str, Any]", base)
        elif base is _MISSING or base is None:
            base_map = cast("Mapping[str, Any]", {})
        else:
            message = "incompatible types during mapping merge"
            raise MergeError(message)
        return _merge_mappings(base_map, ours_map, theirs_map)
    if _is_sequence(ours) and _is_sequence(theirs):
        ours_seq = cast("Sequence[Any]", ours)
        theirs_seq = cast("Sequence[Any]", theirs)
        return _merge_sequences(base, ours_seq, theirs_seq)
    message = "conflicting changes in scalar value"
    raise MergeError(message)


def _merge_mappings(base: Mapping[str, Any], ours: Mapping[str, Any], theirs: Mapping[str, Any]) -> Mapping[str, Any]:
    merged: OrderedDict[str, Any] = OrderedDict()
    seen: set[str] = set()
    for source in (ours, theirs, base):
        for key in source:
            if key not in seen:
                seen.add(key)
                merged[key] = None
    for key in list(merged.keys()):
        base_value = base.get(key, _MISSING)
        our_value = ours.get(key, _MISSING)
        their_value = theirs.get(key, _MISSING)

        if our_value is _MISSING and their_value is _MISSING:
            merged.pop(key, None)
            continue
        if our_value is _MISSING:
            if base_value is _MISSING or _equal(base_value, their_value):
                merged[key] = their_value
                continue
            message = f"conflicting deletion for key: {key}"
            raise MergeError(message)
        if their_value is _MISSING:
            if base_value is _MISSING or _equal(base_value, our_value):
                merged[key] = our_value
                continue
            message = f"conflicting deletion for key: {key}"
            raise MergeError(message)
        merged_value = _merge_values(base_value, our_value, their_value)
        merged[key] = merged_value
    return merged


def _merge_sequences(base: Any, ours: Sequence[Any], theirs: Sequence[Any]) -> Sequence[Any]:
    base_seq: Sequence[Any] | object = base if _is_sequence(base) else _MISSING
    if base_seq is _MISSING and _equal(ours, theirs):
        return ours
    if base_seq is not _MISSING and _equal(ours, cast("Sequence[Any]", base_seq)):
        return theirs
    if base_seq is not _MISSING and _equal(theirs, cast("Sequence[Any]", base_seq)):
        return ours
    message = "conflicting list modifications"
    raise MergeError(message)


def _equal(left: Any, right: Any) -> bool:
    return left == right


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
