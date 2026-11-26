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


def test_forecast_deepwater_db_structure_and_persistence(tmp_path):
    """Verifica la creación, indexado y persistencia en disco de DeepWaterForecastDB."""
    from transfer_lib import DeepWaterForecastDB
    import pandas as pd

    timestamps = pd.date_range("2026-11-04 12:00:00", periods=16, freq="3h")
    n_buoys = 4
    ids = np.arange(1, n_buoys + 1, dtype=np.int32)
    lats = np.array([-32.0, -33.0, -34.0, -35.0])
    lons = np.array([-73.0, -73.0, -73.0, -73.0])
    names = [f"Boya_{i}" for i in ids]

    data = {
        "Hm0": np.ones((n_buoys, len(timestamps)), dtype=np.float32) * 2.5,
        "Tp": np.ones((n_buoys, len(timestamps)), dtype=np.float32) * 14.0,
        "Tm": np.ones((n_buoys, len(timestamps)), dtype=np.float32) * 12.0,
        "Tz": np.ones((n_buoys, len(timestamps)), dtype=np.float32) * 11.0,
        "Dm": np.ones((n_buoys, len(timestamps)), dtype=np.float32) * 230.0,
        "Dp": np.ones((n_buoys, len(timestamps)), dtype=np.float32) * 230.0,
        "s": np.full((n_buoys, len(timestamps)), 10.0, dtype=np.float32),
    }

    db = DeepWaterForecastDB(ids, lats, lons, names, timestamps, data, metadata={"source": "test_ww3"})
    assert len(db.timestamps) == 16
    assert db.data["Hm0"].shape == (4, 16)

    # Subconjunto temporal
    s = db.subset_time_slice("2026-11-04 15:00:00", "2026-11-05 00:00:00")
    assert len(db.timestamps[s]) == 4

    # Guardar y recargar sin pickle
    npz_path = tmp_path / "forecast_test.npz"
    db.save_npz(npz_path)
    loaded = DeepWaterForecastDB.from_npz(npz_path)
    assert len(loaded.timestamps) == 16
    assert np.allclose(loaded.data["Hm0"], db.data["Hm0"])
    assert loaded.names == names


def test_end_to_end_forecast_simulation_noaa_ww3():
    """Verifica la simulación de pronóstico operacional NOAA WW3 sobre la costa chilena."""
    from transfer_lib import WaveHindcastEngine, WeightingConfig

    engine = WaveHindcastEngine(mode="forecast", buoy_mode="1deg")
    res = engine.run_forecast(
        lon=-71.6145,
        lat=-33.0325,
        site_name="Valparaiso_Forecast",
        weighting_config=WeightingConfig(mode="dist_dir", max_buoys=4),
    )

    assert len(res.timeseries) >= 10
    assert np.all(np.isfinite(res.timeseries["Hm0_AS"]))
    assert np.all(res.timeseries["Hm0_AS"] >= 0.0)
    assert np.all(res.timeseries["Tp_AS"] > 0.0)
    assert np.all((res.timeseries["Dir_AS"] >= 0.0) & (res.timeseries["Dir_AS"] <= 360.0))
    assert res.summary_stats["Hm0_AS_mean"] > 0.0


