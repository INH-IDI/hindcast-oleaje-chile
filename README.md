# Modelación Rápida de Oleaje en Chile: Hindcasting & Forecasting (`superSimple`)

Sistema integrado de **Hindcasting histórico** (1980–2015) y **Forecasting operacional** (pronóstico en tiempo real a 5–6 días) de oleaje en aguas someras (AS) para la costa de Chile ($-17.7^\circ\text{S}$ a $-45.0^\circ\text{S}$), basado en **Funciones de Transferencia Espectrales** ($K_a$ y Dirección) precalculadas con el modelo espectral **SWAN** sobre la malla no estructurada `chile_250k` ($255\,521$ nodos y $490\,875$ elementos triangulares).

El sistema permite alternar en una misma interfaz gráfica y API entre:
1. **Hindcasting Histórico (1980–2015):** Forzado con la base de datos de Aguas Profundas (AP) de la Universidad de Valparaíso (`oleaje.uv.cl`) sobre una red de **28 boyas virtuales cada $1^\circ$ de latitud** (o 14 nodos Atlas UV).
2. **Forecasting Operacional NOAA WW3 (Tiempo Real):** Forzado con el modelo global **WAVEWATCH III (WW3 / GFS-Wave)** descargado directamente de servidores oficiales de la **NOAA** (ERDDAP / NOMADS) en los nodos de aguas profundas del borde chileno.

---

## Características Principales

1. **Matriz de Transferencia SWAN (`trabajo_swan/`)**:
   - **333 casos estacionarios de oleaje unitario** ($H_{s,0} = 1.0\,\text{m}$), combinando **9 periodos** ($T \in \{6, 8, 10, 12, 14, 16, 18, 20, 22\}\,\text{s}$, $\Delta T = 2\,\text{s}$) y **37 direcciones** ($\theta \in [180^\circ, 360^\circ]$, $\Delta\theta = 5^\circ$, convención náutica).
   - Almacenamiento consolidado en formato NetCDF4 comprimido (`trabajo_swan/matrices/matriz_transferencia_chile.nc`).
2. **Forecasting Operacional en Tiempo Real NOAA WW3 (`transfer_lib/forecast_engine.py`)**:
   - Descarga automatizada de parámetros espectrales de aguas profundas ($H_{m0}$, $T_p$, $\text{Dir}$) desde servidores **NOAA ERDDAP** (`ww3_global`) y **NOAA NOMADS** (`filter_gfswave.pl`).
   - Mapeo y extracción en todos los nodos de aguas profundas chilenos ($-18^\circ\text{S}$ a $-45^\circ\text{S}$) y caché local inteligente con botón de actualización en vivo (`🔄 Actualizar Pronóstico NOAA`).
3. **Ponderación Multi-Boya por Distancia y Dirección de Aguas Profundas (`transfer_lib/buoy_weighting.py`)**:
   - Combina múltiples boyas de aguas profundas vecinas asignando pesos dinámicos $\omega_i(t)$ en función de la **distancia geodésica** al punto de interés y la **alineación direccional aguas arriba** respecto a la dirección de procedencia del oleaje $\theta(t)$ (priorizando la boya Norte cuando el oleaje proviene del Norte y la boya Sur cuando proviene del Sur).
4. **Interpolación Espacial Baricéntrica y Espectral 2D (`transfer_lib/mesh_interpolator.py`)**:
   - Interpolación espacial baricéntrica sobre la triangulación `chile_250k` para cualquier coordenada $(X, Y)$ en la costa de Chile.
   - Interpolación espectral bilineal en $(f = 1/T, \theta)$ para $K_a$ y vectorial circular para la dirección en aguas someras.
5. **Interfaz Interactiva WebGL, Identidad INH y Descarga CSV (`aplicacion_hindcast/app.py`)**:
   - Aplicación en Streamlit + Plotly WebGL (`Scattergl`) con selector de modo (Hindcasting vs Forecasting), catálogo de 25 puertos, 57 nodos de interés y 569 caletas DOP.
   - Incluye el **logo oficial del Instituto Nacional de Hidráulica (INH)** y **aviso legal (disclaimer)** de uso de datos numéricos.

---

## Estructura del Repositorio

