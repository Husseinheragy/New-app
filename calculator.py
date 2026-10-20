"""A small calculator using only the Python standard library."""

import argparse
import json

from history import HistoryError, append_history, read_history


def add(a: float, b: float) -> float:
    """Return the sum of two numbers."""
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


def multiply(a: float, b: float) -> float:
    """Return the product of two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Divide a by b, raising ValueError when b is zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


def main() -> None:
    """Parse command-line arguments and print the result."""
    operations = {"add": add, "subtract": subtract,
                  "multiply": multiply, "divide": divide}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-file", metavar="PATH", help="save or read JSON Lines history")
    parser.add_argument("operation", choices=[*operations, "history"])
    parser.add_argument("a", type=float, nargs="?")
    parser.add_argument("b", type=float, nargs="?")
    args = parser.parse_args()
    if args.operation == "history":
        if args.a is not None or args.b is not None:
            parser.error("history does not accept operands")
        if args.history_file is None:
            parser.error("history requires --history-file PATH")
        try:
            records = read_history(args.history_file)
        except HistoryError as error:
            parser.error(str(error))
        for record in records:
            print(json.dumps(record, allow_nan=False))
        return
    if args.a is None or args.b is None:
        parser.error("calculation requires two operands")
    try:
        result = operations[args.operation](args.a, args.b)
    except ValueError as error:
        parser.error(str(error))
    if args.history_file is not None:
        try:
            append_history(args.history_file, args.operation, args.a, args.b, result)
        except HistoryError as error:
            parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
