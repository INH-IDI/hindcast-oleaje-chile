# Manual de Uso: Sistema de Hindcasting Rápido de Oleaje en Chile (`transfer_lib`)

Este manual describe cómo utilizar la librería Python, la interfaz de línea de comandos (CLI) y la aplicación web interactiva para obtener series históricas de oleaje en aguas someras (AS) y funciones de transferencia en cualquier punto de la costa de Chile ($-17.7^\circ\text{S}$ a $-45.0^\circ\text{S}$).

---

## 1. Estructura de Archivos del Proyecto

Ruta raíz: `/home/model2/luis/oleaje_chile/superSimple/`

| Carpeta / Archivo | Descripción |
| :--- | :--- |
| `datos_ap_uv/processed/hindcast_ap_1deg_chile.nc` | Base de datos de Aguas Profundas (AP) con **28 boyas cada $1^\circ$ de latitud** ($-18^\circ\text{S}$ a $-45^\circ\text{S}$, $1980\text{–}2015$, resolución 3 h). |
| `datos_ap_uv/processed/hindcast_uv_14nodos.nc` | Base de datos oficial descargada de `oleaje.uv.cl` (**14 nodos cada $2^\circ$**, $1980\text{–}2015$). |
| `trabajo_swan/matrices/matriz_transferencia_chile.nc` | Matriz de transferencia consolidada ($9\text{ periodos} \times 37\text{ direcciones} \times 255\,521\text{ nodos}$) generada con SWAN sobre `chile_250k`. |
| `trabajo_swan/DataSet/` | Los 333 archivos `.mat` individuales de cada corrida estacionaria unitaria ($H_s = 1.0\,\text{m}$). |
| `aplicacion_hindcast/transfer_lib/` | Librería Python principal (`WaveHindcastEngine`, `TransferMatrixDB`, `MultiBuoyWeighter`). |
| `aplicacion_hindcast/app.py` | Aplicación web interactiva en **Streamlit + Plotly**. |
| `aplicacion_hindcast/cli.py` | Interfaz de línea de comandos (CLI) para consultas y exportación rápida. |

---

## 2. Uso de la Interfaz Gráfica Web (Streamlit)

Para iniciar la aplicación interactiva en el navegador:

```bash
/home/model2/.local/bin/streamlit run /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/app.py --server.port 8501
```

### Flujo de trabajo en la interfaz:
1. **Panel lateral izquierdo**:
   - **Selección de punto**: Elige un sitio del catálogo (`Puerto` [25 puertos], `Nodo_Interes` [57 sitios] o `Caleta_DOP` [569 caletas de Chile]) o ingresa manualmente las coordenadas `(Longitud, Latitud)`.
   - **Boyas de Aguas Profundas**: Elige entre la grilla de 28 boyas cada $1^\circ$ (`1deg`) o los 14 nodos originales UV (`uv14`), y selecciona el esquema de ponderación:
     - `Distancia + Dirección AP (Recomendado)`: pondera cada boya según su cercanía y si se ubica aguas arriba de la dirección de procedencia de la ola ($\theta_{\text{AP}}$).
     - `Inverso de la Distancia (IDW)`: pesos fijos sólo por distancia.
     - `Boya única más cercana`: usa 100% la boya más próxima.
   - **Parámetros y fechas**: Selecciona el periodo de referencia (`Tp`, `Tm`, `Tz`, `Te`), la dirección (`Dm`, `Dp`), la resolución temporal (**`1 hora (Interpolado horario)`** por defecto o `3 horas (Nativo UV)`) y el rango de años ($1980\text{–}2015$).
2. **Pestañas de resultados**:
   - **Pestaña 1 (Ubicación y Malla)**: Mapa regional con las boyas activas y sus pesos, junto con un zoom a los nodos y triángulos de la malla `chile_250k` donde se realiza la interpolación baricéntrica.
   - **Pestaña 2 (Matrices de Transferencia)**: Mapas de calor de $K_a(T, \theta_{\text{AP}})$ y $\text{Dir}_{\text{AS}}(T, \theta_{\text{AP}})$, más una calculadora puntual en vivo.
   - **Pestaña 3 (Ponderación Multi-Boya)**: Curvas $\omega_i(\theta_{\text{AP}})$ mostrando cómo varía el peso de las boyas Norte y Sur según la dirección del oleaje incidente.
   - **Pestaña 4 (Hindcasting y Clima)**: Series de tiempo completas renderizadas con WebGL (`Scattergl`, sin submuestreo visual), rosas de oleaje y botón para descargar la serie completa en formato `.CSV`.

---

## 3. Uso desde Línea de Comandos (CLI)

El script `cli.py` permite generar series de hindcasting directamente desde la terminal:

### A. Listar los sitios costeros disponibles en el catálogo
```bash
/usr/bin/python3 /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/cli.py --list-sites
```

