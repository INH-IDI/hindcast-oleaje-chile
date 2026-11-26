"""
Módulo de Reanálisis ERA5 (ECMWF / Copernicus Climate Data Store - CDS API)
para forzamiento histórico de oleaje en Aguas Profundas (1940 - presente,
resolución nativa horaria) y propagación con Matrices de Transferencia SWAN.
"""

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple
import zipfile

import netCDF4 as nc
import numpy as np
import pandas as pd

from .catalog import load_buoy_catalog


DEFAULT_CDS_URL = "https://cds.climate.copernicus.eu/api"
ERA5_DATASET = "reanalysis-era5-single-levels"
ERA5_WAVE_VARIABLES = [
    "significant_height_of_combined_wind_waves_and_swell",
    "peak_wave_period",
    "mean_wave_period",
    "mean_zero_crossing_wave_period",
    "mean_wave_direction",
]
# [North, West, South, East] cubriendo toda la red de boyas AP chilenas (-18° a -45°S, -72° a -76°W)
CHILE_ERA5_AREA = [-17.5, -77.0, -45.5, -71.0]
DEFAULT_ERA5_CACHE_DIR = Path(__file__).resolve().parents[1] / "era5_cache"
ERA5_MIN_DATE = "1940-01-01"
ALL_WAVE_VARS = ["Hm0", "Tp", "Tm", "Tz", "Te", "Dm", "Dp", "s"]


@dataclass
class ERA5Credentials:
    """Credenciales de cuenta Copernicus CDS para descarga de ERA5."""

    url: str = DEFAULT_CDS_URL
    key: Optional[str] = None
    source: str = "none"  # 'explicit', 'env', 'cdsapirc', 'none'

    @property
    def is_configured(self) -> bool:
        return bool(self.key and str(self.key).strip() and self.url and str(self.url).strip())


def get_cdsapirc_path(rc_path: Optional[Path] = None) -> Path:
    """Retorna la ruta efectiva del archivo de credenciales .cdsapirc."""
    if rc_path is not None:
        return Path(rc_path)
    env_rc = os.getenv("CDSAPI_RC")
    if env_rc:
        return Path(env_rc).expanduser()
    return Path.home() / ".cdsapirc"


def read_cdsapirc(rc_path: Optional[Path] = None) -> Optional[ERA5Credentials]:
    """Lee credenciales desde ~/.cdsapirc (soporta token moderno o formato uid:key)."""
    path = get_cdsapirc_path(rc_path)
    if not path.exists() or not path.is_file():
        return None

    url_val: Optional[str] = None
    key_val: Optional[str] = None

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k_clean = k.strip().lower()
        v_clean = v.strip()
        if k_clean == "url" and v_clean:
            url_val = v_clean
        elif k_clean == "key" and v_clean:
            key_val = v_clean

    if not key_val:
        return None

    return ERA5Credentials(
        url=url_val or DEFAULT_CDS_URL,
        key=key_val,
        source="cdsapirc",
    )


def resolve_era5_credentials(
    cds_url: Optional[str] = None,
    cds_key: Optional[str] = None,
    rc_path: Optional[Path] = None,
) -> ERA5Credentials:
    """
    Resuelve credenciales CDS según prioridad:
      1. Parámetros explícitos (`cds_key`)
      2. Variables de entorno (`CDSAPI_KEY`, `CDSAPI_URL`)
      3. Archivo `~/.cdsapirc` (o `CDSAPI_RC` / `rc_path`)
      4. Sin configurar (`source='none'`)
    """
    rc_creds = read_cdsapirc(rc_path=rc_path)
    env_url = os.getenv("CDSAPI_URL")
    env_key = os.getenv("CDSAPI_KEY")

    resolved_url = (
        (cds_url.strip() if cds_url and cds_url.strip() else None)
        or (env_url.strip() if env_url and env_url.strip() else None)
        or (rc_creds.url if rc_creds else None)
        or DEFAULT_CDS_URL
    )

    if cds_key and cds_key.strip():
        return ERA5Credentials(url=resolved_url, key=cds_key.strip(), source="explicit")
    if env_key and env_key.strip():
        return ERA5Credentials(url=resolved_url, key=env_key.strip(), source="env")
    if rc_creds and rc_creds.is_configured:
        return ERA5Credentials(url=resolved_url, key=rc_creds.key, source="cdsapirc")
    return ERA5Credentials(url=resolved_url, key=None, source="none")


