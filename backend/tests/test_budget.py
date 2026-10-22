import unittest
from fastapi import HTTPException
from app.main import extract_usd_budget

class BudgetParsingTests(unittest.TestCase):
    def test_parses_usd_budget_with_commas(self):
        self.assertEqual(extract_usd_budget("Find headphones under $1,299 with good reviews"), 1299.0)

    def test_parses_budget_phrase(self):
        self.assertEqual(extract_usd_budget("I have a budget of USD 80 for a keyboard"), 80.0)

    def test_does_not_silently_treat_rupees_as_usd(self):
        with self.assertRaises(HTTPException) as error:
            extract_usd_budget("Find headphones under ₹8,000")
        self.assertEqual(error.exception.status_code, 422)

    def test_missing_budget(self):
        self.assertIsNone(extract_usd_budget("Find wireless headphones with good battery life"))

    def test_follow_up_budget_uses_last_explicit_limit(self):
        self.assertEqual(
            extract_usd_budget("Initial request under $80; now show alternatives under $50"),
            50.0,
        )

if __name__ == "__main__":
    unittest.main()
