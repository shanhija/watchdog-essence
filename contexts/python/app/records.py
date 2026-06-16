"""A fixed batch of input records the ingest job processes. Two of them
(100102, 100104) are missing a 'price' field — that's what trips the bug."""
RECORDS = [
    {"id": 100101, "name": "alpha", "price": 9.99},
    {"id": 100102, "name": "bravo"},
    {"id": 100103, "name": "charlie", "price": 4.50},
    {"id": 100104, "name": "delta"},
    {"id": 100105, "name": "echo", "price": 12.00},
]
