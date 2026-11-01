#!/usr/bin/env python3
"""
Generador de Datos Sintéticos para Benchmark de Bases Documentales
Asignatura: Bases de Datos en la Nube - IT2iD (UP Chiapas)
Genera 500 000 registros en formato NDJSON basados en el esquema de Registros Académicos.
"""

import sys
import os
import time
import uuid
import random
import argparse
from datetime import datetime, timedelta

# Catálogo de datos realistas para la Universidad Politécnica de Chiapas (UP Chiapas)
CARRERAS = [
    "IT2iD",
    "Ingeniería de Software",
    "Mecatrónica",
    "Ingeniería Biomédica",
    "Biotecnología",
    "Tecnología Ambiental",
    "Agroindustrial",
    "Energía",
]

MODALIDADES = ["presencial", "presencial", "presencial", "hibrida", "virtual"]
CAMPUS_LIST = ["Suchiapa", "Suchiapa", "Suchiapa", "Tuxtla"]
TIPOS_INGRESO = ["nuevo_ingreso", "reingreso", "equivalencia", "pase_directo"]

CATALOGO_MATERIAS = [
    ("IT201", "Bases de Datos en la Nube", 4, 6),
    ("IT202", "Desarrollo Full-Stack", 5, 8),
    ("IT203", "Ingeniería de Software", 4, 5),
    ("IT204", "Arquitectura de Software", 4, 5),
    ("IT205", "Seguridad en la Nube", 3, 4),
    ("IT206", "Inteligencia Artificial Aplicada", 5, 6),
    ("IT207", "DevOps & CI/CD", 4, 6),
    ("IT208", "Computación Concurrente y Distribuida", 4, 5),
    ("IT209", "Redes de Computadoras", 4, 5),
    ("IT210", "Estructuras de Datos Avanzadas", 5, 6),
    ("IT211", "Gobierno de Datos", 3, 4),
    ("IT212", "Sistemas Embebidos e IoT", 4, 6),
]

PERIODOS = [
    "Ene-Abr 2025",
    "May-Ago 2025",
    "Sep-Dic 2025",
    "Ene-Abr 2026",
    "May-Ago 2026",
    "Sep-Dic 2026",
]

ESTADOS = ["activo", "activo", "activo", "inactivo", "egresado", "baja_temporal"]
PLATAFORMAS = ["mindstack_app", "portal_it2id", "app_movil_estudiante", "ventanilla_virtual"]

TAGS_POOL = [
    ["regular"],
    ["regular", "cuadro_honor"],
    ["irregular"],
    ["becario", "regular"],
    ["becario", "cuadro_honor"],
    ["servicio_social", "regular"],
    ["estancia_profesional", "regular"],
]