```text
superSimple/
├── aplicacion_hindcast/               # Librería Python, aplicación Streamlit, CLI y pruebas
│   ├── transfer_lib/                  # Paquete principal (motores de cálculo e interpoladores)
│   │   ├── __init__.py
│   │   ├── buoy_weighting.py          # Ponderación multi-boya por distancia + dirección AP
│   │   ├── catalog.py                 # Catálogo de 25 puertos, 57 nodos y 569 caletas DOP
│   │   ├── forecast_engine.py         # Cliente de pronóstico NOAA WW3 (ERDDAP/NOMADS) y caché
│   │   ├── hindcast_engine.py         # Motor de simulación para Hindcasting y Forecasting
│   │   └── mesh_interpolator.py       # Interpolador espacial baricéntrico y espectral 2D
│   ├── assets/                        # Recursos visuales (logotipo INH.png)
│   ├── forecast_cache/                # Caché local de pronósticos descargados de NOAA
│   ├── app.py                         # Interfaz gráfica interactiva en Streamlit + Plotly WebGL
│   ├── cli.py                         # Interfaz de línea de comandos (CLI)
│   ├── validate_hindcast.py           # Script de validación y generación de figuras
│   ├── MANUAL_DE_USO.md               # Manual detallado de uso (Web, CLI y API Python)
│   ├── outputs/                       # Figuras de validación y tabla resumen de puertos
│   └── tests/                         # Suite de pruebas unitarias automatizadas (pytest)
├── trabajo_swan/                      # Generación de casos unitarios y ensamblaje de matrices SWAN
│   ├── base/INPUT_template.swn        # Plantilla SWAN estacionaria multi-caso
│   ├── run_swan_matrix.py             # Orquestador paralelo de las 333 corridas SWAN
│   ├── build_transfer_matrix.py       # Ensamblador de los 333 .mat a NetCDF4
│   └── casos_catalogo.csv             # Catálogo de los 333 estados de mar unitarios
├── datos_ap_uv/                       # Descarga y grilla 1° de datos de Aguas Profundas (oleaje.uv.cl)
│   ├── download_uv_hindcast.py        # Descargador oficial UV + interpolador espacial a boyas cada 1°
│   ├── catalogo_nodos_uv.csv          # Coordenadas de los 14 nodos originales UV
│   └── catalogo_boyas_1deg.csv        # Coordenadas de las 28 boyas virtuales cada 1° (-18°S a -45°S)
└── modelo_pronostico/                 # Malla no estructurada chile_250k (.node, .ele, .bot) y catálogos
```

---

## Descarga de Bases de Datos Precalculadas (GitHub Releases)

Los archivos binarios NetCDF4 de gran tamaño se encuentran publicados en la sección **[Releases](../../releases)** de este repositorio y pueden descargarse en sus carpetas correspondientes con `gh`:

```bash
# 1. Descargar las bases de datos NetCDF4 desde el Release v1.0.0
mkdir -p trabajo_swan/matrices datos_ap_uv/processed
gh release download v1.0.0 -D .

# Mover cada archivo a su ruta esperada
mv matriz_transferencia_chile.nc trabajo_swan/matrices/
mv hindcast_ap_1deg_chile.nc datos_ap_uv/processed/
mv hindcast_uv_14nodos.nc datos_ap_uv/processed/
```

Alternativamente, para regenerar los datos de aguas profundas desde `https://oleaje.uv.cl/descargas.html`:

```bash
python3 datos_ap_uv/download_uv_hindcast.py
```

---

## Inicio Rápido

### 1. Interfaz Gráfica Web (Streamlit)

```bash
streamlit run aplicacion_hindcast/app.py --server.port 8501
```
En la barra lateral se puede alternar entre:
- **⏳ Hindcasting Histórico (1980 - 2015)**
- **🔮 Forecasting Operacional NOAA WW3 (Tiempo Real)**

### 2. Línea de Comandos (CLI)

```bash
python3 aplicacion_hindcast/cli.py \
    --site "San_Anto" \
    --start 2006-01-01 \
    --end 2015-12-31 \
    --dt-hours 1 \
    --mode dist_dir \
    --max-buoys 4 \
    --out san_antonio_10yr_1h.csv
```

### 3. Librería Python (`transfer_lib`)

```python
from transfer_lib import WaveHindcastEngine, WeightingConfig

# 1. Modo Hindcasting Histórico:
engine_hindcast = WaveHindcastEngine(mode="hindcast", buoy_mode="1deg")
res_h = engine_hindcast.run_hindcast(
    lon=-71.6145, lat=-33.0325, site_name="Valparaiso",
    start_date="2010-01-01", end_date="2015-12-31"
)

# 2. Modo Forecasting Operacional (NOAA WW3):
engine_forecast = WaveHindcastEngine(mode="forecast", buoy_mode="1deg")
res_f = engine_forecast.run_forecast(
    lon=-71.6145, lat=-33.0325, site_name="Valparaiso"
)
print("Pronóstico en costa (Hm0, Tp, Dir):")
print(res_f.timeseries[["DateTime", "Hm0_AS", "Tp_AS", "Dir_AS", "Ka_eff"]].head())
```

Consulta el [**Manual de Uso Completo (`aplicacion_hindcast/MANUAL_DE_USO.md`)**](aplicacion_hindcast/MANUAL_DE_USO.md) para detalles completos de configuración, opciones de servidores NOAA y fórmulas matemáticas.
