# Sistema de Hindcasting Rápido de Oleaje en Chile (`transfer_lib` + Streamlit App)

Librería y aplicación interactiva para obtener el **Hindcasting de oleaje en aguas someras (AS)** en cualquier coordenada de la costa de Chile ($-17.7^\circ\text{S}$ a $-45.0^\circ\text{S}$) a partir de condiciones de borde en **aguas profundas (AP)** mediante **Matrices de Transferencia** ($K_a$ y Dirección) calculadas con el modelo espectral **SWAN** sobre la malla no estructurada `chile_250k` ($255\,521$ nodos y $501\,598$ triángulos).

## Estructura del Proyecto (`/home/model2/luis/oleaje_chile/superSimple/`)

1. **`datos_ap_uv/`**:
   - `raw/`: Los 14 nodos costeros oficiales descargados de [oleaje.uv.cl/descargas.html](https://oleaje.uv.cl/descargas.html) (`1980–2015`, cada 3 horas).
   - `nodos_1deg/`: Los 28 nodos de aguas profundas espaciados cada $1^\circ$ de latitud ($-18^\circ\text{S}$ a $-45^\circ\text{S}$).
   - `processed/hindcast_ap_1deg_chile.nc` y `processed/hindcast_uv_14nodos.nc`: Bases de datos consolidadas en NetCDF4 de lectura instantánea.

2. **`trabajo_swan/`**:
   - `base/INPUT_template.swn`: Plantilla SWAN estacionaria para propagación de oleaje unitario ($H_s = 1.0\,\text{m}$).
   - `run_swan_matrix.py`: Orquestador paralelo de workers por periodo ($T \in [6..22\,\text{s}]$, $\theta \in [180^\circ..360^\circ]$).
   - `build_transfer_matrix.py`: Ensamblador del tensor maestro `matrices/matriz_transferencia_chile.nc`.
   - `DataSet/`: Archivos `.mat` individuales por combinación $(T_0, \theta_0)$.

3. **`aplicacion_hindcast/`**:
   - `transfer_lib/`: Librería Python modular:
     - `mesh_interpolator.py`: Interpolación espacial baricéntrica en la triangulación `chile_250k` (`cKDTree` + coordenadas baricéntricas) e interpolación espectral 2D en $(f_0, \theta_0)$ con álgebra circular para direcciones.
     - `buoy_weighting.py`: Ponderación multi-boya en función de la distancia geodésica y de la alineación con la dirección de aguas profundas del oleaje ($\theta_{\text{AP}}$).
     - `hindcast_engine.py`: Motor de hindcasting vectorizado ($< 30\,\text{ms}$ para 36 años de datos trihorarios).
     - `catalog.py`: Catálogo de 25 puertos chilenos, 57 puntos de interés y 569 caletas DOP.
   - `app.py`: Interfaz gráfica web en **Streamlit + Plotly**.
   - `cli.py`: Interfaz de línea de comandos.
   - `validate_hindcast.py`: Validación y generación de reportes y figuras en los 25 puertos de Chile.
   - `tests/test_transfer_lib.py`: Pruebas unitarias automatizadas (`pytest`).

## Uso Rápido

### 1. Desde Python (`transfer_lib`)
```python
from transfer_lib import WaveHindcastEngine, WeightingConfig

engine = WaveHindcastEngine(buoy_mode="1deg")
cfg = WeightingConfig(mode="dist_dir", max_buoys=4, dir_gamma=0.85, dir_power=2.0)

res = engine.run_hindcast(
    lon=-71.6145,
    lat=-33.0325,
    site_name="Valparaiso",
    start_date="1980-01-01",
    end_date="2015-12-31",
    weighting_config=cfg,
)
print(res.summary_stats)
print(res.timeseries.head())
```

### 2. Interfaz de Línea de Comandos (CLI)
```bash
/usr/bin/python3 /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/cli.py \
    --site "Valparai" --mode dist_dir --max-buoys 4 --out valparaiso_1980_2015.csv
```

### 3. Aplicación Web Interactiva (Streamlit)
```bash
/home/model2/.local/bin/streamlit run /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/app.py
```
