# Reporte Completo: Medición de Métricas en Bases Documentales

**Documento Original:** `playbook.pdf`  
**Institución:** Universidad Politécnica de Chiapas  
**Carrera:** Ingeniería en Tecnologías de la Información e Innovación Digital (IT2iD)  
**Materia:** Bases de Datos en la Nube · 2026  
**Título del Trabajo:** *Medición de métricas en bases documentales: Contención de CPU y memoria en agregaciones JSON: MongoDB frente a PostgreSQL JSONB*

---

## 1. Objetivo General y Preguntas de Investigación

### 1.1. Objetivo
Medir la latencia, el rendimiento (*throughput*) y la huella de recursos computacionales al ejecutar agregaciones JSON anidadas bajo límites estrictos de CPU (CFS Throttling) y memoria mediante Docker cgroups v2, comparando un motor documental nativo (**MongoDB**) frente a un motor relacional que almacena y opera documentos en formato binario (**PostgreSQL JSONB**).

### 1.2. Preguntas de Investigación (Métricas)
* **M1:** ¿Cómo cambian la latencia P95 y P99 de las agregaciones sobre documentos anidados cuando se limita de forma estricta la CPU y la memoria?
* **M2:** ¿Qué motor usa de forma más eficiente los buffers de ordenamiento y agrupamiento antes de volcar a disco temporal (*disk spill*) o fallar por falta de memoria (*OOM-kill*)?
* **M3:** ¿Cuál es la huella de CPU y memoria por cada 1 000 documentos procesados en el motor documental frente al motor con JSONB?

---

## 2. Motores Objetivo y Modelo de Datos

| Característica | MongoDB | PostgreSQL |
| :--- | :--- | :--- |
| **Versión** | `latest-stable` | `latest-stable` |
| **Modelo de datos** | Colección `orders` sin sharding | Tabla `orders` con columna `data JSONB` |
| **Motor de almacenamiento** | WiredTiger | Heap standard con almacenamiento TOAST para JSONB |
| **Esquema de tabla/colección** | Documental BSON | `CREATE TABLE orders (id UUID PRIMARY KEY, data JSONB);` |
| **Indexación** | Índice simple en `timestamp` y `order_id` | Clave primaria en `id`; B-Tree sobre `timestamp` extraído del JSONB |

---

## 3. Perfiles de Recursos (Docker / cgroups v2)

Se establecen 3 perfiles de contención. En todos los casos se desactiva el área de intercambio (`mem_swappiness = 0`) para evitar distorsiones por swap en disco y forzar la contención estricta en RAM:

| ID del Perfil | Nombre / Descripción | CPUs asignadas | Memoria RAM | mem_swappiness |
| :--- | :--- | :--- | :--- | :--- |
| `PROFILE_A_BASELINE` | Sin contención (Baseline de referencia) | 4.0 | 4096 MB | 0 |
| `PROFILE_B_MEDIUM` | Contención media | 2.0 | 2048 MB | 0 |
| `PROFILE_C_SEVERE` | Contención severa (CFS throttling activo) | 1.0 | 1024 MB | 0 |

---

## 4. Especificación del Dataset Sintético

* **Volumen:** 500 000 registros en formato JSON.
* **Estructura jerárquica:** 3 niveles de anidamiento; promedio de 3 ítems por orden.
* **Esquema de atributos:**
  * `order_id` (UUID).
  * `timestamp` (formato ISO-8601).
  * `customer` (objeto anidado):
    * `id`
    * `tier`
    * `segment`
    * `geo`: sub-objeto con `country`, `state`, `city`, `zip`, `coordinates`.
  * `items` (arreglo de sub-objetos):
    * `sku`, `category`, `brand`, `qty`, `price`, `tax_pct`, `discounts`.
  * `payment` (objeto anidado):
    * `method`, `status`, `transaction_id`, `gateway_latency_ms`, `totals`.
  * `metadata` (objeto anidado):
    * `channel`, `user_agent`, `session_id`, `flags`.

