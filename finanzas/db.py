from sqlalchemy import create_engine, inspect, text
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

    eng = eng or engine
    Base.metadata.create_all(eng)
    _añadir_columnas_nuevas(eng)


def _añadir_columnas_nuevas(eng) -> None:
    """Migración mínima: añade a tablas existentes las columnas nuevas (todas admiten NULL).
    Así una base de datos de una versión anterior sigue funcionando sin perder datos."""
    insp = inspect(eng)
    with eng.begin() as con:
        for tabla in Base.metadata.sorted_tables:
            existentes = {c["name"] for c in insp.get_columns(tabla.name)}
            for col in tabla.columns:
                if col.name not in existentes:
                    tipo = col.type.compile(eng.dialect)
                    con.execute(text(f'ALTER TABLE {tabla.name} ADD COLUMN "{col.name}" {tipo}'))


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
