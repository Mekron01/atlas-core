import os
import hashlib
import time
from pathlib import Path
from atlas.ledger.writer import EventWriter

class FilesystemEye:
    def __init__(self, writer: EventWriter):
        self.writer = writer

    def observe(self, root: str):
        root = Path(root)
        for path in root.rglob("*"):
            if not path.is_file():
                continue

            try:
                size = path.stat().st_size
                with open(path, "rb") as f:
                    data = f.read(4096)
                    h = hashlib.sha256(data).hexdigest()

                event = {
                    "event_id": f"fs-{h}",
                    "event_type": "ARTIFACT_SEEN",
                    "ts": time.time(),
                    "actor": {"module": "FilesystemEye"},
                    "artifact_id": h,
                    "confidence": 0.95,
                    "payload": {
                        "path": str(path),
                        "size": size,
                        "hash": h
                    }
                }
                self.writer.append(event)

            except Exception as e:
                continue
