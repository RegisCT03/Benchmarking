// ==========================================================
// REGISTROS ACADÉMICOS - MONGODB CONFIGURACIÓN & QUERIES
// Asignatura: Bases de Datos en la Nube (IT2iD - UP Chiapas)
// ==========================================================

// 1. Usar la base de datos
use it2id_universidad;

// 2. Crear los índices requeridos por el playbook
db.registros_academicos.createIndex({ "fecha_registro": 1 });
db.registros_academicos.createIndex({ "registro_id": 1 });

// ==========================================================
// 3. CONSULTA Q1 - Unwind, Filter & Grouping (Saturación de CPU)
// ==========================================================
// Desanidar materias, filtrar calificación >= 7.0, calcular
// carga horaria (créditos * horas_semana) y agrupar sumatoria,
// promedio y conteo por carrera y clave de materia.
db.registros_academicos.aggregate([
  { "$unwind": "$materias" },
  { "$match": { "materias.calificacion": { "$gte": 7.0 } } },
  {
    "$group": {
      "_id": {
        "carrera": "$estudiante.detalles_academicos.carrera",
        "materia": "$materias.clave"
      },
      "total_carga_horaria": { 
        "$sum": { "$multiply": ["$materias.creditos", "$materias.horas_semana"] } 
      },
      "avg_carga_horaria": { 
        "$avg": { "$multiply": ["$materias.creditos", "$materias.horas_semana"] } 
      },
      "total_registros": { "$sum": 1 }
    }
  }
]);

// ==========================================================
// 4. CONSULTA Q2 - Massive Sort & Top-K (Estrés de Buffer)
// ==========================================================
// Filtrar cuatrimestres activos desde 2026-01-01, ordenar
// descendente por promedio_general sin índice previo y obtener Top-1000.
// Variante A: { allowDiskUse: false }  --> falla si excede memoria
// Variante B: { allowDiskUse: true }   --> permite disk spill
db.registros_academicos.aggregate([
  { 
    "$match": {
      "cuatrimestre_info.estado": "activo",
      "fecha_registro": { "$gte": "2026-01-01T00:00:00Z" }
    } 
  },
  { "$sort": { "cuatrimestre_info.promedio_general": -1 } },
  { "$limit": 1000 },
  { 
    "$project": {
      "registro_id": 1,
      "estudiante.matricula": 1,
      "cuatrimestre_info.promedio_general": 1
    } 
  }
], { allowDiskUse: false });
