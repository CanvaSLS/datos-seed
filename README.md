# datos-seed

Datos ficticios **reproducibles** (semilla 2026) para 3 tenants (UTEC, NORTE, ANDINO): ≥ 30 000 registros por microservicio (≥ 10 000 por tenant).

```bash
python3 seed.py --dry-run               # genera en memoria y muestra conteos (sin AWS)
python3 seed.py                         # carga todas las tablas (tras desplegar los servicios)
python3 seed.py --only auth,cursos      # solo algunos microservicios
python3 verify_counts.py                # evidencia: conteo por tenant y microservicio (Query COUNT)
```
Requiere `boto3` (`pip install boto3`) y credenciales del Learner Lab. Contraseña de todos los usuarios: `Demo2026!`.
Elenco de la demo (en cada tenant): `profe@<dominio>` (docente D001), `ana.torres@`, `valeria.mendoza@` (alumnas), `admin@<dominio>`.
Dominios: `utec.edu.pe`, `inorte.edu.pe`, `andino.edu.pe`. Las fechas son relativas a "hoy": siempre hay tareas vencidas y una abierta. Repetir el seed el mismo día no duplica filas (la referencia de "hoy" es la medianoche UTC); otro día sí añadiría notificaciones nuevas.

## RDS (cursos y evaluaciones)
`sp_cursos`, `sp_modulos`, `sp_matriculas`, `sp_tareas` y `sp_entregas` se cargan en **RDS MySQL** (esquema por tenant) con `INSERT IGNORE`; el resto sigue en DynamoDB.
```bash
pip install -r requirements.txt
export DB_HOST=<DbEndpoint de infra-base> DB_USER=admin DB_PASSWORD='...'
python3 seed.py                  # todo; o:  --only cursos,evaluaciones   /   --only auth,analitica,notificaciones,practica
python3 verify_counts.py         # conteos por tenant (RDS: COUNT(*); DynamoDB: Query COUNT)
```
`sqldb.py` es idéntico al de los microservicios (la prueba lo verifica). Repetir el seed el mismo día no duplica filas.
