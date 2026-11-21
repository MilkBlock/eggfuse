"""Pass-local verified transfer receipts and an audit of raw child token claims."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    token: int
    effect: int
    generation: int


class Transfers:
    """One pass. The producer supplies committed, ordered moves of the same logical port."""
    def __init__(self):
        self.logical = {}
        self.owner = {}
        self.moved = set()
        self.last_boundary = -1

    def publish(self, endpoint, obligation):
        if endpoint in self.logical or obligation in self.owner:
            raise ValueError("reused endpoint or live obligation")
        self.logical[endpoint] = obligation
        self.owner[obligation] = endpoint

    def transfer(self, old, new, boundary):
        key = self.logical.get(old)
        if (boundary < self.last_boundary or old not in self.logical
                or self.owner[key] != old or new in self.logical):
            raise ValueError("out-of-order, stale or ambiguous ownership transfer")
        self.logical[new] = key
        self.owner[key] = new
        self.moved.add(key)
        self.last_boundary = boundary

    def role(self, endpoint):
        if endpoint not in self.logical:
            return 0
        key = self.logical[endpoint]
        if key not in self.moved:
            return 0
        return 1 if self.owner[key] == endpoint else -1

    def audit(self, claims):
        seen = set()
        counts = dict(active=0, retired=0, unknown=0, duplicate=0, novel=0)
        for endpoint, consumer in claims:
            counts["active"] += 1
            if endpoint not in self.logical:
                counts["unknown"] += 1
                continue
            if self.role(endpoint) < 0:
                counts["retired"] += 1
                continue
            key = self.logical[endpoint], consumer
            if key in seen:
                counts["duplicate"] += 1
            else:
                counts["novel"] += 1
                seen.add(key)
        return counts
