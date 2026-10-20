"""History storage and CLI behavior, isolated in temporary directories."""

from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from history import HistoryError, append_history, read_history


SCRIPT = Path(__file__).resolve().parents[1] / "calculator.py"


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "history.jsonl"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=self.directory, capture_output=True, text=True, check=False,
        )

    def assert_cli_error(self, result, message):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_successful_record_and_utc_timestamp(self):
        result = self.cli("add", "2", "3", "--history-file", self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "5.0\n")
        record, = read_history(self.path)
        self.assertEqual(set(record), {"operation", "a", "b", "result", "timestamp"})
        self.assertEqual([record[k] for k in ("operation", "a", "b", "result")],
                         ["add", 2, 3, 5])
        self.assertEqual(datetime.fromisoformat(record["timestamp"]).utcoffset(),
                         timedelta(0))

    def test_sequential_records_and_display_order(self):
        for operation in ("add", "subtract", "multiply", "divide"):
            result = self.cli("--history-file", self.path, operation, "8", "2")
            self.assertEqual(result.returncode, 0, result.stderr)
        records = read_history(self.path)
        self.assertEqual([r["result"] for r in records], [10, 6, 16, 4])
        before = self.path.read_bytes()
        result = self.cli("history", "--history-file", self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(line) for line in result.stdout.splitlines()], records)
        self.assertEqual(self.path.read_bytes(), before)

    def test_no_history_by_default(self):
        result = self.cli("add", "2", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "5.0\n")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_failed_calculations_do_not_create_history(self):
        for args in (("divide", "1", "0"), ("add", "bad", "2"), ("add", "1")):
            with self.subTest(args=args):
                result = self.cli(*args, "--history-file", self.path)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.path.exists())

    def test_failure_preserves_existing_history(self):
        append_history(self.path, "add", 1, 2, 3)
        before = self.path.read_bytes()
        self.assert_cli_error(self.cli("divide", "1", "0", "--history-file", self.path),
                              "Cannot divide by zero")
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_json_and_invalid_records(self):
        for content in ('{broken}\n', '{}\n', '[]\n', '\n'):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                self.assert_cli_error(self.cli("history", "--history-file", self.path),
                                      "line 1")
                self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_corrupt_later_line_has_no_partial_output(self):
        append_history(self.path, "add", 1, 2, 3)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write("broken\n")
        self.assert_cli_error(self.cli("history", "--history-file", self.path), "line 2")

    def test_invalid_encoding(self):
        self.path.write_bytes(b'\xff\n')
        self.assert_cli_error(self.cli("history", "--history-file", self.path),
                              "Cannot read history")

    def test_missing_and_empty_files(self):
        self.assert_cli_error(self.cli("history", "--history-file", self.path),
                              "Cannot read history")
        self.assertFalse(self.path.exists())
        self.path.touch()
        result = self.cli("history", "--history-file", self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_file_access_errors_in_cli(self):
        self.assert_cli_error(self.cli("history", "--history-file", self.directory),
                              "Cannot read history")
        self.assert_cli_error(self.cli("add", "1", "2", "--history-file", self.directory),
                              "Cannot write history")
        self.assert_cli_error(self.cli("add", "1", "2", "--history-file",
                                       self.directory / "missing" / "history.jsonl"),
                              "Cannot write history")

    def test_permission_denied_read_and_write(self):
        # Mock permissions so this check also works when run as root.
        with patch("history.Path.open", side_effect=PermissionError("Permission denied")):
            with self.assertRaisesRegex(HistoryError, "Cannot read history.*Permission denied"):
                read_history(self.path)
            with self.assertRaisesRegex(HistoryError, "Cannot write history.*Permission denied"):
                append_history(self.path, "add", 1, 2, 3)

    def test_history_argument_validation(self):
        self.assert_cli_error(self.cli("history"), "requires --history-file")
        self.assert_cli_error(self.cli("history", "1", "2", "--history-file", self.path),
                              "does not accept operands")
        self.assertFalse(self.path.exists())

    def test_nonfinite_calculation_is_not_recorded(self):
        self.assert_cli_error(self.cli("multiply", "1e308", "1e308", "--history-file", self.path),
                              "finite number")
        self.assertFalse(self.path.exists())

    def test_invalid_timestamp_and_values(self):
        append_history(self.path, "add", 1, 2, 3)
        original = read_history(self.path)[0]
        for changes in ({"timestamp": "bad"}, {"timestamp": "2026-01-01T00:00:00"},
                        {"timestamp": "2026-01-01T00:00:00+02:00"},
                        {"a": True}, {"result": float("nan")}, {"operation": "unknown"}):
            with self.subTest(changes=changes):
                self.path.write_text(json.dumps({**original, **changes}) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(HistoryError, "line 1"):
                    read_history(self.path)


if __name__ == "__main__":
    unittest.main()