def _write_synthetic_era5_nc(
    path: Path,
    timestamps,
    legacy_format: bool = False,
    with_expver: bool = False,
    mask_eastern_cell: bool = False,
):
    """Genera un archivo NetCDF sintético estilo Copernicus CDS ERA5 sobre el dominio chileno."""
    lats = np.arange(-18.0, -45.5, -1.0, dtype=np.float64)
    lons_neg = np.array([-76.0, -75.0, -74.0, -73.0, -72.0], dtype=np.float64)
    lons = (lons_neg % 360.0) if legacy_format else lons_neg

    n_t = len(timestamps)
    n_lat = len(lats)
    n_lon = len(lons)

    with nc.Dataset(path, "w") as ds:
        t_dim = "time" if legacy_format else "valid_time"
        ds.createDimension(t_dim, n_t)
        ds.createDimension("latitude", n_lat)
        ds.createDimension("longitude", n_lon)
        if with_expver:
            ds.createDimension("expver", 2)

        vt = ds.createVariable(t_dim, "f8", (t_dim,))
        if legacy_format:
            vt.units = "hours since 1900-01-01 00:00:00"
            vt.calendar = "gregorian"
            vt[:] = nc.date2num([ts.to_pydatetime() for ts in timestamps], units=vt.units, calendar=vt.calendar)
        else:
            vt.units = "seconds since 1970-01-01 00:00:00"
            vt.calendar = "proleptic_gregorian"
            vt[:] = nc.date2num([ts.to_pydatetime() for ts in timestamps], units=vt.units, calendar=vt.calendar)

        vlat = ds.createVariable("latitude", "f8", ("latitude",))
        vlon = ds.createVariable("longitude", "f8", ("longitude",))
        vlat[:] = lats
        vlon[:] = lons

        dims = (t_dim, "expver", "latitude", "longitude") if with_expver else (t_dim, "latitude", "longitude")
        swh_base = np.full((n_t, n_lat, n_lon), 2.4, dtype=np.float32)
        pp1d_base = np.full((n_t, n_lat, n_lon), 13.5, dtype=np.float32)
        mwp_base = np.full((n_t, n_lat, n_lon), 11.2, dtype=np.float32)
        mp2_base = np.full((n_t, n_lat, n_lon), 9.6, dtype=np.float32)
        mwd_base = np.full((n_t, n_lat, n_lon), 225.0, dtype=np.float32)

        if mask_eastern_cell:
            # Simular máscara de tierra en -72°W
            swh_base[:, :, -1] = np.nan
            pp1d_base[:, :, -1] = np.nan
            mwp_base[:, :, -1] = np.nan
            mp2_base[:, :, -1] = np.nan
            mwd_base[:, :, -1] = np.nan

        for name, arr in [
            ("swh", swh_base),
            ("pp1d", pp1d_base),
            ("mwp", mwp_base),
            ("mp2", mp2_base),
            ("mwd", mwd_base),
        ]:
            v = ds.createVariable(name, "f4", dims, fill_value=np.float32(np.nan))
            if with_expver:
                data4d = np.empty((n_t, 2, n_lat, n_lon), dtype=np.float32)
                data4d[:, 0, :, :] = arr
                data4d[:, 1, :, :] = arr
                # Últimos pasos vienen en expver=1 (ERA5T), expver=0 en NaN
                if n_t >= 2:
                    data4d[-2:, 0, :, :] = np.nan
                v[:] = data4d
            else:
                v[:] = arr


def test_era5_credentials_resolution_and_cdsapirc_roundtrip(tmp_path, monkeypatch):
    """Verifica resolución de credenciales Copernicus CDS y lectura/escritura de .cdsapirc."""
    import os
    import stat
    from transfer_lib.era5_engine import (
        DEFAULT_CDS_URL,
        resolve_era5_credentials,
        read_cdsapirc,
        save_cdsapirc,
    )

    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.delenv("CDSAPI_URL", raising=False)
    monkeypatch.delenv("CDSAPI_RC", raising=False)

    rc_file = tmp_path / ".cdsapirc"
    creds_none = resolve_era5_credentials(rc_path=rc_file)
    assert not creds_none.is_configured
    assert creds_none.source == "none"

    # Guardar y leer token moderno
    saved_path = save_cdsapirc(key="my-personal-access-token", url=DEFAULT_CDS_URL, rc_path=rc_file)
    assert saved_path == rc_file
    if os.name == "posix":
        mode = stat.S_IMODE(rc_file.stat().st_mode)
        assert mode == 0o600

    rc_read = read_cdsapirc(rc_path=rc_file)
    assert rc_read is not None
    assert rc_read.is_configured
    assert rc_read.key == "my-personal-access-token"
    assert rc_read.source == "cdsapirc"

    # También soportar formato uid:key heredado
    rc_file.write_text("url: https://cds.climate.copernicus.eu/api\nkey: 12345:abc-def-key\n", encoding="utf-8")
    rc_legacy = read_cdsapirc(rc_path=rc_file)
    assert rc_legacy.key == "12345:abc-def-key"

    # Prioridad: explicit > env > cdsapirc
    monkeypatch.setenv("CDSAPI_KEY", "env-token")
    c_env = resolve_era5_credentials(rc_path=rc_file)
    assert c_env.source == "env"
    assert c_env.key == "env-token"

    c_exp = resolve_era5_credentials(cds_key="explicit-token", rc_path=rc_file)
    assert c_exp.source == "explicit"
    assert c_exp.key == "explicit-token"


