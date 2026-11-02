#!/usr/bin/env python3
"""
Ensamblador de la Matriz de Transferencia de Oleaje para Chile (chile_250k).
Lee los archivos .mat generados por los workers de SWAN en trabajo_swan/workers/
(o trabajo_swan/DataSet/), ordena las dimensiones (period, direction, node) y
construye el archivo consolidado NetCDF4:
  /home/model2/luis/oleaje_chile/superSimple/trabajo_swan/matrices/matriz_transferencia_chile.nc

Soporta ensamblado parcial o completo: si algún ángulo intermedio (ej. múltiplo impar de 5°)
aún está en cálculo, interpola temporalmente desde los ángulos adyacentes ya calculados
y marca el atributo de completitud, o ensambla el 100% de los casos terminados.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import scipy.io as sio
import netCDF4 as nc

TRABAJO_DIR = Path(__file__).resolve().parent
MESH_DIR = TRABAJO_DIR.parent / "modelo_pronostico" / "malla"
OUT_NC = TRABAJO_DIR / "matrices" / "matriz_transferencia_chile.nc"


def load_mesh_geometry():
    """Lee coordenadas nodales (lon, lat), batimetría (depth) y conectividad (triangles) de chile_250k."""
    node_data = np.loadtxt(MESH_DIR / "chile_250k.node", skiprows=1, dtype=np.float64)
    lon = node_data[:, 1]
    lat = node_data[:, 2]

    bot_data = np.loadtxt(MESH_DIR / "chile_250k.bot", dtype=np.float32)
    # En chile_250k.bot las profundidades están con signo negativo (-h) y factor -1.0 en SWAN
    depth = np.abs(bot_data)

    ele_data = np.loadtxt(MESH_DIR / "chile_250k.ele", skiprows=1, dtype=np.int32)
    triangles = ele_data[:, 1:4] - 1  # 0-based

    return lon, lat, depth, triangles


def build_consolidated_netcdf(cat_csv: Path = TRABAJO_DIR / "casos_catalogo.csv", out_nc: Path = OUT_NC):
    cat_df = pd.read_csv(cat_csv)
    lon, lat, depth, triangles = load_mesh_geometry()
    n_nodes = len(lon)
    n_tris = len(triangles)

    periods = np.sort(cat_df["period"].unique()).astype(np.float32)
    directions = np.sort(cat_df["direction"].unique()).astype(np.float32)
    n_p = len(periods)
    n_d = len(directions)

    p_to_idx = {float(p): i for i, p in enumerate(periods)}
    d_to_idx = {float(d): j for j, d in enumerate(directions)}

    ka_tensor = np.full((n_p, n_d, n_nodes), np.nan, dtype=np.float32)
    dir_tensor = np.full((n_p, n_d, n_nodes), np.nan, dtype=np.float32)
    pkdir_tensor = np.full((n_p, n_d, n_nodes), np.nan, dtype=np.float32)

    loaded_cases = 0
    total_cases = len(cat_df)

    for w_name, group in cat_df.groupby("worker"):
        mat_path = Path(group.iloc[0]["out_mat"])
        if not mat_path.exists():
            continue
        try:
            m = sio.loadmat(mat_path)
        except Exception as e:
            print(f"[WARN] Error leyendo {mat_path}: {e}")
            continue

        for _, row in group.iterrows():
            i_p = p_to_idx[float(row["period"])]
            j_d = d_to_idx[float(row["direction"])]
            suf = row["mat_suffix"]
            k_hs = f"Hsig_{suf}"
            k_dir = f"Dir_{suf}"
            k_pk = f"PkDir_{suf}"

            if k_hs in m and k_dir in m:
                hs = np.asarray(m[k_hs], dtype=np.float32).ravel()
                dr = np.asarray(m[k_dir], dtype=np.float32).ravel()
                pk = np.asarray(m.get(k_pk, m[k_dir]), dtype=np.float32).ravel()

                # Limpiar posibles NaNs o valores fuera de rango en nodos secos
                hs = np.where(np.isfinite(hs) & (hs >= 0.0) & (hs < 10.0), hs, 0.0)
                dr = np.where(np.isfinite(dr), dr % 360.0, float(row["direction"]) % 360.0)
                pk = np.where(np.isfinite(pk), pk % 360.0, dr)

                ka_tensor[i_p, j_d, :] = hs
                dir_tensor[i_p, j_d, :] = dr
                pkdir_tensor[i_p, j_d, :] = pk
                loaded_cases += 1

    print(f"[ENSAMBLADOR] Casos leídos directamente desde SWAN: {loaded_cases}/{total_cases}")

    # Si existen direcciones intermedias aún no completadas, interpolar a lo largo del eje direccional
    for i_p in range(n_p):
        valid_mask = ~np.isnan(ka_tensor[i_p, :, 0])
        if np.all(valid_mask):
            continue
        if not np.any(valid_mask):
            raise RuntimeError(f"El periodo T={periods[i_p]}s no tiene ningún caso completado.")

        valid_j = np.where(valid_mask)[0]
        missing_j = np.where(~valid_mask)[0]
        valid_dirs = directions[valid_j]

        for j_miss in missing_j:
            d_target = directions[j_miss]
            # Buscar vecinos direccionales más cercanos en valid_j
            idx_right = int(np.searchsorted(valid_dirs, d_target))
            if idx_right == 0:
                j0 = j1 = valid_j[0]
                alpha = 0.0
            elif idx_right >= len(valid_dirs):
                j0 = j1 = valid_j[-1]
                alpha = 0.0
            else:
                j0 = valid_j[idx_right - 1]
                j1 = valid_j[idx_right]
                alpha = float((d_target - directions[j0]) / (directions[j1] - directions[j0]))

            ka_tensor[i_p, j_miss, :] = (1.0 - alpha) * ka_tensor[i_p, j0, :] + alpha * ka_tensor[i_p, j1, :]

            r0 = np.deg2rad(dir_tensor[i_p, j0, :])
            r1 = np.deg2rad(dir_tensor[i_p, j1, :])
            s_m = (1.0 - alpha) * np.sin(r0) + alpha * np.sin(r1)
            c_m = (1.0 - alpha) * np.cos(r0) + alpha * np.cos(r1)
            dir_tensor[i_p, j_miss, :] = (np.rad2deg(np.arctan2(s_m, c_m)) % 360.0).astype(np.float32)

            pr0 = np.deg2rad(pkdir_tensor[i_p, j0, :])
            pr1 = np.deg2rad(pkdir_tensor[i_p, j1, :])
            ps_m = (1.0 - alpha) * np.sin(pr0) + alpha * np.sin(pr1)
            pc_m = (1.0 - alpha) * np.cos(pr0) + alpha * np.cos(pr1)
            pkdir_tensor[i_p, j_miss, :] = (np.rad2deg(np.arctan2(ps_m, pc_m)) % 360.0).astype(np.float32)

    out_nc.parent.mkdir(parents=True, exist_ok=True)
    tmp_nc = out_nc.with_suffix(".tmp.nc")

    with nc.Dataset(tmp_nc, "w", format="NETCDF4") as ds:
        ds.title = "Matriz de Transferencia de Oleaje de Chile (SWAN chile_250k)"
        ds.swan_cases_loaded = int(loaded_cases)
        ds.swan_cases_total = int(total_cases)

        ds.createDimension("period", n_p)
        ds.createDimension("direction", n_d)
        ds.createDimension("node", n_nodes)
        ds.createDimension("triangle", n_tris)
        ds.createDimension("three", 3)

        vp = ds.createVariable("period", "f4", ("period",))
        vf = ds.createVariable("frequency", "f4", ("period",))
        vd = ds.createVariable("direction", "f4", ("direction",))
        vlon = ds.createVariable("lon", "f8", ("node",))
        vlat = ds.createVariable("lat", "f8", ("node",))
        vdep = ds.createVariable("depth", "f4", ("node",))
        vtri = ds.createVariable("triangles", "i4", ("triangle", "three"))

        vka = ds.createVariable("Ka", "f4", ("period", "direction", "node"), zlib=False)
        vdir = ds.createVariable("Dir", "f4", ("period", "direction", "node"), zlib=False)
        vpk = ds.createVariable("PkDir", "f4", ("period", "direction", "node"), zlib=False)

        vp[:] = periods
        vf[:] = (1.0 / periods).astype(np.float32)
        vd[:] = directions
        vlon[:] = lon
        vlat[:] = lat
        vdep[:] = depth
        vtri[:] = triangles

        vka[:] = ka_tensor
        vdir[:] = dir_tensor
        vpk[:] = pkdir_tensor

    tmp_nc.replace(out_nc)
    print(f"[OK] Matriz de transferencia guardada exitosamente en: {out_nc} ({out_nc.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    build_consolidated_netcdf()
