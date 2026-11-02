# Hindcasting Rápido de Oleaje en Chile mediante Funciones de Transferencia (`superSimple`)

Sistema de hindcasting rápido de oleaje en aguas someras (AS) para la costa de Chile ($-17.7^\circ\text{S}$ a $-45.0^\circ\text{S}$, hasta Chiloé), basado en **Funciones de Transferencia Espectrales** ($K_a(X, Y, f, \theta_{\text{AP}})$ y $\theta_{\text{AS}}(X, Y, f, \theta_{\text{AP}})$) precalculadas con el modelo **SWAN** sobre la malla no estructurada `chile_250k` ($255\,521$ nodos y $490\,875$ elementos triangulares) y forzado con el **Hindcast de Aguas Profundas (AP) 1980–2015** de la Universidad de Valparaíso (`oleaje.uv.cl`) interpolado a una red de **28 boyas virtuales cada $1^\circ$ de latitud**.

---

## Características Principales

1. **Matriz de Transferencia SWAN (`trabajo_swan/`)**:
   - **333 casos estacionarios de oleaje unitario** ($H_{s,0} = 1.0\,\text{m}$), combinando **9 periodos** ($T \in \{6, 8, 10, 12, 14, 16, 18, 20, 22\}\,\text{s}$, $\Delta T = 2\,\text{s}$) y **37 direcciones** ($\theta_{\text{AP}} \in [180^\circ, 360^\circ]$, $\Delta\theta = 5^\circ$, convención náutica).
   - Almacenamiento consolidado en formato NetCDF4 comprimido (`trabajo_swan/matrices/matriz_transferencia_chile.nc`).
2. **Ponderación Multi-Boya por Distancia y Dirección de Aguas Profundas (`transfer_lib/buoy_weighting.py`)**:
   - Combina múltiples boyas de aguas profundas vecinas (espaciadas cada $1^\circ$ de latitud) asignando pesos dinámicos $\omega_i(t)$ en función de la **distancia geodésica** al punto de interés y la **alineación direccional aguas arriba** respecto a la dirección de procedencia del oleaje $\theta_{\text{AP}}(t)$ (por ejemplo, priorizando la boya Norte cuando el oleaje proviene del Norte y la boya Sur cuando proviene del Sur).
3. **Interpolación Espacial Baricéntrica y Espectral 2D (`transfer_lib/mesh_interpolator.py`)**:
   - Interpolación espacial baricéntrica sobre la triangulación `chile_250k` para cualquier coordenada $(X, Y)$.
   - Interpolación espectral bilineal en $(f = 1/T, \theta_{\text{AP}})$ para $K_a$ y vectorial circular en $(\cos\theta_{\text{AS}}, \sin\theta_{\text{AS}})$ para la dirección en aguas someras, suponiendo invarianza del periodo ($T_{\text{AS}} = T_{\text{AP}}$).
4. **Resolución Horaria ($\Delta t = 1\text{ h}$) y Visualización WebGL (`aplicacion_hindcast/app.py`)**:
   - Cálculo de series históricas completas ($1980\text{–}2015$) con paso horario ($\Delta t = 1\text{ h}$ interpolado o $\Delta t = 3\text{ h}$ nativo UV) y graficación completa sin submuestreo mediante `Plotly Scattergl` en Streamlit.

---

## Estructura del Repositorio

```text
superSimple/
├── aplicacion_hindcast/               # Librería Python, aplicación Streamlit, CLI y pruebas
│   ├── transfer_lib/                  # Paquete principal (motor de hindcasting e interpoladores)
│   │   ├── __init__.py
│   │   ├── buoy_weighting.py          # Ponderación multi-boya por distancia + dirección AP
│   │   ├── catalog.py                 # Catálogo de 25 puertos, 57 nodos y 569 caletas DOP
│   │   ├── hindcast_engine.py         # Motor de hindcasting horario (1h) y tri-horario (3h)
│   │   └── mesh_interpolator.py       # Interpolador espacial baricéntrico y espectral 2D
│   ├── app.py                         # Interfaz gráfica interactiva en Streamlit + Plotly WebGL
│   ├── cli.py                         # Interfaz de línea de comandos (CLI)
│   ├── validate_hindcast.py           # Script de validación y generación de figuras
│   ├── MANUAL_DE_USO.md               # Manual detallado de uso (Web, CLI y API Python)
│   ├── outputs/                       # Figuras de validación y tabla resumen de puertos (1980-2015)
│   └── tests/                         # Suite de pruebas unitarias (pytest)
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

Consulta el [**Manual de Uso Completo (`aplicacion_hindcast/MANUAL_DE_USO.md`)**](aplicacion_hindcast/MANUAL_DE_USO.md) para ejemplos detallados de uso desde scripts Python y Jupyter Notebooks.
