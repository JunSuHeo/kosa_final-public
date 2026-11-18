import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "calculator.py"
SPEC = importlib.util.spec_from_file_location("demo_calculator", MODULE_PATH)
calculator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calculator)


class AdditionTests(unittest.TestCase):
    def test_positive_numbers(self):
        self.assertEqual(calculator.add(3, 5), 8)

    def test_negative_numbers(self):
        self.assertEqual(calculator.add(-7, -4), -11)
        self.assertEqual(calculator.add(-7, 4), -3)

    def test_zero_and_cancellation(self):
        self.assertEqual(calculator.add(0, 0), 0)
        self.assertEqual(calculator.add(12, -12), 0)

    def test_large_integer_has_no_overflow(self):
        self.assertEqual(calculator.add(10**30, 1), 10**30 + 1)


if __name__ == "__main__":
    unittest.main()
