import json
import logging
import sys
from collections import defaultdict
from typing import Any

from core.config import settings


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        try:
            from core.tracing import get_trace_ctx
            ctx = get_trace_ctx()
            if ctx:
                log_entry["trace_id"] = ctx.trace_id
                log_entry["span_id"] = ctx.span_id
        except Exception:
            pass
        if hasattr(record, "extra") and record.extra:
            log_entry["extra"] = record.extra
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def setup_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    for lib in ("httpx", "urllib3", "httpcore", "apscheduler"):
        logging.getLogger(lib).setLevel(logging.WARNING)


_request_durations: dict[str, list[float]] = defaultdict(list)


def record_request_duration(path: str, duration_ms: float):
    key = path.split("?")[0]
    _request_durations[key].append(duration_ms)
    if len(_request_durations[key]) > 1000:
        _request_durations[key] = _request_durations[key][-1000:]


def get_request_stats() -> dict:
    stats = {}
    for path, durations in _request_durations.items():
        if not durations:
            continue
        avg = sum(durations) / len(durations)
        stats[path] = {
            "count": len(durations),
            "avg_ms": round(avg, 2),
            "max_ms": round(max(durations), 2),
            "min_ms": round(min(durations), 2),
        }
    return stats
