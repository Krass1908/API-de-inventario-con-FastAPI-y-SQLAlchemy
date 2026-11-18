from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import servicios
from ..database import get_db
from ..models import Movimiento, TipoMovimiento, Usuario
from ..schemas import MovimientoCrear, MovimientoSalida, PaginaMovimientos
from ..security import get_usuario_actual

router = APIRouter(prefix="/movimientos", tags=["movimientos"])

DB = Annotated[Session, Depends(get_db)]
UsuarioActual = Annotated[Usuario, Depends(get_usuario_actual)]


@router.post("", response_model=MovimientoSalida, status_code=status.HTTP_201_CREATED)
def registrar(datos: MovimientoCrear, db: DB, usuario: UsuarioActual):
    """Entrada, salida o ajuste de stock. Cualquier usuario autenticado puede registrarlos."""
    return servicios.registrar_movimiento(db, datos, usuario)


@router.get("", response_model=PaginaMovimientos)
def historial(
    db: DB,
    usuario: UsuarioActual,
    producto_id: int | None = None,
    tipo: TipoMovimiento | None = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Historial de movimientos, del más reciente al más antiguo."""
    consulta = select(Movimiento)
    if producto_id is not None:
        consulta = consulta.where(Movimiento.producto_id == producto_id)
    if tipo is not None:
        consulta = consulta.where(Movimiento.tipo == tipo.value)
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    items = db.scalars(consulta.order_by(Movimiento.id.desc()).offset(skip).limit(limit)).all()
    return {"total": total, "items": items}
