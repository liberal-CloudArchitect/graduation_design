"""Core module exports.

Keep these imports lazy so tests that only need ``app.core.config`` do not
eagerly import optional auth/database dependencies such as ``jose`` or
SQLAlchemy.
"""

from typing import Any


__all__ = [
    "settings",
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "create_tokens",
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "get_optional_user",
]


def __getattr__(name: str) -> Any:
    if name == "settings":
        from app.core.config import settings

        return settings

    if name in {
        "verify_password",
        "get_password_hash",
        "create_access_token",
        "create_refresh_token",
        "decode_token",
        "create_tokens",
    }:
        from app.core import security as security_mod

        return getattr(security_mod, name)

    if name in {
        "get_db",
        "get_current_user",
        "get_current_active_user",
        "get_optional_user",
    }:
        from app.core import deps as deps_mod

        return getattr(deps_mod, name)

    raise AttributeError(f"module 'app.core' has no attribute {name!r}")
