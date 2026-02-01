import json
import os
import threading
from datetime import datetime
from pathlib import Path

class EventWriter:
    def __init__(self, ledger_dir="atlas/ledger/events"):
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _event_file(self):
        date = datetime.utcnow().strftime("%Y-%m-%d")
        return self.ledger_dir / f"{date}.jsonl"

    def append(self, event: dict):
        if "event_id" not in event or "event_type" not in event:
            raise ValueError("Invalid event envelope")

        line = json.dumps(event, ensure_ascii=False)

        with self._lock:
            path = self._event_file()
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
