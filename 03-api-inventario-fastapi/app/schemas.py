"""Esquemas de entrada y salida de la API (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Rol, TipoMovimiento

# --------------------------------------------------------------------- usuarios


class UsuarioCrear(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class UsuarioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    rol: Rol
    activo: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ------------------------------------------------------------------- productos


class ProductoCrear(BaseModel):
    sku: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=2000)
    precio: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    stock_minimo: int = Field(default=5, ge=0)
    stock_inicial: int = Field(default=0, ge=0)


class ProductoActualizar(BaseModel):
    """PATCH: solo se cambian los campos enviados. El stock NO se edita aquí:
    solo cambia mediante movimientos, para que quede historial."""

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    stock_minimo: int | None = Field(default=None, ge=0)


class ProductoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    nombre: str
    descripcion: str
    precio: Decimal
    stock: int
    stock_minimo: int
    activo: bool
    creado_en: datetime


class PaginaProductos(BaseModel):
    total: int
    items: list[ProductoSalida]


# ----------------------------------------------------------------- movimientos


class MovimientoCrear(BaseModel):
    producto_id: int
    tipo: TipoMovimiento
    cantidad: int = Field(ge=0, description="En 'ajuste' es el nuevo stock total.")
    motivo: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def entradas_y_salidas_requieren_cantidad_positiva(self):
        if self.tipo != TipoMovimiento.ajuste and self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero en entradas y salidas.")
        return self


class MovimientoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    usuario_id: int
    tipo: TipoMovimiento
    cantidad: int
    stock_anterior: int
    stock_resultante: int
    motivo: str
    creado_en: datetime


class PaginaMovimientos(BaseModel):
    total: int
    items: list[MovimientoSalida]


# -------------------------------------------------------------------- reportes


class ResumenInventario(BaseModel):
    productos_activos: int
    unidades_totales: int
    valor_total: Decimal
    productos_stock_bajo: int
    productos_agotados: int
