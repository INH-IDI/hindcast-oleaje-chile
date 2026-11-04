#!/usr/bin/env bash
# ======================================================================
#  Iniciador para WSL Linux / Ubuntu / Debian - Oleaje Chile
#  Instituto Nacional de Hidráulica (INH)
# ======================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "======================================================================"
echo "   SISTEMA DE HINDCASTING Y FORECASTING DE OLEAJE EN CHILE"
echo "   Instituto Nacional de Hidráulica (INH)"
echo "   Entorno: WSL Linux / Ubuntu"
echo "======================================================================"
echo ""

# 1. Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 no está instalado."
    echo "Instálelo en su terminal WSL con: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

# 2. Crear entorno virtual si no existe
if [ ! -f ".venv/bin/activate" ]; then
    echo "[1/4] Creando entorno virtual (.venv)..."
    python3 -m venv .venv
fi

# 3. Activar entorno virtual
echo "[2/4] Activando entorno virtual..."
source .venv/bin/activate

# 4. Instalar dependencias
echo "[3/4] Instalando / verificando dependencias (Streamlit, Plotly, NetCDF4)..."
pip install --upgrade pip > /dev/null 2>&1 || true
pip install -r requirements.txt

# 5. Verificar bases de datos
echo "[4/4] Verificando bases de datos NetCDF en 'data/'..."
python3 descargar_datos.py

# 6. Ejecutar Streamlit
echo ""
echo "======================================================================"
echo "  Iniciando Streamlit..."
echo "  Abra en su navegador (Windows o WSL): http://localhost:8501"
echo "  Para detener, presione Ctrl + C."
echo "======================================================================"
echo ""

streamlit run app.py --server.port 8501 --server.headless true
