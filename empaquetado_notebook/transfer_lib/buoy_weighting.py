"""
Módulo de ponderación multi-boya de Aguas Profundas (AP) en función de:
1) La distancia geodésica entre el punto objetivo costero P y cada boya i.
2) La alineación direccional entre la posición relativa de la boya (Norte/Sur/Oeste)
   y la dirección de procedencia del oleaje en aguas profundas (θ_AP).

Propiedad física fundamental:
- En convención náutica, θ_AP indica de dónde viene la ola (0°=N, 270°=W, 180°=S).
- Si la ola viene desde el Norte/Noroeste (cos(θ_AP) > 0), una boya situada al Norte
  del punto P (aguas arriba del oleaje incidente) recibe mayor peso que una boya
  situada al Sur a igual distancia.
- Si la ola viene desde el Sur/Suroeste (cos(θ_AP) < 0), una boya situada al Sur
  del punto P recibe mayor peso que una boya situada al Norte a igual distancia.
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
import numpy as np


EARTH_RADIUS_KM = 6371.0


def haversine_km(lon1: float, lat1: float, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    """Distancia geodésica Haversine en kilómetros entre (lon1, lat1) y arreglos (lon2, lat2)."""
    rlat1 = np.deg2rad(lat1)
    rlat2 = np.deg2rad(lat2)
    dlat = rlat2 - rlat1
    dlon = np.deg2rad(lon2 - lon1)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))


def bearing_deg(lon_p: float, lat_p: float, lon_b: np.ndarray, lat_b: np.ndarray) -> np.ndarray:
    """
    Acimut náutico α_{P->i} en grados [0, 360) desde el punto costero P(lon_p, lat_p)
    hacia cada boya B(lon_b, lat_b).
    Convención: 0° = Norte, 90° = Este, 180° = Sur, 270° = Oeste.
    """
    mean_lat_rad = np.deg2rad(0.5 * (lat_p + lat_b))
    dx = (lon_b - lon_p) * np.cos(mean_lat_rad)
    dy = lat_b - lat_p
    ang = np.rad2deg(np.arctan2(dx, dy)) % 360.0
    return ang


@dataclass
class WeightingConfig:
    """
    Parámetros del esquema de ponderación multi-boya.
    - mode:
        * 'dist_dir': Combina distancia y dirección del oleaje en AP (recomendado).
        * 'idw': Sólo inverso de la distancia (sin dependencia direccional).
        * 'nearest': 100% de peso a la boya más cercana.
    - max_buoys (K): Número máximo de boyas vecinas consideradas para cada punto.
    - dist_power (p): Exponente de decaimiento con la distancia.
    - dist_smooth_km (d0): Distancia de suavizado (km) para evitar singularidades.
    - dir_gamma (γ): Intensidad de la sensibilidad direccional en [0, 1] (ej. 0.85).
    - dir_power (β): Exponente de agudeza direccional (ej. 2.0).
    - meridional_boost (η): Peso adicional a la componente Norte-Sur pura cos(θ_AP)*sign(Δlat)
      para garantizar sensibilidad N-S incluso cuando las boyas están muy mar adentro.
    """
    mode: str = "dist_dir"
    max_buoys: int = 4
    dist_power: float = 2.0
    dist_smooth_km: float = 15.0
    dir_gamma: float = 0.85
    dir_power: float = 2.0
    meridional_boost: float = 0.5


class MultiBuoyWeighter:
    """
    Calcula los pesos dinámicos w_i(t) de un conjunto de boyas de Aguas Profundas
    para interpolar las condiciones de borde sobre cualquier punto costero P(lon, lat).
    """

    def __init__(
        self,
        buoy_lons: np.ndarray,
        buoy_lats: np.ndarray,
        buoy_ids: Optional[np.ndarray] = None,
        buoy_names: Optional[list] = None,
        config: Optional[WeightingConfig] = None,
    ):
        self.buoy_lons = np.asarray(buoy_lons, dtype=np.float64)
        self.buoy_lats = np.asarray(buoy_lats, dtype=np.float64)
        self.n_buoys = len(self.buoy_lons)
        self.buoy_ids = (
            np.asarray(buoy_ids) if buoy_ids is not None else np.arange(1, self.n_buoys + 1)
        )
        self.buoy_names = (
            list(buoy_names)
            if buoy_names is not None
            else [f"Boya_{i}" for i in self.buoy_ids]
        )
        self.config = config or WeightingConfig()

    def select_active_buoys(self, lon_p: float, lat_p: float) -> Dict[str, Any]:
        """
        Selecciona las K boyas más cercanas al punto P(lon_p, lat_p) y precalcula
        sus distancias geodésicas, acimuts y desplazamientos meridionales.
        """
        dists_km = haversine_km(lon_p, lat_p, self.buoy_lons, self.buoy_lats)
        azimuths = bearing_deg(lon_p, lat_p, self.buoy_lons, self.buoy_lats)
        dlat = self.buoy_lats - lat_p

        k = min(max(1, self.config.max_buoys), self.n_buoys)
        if self.config.mode == "nearest":
            k = 1

        sel_idx = np.argsort(dists_km)[:k]
        sel_dists = dists_km[sel_idx]
        sel_az = azimuths[sel_idx]
        sel_dlat = dlat[sel_idx]

        # Peso base por distancia: W_dist = 1 / (d + d0)^p
        w_dist = 1.0 / np.power(sel_dists + self.config.dist_smooth_km, self.config.dist_power)

        return {
            "indices": sel_idx,
            "buoy_ids": self.buoy_ids[sel_idx],
            "buoy_names": [self.buoy_names[i] for i in sel_idx],
            "lons": self.buoy_lons[sel_idx],
            "lats": self.buoy_lats[sel_idx],
            "distances_km": sel_dists,
            "azimuths_deg": sel_az,
            "dlat_deg": sel_dlat,
            "w_dist_raw": w_dist,
            "w_dist_norm": w_dist / np.sum(w_dist),
        }

    def compute_directional_factor(
        self,
        azimuths_deg: np.ndarray,
        dlat_deg: np.ndarray,
        wave_dirs_deg: np.ndarray,
    ) -> np.ndarray:
        """
        Calcula el factor direccional W_dir(i, t) para cada boya seleccionada i y tiempo t.
        Parámetros:
          - azimuths_deg: (K,) acimut desde P hacia cada boya i en grados [0, 360).
          - dlat_deg: (K,) diferencia de latitud (lat_i - lat_P).
          - wave_dirs_deg: (K, N_t) o (N_t,) dirección náutica de donde viene la ola en AP.
        Retorna:
          - w_dir: (K, N_t) factor direccional positivo.
        """
        dirs = np.asarray(wave_dirs_deg, dtype=np.float64)
        if dirs.ndim == 1:
            dirs = np.broadcast_to(dirs[None, :], (len(azimuths_deg), len(dirs)))

        az_col = np.asarray(azimuths_deg, dtype=np.float64)[:, None]
        dlat_col = np.asarray(dlat_deg, dtype=np.float64)[:, None]

        # 1. Alineación 2D entre el vector P->Boya (acimut α) y la procedencia de la ola (θ_AP)
        delta_rad = np.deg2rad(az_col - dirs)
        cos_2d = np.cos(delta_rad)  # en [-1, 1]

        # 2. Alineación meridional Norte-Sur:
        # cos(θ_AP) > 0 cuando la ola viene del Norte; tanh(dlat) > 0 cuando la boya está al Norte
        merid_sign = np.tanh(dlat_col / 0.75)  # suave en [-1, 1] según posición N/S
        cos_ns = merid_sign * np.cos(np.deg2rad(dirs))  # en [-1, 1]

        # Combinación normalizada en [-1, 1]
        eta = self.config.meridional_boost
        alignment = (cos_2d + eta * cos_ns) / (1.0 + eta)
        alignment = np.clip(alignment, -1.0, 1.0)

        gamma = np.clip(self.config.dir_gamma, 0.0, 0.98)
        base_factor = (1.0 + gamma * alignment) / (1.0 + gamma)
        w_dir = np.power(np.maximum(base_factor, 1e-4), self.config.dir_power)
        return w_dir

    def compute_weights(
        self,
        lon_p: float,
        lat_p: float,
        wave_dirs_deg: np.ndarray,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Calcula los pesos normalizados w_i(t) de dimensión (K, N_t) para el punto P(lon_p, lat_p).
        Si wave_dirs_deg tiene forma (N_b_total, N_t), extrae automáticamente las K boyas activas.
        """
        info = self.select_active_buoys(lon_p, lat_p)
        sel_idx = info["indices"]
        k = len(sel_idx)

        dirs = np.asarray(wave_dirs_deg, dtype=np.float64)
        if dirs.ndim == 1:
            dirs_sel = np.broadcast_to(dirs[None, :], (k, len(dirs)))
        elif dirs.shape[0] == self.n_buoys:
            dirs_sel = dirs[sel_idx, :]
        elif dirs.shape[0] == k:
            dirs_sel = dirs
        else:
            raise ValueError(
                f"Forma de wave_dirs_deg {dirs.shape} incompatible con n_buoys={self.n_buoys} o K={k}"
            )

        n_t = dirs_sel.shape[1]
        w_dist_col = info["w_dist_raw"][:, None]

        if self.config.mode == "nearest" or k == 1:
            weights = np.ones((1, n_t), dtype=np.float32)
            info["w_dir_mean"] = np.ones(1, dtype=np.float32)
            return weights, info

        if self.config.mode == "idw":
            w_norm = (w_dist_col / np.sum(w_dist_col, axis=0, keepdims=True)).astype(np.float32)
            weights = np.broadcast_to(w_norm, (k, n_t)).copy()
            info["w_dir_mean"] = np.ones(k, dtype=np.float32)
            return weights, info

        # Modo completo: Distancia + Dirección AP ('dist_dir')
        w_dir = self.compute_directional_factor(info["azimuths_deg"], info["dlat_deg"], dirs_sel)
        w_total = w_dist_col * w_dir
        w_sum = np.sum(w_total, axis=0, keepdims=True)
        weights = (w_total / np.maximum(w_sum, 1e-12)).astype(np.float32)
        info["w_dir_mean"] = np.mean(w_dir, axis=1).astype(np.float32)
        return weights, info
