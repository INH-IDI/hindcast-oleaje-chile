# Instrucciones Operativas: Sistema de Oleaje Chile (Hindcast & Forecast)
### Instituto Nacional de Hidráulica (INH) — Ministerio de Obras Públicas

Este documento reúne todas las instrucciones de uso, actualización de pronósticos de la NOAA, empaquetamiento y despliegue en computadores portátiles (**notebooks** con Windows nativo o WSL Linux).

---

## 1. Instrucción de Ejecución en Servidor o Máquina Principal

Para iniciar la aplicación gráfica completa:

```bash
streamlit run aplicacion_hindcast/app.py --server.port 8501
```

La aplicación abrirá la interfaz en `http://localhost:8501` mostrando:
- **Cabecera Institucional:** Logotipo oficial del INH y título adaptativo.
- **Pie de página:** Aviso legal (*disclaimer*) que indica que los datos son aproximaciones numéricas bajo propio riesgo.

---

## 2. Instrucción de Uso de la Interfaz Gráfica

En el panel lateral izquierdo (**Sidebar**), seleccione el modo de trabajo deseado:

### Modo A: ⏳ Hindcasting Histórico (1980 – 2015)
1. **Ubicación costera:** Seleccione un puerto (25 puertos), nodo de interés (57 sitios) o caleta DOP (569 caletas) del catálogo, o ingrese coordenadas `(Lon, Lat)`.
2. **Boyas de Aguas Profundas:** Elija entre la red de 28 boyas cada 1° (`1deg`) o 14 nodos Atlas UV (`uv14`).
3. **Ponderación:** Se recomienda `Distancia + Dirección AP` para considerar el efecto aguas arriba de la procedencia del oleaje.
4. **Fechas:** Defina el rango de años entre 1980 y 2015 y la resolución temporal (1 hora o 3 horas).
5. **Resultados:** En la pestaña **4** visualice la serie temporal multivariable y descargue el archivo `.CSV` correspondiente.

### Modo B: 🔮 Forecasting Operacional NOAA WW3 (Tiempo Real)
1. **Ubicación costera:** Seleccione el puerto, caleta o coordenada donde desea pronosticar el oleaje.
2. **Servidor NOAA:**
   - `NOAA ERDDAP (WW3 Global)`: Recomendado por velocidad y descarga directa de parámetros espectrales ($H_{m0}, T_p, \text{Dir}$).
   - `NOAA NOMADS (GFS-Wave)`: Alternativa oficial directa por filtrado GRIB2.
3. **Horizonte de Pronóstico:** Seleccione entre 24h, 48h, 72h, 120h (5 días) o todo el pronóstico disponible (~6 días).
4. **Resolución:** Paso de 3 horas (nativo NOAA WW3) o 1 hora (interpolado horario).
5. **Actualización:** Presione el botón **`🔄 Actualizar Pronóstico NOAA`** si desea forzar una consulta fresca a los servidores en la nube.
6. **Resultados:** En la pestaña **4** analice la serie de tiempo pronosticada, la tabla horaria y descargue el archivo `forecast_AS_...csv`.

---

## 3. Instrucción de Empaquetamiento para Notebook (Windows y WSL Linux)

Para generar el paquete portátil distribuible:

1. Ejecute el script de empaquetamiento:
   ```bash
   python3 empaquetar.py --zip
   ```
2. El script generará:
   - La carpeta autónoma: [`empaquetado_notebook/`](empaquetado_notebook/)
   - El archivo comprimido liviano listo para transferir: **`oleaje_chile_notebook.zip`** (~80 KB).
3. Transfiera `oleaje_chile_notebook.zip` (o la carpeta `empaquetado_notebook/`) a su notebook mediante pendrive, correo, OneDrive o red local.

---

## 4. Instrucción de Instalación y Ejecución en el Notebook o PC

Una vez descomprimido el paquete en el notebook o computador de destino:

### En Linux Nativo (Ubuntu, Debian, Fedora, Arch):
1. Asegúrese de tener Python 3 y venv (`sudo apt install python3-venv`, `sudo dnf install python3`, etc.).
2. En la terminal dentro de la carpeta del paquete, ejecute:
   ```bash
   bash iniciar_linux.sh
   ```
3. El script creará `.venv`, instalará dependencias, verificará datos y levantará Streamlit en `http://localhost:8501`.

### En Windows Nativo (Sin WSL):
1. Asegúrese de tener instalado Python 3.10 o superior (con la opción *"Add python.exe to PATH"* marcada al instalar).
2. Haga doble clic en el archivo:
   ```cmd
   iniciar_windows.bat
   ```
3. El script creará automáticamente el entorno virtual `.venv`, instalará las dependencias necesarias de `requirements.txt`, verificará las bases de datos y abrirá el navegador en `http://localhost:8501`.

### En WSL Linux (Ubuntu / Debian en Windows):
1. Abra la terminal en la carpeta del paquete y ejecute:
   ```bash
   bash iniciar_wsl_linux.sh
   ```
2. Ingrese desde su navegador en Windows o WSL a `http://localhost:8501`.

---

## 5. Instrucción de Manejo de Bases de Datos NetCDF (`data/`)

El modelo costero requiere archivos NetCDF pesados dentro de la carpeta `data/`:

| Archivo | Tamaño | Propósito | Requerimiento |
| :--- | :--- | :--- | :--- |
| `matriz_transferencia_chile.nc` | ~985 MB | Matriz de transferencia SWAN `chile_250k` | **Obligatorio** para propagación costera |
| `hindcast_ap_1deg_chile.nc` | ~91 MB | Serie histórica de aguas profundas (1980–2015) | **Solo requerido si usa Hindcasting** |
| `hindcast_uv_14nodos.nc` | ~46 MB | Nodos originales del Atlas UV | Opcional |

### ¿Cómo obtener estos archivos en el notebook?
- **Descarga automática:** En la consola de Windows o terminal WSL ejecute:
  ```bash
  python descargar_datos.py
  ```
  El script descargará con barra de progreso los archivos faltantes desde los *Releases* oficiales de GitHub.
- **Copia manual:** Si ya tiene los archivos en disco o pendrive, cópielos directamente en la subcarpeta `data/` del paquete.

> [!TIP]
> Si en su notebook **solo utilizará el modo Forecasting (Pronóstico NOAA WW3)**, no necesita descargar la base histórica de 91 MB; el pronóstico se descarga automáticamente en vivo desde los servidores de la NOAA.

---

## 6. Instrucción de Uso Programático en Scripts Python

```python
from transfer_lib import WaveHindcastEngine, WeightingConfig

# A. Para ejecutar Pronóstico Operacional NOAA WW3:
engine_fc = WaveHindcastEngine(mode="forecast", buoy_mode="1deg")
res_fc = engine_fc.run_forecast(
    lon=-71.6145,
    lat=-33.0325,
    site_name="Valparaiso",
)
print("Pronóstico en costa:")
print(res_fc.timeseries[["DateTime", "Hm0_AP", "Hm0_AS", "Tp_AS", "Dir_AS", "Ka_eff"]].head())

# B. Para ejecutar Hindcasting Histórico:
engine_hc = WaveHindcastEngine(mode="hindcast", buoy_mode="1deg")
res_hc = engine_hc.run_hindcast(
    lon=-71.6145,
    lat=-33.0325,
    site_name="Valparaiso",
    start_date="2010-01-01",
    end_date="2015-12-31",
)
print("Resumen histórico:", res_hc.summary_stats)
```
