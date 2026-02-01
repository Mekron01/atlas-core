import time
import uuid

class Session:
    def __init__(self, scope=None, budget=None):
        self.session_id = str(uuid.uuid4())
        self.scope = scope or []
        self.budget = budget
        self.start = time.time()
        self.events = []

    def record(self, event):
        self.events.append(event)

    def elapsed_ms(self):
        return int((time.time() - self.start) * 1000)
