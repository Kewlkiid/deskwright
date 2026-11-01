"""Per-run metering: model calls, cache hits, time and cost."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, fields


@dataclass
class Metrics:
    started: float = field(default_factory=time.time)
    steps: int = 0
    model_calls: int = 0
    calls_by_role: dict = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    model_time: float = 0.0
    cost: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    calls_saved: int = 0
    time_saved: float = 0.0
    cost_saved: float = 0.0
    fixes: int = 0
    fixes_succeeded: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_call(self, role: str, seconds: float, tokens_in: int = 0, tokens_out: int = 0, cost: float = 0.0):
        with self._lock:
            self.model_calls += 1
            self.calls_by_role[role] = self.calls_by_role.get(role, 0) + 1
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out
            self.model_time += seconds
            self.cost += cost

    def record_cache(self, hit: bool, saved_calls: int = 0, saved_time: float = 0.0, saved_cost: float = 0.0):
        with self._lock:
            if hit:
                self.cache_hits += 1
                self.calls_saved += saved_calls
                self.time_saved += saved_time
                self.cost_saved += saved_cost
            else:
                self.cache_misses += 1

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    def snapshot(self) -> dict:
        with self._lock:
            d = {f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_")}
            d["calls_by_role"] = dict(self.calls_by_role)
        d["elapsed"] = round(self.elapsed, 2)
        d["cache_hit_rate"] = round(self.cache_hit_rate, 3)
        d["cost"] = round(self.cost, 5)
        d["cost_saved"] = round(self.cost_saved, 5)
        d["time_saved"] = round(self.time_saved, 2)
        d["model_time"] = round(self.model_time, 2)
        return d


# Used when a model is called outside a run (teach-mode compile, voice).
GLOBAL_METRICS = Metrics()
