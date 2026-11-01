#!/usr/bin/env python3
"""
Script de Carga Masiva e Indexación para MongoDB y PostgreSQL
Asignatura: Bases de Datos en la Nube - IT2iD (UP Chiapas)
Carga el archivo data/dataset_500k.jsonl en ambas bases de datos.
"""

import sys
import os
import io
import time
import json
import argparse
from datetime import datetime

import pymongo
import psycopg2
from psycopg2 import extras


def cargar_mongodb(dataset_path: str, mongo_uri: str, db_name: str, coll_name: str, batch_size: int = 10000):
    print("\n" + "=" * 65)
    print(" INICIANDO CARGA EN MONGODB (WiredTiger)")
    print("=" * 65)
    
    start_time = time.time()
    client = pymongo.MongoClient(mongo_uri)
    db = client[db_name]
    coll = db[coll_name]

    # Limpiar colección si ya tiene datos
    print(f" -> Conectado a MongoDB: {mongo_uri}")
    print(f" -> Colección objetivo : {db_name}.{coll_name}")
    coll.drop()
    print(" -> Colección anterior eliminada (drop)")

    print(f" -> Leyendo e insertando por lotes de {batch_size:,}...")
    total_inserted = 0
    batch = []

    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            batch.append(json.loads(line))
            
            if len(batch) >= batch_size:
                coll.insert_many(batch, ordered=False)
                total_inserted += len(batch)
                batch.clear()
                elapsed = time.time() - start_time
                print(f"    Insertados: {total_inserted:7,d} docs | "
                      f"Velocidad: {total_inserted / elapsed:7.0f} doc/s | "
                      f"Transcurrido: {elapsed:5.1f}s", end="\r")

        if batch:
            coll.insert_many(batch, ordered=False)
            total_inserted += len(batch)

    insert_time = time.time() - start_time
    print(f"\n[OK] Inserción de datos finalizada: {total_inserted:,} documentos en {insert_time:.2f} s")

    # Creación de índices según sección 2 del playbook
    print(" -> Creando índices en MongoDB...")
    idx_start = time.time()
    coll.create_index([("fecha_registro", 1)])
    coll.create_index([("registro_id", 1)])
    idx_time = time.time() - idx_start
    print(f"[OK] Índices creados en {idx_time:.2f} s: ['fecha_registro', 'registro_id']")
    
    final_count = coll.count_documents({})
    print(f" Total de documentos verificados en MongoDB: {final_count:,}")
    client.close()


def cargar_postgresql(dataset_path: str, pg_uri: str, table_name: str, batch_size: int = 10000):
    print("\n" + "=" * 65)
    print(" INICIANDO CARGA EN POSTGRESQL (JSONB)")
    print("=" * 65)

    start_time = time.time()
    conn = psycopg2.connect(pg_uri)
    conn.autocommit = True
    cur = conn.cursor()

    print(f" -> Conectado a PostgreSQL: {pg_uri.split('@')[-1]}")
    
    # 1. Crear tabla limpia
    cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
    cur.execute(f"""
        CREATE TABLE {table_name} (
            id UUID PRIMARY KEY,
            data JSONB NOT NULL
        );
    """)
    print(f" -> Tabla {table_name} recreada exitosamente.")

    # 2. Carga masiva rápida vía COPY con archivo intermedio en memoria
    print(f" -> Transfiriendo registros por streaming COPY...")
    copy_start = time.time()
    total_inserted = 0
    buffer = io.StringIO()

    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            
            # Extraer registro_id sin parsear todo el JSON para máxima velocidad
            idx = line.find('"registro_id":"')
            if idx != -1:
                id_val = line[idx + 15 : idx + 51]
            else:
                id_val = json.loads(line)["registro_id"]

            # Formato COPY tab-delimited: id <TAB> data
            cleaned_json = line.strip().replace("\\", "\\\\").replace("\t", " ")
            buffer.write(f"{id_val}\t{cleaned_json}\n")
            total_inserted += 1

            if total_inserted % batch_size == 0:
                buffer.seek(0)
                cur.copy_from(buffer, table_name, columns=("id", "data"))
                buffer.seek(0)
                buffer.truncate(0)
                elapsed = time.time() - copy_start
                print(f"    Cargados: {total_inserted:7,d} filas | "
                      f"Velocidad: {total_inserted / elapsed:7.0f} filas/s | "
                      f"Transcurrido: {elapsed:5.1f}s", end="\r")

        if buffer.tell() > 0:
            buffer.seek(0)
            cur.copy_from(buffer, table_name, columns=("id", "data"))
            buffer.close()

    copy_time = time.time() - copy_start
    print(f"\n[OK] Carga COPY finalizada: {total_inserted:,} filas en {copy_time:.2f} s")

    # 3. Creación del índice B-Tree sobre timestamp (fecha_registro) del JSONB
    print(" -> Creando índice B-Tree sobre (data->>'fecha_registro')...")
    idx_start = time.time()
    cur.execute(f"""
        CREATE INDEX idx_registros_fecha 
        ON {table_name} USING BTREE (((data->>'fecha_registro')::timestamptz));
    """)
    idx_time = time.time() - idx_start
    print(f"[OK] Índice idx_registros_fecha creado en {idx_time:.2f} s")

    # 4. Estadísticas del planificador
    print(" -> Ejecutando VACUUM ANALYZE...")
    cur.execute(f"VACUUM ANALYZE {table_name};")

    cur.execute(f"SELECT COUNT(*) FROM {table_name};")
    final_count = cur.fetchone()[0]
    print(f" Total de filas verificadas en PostgreSQL: {final_count:,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga masiva para MongoDB y PostgreSQL.")
    parser.add_argument("--dataset", type=str, default="data/dataset_500k.jsonl", help="Ruta del archivo JSONL")
    parser.add_argument("--engine", type=str, choices=["all", "mongo", "postgres"], default="all", help="Motor a cargar")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://localhost:27017/", help="URI de MongoDB")
    parser.add_argument("--pg-uri", type=str, default="postgresql://benchmark:benchmark_password@localhost:5432/it2id_universidad", help="URI de PostgreSQL")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[ERROR] No se encontró el dataset en {args.dataset}")
        sys.exit(1)

    t0 = time.time()
    if args.engine in ("all", "mongo"):
        cargar_mongodb(args.dataset, args.mongo_uri, "it2id_universidad", "registros_academicos")
    
    if args.engine in ("all", "postgres"):
        cargar_postgresql(args.dataset, args.pg_uri, "registros_academicos")

    print("\n" + "=" * 65)
    print(f" PROCESO GLOBAL DE CARGA COMPLETADO EN {time.time() - t0:.2f} SEGUNDOS")
    print("=" * 65)
