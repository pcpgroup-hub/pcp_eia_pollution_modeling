# -*- coding: utf-8 -*-
"""Append-only audit log with a hash chain (tamper evident). No QGIS imports."""
import getpass
import hashlib
import json
import os
from datetime import datetime, timezone

LOG_NAME = "eia_audit.jsonl"


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _entry_hash(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, project_dir):
        self.path = os.path.join(project_dir, LOG_NAME)

    def _last_hash(self):
        if not os.path.exists(self.path):
            return "0" * 64
        last = None
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        return json.loads(last)["entry_hash"] if last else "0" * 64

    def append(self, step, level, model, card_version, parameters, approval=None, files=None, result=None, legal_regime=None):
        body = {
            "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "os_user": getpass.getuser(),
            "step": step,
            "level": level,
            "model": model,
            "card_version": card_version,
            "legal_regime": legal_regime,
            "parameters": parameters,
            "approval": approval,
            "file_hashes": {p: sha256_file(p) for p in (files or []) if os.path.isfile(p)},
            "result": result,
            "prev_hash": self._last_hash(),
        }
        body["entry_hash"] = _entry_hash({k: v for k, v in body.items()})
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
        return body

    def verify(self):
        """Return (ok, message). Recomputes the chain."""
        if not os.path.exists(self.path):
            return True, "no log"
        prev = "0" * 64
        with open(self.path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                e = json.loads(line)
                stored = e.pop("entry_hash")
                if e["prev_hash"] != prev or _entry_hash(e) != stored:
                    return False, "chain broken at line %d" % n
                prev = stored
        return True, "chain ok"
