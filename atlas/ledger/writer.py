"""
Atlas Event Writer

Append-only event log writer with fsync for durability.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from atlas.ledger.validator import validate_strict


class EventWriter:
    """
    Writes events to append-only ledger files.

    Rules:
    - One file per day (YYYY-MM-DD.jsonl)
    - fsync after every write for durability
    - Thread-safe with locking
    - Optional strict validation
    """

    def __init__(
        self,
        ledger_dir: str = "atlas/ledger/events",
        strict: bool = False,
    ):
        """
        Initialize event writer.

        Args:
            ledger_dir: Directory for event files
            strict: If True, validate events before writing
        """
        self.ledger_dir = Path(ledger_dir)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        self.strict = strict
        self._lock = threading.Lock()

    def _event_file(self) -> Path:
        """Get current date's event file path."""
        date = datetime.utcnow().strftime("%Y-%m-%d")
        return self.ledger_dir / f"{date}.jsonl"

    def append(self, event: dict) -> None:
        """
        Append event to ledger.

        Args:
            event: Event dictionary with envelope fields

        Raises:
            ValueError: If event is invalid
        """
        # Basic validation (always)
        if "event_id" not in event or "event_type" not in event:
            raise ValueError("Invalid event envelope")

        # Strict validation (optional)
        if self.strict:
            result = validate_strict(event)
            if not result.valid:
                errors = "; ".join(
                    f"{e.path}: {e.message}" for e in result.errors
                )
                raise ValueError(f"Event validation failed: {errors}")

        line = json.dumps(event, ensure_ascii=False)

        with self._lock:
            path = self._event_file()
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

