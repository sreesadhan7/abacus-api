from __future__ import annotations

from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, event, select, update
from sqlalchemy.engine import Connection, Engine

metadata = MetaData()

abacus_state = Table(
    "abacus_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("total", Integer, nullable=False),
)


def build_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        db_path = database_url.removeprefix("sqlite:///")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {
            "check_same_thread": False,
            "timeout": 30,
        }

    engine = create_engine(
        database_url,
        connect_args=connect_args,
        future=True,
        pool_pre_ping=True,
    )

    if database_url.startswith("sqlite"):
        _configure_sqlite(engine)

    return engine


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


class AbacusStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def initialize(self) -> None:
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            self._ensure_row(connection)

    def add(self, number: int) -> int:
        with self.engine.begin() as connection:
            self._ensure_row(connection)
            result = connection.execute(
                update(abacus_state)
                .where(abacus_state.c.id == 1)
                .values(total=abacus_state.c.total + number)
                .returning(abacus_state.c.total)
            )
            return int(result.scalar_one())

    def get_total(self) -> int:
        with self.engine.begin() as connection:
            self._ensure_row(connection)
            result = connection.execute(
                select(abacus_state.c.total).where(abacus_state.c.id == 1)
            )
            return int(result.scalar_one())

    def reset(self) -> int:
        with self.engine.begin() as connection:
            self._ensure_row(connection)
            result = connection.execute(
                update(abacus_state)
                .where(abacus_state.c.id == 1)
                .values(total=0)
                .returning(abacus_state.c.total)
            )
            return int(result.scalar_one())

    @staticmethod
    def _ensure_row(connection: Connection) -> None:
        exists = connection.execute(
            select(abacus_state.c.id).where(abacus_state.c.id == 1)
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(abacus_state.insert().values(id=1, total=0))
