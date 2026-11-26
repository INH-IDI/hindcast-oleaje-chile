"""
Librería de Funciones de Transferencia y Hindcasting Rápido de Oleaje en Chile.
"""

from .catalog import load_coastal_sites, load_buoy_catalog
from .buoy_weighting import MultiBuoyWeighter, WeightingConfig, haversine_km, bearing_deg
from .mesh_interpolator import TransferMatrixDB, LocalTransferFunction
from .hindcast_engine import WaveHindcastEngine, DeepWaterHindcastDB, HindcastResult
from .forecast_engine import NOAAWaveForecastClient, DeepWaterForecastDB
from .era5_engine import (
    ERA5Credentials,
    DeepWaterERA5DB,
    ERA5WaveClient,
    DEFAULT_CDS_URL,
    resolve_era5_credentials,
    read_cdsapirc,
    save_cdsapirc,
    parse_era5_netcdf_to_db,
)

__all__ = [
    "load_coastal_sites",
    "load_buoy_catalog",
    "MultiBuoyWeighter",
    "WeightingConfig",
    "haversine_km",
    "bearing_deg",
    "TransferMatrixDB",
    "LocalTransferFunction",
    "WaveHindcastEngine",
    "DeepWaterHindcastDB",
    "HindcastResult",
    "NOAAWaveForecastClient",
    "DeepWaterForecastDB",
    "ERA5Credentials",
    "DeepWaterERA5DB",
    "ERA5WaveClient",
    "DEFAULT_CDS_URL",
    "resolve_era5_credentials",
    "read_cdsapirc",
    "save_cdsapirc",
    "parse_era5_netcdf_to_db",
]
