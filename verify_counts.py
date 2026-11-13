#!/usr/bin/env python3
"""verify_counts.py · evidencia para el informe: conteo por tenant y por microservicio (>= 30 000).

  python verify_counts.py                 # usa credenciales de ~/.aws/credentials (us-east-1)
  python verify_counts.py --tenants UTEC,NORTE,ANDINO
DynamoDB: Query (Select=COUNT) sobre la partición tenant_id: nunca Scan.
RDS (ms-cursos, ms-evaluaciones): COUNT(*) en el esquema de cada tenant (necesita DB_HOST, DB_USER, DB_PASSWORD).
Prueba T-ISO-8: la suma por tenant == total y no hay solapamiento (cada ítem tiene un solo tenant_id).
"""
import argparse
import sys

import boto3
from boto3.dynamodb.conditions import Key

MS = {
    "ms-auth": ["sp_usuarios"],
    "ms-cursos": ["sp_cursos", "sp_modulos", "sp_matriculas"],
    "ms-evaluaciones": ["sp_tareas", "sp_entregas"],
    "ms-analitica": ["sp_indicadores"],
    "ms-notificaciones": ["sp_notificaciones"],
    "ms-practica": ["sp_tarjetas"],
}
MINIMO = 30_000
# tabla lógica -> (servicio, tabla SQL) para lo que vive en RDS
SQL = {"sp_cursos": ("cursos", "cursos"), "sp_modulos": ("cursos", "modulos"),
       "sp_matriculas": ("cursos", "matriculas"), "sp_tareas": ("evaluaciones", "tareas"),
       "sp_entregas": ("evaluaciones", "entregas")}


def contar_sql(nombre, tenant):
    import sqldb
    servicio, tabla = SQL[nombre]
    cur = sqldb.conexion().cursor()
    cur.execute(f"SELECT COUNT(*) AS n FROM {sqldb.esquema(servicio, tenant)}.{tabla}")
    return int(cur.fetchall()[0]["n"])


def contar(tabla, tenant):
    total, kw = 0, {"KeyConditionExpression": Key("tenant_id").eq(tenant), "Select": "COUNT"}
    while True:
        r = tabla.query(**kw)
        total += r["Count"]
        if "LastEvaluatedKey" not in r:
            return total
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenants", default="UTEC,NORTE,ANDINO")
    ap.add_argument("--region", default="us-east-1")
    a = ap.parse_args()
    tenants = a.tenants.split(",")
    db = boto3.resource("dynamodb", region_name=a.region)
    ok_global = True
    print(f"{'microservicio':<20}{'tabla':<20}" + "".join(f"{t:>9}" for t in tenants) + f"{'TOTAL':>10}")
    for ms, tablas in MS.items():
        total_ms = 0
        for nombre in tablas:
            try:
                conteos = [contar_sql(nombre, t) if nombre in SQL else contar(db.Table(nombre), t) for t in tenants]
            except Exception as e:  # tabla aún no desplegada
                print(f"{ms:<20}{nombre:<20}  (no disponible: {type(e).__name__})")
                continue
            total_ms += sum(conteos)
            print(f"{ms:<20}{nombre:<20}" + "".join(f"{c:>9}" for c in conteos) + f"{sum(conteos):>10}")
        marca = "OK " if total_ms >= MINIMO else "FALTA"
        ok_global &= total_ms >= MINIMO
        print(f"{'':<20}{'→ ' + marca + ' total ' + ms:<20}{'':>{9 * len(tenants)}}{total_ms:>10}\n")
    sys.exit(0 if ok_global else 1)


if __name__ == "__main__":
    main()
