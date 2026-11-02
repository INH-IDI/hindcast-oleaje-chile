"""
Motor principal de Hindcasting de Oleaje en Aguas Someras (AS) a partir de
datos de Aguas Profundas (AP) y Matrices de Transferencia SWAN (chile_250k).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd
import netCDF4 as nc

from .mesh_interpolator import TransferMatrixDB, LocalTransferFunction
from .buoy_weighting import MultiBuoyWeighter, WeightingConfig
from .catalog import load_coastal_sites


@dataclass
class HindcastResult:
    """Resultado completo de una simulación de Hindcasting en un punto costero."""
    site_name: str
    lon: float
    lat: float
    depth: float
    timeseries: pd.DataFrame
    local_tf: LocalTransferFunction
    buoy_info: Dict[str, Any]
    weights_mean: np.ndarray
    summary_stats: Dict[str, float]


class DeepWaterHindcastDB:
    """
    Gestiona la lectura rápida en memoria / NetCDF de las series de tiempo de
    aguas profundas (28 boyas cada 1° o 14 nodos originales UV, 1980-2015).
    """

    def __init__(self, nc_path: Path):
        self.nc_path = Path(nc_path)
        if not self.nc_path.exists():
            raise FileNotFoundError(f"No existe la base de datos AP: {self.nc_path}")

        with nc.Dataset(self.nc_path, "r") as ds:
            dim_name = "buoy" if "buoy" in ds.dimensions else "node"
            id_var = "buoy_id" if "buoy_id" in ds.variables else "node_id"
            self.ids = np.array(ds.variables[id_var][:], dtype=np.int32)
            self.lats = np.array(ds.variables["lat"][:], dtype=np.float64)
            self.lons = np.array(ds.variables["lon"][:], dtype=np.float64)
            time_hours = np.array(ds.variables["time"][:], dtype=np.float64)
            self.timestamps = pd.Timestamp("1980-01-01 00:00:00") + pd.to_timedelta(time_hours, unit="h")

            names_attr = getattr(ds, "buoy_names", getattr(ds, "node_names", ""))
            if names_attr:
                self.names = names_attr.split(",")
            else:
                self.names = [f"Boya_{i}" for i in self.ids]

            # Cargar variables principales en RAM (~90 MB total) para consultas en milisegundos
            self.data: Dict[str, np.ndarray] = {}
            for var in ["Hm0", "Tp", "Tm", "Tz", "Te", "Dm", "Dp", "s"]:
                if var in ds.variables:
                    self.data[var] = np.array(ds.variables[var][:], dtype=np.float32)

    def subset_time_slice(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> slice:
        if start_date is None and end_date is None:
            return slice(None)
        t0 = pd.Timestamp(start_date) if start_date else self.timestamps[0]
        t1 = pd.Timestamp(end_date) if end_date else self.timestamps[-1]
        i0 = int(self.timestamps.searchsorted(t0, side="left"))
        i1 = int(self.timestamps.searchsorted(t1, side="right"))
        return slice(i0, i1)


class WaveHindcastEngine:
    """
    Motor integrado de Hindcasting costero mediante funciones de transferencia.
    """

    def __init__(
        self,
        transfer_nc_path: Optional[Path] = None,
        ap_nc_path: Optional[Path] = None,
        buoy_mode: str = "1deg",
    ):
        base_dir = Path(__file__).resolve().parents[2]
        if transfer_nc_path is None:
            transfer_nc_path = base_dir / "trabajo_swan" / "matrices" / "matriz_transferencia_chile.nc"
        if ap_nc_path is None:
            if buoy_mode == "uv14":
                ap_nc_path = base_dir / "datos_ap_uv" / "processed" / "hindcast_uv_14nodos.nc"
            else:
                ap_nc_path = base_dir / "datos_ap_uv" / "processed" / "hindcast_ap_1deg_chile.nc"

        self.transfer_db = TransferMatrixDB(transfer_nc_path)
        self.ap_db = DeepWaterHindcastDB(ap_nc_path)
        self.buoy_mode = buoy_mode
        self.sites_df = load_coastal_sites()

    def run_hindcast(
        self,
        lon: float,
        lat: float,
        site_name: str = "Punto_Costero",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period_var: str = "Tp",
        dir_var: str = "Dm",
        weighting_config: Optional[WeightingConfig] = None,
        use_peak_dir_tf: bool = False,
        dt_hours: int = 3,
    ) -> HindcastResult:
        """
        Ejecuta el hindcasting de aguas someras en (lon, lat) usando la matriz de transferencia
        y la ponderación multi-boya por distancia y dirección de aguas profundas.
        Parámetros:
          - dt_hours: Paso temporal de salida en horas (3 = nativo Atlas UV; 1 = interpolado horario).
        """
        w_cfg = weighting_config or WeightingConfig()
        weighter = MultiBuoyWeighter(
            buoy_lons=self.ap_db.lons,
            buoy_lats=self.ap_db.lats,
            buoy_ids=self.ap_db.ids,
            buoy_names=self.ap_db.names,
            config=w_cfg,
        )

        # 1. Obtener la función de transferencia local en (lon, lat)
        local_tf = self.transfer_db.get_local_transfer_function(lon, lat)

        # 2. Recortar ventana temporal solicitada
        t_slice = self.ap_db.subset_time_slice(start_date, end_date)
        times = self.ap_db.timestamps[t_slice]
        n_t = len(times)

        # 3. Seleccionar las K boyas activas y extraer sus series en AP
        info = weighter.select_active_buoys(lon, lat)
        sel_idx = info["indices"]
        k = len(sel_idx)

        hm0_ap_k = self.ap_db.data["Hm0"][sel_idx, t_slice]       # (K, N_t)
        per_ap_k = self.ap_db.data[period_var][sel_idx, t_slice]  # (K, N_t)
        dir_ap_k = self.ap_db.data[dir_var][sel_idx, t_slice]     # (K, N_t)
        tp_ap_k = self.ap_db.data["Tp"][sel_idx, t_slice]
        tm_ap_k = self.ap_db.data["Tm"][sel_idx, t_slice]
        tz_ap_k = self.ap_db.data["Tz"][sel_idx, t_slice]

        # Si se solicita resolución de 1 hora (dt_hours == 1), interpolar las series AP a paso de 1h
        if int(dt_hours) == 1 and n_t >= 2:
            t_orig = np.arange(n_t, dtype=np.float64) * 3.0
            t_1h = np.arange(0.0, t_orig[-1] + 0.1, 1.0, dtype=np.float64)
            times = times[0] + pd.to_timedelta(t_1h, unit="h")
            n_t = len(t_1h)

            def _interp_rows(mat_2d: np.ndarray) -> np.ndarray:
                out = np.empty((mat_2d.shape[0], n_t), dtype=np.float32)
                for r_i in range(mat_2d.shape[0]):
                    out[r_i, :] = np.interp(t_1h, t_orig, mat_2d[r_i, :]).astype(np.float32)
                return out

            def _interp_rows_circ(deg_2d: np.ndarray) -> np.ndarray:
                rad = np.deg2rad(deg_2d.astype(np.float64))
                s_i = _interp_rows(np.sin(rad))
                c_i = _interp_rows(np.cos(rad))
                return (np.rad2deg(np.arctan2(s_i, c_i)) % 360.0).astype(np.float32)

            hm0_ap_k = _interp_rows(hm0_ap_k)
            per_ap_k = _interp_rows(per_ap_k)
            tp_ap_k = _interp_rows(tp_ap_k)
            tm_ap_k = _interp_rows(tm_ap_k)
            tz_ap_k = _interp_rows(tz_ap_k)
            dir_ap_k = _interp_rows_circ(dir_ap_k)

        weights, info = weighter.compute_weights(lon, lat, dir_ap_k)  # (K, N_t)

        # 4. Evaluar función de transferencia para cada boya seleccionada y combinar con pesos w_i(t)
        eval_res = local_tf.evaluate(
            periods_ap=per_ap_k,
            dirs_ap=dir_ap_k,
            hm0_ap=hm0_ap_k,
            use_peak_dir=use_peak_dir_tf,
        )
        ka_k = eval_res["Ka"]          # (K, N_t)
        hm0_as_k = eval_res["Hm0_AS"]  # (K, N_t)
        dir_as_k = eval_res["Dir_AS"]  # (K, N_t)

        # Combinación ponderada
        hm0_ap_eff = np.sum(weights * hm0_ap_k, axis=0)
        hm0_as = np.sum(weights * hm0_as_k, axis=0)
        ka_eff = np.where(hm0_ap_eff > 1e-5, hm0_as / hm0_ap_eff, np.sum(weights * ka_k, axis=0))

        # Invarianza del periodo (ponderado entre boyas activas)
        tp_as = np.sum(weights * tp_ap_k, axis=0)
        tm_as = np.sum(weights * tm_ap_k, axis=0)
        tz_as = np.sum(weights * tz_ap_k, axis=0)

        # Dirección media circular ponderada en AP y AS
        dir_ap_rad = np.deg2rad(dir_ap_k)
        dir_ap_eff = (
            np.rad2deg(
                np.arctan2(
                    np.sum(weights * np.sin(dir_ap_rad), axis=0),
                    np.sum(weights * np.cos(dir_ap_rad), axis=0),
                )
            )
            % 360.0
        )

        dir_as_rad = np.deg2rad(dir_as_k)
        dir_as = (
            np.rad2deg(
                np.arctan2(
                    np.sum(weights * np.sin(dir_as_rad), axis=0),
                    np.sum(weights * np.cos(dir_as_rad), axis=0),
                )
            )
            % 360.0
        )

        df_dict = {
            "DateTime": times,
            "Hm0_AS": hm0_as.astype(np.float32),
            "Tp_AS": tp_as.astype(np.float32),
            "Tm_AS": tm_as.astype(np.float32),
            "Tz_AS": tz_as.astype(np.float32),
            "Dir_AS": dir_as.astype(np.float32),
            "Ka_eff": ka_eff.astype(np.float32),
            "Hm0_AP": hm0_ap_eff.astype(np.float32),
            "Dir_AP": dir_ap_eff.astype(np.float32),
        }
        for b_i, b_name in enumerate(info["buoy_names"]):
            df_dict[f"w_{b_name}"] = weights[b_i, :].astype(np.float32)

        df_out = pd.DataFrame(df_dict)
        weights_mean = np.mean(weights, axis=1).astype(np.float32)
        info["weights_mean"] = weights_mean

        summary = {
            "Hm0_AS_mean": float(np.mean(hm0_as)),
            "Hm0_AS_p50": float(np.percentile(hm0_as, 50)),
            "Hm0_AS_p95": float(np.percentile(hm0_as, 95)),
            "Hm0_AS_p99": float(np.percentile(hm0_as, 99)),
            "Hm0_AS_max": float(np.max(hm0_as)),
            "Ka_mean": float(np.mean(ka_eff)),
            "Tp_mean": float(np.mean(tp_as)),
            "Dir_AS_mean": float(
                np.rad2deg(np.arctan2(np.mean(np.sin(np.deg2rad(dir_as))), np.mean(np.cos(np.deg2rad(dir_as))))) % 360.0
            ),
            "n_records": int(n_t),
        }

        return HindcastResult(
            site_name=site_name,
            lon=float(lon),
            lat=float(lat),
            depth=float(local_tf.depth),
            timeseries=df_out,
            local_tf=local_tf,
            buoy_info=info,
            weights_mean=weights_mean,
            summary_stats=summary,
        )
