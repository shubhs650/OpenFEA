"""SQLite WAL runtime and programmatic, reversible Alembic migrations."""

import sqlite3
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Connection, create_engine, event

ROOT = Path(__file__).resolve().parents[4]


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine = create_engine(
            URL.create("sqlite", database=str(path)),
            connect_args={"check_same_thread": False, "timeout": 5},
        )

        @event.listens_for(self.engine, "connect")
        def configure(dbapi_connection: sqlite3.Connection, record: Any) -> None:
            # Own transactions explicitly: SQLite DDL and migration rollback must be atomic.
            dbapi_connection.isolation_level = None
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
            dbapi_connection.execute("PRAGMA busy_timeout=5000")
            dbapi_connection.execute("PRAGMA journal_mode=WAL")
            dbapi_connection.execute("PRAGMA synchronous=FULL")
            path.chmod(0o600)

        @event.listens_for(self.engine, "begin")
        def begin(connection: Connection) -> None:
            immediate = connection.get_execution_options().get("sqlite_immediate", False)
            connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    def migrate(self, target: str = "head", *, downgrade: bool = False) -> None:
        config = Config()
        config.set_main_option("script_location", str(ROOT / "migrations"))
        with self.engine.connect().execution_options(sqlite_immediate=True) as connection:
            config.attributes["connection"] = connection
            if downgrade:
                command.downgrade(config, target)
            else:
                command.upgrade(config, target)

    def close(self) -> None:
        self.engine.dispose()
