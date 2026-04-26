from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    ttl_sec: float

    def is_fresh(self) -> bool:
        return (time.time() - self.created_at) <= self.ttl_sec


class JsonFileCache:
    def __init__(self, *, path: Path, max_items: int = 300) -> None:
        self._path = path
        self._max_items = int(max_items)
        self._mem: dict[str, CacheEntry] = {}
        self._loaded = False

    def get(self, key: str) -> Any | None:
        self._ensure_loaded()
        ent = self._mem.get(key)
        if not ent:
            return None
        if not ent.is_fresh():
            self._mem.pop(key, None)
            self._flush()
            return None
        return ent.value

    def set(self, key: str, value: Any, *, ttl_sec: float) -> None:
        self._ensure_loaded()
        self._mem[key] = CacheEntry(value=value, created_at=time.time(), ttl_sec=float(ttl_sec))
        self._evict_if_needed()
        self._flush()

    @staticmethod
    def make_key(prefix: str, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{prefix}:{sha256(raw.encode('utf-8')).hexdigest()}"

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        try:
            obj = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(obj, dict):
            return
        for k, v in obj.items():
            if not isinstance(v, dict):
                continue
            if "value" not in v or "created_at" not in v or "ttl_sec" not in v:
                continue
            try:
                ent = CacheEntry(value=v["value"], created_at=float(v["created_at"]), ttl_sec=float(v["ttl_sec"]))
            except Exception:
                continue
            if ent.is_fresh():
                self._mem[str(k)] = ent

    def _evict_if_needed(self) -> None:
        if len(self._mem) <= self._max_items:
            return
        items = sorted(self._mem.items(), key=lambda kv: kv[1].created_at)
        drop = len(self._mem) - self._max_items
        for i in range(drop):
            self._mem.pop(items[i][0], None)

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            obj = {k: {"value": v.value, "created_at": v.created_at, "ttl_sec": v.ttl_sec} for k, v in self._mem.items()}
            self._path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