### B. Ejecutar Hindcasting para un puerto o caleta por nombre
```bash
/usr/bin/python3 /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/cli.py \
    --site "San_Anto" \
    --start 2000-01-01 \
    --end 2015-12-31 \
    --mode dist_dir \
    --max-buoys 4 \
    --out san_antonio_2000_2015.csv
```

### C. Ejecutar Hindcasting para una coordenada `(Lon, Lat)` cualquiera
```bash
/usr/bin/python3 /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/cli.py \
    --lon -71.5558 \
    --lat -32.9975 \
    --buoy-grid 1deg \
    --mode dist_dir \
    --period-var Tp \
    --dir-var Dm \
    --out viña_del_mar_hindcast.csv
```

---

## 4. Uso de la Librería en Python (`transfer_lib`)

Para integrar la librería en tus propios scripts o Jupyter Notebooks, agrega `aplicacion_hindcast` al `sys.path`:

### Caso 1: Obtener la serie de Hindcasting completa (1980–2015) en un punto `(X, Y)`
```python
import sys
sys.path.insert(0, "/home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast")

from transfer_lib import WaveHindcastEngine, WeightingConfig

# 1. Inicializar motor (buoy_mode='1deg' para 28 boyas cada 1°, o 'uv14' para los 14 nodos UV)
engine = WaveHindcastEngine(buoy_mode="1deg")

# 2. Configurar ponderación multi-boya (Distancia + Dirección AP)
cfg = WeightingConfig(
    mode="dist_dir",      # 'dist_dir', 'idw' o 'nearest'
    max_buoys=4,          # Número de boyas vecinas a combinar
    dist_power=2.0,       # Exponente de decaimiento por distancia
    dir_gamma=0.85,       # Sensibilidad direccional [0..0.95]
    dir_power=2.0,        # Exponente de alineación direccional
)

# 3. Ejecutar hindcasting en cualquier coordenada (ej. Coquimbo)
res = engine.run_hindcast(
    lon=-71.3260,
    lat=-29.9353,
    site_name="Coquimbo",
    start_date="1980-01-01",
    end_date="2015-12-31",
    period_var="Tp",
    dir_var="Dm",
    weighting_config=cfg,
)

# DataFrame con columnas: DateTime, Hm0_AS, Tp_AS, Tm_AS, Tz_AS, Dir_AS, Ka_eff, Hm0_AP, Dir_AP y pesos w_*
df = res.timeseries
print(df.head())
print("Estadísticas climáticas:", res.summary_stats)
```

### Caso 2: Usar sólo la Matriz de Transferencia con condiciones de borde propias
Si tienes tus propios datos de aguas profundas (por ejemplo, de una boya o de otro modelo como ERA5/WW3) y quieres interpolar $K_a$ y $\text{Dir}_{\text{AS}}$ en un punto costero `(lon, lat)`:

```python
import numpy as np
from pathlib import Path
from transfer_lib import TransferMatrixDB

# 1. Cargar la base de datos de transferencia
nc_path = Path("/home/model2/luis/oleaje_chile/superSimple/trabajo_swan/matrices/matriz_transferencia_chile.nc")
db = TransferMatrixDB(nc_path)

# 2. Extraer la función de transferencia local interpolada en (lon, lat)
tf_local = db.get_local_transfer_function(lon_q=-73.1549, lat_q=-36.7360)  # San Vicente

# Matrices discretas (9 periodos x 37 direcciones) en el punto:
print("Periodos (s):", tf_local.periods)
print("Direcciones (°):", tf_local.directions)
print("Matriz Ka shape:", tf_local.ka_matrix.shape)

# 3. Interpolar para cualquier serie o estado de mar arbitrario en AP:
hm0_ap = np.array([2.0, 3.5, 4.2])
tp_ap  = np.array([10.5, 14.2, 16.8])
dir_ap = np.array([225.0, 270.0, 320.0])

out = tf_local.evaluate(periods_ap=tp_ap, dirs_ap=dir_ap, hm0_ap=hm0_ap)
print("Coeficientes Ka :", out["Ka"])
print("Hm0 en costa (m):", out["Hm0_AS"])
print("Periodo AS (s)  :", out["T_AS"])
print("Dir en costa (°):", out["Dir_AS"])
```

---

## 5. Re-ejecución o Ampliación de Casos en SWAN (`trabajo_swan/`)

Si en el futuro deseas agregar más periodos o cambiar la resolución angular en SWAN:

1. **Ejecutar los workers paralelos de SWAN**:
   ```bash
   /usr/bin/python3 /home/model2/luis/oleaje_chile/superSimple/trabajo_swan/run_swan_matrix.py \
       --tmin 6.0 --tmax 22.0 --dt 2.0 \
       --dmin 180.0 --dmax 360.0 --ddir 5.0 \
       --mxitst 10 --threads 3
   ```
2. **Re-ensamblar el archivo maestro NetCDF4**:
   ```bash
   /usr/bin/python3 /home/model2/luis/oleaje_chile/superSimple/trabajo_swan/build_transfer_matrix.py
   ```
