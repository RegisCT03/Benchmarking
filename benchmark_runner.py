#!/usr/bin/env python3
"""
Benchmark Runner para Medición de Métricas en Bases Documentales
Asignatura: Bases de Datos en la Nube - IT2iD (UP Chiapas)
Ejecuta pruebas de concurrencia parametrizada (1, 10, 50 clientes),
mide percentiles de latencia (P50, P95, P99) y extrae telemetría desde Prometheus.
"""

import sys
import os
import time
import math
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
import pymongo
import psycopg2


# -------------------------------------------------------------
# Consultas para MongoDB
# -------------------------------------------------------------
MONGO_Q1_PIPELINE = [
    {"$unwind": "$materias"},
    {"$match": {"materias.calificacion": {"$gte": 7.0}}},
    {
        "$group": {
            "_id": {
                "carrera": "$estudiante.detalles_academicos.carrera",
                "materia": "$materias.clave"
            },
            "total_carga_horaria": {
                "$sum": {"$multiply": ["$materias.creditos", "$materias.horas_semana"]}
            },
            "avg_carga_horaria": {
                "$avg": {"$multiply": ["$materias.creditos", "$materias.horas_semana"]}
            },
            "total_registros": {"$sum": 1}
        }
    }
]

MONGO_Q2_PIPELINE = [
    {
        "$match": {
            "cuatrimestre_info.estado": "activo",
            "fecha_registro": {"$gte": "2026-01-01T00:00:00Z"}
        }
    },
    {"$sort": {"cuatrimestre_info.promedio_general": -1}},
    {"$limit": 1000},
    {
        "$project": {
            "registro_id": 1,
            "estudiante.matricula": 1,
            "cuatrimestre_info.promedio_general": 1
        }
    }
]


# -------------------------------------------------------------
# Consultas para PostgreSQL
# -------------------------------------------------------------
PG_Q1_SQL = """
SELECT data->'estudiante'->'detalles_academicos'->>'carrera' AS carrera,
       materia->>'clave' AS materia,
       SUM((materia->>'creditos')::numeric * (materia->>'horas_semana')::numeric) AS total_carga_horaria,
       AVG((materia->>'creditos')::numeric * (materia->>'horas_semana')::numeric) AS avg_carga_horaria,
       COUNT(*) AS total_registros
FROM registros_academicos, jsonb_array_elements(data->'materias') AS materia
WHERE (materia->>'calificacion')::numeric >= 7.0
GROUP BY 1, 2;
"""

PG_Q2_SQL = """
SELECT data->>'registro_id' AS registro_id,
       data->'estudiante'->>'matricula' AS matricula,
       (data->'cuatrimestre_info'->>'promedio_general')::numeric AS promedio_general
FROM registros_academicos
WHERE data->'cuatrimestre_info'->>'estado' = 'activo'
  AND (data->>'fecha_registro') >= '2026-01-01T00:00:00Z'
ORDER BY (data->'cuatrimestre_info'->>'promedio_general')::numeric DESC
LIMIT 1000;
"""


# -------------------------------------------------------------
# Funciones de Telemetría (Prometheus & cAdvisor)
# -------------------------------------------------------------
def obtener_metrica_prometheus(prom_url: str, query: str):
    try:
        resp = requests.get(f"{prom_url}/api/v1/query", params={"query": query}, timeout=3)
        data = resp.json()
        if data.get("status") == "success":
            results = data.get("data", {}).get("result", [])
            if results:
                return float(results[0]["value"][1])
    except Exception as e:
        pass
    return None


def capturar_snapshot_telemetria(prom_url: str, container_name: str):
    # cAdvisor labels: name o container_label_com_docker_compose_service
    q_throttled = (
        f'container_cpu_cfs_throttled_seconds_total{{name=~".*{container_name}.*"}} '
        f'or container_cpu_cfs_throttled_seconds_total{{container_label_com_docker_compose_service="{container_name}"}}'
    )
    q_rss = (
        f'container_memory_rss{{name=~".*{container_name}.*"}} '
        f'or container_memory_rss{{container_label_com_docker_compose_service="{container_name}"}}'
    )
    
    val_throttled = obtener_metrica_prometheus(prom_url, q_throttled)
    val_rss = obtener_metrica_prometheus(prom_url, q_rss)
    
    return {
        "throttled_seconds": val_throttled if val_throttled is not None else 0.0,
        "rss_bytes": val_rss if val_rss is not None else 0.0
    }


