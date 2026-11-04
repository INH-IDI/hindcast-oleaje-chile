# Sistema de Hindcasting y Forecasting Operacional de Oleaje en Chile (`transfer_lib` + Streamlit App)

Librería y aplicación interactiva para obtener el **Hindcasting histórico** (1980–2015) y el **Forecasting operacional NOAA WW3** (tiempo real a 5–6 días) de oleaje en aguas someras (AS) en cualquier coordenada de la costa de Chile ($-17.7^\circ\text{S}$ a $-45.0^\circ\text{S}$) a partir de condiciones de borde en **aguas profundas (AP)** mediante **Matrices de Transferencia** ($K_a$ y Dirección) calculadas con el modelo espectral **SWAN** sobre la malla no estructurada `chile_250k` ($255\,521$ nodos y $501\,598$ triángulos).

La interfaz gráfica incluye el **logotipo oficial del Instituto Nacional de Hidráulica (INH)** y el aviso legal (**disclaimer**) de uso de datos numéricos.

## Estructura del Proyecto (`aplicacion_hindcast/`)

1. **`transfer_lib/`**: Librería Python modular:
   - `mesh_interpolator.py`: Interpolación espacial baricéntrica en la triangulación `chile_250k` (`cKDTree` + coordenadas baricéntricas) e interpolación espectral 2D en $(f_0, \theta_0)$ con álgebra circular para direcciones.
   - `buoy_weighting.py`: Ponderación multi-boya en función de la distancia geodésica y de la alineación con la dirección de aguas profundas del oleaje ($\theta_{\text{AP}}$).
   - `forecast_engine.py`: Cliente de descarga de pronóstico operacional **NOAA WAVEWATCH III (WW3 / GFS-Wave)** vía servidores oficiales ERDDAP y NOMADS, extracción en la red de boyas AP de Chile y caché local.
   - `hindcast_engine.py`: Motor unificado de simulación (`WaveHindcastEngine`) para Hindcasting histórico y Forecasting operacional.
   - `catalog.py`: Catálogo de 25 puertos chilenos, 57 puntos de interés y 569 caletas DOP.

2. **`assets/`**:
   - `INH.png`: Logotipo institucional del Instituto Nacional de Hidráulica (Ministerio de Obras Públicas - Gobierno de Chile).

3. **`forecast_cache/`**:
   - Almacenamiento local en formato `.npz` de las series de pronóstico de aguas profundas para carga instantánea.

4. **`app.py`**: Interfaz gráfica web interactiva en **Streamlit + Plotly WebGL** con alternancia en vivo entre Hindcast histórico y Pronóstico NOAA.
5. **`cli.py`**: Interfaz de línea de comandos para consultas y exportaciones automatizadas.
6. **`validate_hindcast.py`**: Script de validación con figuras y tablas en los 25 puertos chilenos.
7. **`tests/test_transfer_lib.py`**: Suite de pruebas unitarias automatizadas (`pytest`).

## Uso Rápido

### 1. Desde Python (`transfer_lib`)

#### A. Modo Hindcasting Histórico (1980–2015)
```python
from transfer_lib import WaveHindcastEngine, WeightingConfig

engine = WaveHindcastEngine(mode="hindcast", buoy_mode="1deg")
cfg = WeightingConfig(mode="dist_dir", max_buoys=4, dir_gamma=0.85, dir_power=2.0)

res = engine.run_hindcast(
    lon=-71.6145,
    lat=-33.0325,
    site_name="Valparaiso",
    start_date="1980-01-01",
    end_date="2015-12-31",
    weighting_config=cfg,
)
print("Resumen Hindcast:", res.summary_stats)
print(res.timeseries.head())
```

#### B. Modo Forecasting Operacional NOAA WW3 (Tiempo Real)
```python
from transfer_lib import WaveHindcastEngine, WeightingConfig

# Inicializa con pronóstico en tiempo real descargado de NOAA ERDDAP/NOMADS
engine = WaveHindcastEngine(mode="forecast", buoy_mode="1deg")
res_fc = engine.run_forecast(
    lon=-71.6145,
    lat=-33.0325,
    site_name="Valparaiso",
)
print("Resumen Pronóstico:", res_fc.summary_stats)
print(res_fc.timeseries[["DateTime", "Hm0_AP", "Hm0_AS", "Tp_AS", "Dir_AS", "Ka_eff"]].head())
```

### 2. Interfaz de Línea de Comandos (CLI)
```bash
/usr/bin/python3 aplicacion_hindcast/cli.py \
    --site "Valparai" --mode dist_dir --max-buoys 4 --out valparaiso_1980_2015.csv
```

### 3. Aplicación Web Interactiva (Streamlit)
```bash
streamlit run aplicacion_hindcast/app.py
```
