@echo off
setlocal enabledelayedexpansion

:: 0. Asegurar que el directorio de trabajo sea la carpeta del script
cd /d "%~dp0"

title Oleaje Chile - Sistema de Hindcasting y Forecasting NOAA

echo ======================================================================
echo    SISTEMA DE HINDCASTING Y FORECASTING DE OLEAJE EN CHILE
echo    Instituto Nacional de Hidraulica (INH)
echo    Entorno: Windows Nativo
echo ======================================================================
echo.

:: 1. Detectar comando de Python (python en PATH o py launcher de Windows)
set "PY_CMD="
python --version >nul 2>nul
if !ERRORLEVEL! equ 0 (
    set "PY_CMD=python"
) else (
    py -3 --version >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        set "PY_CMD=py -3"
    )
)

if not defined PY_CMD (
    echo [ERROR] No se encontro una instalacion valida de Python en el sistema.
    echo.
    echo Por favor instale Python 3.10, 3.11 o 3.12 desde:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: En la primera pantalla del instalador, marque la casilla:
    echo   [X] "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

:: 2. Crear entorno virtual si no existe
if not exist ".venv\Scripts\activate.bat" (
    echo [1/4] Creando entorno virtual aislado (.venv)...
    !PY_CMD! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        echo Verifique que cuenta con permisos de escritura en esta carpeta.
        pause
        exit /b 1
    )
)

:: 3. Activar entorno virtual
echo [2/4] Activando entorno virtual (.venv)...
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] No se encontro el archivo de activacion .venv\Scripts\activate.bat
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"

:: 4. Instalar o actualizar dependencias dentro del entorno virtual
echo [3/4] Verificando dependencias (Streamlit, Plotly, NetCDF4, Scipy, etc.)...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    echo Verifique su conexion a internet.
    pause
    exit /b 1
)

:: 5. Verificar bases de datos NetCDF
echo [4/4] Verificando bases de datos NetCDF en carpeta 'data'...
python descargar_datos.py

:: 6. Iniciar la aplicacion Streamlit
echo.
echo ======================================================================
echo  Iniciando servidor Streamlit...
echo  Abriendo navegador web en: http://localhost:8501
echo  Para detener la aplicacion, presione Ctrl + C en esta ventana.
echo ======================================================================
echo.

python -m streamlit run app.py --server.port 8501

pause