def test_era5_netcdf_parsing_new_cds_legacy_expver_zip_and_land_mask(tmp_path):
    """Verifica parseo ERA5 para formato nuevo (valid_time), legacy (expver + zip) y máscara tierra."""
    import zipfile
    import pandas as pd
    from transfer_lib.era5_engine import parse_era5_netcdf_to_db

    ts1 = pd.date_range("2024-01-01 00:00:00", periods=6, freq="1h")
    nc_new = tmp_path / "era5_new.nc"
    _write_synthetic_era5_nc(nc_new, ts1, legacy_format=False, with_expver=False, mask_eastern_cell=True)

    db_new = parse_era5_netcdf_to_db(nc_new, buoy_mode="1deg")
    assert len(db_new.timestamps) == 6
    assert db_new.data["Hm0"].shape == (28, 6)
    assert np.all(np.isfinite(db_new.data["Hm0"]))
    assert np.allclose(db_new.data["Hm0"], 2.4, atol=1e-4)
    assert np.allclose(db_new.data["Te"], 11.2, atol=1e-4)
    assert np.allclose(db_new.data["Dm"], 225.0, atol=1e-4)

    # Formato legacy con expver 4D + empaquetado en .zip
    ts2 = pd.date_range("2024-02-01 00:00:00", periods=4, freq="1h")
    nc_leg = tmp_path / "era5_legacy.nc"
    _write_synthetic_era5_nc(nc_leg, ts2, legacy_format=True, with_expver=True, mask_eastern_cell=False)
    zip_path = tmp_path / "era5_legacy.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(nc_leg, arcname="data.nc")

    db_zip = parse_era5_netcdf_to_db(zip_path, buoy_mode="1deg")
    assert len(db_zip.timestamps) == 4
    assert np.all(np.isfinite(db_zip.data["Hm0"]))
    assert np.allclose(db_zip.data["Tp"], 13.5, atol=1e-4)


