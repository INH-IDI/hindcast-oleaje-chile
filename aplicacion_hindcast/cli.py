#!/usr/bin/env python3
"""
Interfaz de Línea de Comandos (CLI) para ejecutar el Hindcasting Rápido de Oleaje
en cualquier punto costero de Chile usando las matrices de transferencia SWAN
y el Hindcasting de Aguas Profundas (Atlas UV / Grilla 1°).

Ejemplos de uso:
  python3 cli.py --site "Valparai" --start 2010-01-01 --end 2015-12-31 --out valparaiso_hindcast.csv
  python3 cli.py --lon -71.6145 --lat -33.0325 --mode dist_dir --max-buoys 4 --out punto_custom.csv
"""

import argparse
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from transfer_lib import WaveHindcastEngine, WeightingConfig, load_coastal_sites


def parse_args():
    parser = argparse.ArgumentParser(
        description="Hindcasting Rápido de Oleaje en Aguas Someras mediante Funciones de Transferencia SWAN."
    )
    parser.add_argument("--lon", type=float, default=None, help="Longitud del punto objetivo (ej. -71.6145)")
    parser.add_argument("--lat", type=float, default=None, help="Latitud del punto objetivo (ej. -33.0325)")
    parser.add_argument("--site", type=str, default=None, help="Nombre de puerto, nodo o caleta del catálogo")
    parser.add_argument("--list-sites", action="store_true", help="Listar sitios costeros disponibles y salir")
    parser.add_argument("--buoy-grid", choices=["1deg", "uv14"], default="1deg", help="Grilla de boyas AP: '1deg' (28 boyas) o 'uv14' (14 nodos UV)")
    parser.add_argument("--mode", choices=["dist_dir", "idw", "nearest"], default="dist_dir", help="Modo de ponderación multi-boya")
    parser.add_argument("--max-buoys", type=int, default=4, help="Número de boyas de AP cercanas a ponderar")
    parser.add_argument("--period-var", choices=["Tp", "Tm", "Tz", "Te"], default="Tp", help="Periodo de referencia en AP")
    parser.add_argument("--dir-var", choices=["Dm", "Dp"], default="Dm", help="Dirección de referencia en AP")
    parser.add_argument("--dt-hours", type=int, choices=[1, 3], default=1, help="Paso horario de salida: 1h o 3h (default: 1)")
    parser.add_argument("--start", type=str, default=None, help="Fecha inicio YYYY-MM-DD (por defecto 1980-01-01)")
    parser.add_argument("--end", type=str, default=None, help="Fecha término YYYY-MM-DD (por defecto 2015-12-31)")
    parser.add_argument("--out", type=str, default=None, help="Ruta de archivo CSV/Parquet de salida")
    return parser.parse_args()


def main():
    args = parse_args()
    sites_df = load_coastal_sites()

    if args.list_sites:
        print(f"Total sitios en catálogo: {len(sites_df)}")
        print(sites_df.to_string(max_rows=100))
        return

    lon, lat = args.lon, args.lat
    site_name = args.site or "Punto_Custom"

    if args.site:
        match = sites_df[sites_df["name"].str.lower() == args.site.lower()]
        if match.empty:
            match = sites_df[sites_df["name"].str.lower().str.contains(args.site.lower())]
        if match.empty:
            raise ValueError(f"No se encontró el sitio '{args.site}' en el catálogo.")
        row = match.iloc[0]
        lon = float(row["lon"])
        lat = float(row["lat"])
        site_name = str(row["name"])
    elif lon is None or lat is None:
        # Por defecto Valparaíso
        lon, lat = -71.614455, -33.032507
        site_name = "Valparaiso"

    t0 = time.perf_counter()
    engine = WaveHindcastEngine(buoy_mode=args.buoy_grid)
    w_cfg = WeightingConfig(mode=args.mode, max_buoys=args.max_buoys)

    result = engine.run_hindcast(
        lon=lon,
        lat=lat,
        site_name=site_name,
        start_date=args.start,
        end_date=args.end,
        period_var=args.period_var,
        dir_var=args.dir_var,
        weighting_config=w_cfg,
        dt_hours=args.dt_hours,
    )
    elapsed = time.perf_counter() - t0

    print("=" * 72)
    print(f"HINDCASTING COSTERO: {result.site_name} (lon={result.lon:.4f}°, lat={result.lat:.4f}°, prof={result.depth:.1f}m)")
    print(f"Método espacial    : {result.local_tf.spatial_info['method']}")
    print(f"Modo multi-boya AP : {args.mode} (grilla={args.buoy_grid}, K={len(result.buoy_info['buoy_names'])})")
    print(f"Registros          : {result.summary_stats['n_records']} pasos ({elapsed*1000:.1f} ms)")
    print("-" * 72)
    print("Boyas de Aguas Profundas seleccionadas y pesos medios:")
    for b_name, b_lon, b_lat, b_dist, b_az, w_m in zip(
        result.buoy_info["buoy_names"],
        result.buoy_info["lons"],
        result.buoy_info["lats"],
        result.buoy_info["distances_km"],
        result.buoy_info["azimuths_deg"],
        result.weights_mean,
    ):
        print(f"  * {b_name:24s} ({b_lon:6.2f}°, {b_lat:6.2f}°) | dist={b_dist:6.1f} km | az={b_az:5.1f}° | peso medio={w_m*100:5.1f}%")
    print("-" * 72)
    print("Estadísticas en Aguas Someras (AS):")
    for k, v in result.summary_stats.items():
        print(f"  {k:16s}: {v:.4f}")
    print("=" * 72)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".parquet":
            result.timeseries.to_parquet(out_path, index=False)
        else:
            result.timeseries.to_csv(out_path, index=False)
        print(f"[OK] Serie de tiempo exportada a: {out_path}")


if __name__ == "__main__":
    main()
