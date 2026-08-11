# -*- coding: utf-8 -*-
"""Regression tests for the PostgreSQL compatibility layer."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from webapp.db import PostgresConnection
from webapp import server


class FakePsycopg:
    class Error(Exception):
        pass

    class IntegrityError(Error):
        pass


class PostgresConnectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.raw_connection = MagicMock()
        self.cursor = self.raw_connection.cursor.return_value
        self.connection = PostgresConnection(self.raw_connection, FakePsycopg)

    def test_parameterless_percent_pattern_is_not_treated_as_placeholder(self) -> None:
        sql = "SELECT 1 WHERE '2026-08-07Z' LIKE '%Z'"

        self.connection.execute(sql)

        self.cursor.execute.assert_called_once_with(sql)

    def test_qmark_parameters_are_translated_and_bound(self) -> None:
        self.connection.execute("SELECT 1 WHERE value=?", ("saved",))

        self.cursor.execute.assert_called_once_with(
            "SELECT 1 WHERE value=%s", ("saved",)
        )

    def test_cursor_can_be_iterated_like_sqlite_cursor(self) -> None:
        self.cursor.__iter__.return_value = iter([{"id": 1}, {"id": 2}])

        rows = list(self.connection.execute("SELECT id FROM orders"))

        self.assertEqual(rows, [{"id": 1}, {"id": 2}])

    def test_production_ordering_follows_recent_cashier_heartbeat(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO settings VALUES ('pos_last_seen_at', ?)",
            (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),),
        )
        original_environment = server.APP_ENV
        try:
            server.APP_ENV = "production"
            self.assertTrue(server.cashier_is_online(connection))
            connection.execute(
                "UPDATE settings SET value=? WHERE key='pos_last_seen_at'",
                ((datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),),
            )
            self.assertFalse(server.cashier_is_online(connection))
        finally:
            server.APP_ENV = original_environment
            connection.close()


if __name__ == "__main__":
    unittest.main()
