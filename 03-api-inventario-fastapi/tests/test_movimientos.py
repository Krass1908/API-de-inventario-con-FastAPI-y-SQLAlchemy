import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Producto


def _mover(client, cabeceras, producto_id, tipo, cantidad, motivo=""):
    return client.post(
        "/movimientos",
        json={"producto_id": producto_id, "tipo": tipo, "cantidad": cantidad, "motivo": motivo},
        headers=cabeceras,
    )


def _stock(client, cabeceras, producto_id):
    return client.get(f"/productos/{producto_id}", headers=cabeceras).json()["stock"]


# ------------------------------------------------------------------ movimientos
def test_entrada_salida_y_ajuste_actualizan_el_stock_y_dejan_rastro(client, operador, crear_producto):
    pid = crear_producto(stock_inicial=10)["id"]

    entrada = _mover(client, operador, pid, "entrada", 5, "Llegó pedido")
    assert entrada.status_code == 201
    assert (entrada.json()["stock_anterior"], entrada.json()["stock_resultante"]) == (10, 15)

    salida = _mover(client, operador, pid, "salida", 4, "Venta")
    assert (salida.json()["stock_anterior"], salida.json()["stock_resultante"]) == (15, 11)

    ajuste = _mover(client, operador, pid, "ajuste", 7, "Conteo físico")
    assert (ajuste.json()["stock_anterior"], ajuste.json()["stock_resultante"]) == (11, 7)
    assert _stock(client, operador, pid) == 7


def test_salida_mayor_al_stock_se_rechaza_y_no_cambia_nada(client, operador, crear_producto):
    pid = crear_producto(stock_inicial=3)["id"]
    respuesta = _mover(client, operador, pid, "salida", 4)

    assert respuesta.status_code == 409
    assert "disponible 3" in respuesta.json()["detail"]
    assert _stock(client, operador, pid) == 3
    historial = client.get("/movimientos", params={"producto_id": pid}, headers=operador).json()
    assert historial["total"] == 1  # solo el stock inicial; el intento fallido no se registra


def test_salida_exacta_deja_el_stock_en_cero(client, operador, crear_producto):
    pid = crear_producto(stock_inicial=5)["id"]
    assert _mover(client, operador, pid, "salida", 5).status_code == 201
    assert _stock(client, operador, pid) == 0


def test_ajuste_a_cero_es_valido(client, operador, crear_producto):
    pid = crear_producto(stock_inicial=5)["id"]
    assert _mover(client, operador, pid, "ajuste", 0, "Producto dañado").status_code == 201
    assert _stock(client, operador, pid) == 0


@pytest.mark.parametrize("tipo", ["entrada", "salida"])
def test_entradas_y_salidas_exigen_cantidad_positiva(client, operador, crear_producto, tipo):
    pid = crear_producto(stock_inicial=5)["id"]
    assert _mover(client, operador, pid, tipo, 0).status_code == 422
    assert _mover(client, operador, pid, tipo, -2).status_code == 422


def test_tipo_de_movimiento_desconocido_da_422(client, operador, crear_producto):
    pid = crear_producto()["id"]
    assert _mover(client, operador, pid, "robo", 1).status_code == 422


def test_movimiento_de_producto_inexistente_da_404(client, operador):
    assert _mover(client, operador, 9999, "entrada", 1).status_code == 404


def test_producto_inactivo_no_admite_movimientos(client, admin, operador, crear_producto):
    pid = crear_producto(stock_inicial=5)["id"]
    client.delete(f"/productos/{pid}", headers=admin)
    respuesta = _mover(client, operador, pid, "entrada", 1)
    assert respuesta.status_code == 409
    assert "inactivo" in respuesta.json()["detail"]


def test_sin_token_no_se_puede_mover_stock(client, crear_producto):
    pid = crear_producto()["id"]
    respuesta = client.post("/movimientos", json={"producto_id": pid, "tipo": "entrada", "cantidad": 1})
    assert respuesta.status_code == 401


def test_la_base_de_datos_impide_stock_negativo_aunque_falle_el_codigo(
    crear_producto, fabrica_sesiones
):
    pid = crear_producto(stock_inicial=2)["id"]
    with fabrica_sesiones() as db:
        db.get(Producto, pid).stock = -1
        with pytest.raises(IntegrityError):
            db.commit()


# -------------------------------------------------------------------- historial
def test_historial_con_filtros_y_orden_descendente(client, operador, crear_producto):
    a = crear_producto(sku="A-1", stock_inicial=10)["id"]
    b = crear_producto(sku="B-1", stock_inicial=10)["id"]
    _mover(client, operador, a, "salida", 3)
    _mover(client, operador, b, "salida", 2)
    _mover(client, operador, a, "entrada", 1)

    del_producto_a = client.get("/movimientos", params={"producto_id": a}, headers=operador).json()
    assert del_producto_a["total"] == 3
    assert [m["tipo"] for m in del_producto_a["items"]] == ["entrada", "salida", "entrada"]  # más reciente primero

    solo_salidas = client.get("/movimientos", params={"tipo": "salida"}, headers=operador).json()
    assert solo_salidas["total"] == 2

    paginado = client.get("/movimientos", params={"limit": 2}, headers=operador).json()
    assert paginado["total"] == 5 and len(paginado["items"]) == 2


def test_cada_movimiento_registra_quien_lo_hizo(client, operador, crear_producto):
    pid = crear_producto(stock_inicial=1)["id"]
    mi_id = client.get("/auth/yo", headers=operador).json()["id"]
    movimiento = _mover(client, operador, pid, "entrada", 1).json()
    assert movimiento["usuario_id"] == mi_id


# --------------------------------------------------------------------- reportes
def test_reporte_de_stock_bajo_ordena_lo_mas_critico_primero(client, admin, crear_producto):
    crear_producto(sku="OK-1", stock_inicial=20, stock_minimo=5)
    crear_producto(sku="BAJO-1", stock_inicial=3, stock_minimo=5)
    crear_producto(sku="CERO-1", stock_inicial=0, stock_minimo=1)
    limite = crear_producto(sku="LIM-1", stock_inicial=5, stock_minimo=5)  # igual al mínimo cuenta

    reporte = client.get("/reportes/stock-bajo", headers=admin).json()
    assert [p["sku"] for p in reporte] == ["CERO-1", "BAJO-1", limite["sku"]]


def test_resumen_calcula_valor_y_conteos_solo_de_productos_activos(client, admin, crear_producto):
    crear_producto(sku="A", precio="10.00", stock_inicial=3, stock_minimo=5)  # bajo, 30.00
    crear_producto(sku="B", precio="2.50", stock_inicial=10, stock_minimo=5)  # ok, 25.00
    crear_producto(sku="C", precio="100.00", stock_inicial=0, stock_minimo=1)  # agotado, 0
    baja = crear_producto(sku="D", precio="999.99", stock_inicial=50)  # se dará de baja
    client.delete(f"/productos/{baja['id']}", headers=admin)

    resumen = client.get("/reportes/resumen", headers=admin).json()
    assert resumen == {
        "productos_activos": 3,
        "unidades_totales": 13,
        "valor_total": "55.00",
        "productos_stock_bajo": 2,
        "productos_agotados": 1,
    }


def test_resumen_con_base_vacia(client, admin):
    resumen = client.get("/reportes/resumen", headers=admin).json()
    assert resumen["productos_activos"] == 0 and resumen["valor_total"] == "0.00"


def test_endpoint_de_salud_es_publico(client):
    assert client.get("/salud").json() == {"estado": "ok"}
