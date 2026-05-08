"""Shared API authentication helpers."""

from __future__ import annotations

import hmac


def has_valid_bearer_token(headers: dict[str, str], expected_token: str) -> bool:
    token = expected_token.strip()
    if not token:
        return False
    normalized = {key.lower(): value for key, value in headers.items()}
    authorization = normalized.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return False
    supplied = authorization.removeprefix("Bearer ").strip()
    return hmac.compare_digest(supplied, token)
