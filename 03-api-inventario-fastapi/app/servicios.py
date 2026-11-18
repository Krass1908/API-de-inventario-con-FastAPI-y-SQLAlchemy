"""Lógica de negocio: la parte que decide qué está permitido y qué no.

Los routers solo reciben la petición y devuelven la respuesta; las reglas
(stock suficiente, SKU único, historial de movimientos) viven aquí.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Movimiento, Producto, TipoMovimiento, Usuario, a_centavos
from .schemas import MovimientoCrear, ProductoCrear


class ErrorNegocio(Exception):
    """Una regla de negocio impide la operación. Se convierte en una respuesta HTTP."""

    def __init__(self, mensaje: str, status_code: int = 409):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


def crear_producto(db: Session, datos: ProductoCrear, usuario: Usuario) -> Producto:
    sku = datos.sku.strip().upper()
    if db.scalar(select(Producto.id).where(Producto.sku == sku)) is not None:
        raise ErrorNegocio(f"Ya existe un producto con SKU {sku}.")

    producto = Producto(
        sku=sku,
        nombre=datos.nombre.strip(),
        descripcion=datos.descripcion,
        precio_centavos=a_centavos(datos.precio),
        stock=datos.stock_inicial,
        stock_minimo=datos.stock_minimo,
    )
    db.add(producto)
    try:
        db.flush()  # asigna el id sin cerrar la transacción
        if datos.stock_inicial > 0:
            db.add(
                Movimiento(
                    producto_id=producto.id,
                    usuario_id=usuario.id,
                    tipo=TipoMovimiento.entrada.value,
                    cantidad=datos.stock_inicial,
                    stock_anterior=0,
                    stock_resultante=datos.stock_inicial,
                    motivo="Stock inicial",
                )
            )
        db.commit()  # producto y movimiento se guardan juntos o no se guarda nada
    except IntegrityError:
        db.rollback()  # otra petición creó el mismo SKU justo antes
        raise ErrorNegocio(f"Ya existe un producto con SKU {sku}.") from None
    db.refresh(producto)
    return producto


def registrar_movimiento(db: Session, datos: MovimientoCrear, usuario: Usuario) -> Movimiento:
    # with_for_update() bloquea la fila del producto durante la transacción: en
    # PostgreSQL, dos salidas simultáneas no pueden leer el mismo stock y dejarlo
    # en negativo. (SQLite ignora la cláusula pero ya serializa las escrituras.)
    producto = db.scalar(
        select(Producto).where(Producto.id == datos.producto_id).with_for_update()
    )
    if producto is None:
        raise ErrorNegocio("Producto no encontrado.", 404)
    if not producto.activo:
        raise ErrorNegocio("El producto está inactivo; no admite movimientos.")

    anterior = producto.stock
    if datos.tipo == TipoMovimiento.entrada:
        nuevo = anterior + datos.cantidad
    elif datos.tipo == TipoMovimiento.salida:
        if datos.cantidad > anterior:
            raise ErrorNegocio(
                f"Stock insuficiente: disponible {anterior}, solicitado {datos.cantidad}."
            )
        nuevo = anterior - datos.cantidad
    else:  # ajuste: conteo físico
        nuevo = datos.cantidad

    producto.stock = nuevo
    movimiento = Movimiento(
        producto_id=producto.id,
        usuario_id=usuario.id,
        tipo=datos.tipo.value,
        cantidad=datos.cantidad,
        stock_anterior=anterior,
        stock_resultante=nuevo,
        motivo=datos.motivo.strip(),
    )
    db.add(movimiento)
    db.commit()
    db.refresh(movimiento)
    return movimiento
