-- Consulta Q2 - Massive Sort & Top-K con work_mem = '4MB'
SET work_mem = '4MB';

SELECT data->>'registro_id' AS registro_id,
       data->'estudiante'->>'matricula' AS matricula,
       (data->'cuatrimestre_info'->>'promedio_general')::numeric AS promedio_general
FROM registros_academicos
WHERE data->'cuatrimestre_info'->>'estado' = 'activo'
  AND (data->>'fecha_registro')::timestamptz >= '2026-01-01 00:00:00Z'
ORDER BY (data->'cuatrimestre_info'->>'promedio_general')::numeric DESC
LIMIT 1000;
