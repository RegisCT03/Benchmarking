// Consulta Q1 - Unwind, Filter & Grouping (Saturación de CPU)
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
