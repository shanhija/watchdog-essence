import unittest

from app.ingest import process


class IngestTests(unittest.TestCase):
    def test_sums_known_prices(self):
        total, processed = process([{"id": 1, "price": 10.0}, {"id": 2, "price": 5.0}])
        self.assertEqual(total, 15.0)
        self.assertEqual(processed, 2)


if __name__ == "__main__":
    unittest.main()
