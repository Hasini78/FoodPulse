"""Snowflake settings from the environment.

The password and account locator are not included in log text or exception text.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class SnowflakeConfig:
    """Connection settings. The representation omits the account, user, and password."""

    account: str
    user: str
    password: str
    warehouse: str
    database: str
    schema: str
    role: str | None

    def __repr__(self) -> str:
        role = "none" if self.role is None else "set"
        return (
            "SnowflakeConfig(account='[redacted]', user='[redacted]', password='[redacted]', "
            f"warehouse={self.warehouse!r}, database={self.database!r}, schema={self.schema!r}, role={role})"
        )

    def secrets(self) -> tuple[str, ...]:
        """Values that must be stripped from errors and logs."""
        values = [self.password, self.account, self.user]
        if self.account:
            values.append(f"https://{self.account}")
            values.append(f"{self.account}.snowflakecomputing.com")
        return tuple(dict.fromkeys(value for value in values if value))


def load_config(environ: dict[str, str] | None = None) -> SnowflakeConfig:
    """Read Snowflake settings. Missing required values raise without echoing them."""
    source = os.environ if environ is None else environ
    account = _required(source, "SNOWFLAKE_ACCOUNT")
    user = _required(source, "SNOWFLAKE_USER")
    password = _required(source, "SNOWFLAKE_PASSWORD")
    warehouse = _identifier(source.get("SNOWFLAKE_WAREHOUSE") or "FOODPULSE_WH", "SNOWFLAKE_WAREHOUSE")
    database = _identifier(source.get("SNOWFLAKE_DATABASE") or "FOODPULSE", "SNOWFLAKE_DATABASE")
    schema = _identifier(source.get("SNOWFLAKE_SCHEMA") or "ANALYTICS", "SNOWFLAKE_SCHEMA")
    role_value = (source.get("SNOWFLAKE_ROLE") or "").strip()
    role = _identifier(role_value, "SNOWFLAKE_ROLE") if role_value else None
    return SnowflakeConfig(account, user, password, warehouse, database, schema, role)


def quote_identifier(value: str) -> str:
    """Return one uppercase identifier, or raise without echoing the value."""
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("Snowflake identifier is not allowed")
    return value.upper()


def redact(text: str, secrets: tuple[str, ...]) -> str:
    """Remove configured secrets from a message without removing the surrounding text."""
    cleaned = text
    for secret in secrets:
        if not secret:
            continue
        pattern = re.compile(re.escape(secret), re.IGNORECASE)
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned


def _required(source: dict[str, str], name: str) -> str:
    value = (source.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is not set")
    return value


def _identifier(value: str, name: str) -> str:
    try:
        return quote_identifier(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a simple identifier") from exc
