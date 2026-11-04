"""
Módulo de Pronóstico (Forecasting) de Oleaje en Aguas Someras y Profundas
utilizando datos operacionales del modelo WAVEWATCH III (WW3 / GFS-Wave) de la NOAA
y el método de Matrices de Transferencia SWAN (chile_250k).
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import io
import re
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import urllib.request
import requests
import numpy as np
import pandas as pd

from .catalog import load_buoy_catalog


# Servidores NOAA oficiales
ERDDAP_WW3_URL = "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/ww3_global.csv"
NOMADS_FILTER_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfswave.pl"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "forecast_cache"


class DeepWaterForecastDB:
    """
    Estructura de datos en memoria para el pronóstico de oleaje en aguas profundas (AP).
    Provee la misma interfaz que DeepWaterHindcastDB para compatibilidad total
    con el motor de matrices de transferencia SWAN.
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
        self.data = {k: np.array(v, dtype=np.float32) for k, v in data.items()}
        self.metadata = metadata or {}

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
        t1 = pd.Timestamp(end_date) if end_date else self.timestamps[-1]
        i0 = int(self.timestamps.searchsorted(t0, side="left"))
        i1 = int(self.timestamps.searchsorted(t1, side="right"))
        return slice(max(0, i0), min(len(self.timestamps), i1))

    def save_npz(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        t_strings = self.timestamps.strftime("%Y-%m-%d %H:%M:%S").to_numpy(dtype="U25")
        names_arr = np.array(self.names, dtype="U60")

        save_dict = {
            "buoy_ids": self.ids,
            "lats": self.lats,
            "lons": self.lons,
            "names": names_arr,
            "timestamps": t_strings,
        }
        for var in ["Hm0", "Tp", "Tm", "Tz", "Dm", "Dp", "s"]:
            if var in self.data:
                save_dict[var] = self.data[var]

        # Guardar metadatos simples
        for k, v in self.metadata.items():
            if isinstance(v, (str, int, float)):
                save_dict[f"meta_{k}"] = np.array(str(v), dtype="U200")

        np.savez_compressed(path, **save_dict)

    @classmethod
    def from_npz(cls, path: Path) -> "DeepWaterForecastDB":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"No existe el archivo de caché de pronóstico en {path}")

        d = np.load(path, allow_pickle=False)
        ids = d["buoy_ids"].astype(np.int32)
        lats = d["lats"].astype(np.float64)
        lons = d["lons"].astype(np.float64)
        names = [str(s) for s in d["names"]]
        t_raw = [str(s) for s in d["timestamps"]]
        timestamps = pd.to_datetime(t_raw)

        data = {}
        for var in ["Hm0", "Tp", "Tm", "Tz", "Dm", "Dp", "s"]:
            if var in d.files:
                data[var] = d[var].astype(np.float32)

        metadata = {}
        for k in d.files:
            if k.startswith("meta_"):
                metadata[k[5:]] = str(d[k])

        return cls(ids, lats, lons, names, timestamps, data, metadata)


