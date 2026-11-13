#!/usr/bin/env python3
"""seed.py · datos ficticios multi-tenant para StudyPulse (rúbrica: >= 30 000 registros por
microservicio, repartidos en 3 tenants -> >= 10 000 por tenant y por microservicio).

  python seed.py --dry-run                       # genera en memoria y muestra conteos (sin AWS)
  python seed.py                                 # carga TODO: DynamoDB (us-east-1) + RDS MySQL (cursos, evaluaciones)
                                                 #   RDS necesita: export DB_HOST=<endpoint> DB_USER=admin DB_PASSWORD=...
                                                 #   y  pip install -r requirements.txt
  python seed.py --only auth,cursos              # solo esos microservicios
  python seed.py --per-tenant 300                # versión liviana para pruebas

Reproducible: semilla fija (2026) -> todos los integrantes generan exactamente el mismo conjunto.
Las fechas son relativas a "hoy" (siempre hay tareas vencidas y una abierta). Repetirlo el mismo día no duplica filas.
Contraseña de TODOS los usuarios sembrados: Demo2026!   (hash PBKDF2 + salt por usuario)
"""
import argparse
import hashlib
import json
import math
import random
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

SEED = 2026
PASSWORD_DEMO = "Demo2026!"
ITERACIONES = 10_000  # debe coincidir con ms-auth/handler.py

TENANTS = {
    "UTEC": {"nombre": "Universidad de Ingeniería y Tecnología", "dominio": "utec.edu.pe"},
    "NORTE": {"nombre": "Instituto del Norte", "dominio": "inorte.edu.pe"},
    "ANDINO": {"nombre": "Colegio Andino", "dominio": "andino.edu.pe"},
}
# tabla -> microservicio (para --only y para el reporte)
MS_DE_TABLA = {
    "sp_usuarios": "auth", "sp_cursos": "cursos", "sp_modulos": "cursos", "sp_matriculas": "cursos",
    "sp_tareas": "evaluaciones", "sp_entregas": "evaluaciones", "sp_indicadores": "analitica",
    "sp_notificaciones": "notificaciones", "sp_tarjetas": "practica",
}

NOMBRES = ["Ana", "Luis", "Valeria", "Mateo", "Camila", "Diego", "Sofía", "Andrés", "Lucía", "Jorge",
           "Fiorella", "Renato", "Daniela", "Sebastián", "Mariana", "Gabriel", "Alejandra", "Marco",
           "Paola", "Rodrigo", "Carla", "Fernando", "Rosa", "Hugo", "Elena", "Pablo", "Natalia", "Iván",
           "Claudia", "Raúl", "Milagros", "Joaquín", "Brenda", "Adrián", "Karen", "Víctor", "Yesenia",
           "Óscar", "Pilar", "Bruno"]
APELLIDOS = ["Torres", "Rojas", "Mendoza", "Salazar", "Vega", "Paredes", "Quispe", "Flores", "Huamán",
             "Castillo", "Ramírez", "Chávez", "Gutiérrez", "Rivera", "Vargas", "Díaz", "Cruz", "Ortiz",
             "Morales", "Silva", "Campos", "Delgado", "Herrera", "Medina", "Núñez", "Ríos", "Soto",
             "Valdez", "Zegarra", "Alvarado", "Benavides", "Cárdenas", "Espinoza", "Fuentes", "Guerrero",
             "Ibáñez", "Lazo", "Montoya", "Navarro", "Olivera"]
CAST = [("Ana", "Torres"), ("Luis", "Rojas"), ("Valeria", "Mendoza"), ("Mateo", "Salazar"),
        ("Camila", "Vega"), ("Diego", "Paredes")]  # alumnos A00001..A00006 = elenco de la demo