def save_cdsapirc(
    key: str,
    url: str = DEFAULT_CDS_URL,
    rc_path: Optional[Path] = None,
) -> Path:
    """Guarda las credenciales Copernicus CDS en ~/.cdsapirc con permisos restringidos."""
    key_clean = (key or "").strip()
    url_clean = (url or "").strip() or DEFAULT_CDS_URL
    if not key_clean:
        raise ValueError("El API Key / Personal Access Token de Copernicus CDS no puede estar vacío.")
    if not url_clean:
        raise ValueError("La URL del servidor Copernicus CDS no puede estar vacía.")

    path = get_cdsapirc_path(rc_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"url: {url_clean}\nkey: {key_clean}\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


class DeepWaterERA5DB:
    """
    Estructura de datos en memoria para series de tiempo ERA5 en aguas profundas (AP).
    Provee la misma interfaz que DeepWaterHindcastDB y DeepWaterForecastDB.
    """

    def __init__(
        self,
        ids: np.ndarray,
        lats: np.ndarray,
        lons: np.ndarray,
        names: List[str],
        timestamps: pd.DatetimeIndex,
        data: Dict[str, np.ndarray],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.ids = np.array(ids, dtype=np.int32)
        self.lats = np.array(lats, dtype=np.float64)
        self.lons = np.array(lons, dtype=np.float64)
        self.names = list(names)
        self.timestamps = pd.DatetimeIndex(timestamps)
        if self.timestamps.tz is not None:
            self.timestamps = self.timestamps.tz_convert("UTC").tz_localize(None)
        self.data = {k: np.array(v, dtype=np.float32) for k, v in data.items()}
        self.metadata = dict(metadata or {})

    def subset_time_slice(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> slice:
        if len(self.timestamps) == 0:
            return slice(0, 0)
        if start_date is None and end_date is None:
            return slice(None)
        t0 = pd.Timestamp(start_date) if start_date else self.timestamps[0]
        if t0.tz is not None:
            t0 = t0.tz_convert("UTC").tz_localize(None)

        if end_date is not None:
            t1 = pd.Timestamp(end_date)
            if t1.tz is not None:
                t1 = t1.tz_convert("UTC").tz_localize(None)
            # Si end_date se entrega sin hora (YYYY-MM-DD), incluir el día completo hasta 23:59:59
            if isinstance(end_date, str) and len(end_date.strip()) <= 10 and t1.hour == 0 and t1.minute == 0 and t1.second == 0:
                t1 = t1 + pd.Timedelta(hours=23, minutes=59, seconds=59)
        else:
            t1 = self.timestamps[-1]

        i0 = int(self.timestamps.searchsorted(t0, side="left"))
        i1 = int(self.timestamps.searchsorted(t1, side="right"))
        return slice(max(0, i0), min(len(self.timestamps), i1))

    def subset(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> "DeepWaterERA5DB":
        """Retorna una nueva instancia recortada al rango temporal solicitado."""
        t_slice = self.subset_time_slice(start_date, end_date)
        sub_times = self.timestamps[t_slice]
        sub_data = {k: v[:, t_slice].copy() for k, v in self.data.items()}
        sub_meta = dict(self.metadata)
        if len(sub_times) > 0:
            sub_meta["era5_start"] = str(sub_times[0])
            sub_meta["era5_end"] = str(sub_times[-1])
        sub_meta["n_records"] = int(len(sub_times))
        return DeepWaterERA5DB(
            ids=self.ids.copy(),
            lats=self.lats.copy(),
            lons=self.lons.copy(),
            names=list(self.names),
            timestamps=sub_times,
            data=sub_data,
            metadata=sub_meta,
        )

    def save_npz(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        t_strings = self.timestamps.strftime("%Y-%m-%d %H:%M:%S").to_numpy(dtype="U25")
        names_arr = np.array(self.names, dtype="U60")

        save_dict: Dict[str, Any] = {
            "buoy_ids": self.ids,
            "lats": self.lats,
            "lons": self.lons,
            "names": names_arr,
            "timestamps": t_strings,
        }
        for var in ALL_WAVE_VARS:
            if var in self.data:
                save_dict[var] = self.data[var]

        for k, v in self.metadata.items():
            if isinstance(v, (str, int, float, bool)):
                save_dict[f"meta_{k}"] = np.array(str(v), dtype="U300")

        tmp_path = path.with_name(path.name + ".tmp.npz")
        np.savez_compressed(tmp_path, **save_dict)
        tmp_path.replace(path)

    @classmethod
    def from_npz(cls, path: Path) -> "DeepWaterERA5DB":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"No existe el archivo de caché ERA5 en {path}")

        with np.load(path, allow_pickle=False) as d:
            ids = d["buoy_ids"].astype(np.int32)
            lats = d["lats"].astype(np.float64)
            lons = d["lons"].astype(np.float64)
            names = [str(s) for s in d["names"]]
            t_raw = [str(s) for s in d["timestamps"]]
            timestamps = pd.to_datetime(t_raw)

            data = {}
            for var in ALL_WAVE_VARS:
                if var in d.files:
                    data[var] = d[var].astype(np.float32)

            metadata = {}
            for k in d.files:
                if k.startswith("meta_"):
                    metadata[k[5:]] = str(d[k])

        return cls(ids, lats, lons, names, timestamps, data, metadata)

    @classmethod
    def merge(cls, dbs: List["DeepWaterERA5DB"]) -> "DeepWaterERA5DB":
        """Concatena múltiples bloques temporales ERA5 ordenando y deduplicando timestamps."""
        non_empty = [db for db in dbs if len(db.timestamps) > 0]
        if not non_empty:
            raise ValueError("No hay registros temporales ERA5 disponibles para combinar.")

        ref = non_empty[0]
        for db in non_empty[1:]:
            if len(db.ids) != len(ref.ids) or not np.array_equal(db.ids, ref.ids):
                raise ValueError("Las grillas de boyas no coinciden entre los bloques ERA5 a combinar.")

        all_times = pd.DatetimeIndex(np.concatenate([db.timestamps.to_numpy() for db in non_empty]))
        # Ordenar y conservar el último valor ante timestamps duplicados
        order = np.argsort(all_times.to_numpy(), kind="mergesort")
        sorted_times = all_times[order]

        # Para conservar el último en duplicados: invertir, unique con return_index, volver a invertir
        rev_times = sorted_times[::-1]
        _, rev_idx = np.unique(rev_times.to_numpy(), return_index=True)
        keep_pos = (len(sorted_times) - 1) - rev_idx
        keep_pos = np.sort(keep_pos)
        final_idx = order[keep_pos]
        final_times = all_times[final_idx]

        common_vars = set(ref.data.keys())
        for db in non_empty[1:]:
            common_vars &= set(db.data.keys())

        merged_data: Dict[str, np.ndarray] = {}
        for var in ALL_WAVE_VARS:
            if var in common_vars:
                concat_arr = np.concatenate([db.data[var] for db in non_empty], axis=1)
                merged_data[var] = concat_arr[:, final_idx].astype(np.float32)

        meta = dict(ref.metadata)
        for db in non_empty[1:]:
            meta.update(db.metadata)
        meta["era5_start"] = str(final_times[0])
        meta["era5_end"] = str(final_times[-1])
        meta["n_records"] = int(len(final_times))

        return cls(
            ids=ref.ids.copy(),
            lats=ref.lats.copy(),
            lons=ref.lons.copy(),
            names=list(ref.names),
            timestamps=final_times,
            data=merged_data,
            metadata=meta,
        )


def _to_nan_float32(arr: Any) -> np.ndarray:
    """Convierte arreglo NetCDF (posiblemente MaskedArray) a float32 con NaN."""
    if np.ma.isMaskedArray(arr):
        return np.ma.filled(arr.astype(np.float32), np.nan)
    return np.asarray(arr, dtype=np.float32)


def _extract_time_index(ds: nc.Dataset) -> pd.DatetimeIndex:
    """Extrae el índice temporal naive UTC desde variables 'valid_time' o 'time'."""
    t_name = "valid_time" if "valid_time" in ds.variables else ("time" if "time" in ds.variables else None)
    if t_name is None:
        raise ValueError("El archivo NetCDF ERA5 no contiene variable temporal ('valid_time' ni 'time').")

    v_time = ds.variables[t_name]
    raw_vals = np.asarray(v_time[:])
    units = getattr(v_time, "units", None)
    calendar_attr = getattr(v_time, "calendar", "standard")

    if units:
        dt_objs = nc.num2date(raw_vals, units=units, calendar=calendar_attr)
        iso_strs = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in np.atleast_1d(dt_objs)]
        return pd.to_datetime(iso_strs)
    return pd.to_datetime(raw_vals, unit="s")


def _extract_var_3d(ds: nc.Dataset, var_name: str, time_name: str, lat_name: str, lon_name: str) -> np.ndarray:
    """
    Lee una variable NetCDF ERA5 y garantiza forma (T, Lat, Lon),
    colapsando automáticamente la dimensión 'expver' si existe.
    """
    var = ds.variables[var_name]
    dims = list(var.dimensions)
    arr = _to_nan_float32(var[:])

    if "expver" in dims:
        exp_axis = dims.index("expver")
        arr = np.moveaxis(arr, exp_axis, 0)
        dims_no_exp = [d for d in dims if d != "expver"]
        collapsed = arr[0].copy()
        for e_i in range(1, arr.shape[0]):
            mask = ~np.isfinite(collapsed)
            if not np.any(mask):
                break
            collapsed[mask] = arr[e_i][mask]
        arr = collapsed
        dims = dims_no_exp

    if arr.ndim != 3:
        raise ValueError(f"Dimensiones inesperadas para variable ERA5 '{var_name}': {var.dimensions}")

    # Reordenar a (time, lat, lon) si viniera en otro orden
    target_order = [dims.index(time_name), dims.index(lat_name), dims.index(lon_name)]
    if target_order != [0, 1, 2]:
        arr = np.transpose(arr, axes=target_order)
    return arr


def _interp_1d_linear(vals: np.ndarray) -> np.ndarray:
    """Rellena NaNs aislados en una serie 1D mediante interpolación lineal y bordes."""
    s = pd.Series(vals.astype(np.float64))
    if s.isna().all():
        return vals.astype(np.float32)
    return s.interpolate(method="linear").bfill().ffill().to_numpy(dtype=np.float32)


def _interp_1d_circular_deg(deg_vals: np.ndarray) -> np.ndarray:
    """Rellena NaNs en direcciones [0, 360) usando interpolación circular sin/cos."""
    valid = np.isfinite(deg_vals)
    if np.all(valid):
        return (deg_vals % 360.0).astype(np.float32)
    if not np.any(valid):
        return deg_vals.astype(np.float32)

    rad = np.deg2rad(deg_vals.astype(np.float64))
    sin_s = pd.Series(np.where(valid, np.sin(rad), np.nan)).interpolate().bfill().ffill().to_numpy()
    cos_s = pd.Series(np.where(valid, np.cos(rad), np.nan)).interpolate().bfill().ffill().to_numpy()
    return (np.rad2deg(np.arctan2(sin_s, cos_s)) % 360.0).astype(np.float32)


def _parse_single_era5_nc(
    nc_path: Path,
    buoy_mode: str = "1deg",
    metadata: Optional[Dict[str, Any]] = None,
) -> DeepWaterERA5DB:
    """Lee un archivo NetCDF ERA5 individual y extrae series en las boyas AP."""
    df_buoys = load_buoy_catalog(mode=buoy_mode)

    with nc.Dataset(nc_path, "r") as ds:
        time_name = "valid_time" if "valid_time" in ds.variables else ("time" if "time" in ds.variables else None)
        lat_name = "latitude" if "latitude" in ds.variables else ("lat" if "lat" in ds.variables else None)
        lon_name = "longitude" if "longitude" in ds.variables else ("lon" if "lon" in ds.variables else None)

        if time_name is None or lat_name is None or lon_name is None:
            raise ValueError(
                f"Archivo ERA5 inválido ({nc_path.name}): faltan coordenadas (time/latitude/longitude)."
            )

        times = _extract_time_index(ds)
        lats_grid = np.asarray(ds.variables[lat_name][:], dtype=np.float64)
        lons_raw = np.asarray(ds.variables[lon_name][:], dtype=np.float64)
        lons_grid = ((lons_raw + 180.0) % 360.0) - 180.0

        avail_vars = set(ds.variables.keys())
        if "swh" not in avail_vars:
            raise ValueError(
                f"El archivo ERA5 ({nc_path.name}) no contiene 'swh' "
                "(significant_height_of_combined_wind_waves_and_swell)."
            )
        if "mwd" not in avail_vars:
            raise ValueError(
                f"El archivo ERA5 ({nc_path.name}) no contiene 'mwd' (mean_wave_direction)."
            )

        fields: Dict[str, np.ndarray] = {}
        for v_key in ["swh", "pp1d", "mwp", "mp1", "mp2", "mwd"]:
            if v_key in avail_vars:
                fields[v_key] = _extract_var_3d(ds, v_key, time_name, lat_name, lon_name)

    # Ordenar cronológicamente si no viniera ordenado
    if len(times) > 1 and not times.is_monotonic_increasing:
        t_order = np.argsort(times.to_numpy(), kind="mergesort")
        times = times[t_order]
        fields = {k: v[t_order, :, :] for k, v in fields.items()}

    swh_3d = fields["swh"]
    ocean_mask = np.any(np.isfinite(swh_3d), axis=0)  # (n_lat, n_lon)
    if not np.any(ocean_mask):
        raise ValueError(f"El archivo ERA5 ({nc_path.name}) no contiene celdas oceánicas válidas para 'swh'.")

    lon_2d, lat_2d = np.meshgrid(lons_grid, lats_grid)
    ocean_iy, ocean_ix = np.where(ocean_mask)
    ocean_lons = lon_2d[ocean_iy, ocean_ix]
    ocean_lats = lat_2d[ocean_iy, ocean_ix]

    n_buoys = len(df_buoys)
    n_times = len(times)

    hm0 = np.zeros((n_buoys, n_times), dtype=np.float32)
    tp = np.zeros((n_buoys, n_times), dtype=np.float32)
    tm = np.zeros((n_buoys, n_times), dtype=np.float32)
    te = np.zeros((n_buoys, n_times), dtype=np.float32)
    tz = np.zeros((n_buoys, n_times), dtype=np.float32)
    dm = np.zeros((n_buoys, n_times), dtype=np.float32)

    for b_i, (_, b_row) in enumerate(df_buoys.iterrows()):
        b_lat = float(b_row["lat"])
        b_lon = ((float(b_row["lon"]) + 180.0) % 360.0) - 180.0
        cos_lat = np.cos(np.deg2rad(b_lat))
        dist2 = ((ocean_lons - b_lon) * cos_lat) ** 2 + (ocean_lats - b_lat) ** 2
        best = int(np.argmin(dist2))
        iy = int(ocean_iy[best])
        ix = int(ocean_ix[best])

        hm0_b = _interp_1d_linear(fields["swh"][:, iy, ix])
        dm_b = _interp_1d_circular_deg(fields["mwd"][:, iy, ix])

        if "pp1d" in fields and np.any(np.isfinite(fields["pp1d"][:, iy, ix])):
            tp_b = _interp_1d_linear(fields["pp1d"][:, iy, ix])
        elif "mwp" in fields:
            tp_b = (_interp_1d_linear(fields["mwp"][:, iy, ix]) / 0.85).astype(np.float32)
        else:
            raise ValueError(f"El archivo ERA5 ({nc_path.name}) no contiene periodo ('pp1d' ni 'mwp').")

        if "mwp" in fields and np.any(np.isfinite(fields["mwp"][:, iy, ix])):
            mwp_b = _interp_1d_linear(fields["mwp"][:, iy, ix])
        else:
            mwp_b = (tp_b * 0.90).astype(np.float32)

        if "mp1" in fields and np.any(np.isfinite(fields["mp1"][:, iy, ix])):
            tm_b = _interp_1d_linear(fields["mp1"][:, iy, ix])
        elif "mwp" in fields:
            tm_b = mwp_b
        else:
            tm_b = (tp_b * 0.85).astype(np.float32)

        if "mp2" in fields and np.any(np.isfinite(fields["mp2"][:, iy, ix])):
            tz_b = _interp_1d_linear(fields["mp2"][:, iy, ix])
        else:
            tz_b = (tp_b * 0.78).astype(np.float32)

        hm0[b_i, :] = np.maximum(hm0_b, 0.0)
        tp[b_i, :] = np.maximum(tp_b, 1.0)
        tm[b_i, :] = np.maximum(tm_b, 1.0)
        te[b_i, :] = np.maximum(mwp_b, 1.0)
        tz[b_i, :] = np.maximum(tz_b, 1.0)
        dm[b_i, :] = dm_b

    s_spread = np.full_like(hm0, 10.0, dtype=np.float32)

    dt_step = 1
    if len(times) >= 2:
        dt_step = max(1, int(round(float(np.median(np.diff(times).astype("timedelta64[s]").astype(np.float64))) / 3600.0)))

    meta = {
        "source": "ECMWF ERA5 (Copernicus CDS)",
        "dataset": ERA5_DATASET,
        "buoy_mode": buoy_mode,
        "step_hours": str(dt_step),
        "era5_start": str(times[0]) if len(times) > 0 else "",
        "era5_end": str(times[-1]) if len(times) > 0 else "",
        "n_records": str(n_times),
    }
    if metadata:
        meta.update(metadata)

    return DeepWaterERA5DB(
        ids=df_buoys["id"].to_numpy(dtype=np.int32),
        lats=df_buoys["lat"].to_numpy(dtype=np.float64),
        lons=df_buoys["lon"].to_numpy(dtype=np.float64),
        names=df_buoys["name"].tolist(),
        timestamps=times,
        data={
            "Hm0": hm0,
            "Tp": tp,
            "Tm": tm,
            "Tz": tz,
            "Te": te,
            "Dm": dm,
            "Dp": dm.copy(),
            "s": s_spread,
        },
        metadata=meta,
    )


def parse_era5_netcdf_to_db(
    nc_or_zip_path: Path,
    buoy_mode: str = "1deg",
    metadata: Optional[Dict[str, Any]] = None,
) -> DeepWaterERA5DB:
    """
    Parsea un archivo ERA5 descargado de CDS (.nc o .zip conteniendo múltiples .nc)
    a una instancia de DeepWaterERA5DB en las boyas de aguas profundas chilenas.
    """
    src_path = Path(nc_or_zip_path)
    if not src_path.exists():
        raise FileNotFoundError(f"No existe el archivo ERA5: {src_path}")

    if zipfile.is_zipfile(src_path):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(src_path, "r") as zf:
                zf.extractall(tmp_dir)
            nc_files = sorted(Path(tmp_dir).rglob("*.nc"))
            if not nc_files:
                raise ValueError(f"El archivo ZIP ERA5 ({src_path.name}) no contiene archivos .nc.")
            dbs = [_parse_single_era5_nc(nc_f, buoy_mode=buoy_mode, metadata=metadata) for nc_f in nc_files]
            return DeepWaterERA5DB.merge(dbs)

    return _parse_single_era5_nc(src_path, buoy_mode=buoy_mode, metadata=metadata)


class ERA5WaveClient:
    """
    Cliente para descarga autenticada (cuenta Copernicus CDS), parseo y caché mensual
    de reanálisis de oleaje ERA5 (`reanalysis-era5-single-levels`).
    """

    def __init__(
        self,
        cds_url: Optional[str] = None,
        cds_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        rc_path: Optional[Path] = None,
    ):
        self.cds_url = cds_url
        self.cds_key = cds_key
        self.rc_path = Path(rc_path) if rc_path is not None else None
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_ERA5_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_credentials(self) -> ERA5Credentials:
        return resolve_era5_credentials(
            cds_url=self.cds_url,
            cds_key=self.cds_key,
            rc_path=self.rc_path,
        )

    def get_month_cache_path(
        self,
        buoy_mode: str,
        year: int,
        month: int,
        step_hours: int = 1,
    ) -> Path:
        return self.cache_dir / f"era5_{buoy_mode}_{year:04d}_{month:02d}_{int(step_hours)}h.npz"

    @staticmethod
    def build_month_plan(start_date: str, end_date: str) -> List[Tuple[int, int, List[str]]]:
        """Descompone [start_date, end_date] en bloques mensuales (year, month, days_str_list)."""
        t0 = pd.Timestamp(start_date).normalize()
        t1 = pd.Timestamp(end_date).normalize()
        if t0.tz is not None:
            t0 = t0.tz_convert("UTC").tz_localize(None)
        if t1.tz is not None:
            t1 = t1.tz_convert("UTC").tz_localize(None)

        min_dt = pd.Timestamp(ERA5_MIN_DATE)
        if t0 < min_dt:
            raise ValueError(f"ERA5 está disponible desde {ERA5_MIN_DATE}; fecha inicio recibida: {start_date}")
        if t1 < t0:
            raise ValueError(f"La fecha de término ({end_date}) no puede ser anterior al inicio ({start_date}).")

        plan: List[Tuple[int, int, List[str]]] = []
        cur_y, cur_m = int(t0.year), int(t0.month)
        while (cur_y, cur_m) <= (int(t1.year), int(t1.month)):
            last_dom = calendar.monthrange(cur_y, cur_m)[1]
            d_start = int(t0.day) if (cur_y, cur_m) == (int(t0.year), int(t0.month)) else 1
            d_end = int(t1.day) if (cur_y, cur_m) == (int(t1.year), int(t1.month)) else last_dom
            days = [f"{d:02d}" for d in range(d_start, d_end + 1)]
            plan.append((cur_y, cur_m, days))
            if cur_m == 12:
                cur_y += 1
                cur_m = 1
            else:
                cur_m += 1
        return plan

    def _is_month_cached_for_days(
        self,
        buoy_mode: str,
        year: int,
        month: int,
        days: List[str],
        step_hours: int,
    ) -> bool:
        c_path = self.get_month_cache_path(buoy_mode, year, month, step_hours)
        if not c_path.exists():
            return False
        try:
            with np.load(c_path, allow_pickle=False) as d:
                if "timestamps" not in d.files or len(d["timestamps"]) == 0:
                    return False
                ts = pd.to_datetime([str(s) for s in d["timestamps"]])
        except Exception:
            return False

        d_first = pd.Timestamp(f"{year:04d}-{month:02d}-{days[0]} 00:00:00")
        d_last = pd.Timestamp(f"{year:04d}-{month:02d}-{days[-1]} 00:00:00")
        tol_last = pd.Timestamp(f"{year:04d}-{month:02d}-{days[-1]} {24 - int(step_hours):02d}:00:00")
        return bool(ts[0] <= d_first + pd.Timedelta(hours=int(step_hours)) and ts[-1] >= tol_last)

    def check_cache_coverage(
        self,
        buoy_mode: str,
        start_date: str,
        end_date: str,
        step_hours: int = 1,
    ) -> Tuple[bool, List[Tuple[int, int, List[str]]]]:
        """Verifica si todo el rango solicitado está cubierto en el caché mensual local."""
        plan = self.build_month_plan(start_date, end_date)
        missing: List[Tuple[int, int, List[str]]] = []
        for year, month, days in plan:
            if not self._is_month_cached_for_days(buoy_mode, year, month, days, step_hours):
                missing.append((year, month, days))
        return (len(missing) == 0), missing

    def list_cached_ranges(
        self,
        buoy_mode: str = "1deg",
        step_hours: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Lista los bloques mensuales ERA5 disponibles actualmente en el caché local."""
        pattern = re.compile(rf"^era5_{re.escape(buoy_mode)}_(\d{{4}})_(\d{{2}})_(\d+)h\.npz$")
        entries: List[Dict[str, Any]] = []
        if not self.cache_dir.exists():
            return entries

        for p in sorted(self.cache_dir.glob(f"era5_{buoy_mode}_*.npz")):
            m = pattern.match(p.name)
            if not m:
                continue
            y, mo, sh = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if step_hours is not None and sh != int(step_hours):
                continue
            try:
                with np.load(p, allow_pickle=False) as d:
                    ts = d["timestamps"]
                    n_rec = int(len(ts))
                    t_start = str(ts[0]) if n_rec > 0 else ""
                    t_end = str(ts[-1]) if n_rec > 0 else ""
                entries.append({
                    "path": p,
                    "year": y,
                    "month": mo,
                    "step_hours": sh,
                    "start": t_start,
                    "end": t_end,
                    "n_records": n_rec,
                })
            except Exception:
                continue
        return entries

    @staticmethod
    def _group_missing_requests(
        missing: List[Tuple[int, int, List[str]]],
    ) -> List[Tuple[int, List[int], List[str]]]:
        """
        Agrupa meses faltantes consecutivos del mismo año que tienen el mes completo
        para reducir la cantidad de envíos a la cola del CDS.
        """
        groups: List[Tuple[int, List[int], List[str]]] = []
        for year, month, days in missing:
            is_full_month = len(days) == calendar.monthrange(year, month)[1]
            if groups:
                prev_y, prev_months, prev_days = groups[-1]
                prev_full = len(prev_days) == calendar.monthrange(prev_y, prev_months[-1])[1]
                if year == prev_y and month == prev_months[-1] + 1 and is_full_month and prev_full:
                    prev_months.append(month)
                    # En solicitud multi-mes, CDS interpreta 'day' 01..31 ignorando días inexistentes del mes
                    all_days = sorted(set(prev_days) | set(days))
                    groups[-1] = (prev_y, prev_months, all_days)
                    continue
            groups.append((year, [month], days))
        return groups

    @staticmethod
    def _translate_cds_error(err: Exception) -> RuntimeError:
        msg = str(err)
        low = msg.lower()
        if "401" in low or "unauthorized" in low or "invalid" in low and "key" in low:
            return RuntimeError(
                "Credenciales Copernicus CDS rechazadas (HTTP 401). "
                "Verifique su Personal Access Token y URL (https://cds.climate.copernicus.eu/api) en su perfil CDS."
            )
        if "403" in low or "licence" in low or "license" in low or "terms" in low:
            return RuntimeError(
                "Acceso denegado por Copernicus CDS (HTTP 403 / Licencia). "
                "Debe aceptar los 'Terms of Use' del dataset 'reanalysis-era5-single-levels' "
                "en https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels."
            )
        return RuntimeError(f"Error al descargar datos ERA5 desde Copernicus CDS: {msg}")

    def _save_monthly_partitions(
        self,
        db: DeepWaterERA5DB,
        buoy_mode: str,
        step_hours: int,
    ) -> None:
        """Divide un DeepWaterERA5DB por mes y lo guarda/fusiona en era5_cache/."""
        ym_pairs = sorted(set(zip(db.timestamps.year, db.timestamps.month)))
        for year, month in ym_pairs:
            mask = (db.timestamps.year == year) & (db.timestamps.month == month)
            sub_times = db.timestamps[mask]
            sub_data = {k: v[:, mask].copy() for k, v in db.data.items()}
            sub_meta = dict(db.metadata)
            sub_meta["step_hours"] = str(int(step_hours))
            sub_meta["era5_start"] = str(sub_times[0])
            sub_meta["era5_end"] = str(sub_times[-1])
            sub_meta["n_records"] = str(len(sub_times))

            month_db = DeepWaterERA5DB(
                ids=db.ids.copy(),
                lats=db.lats.copy(),
                lons=db.lons.copy(),
                names=list(db.names),
                timestamps=sub_times,
                data=sub_data,
                metadata=sub_meta,
            )
            c_path = self.get_month_cache_path(buoy_mode, int(year), int(month), step_hours)
            if c_path.exists():
                try:
                    existing = DeepWaterERA5DB.from_npz(c_path)
                    month_db = DeepWaterERA5DB.merge([existing, month_db])
                except Exception:
                    pass
            month_db.save_npz(c_path)

    def get_era5_data(
        self,
        buoy_mode: str = "1deg",
        start_date: str = "2024-01-01",
        end_date: str = "2024-01-31",
        step_hours: int = 1,
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> DeepWaterERA5DB:
        """
        Obtiene series de oleaje ERA5 para todas las boyas de aguas profundas chilenas.
        Reutiliza el caché mensual local y descarga desde Copernicus CDS solo los meses faltantes.
        """
        step_h = int(step_hours)
        if step_h not in (1, 3, 6):
            raise ValueError(f"step_hours debe ser 1, 3 o 6 (recibido: {step_hours})")

        plan = self.build_month_plan(start_date, end_date)
        if force_refresh:
            missing = list(plan)
        else:
            _, missing = self.check_cache_coverage(buoy_mode, start_date, end_date, step_hours=step_h)

        if missing:
            creds = self.get_credentials()
            if not creds.is_configured:
                raise PermissionError(
                    "No se encontraron credenciales de cuenta Copernicus CDS. "
                    "Configure ~/.cdsapirc (url + Personal Access Token), defina CDSAPI_KEY, "
                    "o ingrese su API Key en la aplicación / CLI (--era5-key)."
                )
            try:
                import cdsapi
            except ImportError as exc:
                raise RuntimeError(
                    "El paquete 'cdsapi' no está instalado. Instálelo con: pip install cdsapi>=0.7.0"
                ) from exc

            groups = self._group_missing_requests(missing)
            times_list = [f"{h:02d}:00" for h in range(0, 24, step_h)]
            client = cdsapi.Client(url=creds.url, key=creds.key, quiet=True)

            total_groups = len(groups)
            for idx, (year, months, days) in enumerate(groups):
                months_str = [f"{m:02d}" for m in months]
                label = f"{year}-{months_str[0]}" if len(months_str) == 1 else f"{year}-{months_str[0]}..{months_str[-1]}"
                if progress_callback:
                    progress_callback(
                        f"Solicitando ERA5 a Copernicus CDS ({label}, paso {step_h}h) [{idx + 1}/{total_groups}]...",
                        idx / max(total_groups, 1),
                    )

                request = {
                    "product_type": "reanalysis",
                    "variable": ERA5_WAVE_VARIABLES,
                    "year": f"{year:04d}",
                    "month": months_str if len(months_str) > 1 else months_str[0],
                    "day": days,
                    "time": times_list,
                    "area": CHILE_ERA5_AREA,
                    "data_format": "netcdf",
                    "download_format": "unarchived",
                }

                with tempfile.TemporaryDirectory() as tmp_dir:
                    target_path = Path(tmp_dir) / f"era5_{year}_{months_str[0]}.nc"
                    try:
                        client.retrieve(ERA5_DATASET, request, str(target_path))
                    except Exception as err:
                        raise self._translate_cds_error(err) from err

                    if progress_callback:
                        progress_callback(
                            f"Procesando y cacheando ERA5 ({label})...",
                            (idx + 0.7) / max(total_groups, 1),
                        )

                    parsed_db = parse_era5_netcdf_to_db(
                        target_path,
                        buoy_mode=buoy_mode,
                        metadata={
                            "source": "ECMWF ERA5 (Copernicus CDS)",
                            "step_hours": str(step_h),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    self._save_monthly_partitions(parsed_db, buoy_mode=buoy_mode, step_hours=step_h)

            if progress_callback:
                progress_callback("Descarga ERA5 completada.", 1.0)

        month_dbs: List[DeepWaterERA5DB] = []
        for year, month, _ in plan:
            c_path = self.get_month_cache_path(buoy_mode, year, month, step_h)
            if not c_path.exists():
                raise FileNotFoundError(f"Falta bloque mensual en caché ERA5 tras descarga: {c_path}")
            month_dbs.append(DeepWaterERA5DB.from_npz(c_path))

        merged = DeepWaterERA5DB.merge(month_dbs)
        merged.metadata["source"] = "ECMWF ERA5 (Copernicus CDS)"
        merged.metadata["step_hours"] = str(step_h)
        return merged.subset(start_date, end_date)

    def load_from_local_netcdf(
        self,
        nc_path: Path,
        buoy_mode: str = "1deg",
        save_to_cache: bool = False,
    ) -> DeepWaterERA5DB:
        """Carga un archivo ERA5 local (.nc o .zip) y opcionalmente lo almacena en el caché mensual."""
        db = parse_era5_netcdf_to_db(
            Path(nc_path),
            buoy_mode=buoy_mode,
            metadata={"source": f"ECMWF ERA5 Local ({Path(nc_path).name})"},
        )
        if save_to_cache and len(db.timestamps) > 0:
            step_h = int(db.metadata.get("step_hours", "1"))
            self._save_monthly_partitions(db, buoy_mode=buoy_mode, step_hours=step_h)
        return db
