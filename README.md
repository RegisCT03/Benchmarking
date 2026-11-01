# Benchmarking: MongoDB WiredTiger vs PostgreSQL JSONB

Experimento comparativo de motores de bases de datos bajo contención estricta de CPU/memoria con Docker cgroups v2.

**Asignatura:** Bases de Datos en la Nube 2026 — Universidad Politécnica de Chiapas / IT2iD  
**Matrícula:** 243723  

---

## Descripción

Este repositorio contiene el código completo del experimento definido en el playbook de la asignatura. Se compara el comportamiento de **MongoDB (WiredTiger)** vs **PostgreSQL 17 (JSONB)** bajo tres perfiles de recursos progresivamente restrictivos, usando un dataset de **500,000 registros académicos** con 3 niveles de anidamiento.

### Queries evaluadas

| Query | Descripción |
|---|---|
| **Q1** | Agregación analítica: promedio de calificaciones agrupado por carrera/campus |
| **Q2** | Filtrado temporal con índice: registros desde 2026-01-01, ordenados por fecha |

### Perfiles de recursos (cgroups v2)

| Perfil | CPU | RAM |
|---|---|---|
| `PROFILE_A_BASELINE` | 4.0 vCPU | 4 GB |
| `PROFILE_B_MEDIUM` | 2.0 vCPU | 2 GB |
| `PROFILE_C_SEVERE` | 0.5 vCPU | 512 MB |

### Matriz experimental

- 2 motores × 3 perfiles × 4 sub-queries × 3 concurrencias × 3 repeticiones = **162 corridas totales**

---

## Requisitos

- Docker Desktop con WSL2 y cgroups v2 habilitados
- Python 3.11+ con `.venv`
- WSL2 para el comando `drop_caches` entre corridas

---

## Inicio rápido

### 1. Configurar variables de entorno

```bash
cp .env.example .env
# Edita .env con tus credenciales y el perfil deseado
```

### 2. Levantar la infraestructura

```bash
docker compose up -d
```

### 3. Generar el dataset sintético

```bash
python synthetic_data_generator.py
# Genera data/dataset_500k.jsonl (~380 MB, semilla 42)
```

### 4. Cargar datos en ambos motores

```bash
python load_data.py
# Carga 500k registros en MongoDB y PostgreSQL + crea índices
```

### 5. Ejecutar la suite de benchmarks

```bash
python run_benchmarks.py
# Ejecuta las 162 corridas (tiempo estimado: 12-14 horas)
```

### 6. Generar gráficas y CSV consolidado

```bash
python generate_report_charts.py
# Genera results_final.csv y 4 PNGs en reporte/graficos/
```

---

## Estructura del repositorio

```
243723_Experimento/
├── docker-compose.yml          # Stack: MongoDB, PostgreSQL, Prometheus, cAdvisor, Node Exporter
├── .env.example                # Plantilla de variables de entorno (copia como .env)
├── prometheus/
│   └── prometheus.yml          # Configuración de scraping (interval: 1s)
├── queries/
│   ├── init_mongo.js           # Inicialización colección MongoDB
│   ├── init_postgres.sql       # Inicialización tabla PostgreSQL
│   ├── mongo_q1.js             # Q1 MongoDB (aggregation pipeline)
│   ├── mongo_q2_disk_false.js  # Q2 MongoDB (allowDiskUse: false)
│   ├── mongo_q2_disk_true.js   # Q2 MongoDB (allowDiskUse: true)
│   ├── postgres_q1.sql         # Q1 PostgreSQL (JSONB aggregation)
│   ├── postgres_q2_4mb.sql     # Q2 PostgreSQL (work_mem 4MB)
│   └── postgres_q2_64mb.sql    # Q2 PostgreSQL (work_mem 64MB)
├── contexto/
│   ├── base.json               # Plantilla de documento académico
│   ├── registros_academicos.js # Consultas de referencia (MongoDB)
│   └── registros_academicos.sql # Consultas de referencia (PostgreSQL)
├── synthetic_data_generator.py # Genera 500k registros académicos (semilla 42)
├── load_data.py                # Carga masiva + índices + VACUUM ANALYZE
├── benchmark_runner.py         # Runner multihilo con telemetría Prometheus
├── run_benchmarks.py           # Orquestador Python (162 corridas)
├── run_benchmarks.sh           # Orquestador Bash (alternativo)
└── generate_report_charts.py   # Consolida CSVs y genera 4 gráficas PNG
```

---

## Métricas recolectadas

Por cada corrida se registran 14 columnas en el CSV de resultados:

| Columna | Descripción |
|---|---|
| `timestamp_epoch` | Unix timestamp de inicio |
| `engine` | `mongodb` o `postgresql` |
| `profile` | Perfil de recursos activo |
| `query_id` | `Q1` o `Q2` |
| `concurrency` | Clientes simultáneos (1, 10, 50) |
| `run_number` | Repetición (1, 2, 3) |
| `throughput_qps` | Consultas por segundo |
| `latency_p50/p95/p99_ms` | Percentiles de latencia |
| `cpu_throttled_seconds` | Throttling CFS acumulado (vía cAdvisor) |
| `max_rss_mb` | Memoria RSS máxima del contenedor |
| `disk_spill` | Si hubo spill a disco |
| `status` | `success` o `failed` |

---

## Notas técnicas

- **cgroups v2** verificados con Docker Desktop WSL2
- **drop_caches** entre corridas: `wsl -d docker-desktop -u root -e sh -c "sync; echo 3 > /proc/sys/vm/drop_caches"`
- **PostgreSQL 17** requerido (v18+ cambió la ruta del volumen de datos)
- El índice de fecha en PostgreSQL es sobre texto ISO-8601 (no `::timestamptz`) por restricciones de inmutabilidad
