from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import servicios
from ..database import get_db
from ..models import Producto, Usuario, a_centavos
from ..schemas import PaginaProductos, ProductoActualizar, ProductoCrear, ProductoSalida
from ..security import get_usuario_actual, requiere_admin

# Todas las rutas exigen sesión iniciada; escribir exige además ser administrador.
router = APIRouter(
    prefix="/productos",
    tags=["productos"],
    dependencies=[Depends(get_usuario_actual)],
)

DB = Annotated[Session, Depends(get_db)]
Admin = Annotated[Usuario, Depends(requiere_admin)]


def _escapar_like(texto: str) -> str:
    """Evita que `%` y `_` escritos por el usuario actúen como comodines."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _obtener_o_404(db: Session, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")
    return producto


@router.get("", response_model=PaginaProductos)
def listar(
    db: DB,
    q: Annotated[str | None, Query(min_length=1, max_length=60, description="Busca en nombre o SKU")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    incluir_inactivos: bool = False,
):
    consulta = select(Producto)
    if not incluir_inactivos:
        consulta = consulta.where(Producto.activo.is_(True))
    if q:
        patron = f"%{_escapar_like(q)}%"
        consulta = consulta.where(
            or_(Producto.nombre.ilike(patron, escape="\\"), Producto.sku.ilike(patron, escape="\\"))
        )
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    items = db.scalars(consulta.order_by(Producto.id).offset(skip).limit(limit)).all()
    return {"total": total, "items": items}


@router.post("", response_model=ProductoSalida, status_code=status.HTTP_201_CREATED)
def crear(datos: ProductoCrear, db: DB, admin: Admin):
    return servicios.crear_producto(db, datos, admin)


@router.get("/{producto_id}", response_model=ProductoSalida)
def obtener(producto_id: int, db: DB):
    return _obtener_o_404(db, producto_id)


@router.patch("/{producto_id}", response_model=ProductoSalida)
def actualizar(producto_id: int, datos: ProductoActualizar, db: DB, admin: Admin):
    producto = _obtener_o_404(db, producto_id)
    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if "precio" in cambios:
        producto.precio_centavos = a_centavos(cambios.pop("precio"))
    for campo, valor in cambios.items():
        setattr(producto, campo, valor)
    db.commit()
    db.refresh(producto)
    return producto


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar(producto_id: int, db: DB, admin: Admin):
    """Baja lógica: el producto deja de aparecer, pero su historial se conserva."""
    producto = _obtener_o_404(db, producto_id)
    producto.activo = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
