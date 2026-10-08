"""Sanitized, action-level agent tracing without prompts or private reasoning."""
from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "api_key", "authorization", "database_url", "password", "secret", "token",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)postgres(?:ql)?://[^\s]+"),
    re.compile(r"(?i)(?:sk|gsk)_[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{12,}"),
)


def sanitize_trace_value(value: Any, *, key: str = "") -> Any:
    normalized_key = key.lower()
    if any(marker in normalized_key for marker in SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_trace_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_trace_value(item, key=key) for item in value[:20]]
    if isinstance(value, str):
        sanitized = value
        for pattern in SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)
        return sanitized[:300]
    return value


def append_trace(
    existing: list[dict[str, Any]], node: str, decision: str, **extra: Any
) -> list[dict[str, Any]]:
    event = sanitize_trace_value({"node": node, "decision": decision, **extra})
    return [*existing, event]
