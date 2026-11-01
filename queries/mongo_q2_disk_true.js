// Consulta Q2 - Massive Sort & Top-K con allowDiskUse: true
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
], { allowDiskUse: true });
