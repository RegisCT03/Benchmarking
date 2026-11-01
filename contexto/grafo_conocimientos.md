# Grafo de Conocimientos: Medición de Métricas en Bases Documentales

Este documento contiene la representación visual estructurada (grafo de conocimiento en formato Mermaid) de la arquitectura experimental, variables, cargas de trabajo y flujo de resultados definidos en el `playbook.pdf`.

---

## 1. Diagrama de Relaciones y Entidades

```mermaid
flowchart TD
    %% NODO PRINCIPAL
    EXP["Experimento: Medición de Métricas en Bases Documentales\n(UP Chiapas - IT2iD 2026)"]

    %% OBJETIVOS Y PREGUNTAS
    subgraph S_OBJETIVOS["1. Objetivos y Preguntas de Investigación"]
        OBJ["Objetivo Central:\nMedir latencia, rendimiento y huella de recursos\nbajo contención estricta de CPU (CFS) y Memoria"]
        M1["M1: Degradación de latencia P95 y P99"]
        M2["M2: Eficiencia de buffers vs Disk Spill / OOM"]
        M3["M3: Huella de CPU y RAM por 1 000 documentos"]
        OBJ --> M1
        OBJ --> M2
        OBJ --> M3
    end

    %% MOTORES Y ALMACENAMIENTO
    subgraph S_MOTORES["2. Motores Objetivo y Modelado"]
        MONGO["MongoDB (latest-stable)"]
        PG["PostgreSQL (latest-stable)"]
        
        MONGO_CONFIG["- Storage: WiredTiger\n- Colección: orders (sin sharding)\n- Índices: timestamp, order_id"]
        PG_CONFIG["- Tabla: orders (id UUID, data JSONB)\n- PK en id\n- B-Tree sobre timestamp extraído de JSONB"]
        
        MONGO --> MONGO_CONFIG
        PG --> PG_CONFIG
    end

    %% PERFILES DE RECURSOS
    subgraph S_PERFILES["3. Perfiles de Recursos (cgroups v2)"]
        SWAPPINESS["mem_swappiness = 0 (Sin Swap)"]
        P_A["PROFILE_A_BASELINE\n4.0 CPUs | 4096 MB RAM"]
        P_B["PROFILE_B_MEDIUM\n2.0 CPUs | 2048 MB RAM"]
        P_C["PROFILE_C_SEVERE\n1.0 CPU | 1024 MB RAM (Throttling)"]
        
        SWAPPINESS --- P_A
        SWAPPINESS --- P_B
        SWAPPINESS --- P_C
    end

    %% DATASET
    subgraph S_DATASET["4. Especificación del Dataset"]
        DATASET_MAIN["500 000 Registros JSON\n3 niveles de anidamiento\nPromedio 3 items/registro"]
        DATASET_FIELDS["Atributos:\n- order_id (UUID), timestamp (ISO-8601)\n- customer (id, tier, segment, geo)\n- items (arreglo: sku, price, qty, tax)\n- payment (method, status, final_total)\n- metadata (channel, session_id)"]
        DATASET_MAIN --- DATASET_FIELDS
    end

    %% CARGAS DE TRABAJO (QUERIES)
    subgraph S_QUERIES["5. Cargas de Trabajo (Consultas)"]
        Q1["Q1: Unwind, Filter & Grouping\n(Saturación de CPU)"]
        Q1_OP["Desanidar items -> price > 50 ->\nSum/Avg Revenue & Count por país y categoría\n- Mongo: $unwind + $match + $group\n- Postgres: jsonb_array_elements"]

        Q2["Q2: Massive Sort & Top-K\n(Estrés de Buffer y Memoria)"]
        Q2_OP["Filtro status=completed y timestamp ->\nSort final_total DESC -> LIMIT 1000"]
        Q2_VAR["Variantes de Memoria:\n- Mongo: allowDiskUse (true / false)\n- Postgres: work_mem (4MB / 64MB)"]

        Q1 --> Q1_OP
        Q2 --> Q2_OP
        Q2 --> Q2_VAR
    end

    %% PROTOCOLO EXPERIMENTAL
    subgraph S_PROTOCOLO["6. Protocolo de Ejecución"]
        CONCURRENCY["Concurrencia: 1, 10, 50 clientes"]
        LIFECYCLE["Ciclo de Vida por Prueba:\n1. Drop caches: echo 3 > drop_caches\n2. Warmup: 60s\n3. Medición activa: 300s\n4. Cooldown: 60s"]
        RUNS["Matriz Experimental:\n2 motores × 3 perfiles × 2 queries × 3 concurrencias\n= 36 combinaciones × 3 repeticiones = 108 corridas"]
        CONCURRENCY --> RUNS
        LIFECYCLE --> RUNS
    end

    %% TELEMETRÍA Y OBSERVABILIDAD
    subgraph S_TELEMETRIA["7. Stack de Telemetría y KPIs"]
        OBS_STACK["Stack de Observabilidad:\n- cAdvisor (cgroups v2)\n- Node Exporter (Host I/O & Swap)\n- Prometheus (scrape_interval: 1s)"]
        KPIS["Métricas / KPIs:\n- Performance: throughput_qps, latency_p50/p95/p99_ms\n- OS / Contención: container_cpu_cfs_throttled_seconds_total\n- OS / Memoria: container_memory_rss_bytes\n- Motor / Estabilidad: disk_spill_detected, oom_killed"]
        OBS_STACK --> KPIS
    end

    %% ENTREGABLES
    subgraph S_ENTREGABLES["8. Entregables Requeridos"]
        REPO["Repositorio de Código:\n- docker-compose.yml\n- synthetic_data_generator.py\n- benchmark_runner\n- queries/\n- run_benchmarks.sh"]
        CSV["Esquema CSV Consolidado\n(14 columnas con telemetría normalizada)"]
        REPORTE["Reporte Técnico (7 Secciones):\n- Host y entorno Docker\n- Verificación Baseline\n- Resultados Throughput / Latencia\n- Análisis Gráfico (P99, Throttling, RSS)\n- Execution Plans (explain)\n- Interpretación de Límites\n- Recomendaciones Cloud"]
    end

    %% VINCULACIÓN ENTRE COMPONENTES
    EXP --> S_OBJETIVOS
    EXP --> S_MOTORES
    EXP --> S_PERFILES
    EXP --> S_DATASET

    S_MOTORES ==> S_QUERIES
    S_DATASET ==> S_QUERIES
    S_PERFILES ==> S_PROTOCOLO
    S_QUERIES ==> S_PROTOCOLO
    S_PROTOCOLO ==> S_TELEMETRIA
    S_TELEMETRIA ==> S_ENTREGABLES
```

