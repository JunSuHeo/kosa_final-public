from pathlib import Path
import subprocess
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "src" / "calculator.py"


class CalculatorCLITests(unittest.TestCase):
    def execute(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *arguments],
            cwd=PROJECT, text=True, capture_output=True, timeout=10, check=False,
        )

    def test_addition_output(self):
        result = self.execute("3", "5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "8\n")
        self.assertEqual(result.stderr, "")

    def test_negative_input(self):
        result = self.execute("-8", "3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "-5\n")

    def test_missing_argument(self):
        result = self.execute("3")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("required", result.stderr)

    def test_invalid_integer(self):
        result = self.execute("hello", "5")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid int value", result.stderr)


if __name__ == "__main__":
    unittest.main()
