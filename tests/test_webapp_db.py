# -*- coding: utf-8 -*-
"""Regression tests for the PostgreSQL compatibility layer."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from webapp.db import PostgresConnection


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


if __name__ == "__main__":
    unittest.main()
