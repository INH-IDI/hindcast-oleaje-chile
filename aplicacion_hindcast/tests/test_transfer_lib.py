"""
Pruebas unitarias para la librería de Funciones de Transferencia y Hindcasting de Oleaje.
Verifica:
1. Ponderación multi-boya por distancia y dirección de procedencia del oleaje (N vs S).
2. Interpolación espectral 2D en (frecuencia, dirección) y manejo circular 0°/360°.
3. Invarianza del periodo y proporcionalidad del coeficiente de agitación Ka.
4. Interpolación espacial baricéntrica en mallas triangulares.
"""

import sys
from pathlib import Path
import numpy as np
import netCDF4 as nc
import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from transfer_lib.buoy_weighting import MultiBuoyWeighter, WeightingConfig, haversine_km
from transfer_lib.mesh_interpolator import LocalTransferFunction, TransferMatrixDB


def test_directional_buoy_weighting_north_vs_south():
    """
    Si un punto costero P tiene dos boyas a igual distancia, una al Norte y otra al Sur:
    - Cuando el oleaje viene del Norte (ej. 350° o 340°), la boya Norte debe tener mayor peso.
    - Cuando el oleaje viene del Sur (ej. 190° o 200°), la boya Sur debe tener mayor peso.
    - Cuando el oleaje viene exactamente del Oeste (270°), ambas boyas tienen igual peso.
    """
    lon_p, lat_p = -71.6, -33.0
    # Boya 1 al Norte (-32.0°S), Boya 2 al Sur (-34.0°S), misma longitud (-73.0°W)
    buoy_lons = np.array([-73.0, -73.0])
    buoy_lats = np.array([-32.0, -34.0])

    weighter = MultiBuoyWeighter(
        buoy_lons=buoy_lons,
        buoy_lats=buoy_lats,
        buoy_names=["Boya_Norte", "Boya_Sur"],
        config=WeightingConfig(mode="dist_dir", max_buoys=2, dir_gamma=0.85, dir_power=2.0),
    )

    # Tres estados de mar: [Norte (350°), Oeste (270°), Sur (190°)]
    wave_dirs = np.array([350.0, 270.0, 190.0])
    weights, info = weighter.compute_weights(lon_p, lat_p, wave_dirs)

    # Identificar cuál fila corresponde a Boya_Norte y cuál a Boya_Sur
    idx_n = info["buoy_names"].index("Boya_Norte")
    idx_s = info["buoy_names"].index("Boya_Sur")

    # Caso 0: Ola del Norte (350°) -> peso Norte > peso Sur
    assert weights[idx_n, 0] > weights[idx_s, 0], (
        f"Para ola del Norte (350°), Boya Norte ({weights[idx_n, 0]:.3f}) "
        f"debe superar a Boya Sur ({weights[idx_s, 0]:.3f})"
    )
    assert weights[idx_n, 0] > 0.70

    # Caso 1: Ola del Oeste (270°) -> pesos prácticamente iguales (diferencia sólo por esfericidad < 1%)
    assert np.isclose(weights[idx_n, 1], weights[idx_s, 1], atol=0.02)

    # Caso 2: Ola del Sur (190°) -> peso Sur > peso Norte
    assert weights[idx_s, 2] > weights[idx_n, 2], (
        f"Para ola del Sur (190°), Boya Sur ({weights[idx_s, 2]:.3f}) "
        f"debe superar a Boya Norte ({weights[idx_n, 2]:.3f})"
    )
    assert weights[idx_s, 2] > 0.70


def test_distance_weighting_priority():
    """A igual dirección, una boya más cercana recibe mayor peso que una más lejana."""
    lon_p, lat_p = -71.6, -33.0
    buoy_lons = np.array([-72.0, -74.0])
    buoy_lats = np.array([-33.0, -33.0])

    weighter = MultiBuoyWeighter(
        buoy_lons=buoy_lons,
        buoy_lats=buoy_lats,
        buoy_names=["Cercana", "Lejana"],
        config=WeightingConfig(mode="dist_dir", max_buoys=2),
    )
    weights, info = weighter.compute_weights(lon_p, lat_p, np.array([270.0]))
    idx_near = info["buoy_names"].index("Cercana")
    idx_far = info["buoy_names"].index("Lejana")
    assert weights[idx_near, 0] > weights[idx_far, 0]


