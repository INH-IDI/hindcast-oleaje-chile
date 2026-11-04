#!/usr/bin/env python3
"""
Script de Empaquetamiento Autónomo para Notebook / Portátil (Windows y WSL Linux).
Copia todos los módulos de código, catálogos, recursos gráficos y archivos de inicio
en 'empaquetado_notebook/', y opcionalmente genera un archivo .ZIP listo para transferir.

Uso:
  python3 empaquetar.py [--zip]
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_APP = ROOT_DIR / "aplicacion_hindcast"
DEST_PKG = ROOT_DIR / "empaquetado_notebook"


def sync_package(create_zip: bool = False):
    print("=" * 70)
    print("  EMPAQUETANDO APLICACIÓN OLEAJE CHILE PARA NOTEBOOK (WINDOWS / WSL)")
    print("=" * 70)

    DEST_PKG.mkdir(parents=True, exist_ok=True)
    (DEST_PKG / "data").mkdir(exist_ok=True)
    (DEST_PKG / "assets").mkdir(exist_ok=True)
    (DEST_PKG / "forecast_cache").mkdir(exist_ok=True)

    # 1. Copiar app.py
    shutil.copy2(SRC_APP / "app.py", DEST_PKG / "app.py")
    print("[1/6] Copiado app.py")

    # 2. Copiar transfer_lib (código fuente limpio, sin __pycache__)
    dest_lib = DEST_PKG / "transfer_lib"
    if dest_lib.exists():
        shutil.rmtree(dest_lib)
    shutil.copytree(
        SRC_APP / "transfer_lib",
        dest_lib,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    print("[2/6] Copiado paquete transfer_lib/")

    # 3. Copiar assets (Logotipo INH)
    if (SRC_APP / "assets" / "INH.png").exists():
        shutil.copy2(SRC_APP / "assets" / "INH.png", DEST_PKG / "assets" / "INH.png")
    elif (ROOT_DIR / "INH.png").exists():
        shutil.copy2(ROOT_DIR / "INH.png", DEST_PKG / "assets" / "INH.png")
    print("[3/6] Copiado assets/INH.png")

    # 4. Exportar y copiar catálogos a data/
    from aplicacion_hindcast.transfer_lib.catalog import load_coastal_sites
    df_sites = load_coastal_sites()
    df_sites.to_csv(DEST_PKG / "data" / "sitios_costeros.csv", index=False)
    shutil.copy2(ROOT_DIR / "datos_ap_uv" / "catalogo_boyas_1deg.csv", DEST_PKG / "data" / "catalogo_boyas_1deg.csv")
    shutil.copy2(ROOT_DIR / "datos_ap_uv" / "catalogo_nodos_uv.csv", DEST_PKG / "data" / "catalogo_nodos_uv.csv")
    print(f"[4/6] Exportados catálogos a data/ ({len(df_sites)} sitios costeros + 28 boyas)")

    # 5. Copiar caché de pronóstico más reciente si existe
    src_fc = SRC_APP / "forecast_cache"
    if src_fc.exists():
        for fc_file in src_fc.glob("*.npz"):
            shutil.copy2(fc_file, DEST_PKG / "forecast_cache" / fc_file.name)
    print("[5/6] Sincronizado forecast_cache/")

    # 6. Generar archivo .ZIP si se solicitó
    if create_zip:
        zip_path = ROOT_DIR / "oleaje_chile_notebook.zip"
        print(f"\nGenerando archivo comprimido {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(DEST_PKG):
                dirs[:] = [d for d in dirs if d not in [".venv", "__pycache__", ".git"]]
                for f in files:
                    if f.endswith((".pyc", ".tmp")) or f.endswith(".nc"):
                        continue
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(DEST_PKG)
                    zf.write(full_p, arcname=rel_p)
        print(f"[6/6] ZIP generado exitosamente: {zip_path} ({zip_path.stat().st_size / (1024*1024):.2f} MB)")
    else:
        print("[6/6] Estructura de paquete lista en 'empaquetado_notebook/'")

    print("\nEmpaquetamiento completado con éxito.")


if __name__ == "__main__":
    make_zip = "--zip" in sys.argv
    sync_package(create_zip=make_zip)
