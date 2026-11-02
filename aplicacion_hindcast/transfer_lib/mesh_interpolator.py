"""
Interpolador espacial (X, Y) sobre la malla no estructurada chile_250k
e interpolador espectral 2D (frecuencia f = 1/T, dirección θ_AP) para
obtener el coeficiente de agitación Ka(X,Y,f,θ) y la dirección en aguas someras Dir_AS(X,Y,f,θ).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import numpy as np
import netCDF4 as nc
from scipy.spatial import cKDTree
from scipy.interpolate import RegularGridInterpolator


@dataclass
class LocalTransferFunction:
    """
    Representa la función de transferencia local en un punto costero P(lon, lat):
    - Matriz Ka(period, direction) de dimensión (N_T, N_Dir)
    - Matriz Dir_AS(period, direction) de dimensión (N_T, N_Dir) (dirección media)
    - Matriz PkDir_AS(period, direction) de dimensión (N_T, N_Dir) (dirección peak)
    Provee evaluación vectorizada en frecuencia (f = 1/T) y dirección (θ_AP).
    """
    lon: float
    lat: float
    depth: float
    periods: np.ndarray          # (N_T,) en segundos, orden ascendente
    frequencies: np.ndarray      # (N_T,) en Hz (1/periods), orden descendente -> se invierte al interpolar
    directions: np.ndarray       # (N_Dir,) en grados [180..360]
    ka_matrix: np.ndarray        # (N_T, N_Dir)
    dir_matrix: np.ndarray       # (N_T, N_Dir) en grados [0, 360)
    pkdir_matrix: np.ndarray     # (N_T, N_Dir) en grados [0, 360)
    spatial_info: Dict[str, Any]

    def __post_init__(self):
        # Preparar grillas ordenadas en frecuencia ascendente f_asc = 1 / T_desc
        self._f_asc = (1.0 / self.periods[::-1]).astype(np.float64)
        self._dirs_asc = self.directions.astype(np.float64)

        ka_f_asc = self.ka_matrix[::-1, :].astype(np.float64)
        dir_rad = np.deg2rad(self.dir_matrix[::-1, :].astype(np.float64))
        pkdir_rad = np.deg2rad(self.pkdir_matrix[::-1, :].astype(np.float64))

        self._interp_ka = RegularGridInterpolator(
            (self._f_asc, self._dirs_asc),
            ka_f_asc,
            method="linear",
            bounds_error=False,
            fill_value=None,
        )
        self._interp_sin_dir = RegularGridInterpolator(
            (self._f_asc, self._dirs_asc),
            np.sin(dir_rad),
            method="linear",
            bounds_error=False,
            fill_value=None,
        )
        self._interp_cos_dir = RegularGridInterpolator(
            (self._f_asc, self._dirs_asc),
            np.cos(dir_rad),
            method="linear",
            bounds_error=False,
            fill_value=None,
        )
        self._interp_sin_pkdir = RegularGridInterpolator(
            (self._f_asc, self._dirs_asc),
            np.sin(pkdir_rad),
            method="linear",
            bounds_error=False,
            fill_value=None,
        )
        self._interp_cos_pkdir = RegularGridInterpolator(
            (self._f_asc, self._dirs_asc),
            np.cos(pkdir_rad),
            method="linear",
            bounds_error=False,
            fill_value=None,
        )

    @staticmethod
    def map_incident_direction(theta_deg: np.ndarray, dmin: float = 180.0, dmax: float = 360.0) -> np.ndarray:
        """
        Mapea direcciones náuticas [0, 360) al dominio incidente [dmin, dmax] (típicamente [180°, 360°]):
        - Ángulos en [0°, 90°) corresponden a oleaje del N-NE, contiguo a 360° (Norte), por lo que
          se proyectan hacia 360° (no hacia 180° Sur).
        - Ángulos en [90°, dmin) se acotan al borde Sur dmin (180°).
        """
        ang = np.asarray(theta_deg, dtype=np.float64) % 360.0
        mapped = np.where(ang < 90.0, dmax, np.clip(ang, dmin, dmax))
        return mapped

    def evaluate(
        self,
        periods_ap: np.ndarray,
        dirs_ap: np.ndarray,
        hm0_ap: Optional[np.ndarray] = None,
        use_peak_dir: bool = False,
    ) -> Dict[str, np.ndarray]:
        """
        Evalúa de forma vectorizada el coeficiente de agitación Ka y la dirección transformada
        en aguas someras para vectores de periodo (s) y dirección (grados) en aguas profundas.
        """
        t_arr = np.asarray(periods_ap, dtype=np.float64)
        f_arr = np.clip(1.0 / np.maximum(t_arr, 1.0), self._f_asc[0], self._f_asc[-1])
        d_arr = self.map_incident_direction(dirs_ap, self._dirs_asc[0], self._dirs_asc[-1])

        pts = np.column_stack([f_arr.ravel(), d_arr.ravel()])
        ka = np.maximum(0.0, self._interp_ka(pts)).reshape(t_arr.shape).astype(np.float32)

        if use_peak_dir:
            sin_val = self._interp_sin_pkdir(pts)
            cos_val = self._interp_cos_pkdir(pts)
        else:
            sin_val = self._interp_sin_dir(pts)
            cos_val = self._interp_cos_dir(pts)

        dir_as = (np.rad2deg(np.arctan2(sin_val, cos_val)) % 360.0).reshape(t_arr.shape).astype(np.float32)

        res = {
            "Ka": ka,
            "Dir_AS": dir_as,
            "T_AS": t_arr.astype(np.float32),  # Invarianza del periodo
        }
        if hm0_ap is not None:
            res["Hm0_AS"] = (np.asarray(hm0_ap, dtype=np.float32) * ka).astype(np.float32)
        return res


class TransferMatrixDB:
    """
    Gestiona la lectura y consulta espacial sobre la Matriz de Transferencia de Chile
    (generada con SWAN sobre la malla chile_250k).
    """

    def __init__(self, nc_path: Path, mesh_dir: Optional[Path] = None):
        self.nc_path = Path(nc_path)
        if not self.nc_path.exists():
            raise FileNotFoundError(f"No existe el archivo de matriz de transferencia: {self.nc_path}")

        self.mesh_dir = (
            Path(mesh_dir)
            if mesh_dir is not None
            else Path(__file__).resolve().parents[2] / "modelo_pronostico" / "malla"
        )

        with nc.Dataset(self.nc_path, "r") as ds:
            self.periods = np.array(ds.variables["period"][:], dtype=np.float32)
            self.directions = np.array(ds.variables["direction"][:], dtype=np.float32)
            self.lon = np.array(ds.variables["lon"][:], dtype=np.float64)
            self.lat = np.array(ds.variables["lat"][:], dtype=np.float64)
            self.depth = np.array(ds.variables["depth"][:], dtype=np.float32)
            if "triangles" in ds.variables:
                self.triangles = np.array(ds.variables["triangles"][:], dtype=np.int32)
            else:
                self.triangles = self._load_triangles_from_ele()

        self.n_nodes = len(self.lon)
        self.n_periods = len(self.periods)
        self.n_directions = len(self.directions)

        # Construir árbol KDTree 2D (con corrección de cos(lat) media para distancias locales)
        self._kdtree = cKDTree(np.column_stack([self.lon, self.lat]))

        # Construir índice inverso nodo -> triángulos incidentes para búsqueda baricéntrica en <0.2ms
        self._node_to_tris: list = [[] for _ in range(self.n_nodes)]
        for t_idx, (v0, v1, v2) in enumerate(self.triangles):
            self._node_to_tris[v0].append(t_idx)
            self._node_to_tris[v1].append(t_idx)
            self._node_to_tris[v2].append(t_idx)

    def _load_triangles_from_ele(self) -> np.ndarray:
        ele_path = self.mesh_dir / "chile_250k.ele"
        raw = np.loadtxt(ele_path, skiprows=1, dtype=np.int32)
        return raw[:, 1:4] - 1  # Convertir índices 1-based a 0-based

    @staticmethod
    def _barycentric_coords(
        px: float, py: float,
        x0: np.ndarray, y0: np.ndarray,
        x1: np.ndarray, y1: np.ndarray,
        x2: np.ndarray, y2: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calcula coordenadas baricéntricas (w0, w1, w2) de (px, py) en un conjunto de triángulos."""
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        denom = np.where(np.abs(denom) < 1e-15, 1e-15, denom)
        w0 = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / denom
        w1 = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / denom
        w2 = 1.0 - w0 - w1
        return w0, w1, w2

    def find_spatial_weights(self, lon_q: float, lat_q: float, k_nearest: int = 12) -> Dict[str, Any]:
        """
        Determina los nodos y pesos de interpolación espacial para el punto (lon_q, lat_q):
        1. Busca si (lon_q, lat_q) cae dentro de alguno de los triángulos incidentes a los
           k_nearest nodos más cercanos (interpolación baricéntrica exacta).
        2. Si el punto está ligeramente fuera del borde costero de la malla, usa interpolación
           por inverso de la distancia (IDW) sobre los 3 nodos húmedos más cercanos.
        """
        k_eff = min(k_nearest, self.n_nodes)
        dists_deg, near_nodes = self._kdtree.query([lon_q, lat_q], k=k_eff)
        near_nodes = np.atleast_1d(near_nodes)
        dists_deg = np.atleast_1d(dists_deg)

        # Si coincide exactamente con un nodo de la malla
        if dists_deg[0] < 1e-7:
            n0 = int(near_nodes[0])
            return {
                "method": "exact_node",
                "node_indices": np.array([n0], dtype=np.int32),
                "weights": np.array([1.0], dtype=np.float64),
                "distance_km": 0.0,
            }

        # Recolectar triángulos candidatos alrededor de los nodos más cercanos
        cand_tris = set()
        for n_idx in near_nodes:
            cand_tris.update(self._node_to_tris[int(n_idx)])

        if cand_tris:
            tri_arr = np.array(list(cand_tris), dtype=np.int32)
            verts = self.triangles[tri_arr]  # (M, 3)
            v0, v1, v2 = verts[:, 0], verts[:, 1], verts[:, 2]
            w0, w1, w2 = self._barycentric_coords(
                lon_q, lat_q,
                self.lon[v0], self.lat[v0],
                self.lon[v1], self.lat[v1],
                self.lon[v2], self.lat[v2],
            )
            tol = -1e-4
            inside = (w0 >= tol) & (w1 >= tol) & (w2 >= tol)
            if np.any(inside):
                best_idx = int(np.where(inside)[0][0])
                nodes = verts[best_idx]
                w = np.clip([w0[best_idx], w1[best_idx], w2[best_idx]], 0.0, 1.0)
                w = w / np.sum(w)
                return {
                    "method": "barycentric_triangle",
                    "triangle_id": int(tri_arr[best_idx]),
                    "node_indices": nodes.astype(np.int32),
                    "weights": w.astype(np.float64),
                    "distance_km": 0.0,
                }

        # Respaldo: IDW sobre los 3 nodos más cercanos
        top3 = near_nodes[:3].astype(np.int32)
        d_km = np.maximum(dists_deg[:3] * 111.0, 1e-4)
        w = 1.0 / (d_km ** 2)
        w = w / np.sum(w)
        return {
            "method": "coastal_idw_fallback",
            "node_indices": top3,
            "weights": w.astype(np.float64),
            "distance_km": float(d_km[0]),
        }

    def get_local_transfer_function(self, lon_q: float, lat_q: float) -> LocalTransferFunction:
        """
        Extrae e interpola espacialmente la matriz de transferencia (Ka, Dir, PkDir)
        de dimensión (N_T, N_Dir) para cualquier coordenada (lon_q, lat_q).
        """
        sp = self.find_spatial_weights(lon_q, lat_q)
        nodes = sp["node_indices"]
        weights = sp["weights"]

        ka_local = np.zeros((self.n_periods, self.n_directions), dtype=np.float64)
        sin_dir = np.zeros((self.n_periods, self.n_directions), dtype=np.float64)
        cos_dir = np.zeros((self.n_periods, self.n_directions), dtype=np.float64)
        sin_pkdir = np.zeros((self.n_periods, self.n_directions), dtype=np.float64)
        cos_pkdir = np.zeros((self.n_periods, self.n_directions), dtype=np.float64)
        depth_local = 0.0

        with nc.Dataset(self.nc_path, "r") as ds:
            v_ka = ds.variables["Ka"]
            v_dir = ds.variables["Dir"]
            v_pkdir = ds.variables["PkDir"] if "PkDir" in ds.variables else v_dir

            for n_idx, w in zip(nodes, weights):
                n_int = int(n_idx)
                ka_n = np.array(v_ka[:, :, n_int], dtype=np.float64)
                dir_n = np.deg2rad(np.array(v_dir[:, :, n_int], dtype=np.float64))
                pkdir_n = np.deg2rad(np.array(v_pkdir[:, :, n_int], dtype=np.float64))

                ka_local += w * ka_n
                sin_dir += w * np.sin(dir_n)
                cos_dir += w * np.cos(dir_n)
                sin_pkdir += w * np.sin(pkdir_n)
                cos_pkdir += w * np.cos(pkdir_n)
                depth_local += float(w * self.depth[n_int])

        dir_local = (np.rad2deg(np.arctan2(sin_dir, cos_dir)) % 360.0).astype(np.float32)
        pkdir_local = (np.rad2deg(np.arctan2(sin_pkdir, cos_pkdir)) % 360.0).astype(np.float32)

        return LocalTransferFunction(
            lon=float(lon_q),
            lat=float(lat_q),
            depth=float(depth_local),
            periods=self.periods.copy(),
            frequencies=(1.0 / self.periods).astype(np.float32),
            directions=self.directions.copy(),
            ka_matrix=ka_local.astype(np.float32),
            dir_matrix=dir_local,
            pkdir_matrix=pkdir_local,
            spatial_info=sp,
        )
