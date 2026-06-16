"""The app's logger. Appends one JSON object per line to a log file — your
"log aggregation", such as it is. The log store reads this same file.
Override the path with the APP_LOG env var."""
import json
import os
import time


def log_path() -> str:
    return os.environ.get("APP_LOG") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.log"
    )


def emit(level: str, text: str) -> None:
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "level": level, "text": text}) + "\n")
