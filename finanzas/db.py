from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from finanzas import config


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    if url is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{config.DB_PATH}"
    return create_engine(url, connect_args={"check_same_thread": False})


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(eng=None) -> None:
    from finanzas import models  # noqa: F401  (registra las tablas)

    Base.metadata.create_all(eng or engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
