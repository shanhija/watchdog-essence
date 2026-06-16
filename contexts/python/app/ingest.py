"""Tiny data-ingest job — the service the watchdog watches (and will patch).

It sums the prices in a batch of records. BUG: it assumes every record has a
'price', so records that don't are dropped (and an error is logged for each).
"""
from app.applog import emit
from app.records import RECORDS


def process(records):
    total = 0.0
    processed = 0
    for r in records:
        try:
            price = r["price"]
        except KeyError:
            emit("ERROR", f'KeyError: "price" while processing record id={r["id"]} (app/ingest.py)')
            continue  # the record is dropped — that's the bug
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