CURSOS_BASE = [
    ("CS2032", "Computación en la Nube"), ("CS2031", "Bases de Datos"), ("CS2041", "Ingeniería de Software"),
    ("MA1001", "Cálculo I"), ("MA1002", "Cálculo II"), ("FI1001", "Física General"),
    ("QU1001", "Química General"), ("CS1100", "Introducción a la Computación"), ("CS1101", "Programación I"),
    ("CS1102", "Programación II"), ("CS2100", "Estructuras de Datos"), ("CS2101", "Algoritmos"),
    ("CS2200", "Sistemas Operativos"), ("CS2201", "Redes de Computadoras"), ("CS2300", "Inteligencia Artificial"),
    ("CS2301", "Machine Learning"), ("CS2400", "Seguridad Informática"), ("EC1001", "Economía"),
    ("AD1001", "Administración"), ("CO1001", "Comunicación"), ("ET1001", "Ética Profesional"),
    ("ES1001", "Estadística"), ("ES1002", "Probabilidades"), ("MA1100", "Álgebra Lineal"),
    ("MA1200", "Matemática Discreta"), ("IN1001", "Inglés I"), ("IN1002", "Inglés II"),
    ("PY1001", "Gestión de Proyectos"), ("DI1001", "Diseño de Interfaces"), ("DA1001", "Analítica de Datos")]
COLORES = ["#2677a6", "#2f855a", "#b7791f", "#805ad5", "#c05621", "#2b6cb0", "#b83280", "#2c7a7b"]
MODULOS = ["Introducción", "Fundamentos", "Diseño", "Implementación", "Pruebas", "Despliegue", "Seguridad",
           "Proyecto final"]
TAREAS = ["Laboratorio 1", "Laboratorio 2", "Práctica calificada", "Proyecto parcial"]
DIAS_TAREA = [-38, -24, -10, 18]  # relativo a hoy: 3 vencidas y 1 abierta (para entregar en vivo)
BANCO_QA = [
    ("¿Qué servicio de AWS ejecuta código sin administrar servidores?", "AWS Lambda", ["Amazon EC2", "Amazon RDS", "Amazon S3"]),
    ("¿Qué patrón desacopla productores y consumidores con un tema al que se suscriben varios destinos?", "Publicación/Suscripción (SNS)", ["Petición/respuesta síncrona", "Polling a base de datos", "Monolito compartido"]),
    ("¿Para qué sirve una Dead Letter Queue?", "Guardar mensajes que fallaron tras varios reintentos", ["Acelerar la cola principal", "Cifrar los mensajes", "Duplicar mensajes"]),
    ("En multi-tenancy con una tabla DynamoDB compartida, ¿qué atributo suele ser la clave de partición?", "tenant_id", ["created_at", "color", "password"]),
    ("¿Qué ventaja principal ofrece serverless?", "No se administran servidores y se paga por uso", ["Control total del sistema operativo", "Costo fijo mensual", "Menos servicios que mantener"]),
    ("¿Qué hace un Lambda Authorizer?", "Valida el token y decide si API Gateway deja pasar la petición", ["Almacena archivos", "Balancea carga entre zonas", "Compila el frontend"]),
    ("¿Qué significa que un consumidor sea idempotente?", "Procesar el mismo mensaje dos veces da el mismo resultado", ["Procesa mensajes más rápido", "Nunca falla", "Solo acepta un mensaje"]),
    ("¿Qué herramienta describe la infraestructura como código en un serverless.yml?", "Serverless Framework", ["Postman", "Wireshark", "Excel"]),
    ("¿Dónde se consultan logs JSON con filtros y agregaciones en AWS?", "CloudWatch Logs Insights", ["AWS Budgets", "Amazon SES", "AWS KMS"]),
    ("¿Qué entrega una URL prefirmada de S3?", "Acceso temporal a un objeto privado", ["Acceso público permanente", "Una copia del bucket", "Un certificado TLS"]),
    ("¿Qué escalabilidad agrega más instancias en vez de una más grande?", "Horizontal", ["Vertical", "Diagonal", "Cuántica"]),
    ("¿Qué pilar del Well-Architected se enfoca en proteger datos y accesos?", "Seguridad", ["Optimización de costos", "Sostenibilidad", "Excelencia operativa"]),
]


