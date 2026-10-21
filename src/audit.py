"""Tamper-evident audit log: every entry carries the hash of the previous one."""
import hashlib
import json


class AuditLog:
    def __init__(self):
        self.entries = []

    @staticmethod
    def _hash(body):
        return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()

    def add(self, actor, action, subject, detail=None, day=None):
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        body = dict(seq=len(self.entries), actor=actor, action=action, subject=subject, detail=detail or {}, day=day, prev=prev)
        self.entries.append({**body, "hash": self._hash(body)})
        return self.entries[-1]

    def verify(self):
        prev = "0" * 64
        for e in self.entries:
            body = {k: v for k, v in e.items() if k != "hash"}
            if body["prev"] != prev or self._hash(body) != e["hash"]:
                return False
            prev = e["hash"]
        return True
