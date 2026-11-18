"""Modelos de base de datos (SQLAlchemy 2.0)."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Rol(str, enum.Enum):
    admin = "admin"
    operador = "operador"


class TipoMovimiento(str, enum.Enum):
    entrada = "entrada"  # llega mercancía: suma al stock
    salida = "salida"  # se vende o se retira: resta del stock
    ajuste = "ajuste"  # conteo físico: fija el stock en la cantidad indicada


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def a_centavos(precio: Decimal) -> int:
    """Los precios se guardan como enteros (centavos) para evitar errores de redondeo."""
    return int(precio * 100)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(16), default=Rol.operador.value)
    activo: Mapped[bool] = mapped_column(default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        # Última línea de defensa: aunque el código tuviera un error, la base
        # nunca aceptará stock ni precios negativos.
        CheckConstraint("stock >= 0", name="ck_producto_stock_no_negativo"),
        CheckConstraint("stock_minimo >= 0", name="ck_producto_stock_minimo_no_negativo"),
        CheckConstraint("precio_centavos >= 0", name="ck_producto_precio_no_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    precio_centavos: Mapped[int] = mapped_column()
    stock: Mapped[int] = mapped_column(default=0)
    stock_minimo: Mapped[int] = mapped_column(default=5)
    activo: Mapped[bool] = mapped_column(default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    movimientos: Mapped[list["Movimiento"]] = relationship(back_populates="producto")

    @property
    def precio(self) -> Decimal:
        return (Decimal(self.precio_centavos) / 100).quantize(Decimal("0.01"))


class Movimiento(Base):
    """Cada cambio de stock queda registrado: quién, cuándo, cuánto y por qué."""

    __tablename__ = "movimientos"
    __table_args__ = (CheckConstraint("cantidad >= 0", name="ck_movimiento_cantidad"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(String(10), index=True)
    cantidad: Mapped[int] = mapped_column()
    stock_anterior: Mapped[int] = mapped_column()
    stock_resultante: Mapped[int] = mapped_column()
    motivo: Mapped[str] = mapped_column(String(200), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    producto: Mapped[Producto] = relationship(back_populates="movimientos")
