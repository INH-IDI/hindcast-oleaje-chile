"""
Aplicación Interactiva de Hindcasting Rápido de Oleaje en Chile
mediante Funciones de Transferencia (SWAN chile_250k) y Boyas de Aguas Profundas (Atlas UV / Grilla 1°).

Ejecución:
  streamlit run /home/model2/luis/oleaje_chile/superSimple/aplicacion_hindcast/app.py
"""

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from transfer_lib import (
    WaveHindcastEngine,
    WeightingConfig,
    MultiBuoyWeighter,
    load_coastal_sites,
    NOAAWaveForecastClient,
    DeepWaterForecastDB,
)

st.set_page_config(
    page_title="Oleaje Chile - Hindcasting & Forecasting NOAA WW3",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_hindcast_engine(buoy_mode: str) -> WaveHindcastEngine:
    return WaveHindcastEngine(buoy_mode=buoy_mode, mode="hindcast")


def get_forecast_engine(buoy_mode: str, server: str, force_refresh: bool = False) -> WaveHindcastEngine:
    srv_key = "nomads" if "nomads" in server.lower() else "erddap"
    return WaveHindcastEngine(
        buoy_mode=buoy_mode,
        mode="forecast",
        forecast_server=srv_key,
        force_refresh_forecast=force_refresh,
    )


@st.cache_data
def get_sites_catalog() -> pd.DataFrame:
    return load_coastal_sites()


def build_wave_rose(df: pd.DataFrame, hm0_col: str, dir_col: str, title: str) -> go.Figure:
    """Construye una rosa de oleaje polar agrupada por sectores direccionales de 15° y rangos de Hm0."""
    dirs = df[dir_col].to_numpy() % 360.0
    hs = df[hm0_col].to_numpy()

    sector_width = 15.0
    sector_centers = np.arange(0.0, 360.0, sector_width)
    sector_idx = (np.floor(((dirs + sector_width / 2.0) % 360.0) / sector_width)).astype(int)

    bins = [0.0, 1.0, 2.0, 3.0, 4.0, 100.0]
    labels = ["0 - 1 m", "1 - 2 m", "2 - 3 m", "3 - 4 m", "> 4 m"]
    colors = ["#2b83ba", "#abdda4", "#ffffbf", "#fdae61", "#d7191c"]

    n_total = max(1, len(hs))
    fig = go.Figure()

    for b_i in range(len(bins) - 1):
        mask_h = (hs >= bins[b_i]) & (hs < bins[b_i + 1])
        counts = np.bincount(sector_idx[mask_h], minlength=len(sector_centers))
        freq_pct = (counts / n_total) * 100.0
        fig.add_trace(
            go.Barpolar(
                r=freq_pct,
                theta=sector_centers,
                width=[sector_width * 0.9] * len(sector_centers),
                name=labels[b_i],
                marker_color=colors[b_i],
                marker_line_color="black",
                marker_line_width=0.4,
            )
        )

    fig.update_layout(
        title=title,
        template="plotly_white",
        polar=dict(
            angularaxis=dict(direction="clockwise", rotation=90, dtick=45),
            radialaxis=dict(ticksuffix="%", angle=45),
        ),
        legend=dict(orientation="h", y=-0.15),
        height=430,
        margin=dict(l=30, r=30, t=50, b=50),
    )
    return fig


LOGO_INH = APP_DIR / "assets" / "INH.png"

DISCLAIMER_TEXT = (
    "**Aviso legal (disclaimer):** Los datos presentados en esta aplicación (tanto de hindcasting histórico "
    "como de pronóstico operacional NOAA WW3) son **aproximaciones** obtenidas mediante modelación numérica "
    "y funciones de transferencia espectral, por lo que pueden diferir de las condiciones reales de oleaje. "
    "Su uso es **bajo su propio riesgo**; el Instituto Nacional de Hidráulica no se hace responsable por decisiones "
    "operacionales, de navegación o daños derivados de su utilización."
)


def render_disclaimer():
    st.divider()
    st.caption(DISCLAIMER_TEXT)


def main():
    sites_df = get_sites_catalog()

    # ================= BARRA LATERAL =================
    with st.sidebar:
        st.header("Modo de Operación")
        sim_mode = st.radio(
            "Seleccione el modo:",
            [
                "⏳ Hindcasting Histórico (1980 - 2015)",
                "🔮 Forecasting Operacional NOAA WW3 (Tiempo Real)",
            ],
            index=0,
        )
        is_forecast = "Forecasting" in sim_mode

        st.divider()
        st.header("1. Selección de Punto Costero")
        sel_mode = st.radio(
            "Modo de ubicación:",
            ["Catálogo (Puertos / Caletas DOP)", "Coordenadas (Lon, Lat)"],
            index=0,
        )

        if sel_mode.startswith("Catálogo") and not sites_df.empty:
            cat_options = sorted(sites_df["category"].unique())
            default_cat = "Puerto" if "Puerto" in cat_options else cat_options[0]
            chosen_cat = st.selectbox("Categoría:", cat_options, index=cat_options.index(default_cat))
            sub_sites = sites_df[sites_df["category"] == chosen_cat].reset_index(drop=True)
            default_idx = 0
            for idx_r, r_name in enumerate(sub_sites["name"]):
                if "valparai" in r_name.lower():
                    default_idx = idx_r
                    break
            chosen_name = st.selectbox("Sitio:", sub_sites["name"].tolist(), index=default_idx)
            row_site = sub_sites[sub_sites["name"] == chosen_name].iloc[0]
            lon_target = float(row_site["lon"])
            lat_target = float(row_site["lat"])
            site_label = str(row_site["name"])
            st.caption(f"Coordenadas: `Lon = {lon_target:.4f}°`, `Lat = {lat_target:.4f}°`")
        else:
            lon_target = st.number_input("Longitud (°W, negativo):", value=-71.6145, min_value=-76.0, max_value=-70.0, step=0.01, format="%.4f")
            lat_target = st.number_input("Latitud (°S, negativo):", value=-33.0325, min_value=-45.0, max_value=-17.7, step=0.01, format="%.4f")
            site_label = f"Punto ({lon_target:.3f}°, {lat_target:.3f}°)"

        st.divider()
        st.header("2. Boyas de Aguas Profundas (AP)")
        buoy_grid = st.selectbox(
            "Grilla de Boyas AP:",
            options=["1deg", "uv14"],
            format_func=lambda x: "Boyas cada 1° (-18° a -45°S, 28 boyas)" if x == "1deg" else "Nodos Atlas UV (-19° a -45°S, 14 nodos)",
            index=0,
        )
        w_mode = st.selectbox(
            "Esquema de ponderación:",
            options=["dist_dir", "idw", "nearest"],
            format_func=lambda x: {
                "dist_dir": "Distancia + Dirección AP (Recomendado)",
                "idw": "Inverso de la Distancia (IDW)",
                "nearest": "Boya única más cercana",
            }[x],
            index=0,
        )
        max_buoys = st.slider("Número de boyas cercanas (K):", min_value=1, max_value=6, value=4)
        dir_gamma = st.slider("Sensibilidad direccional (γ):", min_value=0.0, max_value=0.95, value=0.85, step=0.05)
        dir_power = st.slider("Exponente direccional (β):", min_value=1.0, max_value=4.0, value=2.0, step=0.5)
        dist_power = st.slider("Exponente de distancia (p):", min_value=1.0, max_value=4.0, value=2.0, step=0.5)

        st.divider()
        if is_forecast:
            st.header("3. Parámetros de Pronóstico NOAA")
            forecast_server = st.selectbox(
                "Servidor NOAA:",
                options=["erddap", "nomads"],
                format_func=lambda x: "NOAA ERDDAP (WW3 Global - Recomendado)" if x == "erddap" else "NOAA NOMADS (GFS-Wave GRIB2)",
                index=0,
            )
            btn_refresh = st.button("🔄 Actualizar Pronóstico NOAA", help="Descarga los datos más recientes desde los servidores de NOAA")
            horizon_opt = st.selectbox(
                "Horizonte de visualización:",
                options=["todo", "24h", "48h", "72h", "120h"],
                format_func=lambda x: {
                    "todo": "Todo el pronóstico disponible (~5 a 6 días)",
                    "24h": "Próximas 24 horas (1 día)",
                    "48h": "Próximas 48 horas (2 días)",
                    "72h": "Próximas 72 horas (3 días)",
                    "120h": "Próximos 5 días",
                }[x],
                index=0,
            )
            period_var = "Tp"
            dir_var = "Dm"
            dt_hours = st.selectbox(
                "Paso de tiempo (Resolución):",
                options=[3, 1],
                format_func=lambda x: "Cada 3 horas (Nativo NOAA WW3)" if x == 3 else "Cada 1 hora (Interpolado horario)",
                index=0,
            )
            start_year = 0
            end_year = 0
        else:
            st.header("3. Parámetros y Fechas")
            btn_refresh = False
            forecast_server = "erddap"
            horizon_opt = "todo"
            period_var = st.selectbox("Periodo de entrada AP:", ["Tp", "Tm", "Tz", "Te"], index=0)
            dir_var = st.selectbox("Dirección de entrada AP:", ["Dm", "Dp"], index=0)
            dt_hours = st.selectbox(
                "Paso de tiempo (Resolución):",
                options=[1, 3],
                format_func=lambda x: "Cada 1 hora (Interpolado horario)" if x == 1 else "Cada 3 horas (Nativo Atlas UV)",
                index=0,
            )
            col_d1, col_d2 = st.columns(2)
            start_year = col_d1.number_input("Año inicio:", min_value=1980, max_value=2015, value=2010)
            end_year = col_d2.number_input("Año fin:", min_value=1980, max_value=2015, value=2015)
            if end_year < start_year:
                end_year = start_year

    # Encabezado Principal con Logo INH
    col_logo, col_title = st.columns([1, 9], vertical_alignment="center")
    with col_logo:
        if LOGO_INH.exists():
            st.image(str(LOGO_INH), width=110)
    with col_title:
        title_text = (
            "🔮 Sistema de Pronóstico Operacional de Oleaje (NOAA WW3)"
            if is_forecast
            else "🌊 Sistema de Hindcasting Rápido de Oleaje en Chile"
        )
        subtitle_text = (
            "**Pronóstico de Oleaje en Aguas Someras mediante Matrices de Transferencia SWAN `chile_250k` "
            "y Forzamiento Espectral Global NOAA WAVEWATCH III (ERDDAP / NOMADS)**"
            if is_forecast
            else "**Método de Matrices de Transferencia ($K_a$ y Dirección) sobre Malla No Estructurada SWAN `chile_250k` "
            "y Ponderación Espacial-Direccional Multi-Boya de Aguas Profundas**"
        )
        st.title(title_text)
        st.markdown(subtitle_text)

    # Cargar motor y ejecutar simulación (Hindcast o Forecast)
    try:
        if is_forecast:
            engine = get_forecast_engine(
                buoy_mode=buoy_grid,
                server=forecast_server,
                force_refresh=btn_refresh,
            )
        else:
            engine = get_hindcast_engine(buoy_grid)
    except Exception as e:
        st.error(f"Error cargando base de datos ({'Pronóstico NOAA' if is_forecast else 'Hindcast'}): {e}")
        render_disclaimer()
        st.stop()

    w_cfg = WeightingConfig(
        mode=w_mode,
        max_buoys=max_buoys,
        dist_power=dist_power,
        dir_gamma=dir_gamma,
        dir_power=dir_power,
    )

    if is_forecast:
        all_times = engine.ap_db.timestamps
        start_date = str(all_times[0])
        if horizon_opt == "24h":
            end_date = str(all_times[0] + pd.Timedelta(hours=24))
        elif horizon_opt == "48h":
            end_date = str(all_times[0] + pd.Timedelta(hours=48))
        elif horizon_opt == "72h":
            end_date = str(all_times[0] + pd.Timedelta(hours=72))
        elif horizon_opt == "120h":
            end_date = str(all_times[0] + pd.Timedelta(hours=120))
        else:
            end_date = str(all_times[-1])
    else:
        start_date = f"{int(start_year)}-01-01"
        end_date = f"{int(end_year)}-12-31 23:59:59"

    t0 = time.perf_counter()
    res = engine.run_simulation(
        lon=lon_target,
        lat=lat_target,
        site_name=site_label,
        start_date=start_date,
        end_date=end_date,
        period_var=period_var,
        dir_var=dir_var,
        weighting_config=w_cfg,
        dt_hours=dt_hours,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Métricas superiores
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    if is_forecast:
        m1.metric("Sitio Costero", res.site_name)
        m2.metric("Profundidad Malla", f"{res.depth:.1f} m")
        m3.metric("Hm0 Actual (AS)", f"{res.timeseries['Hm0_AS'].iloc[0]:.2f} m", f"AP: {res.timeseries['Hm0_AP'].iloc[0]:.2f} m")
        m4.metric("Hm0 Máx Previsto", f"{res.summary_stats['Hm0_AS_max']:.2f} m")
        m5.metric("Tp Medio / Ka", f"{res.summary_stats['Tp_mean']:.1f} s", f"Ka={res.summary_stats['Ka_mean']:.2f}")
        m6.metric("Horizonte Pronóstico", f"{res.summary_stats['n_records']} estados", f"{elapsed_ms:.1f} ms")
    else:
        m1.metric("Sitio Costero", res.site_name)
        m2.metric("Profundidad Malla", f"{res.depth:.1f} m")
        m3.metric("Ka Medio", f"{res.summary_stats['Ka_mean']:.3f}")
        m4.metric("Hm0 Medio (AS)", f"{res.summary_stats['Hm0_AS_mean']:.2f} m")
        m5.metric("Hm0 P99 / Máx (AS)", f"{res.summary_stats['Hm0_AS_p99']:.2f} / {res.summary_stats['Hm0_AS_max']:.2f} m")
        m6.metric("Tiempo Cálculo", f"{elapsed_ms:.1f} ms", f"{res.summary_stats['n_records']:,} estados")

    tab1_label = "🗺️ 1. Ubicación, Malla y Boyas AP"
    tab2_label = "📐 2. Matrices de Transferencia (Ka y Dir)"
    tab3_label = "🧭 3. Ponderación Multi-Boya (Distancia + Dirección)"
    tab4_label = "🔮 4. Serie de Pronóstico NOAA WW3" if is_forecast else "📈 4. Serie de Hindcasting y Clima de Oleaje"

    tab1, tab2, tab3, tab4 = st.tabs([tab1_label, tab2_label, tab3_label, tab4_label])

    # ================= PESTAÑA 1: MAPA Y MALLA =================
    with tab1:
        c_map1, c_map2 = st.columns([1.1, 1.0])
        with c_map1:
            st.subheader("Posición del Sitio Costero y Boyas de Aguas Profundas")
            fig_geo = go.Figure()
            # Todas las boyas disponibles
            fig_geo.add_trace(
                go.Scattergeo(
                    lon=engine.ap_db.lons,
                    lat=engine.ap_db.lats,
                    mode="markers",
                    name="Boyas AP disponibles",
                    marker=dict(size=7, color="#90a4ae", symbol="circle-open"),
                    text=engine.ap_db.names,
                )
            )
            # Líneas de conexión y boyas seleccionadas
            for b_name, b_lon, b_lat, w_m in zip(
                res.buoy_info["buoy_names"],
                res.buoy_info["lons"],
                res.buoy_info["lats"],
                res.weights_mean,
            ):
                fig_geo.add_trace(
                    go.Scattergeo(
                        lon=[res.lon, b_lon],
                        lat=[res.lat, b_lat],
                        mode="lines",
                        line=dict(width=max(1.0, float(w_m) * 6.0), color="#1e88e5"),
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
            fig_geo.add_trace(
                go.Scattergeo(
                    lon=res.buoy_info["lons"],
                    lat=res.buoy_info["lats"],
                    mode="markers+text",
                    name="Boyas AP Activas (ponderadas)",
                    text=[f"{n} ({w*100:.1f}%)" for n, w in zip(res.buoy_info["buoy_names"], res.weights_mean)],
                    textposition="middle left",
                    marker=dict(
                        size=[max(10.0, float(w) * 28.0) for w in res.weights_mean],
                        color=res.weights_mean * 100.0,
                        colorscale="Blues",
                        showscale=False,
                        line=dict(width=1.5, color="black"),
                    ),
                )
            )
            fig_geo.add_trace(
                go.Scattergeo(
                    lon=[res.lon],
                    lat=[res.lat],
                    mode="markers+text",
                    name="Punto Costero Objetivo (AS)",
                    text=[res.site_name],
                    textposition="middle right",
                    marker=dict(size=14, color="#e53935", symbol="star", line=dict(width=1, color="black")),
                )
            )
            fig_geo.update_geos(
                resolution=50,
                showcountries=True,
                showcoastlines=True,
                showland=True,
                landcolor="#f5f5f5",
                oceancolor="#e3f2fd",
                showocean=True,
                lonaxis_range=[min(res.lon - 4.5, -77.0), max(res.lon + 2.5, -69.0)],
                lataxis_range=[res.lat - 4.5, res.lat + 4.5],
            )
            fig_geo.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=-0.05))
            st.plotly_chart(fig_geo, use_container_width=True)

        with c_map2:
            st.subheader("Malla No Estructurada Local `chile_250k` e Interpolación")
            # Mostrar nodos de la malla en una caja de ±0.15° alrededor del punto
            box_deg = 0.15
            mask_local = (
                (np.abs(engine.transfer_db.lon - res.lon) <= box_deg)
                & (np.abs(engine.transfer_db.lat - res.lat) <= box_deg)
            )
            if np.sum(mask_local) < 30:
                box_deg = 0.45
                mask_local = (
                    (np.abs(engine.transfer_db.lon - res.lon) <= box_deg)
                    & (np.abs(engine.transfer_db.lat - res.lat) <= box_deg)
                )

            fig_mesh = go.Figure()
            fig_mesh.add_trace(
                go.Scatter(
                    x=engine.transfer_db.lon[mask_local],
                    y=engine.transfer_db.lat[mask_local],
                    mode="markers",
                    name="Nodos Malla SWAN",
                    marker=dict(
                        size=5,
                        color=engine.transfer_db.depth[mask_local],
                        colorscale="Deep",
                        colorbar=dict(title="Prof. (m)"),
                    ),
                    text=[f"Prof: {d:.1f} m" for d in engine.transfer_db.depth[mask_local]],
                )
            )
            interp_nodes = res.local_tf.spatial_info["node_indices"]
            interp_weights = res.local_tf.spatial_info["weights"]
            fig_mesh.add_trace(
                go.Scatter(
                    x=engine.transfer_db.lon[interp_nodes],
                    y=engine.transfer_db.lat[interp_nodes],
                    mode="markers+lines",
                    name=f"Nodos Interpolación ({res.local_tf.spatial_info['method']})",
                    marker=dict(size=12, color="#fb8c00", symbol="diamond", line=dict(width=1.5, color="black")),
                    text=[f"Nodo {n} (w={w:.3f})" for n, w in zip(interp_nodes, interp_weights)],
                )
            )
            fig_mesh.add_trace(
                go.Scatter(
                    x=[res.lon],
                    y=[res.lat],
                    mode="markers",
                    name="Punto Costero P(X,Y)",
                    marker=dict(size=14, color="#e53935", symbol="star"),
                )
            )
            fig_mesh.update_layout(
                xaxis_title="Longitud (°)",
                yaxis_title="Latitud (°)",
                yaxis=dict(scaleanchor="x", scaleratio=1.0),
                template="plotly_white",
                height=520,
                legend=dict(orientation="h", y=-0.15),
                margin=dict(l=20, r=20, t=30, b=40),
            )
            st.plotly_chart(fig_mesh, use_container_width=True)

    # ================= PESTAÑA 2: MATRICES DE TRANSFERENCIA =================
    with tab2:
        st.subheader(f"Funciones de Transferencia Locales en {res.site_name} ({res.lon:.4f}°, {res.lat:.4f}°)")
        col_tf1, col_tf2 = st.columns(2)

        with col_tf1:
            fig_ka = go.Figure(
                data=go.Heatmap(
                    z=res.local_tf.ka_matrix,
                    x=res.local_tf.directions,
                    y=res.local_tf.periods,
                    colorscale="Viridis",
                    colorbar=dict(title="Ka = Hm0_AS / Hm0_AP"),
                )
            )
            fig_ka.update_layout(
                title="Matriz de Coeficiente de Agitación Ka(T, Dir_AP)",
                xaxis_title="Dirección en Aguas Profundas (° náuticos)",
                yaxis_title="Periodo T (s)",
                template="plotly_white",
                height=440,
            )
            st.plotly_chart(fig_ka, use_container_width=True)

        with col_tf2:
            fig_dir = go.Figure(
                data=go.Heatmap(
                    z=res.local_tf.dir_matrix,
                    x=res.local_tf.directions,
                    y=res.local_tf.periods,
                    colorscale="Twilight",
                    zmin=0,
                    zmax=360,
                    colorbar=dict(title="Dir_AS (°)"),
                )
            )
            fig_dir.update_layout(
                title="Matriz de Dirección Transformada en Aguas Someras Dir_AS(T, Dir_AP)",
                xaxis_title="Dirección en Aguas Profundas (° náuticos)",
                yaxis_title="Periodo T (s)",
                template="plotly_white",
                height=440,
            )
            st.plotly_chart(fig_dir, use_container_width=True)

        st.markdown("#### Calculadora Puntual de Transferencia Espectral")
        cc1, cc2, cc3, cc4 = st.columns(4)
        hs_in = cc1.number_input("Hm0 Aguas Profundas (m):", value=2.50, min_value=0.1, max_value=15.0, step=0.1)
        tp_in = cc2.number_input("Periodo Aguas Profundas (s):", value=13.0, min_value=4.0, max_value=24.0, step=0.5)
        dir_in = cc3.number_input("Dirección Aguas Profundas (°):", value=240.0, min_value=180.0, max_value=360.0, step=2.5)
        single_eval = res.local_tf.evaluate(
            periods_ap=np.array([tp_in]),
            dirs_ap=np.array([dir_in]),
            hm0_ap=np.array([hs_in]),
        )
        cc4.success(
            f"**Resultado en {res.site_name}:**\n"
            f"- **$K_a$ interpolado:** `{single_eval['Ka'][0]:.3f}`\n"
            f"- **$H_{{m0,\\text{{AS}}}}$:** `{single_eval['Hm0_AS'][0]:.2f} m`\n"
            f"- **$T_{{\\text{{AS}}}}$:** `{single_eval['T_AS'][0]:.1f} s` (invariante)\n"
            f"- **$\\text{{Dir}}_{{\\text{{AS}}}}$:** `{single_eval['Dir_AS'][0]:.1f}°`"
        )

    # ================= PESTAÑA 3: PONDERACIÓN MULTI-BOYA =================
    with tab3:
        st.subheader("Respuesta de Pesos Multi-Boya en Función de la Distancia y Dirección de Aguas Profundas")
        st.markdown(
            "Cuando el oleaje proviene del **Norte/Noroeste** ($\\theta_{\\text{AP}} \\to 360^\\circ$), "
            "las boyas ubicadas hacia el Norte del punto reciben mayor peso. Cuando el oleaje proviene del "
            "**Sur/Suroeste** ($\\theta_{\\text{AP}} \\to 180^\\circ$), dominan las boyas ubicadas hacia el Sur."
        )

        test_dirs = np.linspace(180.0, 360.0, 181)
        weighter_demo = MultiBuoyWeighter(
            buoy_lons=engine.ap_db.lons,
            buoy_lats=engine.ap_db.lats,
            buoy_ids=engine.ap_db.ids,
            buoy_names=engine.ap_db.names,
            config=w_cfg,
        )
        w_curve, b_info = weighter_demo.compute_weights(res.lon, res.lat, test_dirs)

        fig_w = go.Figure()
        for idx_b, b_name in enumerate(b_info["buoy_names"]):
            dlat_str = f"ΔLat={b_info['dlat_deg'][idx_b]:+.2f}° ({'Norte' if b_info['dlat_deg'][idx_b] >= 0 else 'Sur'})"
            fig_w.add_trace(
                go.Scatter(
                    x=test_dirs,
                    y=w_curve[idx_b, :] * 100.0,
                    mode="lines",
                    line=dict(width=3),
                    name=f"{b_name} | d={b_info['distances_km'][idx_b]:.0f} km | {dlat_str}",
                )
            )
        fig_w.update_layout(
            title=f"Curvas de Peso Dinámico ω_i(θ_AP) para {res.site_name}",
            xaxis_title="Dirección de Procedencia del Oleaje en Aguas Profundas θ_AP (°) [180°=Sur, 270°=Oeste, 360°=Norte]",
            yaxis_title="Peso Asignado a la Boya (%)",
            template="plotly_white",
            height=430,
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(fig_w, use_container_width=True)

        # Tabla resumen de boyas activas
        df_buoys_table = pd.DataFrame({
            "Boya AP": res.buoy_info["buoy_names"],
            "Longitud (°)": res.buoy_info["lons"],
            "Latitud (°)": res.buoy_info["lats"],
            "ΔLat respecto al punto (°)": np.round(res.buoy_info["dlat_deg"], 3),
            "Posición Relativa": ["Norte (Aguas arriba N)" if dl >= 0 else "Sur (Aguas arriba S)" for dl in res.buoy_info["dlat_deg"]],
            "Distancia (km)": np.round(res.buoy_info["distances_km"], 1),
            "Acimut P→Boya (°)": np.round(res.buoy_info["azimuths_deg"], 1),
            "Peso Solo Distancia (%)": np.round(res.buoy_info["w_dist_norm"] * 100.0, 1),
            "Peso Medio Histórico Dist+Dir (%)": np.round(res.weights_mean * 100.0, 1),
        })
        st.dataframe(df_buoys_table, use_container_width=True)

    # ================= PESTAÑA 4: HINDCASTING / FORECASTING =================
    with tab4:
        ts = res.timeseries
        t_start_fmt = ts["DateTime"].iloc[0].strftime("%d/%m/%Y %H:%M")
        t_end_fmt = ts["DateTime"].iloc[-1].strftime("%d/%m/%Y %H:%M")

        if is_forecast:
            st.subheader(
                f"Pronóstico Operacional NOAA WW3 ({t_start_fmt} – {t_end_fmt} UTC, "
                f"cada {dt_hours} h, {len(ts)} pasos) en {res.site_name}"
            )
            src_str = engine.ap_db.metadata.get("source", "NOAA WW3 Global")
            st.info(
                f"📡 **Forzamiento Espectral Oceánico:** Modelo global WAVEWATCH III / GFS-Wave de la NOAA. "
                f"Transformado a aguas someras mediante SWAN `chile_250k`. Fuente: `{src_str}`."
            )
        else:
            st.subheader(
                f"Serie de Tiempo de Hindcasting ({start_year}–{end_year}, cada {dt_hours} h, "
                f"{len(ts):,} registros) en {res.site_name}"
            )

        # Graficar serie temporal usando WebGL (Scattergl)
        sub_title_hm0 = (
            "Hm0 Pronosticado: Borde NOAA Aguas Profundas (AP) vs Costa Aguas Someras (AS)"
            if is_forecast
            else "Altura Significativa Hm0: Aguas Profundas (AP) vs Aguas Someras (AS)"
        )
        sub_title_dir = (
            "Dirección del Oleaje Pronosticada: Borde NOAA (AP) vs Costa (AS)"
            if is_forecast
            else "Dirección del Oleaje: Aguas Profundas (AP) vs Aguas Someras (AS)"
        )

        fig_ts = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=(
                sub_title_hm0,
                "Periodo de Oleaje Tp (Invariante AP = AS)",
                sub_title_dir,
            ),
        )
        fig_ts.add_trace(
            go.Scattergl(x=ts["DateTime"], y=ts["Hm0_AP"], name="Hm0 AP (m)", line=dict(color="#90caf9", width=1.4)),
            row=1, col=1,
        )
        fig_ts.add_trace(
            go.Scattergl(x=ts["DateTime"], y=ts["Hm0_AS"], name="Hm0 AS (m)", line=dict(color="#d32f2f", width=1.8)),
            row=1, col=1,
        )
        fig_ts.add_trace(
            go.Scattergl(x=ts["DateTime"], y=ts["Tp_AS"], name="Tp (s)", line=dict(color="#388e3c", width=1.4)),
            row=2, col=1,
        )
        fig_ts.add_trace(
            go.Scattergl(x=ts["DateTime"], y=ts["Dir_AP"], name="Dir AP (°)", mode="markers", marker=dict(size=3.0, color="#90caf9")),
            row=3, col=1,
        )
        fig_ts.add_trace(
            go.Scattergl(x=ts["DateTime"], y=ts["Dir_AS"], name="Dir AS (°)", mode="markers", marker=dict(size=3.0, color="#1976d2")),
            row=3, col=1,
        )
        fig_ts.update_layout(height=620, template="plotly_white", margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_ts, use_container_width=True)

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.plotly_chart(
                build_wave_rose(ts, "Hm0_AP", "Dir_AP", "Rosa de Oleaje en Aguas Profundas (Borde NOAA Ponderado)" if is_forecast else "Rosa de Oleaje en Aguas Profundas (Borde Ponderado)"),
                use_container_width=True,
            )
        with col_r2:
            st.plotly_chart(
                build_wave_rose(ts, "Hm0_AS", "Dir_AS", f"Rosa de Oleaje en Aguas Someras ({res.site_name})"),
                use_container_width=True,
            )

        # En modo pronóstico, mostrar tabla interactiva detallada
        if is_forecast:
            st.subheader(f"📋 Tabla Detallada de Pronóstico Horario en {res.site_name}")
            df_disp = ts[["DateTime", "Hm0_AS", "Tp_AS", "Dir_AS", "Ka_eff", "Hm0_AP", "Dir_AP"]].copy()
            df_disp.columns = ["Fecha / Hora (UTC)", "Hm0 Costa (m)", "Tp (s)", "Dir Costa (°)", "Ka Coef", "Hm0 Oceánico (m)", "Dir Oceánica (°)"]
            st.dataframe(df_disp, use_container_width=True)

        # Descarga CSV
        csv_bytes = ts.to_csv(index=False).encode("utf-8")
        if is_forecast:
            btn_label = f"⬇️ Descargar Pronóstico NOAA en {res.site_name} (.CSV)"
            f_name = f"forecast_AS_{res.site_name.replace(' ', '_')}_{ts['DateTime'].iloc[0].strftime('%Y%m%d')}_{ts['DateTime'].iloc[-1].strftime('%Y%m%d')}.csv"
        else:
            btn_label = f"⬇️ Descargar Serie de Hindcasting en {res.site_name} (.CSV)"
            f_name = f"hindcast_AS_{res.site_name.replace(' ', '_')}_{start_year}_{end_year}.csv"

        st.download_button(
            label=btn_label,
            data=csv_bytes,
            file_name=f_name,
            mime="text/csv",
        )

    render_disclaimer()


if __name__ == "__main__":
    main()
