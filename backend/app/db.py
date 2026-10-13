import re
import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from .config import config

_connection: ContextVar[Any | None] = ContextVar("database_connection", default=None)
_operation_timeout: ContextVar[int | None] = ContextVar("database_operation_timeout", default=None)

@contextmanager
def operation_timeout(milliseconds: int):
    """Bound SQL on newly opened PostgreSQL connections in this context only."""
    if type(milliseconds) is not int or not 1 <= milliseconds <= 60000:
        raise ValueError("Database operation timeout must be between 1 and 60000 milliseconds.")
    token = _operation_timeout.set(milliseconds)
    try:
        yield
    finally:
        _operation_timeout.reset(token)

def connect():
    if config.database_url:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(config.database_url, autocommit=True, row_factory=dict_row, connect_timeout=10)
        timeout = _operation_timeout.get()
        if timeout is not None:
            try:
                # Preserve URL/service/PGOPTIONS settings such as search_path.
                connection.execute(
                    "SELECT set_config('statement_timeout', %s, false), set_config('lock_timeout', %s, false)",
                    (str(timeout), str(timeout)),
                )
            except BaseException:
                connection.close()
                raise
        return connection
    if config.production and not os.getenv("SQLITE_PATH"):
        raise RuntimeError("Configure DATABASE_URL or an explicit persistent SQLITE_PATH in production.")
    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.sqlite_path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection

def query(sql: str, values=()) -> list[dict]:
    connection = _connection.get()
    own = connection is None
    if own:
        connection = connect()
    bindings = []
    def placeholder(match):
        bindings.append(values[int(match[1]) - 1])
        return "%s" if config.database_url else "?"
    statement = re.sub(r"\$(\d+)", placeholder, sql)
    try:
        cursor = connection.execute(statement, bindings)
        return [dict(row) for row in cursor.fetchall()] if cursor.description else []
    finally:
        if own:
            connection.close()

@contextmanager
def transaction():
    if _connection.get() is not None:
        yield
        return
    connection = connect()
    token = _connection.set(connection)
    try:
        connection.execute("BEGIN" if config.database_url else "BEGIN IMMEDIATE")
        if config.database_url:
            connection.execute("SELECT pg_advisory_xact_lock(19962411)")
        yield
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        _connection.reset(token)
        connection.close()

def migrate():
    from .schema import upgrade_schema
    upgrade_schema()