# ----------------------------------------------------------------------------- utilidades
def slug(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if c.isalpha())


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def D(x):
    return None if x is None else Decimal(str(x))


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), ITERACIONES).hex()


def calcular_riesgo(resumen):  # COPIA de ms-analitica/riesgo.py (mantener igual)
    puntaje, motivos = 0, []
    prom = resumen.get("promedio")
    if prom is not None:
        if prom < 10.5:
            puntaje += 40
            motivos.append(f"R1 · promedio {float(prom):.1f} (menor a 10.5)")
        elif prom < 13:
            puntaje += 20
            motivos.append(f"R1 · promedio {float(prom):.1f} (menor a 13)")
    tard = int(resumen.get("n_tardias") or 0)
    if tard >= 2:
        puntaje += 20
        motivos.append(f"R2 · {tard} entregas tardías")
    elif tard == 1:
        puntaje += 10
        motivos.append("R2 · 1 entrega tardía")
    caida = resumen.get("caida_ultima") or 0
    if caida >= 8:
        puntaje += 35
        motivos.append(f"R3 · la última nota cayó {float(caida):.1f} pts bajo su promedio previo")
    elif caida >= 4:
        puntaje += 15
        motivos.append(f"R3 · la última nota cayó {float(caida):.1f} pts bajo su promedio previo")
    nivel = "ROJO" if puntaje >= 50 else "AMBAR" if puntaje >= 25 else "VERDE"
    return puntaje, nivel, motivos


def resumen_de(entregas):  # misma lógica que ms-evaluaciones.resumen_alumno
    cal = sorted((e for e in entregas if e["estado"] == "CALIFICADA"), key=lambda e: e["calificado_en"])
    n = len(cal)
    prom = round(sum(float(e["nota"]) for e in cal) / n, 2) if n else None
    caida = 0.0
    if n >= 2:
        previo = sum(float(e["nota"]) for e in cal[:-1]) / (n - 1)
        caida = round(max(0.0, previo - float(cal[-1]["nota"])), 2)
    return {"n_entregas": len(entregas), "n_notas": n, "promedio": prom,
            "n_tardias": sum(1 for e in entregas if e["es_tardia"]), "caida_ultima": caida}


