"""Unit and command-line tests for the calculator."""

from pathlib import Path
import subprocess
import sys
import unittest

from calculator import add, subtract, multiply, divide


class CalculatorTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
        self.assertAlmostEqual(add(0.1, 0.2), 0.3)

    def test_subtract(self):
        self.assertEqual(subtract(2, 5), -3)
        self.assertEqual(subtract(-2, -5), 3)

    def test_multiply(self):
        self.assertEqual(multiply(-3, 4), -12)
        self.assertEqual(multiply(7, 0), 0)

    def test_divide(self):
        self.assertEqual(divide(7, 2), 3.5)
        self.assertEqual(divide(0, 2), 0)
        self.assertEqual(divide(-6, 2), -3)

    def test_divide_by_zero(self):
        for zero in (0, 0.0, -0.0):
            with self.subTest(zero=zero):
                with self.assertRaisesRegex(ValueError, "Cannot divide by zero"):
                    divide(5, zero)


class CommandLineTests(unittest.TestCase):
    def run_calculator(self, *args):
        script = Path(__file__).resolve().parents[1] / "calculator.py"
        return subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True, text=True, check=False,
        )

    def test_operations(self):
        for operation, expected in (
            ("add", "10.0"), ("subtract", "6.0"),
            ("multiply", "16.0"), ("divide", "4.0"),
        ):
            with self.subTest(operation=operation):
                result = self.run_calculator(operation, "8", "2")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_zero_division_error(self):
        result = self.run_calculator("divide", "1", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot divide by zero", result.stderr)

    def test_invalid_arguments(self):
        for args in (("unknown", "1", "2"), ("add", "text", "2"), ("add", "1")):
            with self.subTest(args=args):
                result = self.run_calculator(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
