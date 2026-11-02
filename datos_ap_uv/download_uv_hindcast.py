#!/usr/bin/env python3
"""
Descarga y procesa los datos de Hindcasting de Aguas Profundas (AP) desde
https://oleaje.uv.cl/descargas.html (Nodos 1 al 14: Arica a Los Chonos, 1980-2015)
y construye además la grilla de boyas cada 1° de latitud (-18° a -45°S) para Chile.
"""

import os
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
import netCDF4 as nc

BASE_URL = "https://oleaje.uv.cl/descargables/Datos%20Nodos/"

UV_NODES = [
    {"id": 1,  "lat": -19.0, "lon": -72.0, "name": "Arica",                      "filename": "Nodo 1 (-19,-72) - Arica.txt"},
    {"id": 2,  "lat": -21.0, "lon": -72.0, "name": "Iquique",                    "filename": "Nodo 2 (-21,-72) - Iquique.txt"},
    {"id": 3,  "lat": -23.0, "lon": -72.0, "name": "Mejillones",                 "filename": "Nodo 3 (-23,-72) - Mejillones.txt"},
    {"id": 4,  "lat": -25.0, "lon": -72.0, "name": "Taltal",                     "filename": "Nodo 4 (-25,-72) - Taltal.txt"},
    {"id": 5,  "lat": -27.0, "lon": -72.0, "name": "Bahia_Inglesa",              "filename": "Nodo 5 (-27,-72) - Bahía Inglesa.txt"},
    {"id": 6,  "lat": -29.0, "lon": -73.0, "name": "Huasco",                     "filename": "Nodo 6 (-29,-73) - Huasco.txt"},
    {"id": 7,  "lat": -31.0, "lon": -73.0, "name": "Tongoy",                     "filename": "Nodo 7 (-31,-73) - Tongoy.txt"},
    {"id": 8,  "lat": -33.0, "lon": -73.0, "name": "Valparaiso",                 "filename": "Nodo 8 (-33,-73) - Valparaíso.txt"},
    {"id": 9,  "lat": -35.0, "lon": -73.0, "name": "Constitucion",               "filename": "Nodo 9 (-35,-73) - Constitución.txt"},
    {"id": 10, "lat": -37.0, "lon": -75.0, "name": "Talcahuano",                 "filename": "Nodo 10 (-37,-75) - Talcahuano.txt"},
    {"id": 11, "lat": -39.0, "lon": -75.0, "name": "Puerto_Saavedra",            "filename": "Nodo 11 (-39,-75) - Puerto Saavedra.txt"},
    {"id": 12, "lat": -41.0, "lon": -75.0, "name": "Bahia_Mansa",                "filename": "Nodo 12 (-41,-75) - Bahía Mansa.txt"},
    {"id": 13, "lat": -43.0, "lon": -76.0, "name": "Chiloe",                     "filename": "Nodo 13 (-43,-76) - Chiloé.txt"},
    {"id": 14, "lat": -45.0, "lon": -76.0, "name": "Archipielago_de_Los_Chonos", "filename": "Nodo 14 (-45,-76) - Archipiélago de Los Chonos.txt"},
]

# Boyas cada 1° en todo Chile (de -18° a -45°S), alineadas con el borde de la malla chile_250k
BUOYS_1DEG = [
    {"id": i + 1, "lat": float(lat), "lon": float(lon), "name": f"Boya_AP_{abs(int(lat))}S"}
    for i, (lon, lat) in enumerate([
        (-73.0, -18), (-72.0, -19), (-72.0, -20), (-72.0, -21), (-72.0, -22),
        (-72.0, -23), (-72.0, -24), (-72.0, -25), (-72.0, -26), (-72.0, -27),
        (-72.5, -28), (-73.0, -29), (-73.0, -30), (-73.0, -31), (-73.0, -32),
        (-73.0, -33), (-73.0, -34), (-73.0, -35), (-74.0, -36), (-75.0, -37),
        (-75.0, -38), (-75.0, -39), (-75.0, -40), (-75.0, -41), (-75.5, -42),
        (-76.0, -43), (-76.0, -44), (-76.0, -45),
    ])
]

COLUMNS = [
    "year", "month", "day", "hour",
    "Hm0", "Tz", "Te", "Tm", "Tp", "Dm", "Dp",
    "e", "v", "Qp", "y", "s"
]


