from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def init_engine(url: str) -> Engine:
    global _engine
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    SessionLocal.configure(bind=engine)
    _engine = engine
    from app import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    added = _add_missing_columns(engine)
    if {"listings.water_distance"} & added:
        # Existing listings were fetched before these fields were parsed; queue a re-fetch.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE listings SET detail_fetched_at = NULL, detail_attempts = 0 "
                    "WHERE status = 'active'"
                )
            )
    return engine


def _add_missing_columns(engine: Engine) -> set[str]:
    """create_all() never alters existing tables; add new nullable columns in place."""
    added: set[str] = set()
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing or not col.nullable:
                    continue
                ddl = col.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                added.add(f"{table.name}.{col.name}")
    return added


def get_engine() -> Engine:
    assert _engine is not None, "init_engine() not called"
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
