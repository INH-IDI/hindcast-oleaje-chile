"""
Librería de Funciones de Transferencia y Hindcasting Rápido de Oleaje en Chile.
"""

from .catalog import load_coastal_sites, load_buoy_catalog
from .buoy_weighting import MultiBuoyWeighter, WeightingConfig, haversine_km, bearing_deg
from .mesh_interpolator import TransferMatrixDB, LocalTransferFunction
from .hindcast_engine import WaveHindcastEngine, DeepWaterHindcastDB, HindcastResult
from .forecast_engine import NOAAWaveForecastClient, DeepWaterForecastDB

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
]
