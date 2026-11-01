#!/usr/bin/env python3
"""
Orquestador de Automatización de la Matriz de Mediciones (108 Corridas)
Asignatura: Bases de Datos en la Nube - IT2iD (UP Chiapas)
Automatiza la ejecución del benchmark cruzando:
2 motores x 3 perfiles x 2 queries x 3 concurrencias x 3 repeticiones
Aplica flush de caché, warmup, medición y cooldown.
"""

import sys
import os
import time
import subprocess
import argparse

PERFILES = {
    "PROFILE_A_BASELINE": {"cpus": "4.0", "memory": "4096M"},
    "PROFILE_B_MEDIUM":   {"cpus": "2.0", "memory": "2048M"},
    "PROFILE_C_SEVERE":   {"cpus": "1.0", "memory": "1024M"},
}

MOTORES = ["mongodb", "postgresql"]
QUERIES = ["Q1", "Q2"]
CONCURRENCIAS = [1, 10, 50]


def flush_caches():
    """Ejecuta drop_caches en el kernel de Linux (WSL2/Docker o nativo)."""
    try:
        # En Windows con Docker Desktop / WSL2
        cmd = ["wsl", "-d", "docker-desktop", "-u", "root", "-e", "sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    try:
        # En entorno Linux nativo
        res = subprocess.run("sync; echo 3 | sudo tee /proc/sys/vm/drop_caches", shell=True, capture_output=True, timeout=10)
        return res.returncode == 0
    except Exception:
        return False


def aplicar_perfil_recursos(profile_name: str):
    """Reconfigura los límites cgroups v2 del contenedor mediante docker compose."""
    if profile_name not in PERFILES:
        raise ValueError(f"Perfil desconocido: {profile_name}")
    
    cfg = PERFILES[profile_name]
    print(f"\n>>> APLICANDO PERFIL: {profile_name} (CPUs: {cfg['cpus']}, RAM: {cfg['memory']}) <<<")

    # Actualizar archivo .env
    with open(".env", "w", encoding="utf-8") as f:
        f.write(f"PROFILE={profile_name}\n")
        f.write(f"DB_CPUS={cfg['cpus']}\n")
        f.write(f"DB_MEMORY={cfg['memory']}\n")
        f.write("POSTGRES_USER=benchmark\n")
        f.write("POSTGRES_PASSWORD=benchmark_password\n")
        f.write("POSTGRES_DB=it2id_universidad\n")
        f.write("MONGO_INITDB_DATABASE=it2id_universidad\n")

    # Aplicar cambios con docker compose
    cmd = ["docker", "compose", "up", "-d", "mongodb", "postgres"]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Esperar a que ambas bases de datos estén listas para aceptar conexiones
    print(" -> Esperando disponibilidad de motores...", end="", flush=True)
    for _ in range(15):
        time.sleep(1)
        mongo_ok = False
        pg_ok = False
        try:
            import pymongo
            c = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=1000)
            c.admin.command('ping')
            c.close()
            mongo_ok = True
        except:
            pass
        
        try:
            import psycopg2
            conn = psycopg2.connect("postgresql://benchmark:benchmark_password@localhost:5432/it2id_universidad", connect_timeout=1)
            conn.close()
            pg_ok = True
        except:
            pass

        if mongo_ok and pg_ok:
            print(" [LISTO]")
            return

    print(" [AVISO: Tiempo de espera agotado, continuando]")