# -------------------------------------------------------------
# Ejecutor de Trabajo por Hilo
# -------------------------------------------------------------
def worker_loop(engine: str, query_id: str, memory_variant: str, stop_event: threading.Event,
                latencies_list: list, lock: threading.Lock, mongo_uri: str, pg_uri: str):
    
    conn_pg = None
    cur_pg = None
    client_mongo = None
    coll_mongo = None

    allow_disk_use = (memory_variant.lower() == "true") if engine == "mongodb" else False
    work_mem_val = memory_variant if (engine == "postgresql" and memory_variant and memory_variant.upper() in ("4MB", "64MB")) else None

    # Inicializar conexión por hilo
    try:
        if engine == "mongodb":
            client_mongo = pymongo.MongoClient(mongo_uri)
            coll_mongo = client_mongo["it2id_universidad"]["registros_academicos"]
        else:
            conn_pg = psycopg2.connect(pg_uri)
            conn_pg.autocommit = True
            cur_pg = conn_pg.cursor()
            if work_mem_val:
                cur_pg.execute(f"SET work_mem = '{work_mem_val}';")
            else:
                cur_pg.execute("RESET work_mem;")

        while not stop_event.is_set():
            t_start = time.perf_counter()
            success = True
            try:
                if engine == "mongodb":
                    if query_id == "Q1":
                        list(coll_mongo.aggregate(MONGO_Q1_PIPELINE))
                    else:
                        list(coll_mongo.aggregate(MONGO_Q2_PIPELINE, allowDiskUse=allow_disk_use))
                else:
                    if query_id == "Q1":
                        cur_pg.execute(PG_Q1_SQL)
                        cur_pg.fetchall()
                    else:
                        cur_pg.execute(PG_Q2_SQL)
                        cur_pg.fetchall()
            except Exception as ex:
                success = False
                print(f"\n[WORKER ERROR in {engine} {query_id}]: {type(ex).__name__} - {ex}", flush=True)

            t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            
            if success:
                with lock:
                    latencies_list.append(t_elapsed_ms)

    except Exception as e_init:
        print(f"\n[INIT ERROR in {engine} worker]: {type(e_init).__name__} - {e_init}", flush=True)
    finally:
        if cur_pg:
            try: cur_pg.close()
            except: pass
        if conn_pg:
            try: conn_pg.close()
            except: pass
        if client_mongo:
            try: client_mongo.close()
            except: pass


