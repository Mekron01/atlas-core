import json
from pathlib import Path

class EventReader:
    def __init__(self, ledger_dir="atlas/ledger/events"):
        self.ledger_dir = Path(ledger_dir)

    def read_all(self):
        for file in sorted(self.ledger_dir.glob("*.jsonl")):
            with open(file, encoding="utf-8") as f:
                for line in f:
                    yield json.loads(line)