def download_single_node(node_info: dict, raw_dir: Path) -> Path:
    """Descarga un archivo de nodo desde oleaje.uv.cl si no existe localmente."""
    dest = raw_dir / node_info["filename"]
    url = BASE_URL + urllib.parse.quote(node_info["filename"].encode("utf-8"))

    if dest.exists() and dest.stat().st_size > 10_000_000:
        print(f"[OK] Ya existe: {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
        return dest

    print(f"[DESCARGANDO] {node_info['filename']} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        content = response.read()
    tmp_dest = dest.with_suffix(".tmp")
    tmp_dest.write_bytes(content)
    tmp_dest.replace(dest)
    print(f"[COMPLETADO] {dest.name} ({len(content) / 1e6:.2f} MB)")
    return dest


def load_node_txt(filepath: Path) -> pd.DataFrame:
    """Carga un archivo de texto de nodo UV de manera rápida."""
    df = pd.read_csv(
        filepath,
        sep=r"\s+",
        skiprows=1,
        names=COLUMNS,
        encoding="latin-1",
        dtype=np.float32,
        engine="c",
    )
    return df


def circular_interp_deg(deg1: np.ndarray, deg2: np.ndarray, alpha: float) -> np.ndarray:
    """Interpolación circular entre dos series de direcciones en grados [0, 360)."""
    rad1 = np.deg2rad(deg1)
    rad2 = np.deg2rad(deg2)
    sin_m = (1.0 - alpha) * np.sin(rad1) + alpha * np.sin(rad2)
    cos_m = (1.0 - alpha) * np.cos(rad1) + alpha * np.cos(rad2)
    ang = np.rad2deg(np.arctan2(sin_m, cos_m)) % 360.0
    return ang.astype(np.float32)


def build_datasets(base_dir: Path):
    raw_dir = base_dir / "raw"
    proc_dir = base_dir / "processed"
    nodos_1deg_dir = base_dir / "nodos_1deg"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    nodos_1deg_dir.mkdir(parents=True, exist_ok=True)

    # 1. Descargar los 14 nodos en paralelo
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(download_single_node, n, raw_dir): n for n in UV_NODES}
        for fut in as_completed(futures):
            fut.result()

    # 2. Leer todos los nodos y verificar consistencia temporal
    print("\nLeyendo y consolidando los 14 nodos UV...")
    node_dfs = {}
    for n in UV_NODES:
        fpath = raw_dir / n["filename"]
        df = load_node_txt(fpath)
        node_dfs[n["id"]] = df
        print(f"  Nodo {n['id']:2d} ({n['name']:26s}): {len(df)} registros")

    ref_df = node_dfs[1]
    n_time = len(ref_df)
    dt_index = pd.to_datetime({
        "year": ref_df["year"].astype(int),
        "month": ref_df["month"].astype(int),
        "day": ref_df["day"].astype(int),
        "hour": ref_df["hour"].astype(int),
    })
    # Horas desde 1980-01-01 00:00:00
    time_hours = ((dt_index - pd.Timestamp("1980-01-01 00:00:00")).dt.total_seconds() / 3600.0).to_numpy(dtype=np.float64)

    vars_to_save = ["Hm0", "Tp", "Tm", "Tz", "Te", "Dm", "Dp", "s"]
    n_uv = len(UV_NODES)

    # Guardar NetCDF consolidado de los 14 nodos oficiales UV
    uv_nc_path = proc_dir / "hindcast_uv_14nodos.nc"
    with nc.Dataset(uv_nc_path, "w", format="NETCDF4") as ds:
        ds.title = "Hindcasting de Aguas Profundas Atlas de Oleaje UV (14 Nodos Costeros)"
        ds.source = "https://oleaje.uv.cl/descargas.html"
        ds.createDimension("node", n_uv)
        ds.createDimension("time", n_time)

        v_id = ds.createVariable("node_id", "i4", ("node",))
        v_lat = ds.createVariable("lat", "f4", ("node",))
        v_lon = ds.createVariable("lon", "f4", ("node",))
        v_time = ds.createVariable("time", "f8", ("time",))
        v_time.units = "hours since 1980-01-01 00:00:00"

        v_id[:] = [n["id"] for n in UV_NODES]
        v_lat[:] = [n["lat"] for n in UV_NODES]
        v_lon[:] = [n["lon"] for n in UV_NODES]
        v_time[:] = time_hours

        # Nombres como atributo separado por comas
        ds.node_names = ",".join(n["name"] for n in UV_NODES)

        for var in vars_to_save:
            v = ds.createVariable(var, "f4", ("node", "time"), zlib=False)
            arr = np.zeros((n_uv, n_time), dtype=np.float32)
            for idx, n in enumerate(UV_NODES):
                arr[idx, :] = node_dfs[n["id"]][var].to_numpy(dtype=np.float32)
            v[:] = arr

    print(f"[OK] Archivo NetCDF de 14 nodos UV guardado en: {uv_nc_path}")

    # 3. Construir la grilla de 28 boyas cada 1° (-18° a -45°S)
    print("\nConstruyendo grilla de boyas AP cada 1° de latitud (-18° a -45°S)...")
    uv_lats = np.array([n["lat"] for n in UV_NODES], dtype=np.float64)  # [-19, -21, ..., -45]
    uv_ids = [n["id"] for n in UV_NODES]

    n_1deg = len(BUOYS_1DEG)
    buoy_nc_path = proc_dir / "hindcast_ap_1deg_chile.nc"

    with nc.Dataset(buoy_nc_path, "w", format="NETCDF4") as ds:
        ds.title = "Hindcasting de Aguas Profundas cada 1 grado en Chile (-18S a -45S)"
        ds.source = "Interpolado desde Atlas de Oleaje UV (https://oleaje.uv.cl/descargas.html)"
        ds.createDimension("buoy", n_1deg)
        ds.createDimension("time", n_time)

        v_id = ds.createVariable("buoy_id", "i4", ("buoy",))
        v_lat = ds.createVariable("lat", "f4", ("buoy",))
        v_lon = ds.createVariable("lon", "f4", ("buoy",))
        v_time = ds.createVariable("time", "f8", ("time",))
        v_time.units = "hours since 1980-01-01 00:00:00"

        v_id[:] = [b["id"] for b in BUOYS_1DEG]
        v_lat[:] = [b["lat"] for b in BUOYS_1DEG]
        v_lon[:] = [b["lon"] for b in BUOYS_1DEG]
        v_time[:] = time_hours
        ds.buoy_names = ",".join(b["name"] for b in BUOYS_1DEG)

        nc_vars = {
            var: ds.createVariable(var, "f4", ("buoy", "time"), zlib=False)
            for var in vars_to_save
        }

        for b_idx, b in enumerate(BUOYS_1DEG):
            lat_target = b["lat"]
            # Determinar qué nodo(s) UV rodean a lat_target
            # Notar que uv_lats es decreciente: [-19, -21, ..., -45]
            if lat_target >= uv_lats[0]:
                # Al norte o igual a -19° (ej. -18° o -19°): usa Nodo 1
                df_interp = {var: node_dfs[uv_ids[0]][var].to_numpy(dtype=np.float32) for var in vars_to_save}
                source_desc = f"UV_Nodo_{uv_ids[0]}"
            elif lat_target <= uv_lats[-1]:
                # Al sur o igual a -45°: usa Nodo 14
                df_interp = {var: node_dfs[uv_ids[-1]][var].to_numpy(dtype=np.float32) for var in vars_to_save}
                source_desc = f"UV_Nodo_{uv_ids[-1]}"
            else:
                # Encontrar índice i tal que uv_lats[i] >= lat_target >= uv_lats[i+1]
                idx_upper = int(np.searchsorted(-uv_lats, -lat_target, side="right") - 1)
                idx_upper = max(0, min(idx_upper, len(uv_lats) - 2))
                lat1 = uv_lats[idx_upper]
                lat2 = uv_lats[idx_upper + 1]
                alpha = float((lat1 - lat_target) / (lat1 - lat2))
                id1 = uv_ids[idx_upper]
                id2 = uv_ids[idx_upper + 1]

                if abs(alpha) < 1e-6:
                    df_interp = {var: node_dfs[id1][var].to_numpy(dtype=np.float32) for var in vars_to_save}
                    source_desc = f"UV_Nodo_{id1}"
                elif abs(alpha - 1.0) < 1e-6:
                    df_interp = {var: node_dfs[id2][var].to_numpy(dtype=np.float32) for var in vars_to_save}
                    source_desc = f"UV_Nodo_{id2}"
                else:
                    df1 = node_dfs[id1]
                    df2 = node_dfs[id2]
                    df_interp = {}
                    # Conservación de energía para Hm0
                    h1 = df1["Hm0"].to_numpy(dtype=np.float32)
                    h2 = df2["Hm0"].to_numpy(dtype=np.float32)
                    df_interp["Hm0"] = np.sqrt((1.0 - alpha) * (h1 ** 2) + alpha * (h2 ** 2)).astype(np.float32)
                    # Interpolación lineal de periodos y spreading
                    for pvar in ["Tp", "Tm", "Tz", "Te", "s"]:
                        v1 = df1[pvar].to_numpy(dtype=np.float32)
                        v2 = df2[pvar].to_numpy(dtype=np.float32)
                        df_interp[pvar] = ((1.0 - alpha) * v1 + alpha * v2).astype(np.float32)
                    # Interpolación circular de direcciones
                    for dvar in ["Dm", "Dp"]:
                        d1 = df1[dvar].to_numpy(dtype=np.float32)
                        d2 = df2[dvar].to_numpy(dtype=np.float32)
                        df_interp[dvar] = circular_interp_deg(d1, d2, alpha)
                    source_desc = f"Interp_UV_{id1}_{id2}"

            b["source"] = source_desc
            for var in vars_to_save:
                nc_vars[var][b_idx, :] = df_interp[var]

            # Guardar también archivo individual .npz por boya de 1°
            npz_path = nodos_1deg_dir / f"{b['name']}_lat{int(abs(b['lat']))}S.npz"
            np.savez(
                npz_path,
                lat=np.float32(b["lat"]),
                lon=np.float32(b["lon"]),
                time_hours=time_hours,
                **df_interp,
            )

    # Guardar catálogos CSV
    pd.DataFrame(UV_NODES).to_csv(base_dir / "catalogo_nodos_uv.csv", index=False)
    pd.DataFrame(BUOYS_1DEG).to_csv(base_dir / "catalogo_boyas_1deg.csv", index=False)
    print(f"[OK] Grilla de 28 boyas cada 1° guardada en: {buoy_nc_path}")
    print(f"[OK] Catálogos guardados en: {base_dir}")


if __name__ == "__main__":
    base_path = Path(__file__).resolve().parent
    build_datasets(base_path)
