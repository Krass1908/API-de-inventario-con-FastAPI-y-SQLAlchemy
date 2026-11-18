from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.models import Usuario
from app.security import hashear_password, verificar_password

from .conftest import PASSWORD, iniciar_sesion

CLAVE_AJENA = "otra-clave-distinta-de-al-menos-32-caracteres!!"


def _token(clave, algoritmo="HS256", **cambios):
    payload = {
        "sub": "operador1",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    payload.update(cambios)
    return jwt.encode(payload, clave, algorithm=algoritmo)


def _con_token(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------- registro
def test_registro_crea_operador_y_no_expone_la_password(client):
    respuesta = client.post("/auth/registro", json={"username": "Ana_01", "password": PASSWORD})
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["username"] == "ana_01"  # se guarda en minúsculas
    assert cuerpo["rol"] == "operador"
    assert "password" not in cuerpo and "password_hash" not in cuerpo


def test_registro_no_permite_elegir_el_rol(client):
    respuesta = client.post(
        "/auth/registro", json={"username": "intruso", "password": PASSWORD, "rol": "admin"}
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "operador"


def test_registro_rechaza_usuario_repetido_sin_importar_mayusculas(client):
    assert client.post("/auth/registro", json={"username": "ana", "password": PASSWORD}).status_code == 201
    repetido = client.post("/auth/registro", json={"username": "ANA", "password": PASSWORD})
    assert repetido.status_code == 409


@pytest.mark.parametrize(
    "datos",
    [
        {"username": "ab", "password": PASSWORD},  # muy corto
        {"username": "con espacios", "password": PASSWORD},  # caracteres no permitidos
        {"username": "valido", "password": "corta"},  # contraseña débil
    ],
)
def test_registro_valida_los_datos(client, datos):
    assert client.post("/auth/registro", json=datos).status_code == 422


# ---------------------------------------------------------------------- login
def test_login_entrega_un_token_que_sirve(client):
    client.post("/auth/registro", json={"username": "ana", "password": PASSWORD})
    cabeceras = iniciar_sesion(client, "ana")
    perfil = client.get("/auth/yo", headers=cabeceras)
    assert perfil.status_code == 200
    assert perfil.json()["username"] == "ana"


def test_login_fallido_da_el_mismo_error_exista_o_no_el_usuario(client, nuevo_usuario):
    nuevo_usuario("ana")
    mala_password = client.post("/auth/login", data={"username": "ana", "password": "incorrecta1"})
    no_existe = client.post("/auth/login", data={"username": "fantasma", "password": "incorrecta1"})
    assert mala_password.status_code == no_existe.status_code == 401
    assert mala_password.json() == no_existe.json()


# -------------------------------------------------------------------- tokens
@pytest.mark.parametrize("ruta", ["/auth/yo", "/productos", "/movimientos", "/reportes/resumen"])
def test_las_rutas_protegidas_exigen_token(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_rechaza_token_con_firma_falsa(client, nuevo_usuario):
    nuevo_usuario("operador1")
    assert client.get("/auth/yo", headers=_con_token(_token(CLAVE_AJENA))).status_code == 401


def test_rechaza_token_expirado(client, nuevo_usuario):
    nuevo_usuario("operador1")
    vencido = _token(
        get_settings().secret_key, exp=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    assert client.get("/auth/yo", headers=_con_token(vencido)).status_code == 401


def test_rechaza_token_sin_firma_algoritmo_none(client, nuevo_usuario):
    nuevo_usuario("operador1")
    sin_firma = _token(None, algoritmo="none")
    assert client.get("/auth/yo", headers=_con_token(sin_firma)).status_code == 401


def test_rechaza_token_sin_fecha_de_expiracion(client, nuevo_usuario):
    nuevo_usuario("operador1")
    payload = {"sub": "operador1"}
    eterno = jwt.encode(payload, get_settings().secret_key, algorithm="HS256")
    assert client.get("/auth/yo", headers=_con_token(eterno)).status_code == 401


def test_usuario_desactivado_pierde_acceso_aunque_su_token_siga_vigente(
    client, nuevo_usuario, fabrica_sesiones
):
    nuevo_usuario("ana")
    cabeceras = iniciar_sesion(client, "ana")
    assert client.get("/auth/yo", headers=cabeceras).status_code == 200

    with fabrica_sesiones() as db:
        db.query(Usuario).filter_by(username="ana").one().activo = False
        db.commit()

    assert client.get("/auth/yo", headers=cabeceras).status_code == 401


def test_usuario_desactivado_no_puede_iniciar_sesion(client, nuevo_usuario):
    nuevo_usuario("baja", activo=False)
    respuesta = client.post("/auth/login", data={"username": "baja", "password": PASSWORD})
    assert respuesta.status_code == 401


# ------------------------------------------------------------------ contraseñas
def test_hash_usa_sal_aleatoria_y_se_verifica():
    h1, h2 = hashear_password("mi-clave-123"), hashear_password("mi-clave-123")
    assert h1 != h2  # misma contraseña, distinto hash
    assert "mi-clave-123" not in h1
    assert verificar_password("mi-clave-123", h1)
    assert not verificar_password("otra-clave-456", h1)


@pytest.mark.parametrize("basura", ["", "no-es-un-hash", "scrypt$a$b$c$d$e", "md5$1$2$3$ab$cd"])
def test_un_hash_mal_formado_nunca_valida(basura):
    assert verificar_password("lo-que-sea", basura) is False
