"""Append and read calculator history in JSON Lines format."""

from datetime import datetime, timezone
import json
import math
from pathlib import Path


class HistoryError(ValueError):
    """A history file cannot be read, written, or interpreted."""


def _validate(record):
    if not isinstance(record, dict) or set(record) != {
        "operation", "a", "b", "result", "timestamp"
    }:
        raise ValueError("expected operation, a, b, result and timestamp")
    if record["operation"] not in ("add", "subtract", "multiply", "divide"):
        raise ValueError("unknown operation")
    for field in ("a", "b", "result"):
        value = record[field]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
    if not isinstance(record["timestamp"], str):
        raise ValueError("timestamp must be an ISO 8601 UTC string")
    timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    if timestamp.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("timestamp must use UTC")


def append_history(path, operation, a, b, result):
    """Append one successful calculation; create the file if necessary."""
    record = {
        "operation": operation, "a": a, "b": b, "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _validate(record)
        line = json.dumps(record, allow_nan=False) + "\n"
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(line)
    except (OSError, ValueError, OverflowError) as error:
        raise HistoryError(f"Cannot write history '{path}': {error}") from error


def read_history(path):
    """Return validated records in file order, without altering the file."""
    records = []
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, start=1):
                try:
                    record = json.loads(line)
                    _validate(record)
                except (ValueError, TypeError, OverflowError) as error:
                    raise HistoryError(
                        f"Invalid history '{path}' at line {number}: {error}"
                    ) from error
                records.append(record)
    except (OSError, UnicodeError) as error:
        raise HistoryError(f"Cannot read history '{path}': {error}") from error
    return records
