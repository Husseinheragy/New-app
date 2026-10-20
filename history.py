"""Append and read calculator history in JSON Lines format."""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile


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
    if not isinstance(record["timestamp"], str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)", record["timestamp"]
    ):
        raise ValueError("timestamp must be an ISO 8601 UTC string")
    timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    if timestamp.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("timestamp must use UTC")


def _unique_pairs(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"duplicate JSON key: {key}")
        record[key] = value
    return record


def _invalid_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


def append_history(path, operation, a, b, result):
    """Replace history atomically after closing a complete temporary copy.

    This is a single-writer operation, not a concurrent append protocol.
    """
    record = {
        "operation": operation, "a": a, "b": b, "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    temporary_path = None
    try:
        _validate(record)
        line = (json.dumps(record, allow_nan=False) + "\n").encode("utf-8")
        target = Path(path)
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            metadata = None
        original = b""
        if metadata is not None:
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("history must be a regular file, not a symlink or directory")
            if metadata.st_uid != os.geteuid():
                raise ValueError("history must be owned by the current user")
            read_history(target)
            original = target.read_bytes()
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=".calculator-history-", delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(original)
            if original and not original.endswith(b"\n"):
                stream.write(b"\n")
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        # The temporary copy stays private (0600) throughout writing/closing.
        # Keep it private even when the source has group/other read permissions.
        # This also avoids broadening access when source ACLs are restrictive.
        if metadata is not None:
            os.chmod(temporary_path, stat.S_IMODE(metadata.st_mode) & 0o600)
        os.replace(temporary_path, target)
        temporary_path = None
    except (OSError, ValueError, OverflowError) as error:
        raise HistoryError(f"Cannot write history '{path}': {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as error:
                raise HistoryError(
                    f"Cannot clean temporary history '{temporary_path}': {error}"
                ) from error


def read_history(path):
    """Return validated records in file order, without altering the file."""
    records = []
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, start=1):
                try:
                    record = json.loads(
                        line, object_pairs_hook=_unique_pairs,
                        parse_constant=_invalid_constant,
                    )
                    _validate(record)
                except (ValueError, TypeError, OverflowError, RecursionError) as error:
                    raise HistoryError(
                        f"Invalid history '{path}' at line {number}: {error}"
                    ) from error
                records.append(record)
    except (OSError, UnicodeError) as error:
        raise HistoryError(f"Cannot read history '{path}': {error}") from error
    return records
