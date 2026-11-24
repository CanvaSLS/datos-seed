#!/usr/bin/env python3
"""seed_s3.py · siembra materiales de ejemplo reales en S3 y los vincula en RDS (ms-cursos).

Usa exactamente el mismo formato JSON y prefijo S3 que `ms-cursos/handler.py` (`agregar_material`):
  key = tenant_id=<TENANT>/materiales/<curso_id>/<modulo_id>/<material_id>-<nombre>

Es 100 % idempotente: repetirlo actualiza los archivos en S3 y no duplica entradas en el JSON
`materiales` de `cursos_<tenant>.modulos` porque usa `material_id` deterministas.

Uso:
  python seed_s3.py --dry-run
  python seed_s3.py --stage dev          # detecta el bucket sp-storage-<accountId>-<stage> con STS
  python seed_s3.py --bucket sp-storage-313164171003-dev
"""
import argparse
import json
from datetime import datetime, timezone

TENANTS_NOMBRE = {
    "UTEC": "Universidad de Ingeniería y Tecnología",
    "NORTE": "Instituto del Norte",
    "ANDINO": "Colegio Andino",
}

# Materiales de muestra para el curso principal de la demo (C0001 - CS2032 Computación en la Nube)
MATERIALES_DEMO = [
    (
        "C0001", "M01", "seedm01a", "Silabo_CS2032.txt", "text/plain; charset=utf-8",
        "SILABO DEL CURSO CS2032 - COMPUTACION EN LA NUBE\n"
        "Institucion: {tenant_nombre} ({tenant})\n"
        "Ciclo: 2026-2\n\n"
        "Unidades:\n"
        "1. Introduccion a Serverless y AWS Lambda\n"
        "2. API Gateway, IAM y Seguridad Multi-Tenant\n"
        "3. Persistencia Poliglota (DynamoDB + RDS MySQL)\n"
        "4. Arquitectura Orientada a Eventos (SNS + SQS + DLQ)\n"
        "5. Almacenamiento Privado S3 con URLs Prefirmadas\n",
    ),
    (
        "C0001", "M01", "seedm01b", "Guia_Lab1_Serverless.md", "text/markdown; charset=utf-8",
        "# Guia de Laboratorio 1 - Serverless Multi-Tenant\n\n"
        "- **Institucion:** {tenant_nombre} (`{tenant}`)\n"
        "- **Objetivo:** Desplegar microservicios aislados por tenant en AWS Lambda.\n\n"
        "## Pasos\n"
        "1. Verificar el Lambda Authorizer (`ms-auth-dev-autorizar`).\n"
        "2. Comprobar el aislamiento de datos entre tenants.\n"
        "3. Validar la descarga de materiales mediante URL prefirmada S3.\n",
    ),
    (
        "C0001", "M02", "seedm02a", "Resumen_SNS_SQS_DLQ.txt", "text/plain; charset=utf-8",
        "RESUMEN DE ARQUITECTURA ORIENTADA A EVENTOS (EDA)\n"
        "Institucion: {tenant_nombre} ({tenant})\n\n"
        "Flujo principal:\n"
        "  ms-evaluaciones --(NotaPublicada)--> SNS sp-eventos-dev\n"
        "    |--(FilterPolicy)--> SQS sp-analitica-dev --> ms-analitica --(AlumnoEnRiesgo)--> SNS\n"
        "    |--(FilterPolicy)--> SQS sp-notificaciones-dev --> ms-notificaciones\n",
    ),
]


def _resolver_bucket(bucket_arg, stage, region):
    if bucket_arg:
        return bucket_arg
    import boto3
    account_id = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
    return f"sp-storage-{account_id}-{stage}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenants", default="UTEC,NORTE,ANDINO")
    ap.add_argument("--stage", default="dev")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--bucket", default="", help="Nombre del bucket S3 (por defecto: sp-storage-<accountId>-<stage>)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tenants = [t.strip().upper() for t in a.tenants.split(",") if t.strip()]
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if a.dry_run:
        bucket = a.bucket or f"sp-storage-<accountId>-{a.stage}"
        print(f"[dry-run] Bucket destino: {bucket}")
        for tid in tenants:
            for cid, mid, mat_id, nombre, ctype, _ in MATERIALES_DEMO:
                key = f"tenant_id={tid}/materiales/{cid}/{mid}/{mat_id}-{nombre}"
                print(f"  {tid:<7} {cid}/{mid} -> s3://{bucket}/{key} ({ctype})")
        print("\n(dry-run: no se escribió nada en S3 ni en RDS)")
        return

    import boto3
    import sqldb
    bucket = _resolver_bucket(a.bucket, a.stage, a.region)
    s3 = boto3.client("s3", region_name=a.region)
    cur = sqldb.conexion().cursor()

    print(f"Subiendo materiales demo a s3://{bucket} y actualizando RDS...")
    for tid in tenants:
        esq = sqldb.asegurar("cursos", tid)
        por_modulo = {}
        for cid, mid, mat_id, nombre, ctype, plantilla in MATERIALES_DEMO:
            key = f"tenant_id={tid}/materiales/{cid}/{mid}/{mat_id}-{nombre}"
            cuerpo = plantilla.format(tenant=tid, tenant_nombre=TENANTS_NOMBRE.get(tid, tid)).encode("utf-8")
            s3.put_object(Bucket=bucket, Key=key, Body=cuerpo, ContentType=ctype)
            por_modulo.setdefault((cid, mid), []).append({
                "material_id": mat_id,
                "nombre": nombre,
                "key": key,
                "content_type": ctype,
                "subido_en": ahora,
            })

        for (cid, mid), nuevos in por_modulo.items():
            cur.execute(f"SELECT materiales FROM {esq}.modulos WHERE curso_id = %s AND modulo_id = %s", (cid, mid))
            fila = cur.fetchone()
            if not fila:
                print(f"  [AVISO] {esq}.modulos no tiene {cid}/{mid} (ejecuta seed.py primero)")
                continue
            existentes = json.loads(fila.get("materiales") or "[]")
            por_id = {m["material_id"]: m for m in existentes}
            for item in nuevos:
                por_id[item["material_id"]] = item
            cur.execute(
                f"UPDATE {esq}.modulos SET materiales = %s, actualizado_en = %s WHERE curso_id = %s AND modulo_id = %s",
                (json.dumps(list(por_id.values()), ensure_ascii=False), ahora, cid, mid),
            )
            print(f"  {esq}.modulos {cid}/{mid} -> {len(nuevos)} materiales S3 registrados")

    print("\nListo. Materiales demo disponibles en S3 y RDS.")


if __name__ == "__main__":
    main()
