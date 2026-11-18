from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Producto
from ..schemas import ProductoSalida, ResumenInventario
from ..security import get_usuario_actual

router = APIRouter(
    prefix="/reportes",
    tags=["reportes"],
    dependencies=[Depends(get_usuario_actual)],
)

DB = Annotated[Session, Depends(get_db)]


@router.get("/stock-bajo", response_model=list[ProductoSalida])
def stock_bajo(db: DB):
    """Productos activos cuyo stock es igual o menor a su mínimo, los más críticos primero."""
    consulta = (
        select(Producto)
        .where(Producto.activo.is_(True), Producto.stock <= Producto.stock_minimo)
        .order_by(Producto.stock, Producto.id)
    )
    return db.scalars(consulta).all()


@router.get("/resumen", response_model=ResumenInventario)
def resumen(db: DB):
    """Indicadores del inventario activo, calculados directamente en la base de datos."""
    fila = db.execute(
        select(
            func.count(Producto.id),
            func.coalesce(func.sum(Producto.stock), 0),
            func.coalesce(func.sum(Producto.precio_centavos * Producto.stock), 0),
            func.coalesce(func.sum(case((Producto.stock <= Producto.stock_minimo, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Producto.stock == 0, 1), else_=0)), 0),
        ).where(Producto.activo.is_(True))
    ).one()
    return ResumenInventario(
        productos_activos=fila[0],
        unidades_totales=fila[1],
        valor_total=(Decimal(fila[2]) / 100).quantize(Decimal("0.01")),
        productos_stock_bajo=fila[3],
        productos_agotados=fila[4],
    )
