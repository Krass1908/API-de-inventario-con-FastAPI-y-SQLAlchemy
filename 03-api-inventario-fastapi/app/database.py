"""Conexión a la base de datos y sesión por petición."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def habilitar_claves_foraneas(engine: Engine) -> None:
    """SQLite ignora las claves foráneas salvo que se activen en cada conexión."""
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _activar(conexion, _registro):
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def crear_engine(url: str) -> Engine:
    argumentos = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=argumentos, pool_pre_ping=True)
    habilitar_claves_foraneas(engine)
    return engine


engine = crear_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición, siempre cerrada al terminar."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