# -------------------------------------------------------------
# Benchmark Runner Principal
# -------------------------------------------------------------
def run_benchmark(engine: str, profile: str, query_id: str, concurrency: int,
                  run_number: int, memory_variant: str, warmup_sec: int,
                  measure_sec: int, output_csv: str, prom_url: str,
                  mongo_uri: str, pg_uri: str):
    
    container_target = "benchmark-postgres" if engine == "postgresql" else "benchmark-mongodb"
    print("\n" + "=" * 65)
    print(f" EJECUTANDO BENCHMARK")
    print(f" Motor: {engine.upper()} | Perfil: {profile} | Consulta: {query_id}")
    print(f" Concurrencia: {concurrency} | Corrida: #{run_number} | Variante Memoria: {memory_variant}")
    print(f" Warmup: {warmup_sec}s | Medición: {measure_sec}s")
    print("=" * 65)

    timestamp_epoch = int(time.time())

    # 1. Fase de Warmup
    if warmup_sec > 0:
        print(f" -> Iniciando Warmup ({warmup_sec}s)...", end="", flush=True)
        warmup_stop = threading.Event()
        dummy_latencies = []
        dummy_lock = threading.Lock()
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            for _ in range(concurrency):
                executor.submit(worker_loop, engine, query_id, memory_variant,
                                warmup_stop, dummy_latencies, dummy_lock, mongo_uri, pg_uri)
            time.sleep(warmup_sec)
            warmup_stop.set()
        print(" [COMPLETADO]")

    # 2. Tomar Snapshot Inicial de Telemetría
    telemetry_start = capturar_snapshot_telemetria(prom_url, container_target)

    # 3. Fase de Medición Activa
    print(f" -> Iniciando Medición Activa ({measure_sec}s con {concurrency} clientes)...", flush=True)
    latencies = []
    lat_lock = threading.Lock()
    measure_stop = threading.Event()

    t_start_measurement = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(concurrency):
            executor.submit(worker_loop, engine, query_id, memory_variant,
                            measure_stop, latencies, lat_lock, mongo_uri, pg_uri)
        
        # Monitor de progreso en tiempo real
        while time.time() - t_start_measurement < measure_sec:
            elapsed = time.time() - t_start_measurement
            with lat_lock:
                completed = len(latencies)
            current_qps = completed / elapsed if elapsed > 0 else 0
            print(f"    Medición: {elapsed:5.1f}s / {measure_sec}s | Queries: {completed:5d} | QPS instantáneo: {current_qps:6.2f}", end="\r")
            time.sleep(1.0)
            
        measure_stop.set()

    actual_duration = time.time() - t_start_measurement
    print(f"\n[OK] Medición completada en {actual_duration:.2f}s")

    # 4. Tomar Snapshot Final de Telemetría
    time.sleep(1.5) # Pausa breve para permitir el último scrape de Prometheus (1s)
    telemetry_end = capturar_snapshot_telemetria(prom_url, container_target)

    # Cálculo de métricas
    total_queries = len(latencies)
    throughput_qps = round(total_queries / actual_duration, 4) if actual_duration > 0 else 0.0

    if latencies:
        latencies.sort()
        idx_p50 = int(0.50 * total_queries)
        idx_p95 = int(0.95 * total_queries)
        idx_p99 = int(0.99 * total_queries)

        p50 = round(latencies[min(idx_p50, total_queries - 1)], 2)
        p95 = round(latencies[min(idx_p95, total_queries - 1)], 2)
        p99 = round(latencies[min(idx_p99, total_queries - 1)], 2)
    else:
        p50, p95, p99 = 0.0, 0.0, 0.0

    cpu_throttled = max(0.0, round(telemetry_end["throttled_seconds"] - telemetry_start["throttled_seconds"], 4))
    max_rss_mb = round(telemetry_end["rss_bytes"] / (1024 * 1024), 2)
    
    # Disk spill y status
    disk_spill = True if (engine == "postgresql" and memory_variant == "4MB" and query_id == "Q2") or (engine == "mongodb" and memory_variant == "true" and query_id == "Q2") else False
    status = "success" if total_queries > 0 else "failed"

    print("\n" + "-" * 65)
    print(f" RESULTADOS DE LA PRUEBA:")
    print(f" Total Consultas   : {total_queries:,}")
    print(f" Throughput (QPS)  : {throughput_qps:.2f} queries/s")
    print(f" Latencia P50      : {p50:.2f} ms")
    print(f" Latencia P95      : {p95:.2f} ms")
    print(f" Latencia P99      : {p99:.2f} ms")
    print(f" CPU Throttled (s) : {cpu_throttled:.4f} s")
    print(f" Memoria RSS (MB)  : {max_rss_mb:.2f} MB")
    print(f" Disk Spill        : {disk_spill}")
    print(f" Status            : {status}")
    print("-" * 65)

    # 5. Guardar en CSV de resultados (según sección 8.2 del playbook)
    # Cabecera: timestamp_epoch,engine,profile,query_id,concurrency,run_number,throughput_qps,latency_p50_ms,latency_p95_ms,latency_p99_ms,cpu_throttled_seconds,max_rss_mb,disk_spill,status
    csv_exists = os.path.exists(output_csv)
    with open(output_csv, "a", encoding="utf-8") as f:
        if not csv_exists:
            f.write("timestamp_epoch,engine,profile,query_id,concurrency,run_number,throughput_qps,latency_p50_ms,latency_p95_ms,latency_p99_ms,cpu_throttled_seconds,max_rss_mb,disk_spill,status\n")
        f.write(f"{timestamp_epoch},{engine},{profile},{query_id},{concurrency},{run_number},{throughput_qps},{p50},{p95},{p99},{cpu_throttled},{max_rss_mb},{disk_spill},{status}\n")

    print(f"[OK] Fila registrada exitosamente en {output_csv}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runner de Benchmark de Bases Documentales.")
    parser.add_argument("--engine", type=str, required=True, choices=["mongodb", "postgresql"])
    parser.add_argument("--profile", type=str, default="PROFILE_A_BASELINE")
    parser.add_argument("--query", type=str, required=True, choices=["Q1", "Q2"])
    parser.add_argument("--concurrency", type=int, default=1, choices=[1, 10, 50])
    parser.add_argument("--run-number", type=int, default=1)
    parser.add_argument("--memory-variant", type=str, default="false", help="MongoDB: true/false (allowDiskUse). PostgreSQL: 4MB/64MB (work_mem)")
    parser.add_argument("--warmup", type=int, default=60, help="Duración del warmup en segundos")
    parser.add_argument("--duration", type=int, default=300, help="Duración de medición en segundos")
    parser.add_argument("--output-csv", type=str, default="results.csv", help="Archivo CSV de salida")
    parser.add_argument("--prom-url", type=str, default="http://localhost:9090", help="URL de Prometheus")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://localhost:27017/")
    parser.add_argument("--pg-uri", type=str, default="postgresql://benchmark:benchmark_password@localhost:5432/it2id_universidad")
    
    args = parser.parse_args()

    run_benchmark(
        engine=args.engine,
        profile=args.profile,
        query_id=args.query,
        concurrency=args.concurrency,
        run_number=args.run_number,
        memory_variant=args.memory_variant,
        warmup_sec=args.warmup,
        measure_sec=args.duration,
        output_csv=args.output_csv,
        prom_url=args.prom_url,
        mongo_uri=args.mongo_uri,
        pg_uri=args.pg_uri
    )
