REQUIRED_KEYS = {"event_id", "event_type", "ts", "actor", "payload"}

def validate_event(event: dict):
    missing = REQUIRED_KEYS - event.keys()
    if missing:
        raise ValueError(f"Missing event keys: {missing}")
    return True