def test_local_transfer_function_interpolation_and_circular_dir():
    """
    Verifica:
    1) Interpolación bilineal en frecuencia (f=1/T) y dirección.
    2) Interpolación circular sin saltos en el cruce 359° <-> 1°.
    3) Invarianza del periodo y proporcionalidad Hm0_AS = Ka * Hm0_AP.
    """
    periods = np.array([8.0, 12.0, 16.0], dtype=np.float32)
    directions = np.array([180.0, 270.0, 360.0], dtype=np.float32)

    # Matriz Ka sintética
    ka_mat = np.array([
        [0.4, 0.8, 0.6],
        [0.5, 0.9, 0.7],
        [0.6, 1.0, 0.8],
    ], dtype=np.float32)

    # Matriz de direcciones que cruza 358° -> 2° entre 270° y 360°
    dir_mat = np.array([
        [200.0, 358.0, 2.0],
        [200.0, 358.0, 2.0],
        [200.0, 358.0, 2.0],
    ], dtype=np.float32)

    tf = LocalTransferFunction(
        lon=-71.6,
        lat=-33.0,
        depth=25.0,
        periods=periods,
        frequencies=1.0 / periods,
        directions=directions,
        ka_matrix=ka_mat,
        dir_matrix=dir_mat,
        pkdir_matrix=dir_mat,
        spatial_info={"method": "test"},
    )

    # Evaluar en el punto medio direccional (315°, entre 270° y 360°) con T=12s y Hm0=2.5m
    res = tf.evaluate(
        periods_ap=np.array([12.0]),
        dirs_ap=np.array([315.0]),
        hm0_ap=np.array([2.5]),
    )
    # Ka en T=12s entre 270° (0.9) y 360° (0.7) es 0.8
    assert np.isclose(res["Ka"][0], 0.8, atol=1e-4)
    assert np.isclose(res["Hm0_AS"][0], 2.5 * 0.8, atol=1e-4)
    assert np.isclose(res["T_AS"][0], 12.0, atol=1e-5)

    # La dirección media circular entre 358° y 2° debe ser 0° (o 360°), NUNCA 180°
    dir_val = res["Dir_AS"][0]
    assert dir_val < 5.0 or dir_val > 355.0, f"Interpolación circular falló: dio {dir_val}°"


def test_barycentric_mesh_interpolation(tmp_path):
    """Verifica que TransferMatrixDB interpole exactamente en un triángulo sintético."""
    nc_file = tmp_path / "synthetic_tf.nc"
    with nc.Dataset(nc_file, "w") as ds:
        ds.createDimension("period", 2)
        ds.createDimension("direction", 2)
        ds.createDimension("node", 3)
        ds.createDimension("triangle", 1)
        ds.createDimension("three", 3)

        vp = ds.createVariable("period", "f4", ("period",))
        vd = ds.createVariable("direction", "f4", ("direction",))
        vlon = ds.createVariable("lon", "f8", ("node",))
        vlat = ds.createVariable("lat", "f8", ("node",))
        vdep = ds.createVariable("depth", "f4", ("node",))
        vtri = ds.createVariable("triangles", "i4", ("triangle", "three"))
        vka = ds.createVariable("Ka", "f4", ("period", "direction", "node"))
        vdir = ds.createVariable("Dir", "f4", ("period", "direction", "node"))

        vp[:] = [8.0, 16.0]
        vd[:] = [180.0, 360.0]
        vlon[:] = [-72.0, -71.0, -72.0]
        vlat[:] = [-33.0, -33.0, -32.0]
        vdep[:] = [50.0, 20.0, 40.0]
        vtri[:] = [[0, 1, 2]]

        # Ka distinto en cada vértice: nodo 0 -> 0.5, nodo 1 -> 0.8, nodo 2 -> 1.1
        vka[:, :, 0] = 0.5
        vka[:, :, 1] = 0.8
        vka[:, :, 2] = 1.1
        vdir[:, :, :] = 250.0

    db = TransferMatrixDB(nc_file)
    # Centroide del triángulo: (-71.6667, -32.6667) -> pesos (1/3, 1/3, 1/3) -> Ka = 0.8
    tf_centroid = db.get_local_transfer_function(-71.0 / 3.0 - 48.0, -32.0 / 3.0 - 22.0)
    assert tf_centroid.spatial_info["method"] == "barycentric_triangle"
    assert np.isclose(tf_centroid.ka_matrix[0, 0], 0.8, atol=1e-3)


def test_end_to_end_engine_on_chile_250k():
    """Prueba de integración extremo a extremo sobre la matriz real chile_250k y datos UV/1deg."""
    from transfer_lib import WaveHindcastEngine

    engine = WaveHindcastEngine(buoy_mode="1deg")
    res = engine.run_hindcast(
        lon=-71.6272,
        lat=-33.5882,
        site_name="San_Anto",
        start_date="2015-08-01",
        end_date="2015-08-15",
        weighting_config=WeightingConfig(mode="dist_dir", max_buoys=4),
    )
    assert len(res.timeseries) > 100
    assert np.all(np.isfinite(res.timeseries["Hm0_AS"]))
    assert np.all(res.timeseries["Hm0_AS"] >= 0.0)
    assert np.all((res.timeseries["Dir_AS"] >= 0.0) & (res.timeseries["Dir_AS"] <= 360.0))
    # Verificar que los pesos de las 4 boyas suman 1.0 en cada instante
    w_cols = [c for c in res.timeseries.columns if c.startswith("w_")]
    assert len(w_cols) == 4
    w_sum = res.timeseries[w_cols].sum(axis=1).to_numpy()
    assert np.allclose(w_sum, 1.0, atol=1e-4)

    # Verificar resolución horaria (dt_hours=1) vs tri-horaria (dt_hours=3)
    res_1h = engine.run_hindcast(
        lon=-71.6272,
        lat=-33.5882,
        site_name="San_Anto_1h",
        start_date="2006-01-01",
        end_date="2015-12-31",
        dt_hours=1,
    )
    dt_diffs_1h = res_1h.timeseries["DateTime"].diff().dropna()
    assert (dt_diffs_1h == np.timedelta64(1, "h")).all()
    assert len(res_1h.timeseries) > 87000  # 10 años a 1 hora (~87,646 registros)