---

## 5. Cargas de Trabajo (Consultas)

### 5.1. Q1 — Unwind, Filter & Grouping (Saturación de CPU)
* **Propósito:** Evaluar el coste de CPU al deserializar y aplanar arreglos anidados, aplicar predicados sobre campos secundarios y realizar cálculos agregados.
* **Operación:** Desanidar el arreglo `items`, filtrar productos con `price > 50`, calcular subtotal (`qty * price`), y obtener la sumatoria de ingresos (`total_revenue`), el promedio (`avg_revenue`) y la cantidad de items (`count`), agrupados por país (`customer.geo.country`) y categoría (`items.category`).

#### Implementación en MongoDB:
```javascript
[
  { "$unwind": "$items" },
  { "$match": { "items.price": { "$gt": 50 } } },
  {
    "$group": {
      "_id": {
        "country": "$customer.geo.country",
        "category": "$items.category"
      },
      "total_revenue": { "$sum": { "$multiply": ["$items.qty", "$items.price"] } },
      "avg_revenue": { "$avg": { "$multiply": ["$items.qty", "$items.price"] } },
      "count": { "$sum": 1 }
    }
  }
]
```

#### Implementación en PostgreSQL:
```sql
SELECT data->'customer'->'geo'->>'country' AS country,
       item->>'category' AS category,
       SUM((item->>'qty')::numeric * (item->>'price')::numeric) AS total_revenue,
       AVG((item->>'qty')::numeric * (item->>'price')::numeric) AS avg_revenue,
       COUNT(*) AS count
FROM orders, jsonb_array_elements(data->'items') AS item
WHERE (item->>'price')::numeric > 50
GROUP BY 1, 2;
```

---

### 5.2. Q2 — Massive Sort & Top-K (Estrés de Buffer y Memoria)
* **Propósito:** Medir la capacidad de gestión de memoria al procesar un ordenamiento masivo sin índice de soporte sobre campos numéricos anidados.
* **Operación:** Filtrar órdenes con `payment.status = 'completed'` posteriores a `'2026-01-01T00:00:00Z'`, ordenar descendentemente por `payment.final_total` y retornar los primeros 1 000 resultados.
* **Variantes de estrés de memoria:**
  * **MongoDB:** Ejecución con `allowDiskUse: false` frente a `allowDiskUse: true`.
  * **PostgreSQL:** Configuración de sesión con `SET work_mem = '4MB'` frente a `SET work_mem = '64MB'`.

#### Implementación en MongoDB:
```javascript
[
  { 
    "$match": {
      "payment.status": "completed",
      "timestamp": { "$gte": "2026-01-01T00:00:00Z" }
    } 
  },
  { "$sort": { "payment.final_total": -1 } },
  { "$limit": 1000 },
  { 
    "$project": {
      "order_id": 1, 
      "customer.id": 1, 
      "payment.final_total": 1
    } 
  }
]
```

#### Implementación en PostgreSQL:
```sql
SELECT data->>'order_id' AS order_id,
       data->'customer'->>'id' AS customer_id,
       (data->'payment'->>'final_total')::numeric AS final_total
FROM orders
WHERE data->'payment'->>'status' = 'completed'
  AND (data->>'timestamp')::timestamptz >= '2026-01-01 00:00:00Z'
ORDER BY (data->'payment'->>'final_total')::numeric DESC
LIMIT 1000;
```

---

## 6. Protocolo de Ejecución Experimental

1. **Variables de Concurrencia:** 1, 10 y 50 clientes simultáneos.
2. **Repeticiones:** 3 iteraciones por cada escenario para garantizar significancia estadística.
3. **Ciclo de Vida por Prueba:**
   * **Limpieza de caché de página y buffer del SO:**
     ```bash
     sync; echo 3 > /proc/sys/vm/drop_caches
     ```
   * **Warmup:** 60 segundos para precalentar pools de conexiones y buffers permitidos.
   * **Fase de medición:** 300 segundos (5 minutos de carga sostenida).
   * **Cooldown:** 60 segundos de reposo antes de la siguiente prueba.
