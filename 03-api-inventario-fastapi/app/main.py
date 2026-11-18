"""Punto de entrada de la API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import Rol, Usuario
from .routers import auth, movimientos, productos, reportes
from .security import hashear_password
from .servicios import ErrorNegocio

logger = logging.getLogger(__name__)

DESCRIPCION = """
API de inventario: catálogo de productos, control de stock con historial de
movimientos y reportes. Autenticación con JWT y dos roles:

* **admin**: crea, edita y da de baja productos.
* **operador**: consulta el catálogo y registra entradas, salidas y ajustes.

Para probarla desde esta página: crea una cuenta en `/auth/registro`, pulsa
**Authorize** e inicia sesión.
"""


def sembrar_admin() -> None:
    """Crea el administrador inicial si ADMIN_USERNAME y ADMIN_PASSWORD están definidos."""
    settings = get_settings()
    if not (settings.admin_username and settings.admin_password):
        return
    username = settings.admin_username.lower()
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.username == username)) is None:
            db.add(
                Usuario(
                    username=username,
                    password_hash=hashear_password(settings.admin_password),
                    rol=Rol.admin.value,
                )
            )
            db.commit()
            logger.info("Administrador inicial '%s' creado.", username)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)  # en un proyecto grande se usaría Alembic
    sembrar_admin()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="API de Inventario",
        version="1.0.0",
        description=DESCRIPCION,
        lifespan=lifespan,
    )
    app.include_router(auth.router)
    app.include_router(productos.router)
    app.include_router(movimientos.router)
    app.include_router(reportes.router)

    @app.exception_handler(ErrorNegocio)
    async def manejar_error_negocio(_request: Request, error: ErrorNegocio):
        return JSONResponse(status_code=error.status_code, content={"detail": error.mensaje})

    @app.get("/salud", tags=["sistema"])
    def salud():
        """Para comprobar que el servicio está vivo (lo usa el healthcheck de Docker)."""
        return {"estado": "ok"}

    return app


app = create_app()
