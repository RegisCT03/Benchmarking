# Resumen Ejecutivo: Medición de Métricas en Bases Documentales

**Asignatura / Contexto:** Bases de Datos en la Nube (2026) · Universidad Politécnica de Chiapas (IT2iD)  
**Documento Fuente:** `playbook.pdf`

---

## 1. Objetivo General
Comparar la latencia, el rendimiento (*throughput*) y la huella de recursos computacionales de un motor puramente documental (**MongoDB con WiredTiger**) frente a un motor relacional con soporte para documentos (**PostgreSQL con JSONB**) al ejecutar agregaciones complejas sobre JSON anidado, bajo condiciones estrictas de contención de CPU (CFS Throttling) y memoria mediante Docker cgroups v2.

---

## 2. Puntos Clave de la Experimentación

* **Preguntas de Investigación:**
  * **M1 (Latencia):** Impacto en percentiles P95 y P99 bajo contención severa de CPU y memoria.
  * **M2 (Buffers y OOM):** Eficiencia en el uso de buffers en ordenamiento/agrupamiento antes de volcar a disco (*disk spill*) o fallar por *OOM-kill*.
  * **M3 (Huella de Recursos):** Costo de CPU y memoria por cada 1 000 documentos procesados.

* **Motores y Modelado:**
  * **MongoDB (latest-stable):** Colección `orders` sin sharding, motor WiredTiger. Índices simples en `timestamp` y `order_id`.
  * **PostgreSQL (latest-stable):** Tabla `orders (id UUID PRIMARY KEY, data JSONB)`. Índice PK en `id` e índice B-Tree sobre la expresión `timestamp` extraída del JSONB.

* **Perfiles de Recursos (Docker cgroups v2, `mem_swappiness = 0`):**
  * `PROFILE_A_BASELINE`: 4.0 CPUs, 4096 MB RAM (Sin contención).
  * `PROFILE_B_MEDIUM`: 2.0 CPUs, 2048 MB RAM (Contención media).
  * `PROFILE_C_SEVERE`: 1.0 CPU, 1024 MB RAM (Contención severa con throttling activo).

* **Dataset:** 500 000 registros JSON con 3 niveles de anidamiento y promedio de 3 ítems por orden (`customer`, `items`, `payment`, `metadata`).

* **Cargas de Trabajo (Consultas):**
  * **Q1 (Saturación de CPU):** Desanidación de arreglos (`$unwind` / `jsonb_array_elements`), filtrado `price > 50`, cálculo de subtotal (`qty * price`) y agregaciones agrupadas por país y categoría.
  * **Q2 (Estrés de Buffer y Memoria):** Filtrado por estado/fecha, ordenamiento descendente por monto final sin índices previos y corte Top-1000. Se evalúan variantes:
    * MongoDB: `allowDiskUse: false` vs `allowDiskUse: true`.
    * PostgreSQL: `work_mem = '4MB'` vs `work_mem = '64MB'`.

* **Protocolo Experimental:**
  * Concurrencias de 1, 10 y 50 clientes.
  * Ciclo por corrida: Flush de caché del SO (`echo 3 > /proc/sys/vm/drop_caches`), Warmup (60s), Medición (300s) y Cooldown (60s).
  * Matriz total: 36 celdas $\times$ 3 repeticiones = **108 ejecuciones**.

* **Telemetría y KPIs:**
  * Stack: cAdvisor (cgroups v2), Node Exporter (I/O, disco, swap) y Prometheus (scrape cada 1s).
  * KPIs: `throughput_qps`, `latency_p50/p95/p99_ms`, `container_cpu_cfs_throttled_seconds_total`, `container_memory_rss_bytes`, `disk_spill_detected`, `oom_killed`.

* **Entregables:**
  * Repositorio con `docker-compose.yml`, generador sintético (`synthetic_data_generator.py`), ejecutor de benchmarks (`benchmark_runner`), scripts de consultas (`queries/`) y automatización (`run_benchmarks.sh`).
  * Archivo CSV consolidado de resultados.
  * Reporte técnico final estructurado en 7 secciones analíticas.