---

## 2. Descripción de Subgrafos y Conexiones

1. **Subgrafo de Objetivos y Métricas:** Establece el marco conceptual enfocado en evaluar cómo la limitación de hardware en microservicios/contenedores altera la latencia de cola (P95/P99) y cómo responden los motores ante insuficiencia de buffers en memoria.
2. **Subgrafo de Motores y Modelado:** Contrasta la arquitectura nativa documental basada en documentos BSON (MongoDB) con un modelo híbrido relacional que indexa y almacena documentos JSONB mediante tipos binarios estructurados (PostgreSQL).
3. **Subgrafo de Perfiles de Recursos:** Modela los tres escalones de aislamiento de Docker basados en cgroups v2 (`BASELINE`, `MEDIUM`, `SEVERE`), donde la supresión de swap (`mem_swappiness = 0`) asegura que la memoria no tenga rutas de escape.
4. **Subgrafo de Cargas de Trabajo (Consultas):**
   * **Q1** pone a prueba la capacidad de CPU deserializando 500,000 registros anidados.
   * **Q2** somete a prueba los algoritmos de ordenamiento interno (in-memory sort vs external merge sort en disco) ajustando parámetros de motor (`allowDiskUse` y `work_mem`).
5. **Subgrafo de Protocolo y Matriz:** Diseña la repetibilidad estadística mediante 108 iteraciones con limpieza estricta de cachés de kernel (`drop_caches`), precalentamiento y periodos de estabilización.
6. **Subgrafo de Telemetría:** Vincula el raspado en tiempo real a intervalos de 1 segundo de Prometheus con las métricas de contención CFS provistas por cAdvisor a nivel de cgroups v2.
7. **Subgrafo de Entregables:** Mapea cómo los resultados de la telemetría alimentan el dataset CSV final y las 7 secciones analíticas del reporte técnico de investigación.
