#!/usr/bin/env bash
# ==============================================================================
# Automatización de la Matriz de Mediciones - Playbook IT2iD 2026
# Asignatura: Bases de Datos en la Nube (Universidad Politécnica de Chiapas)
# ==============================================================================

set -e

# Detectar intérprete de Python en el entorno virtual
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_CMD=".venv/Scripts/python.exe"
else
    PYTHON_CMD="python3"
fi

echo "=================================================================="
echo " INICIANDO RUN_BENCHMARKS.SH"
echo " Intérprete Python: $PYTHON_CMD"
echo "=================================================================="

# Delegar la orquestación a run_benchmarks.py pasando todos los argumentos
$PYTHON_CMD run_benchmarks.py "$@"