4. **Matriz de Ejecución:**
   $$\text{2 motores} \times \text{3 perfiles de recursos} \times \text{2 queries} \times \text{3 niveles de concurrencia} = 36 \text{ combinaciones}$$
   Con 3 repeticiones por combinación, se completa un total de **108 corridas experimentales**.

---

## 7. Telemetría y KPIs

### 7.1. Stack de Monitoreo
* **cAdvisor:** Monitoreo y métricas a nivel de contenedor Linux (métricas de cgroups v2).
* **Node Exporter:** Métricas globales del host físico (E/S de disco, swap, paginación).
* **Prometheus:** Colector central con intervalo de recolección de alta resolución: `scrape_interval: 1s`.

### 7.2. Indicadores Clave de Rendimiento (KPIs)

| Indicador (KPI) | Unidad | Tipo de Métrica | Descripción |
| :--- | :--- | :--- | :--- |
| `throughput_qps` | queries/s | Performance | Tasa de consultas procesadas por segundo |
| `latency_p50_ms` | ms | Performance | Mediana de tiempo de respuesta |
| `latency_p95_ms` | ms | Performance | Percentil 95 de latencia |
| `latency_p99_ms` | ms | Performance | Percentil 99 de latencia (análisis de cola) |
| `container_cpu_cfs_throttled_seconds_total` | segundos | OS / Contención | Tiempo total estrangulado por el planificador CFS |
| `container_memory_rss_bytes` | bytes | OS / Memory | Memoria física residente ocupada por el motor |
| `disk_spill_detected` | boolean | Engine / Internal | Indica si la consulta requirió volcado a disco temporal |
| `oom_killed` | boolean | Stability | Indica si el contenedor/proceso fue terminado por OOM |

---

## 8. Entregables del Proyecto

### 8.1. Estructura del Repositorio de Código
* `docker-compose.yml`: Archivo de orquestación con perfiles de recursos parametrizados para MongoDB y PostgreSQL.
* `synthetic_data_generator.py`: Generador determinista del dataset de 500k registros JSON.
* `benchmark_runner`: Scripts ejecutores de prueba de carga (desarrollados en k6 o Python multiproceso).
* `queries/`: Directorio con los scripts de agregación para MongoDB y las sentencias SQL para PostgreSQL.
* `run_benchmarks.sh`: Script de bash para automatizar la ejecución secuencial de la matriz de 108 pruebas.

### 8.2. Esquema CSV de Resultados
El script de benchmark debe consolidar los datos de telemetría y resultados en un archivo CSV con la siguiente cabecera:
```csv
timestamp_epoch,engine,profile,query_id,concurrency,run_number,throughput_qps,latency_p50_ms,latency_p95_ms,latency_p99_ms,cpu_throttled_seconds,max_rss_mb,disk_spill,status
```

### 8.3. Secciones Requeridas en el Reporte de Métricas Final
1. **Especificaciones del host y del entorno Docker:** Características de CPU, memoria, kernel y configuración de cgroups v2.
2. **Método de medición y verificación del baseline:** Validación de condiciones iniciales sin contención.
3. **Resultados consolidados:** Tablas comparativas de Throughput, P95/P99 y tiempo de throttling.
4. **Análisis gráfico:** Curvas de P99 frente a concurrencia, Throttling frente a QPS y evolución del consumo RSS.
5. **Planes de ejecución:** Análisis comparativo de `explain("executionStats")` frente a `EXPLAIN (ANALYZE, BUFFERS)`.
6. **Interpretación:** Discusión sobre impacto de cuotas de memoria, volcado a disco y CFS throttling.
7. **Recomendaciones técnicas:** Guía de buenas prácticas y dimensionamiento para despliegues documentales en la nube.