class NOAAWaveForecastClient:
    """
    Cliente para la descarga y procesamiento de datos operacionales de oleaje WW3 de NOAA.
    Soporta:
      1. NOAA ERDDAP (WW3 Global): descarga directa de parámetros espectrales Thgt, Tper, Tdir.
      2. NOAA NOMADS GFS-Wave: filtrado espacial grib2 para el borde chileno.
      3. Almacenamiento en caché local con control de frescura.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_file(self, buoy_mode: str) -> Path:
        return self.cache_dir / f"forecast_latest_{buoy_mode}.npz"

    def is_cache_valid(self, buoy_mode: str, max_age_hours: float = 3.0) -> bool:
        c_file = self.get_cache_file(buoy_mode)
        if not c_file.exists():
            return False
        mtime = datetime.fromtimestamp(c_file.stat().st_mtime, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0
        return age_hours < max_age_hours

    def download_from_erddap(
        self,
        buoy_mode: str = "1deg",
        hours_back: int = 6,
        hours_stride: int = 3,
        timeout: int = 25,
    ) -> DeepWaterForecastDB:
        """
        Descarga el pronóstico WW3 desde el servidor ERDDAP de NOAA/PacIOOS
        para todos los nodos de aguas profundas chilenos.
        """
        df_buoys = load_buoy_catalog(mode=buoy_mode)
        now = datetime.now(timezone.utc)
        t_start = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:00:00Z")

        # El dominio chileno abarca lat [-45.0, -18.0], lon [-76.0, -72.0] -> lon [284.0, 288.0]
        # Con paso de 1° en latitud y 0.5° en longitud cubre con exactitud todos los nodos
        url = (
            f"{ERDDAP_WW3_URL}?"
            f"Thgt[({t_start}):{hours_stride}:(last)][(0.0)][(-45.0):1.0:(-18.0)][(283.5):0.5:(288.5)],"
            f"Tper[({t_start}):{hours_stride}:(last)][(0.0)][(-45.0):1.0:(-18.0)][(283.5):0.5:(288.5)],"
            f"Tdir[({t_start}):{hours_stride}:(last)][(0.0)][(-45.0):1.0:(-18.0)][(283.5):0.5:(288.5)]"
        )

        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Error al descargar pronóstico de ERDDAP NOAA (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        df = pd.read_csv(io.StringIO(resp.text), skiprows=[1])
        df["time"] = pd.to_datetime(df["time"])
        times = pd.DatetimeIndex(sorted(df["time"].unique()))
        n_times = len(times)
        n_buoys = len(df_buoys)

        hm0 = np.zeros((n_buoys, n_times), dtype=np.float32)
        tp = np.zeros((n_buoys, n_times), dtype=np.float32)
        dirs = np.zeros((n_buoys, n_times), dtype=np.float32)

        for b_i, (_, b_row) in enumerate(df_buoys.iterrows()):
            b_lat = float(b_row["lat"])
            b_lon_raw = float(b_row["lon"])
            b_lon = b_lon_raw if b_lon_raw >= 0 else 360.0 + b_lon_raw

            sub_lat = df[np.isclose(df["latitude"], b_lat, atol=0.2)]
            lons_avail = sub_lat["longitude"].unique()
            if len(lons_avail) == 0:
                raise ValueError(f"No hay datos ERDDAP para la latitud {b_lat}")

            best_lon = lons_avail[np.argmin(np.abs(lons_avail - b_lon))]
            sub = sub_lat[np.isclose(sub_lat["longitude"], best_lon, atol=0.1)].sort_values("time")

            # Si el nodo más cercano cae en tierra (NaN), buscar el punto contiguo en aguas abiertas
            if sub["Thgt"].isna().all():
                for alt_lon in sorted(lons_avail, key=lambda x: abs(x - b_lon)):
                    cand = sub_lat[np.isclose(sub_lat["longitude"], alt_lon, atol=0.1)].sort_values("time")
                    if not cand["Thgt"].isna().all():
                        sub = cand
                        break

            hm0[b_i, :] = sub["Thgt"].interpolate().bfill().ffill().to_numpy()
            tp[b_i, :] = sub["Tper"].interpolate().bfill().ffill().to_numpy()
            dirs[b_i, :] = sub["Tdir"].interpolate().bfill().ffill().to_numpy()

        tm = tp * 0.85
        tz = tp * 0.78
        s_spread = np.full_like(hm0, 10.0, dtype=np.float32)

        meta = {
            "source": "NOAA WW3 Global via ERDDAP",
            "server": ERDDAP_WW3_URL,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "buoy_mode": buoy_mode,
            "forecast_start": str(times[0]),
            "forecast_end": str(times[-1]),
            "n_records": n_times,
        }

        db = DeepWaterForecastDB(
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
                "Dm": dirs,
                "Dp": dirs,
                "s": s_spread,
            },
            metadata=meta,
        )

        # Guardar en caché
        c_path = self.get_cache_file(buoy_mode)
        db.save_npz(c_path)
        return db

    def download_from_nomads(
        self,
        buoy_mode: str = "1deg",
        cycle_date: Optional[str] = None,
        cycle_hour: str = "12",
        hours_ahead: int = 120,
        hours_stride: int = 3,
        timeout: int = 20,
    ) -> DeepWaterForecastDB:
        """
        Descarga el pronóstico WW3 desde NOMADS GFS-Wave mediante el filtro de subregión GRIB2.
        """
        try:
            import pygrib
        except ImportError:
            raise RuntimeError("pygrib no está instalado para procesar archivos NOMADS GRIB2.")

        df_buoys = load_buoy_catalog(mode=buoy_mode)
        date_str = cycle_date or datetime.now(timezone.utc).strftime("%Y%m%d")
        cycle_dir = f"/gfs.{date_str}/{cycle_hour}/wave/gridded"

        steps = [f"f{h:03d}" for h in range(0, hours_ahead + 1, hours_stride)]
        n_steps = len(steps)
        n_buoys = len(df_buoys)

        hm0 = np.zeros((n_buoys, n_steps), dtype=np.float32)
        tp = np.zeros((n_buoys, n_steps), dtype=np.float32)
        dirs = np.zeros((n_buoys, n_steps), dtype=np.float32)
        valid_times: List[pd.Timestamp] = []

        base_time = pd.Timestamp(f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {cycle_hour}:00:00")

        for s_idx, step in enumerate(steps):
            params = {
                "file": f"gfswave.t{cycle_hour}z.global.0p25.{step}.grib2",
                "lev_surface": "on",
                "var_HTSGW": "on",
                "var_PERPW": "on",
                "var_DIRPW": "on",
                "subregion": "on",
                "leftlon": "280",
                "rightlon": "295",
                "toplat": "-17",
                "bottomlat": "-46",
                "dir": cycle_dir,
            }
            r = requests.get(NOMADS_FILTER_URL, params=params, timeout=timeout)
            if r.status_code != 200:
                raise RuntimeError(f"Error descargando {step} de NOMADS: {r.status_code}")

            # Guardar temporalmente y leer con pygrib
            with pygrib.open(io.BytesIO(r.content)) as grbs:
                g_swh = grbs.select(shortName="swh")[0]
                g_tp = grbs.select(shortName="perpw")[0]
                g_dir = grbs.select(shortName="dirpw")[0]

                lats, lons = g_swh.latlons()
                val_swh = g_swh.values
                val_tp = g_tp.values
                val_dir = g_dir.values

                step_hours = int(step.replace("f", ""))
                valid_times.append(base_time + pd.Timedelta(hours=step_hours))

                for b_i, (_, b_row) in enumerate(df_buoys.iterrows()):
                    b_lat = float(b_row["lat"])
                    b_lon = float(b_row["lon"]) if float(b_row["lon"]) >= 0 else 360.0 + float(b_row["lon"])
                    dist2 = (lats - b_lat) ** 2 + (lons - b_lon) ** 2
                    iy, ix = np.unravel_index(np.argmin(dist2), dist2.shape)
                    hm0[b_i, s_idx] = float(val_swh[iy, ix])
                    tp[b_i, s_idx] = float(val_tp[iy, ix])
                    dirs[b_i, s_idx] = float(val_dir[iy, ix])

        timestamps = pd.DatetimeIndex(valid_times)
        tm = tp * 0.85
        tz = tp * 0.78
        s_spread = np.full_like(hm0, 10.0, dtype=np.float32)

        meta = {
            "source": f"NOAA GFS-Wave via NOMADS ({date_str} {cycle_hour}z)",
            "server": NOMADS_FILTER_URL,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "buoy_mode": buoy_mode,
            "forecast_start": str(timestamps[0]),
            "forecast_end": str(timestamps[-1]),
            "n_records": n_steps,
        }

        db = DeepWaterForecastDB(
            ids=df_buoys["id"].to_numpy(dtype=np.int32),
            lats=df_buoys["lat"].to_numpy(dtype=np.float64),
            lons=df_buoys["lon"].to_numpy(dtype=np.float64),
            names=df_buoys["name"].tolist(),
            timestamps=timestamps,
            data={
                "Hm0": hm0,
                "Tp": tp,
                "Tm": tm,
                "Tz": tz,
                "Dm": dirs,
                "Dp": dirs,
                "s": s_spread,
            },
            metadata=meta,
        )

        c_path = self.get_cache_file(buoy_mode)
        db.save_npz(c_path)
        return db

    def get_forecast(
        self,
        buoy_mode: str = "1deg",
        server: str = "erddap",
        force_refresh: bool = False,
        max_cache_age_hours: float = 3.0,
    ) -> DeepWaterForecastDB:
        """
        Obtiene el pronóstico de aguas profundas:
        - Si existe un archivo en caché reciente y force_refresh es False, lo carga al instante.
        - Si no o si se fuerza la recarga, descarga de la fuente seleccionada (ERDDAP o NOMADS).
        - Si la red falla, intenta cargar el último pronóstico guardado con aviso.
        """
        c_path = self.get_cache_file(buoy_mode)

        if not force_refresh and self.is_cache_valid(buoy_mode, max_cache_age_hours):
            try:
                return DeepWaterForecastDB.from_npz(c_path)
            except Exception:
                pass

        # Intento de descarga
        try:
            if server == "nomads":
                return self.download_from_nomads(buoy_mode=buoy_mode)
            else:
                return self.download_from_erddap(buoy_mode=buoy_mode)
        except Exception as err:
            # Si falla la descarga, intentar cargar el caché disponible
            if c_path.exists():
                db = DeepWaterForecastDB.from_npz(c_path)
                db.metadata["warning"] = f"Aviso: Usando pronóstico en caché debido a error de descarga: {err}"
                return db
            raise RuntimeError(f"No se pudo descargar el pronóstico ni hay caché disponible: {err}")
