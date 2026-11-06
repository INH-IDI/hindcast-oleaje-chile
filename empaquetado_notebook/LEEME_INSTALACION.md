# Guía de Instalación y Uso en Notebook y PC (Linux Nativo, Windows y WSL)
## Sistema de Hindcasting y Forecasting de Oleaje en Chile — INH

Este paquete permite ejecutar la aplicación gráfica completa en su computador portátil (**notebook**) o de escritorio, ya sea en **Linux Nativo** (Ubuntu, Debian, Fedora, Arch), **Windows (nativo)** o mediante **WSL (Windows Subsystem for Linux)**.

---

## Contenido del Paquete

```text
empaquetado_notebook/
├── app.py                      # Aplicación gráfica interactiva en Streamlit + Plotly
├── transfer_lib/               # Motor de cálculo y cliente de pronóstico NOAA WW3
├── assets/
│   └── INH.png                 # Logotipo institucional del Instituto Nacional de Hidráulica
├── data/                       # Catálogos de puertos, caletas DOP y boyas
│   ├── sitios_costeros.csv     # 650 sitios predefinidos de la costa de Chile
│   ├── catalogo_boyas_1deg.csv # 28 boyas de aguas profundas cada 1°
│   ├── catalogo_nodos_uv.csv   # 14 nodos de aguas profundas Atlas UV
│   └── (aquí van los .nc pesados)
├── forecast_cache/             # Almacenamiento local de pronósticos NOAA recientes
├── requirements.txt            # Dependencias Python optimizadas para Windows y Linux
├── descargar_datos.py          # Script de verificación y descarga automática de NetCDF
├── iniciar_linux.sh            # Lanzador para Linux Nativo y WSL (Ubuntu, Fedora, Arch)
├── iniciar_windows.bat         # Lanzador de 1 clic para Windows nativo
└── iniciar_wsl_linux.sh        # Lanzador específico para WSL Linux (Ubuntu)
```

---

## Opción A: Ejecutar en Linux Nativo (Desktop / Servidores: Ubuntu, Debian, Fedora, Arch)

### Requisitos previos:
Instalar Python y gestor de paquetes según su distribución:
- **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt update && sudo apt install -y python3 python3-venv python3-pip
  ```
- **Fedora / RHEL / CentOS:**
  ```bash
  sudo dnf install -y python3 python3-pip
  ```
- **Arch Linux / Manjaro:**
  ```bash
  sudo pacman -S python python-pip
  ```

### Pasos de inicio:
1. Abra su terminal en esta carpeta y ejecute:
   ```bash
   bash iniciar_linux.sh
   ```
2. El script automáticamente:
   - Creará un entorno virtual aislado (`.venv`).
   - Instalará las dependencias necesarias (`streamlit`, `plotly`, `netCDF4`, `pandas`, `scipy`, etc.).
   - Verificará los archivos de datos en `data/`.
   - Iniciará el servidor Streamlit en `http://localhost:8501`.
3. Abra su navegador web en `http://localhost:8501`.

---

## Opción B: Ejecutar en Windows Nativo (Sin WSL)

### Requisitos previos:
- Tener instalado **Python 3.10, 3.11 o 3.12** en Windows ([python.org](https://www.python.org/downloads/)).
  > **IMPORTANTE:** Durante la instalación de Python, asegúrese de marcar la casilla **"Add python.exe to PATH"** en la primera pantalla del instalador.

### Pasos de inicio:
1. Haga **doble clic** en el archivo:
   ```cmd
   iniciar_windows.bat
   ```
2. El script automáticamente creará el entorno virtual `.venv`, instalará dependencias, verificará datos y abrirá su navegador web en `http://localhost:8501`.

---

## Opción C: Ejecutar en Windows con WSL (Windows Subsystem for Linux / Ubuntu)

### Requisitos previos:
En su terminal de WSL, asegúrese de tener Python y venv:
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
```

### Pasos de inicio:
1. Abra la terminal en esta carpeta y ejecute:
   ```bash
   bash iniciar_wsl_linux.sh
   ```
2. Abra su navegador en Windows o WSL e ingrese a `http://localhost:8501`.
   ```bash
   bash iniciar_wsl_linux.sh
   ```
2. El script configurará el entorno e iniciará Streamlit.
3. Abra su navegador en Windows o WSL e ingrese a:
   ```text
   http://localhost:8501
   ```

---

## Manejo de las Bases de Datos Pesadas (`.nc`)

Para el cálculo sobre la malla `chile_250k`, el sistema utiliza dos archivos NetCDF pesados dentro de la carpeta `data/`:

| Archivo | Tamaño | Descripción | ¿Es Obligatorio? |
| :--- | :--- | :--- | :--- |
| `data/matriz_transferencia_chile.nc` | ~985 MB | Matriz de transferencia SWAN | **Sí** (requerido para propagación costera) |
| `data/hindcast_ap_1deg_chile.nc` | ~91 MB | Base de datos histórica AP (1980–2015) | **Solo para Hindcasting** (no necesario si solo usa Forecast) |
| `data/hindcast_uv_14nodos.nc` | ~46 MB | Base histórica 14 nodos UV | Opcional |

### ¿Cómo obtener estos archivos en su notebook?

1. **Descarga automática:**
   Ejecute en la terminal (o consola de Windows):
   ```bash
   python descargar_datos.py
   ```
   El script descargará los archivos faltantes desde los Releases oficiales del repositorio en GitHub con barra de progreso.

2. **Copia manual vía Pendrive / Disco / Red local:**
   Si ya tiene los archivos en su computador o en un pendrive, simplemente cópielos directamente dentro de la carpeta `data/` de este paquete:
   ```text
   empaquetado_notebook/data/matriz_transferencia_chile.nc
   empaquetado_notebook/data/hindcast_ap_1deg_chile.nc
   ```

---

## Funcionalidades Disponibles en su Notebook

1. **Forecasting Operacional NOAA WW3 (Tiempo Real):**
   - Descarga automática por internet en segundos desde servidores oficiales de la **NOAA (ERDDAP / NOMADS)**.
   - Permite consultar el pronóstico a 5–6 días en cualquier puerto, caleta o coordenada de Chile.
   - Funciona de forma 100% pura en Python sin requerir compiladores C ni librerías del sistema adicionales.

2. **Hindcasting Histórico (1980–2015):**
   - Consulta instantánea (< 50 ms) de los 36 años de oleaje en cualquier punto de la costa.
   - Exportación de series horarias y tri-horarias en formato `.CSV`.
   - Rosas de oleaje polar y análisis de transformación espectral.

---

## Detener la Aplicación
Para cerrar el servidor, presione `Ctrl + C` en la ventana de la consola o terminal.
