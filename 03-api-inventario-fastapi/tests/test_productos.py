import pytest


def test_admin_crea_producto_con_stock_inicial_y_queda_en_el_historial(client, admin, crear_producto):
    producto = crear_producto(sku="lap-001", precio="1299.90", stock_inicial=8)

    assert producto["sku"] == "LAP-001"  # se normaliza a mayúsculas
    assert producto["precio"] == "1299.90"  # el dinero viaja como texto decimal exacto
    assert producto["stock"] == 8 and producto["activo"] is True

    historial = client.get("/movimientos", params={"producto_id": producto["id"]}, headers=admin).json()
    assert historial["total"] == 1
    assert historial["items"][0]["motivo"] == "Stock inicial"
    assert historial["items"][0]["stock_resultante"] == 8


def test_operador_no_puede_crear_ni_modificar_ni_borrar(client, operador, crear_producto):
    producto = crear_producto()
    nuevo = {"sku": "X-1", "nombre": "Algo", "precio": "1.00"}

    assert client.post("/productos", json=nuevo, headers=operador).status_code == 403
    assert client.patch(f"/productos/{producto['id']}", json={"nombre": "Z"}, headers=operador).status_code == 403
    assert client.delete(f"/productos/{producto['id']}", headers=operador).status_code == 403


def test_operador_si_puede_consultar(client, operador, crear_producto):
    producto = crear_producto()
    assert client.get("/productos", headers=operador).json()["total"] == 1
    assert client.get(f"/productos/{producto['id']}", headers=operador).status_code == 200


def test_sku_duplicado_da_conflicto_sin_importar_mayusculas(client, admin, crear_producto):
    crear_producto(sku="ABC-1")
    repetido = client.post(
        "/productos", json={"sku": "abc-1", "nombre": "Otro", "precio": "5.00"}, headers=admin
    )
    assert repetido.status_code == 409
    assert "ABC-1" in repetido.json()["detail"]


@pytest.mark.parametrize(
    "cambios",
    [
        {"precio": "-1.00"},
        {"precio": "10.999"},  # más de 2 decimales
        {"precio": "abc"},
        {"nombre": ""},
        {"sku": "con espacios"},
        {"stock_inicial": -3},
        {"stock_minimo": -1},
    ],
)
def test_validaciones_al_crear(client, admin, cambios):
    datos = {"sku": "OK-1", "nombre": "Producto", "precio": "10.00", **cambios}
    assert client.post("/productos", json=datos, headers=admin).status_code == 422


def test_obtener_producto_inexistente_da_404(client, operador):
    assert client.get("/productos/9999", headers=operador).status_code == 404


def test_listado_con_busqueda_y_paginacion(client, admin, crear_producto):
    for i in range(1, 6):
        crear_producto(sku=f"MOU-{i}", nombre=f"Mouse modelo {i}")
    crear_producto(sku="TEC-1", nombre="Teclado mecánico")

    todos = client.get("/productos", headers=admin).json()
    assert todos["total"] == 6

    pagina = client.get("/productos", params={"skip": 2, "limit": 2}, headers=admin).json()
    assert pagina["total"] == 6 and len(pagina["items"]) == 2
    assert [p["sku"] for p in pagina["items"]] == ["MOU-3", "MOU-4"]

    por_nombre = client.get("/productos", params={"q": "teclado"}, headers=admin).json()
    assert [p["sku"] for p in por_nombre["items"]] == ["TEC-1"]

    por_sku = client.get("/productos", params={"q": "mou-"}, headers=admin).json()
    assert por_sku["total"] == 5


def test_la_busqueda_no_interpreta_comodines_de_sql(client, admin, crear_producto):
    crear_producto(sku="A-1", nombre="Alfa")
    crear_producto(sku="B-2", nombre="Beta")
    for comodin in ["%", "_"]:
        assert client.get("/productos", params={"q": comodin}, headers=admin).json()["total"] == 0


def test_limite_de_paginacion_fuera_de_rango_da_422(client, admin):
    assert client.get("/productos", params={"limit": 1000}, headers=admin).status_code == 422
    assert client.get("/productos", params={"skip": -1}, headers=admin).status_code == 422


def test_patch_actualiza_solo_lo_enviado(client, admin, crear_producto):
    producto = crear_producto(nombre="Original", precio="10.00", stock_minimo=5)
    respuesta = client.patch(f"/productos/{producto['id']}", json={"precio": "12.50"}, headers=admin)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["precio"] == "12.50"
    assert cuerpo["nombre"] == "Original" and cuerpo["stock_minimo"] == 5


def test_patch_no_permite_cambiar_stock_ni_sku(client, admin, crear_producto):
    producto = crear_producto(sku="FIJO-1", stock_inicial=4)
    respuesta = client.patch(
        f"/productos/{producto['id']}", json={"stock": 999, "sku": "HACK-1", "nombre": "Nuevo"}, headers=admin
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["stock"] == 4 and cuerpo["sku"] == "FIJO-1" and cuerpo["nombre"] == "Nuevo"


def test_patch_con_null_no_borra_campos_obligatorios(client, admin, crear_producto):
    producto = crear_producto(nombre="Conservar")
    respuesta = client.patch(f"/productos/{producto['id']}", json={"nombre": None}, headers=admin)
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Conservar"


def test_borrar_es_baja_logica_y_conserva_el_historial(client, admin, crear_producto):
    producto = crear_producto(stock_inicial=3)
    assert client.delete(f"/productos/{producto['id']}", headers=admin).status_code == 204

    assert client.get("/productos", headers=admin).json()["total"] == 0
    con_inactivos = client.get("/productos", params={"incluir_inactivos": True}, headers=admin).json()
    assert con_inactivos["total"] == 1 and con_inactivos["items"][0]["activo"] is False

    historial = client.get("/movimientos", params={"producto_id": producto["id"]}, headers=admin).json()
    assert historial["total"] == 1
