-- Consulta Q1 - Unwind, Filter & Grouping (Saturación de CPU)
SELECT data->'estudiante'->'detalles_academicos'->>'carrera' AS carrera,
       materia->>'clave' AS materia,
       SUM((materia->>'creditos')::numeric * (materia->>'horas_semana')::numeric) AS total_carga_horaria,
       AVG((materia->>'creditos')::numeric * (materia->>'horas_semana')::numeric) AS avg_carga_horaria,
       COUNT(*) AS total_registros
FROM registros_academicos, jsonb_array_elements(data->'materias') AS materia
WHERE (materia->>'calificacion')::numeric >= 7.0
GROUP BY 1, 2;
