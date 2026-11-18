import os

# Se definen ANTES de importar la app, porque la configuración se lee al importarla.
os.environ["SECRET_KEY"] = "clave-de-pruebas-que-no-es-secreta-0123456789"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.pop("ADMIN_USERNAME", None)
os.environ.pop("ADMIN_PASSWORD", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import security  # noqa: E402
from app.database import Base, get_db, habilitar_claves_foraneas  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Rol, Usuario  # noqa: E402

PASSWORD = "contraseña-segura-123"


@pytest.fixture(autouse=True, scope="session")
def hash_rapido():
    """scrypt es lento a propósito; en las pruebas se baja su costo para que corran rápido."""
    original = security.SCRYPT_N
    security.SCRYPT_N = 2**4
    yield
    security.SCRYPT_N = original


@pytest.fixture
def db_engine():
    """Una base de datos SQLite en memoria, nueva y vacía para cada prueba."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    habilitar_claves_foraneas(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def fabrica_sesiones(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(fabrica_sesiones):
    def _get_db():
        db = fabrica_sesiones()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def nuevo_usuario(fabrica_sesiones):
    """Inserta un usuario directamente en la base (sin pasar por la API)."""

    def _crear(username, rol=Rol.operador, activo=True):
        with fabrica_sesiones() as db:
            db.add(
                Usuario(
                    username=username,
                    password_hash=security.hashear_password(PASSWORD),
                    rol=rol.value,
                    activo=activo,
                )
            )
            db.commit()

    return _crear


def iniciar_sesion(client, username) -> dict:
    respuesta = client.post("/auth/login", data={"username": username, "password": PASSWORD})
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


@pytest.fixture
def admin(client, nuevo_usuario):
    nuevo_usuario("admin", Rol.admin)
    return iniciar_sesion(client, "admin")


@pytest.fixture
def operador(client, nuevo_usuario):
    nuevo_usuario("operador1", Rol.operador)
    return iniciar_sesion(client, "operador1")


@pytest.fixture
def crear_producto(client, admin):
    def _crear(sku="LAP-001", nombre="Laptop 14", precio="10.00", stock_inicial=0,
               stock_minimo=5, descripcion=""):
        respuesta = client.post(
            "/productos",
            json={
                "sku": sku,
                "nombre": nombre,
                "descripcion": descripcion,
                "precio": precio,
                "stock_inicial": stock_inicial,
                "stock_minimo": stock_minimo,
            },
            headers=admin,
        )
        assert respuesta.status_code == 201, respuesta.text
        return respuesta.json()

    return _crear