def orquestar_matriz(engines: list, profiles: list, queries: list,
                     concurrencies: list, repetitions: int, warmup_sec: int,
                     measure_sec: int, cooldown_sec: int, output_csv: str):
    
    # Calcular total exacto de corridas considerando variantes de memoria
    total_corridas = 0
    for p in profiles:
        for e in engines:
            for q in queries:
                vars_count = 2 if q == "Q2" else 1
                total_corridas += len(concurrencies) * vars_count * repetitions

    print("=" * 70)
    print(" ORQUESTADOR DE MATRIZ EXPERIMENTAL - PLAYBOOK IT2iD 2026")
    print(f" Motores       : {', '.join(engines)}")
    print(f" Perfiles      : {', '.join(profiles)}")
    print(f" Consultas     : {', '.join(queries)}")
    print(f" Concurrencias : {concurrencies}")
    print(f" Repeticiones  : {repetitions}")
    print(f" Total Corridas: {total_corridas} ejecuciones")
    print(f" Warmup / Medición / Cooldown : {warmup_sec}s / {measure_sec}s / {cooldown_sec}s")
    print(f" Archivo Salida: {output_csv}")
    print("=" * 70)

    corrida_actual = 0
    t_global_start = time.time()

    for profile in profiles:
        aplicar_perfil_recursos(profile)

        for engine in engines:
            for query in queries:
                for conc in concurrencies:
                    # Determinación de variante de memoria para Q2
                    # En Q2 se evalúan las variantes de estrés de memoria
                    variantes_memoria = ["false", "true"] if (query == "Q2" and engine == "mongodb") else \
                                        (["4MB", "64MB"] if (query == "Q2" and engine == "postgresql") else ["default"])

                    for var_mem in variantes_memoria:
                        for rep in range(1, repetitions + 1):
                            corrida_actual += 1
                            progreso_pct = (corrida_actual / total_corridas) * 100
                            tiempo_transcurrido = time.time() - t_global_start

                            print("\n" + "#" * 70)
                            print(f" CORRIDA {corrida_actual}/{total_corridas} ({progreso_pct:.1f}%) | "
                                  f"Tiempo acumulado: {tiempo_transcurrido/60:.1f} min")
                            print(f" Config: {engine.upper()} | {profile} | {query} | "
                                  f"Clientes: {conc} | VarMem: {var_mem} | Rep: #{rep}")
                            print("#" * 70)

                            # 1. Flush de caché del kernel del host/VM
                            print(" -> Ejecutando flush de caché (drop_caches)...", end="", flush=True)
                            flush_ok = flush_caches()
                            print(f" [{'OK' if flush_ok else 'WARN'}]")

                            # 2. Ejecutar Benchmark Runner
                            python_bin = os.path.join(".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join(".venv", "bin", "python")
                            if not os.path.exists(python_bin):
                                python_bin = sys.executable

                            cmd_runner = [
                                python_bin, "benchmark_runner.py",
                                "--engine", engine,
                                "--profile", profile,
                                "--query", query,
                                "--concurrency", str(conc),
                                "--run-number", str(rep),
                                "--memory-variant", var_mem,
                                "--warmup", str(warmup_sec),
                                "--duration", str(measure_sec),
                                "--output-csv", output_csv
                            ]

                            subprocess.run(cmd_runner, check=True)

                            # 3. Cooldown de reposo
                            if cooldown_sec > 0 and corrida_actual < total_corridas:
                                print(f" -> Periodo de enfriamiento (cooldown: {cooldown_sec}s)...", end="", flush=True)
                                time.sleep(cooldown_sec)
                                print(" [LISTO]")

    t_total = time.time() - t_global_start
    print("\n" + "=" * 70)
    print(" MATRIZ EXPERIMENTAL COMPLETADA EXITOSAMENTE")
    print(f" Total de corridas ejecutadas: {corrida_actual}")
    print(f" Tiempo total invertido       : {t_total/60:.2f} minutos ({t_total/3600:.2f} horas)")
    print(f" Archivo consolidado CSV      : {output_csv}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador de la matriz de benchmarks de bases documentales.")
    parser.add_argument("--engines", nargs="+", default=MOTORES, choices=MOTORES)
    parser.add_argument("--profiles", nargs="+", default=list(PERFILES.keys()), choices=list(PERFILES.keys()))
    parser.add_argument("--queries", nargs="+", default=QUERIES, choices=QUERIES)
    parser.add_argument("--concurrencies", nargs="+", type=int, default=CONCURRENCIAS)
    parser.add_argument("--repetitions", type=int, default=3, help="Repeticiones por celda (default: 3)")
    parser.add_argument("--warmup", type=int, default=60, help="Segundos de warmup (default: 60)")
    parser.add_argument("--duration", type=int, default=300, help="Segundos de medición (default: 300)")
    parser.add_argument("--cooldown", type=int, default=60, help="Segundos de cooldown (default: 60)")
    parser.add_argument("--output-csv", type=str, default="results.csv", help="Ruta del archivo CSV consolidado")
    parser.add_argument("--quick", action="store_true", help="Modo rápido de prueba (5s warmup, 15s medición, 5s cooldown, 1 rep)")

    args = parser.parse_args()

    warmup = 5 if args.quick else args.warmup
    duration = 15 if args.quick else args.duration
    cooldown = 5 if args.quick else args.cooldown
    reps = 1 if args.quick else args.repetitions

    orquestar_matriz(
        engines=args.engines,
        profiles=args.profiles,
        queries=args.queries,
        concurrencies=args.concurrencies,
        repetitions=reps,
        warmup_sec=warmup,
        measure_sec=duration,
        cooldown_sec=cooldown,
        output_csv=args.output_csv
    )
