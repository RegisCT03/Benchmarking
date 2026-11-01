-- ==========================================================
-- REGISTROS ACADÉMICOS - POSTGRESQL CONFIGURACIÓN & QUERIES
-- Asignatura: Bases de Datos en la Nube (IT2iD - UP Chiapas)
-- ==========================================================

-- 1. Crear la tabla para documentos JSONB
CREATE TABLE IF NOT EXISTS registros_academicos (
    id UUID PRIMARY KEY,
    data JSONB NOT NULL
);

-- 2. Crear el índice B-Tree sobre timestamp (fecha_registro) extraído del JSONB
CREATE INDEX IF NOT EXISTS idx_registros_fecha 
ON registros_academicos USING BTREE (((data->>'fecha_registro')::timestamptz));

-- ==========================================================
-- 3. CONSULTA Q1 - Unwind, Filter & Grouping (Saturación de CPU)
-- ==========================================================
-- Desanidar materias con jsonb_array_elements, filtrar calificación >= 7.0,
-- calcular carga horaria (créditos * horas_semana) y agrupar sumatoria,
-- promedio y conteo por carrera y clave de materia.
SELECT data->'estudiante'->'detalles_academicos'->>'carrera' AS carrera,
       materia->>'clave' AS materia,
       SUM((materia->>'creditos')::numeric * (materia->>'horas_semana')::numeric) AS total_carga_horaria,
       AVG((materia->>'creditos')::numeric * (materia->>'horas_semana')::numeric) AS avg_carga_horaria,
       COUNT(*) AS total_registros
FROM registros_academicos, jsonb_array_elements(data->'materias') AS materia
WHERE (materia->>'calificacion')::numeric >= 7.0
GROUP BY 1, 2;

-- ==========================================================
-- 4. CONSULTA Q2 - Massive Sort & Top-K (Estrés de Buffer)
-- ==========================================================
-- Filtrar registros activos desde 2026-01-01, ordenar descendente
-- por promedio_general (sin índice) y limitar al Top-1000.
-- Variantes de memoria:
-- SET work_mem = '4MB';  -- para forzar derrame a disco temporal
-- SET work_mem = '64MB'; -- para permitir ordenamiento en RAM
SELECT data->>'registro_id' AS registro_id,
       data->'estudiante'->>'matricula' AS matricula,
       (data->'cuatrimestre_info'->>'promedio_general')::numeric AS promedio_general
FROM registros_academicos
WHERE data->'cuatrimestre_info'->>'estado' = 'activo'
  AND (data->>'fecha_registro')::timestamptz >= '2026-01-01 00:00:00Z'
ORDER BY (data->'cuatrimestre_info'->>'promedio_general')::numeric DESC
LIMIT 1000;
