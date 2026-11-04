@echo off
setlocal enabledelayedexpansion
title Oleaje Chile - Sistema de Hindcasting y Forecasting NOAA

echo ======================================================================
echo    SISTEMA DE HINDCASTING Y FORECASTING DE OLEAJE EN CHILE
echo    Instituto Nacional de Hidraulica (INH)
echo ======================================================================
echo.

:: 1. Verificar instalacion de Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] No se encontro Python en el sistema.
    echo Por favor instale Python 3.10, 3.11 o 3.12 desde https://www.python.org/
    echo Asegurese de marcar la casilla "Add python.exe to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

:: 2. Crear entorno virtual si no existe
if not exist ".venv\Scripts\activate.bat" (
    echo [1/4] Creando entorno virtual Python (.venv)...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

:: 3. Activar entorno virtual
echo [2/4] Activando entorno virtual (.venv)...
call .venv\Scripts\activate.bat

:: 4. Instalar o actualizar dependencias
echo [3/4] Verificando dependencias (Streamlit, Plotly, NetCDF4, etc.)...
python -m pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

:: 5. Verificar bases de datos NetCDF
echo [4/4] Verificando bases de datos NetCDF en carpeta 'data'...
python descargar_datos.py

:: 6. Iniciar Streamlit App
echo.
echo ======================================================================
echo  Iniciando servidor Streamlit...
echo  Se abrira automaticamente su navegador web en http://localhost:8501
echo  Para detener la aplicacion, presione Ctrl + C en esta ventana.
echo ======================================================================
echo.

streamlit run app.py --server.port 8501

pause
