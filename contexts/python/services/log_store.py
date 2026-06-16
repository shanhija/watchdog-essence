"""Log store — reads the JSON-lines log the app writes. Your real log
aggregation (Loki/CloudWatch/ELK/...) goes here instead. ESSENCE §4A."""
import json
import os


class FileLogStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def fetch(self, since: float = 0.0, until: float | None = None) -> list[dict]:
        hi = float("inf") if until is None else until
        out: list[dict] = []
        if not os.path.exists(self.path):
            return out
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if since <= rec.get("ts", 0.0) <= hi:
                    out.append(rec)
        return out
