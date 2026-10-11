"""Open a Snowflake connection only when a load or connection test asks for one.

The login does not select the analytical database or schema. Those objects are
created, when needed, after autocommit has been disabled by the loader. The
warehouse is required at login and is never created by this package.
``connect`` does not change autocommit. The connection test therefore runs one
context query and does not issue session or DDL statements.
"""

from __future__ import annotations

import logging

from warehouse.snowflake.config import SnowflakeConfig, redact

logger = logging.getLogger(__name__)

CONTEXT_SQL = "SELECT CURRENT_VERSION(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"


def connection_arguments(config: SnowflakeConfig) -> dict[str, str]:
    """Return login arguments. Database and schema are intentionally absent."""
    arguments = {
        "account": config.account,
        "user": config.user,
        "password": config.password,
        "warehouse": config.warehouse,
        "paramstyle": "qmark",
    }
    if config.role:
        arguments["role"] = config.role
    return arguments


def connect(config: SnowflakeConfig):
    """Connect with the configured warehouse. The account, user, and password are not logged."""
    import snowflake.connector

    logging.getLogger("snowflake").setLevel(logging.WARNING)
    logging.getLogger("snowflake.connector").setLevel(logging.WARNING)
    logger.info("Opening a Snowflake connection")
    return snowflake.connector.connect(**connection_arguments(config))


def probe_connection(config: SnowflakeConfig, connector=None) -> tuple:
    """Read session context. No objects are created and no data is written."""
    if connector is None:
        connector = connect
    connection = None
    try:
        try:
            connection = connector(config)
        except Exception as exc:
            raise RuntimeError(redact(str(exc), config.secrets())) from None
        cursor = connection.cursor()
        try:
            cursor.execute(CONTEXT_SQL)
            row = cursor.fetchone()
        finally:
            cursor.close()
        if row is None or len(row) < 4:
            raise RuntimeError("Snowflake did not return connection context")
        return tuple(row[:4])
    except Exception as exc:
        raise RuntimeError(redact(str(exc), config.secrets())) from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception as exc:
                logger.error("Closing the Snowflake connection failed. %s", redact(str(exc), config.secrets()))
