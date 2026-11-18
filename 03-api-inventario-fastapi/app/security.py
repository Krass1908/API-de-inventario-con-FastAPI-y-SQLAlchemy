"""Contraseñas (scrypt), tokens JWT y dependencias de autorización."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Rol, Usuario

ALGORITMO_JWT = "HS256"

# Parámetros de scrypt. El hash guarda los que se usaron, así que se pueden
# subir en el futuro sin invalidar las contraseñas ya guardadas.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ------------------------------------------------------------------ contraseñas
def hashear_password(password: str) -> str:
    sal = os.urandom(16)
    derivada = hashlib.scrypt(
        password.encode(), salt=sal, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${sal.hex()}${derivada.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        algoritmo, n, r, p, sal_hex, hash_hex = almacenado.split("$")
        if algoritmo != "scrypt":
            return False
        esperada = bytes.fromhex(hash_hex)
        candidata = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(sal_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(esperada),
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidata, esperada)  # comparación en tiempo constante


@lru_cache
def hash_falso() -> str:
    """Se verifica contra este hash cuando el usuario no existe, para que el login
    tarde lo mismo y no revele qué usuarios están registrados."""
    return hashear_password("contraseña-que-nadie-usa")


# ------------------------------------------------------------------------ JWT
def crear_token(username: str) -> str:
    ahora = datetime.now(timezone.utc)
    settings = get_settings()
    payload = {
        "sub": username,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.token_minutos),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO_JWT)


def _no_autenticado() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_usuario_actual(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Usuario:
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[ALGORITMO_JWT],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise _no_autenticado() from None

    # Se consulta la base en cada petición: si el usuario se desactiva o cambia de
    # rol, el efecto es inmediato aunque su token siga vigente.
    usuario = db.scalar(select(Usuario).where(Usuario.username == payload["sub"]))
    if usuario is None or not usuario.activo:
        raise _no_autenticado()
    return usuario


def requiere_admin(usuario: Annotated[Usuario, Depends(get_usuario_actual)]) -> Usuario:
    if usuario.rol != Rol.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador.",
        )
    return usuario
