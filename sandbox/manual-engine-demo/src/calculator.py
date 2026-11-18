"""Small integer-addition CLI for exercising the manual coding workflow."""

import argparse


def add(left: int, right: int) -> int:
    return left + right


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add two integers.")
    parser.add_argument("left", type=int)
    parser.add_argument("right", type=int)
    arguments = parser.parse_args(argv)
    print(add(arguments.left, arguments.right))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
