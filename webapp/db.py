# -*- coding: utf-8 -*-
"""Small database compatibility layer for local SQLite and hosted PostgreSQL.

The desktop/local server keeps using SQLite.  Railway uses PostgreSQL whenever
``DATABASE_URL`` is present (the pooled Neon connection string is preferred).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if os.getenv("BROOST_LOAD_DOTENV", "1") != "0":
    load_dotenv(PROJECT_ROOT / ".env", override=False)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USING_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))


class DatabaseError(Exception):
    """Database failure safe to expose through the API error handler."""


class DatabaseIntegrityError(DatabaseError):
    """Unique/foreign-key/check constraint failure."""


class PostgresCursor:
    def __init__(self, connection: Any, cursor: Any):
        self._connection = connection
        self._cursor = cursor
        self._lastrowid: int | None = None

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int:
        if self._lastrowid is None:
            try:
                cursor = self._connection.cursor()
                cursor.execute("SELECT LASTVAL() AS id")
                row = cursor.fetchone()
                self._lastrowid = int(row["id"])
                cursor.close()
            except Exception as exc:  # pragma: no cover - only used by PostgreSQL
                raise DatabaseError(f"Could not read inserted row id: {exc}") from exc
        return self._lastrowid

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()


def _postgres_sql(sql: str) -> str:
    """Translate the qmark placeholders used by sqlite3 to psycopg format."""
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self, connection: Any, psycopg_module: Any):
        self._connection = connection
        self._psycopg = psycopg_module

    def _raise(self, exc: Exception) -> None:
        if isinstance(exc, self._psycopg.IntegrityError):
            raise DatabaseIntegrityError(str(exc)) from exc
        raise DatabaseError(str(exc)) from exc

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> PostgresCursor:
        try:
            cursor = self._connection.cursor()
            translated_sql = _postgres_sql(sql)
            bound_params = tuple(params) if params is not None else ()
            # Psycopg parses percent signs as client-side placeholders whenever
            # a parameters argument is supplied, even when that argument is an
            # empty tuple. Execute parameterless SQL without a second argument
            # so literal LIKE patterns such as '%Z' remain valid PostgreSQL.
            if bound_params:
                cursor.execute(translated_sql, bound_params)
            else:
                cursor.execute(translated_sql)
            return PostgresCursor(self._connection, cursor)
        except self._psycopg.Error as exc:
            self._raise(exc)
            raise AssertionError("unreachable")

    def executemany(self, sql: str, params: Iterable[Iterable[Any]]) -> PostgresCursor:
        try:
            cursor = self._connection.cursor()
            cursor.executemany(_postgres_sql(sql), params)
            return PostgresCursor(self._connection, cursor)
        except self._psycopg.Error as exc:
            self._raise(exc)
            raise AssertionError("unreachable")

    def executescript(self, sql: str) -> None:
        # The schema only contains simple CREATE statements; it has no function
        # bodies or other blocks containing semicolons.
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                self.execute(statement)

    def commit(self) -> None:
        try:
            self._connection.commit()
        except self._psycopg.Error as exc:
            self._raise(exc)

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def connect_database(sqlite_path: Path) -> sqlite3.Connection | PostgresConnection:
    if not USING_POSTGRES:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(sqlite_path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError(
            "DATABASE_URL is PostgreSQL but psycopg is not installed. "
            "Install requirements-web.txt."
        ) from exc

    try:
        connection = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
        )
        return PostgresConnection(connection, psycopg)
    except psycopg.Error as exc:  # pragma: no cover - requires live PostgreSQL
        raise DatabaseError(str(exc)) from exc


def table_columns(connection: Any, table_name: str) -> set[str]:
    if USING_POSTGRES:
        rows = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=?",
            (table_name,),
        ).fetchall()
        return {str(row["column_name"]) for row in rows}
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