def generar_registro(rnd: random.Random, timestamp_base: datetime) -> str:
    # 1. Identificadores y fechas
    reg_id = str(uuid.UUID(int=rnd.getrandbits(128), version=4))
    
    # Rango de fechas entre 2025-01-01 y 2026-12-31 (~50% antes/después de 2026-01-01)
    segundos_offset = rnd.randint(0, 730 * 86400)
    fecha_dt = timestamp_base + timedelta(seconds=segundos_offset)
    fecha_iso = fecha_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. Datos del estudiante (3 niveles de profundidad)
    matricula = str(rnd.randint(210000, 269999))
    tipo_ingreso = rnd.choice(TIPOS_INGRESO)
    carrera = rnd.choice(CARRERAS)
    modalidad = rnd.choice(MODALIDADES)
    campus = rnd.choice(CAMPUS_LIST)

    # 3. Arreglo de materias (promedio 3 items: 2 a 4 materias)
    num_materias = rnd.choices([2, 3, 4], weights=[20, 60, 20])[0]
    materias_seleccionadas = rnd.sample(CATALOGO_MATERIAS, num_materias)
    
    materias_json_items = []
    suma_califs = 0.0
    total_creditos = 0

    for clave, nombre, creditos, horas in materias_seleccionadas:
        # Calificaciones entre 5.0 y 10.0 en incrementos de 0.5
        calif = round(rnd.uniform(5.0, 10.0), 1)
        suma_califs += calif
        total_creditos += creditos
        
        materias_json_items.append(
            f'{{"clave":"{clave}","nombre":"{nombre}","creditos":{creditos},"horas_semana":{horas},"calificacion":{calif}}}'
        )

    materias_str = "[" + ",".join(materias_json_items) + "]"
    promedio_general = round(suma_califs / num_materias, 2)

    # 4. Información de cuatrimestre
    # Si la fecha es de 2026, asignamos periodo de 2026
    periodo = rnd.choice(PERIODOS[3:]) if fecha_dt.year >= 2026 else rnd.choice(PERIODOS[:3])
    estado = rnd.choice(ESTADOS)

    # 5. Auditoría
    plataforma = rnd.choice(PLATAFORMAS)
    ip_registro = f"192.168.{rnd.randint(1, 254)}.{rnd.randint(1, 254)}"
    tags_selected = rnd.choice(TAGS_POOL)
    tags_str = "[" + ",".join(f'"{t}"' for t in tags_selected) + "]"

    # Ensamblado directo de JSON para máxima velocidad de generación
    return (
        f'{{"registro_id":"{reg_id}",'
        f'"fecha_registro":"{fecha_iso}",'
        f'"estudiante":{{"matricula":"{matricula}","tipo_ingreso":"{tipo_ingreso}",'
        f'"detalles_academicos":{{"carrera":"{carrera}","modalidad":"{modalidad}","campus":"{campus}"}}}},'
        f'"materias":{materias_str},'
        f'"cuatrimestre_info":{{"periodo":"{periodo}","estado":"{estado}",'
        f'"promedio_general":{promedio_general},"total_creditos":{total_creditos}}},'
        f'"auditoria":{{"plataforma":"{plataforma}","ip_registro":"{ip_registro}","tags":{tags_str}}}}}\n'
    )


def generar_dataset(total_records: int, output_file: str, seed: int = 42, batch_size: int = 10000):
    print("=" * 65)
    print(" GENERADOR DE DATASET SINTÉTICO - REGISTROS ACADÉMICOS (IT2iD)")
    print(f" Registros objetivo : {total_records:,}")
    print(f" Archivo de salida  : {output_file}")
    print(f" Semilla aleatoria  : {seed}")
    print(f" Tamaño de lote     : {batch_size:,}")
    print("=" * 65)

    rnd = random.Random(seed)
    timestamp_base = datetime(2025, 1, 1, 0, 0, 0)
    
    start_time = time.time()
    generated_count = 0

    # Crear directorio padre si no existe
    parent_dir = os.path.dirname(output_file)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    with open(output_file, "w", encoding="utf-8", buffering=1024 * 1024 * 8) as f:
        buffer = []
        for i in range(1, total_records + 1):
            buffer.append(generar_registro(rnd, timestamp_base))
            
            if i % batch_size == 0 or i == total_records:
                f.writelines(buffer)
                buffer.clear()
                generated_count = i
                elapsed = time.time() - start_time
                rate = generated_count / elapsed if elapsed > 0 else 0
                pct = (generated_count / total_records) * 100
                print(f" -> Progreso: {generated_count:7,d} / {total_records:,} ({pct:5.1f}%) | "
                      f"Velocidad: {rate:7.0f} reg/s | Transcurrido: {elapsed:5.1f}s", end="\r")

    total_time = time.time() - start_time
    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"\n\n[OK] Generación completada con éxito.")
    print(f" Archivo generado   : {output_file}")
    print(f" Tamaño en disco    : {file_size_mb:.2f} MB")
    print(f" Tiempo total       : {total_time:.2f} s")
    print(f" Velocidad media    : {total_records / total_time:.0f} registros/s")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador de dataset de Registros Académicos.")
    parser.add_argument("--count", type=int, default=500000, help="Número de registros (default: 500000)")
    parser.add_argument("--output", type=str, default="dataset_500k.jsonl", help="Ruta del archivo de salida")
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria para reproducibilidad")
    parser.add_argument("--batch-size", type=int, default=10000, help="Tamaño del lote en memoria")
    args = parser.parse_args()

    generar_dataset(args.count, args.output, args.seed, args.batch_size)
