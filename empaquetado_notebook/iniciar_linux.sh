#!/usr/bin/env bash
# ======================================================================
#  Iniciador para Linux (Nativo y WSL: Ubuntu, Debian, Fedora, Arch)
#  Sistema de Hindcasting y Forecasting de Oleaje en Chile
#  Instituto Nacional de Hidráulica (INH)
# ======================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "======================================================================"
echo "   SISTEMA DE HINDCASTING Y FORECASTING DE OLEAJE EN CHILE"
echo "   Instituto Nacional de Hidráulica (INH)"
echo "   Entorno: Linux (Nativo / WSL)"
echo "======================================================================"
echo ""

# 1. Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 no está instalado en el sistema."
    echo "Instálelo según su distribución:"
    echo "  - Ubuntu / Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "  - Fedora / RHEL:   sudo dnf install -y python3 python3-pip"
    echo "  - Arch Linux:      sudo pacman -S python python-pip"
    exit 1
fi

# 2. Crear entorno virtual si no existe
if [ ! -f ".venv/bin/activate" ]; then
    echo "[1/4] Creando entorno virtual aislado (.venv)..."
    python3 -m venv .venv
fi

# 3. Activar entorno virtual
echo "[2/4] Activando entorno virtual (.venv)..."
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
echo "  Abra en su navegador web: http://localhost:8501"
echo "  Para detener el servidor, presione Ctrl + C."
echo "======================================================================"
echo ""

streamlit run app.py --server.port 8501
