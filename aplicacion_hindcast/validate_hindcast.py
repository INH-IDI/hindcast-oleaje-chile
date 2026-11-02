#!/usr/bin/env python3
"""
Script de validación integral y generación de figuras de diagnóstico para el
Sistema de Hindcasting Rápido de Oleaje en Chile.
Evalúa todos los puertos chilenos, genera estadísticas 1980-2015 y exporta figuras PNG.
"""

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from transfer_lib import WaveHindcastEngine, WeightingConfig, MultiBuoyWeighter, load_coastal_sites


def main():
    out_dir = APP_DIR / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Inicializando WaveHindcastEngine...")
    t0 = time.perf_counter()
    engine = WaveHindcastEngine(buoy_mode="1deg")
    print(f"Motor cargado en {(time.perf_counter() - t0)*1000:.1f} ms")

    sites_df = load_coastal_sites()
    ports_df = sites_df[sites_df["category"] == "Puerto"].reset_index(drop=True)

    # 1. Evaluar todos los puertos de Chile (1980-2015, 105,191 registros c/u)
    summary_rows = []
    port_results = {}
    w_cfg = WeightingConfig(mode="dist_dir", max_buoys=4, dir_gamma=0.85, dir_power=2.0)

    for _, row in ports_df.iterrows():
        t_p = time.perf_counter()
        res = engine.run_hindcast(
            lon=float(row["lon"]),
            lat=float(row["lat"]),
            site_name=str(row["name"]),
            weighting_config=w_cfg,
        )
        dt_ms = (time.perf_counter() - t_p) * 1000.0
        port_results[row["name"]] = res
        summary_rows.append({
            "Puerto": row["name"],
            "Lon": row["lon"],
            "Lat": row["lat"],
            "Prof_m": round(res.depth, 1),
            "Metodo_Espacial": res.local_tf.spatial_info["method"],
            "Ka_Medio": round(res.summary_stats["Ka_mean"], 3),
            "Hm0_AS_Medio_m": round(res.summary_stats["Hm0_AS_mean"], 2),
            "Hm0_AS_P95_m": round(res.summary_stats["Hm0_AS_p95"], 2),
            "Hm0_AS_P99_m": round(res.summary_stats["Hm0_AS_p99"], 2),
            "Hm0_AS_Max_m": round(res.summary_stats["Hm0_AS_max"], 2),
            "Tp_Medio_s": round(res.summary_stats["Tp_mean"], 2),
            "Dir_AS_Media_deg": round(res.summary_stats["Dir_AS_mean"], 1),
            "Tiempo_ms": round(dt_ms, 1),
        })
        print(
            f"  [OK] {row['name']:12s} | Prof={res.depth:5.1f}m | Ka={res.summary_stats['Ka_mean']:.3f} | "
            f"Hm0_AS medio={res.summary_stats['Hm0_AS_mean']:.2f}m | P99={res.summary_stats['Hm0_AS_p99']:.2f}m | {dt_ms:.1f} ms"
        )

    summary_df = pd.DataFrame(summary_rows)
    csv_summary = out_dir / "resumen_puertos_chile_1980_2015.csv"
    summary_df.to_csv(csv_summary, index=False)
    print(f"\n[OK] Resumen estadístico 1980-2015 de puertos guardado en: {csv_summary}")

    # 2. Figura 1: Matrices de Transferencia Ka(T, Dir_AP) y Dir_AS(T, Dir_AP) en 4 puertos representativos
    rep_ports = [p for p in ["Arica", "Coquimbo", "Valparai", "Talcahu", "Ancud"] if p in port_results][:4]
    fig, axes = plt.subplots(2, len(rep_ports), figsize=(4.2 * len(rep_ports), 7.5), constrained_layout=True)

    for col_i, p_name in enumerate(rep_ports):
        tf = port_results[p_name].local_tf
        ax_top = axes[0, col_i]
        im1 = ax_top.pcolormesh(tf.directions, tf.periods, tf.ka_matrix, shading="auto", cmap="viridis", vmin=0.0, vmax=1.3)
        ax_top.set_title(f"{p_name} ({tf.lat:.2f}°S)\nKa(T, Dir_AP)", fontsize=10, fontweight="bold")
        ax_top.set_xlabel("Dir AP (°)")
        if col_i == 0:
            ax_top.set_ylabel("Periodo T (s)")
        fig.colorbar(im1, ax=ax_top, label="Ka")

        ax_bot = axes[1, col_i]
        im2 = ax_bot.pcolormesh(tf.directions, tf.periods, tf.dir_matrix, shading="auto", cmap="twilight", vmin=150, vmax=360)
        ax_bot.set_title(f"{p_name} - Dir_AS (°)", fontsize=10)
        ax_bot.set_xlabel("Dir AP (°)")
        if col_i == 0:
            ax_bot.set_ylabel("Periodo T (s)")
        fig.colorbar(im2, ax=ax_bot, label="Dir AS (°)")

    fig1_path = out_dir / "fig1_transfer_matrices_ports.png"
    fig.savefig(fig1_path, dpi=160)
    plt.close(fig)
    print(f"[OK] Figura 1 guardada en: {fig1_path}")

    # 3. Figura 2: Ponderación Multi-Boya en función de la Distancia y Dirección AP
    fig2, (ax_w1, ax_w2) = plt.subplots(1, 2, figsize=(13, 5.0), constrained_layout=True)
    test_dirs = np.linspace(180.0, 360.0, 181)

    for ax_cur, p_name in zip([ax_w1, ax_w2], ["Valparai", "Talcahu"]):
        if p_name not in port_results:
            continue
        r_p = port_results[p_name]
        weighter = MultiBuoyWeighter(
            buoy_lons=engine.ap_db.lons,
            buoy_lats=engine.ap_db.lats,
            buoy_ids=engine.ap_db.ids,
            buoy_names=engine.ap_db.names,
            config=w_cfg,
        )
        w_curve, b_info = weighter.compute_weights(r_p.lon, r_p.lat, test_dirs)
        for idx_b, b_name in enumerate(b_info["buoy_names"]):
            pos_ns = "Norte" if b_info["dlat_deg"][idx_b] >= 0 else "Sur"
            ax_cur.plot(
                test_dirs,
                w_curve[idx_b, :] * 100.0,
                lw=2.4,
                label=f"{b_name} ({pos_ns}, d={b_info['distances_km'][idx_b]:.0f} km)",
            )
        ax_cur.axvline(270.0, color="gray", ls="--", lw=1.0, label="Oeste (270°)")
        ax_cur.set_title(f"Pesos Multi-Boya ω_i(θ_AP) en {p_name} (lat={r_p.lat:.2f}°S)", fontweight="bold")
        ax_cur.set_xlabel("Dirección de Procedencia en Aguas Profundas θ_AP (°) [180°=S, 270°=W, 360°=N]")
        ax_cur.set_ylabel("Peso de la Boya (%)")
        ax_cur.set_xlim(180, 360)
        ax_cur.set_ylim(0, 100)
        ax_cur.grid(True, alpha=0.3)
        ax_cur.legend(fontsize=8.5)

    fig2_path = out_dir / "fig2_multibuoy_directional_weights.png"
    fig2.savefig(fig2_path, dpi=160)
    plt.close(fig2)
    print(f"[OK] Figura 2 guardada en: {fig2_path}")

    # 4. Figura 3: Serie de tiempo de Hindcasting (año 2015) y dispersión conjunta en Valparaíso
    if "Valparai" in port_results:
        r_val = port_results["Valparai"]
        ts_val = r_val.timeseries
        ts_2015 = ts_val[ts_val["DateTime"] >= "2015-01-01"].copy()

        fig3, axes3 = plt.subplots(2, 2, figsize=(13.5, 7.5), constrained_layout=True)

        axes3[0, 0].plot(ts_2015["DateTime"], ts_2015["Hm0_AP"], label="Hm0 Aguas Profundas (AP)", color="#90caf9", lw=1.1)
        axes3[0, 0].plot(ts_2015["DateTime"], ts_2015["Hm0_AS"], label="Hm0 Aguas Someras (AS)", color="#d32f2f", lw=1.3)
        axes3[0, 0].set_title("Valparaíso (2015): Serie Temporal Hm0 (AP vs AS)", fontweight="bold")
        axes3[0, 0].set_ylabel("Hm0 (m)")
        axes3[0, 0].legend()
        axes3[0, 0].grid(True, alpha=0.3)

        axes3[0, 1].plot(ts_2015["DateTime"], ts_2015["Dir_AP"], ".", ms=2.5, label="Dir AP (°)", color="#64b5f6", alpha=0.6)
        axes3[0, 1].plot(ts_2015["DateTime"], ts_2015["Dir_AS"], ".", ms=2.5, label="Dir AS (°)", color="#1a237e", alpha=0.7)
        axes3[0, 1].set_title("Valparaíso (2015): Refracción Direccional (Dir AP vs Dir AS)", fontweight="bold")
        axes3[0, 1].set_ylabel("Dirección Náutica (°)")
        axes3[0, 1].legend()
        axes3[0, 1].grid(True, alpha=0.3)

        hb1 = axes3[1, 0].hexbin(ts_val["Tp_AS"], ts_val["Hm0_AS"], gridsize=35, cmap="YlOrRd", mincnt=1)
        axes3[1, 0].set_title("Clima 1980-2015 (AS): Densidad Conjunta Hm0 vs Tp", fontweight="bold")
        axes3[1, 0].set_xlabel("Periodo Tp (s)")
        axes3[1, 0].set_ylabel("Hm0 AS (m)")
        axes3[1, 0].grid(True, alpha=0.3)
        fig3.colorbar(hb1, ax=axes3[1, 0], label="N° estados (1980-2015)")

        hb2 = axes3[1, 1].hexbin(ts_val["Dir_AS"], ts_val["Hm0_AS"], gridsize=35, cmap="PuBuGn", mincnt=1)
        axes3[1, 1].set_title("Clima 1980-2015 (AS): Densidad Conjunta Hm0 vs Dir_AS", fontweight="bold")
        axes3[1, 1].set_xlabel("Dirección en Aguas Someras Dir_AS (°)")
        axes3[1, 1].set_ylabel("Hm0 AS (m)")
        axes3[1, 1].grid(True, alpha=0.3)
        fig3.colorbar(hb2, ax=axes3[1, 1], label="N° estados (1980-2015)")

        fig3_path = out_dir / "fig3_hindcast_timeseries_and_roses.png"
        fig3.savefig(fig3_path, dpi=160)
        plt.close(fig3)
        print(f"[OK] Figura 3 guardada en: {fig3_path}")


if __name__ == "__main__":
    main()
