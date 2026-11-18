"""Configuración leída de variables de entorno."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

LONGITUD_MINIMA_CLAVE = 32


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    token_minutos: int
    admin_username: str | None
    admin_password: str | None


@lru_cache
def get_settings() -> Settings:
    clave = os.getenv("SECRET_KEY")
    if not clave:
        logger.warning(
            "SECRET_KEY no está definida: se usa una clave aleatoria que cambia en cada "
            "arranque (los tokens dejan de valer al reiniciar). Defínela en producción."
        )
        clave = secrets.token_urlsafe(LONGITUD_MINIMA_CLAVE)
    elif len(clave) < LONGITUD_MINIMA_CLAVE:
        raise RuntimeError(
            f"SECRET_KEY debe tener al menos {LONGITUD_MINIMA_CLAVE} caracteres."
        )

    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./inventario.db"),
        secret_key=clave,
        token_minutos=int(os.getenv("TOKEN_MINUTOS", "60")),
        admin_username=os.getenv("ADMIN_USERNAME"),
        admin_password=os.getenv("ADMIN_PASSWORD"),
    )
