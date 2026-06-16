#!/usr/bin/env python3
"""Run the ingest job once. It processes the record batch and writes its logs
(including the errors caused by the bug) to app.log."""
from app.ingest import main

if __name__ == "__main__":
    main()
