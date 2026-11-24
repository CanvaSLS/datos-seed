# datos-seed

Datos ficticios **reproducibles** (semilla `2026`) para 3 tenants (`UTEC`, `NORTE`, `ANDINO`): **≥ 30 000 registros por microservicio** (≥ 10 000 por tenant).

- **RDS MySQL** (esquema por tenant, `INSERT IGNORE`): `cursos`, `modulos`, `matriculas` (`ms-cursos`) y `tareas`, `entregas` (`ms-evaluaciones`).
- **DynamoDB**: `sp_usuarios` (`ms-auth`), `sp_indicadores` (`ms-analitica`), `sp_notificaciones` (`ms-notificaciones`) y `sp_tarjetas` (`ms-practica`, opcional).
- **S3 (opcional, `seed_s3.py`)**: sube 3 archivos reales de muestra por tenant bajo `tenant_id=<T>/materiales/C0001/...` y los enlaza en `cursos_<t>.modulos`.

> Contraseña de todos los usuarios sembrados: `Demo2026!`.
> Elenco de demo en cada tenant: `profe@<dominio>` (`D001`), `ana.torres@<dominio>` (`A00001`), `valeria.mendoza@<dominio>` (`A00003`), `admin@<dominio>` (`X01`).
> Dominios: `UTEC -> utec.edu.pe`, `NORTE -> inorte.edu.pe`, `ANDINO -> andino.edu.pe`.

## Instalación y variables (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Credenciales temporales del Learner Lab
$env:AWS_ACCESS_KEY_ID     = "<access key>"
$env:AWS_SECRET_ACCESS_KEY = "<secret key>"
$env:AWS_SESSION_TOKEN     = "<session token>"
$env:AWS_DEFAULT_REGION    = "us-east-1"

# RDS MySQL (DbEndpoint del stack sp-infra-dev)
$env:DB_HOST     = "<DbEndpoint>"
$env:DB_USER     = "admin"
$env:DB_PASSWORD = "<contraseña de infra-base>"
```

*(Nota: `requirements.txt` incluye `cryptography`, necesario para autenticar con `pymysql` contra MySQL 8.0 / `caching_sha2_password`.)*

## Flujo recomendado

1. **Verificación previa (antes de insertar, para no duplicar si ya hay datos cargados):**
   ```powershell
   .\.venv\Scripts\python.exe verify_counts.py --sin-practica
   ```
2. **Prueba en memoria sin escribir en AWS:**
   ```powershell
   .\.venv\Scripts\python.exe seed.py --dry-run --sin-practica
   ```
3. **Carga real en AWS (RDS + DynamoDB):**
   ```powershell
   # Sin ms-practica (si el MS opcional aún no está desplegado)
   .\.venv\Scripts\python.exe seed.py --sin-practica --conservar-usuarios

   # Con los 6 microservicios desplegados (incluyendo ms-practica)
   .\.venv\Scripts\python.exe seed.py --conservar-usuarios

   # Solo algunos microservicios o con fecha fija para re-ejecutar otro día sin duplicar notificaciones
   .\.venv\Scripts\python.exe seed.py --only auth,cursos --fecha-base 2026-11-24
   ```
4. **Subir materiales de ejemplo reales a S3 (opcional, tras `seed.py`):**
   ```powershell
   .\.venv\Scripts\python.exe seed_s3.py --dry-run
   .\.venv\Scripts\python.exe seed_s3.py --stage dev
   ```
5. **Evidencia final de conteos (≥ 30 000 por MS y 0 solapamiento entre tenants):**
   ```powershell
   .\.venv\Scripts\python.exe verify_counts.py --sin-practica
   # o sin flag si ms-practica también está desplegado:
   .\.venv\Scripts\python.exe verify_counts.py
   ```

## Opciones útiles de `seed.py`

| Flag | Descripción |
|---|---|
| `--dry-run` | Genera en memoria y muestra conteos sin tocar AWS |
| `--sin-practica` | Excluye `sp_tarjetas` (`ms-practica`) si no está desplegado |
| `--only auth,cursos,...` | Carga solo los microservicios indicados |
| `--per-tenant 300` | Versión liviana para pruebas rápidas (default: `10000`) |
| `--fecha-base YYYY-MM-DD` | Fija la fecha base UTC para evitar duplicar `sp_notificaciones` al repetir otro día |
| `--conservar-usuarios` | Usa escritura condicional en `sp_usuarios` para no pisar cuentas ya migradas a 600k iteraciones por `ms-auth` |

> **Importante:** `sqldb.py` NO se modificó y sigue siendo byte a byte idéntico al de `ms-cursos` y `ms-evaluaciones` (validado por `pruebas-locales/test_e2e.py`).
