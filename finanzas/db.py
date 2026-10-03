from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from finanzas import config


class Base(DeclarativeBase):
    pass


def url_postgres(url: str) -> str:
    """Neon y Vercel dan URLs postgres://; SQLAlchemy necesita el driver explícito."""
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


def make_engine(url: str | None = None):
    if url is None and config.DATABASE_URL:
        url = config.DATABASE_URL
    if url is None:
        if config.EN_VERCEL:
            raise RuntimeError("En Vercel hace falta DATABASE_URL (una base de datos Postgres). Ver README.")
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{config.DB_PATH}"
    url = url_postgres(url)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    # En funciones serverless cada instancia abre pocas conexiones y comprueba que siguen vivas
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2, pool_recycle=300)


try:
    engine = make_engine()
    ERROR_CONFIG = ""
except RuntimeError as e:  # en Vercel sin base de datos: la app arranca y explica qué falta
    engine, ERROR_CONFIG = None, str(e)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


_tablas_listas = False


def asegurar_tablas() -> None:
    """Crea tablas y columnas nuevas una vez por proceso. En Vercel cada función puede arrancar
    en frío sin pasar por el arranque de la app, así que se llama también al pedir una sesión."""
    global _tablas_listas
    if not _tablas_listas and engine is not None:
        init_db()
        _tablas_listas = True


def init_db(eng=None) -> None:
    from finanzas import models  # noqa: F401  (registra las tablas)

    eng = eng or engine
    if eng is None:
        return
    Base.metadata.create_all(eng)
    _añadir_columnas_nuevas(eng)
    if eng is engine:
        global _tablas_listas
        _tablas_listas = True


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
    if engine is None:
        from fastapi import HTTPException
        raise HTTPException(503, ERROR_CONFIG)
    asegurar_tablas()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
