# 📦 API de Inventario con FastAPI

API REST para controlar un inventario: catálogo de productos, **movimientos de stock con historial completo**, reportes y **autenticación JWT con roles**. Incluye pruebas automáticas, Docker y CI con GitHub Actions.

!\[Python](https://img.shields.io/badge/python-3.11%2B-blue)
!\[FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)
!\[SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red)
!\[CI](https://github.com/Krass1908/api-inventario-fastapi/actions/workflows/ci.yml/badge.svg)

## Características

* **Autenticación JWT** con flujo estándar OAuth2 (el botón *Authorize* de Swagger funciona).
* **Dos roles**: `admin` gestiona el catálogo; `operador` consulta y registra movimientos.
* **Stock trazable**: el stock solo cambia mediante movimientos (`entrada`, `salida`, `ajuste`) y cada uno guarda quién lo hizo, cuándo, el stock anterior y el resultante.
* **Reglas de negocio**: no se puede sacar más de lo que hay, el SKU es único, un producto dado de baja no admite movimientos.
* **Reportes**: productos con stock bajo y resumen de valor del inventario (calculado en SQL).
* Búsqueda, paginación y filtros; documentación interactiva automática en `/docs`.

## Decisiones de diseño (lo que más conviene mirar)

|Tema|Decisión|
|-|-|
|Contraseñas|Hash con `scrypt` + sal aleatoria, comparación en tiempo constante. Nunca se guardan ni se devuelven en claro.|
|Login|Mismo error y mismo tiempo de respuesta exista o no el usuario (evita enumerar cuentas).|
|JWT|Firma `HS256` con clave de entorno (mínimo 32 caracteres), expiración obligatoria, algoritmo fijado al decodificar (rechaza tokens `alg: none`).|
|Revocación|En cada petición se consulta al usuario en la base: si se desactiva o cambia de rol, el efecto es inmediato aunque su token siga vigente.|
|Registro|Siempre crea `operador`; el rol no se puede elegir. El primer admin se crea con variables de entorno.|
|Dinero|Se guarda como **enteros en centavos** y viaja como texto decimal (`"1299.90"`). Sin errores de punto flotante.|
|Concurrencia|`SELECT ... FOR UPDATE` al mover stock: en PostgreSQL dos salidas simultáneas no pueden dejarlo en negativo.|
|Integridad|`CHECK (stock >= 0)` y claves foráneas en la base: una barrera extra por si el código fallara.|
|Atomicidad|Crear un producto con stock inicial guarda producto y movimiento en la misma transacción.|
|Búsqueda|`%` y `\_` escritos por el usuario se escapan; no actúan como comodines SQL.|
|Capas|Routers (HTTP) → servicios (reglas de negocio) → modelos (base de datos).|
|Bajas|`DELETE` es baja lógica: el producto desaparece de los listados pero su historial se conserva.|

## Ejecutar con Docker

```bash
git clone https://github.com/<tu-usuario>/api-inventario-fastapi.git
cd api-inventario-fastapi
cp .env.example .env        # edita SECRET\_KEY y ADMIN\_PASSWORD
docker compose up --build
```

La API queda en [http://localhost:8000](http://localhost:8000) y la documentación en [http://localhost:8000/docs](http://localhost:8000/docs). La base de datos vive en un volumen, así que sobrevive a los reinicios.

## Ejecutar sin Docker

```bash
python -m venv .venv \&\& source .venv/bin/activate   # en Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt

export SECRET\_KEY="$(python -c 'import secrets; print(secrets.token\_urlsafe(48))')"
export ADMIN\_USERNAME=admin ADMIN\_PASSWORD=una-contraseña-segura
uvicorn app.main:app --reload
```

## Ejemplo de uso

```bash
# 1. Iniciar sesión como administrador (formulario OAuth2) y guardar el token
TOKEN=$(curl -s -X POST localhost:8000/auth/login \\
  -d "username=admin\&password=una-contraseña-segura" | python -c "import sys,json; print(json.load(sys.stdin)\['access\_token'])")

# 2. Crear un producto con 12 unidades iniciales
curl -s -X POST localhost:8000/productos \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{"sku":"mou-01","nombre":"Mouse inalámbrico","precio":"249.90","stock\_inicial":12,"stock\_minimo":5}'

# 3. Registrar una salida de 9 unidades
curl -s -X POST localhost:8000/movimientos \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{"producto\_id":1,"tipo":"salida","cantidad":9,"motivo":"Venta"}'
# {"id":2,"producto\_id":1,"tipo":"salida","cantidad":9,"stock\_anterior":12,"stock\_resultante":3,...}

# 4. Intentar sacar más de lo que hay
curl -s -X POST localhost:8000/movimientos \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{"producto\_id":1,"tipo":"salida","cantidad":20}'
# {"detail":"Stock insuficiente: disponible 3, solicitado 20."}

# 5. Resumen del inventario
curl -s localhost:8000/reportes/resumen -H "Authorization: Bearer $TOKEN"
# {"productos\_activos":1,"unidades\_totales":3,"valor\_total":"749.70","productos\_stock\_bajo":1,"productos\_agotados":0}
```

## Endpoints

|Método|Ruta|Acceso|Descripción|
|-|-|-|-|
|POST|`/auth/registro`|público|Crea una cuenta `operador`|
|POST|`/auth/login`|público|Devuelve un JWT|
|GET|`/auth/yo`|autenticado|Datos del usuario del token|
|GET|`/productos`|autenticado|Lista con `q`, `skip`, `limit`, `incluir\_inactivos`|
|GET|`/productos/{id}`|autenticado|Detalle|
|POST|`/productos`|admin|Crea producto (con stock inicial opcional)|
|PATCH|`/productos/{id}`|admin|Edita nombre, descripción, precio o stock mínimo|
|DELETE|`/productos/{id}`|admin|Baja lógica|
|POST|`/movimientos`|autenticado|Entrada, salida o ajuste de stock|
|GET|`/movimientos`|autenticado|Historial con filtros `producto\_id`, `tipo`|
|GET|`/reportes/stock-bajo`|autenticado|Productos en o bajo su stock mínimo|
|GET|`/reportes/resumen`|autenticado|Unidades, valor total y alertas|
|GET|`/salud`|público|Comprobación de estado|

Códigos que devuelve la API: `201` creado, `204` baja, `401` sin sesión o token inválido, `403` sin permiso, `404` no existe, `409` choca con una regla de negocio (SKU repetido, stock insuficiente), `422` datos inválidos.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

59 pruebas contra una base SQLite en memoria (nueva para cada prueba). Cubren, entre otras cosas: tokens falsos, expirados, sin firma y sin expiración; usuario desactivado con token vigente; permisos por rol; validaciones de entrada; paginación y búsqueda; las reglas de stock; el `CHECK` de la base; y los cálculos de los reportes.

## Estructura

```
app/
├── main.py          # crea la app, registra routers y errores, siembra el admin
├── config.py        # variables de entorno
├── database.py      # motor, sesión por petición, claves foráneas en SQLite
├── models.py        # Usuario, Producto, Movimiento
├── schemas.py       # validación de entradas y formato de salidas (Pydantic)
├── security.py      # scrypt, JWT, dependencias get\_usuario\_actual / requiere\_admin
├── servicios.py     # reglas de negocio (stock, SKU, historial)
└── routers/         # auth, productos, movimientos, reportes
tests/
Dockerfile · docker-compose.yml · .github/workflows/ci.yml
```

## Despliegue y CI

* **Docker**: imagen basada en `python:3.12-slim`, usuario sin privilegios, `HEALTHCHECK` sobre `/salud` y capa de dependencias cacheable.
* **GitHub Actions**: en cada push y pull request corre `pytest` en Python 3.11, 3.12 y 3.13, y después comprueba que la imagen Docker construye.

## Qué mejoraría para producción

* Migraciones con **Alembic** (hoy las tablas se crean al arrancar).
* **PostgreSQL** en lugar de SQLite (el código ya está preparado: bloqueo de filas y `DATABASE\_URL`).
* Límite de intentos de login y *refresh tokens*.
* Registro de auditoría de cambios de precio y de rol.

