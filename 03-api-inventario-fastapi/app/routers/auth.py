from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Rol, Usuario
from ..schemas import Token, UsuarioCrear, UsuarioSalida
from ..security import (
    crear_token,
    get_usuario_actual,
    hash_falso,
    hashear_password,
    verificar_password,
)

router = APIRouter(prefix="/auth", tags=["autenticación"])

DB = Annotated[Session, Depends(get_db)]


@router.post("/registro", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def registrar(datos: UsuarioCrear, db: DB):
    """Crea una cuenta con rol `operador`. Los administradores no se crean por aquí."""
    username = datos.username.lower()
    if db.scalar(select(Usuario.id).where(Usuario.username == username)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese nombre de usuario ya existe.")

    usuario = Usuario(
        username=username,
        password_hash=hashear_password(datos.password),
        rol=Rol.operador.value,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese nombre de usuario ya existe.") from None
    db.refresh(usuario)
    return usuario


@router.post("/login", response_model=Token)
def login(formulario: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    """Recibe `username` y `password` como formulario (estándar OAuth2) y devuelve un JWT."""
    usuario = db.scalar(select(Usuario).where(Usuario.username == formulario.username.lower()))
    hash_guardado = usuario.password_hash if usuario else hash_falso()
    password_correcta = verificar_password(formulario.password, hash_guardado)

    if usuario is None or not password_correcta or not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=crear_token(usuario.username))


@router.get("/yo", response_model=UsuarioSalida)
def perfil(usuario: Annotated[Usuario, Depends(get_usuario_actual)]):
    """Datos del usuario dueño del token."""
    return usuario
