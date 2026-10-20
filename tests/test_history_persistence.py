"""Regression checks for atomic single-writer persistence and strict JSON."""

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from history import HistoryError, append_history, read_history


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "history.jsonl"
        append_history(self.path, "add", 1, 2, 3)
        self.original = self.path.read_bytes()

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_empty_newline_and_no_newline_files(self):
        for content in (b"", self.original, self.original.rstrip(b"\n")):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                append_history(self.path, "multiply", 3, 4, 12)
                records = read_history(self.path)
                self.assertEqual([r["result"] for r in records],
                                 [3, 12] if content else [12])
                self.assertTrue(self.path.read_bytes().startswith(content))
                self.assert_no_temporary_files()

    def exercise_stream_failure(self, failure):
        factory = tempfile.NamedTemporaryFile
        path = self.path
        original = self.original
        owner = self

        class FaultyStream:
            def __init__(self, *args, **kwargs):
                self.stream = factory(*args, **kwargs)
                self.name = self.stream.name

            def __enter__(self):
                return self

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def write(self, data):
                if failure == "write":
                    self.stream.write(data[:5])
                    raise OSError("simulated partial write")
                return self.stream.write(data)

            def flush(self):
                if failure == "flush":
                    raise OSError("simulated flush failure")
                return self.stream.flush()

            def __exit__(self, *args):
                owner.assertEqual(path.read_bytes(), original)
                self.stream.close()
                if failure == "close":
                    raise OSError("simulated close failure")

        with patch("history.tempfile.NamedTemporaryFile", FaultyStream):
            with self.assertRaisesRegex(HistoryError, "simulated"):
                append_history(self.path, "subtract", 5, 1, 4)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assert_no_temporary_files()
        append_history(self.path, "subtract", 5, 1, 4)
        self.assertEqual([r["result"] for r in read_history(self.path)], [3, 4])
        self.assert_no_temporary_files()

    def test_partial_write_preserves_original_and_allows_retry(self):
        self.exercise_stream_failure("write")

    def test_close_failure_preserves_original_and_allows_retry(self):
        self.exercise_stream_failure("close")

    def test_flush_failure_preserves_original_and_allows_retry(self):
        self.exercise_stream_failure("flush")

    def test_replace_failure_preserves_original_and_allows_retry(self):
        def fail(source, target):
            self.assertEqual(Path(source).parent, self.path.parent)
            self.assertEqual(Path(target).read_bytes(), self.original)
            self.assertEqual(len(read_history(source)), 2)
            raise OSError("simulated replace failure")

        with patch("history.os.replace", side_effect=fail):
            with self.assertRaisesRegex(HistoryError, "replace failure"):
                append_history(self.path, "add", 4, 5, 9)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assert_no_temporary_files()
        append_history(self.path, "add", 4, 5, 9)
        self.assertEqual([r["result"] for r in read_history(self.path)], [3, 9])

    def test_fsync_or_chmod_failure_preserves_original(self):
        for name in ("history.os.fsync", "history.os.chmod"):
            with self.subTest(name=name), patch(name, side_effect=OSError("simulated failure")):
                with self.assertRaises(HistoryError):
                    append_history(self.path, "add", 1, 2, 3)
            self.assertEqual(self.path.read_bytes(), self.original)
            self.assert_no_temporary_files()

    def test_failed_first_write_does_not_create_target(self):
        self.path.unlink()
        with patch("history.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaises(HistoryError):
                append_history(self.path, "add", 1, 2, 3)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_replacement_occurs_after_close(self):
        factory = tempfile.NamedTemporaryFile
        replace = os.replace
        streams = []

        def create(*args, **kwargs):
            stream = factory(*args, **kwargs)
            streams.append(stream)
            self.assertEqual(Path(stream.name).parent, self.path.parent)
            self.assertEqual(stat.S_IMODE(os.fstat(stream.fileno()).st_mode), 0o600)
            return stream

        def inspect(source, target):
            self.assertTrue(streams[0].closed)
            self.assertEqual(self.path.read_bytes(), self.original)
            self.assertEqual([r["result"] for r in read_history(source)], [3, 9])
            return replace(source, target)

        with patch("history.tempfile.NamedTemporaryFile", side_effect=create), \
                patch("history.os.replace", side_effect=inspect):
            append_history(self.path, "add", 4, 5, 9)
        self.assert_no_temporary_files()

    def test_permissions_never_broaden(self):
        for mode in (0o600, 0o640, 0o644, 0o400):
            with self.subTest(mode=oct(mode)):
                self.path.chmod(0o600)
                self.path.write_bytes(self.original)
                self.path.chmod(mode)
                append_history(self.path, "add", 1, 2, 3)
                self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), mode & 0o600)
        self.path.chmod(0o600)

    def test_new_file_is_private(self):
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_symlink_is_rejected_without_modifying_target(self):
        link = self.root / "link.jsonl"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(HistoryError, "regular file"):
            append_history(link, "add", 1, 2, 3)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(link.is_symlink())

    def test_invalid_existing_file_is_not_replaced(self):
        self.path.write_bytes(b"broken\n")
        with self.assertRaisesRegex(HistoryError, "line 1"):
            append_history(self.path, "add", 1, 2, 3)
        self.assertEqual(self.path.read_bytes(), b"broken\n")
        self.assert_no_temporary_files()

    def test_duplicate_keys_even_with_equal_values(self):
        for value in (3, 999):
            content = self.original.decode().rstrip()[:-1] + f', "result": {value}}}\n'
            self.path.write_text(content, encoding="utf-8")
            with self.subTest(value=value), self.assertRaisesRegex(HistoryError, "duplicate JSON key"):
                read_history(self.path)

    def test_all_nonfinite_json_constants(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e999"):
            record = json.loads(self.original)
            content = json.dumps(record).replace('"result": 3', '"result": ' + value)
            self.path.write_text(content + "\n", encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(HistoryError):
                read_history(self.path)

    def test_strict_timestamps_and_previous_format(self):
        for value, valid in (
            ("2026-01-01T00:00:00+00:00", True),
            ("2026-01-01T00:00:00.123456+00:00", True),
            ("2026-01-01T00:00:00Z", True),
            ("2026-01-01T00:00:00.1Z", True),
            ("2026-01-01X00:00:00+00:00", False),
            ("2026-01-01 00:00:00+00:00", False),
            ("2026-01-01T00:00:00-00:00", False),
            ("2026-02-30T00:00:00Z", False),
            ("2026-01-01T00:00:00.1234567Z", False),
            (None, False), (42, False), ([], False), ({}, False),
        ):
            with self.subTest(timestamp=value):
                record = json.loads(self.original)
                record["timestamp"] = value
                self.path.write_text(json.dumps(record) + "\n", encoding="utf-8")
                if valid:
                    self.assertEqual(read_history(self.path)[0], record)
                else:
                    with self.assertRaisesRegex(HistoryError, "line 1"):
                        read_history(self.path)