# --------------------------------------------------------------------------- generación
def generar_tenant(tid, n, ahora):
    rng = random.Random(f"{SEED}-{tid}")
    dom = TENANTS[tid]["dominio"]
    n_cursos = 60 if n >= 3000 else max(6, n // 50)
    n_docentes = 100 if n >= 3000 else max(6, n // 20)
    out = {k: [] for k in MS_DE_TABLA}

    # ---- usuarios (ms-auth)
    docentes = {}
    alumnos = {}
    for d in range(1, n_docentes + 1):
        nom, ape = ("Carlos", "Salas") if d == 1 else (rng.choice(NOMBRES), rng.choice(APELLIDOS))
        email = f"profe@{dom}" if d == 1 else f"{slug(nom)}.{slug(ape)}.d{d}@{dom}"
        docentes[f"D{d:03d}"] = (f"{nom} {ape}", email, "docente")
    for i in range(1, n + 1):
        nom, ape = CAST[i - 1] if i <= len(CAST) else (rng.choice(NOMBRES), rng.choice(APELLIDOS))
        email = f"{slug(nom)}.{slug(ape)}@{dom}" if i <= len(CAST) else f"{slug(nom)}.{slug(ape)}{i}@{dom}"
        alumnos[f"A{i:05d}"] = (f"{nom} {ape}", email, "alumno")
    admins = {f"X{a:02d}": ("Administrador Demo" if a == 1 else f"Admin {a}",
                            f"admin@{dom}" if a == 1 else f"admin{a}@{dom}", "admin") for a in range(1, 11)}
    for uid, (nombre, email, rol) in [*admins.items(), *docentes.items(), *alumnos.items()]:
        salt = hashlib.sha256(f"{tid}-{uid}".encode()).hexdigest()[:32]
        out["sp_usuarios"].append({
            "tenant_id": tid, "user_id": uid, "email": email, "nombre": nombre, "rol": rol, "salt": salt,
            "pwd_hash": hash_password(PASSWORD_DEMO, salt), "estado": "ACTIVO",
            "creado_en": iso(ahora - timedelta(days=rng.randint(30, 400)))})

    # ---- cursos, módulos, tareas
    doc_ids = list(docentes)
    cursos, tareas = {}, {}
    for c in range(1, n_cursos + 1):
        cid = f"C{c:04d}"
        codigo, nombre = CURSOS_BASE[(c - 1) % len(CURSOS_BASE)]
        if c > len(CURSOS_BASE):
            codigo, nombre = codigo + "B", nombre + " (Sec. B)"
        did = "D001" if c <= 3 else doc_ids[(c * 7) % len(doc_ids)]
        cursos[cid] = {"codigo": codigo, "nombre": nombre, "docente_id": did}
        out["sp_cursos"].append({
            "tenant_id": tid, "curso_id": cid, "codigo": codigo, "nombre": nombre,
            "descripcion": f"Curso de {nombre} del ciclo 2026-2.", "docente_id": did,
            "docente_nombre": docentes[did][0], "ciclo": "2026-2", "creditos": 3 + (c % 2),
            "estado": "ACTIVO", "color": COLORES[c % len(COLORES)], "creado_en": iso(ahora - timedelta(days=120))})
        for m, titulo in enumerate(MODULOS, start=1):
            out["sp_modulos"].append({
                "tenant_id": tid, "curso_modulo": f"{cid}#M{m:02d}", "curso_id": cid, "modulo_id": f"M{m:02d}",
                "numero": m, "titulo": titulo, "descripcion": f"{titulo} de {nombre}.", "publicado": m <= 6,
                "materiales": [], "fecha_publicacion": iso(ahora - timedelta(days=70 - 7 * m))})
        for k, titulo in enumerate(TAREAS, start=1):
            tarea_id = f"T{(c - 1) * 4 + k:04d}"
            jitter = 0 if c == 1 else rng.randint(-2, 2)
            due = ahora + timedelta(days=DIAS_TAREA[k - 1] + jitter)
            tareas[(cid, k)] = {"tarea_id": tarea_id, "due": due}
            out["sp_tareas"].append({
                "tenant_id": tid, "curso_tarea": f"{cid}#{tarea_id}", "curso_id": cid, "tarea_id": tarea_id,
                "titulo": titulo, "descripcion": f"{titulo} de {nombre}.", "fecha_limite": iso(due),
                "puntaje_max": Decimal(20), "docente_id": did, "docente_nombre": docentes[did][0],
                "publicada": True, "creado_en": iso(due - timedelta(days=21))})

    # ---- matrículas (ms-cursos)
    for i in range(1, n + 1):
        aid = f"A{i:05d}"
        cids = [f"C{((i - 1) % n_cursos) + 1:04d}"]
        if i <= len(CAST):
            cids = ["C0001", "C0002", "C0003"]
        for cid in cids:
            out["sp_matriculas"].append({
                "tenant_id": tid, "curso_alumno": f"{cid}#{aid}", "alumno_curso": f"{aid}#{cid}",
                "curso_id": cid, "alumno_id": aid, "alumno_nombre": alumnos[aid][0], "estado": "ACTIVA",
                "avance_pct": rng.randint(5, 100), "matriculado_en": iso(ahora - timedelta(days=rng.randint(60, 100)))})

    # ---- entregas (ms-evaluaciones)
    por_alumno = {}

    def entrega(aid, cid, k, estado, nota, tardia, dias_antes=3):
        tarea = tareas[(cid, k)]
        due = tarea["due"]
        ent = due + timedelta(days=rng.randint(1, 3)) if tardia else due - timedelta(days=dias_antes)
        cal = min(ent + timedelta(days=rng.randint(2, 4)), ahora - timedelta(hours=2))
        e = {"tenant_id": tid, "tarea_alumno": f"{tarea['tarea_id']}#{aid}", "alumno_tarea": f"{aid}#{tarea['tarea_id']}",
             "tarea_id": tarea["tarea_id"], "curso_id": cid, "alumno_id": aid, "alumno_nombre": alumnos[aid][0],
             "titulo_tarea": TAREAS[k - 1], "docente_id": cursos[cid]["docente_id"], "estado": estado,
             "texto": "Entrega ficticia generada por seed.py", "archivo_nombre": "", "entregado_en": iso(ent),
             "es_tardia": tardia}
        if estado == "CALIFICADA":
            e.update({"nota": D(nota), "retroalimentacion": "Buen trabajo." if nota >= 13 else "Revisar conceptos.",
                      "calificado_por": cursos[cid]["docente_id"], "calificado_en": iso(cal)})
        out["sp_entregas"].append(e)
        por_alumno.setdefault(aid, []).append(e)

    # elenco de la demo (curso C0001): estados controlados
    guion = {
        "A00001": [(1, "CALIFICADA", 17, False), (2, "CALIFICADA", 16, False), (3, "ENTREGADA", None, False)],
        "A00002": [(1, "CALIFICADA", 9, True), (2, "CALIFICADA", 8, True)],
        "A00003": [(1, "CALIFICADA", 12.5, True), (2, "CALIFICADA", 11, False)],
        "A00004": [(1, "CALIFICADA", 15, False), (2, "CALIFICADA", 14, False), (3, "CALIFICADA", 15, False)],
        "A00005": [(1, "CALIFICADA", 18, False), (2, "CALIFICADA", 19, False), (3, "ENTREGADA", None, False)],
    }
    for aid, pasos in guion.items():
        if aid in alumnos:
            for k, estado, nota, tardia in pasos:
                entrega(aid, "C0001", k, estado, nota, tardia, dias_antes=2 + k)
    for i in range(len(CAST) + 1, n + 1):
        aid, cid = f"A{i:05d}", f"C{((i - 1) % n_cursos) + 1:04d}"
        r = rng.random()
        if r < 0.72:
            nota, tardia = min(20, max(13, rng.gauss(15.5, 1.8))), rng.random() < 0.10
        elif r < 0.92:
            nota, tardia = ((rng.uniform(6, 10.4), False) if rng.random() < 0.5 else (rng.uniform(10.5, 12.9), True))
        else:
            nota, tardia = rng.uniform(2, 10.4), True
        nota = math.floor(nota * 2) / 2
        estado = "ENTREGADA" if rng.random() < 0.06 else "CALIFICADA"
        entrega(aid, cid, rng.randint(1, 3), estado, nota, tardia)

    # ---- indicadores / semáforo (ms-analitica): misma regla que el sistema en vivo
    niveles = {"VERDE": 0, "AMBAR": 0, "ROJO": 0}
    for aid, (nombre, _, _) in alumnos.items():
        res = resumen_de(por_alumno.get(aid, []))
        puntaje, nivel, motivos = calcular_riesgo(res)
        niveles[nivel] += 1
        out["sp_indicadores"].append({
            "tenant_id": tid, "alumno_id": aid, "alumno_nombre": nombre, "promedio": D(res["promedio"]),
            "n_notas": res["n_notas"], "n_tardias": res["n_tardias"], "caida_ultima": D(res["caida_ultima"]),
            "n_entregas": res["n_entregas"], "puntaje": puntaje, "nivel": nivel, "motivos": motivos,
            "tenant_nivel": f"{tid}#{nivel}", "riesgo_orden": f"{puntaje:03d}#{aid}",
            "actualizado_en": iso(ahora - timedelta(days=1, minutes=rng.randint(0, 600))), "ultimo_evento": "seed"})

    # ---- notificaciones (ms-notificaciones): derivadas de los hechos anteriores
    notifs = []

    def notif(user, tipo, titulo, texto, evento, ts):
        eid = f"seed-{len(notifs):06d}"
        notifs.append({
            "tenant_id": tid, "usuario_ts": f"{user}#{iso(ts)}#{eid}", "user_id": user, "tipo": tipo,
            "titulo": titulo, "mensaje": texto, "leida": rng.random() < 0.7, "evento": evento,
            "event_id": eid, "origen": "seed", "creado_en": iso(ts)})

    for e in sorted(out["sp_entregas"], key=lambda e: e["alumno_id"]):  # elenco primero (A00001..)
        if e["estado"] == "CALIFICADA":
            notif(e["alumno_id"], "NOTA", f"Nueva nota en {e['titulo_tarea']}", f"Obtuviste {e['nota']} / 20.",
                  "NotaPublicada", datetime.strptime(e["calificado_en"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
    docente_de = {e["alumno_id"]: e["docente_id"] for e in out["sp_entregas"]}
    for ind in out["sp_indicadores"]:
        if ind["nivel"] == "ROJO":
            ts = ahora - timedelta(days=rng.randint(1, 6), minutes=rng.randint(0, 900))
            notif(docente_de.get(ind["alumno_id"], "D001"), "RIESGO", "Alumno en riesgo académico",
                  f"{ind['alumno_nombre']} pasó a ROJO (puntaje {ind['puntaje']}): " + "; ".join(ind["motivos"]),
                  "AlumnoEnRiesgo", ts)
    while len(notifs) < n:
        aid = f"A{rng.randint(1, n):05d}"
        notif(aid, "MODULO", "Nuevo módulo publicado", "Se publicó un módulo en tu curso.", "ModuloPublicado",
              ahora - timedelta(days=rng.randint(1, 40), minutes=rng.randint(0, 1400)))
    out["sp_notificaciones"] = notifs[:n]

    # ---- tarjetas de práctica (ms-practica, opcional)
    por_curso = math.ceil(n / n_cursos)
    idx = 0
    for cid, c in cursos.items():
        for _ in range(por_curso):
            if idx >= n:
                break
            idx += 1
            q, ok, malas = BANCO_QA[rng.randrange(len(BANCO_QA))]
            opciones = [ok, *malas]
            rng.shuffle(opciones)
            out["sp_tarjetas"].append({
                "tenant_id": tid, "curso_tarjeta": f"{cid}#K{idx:05d}", "tarjeta_id": f"K{idx:05d}",
                "curso_id": cid, "modulo_id": f"M{rng.randint(1, 6):02d}", "tema": MODULOS[rng.randint(0, 5)],
                "pregunta": f"[{c['codigo']}] {q}", "opciones": opciones, "correcta": opciones.index(ok),
                "dificultad": rng.randint(1, 3)})
    return out, niveles



# ----------------------------------------------------------------------- RDS (ms-cursos y ms-evaluaciones)
# tabla lógica -> (servicio, tabla SQL, columnas). El orden importa: primero los "padres" (claves foráneas).
SQL_TABLAS = {
    "sp_cursos": ("cursos", "cursos", ["curso_id", "codigo", "nombre", "descripcion", "docente_id", "docente_nombre",
                                       "ciclo", "creditos", "estado", "color", "creado_en"]),
    "sp_modulos": ("cursos", "modulos", ["curso_id", "modulo_id", "numero", "titulo", "descripcion", "publicado",
                                         "materiales", "fecha_publicacion"]),
    "sp_matriculas": ("cursos", "matriculas", ["curso_id", "alumno_id", "alumno_nombre", "estado", "avance_pct",
                                               "matriculado_en"]),
    "sp_tareas": ("evaluaciones", "tareas", ["tarea_id", "curso_id", "titulo", "descripcion", "fecha_limite",
                                             "puntaje_max", "docente_id", "docente_nombre", "publicada", "creado_en"]),
    "sp_entregas": ("evaluaciones", "entregas", ["tarea_id", "alumno_id", "curso_id", "alumno_nombre", "titulo_tarea",
                                                 "docente_id", "estado", "texto", "archivo_nombre", "entregado_en",
                                                 "es_tardia", "nota", "retroalimentacion", "calificado_por",
                                                 "calificado_en"]),
}


def _valor_sql(col, v):
    if col == "materiales":
        return json.dumps(v)
    if isinstance(v, bool):
        return int(v)
    return v


def cargar_sql(tenant, datos, lote=500):
    """Inserta las tablas relacionales del tenant en su ESQUEMA (cursos_<t>, evaluaciones_<t>).
    INSERT IGNORE: repetir el seed no duplica ni falla. Requiere DB_HOST, DB_USER y DB_PASSWORD."""
    import sqldb
    cur = sqldb.conexion().cursor()
    for tabla, (servicio, sql_tabla, cols) in SQL_TABLAS.items():
        if tabla not in datos:
            continue
        esq = sqldb.asegurar(servicio, tenant)
        filas = [[_valor_sql(c, it.get(c)) for c in cols] for it in datos[tabla]]
        sentencia = f"INSERT IGNORE INTO {esq}.{sql_tabla} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
        for i in range(0, len(filas), lote):
            cur.executemany(sentencia, filas[i:i + lote])
        print(f"\r  {esq + '.' + sql_tabla:<32} {len(filas):>7} filas", flush=True)

# -------------------------------------------------------------------------------- carga
_local = threading.local()


def _tabla(nombre, region):
    import boto3
    if not hasattr(_local, "res"):
        _local.res = boto3.session.Session(region_name=region).resource("dynamodb")
    return _local.res.Table(nombre)


def escribir(nombre, items, region, workers):
    trozos = [items[i:i + 250] for i in range(0, len(items), 250)]

    def lote(trozo):
        with _tabla(nombre, region).batch_writer() as bw:
            for it in trozo:
                bw.put_item(Item=it)
        return len(trozo)

    hecho = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for n in ex.map(lote, trozos):
            hecho += n
            print(f"\r  {nombre:<18} {hecho:>7}/{len(items)}", end="", flush=True)
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenants", default="UTEC,NORTE,ANDINO")
    ap.add_argument("--per-tenant", type=int, default=10_000)
    ap.add_argument("--only", default="", help="auth,cursos,evaluaciones,analitica,notificaciones,practica")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tenants = [t.strip().upper() for t in a.tenants.split(",") if t.strip()]
    solo = {s.strip() for s in a.only.split(",") if s.strip()}
    ahora = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)  # fijo por día: repetir el seed el mismo día no duplica filas

    acumulado = {k: [] for k in MS_DE_TABLA}
    print(f"Generando datos ({a.per_tenant} alumnos por tenant, semilla {SEED})...")
    for tid in tenants:
        datos, niveles = generar_tenant(tid, a.per_tenant, ahora)
        for k, v in datos.items():
            acumulado[k] += v
        print(f"  {tid:<7} semáforo: {niveles}")

    print("\nConteos por tabla y tenant:")
    for tabla, items in acumulado.items():
        if solo and MS_DE_TABLA[tabla] not in solo:
            continue
        por_t = {t: sum(1 for i in items if i["tenant_id"] == t) for t in tenants}
        print(f"  {tabla:<18} total {len(items):>7}  " + "  ".join(f"{t}={c}" for t, c in por_t.items()))
    if a.dry_run:
        print("\n(dry-run: no se escribió nada en AWS)")
        return
    sql_activas = [t for t in SQL_TABLAS if not solo or MS_DE_TABLA[t] in solo]
    if sql_activas:
        print("\nEscribiendo en RDS MySQL (esquema por tenant)...  [DB_HOST, DB_USER, DB_PASSWORD]")
        for tid in tenants:
            cargar_sql(tid, {t: [i for i in acumulado[t] if i["tenant_id"] == tid] for t in sql_activas})
    print("\nEscribiendo en DynamoDB...")
    for tabla, items in acumulado.items():
        if (solo and MS_DE_TABLA[tabla] not in solo) or tabla in SQL_TABLAS:
            continue
        escribir(tabla, items, a.region, a.workers)
    print("\nListo. Verifica con:  python verify_counts.py")


if __name__ == "__main__":
    main()
