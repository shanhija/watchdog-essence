"""The fix the (fake) coding agent applies for each known incident slug — keyed
by slug, value is {repo_path: new_file_contents}. A REAL coding agent generates
these by reading the code; this fake just looks them up so the demo needs no LLM."""

_INGEST_FIXED = '''\
"""Tiny data-ingest job — the service the watchdog watches (and will patch).

It sums the prices in a batch of records. Missing 'price' is treated as 0.0 so
no record is dropped.
"""
from app.applog import emit
from app.records import RECORDS


def process(records):
    total = 0.0
    processed = 0
    for r in records:
        price = r.get("price", 0.0)
        total += price
        processed += 1
    return total, processed


def main():
    emit("INFO", "ingest: starting batch")
    total, processed = process(RECORDS)
    emit("INFO", f"ingest: done total={total} processed={processed}/{len(RECORDS)}")
    return total, processed


if __name__ == "__main__":
    main()
'''

_TEST_FIXED = '''\
import unittest

from app.ingest import process


class IngestTests(unittest.TestCase):
    def test_sums_known_prices(self):
        total, processed = process([{"id": 1, "price": 10.0}, {"id": 2, "price": 5.0}])
        self.assertEqual(total, 15.0)
        self.assertEqual(processed, 2)

    def test_missing_price_is_kept_not_dropped(self):
        total, processed = process([{"id": 1}, {"id": 2, "price": 5.0}])
        self.assertEqual(processed, 2)
        self.assertEqual(total, 5.0)


if __name__ == "__main__":
    unittest.main()
'''

CANNED_FIXES = {
    "ingest-price-keyerror": {
        "app/ingest.py": _INGEST_FIXED,
        "app/tests/test_ingest.py": _TEST_FIXED,
    },
}