def test_era5_client_monthly_cache_and_mocked_cds_download(tmp_path, monkeypatch):
    """Verifica agrupación de solicitudes, caché mensual ERA5 y cero llamadas cuando está cacheado."""
    import types
    import pandas as pd
    from transfer_lib.era5_engine import ERA5WaveClient

    calls = []

    class FakeCDSClient:
        def __init__(self, url=None, key=None, quiet=True):
            self.url = url
            self.key = key

        def retrieve(self, dataset, request, target):
            calls.append({"dataset": dataset, "request": dict(request)})
            year = int(request["year"])
            months = request["month"] if isinstance(request["month"], list) else [request["month"]]
            days = [int(d) for d in request["day"]]
            hours = [int(t.split(":")[0]) for t in request["time"]]

            stamps = []
            for m_str in months:
                m_int = int(m_str)
                for d_int in days:
                    try:
                        base_d = pd.Timestamp(year=year, month=m_int, day=d_int)
                    except ValueError:
                        continue
                    for h_int in hours:
                        stamps.append(base_d + pd.Timedelta(hours=h_int))
            _write_synthetic_era5_nc(Path(target), pd.DatetimeIndex(stamps))

    fake_mod = types.ModuleType("cdsapi")
    fake_mod.Client = FakeCDSClient
    monkeypatch.setitem(sys.modules, "cdsapi", fake_mod)

    cache_dir = tmp_path / "era5_cache"
    client = ERA5WaveClient(cds_key="fake-token", cache_dir=cache_dir)

    # 1. Primera descarga: 2024-01-01 a 2024-02-29 (dos meses completos agrupados en 1 llamada)
    db1 = client.get_era5_data(
        buoy_mode="1deg",
        start_date="2024-01-01",
        end_date="2024-02-29",
        step_hours=3,
    )
    assert len(calls) == 1
    assert (cache_dir / "era5_1deg_2024_01_3h.npz").exists()
    assert (cache_dir / "era5_1deg_2024_02_3h.npz").exists()
    assert len(db1.timestamps) == 60 * 8

    # 2. Sub-rango ya cacheado -> 0 llamadas adicionales a CDS
    db2 = client.get_era5_data(
        buoy_mode="1deg",
        start_date="2024-01-10",
        end_date="2024-01-20",
        step_hours=3,
    )
    assert len(calls) == 1
    assert len(db2.timestamps) == 11 * 8

    # 3. Extensión hasta 2024-03-05 -> solo descarga marzo
    db3 = client.get_era5_data(
        buoy_mode="1deg",
        start_date="2024-01-01",
        end_date="2024-03-05",
        step_hours=3,
    )
    assert len(calls) == 2
    assert calls[1]["request"]["month"] == "03"
    assert len(db3.timestamps) == (60 + 5) * 8


def test_end_to_end_era5_engine_1h_and_3h_on_chile_250k(tmp_path):
    """Prueba extremo a extremo de WaveHindcastEngine en modo 'era5' sobre chile_250k (1h y 3h)."""
    import pandas as pd
    from transfer_lib import WaveHindcastEngine, WeightingConfig

    ts_1h = pd.date_range("2024-01-01 00:00:00", periods=48, freq="1h")
    nc_path = tmp_path / "era5_48h.nc"
    _write_synthetic_era5_nc(nc_path, ts_1h)

    engine = WaveHindcastEngine(
        mode="era5",
        buoy_mode="1deg",
        era5_nc_path=nc_path,
    )

    # Paso 1h preserva exactamente las 48 estampas horarias
    res_1h = engine.run_era5(
        lon=-71.6145,
        lat=-33.0325,
        site_name="Valparaiso_ERA5_1h",
        weighting_config=WeightingConfig(mode="dist_dir", max_buoys=4),
        dt_hours=1,
    )
    assert len(res_1h.timeseries) == 48
    dt_diffs_1h = res_1h.timeseries["DateTime"].diff().dropna()
    assert (dt_diffs_1h == np.timedelta64(1, "h")).all()
    assert np.all(np.isfinite(res_1h.timeseries["Hm0_AS"]))
    assert np.all(res_1h.timeseries["Hm0_AS"] >= 0.0)
    assert np.all((res_1h.timeseries["Dir_AS"] >= 0.0) & (res_1h.timeseries["Dir_AS"] <= 360.0))
    w_cols = [c for c in res_1h.timeseries.columns if c.startswith("w_")]
    assert np.allclose(res_1h.timeseries[w_cols].sum(axis=1).to_numpy(), 1.0, atol=1e-4)

    # Paso 3h remuestrea limpiamente cada 3 horas
    res_3h = engine.run_era5(
        lon=-71.6145,
        lat=-33.0325,
        site_name="Valparaiso_ERA5_3h",
        weighting_config=WeightingConfig(mode="dist_dir", max_buoys=4),
        dt_hours=3,
    )
    assert len(res_3h.timeseries) == 16
    dt_diffs_3h = res_3h.timeseries["DateTime"].diff().dropna()
    assert (dt_diffs_3h == np.timedelta64(3, "h")).all()




