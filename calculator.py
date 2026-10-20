"""A small calculator using only the Python standard library."""

import argparse


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
    parser.add_argument("operation", choices=operations)
    parser.add_argument("a", type=float)
    parser.add_argument("b", type=float)
    args = parser.parse_args()
    try:
        result = operations[args.operation](args.a, args.b)
    except ValueError as error:
        parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
