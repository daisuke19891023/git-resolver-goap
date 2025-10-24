"""Structured logging utilities."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from typing import Any, TextIO


class StructuredLogger:
    """Simple structured logger supporting JSON lines and text output."""

    def __init__(self, *, name: str, json_mode: bool = False, stream: TextIO | None = None) -> None:
        """Initialise the structured logger."""
        self._name = name
        self._json_mode = json_mode
        self._stream: TextIO = stream or _default_stream()

    @property
    def name(self) -> str:
        """Return the logger name."""
        return self._name

    @property
    def json_mode(self) -> bool:
        """Return whether JSON mode is enabled."""
        return self._json_mode

    def debug(self, message: str, **fields: Any) -> None:
        """Log a DEBUG-level message."""
        self._emit("DEBUG", message, fields)

    def info(self, message: str, **fields: Any) -> None:
        """Log an INFO-level message."""
        self._emit("INFO", message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        """Log a WARNING-level message."""
        self._emit("WARNING", message, fields)

    def error(self, message: str, **fields: Any) -> None:
        """Log an ERROR-level message."""
        self._emit("ERROR", message, fields)

    def _emit(self, level: str, message: str, fields: dict[str, Any]) -> None:
        timestamp = datetime.now(UTC).isoformat()
        if self._json_mode:
            payload: dict[str, Any] = {
                "timestamp": timestamp,
                "level": level,
                "logger": self._name,
                "message": message,
            }
            payload.update(fields)
            self._stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        else:
            line = f"[{timestamp}] {level:<7} {self._name}: {message}"
            if fields:
                extras = " ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in fields.items())
                line = f"{line} | {extras}"
            self._stream.write(line + "\n")
        self._stream.flush()


def _default_stream() -> TextIO:
    import sys

    return sys.stdout


__all__ = ["StructuredLogger"]
