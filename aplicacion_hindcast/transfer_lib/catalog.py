"""
Catálogo de sitios costeros (puertos, nodos de interés, 569 caletas de Chile)
y boyas de aguas profundas (14 nodos Atlas UV y 28 boyas cada 1°).
"""

import re
from pathlib import Path
from typing import List, Dict, Optional
import pandas as pd

SUPER_SIMPLE_DIR = Path(__file__).resolve().parents[2]
MODELO_PRONOSTICO_DIR = SUPER_SIMPLE_DIR / "modelo_pronostico"
DATOS_AP_DIR = SUPER_SIMPLE_DIR / "datos_ap_uv"


def load_coastal_sites() -> pd.DataFrame:
    """
    Lee los sitios costeros predefinidos en el modelo SWAN:
    - Puertos chilenos (25 sitios)
    - Nodos de interés costero (57 sitios)
    - Caletas pesqueras y obras costeras DOP (569 sitios)
    Retorna un DataFrame con columnas: ['name', 'category', 'lon', 'lat'].
    """
    records: List[Dict] = []

    # 1. Leer puertos y puntos de interés desde swan_INPUT.swn
    swan_inp = MODELO_PRONOSTICO_DIR / "base" / "swan_INPUT.swn"
    if swan_inp.exists():
        current_category = "General"
        for line in swan_inp.read_text(encoding="latin-1").splitlines():
            s = line.strip()
            if "AGUAS PROFUNDAS" in s:
                current_category = "Aguas_Profundas_SWAN"
            elif "PUERTOS CHILENOS" in s:
                current_category = "Puerto"
            elif "NODOS INTERES" in s:
                current_category = "Nodo_Interes"
            elif "TABLAS" in s:
                break

            if s.startswith("POINTS"):
                m = re.match(r"POINTS\s+'([^']+)'\s+([-\d.]+)\s+([-\d.]+)", s)
                if m and current_category in ("Puerto", "Nodo_Interes"):
                    records.append({
                        "name": m.group(1).strip(),
                        "category": current_category,
                        "lon": float(m.group(2)),
                        "lat": float(m.group(3)),
                    })

    # 2. Leer las 569 caletas y obras desde xy_pro_caletas_dop.txt
    caletas_file = MODELO_PRONOSTICO_DIR / "base" / "xy_pro_caletas_dop.txt"
    if caletas_file.exists():
        for line in caletas_file.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s.startswith("POINT"):
                continue
            parts = s.split()
            if len(parts) >= 4:
                try:
                    lon = float(parts[-2])
                    lat = float(parts[-1])
                    raw_name = " ".join(parts[1:-2]).strip("'\"")
                    records.append({
                        "name": raw_name,
                        "category": "Caleta_DOP",
                        "lon": lon,
                        "lat": lat,
                    })
                except ValueError:
                    continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["name", "category"]).reset_index(drop=True)
    return df


def load_buoy_catalog(mode: str = "1deg", datos_ap_dir: Optional[Path] = None) -> pd.DataFrame:
    """
    Carga el catálogo de boyas de aguas profundas.
    mode:
      - '1deg': 28 boyas cada 1° de latitud (-18° a -45°S)
      - 'uv14': 14 nodos originales del Atlas de Oleaje UV (-19° a -45°S cada 2°)
    """
    base = Path(datos_ap_dir) if datos_ap_dir else DATOS_AP_DIR
    if mode == "uv14":
        csv_path = base / "catalogo_nodos_uv.csv"
    else:
        csv_path = base / "catalogo_boyas_1deg.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No se encontró el catálogo de boyas en {csv_path}")
    return pd.read_csv(csv_path)
