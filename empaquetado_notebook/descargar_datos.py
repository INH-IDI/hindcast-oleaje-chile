"""
Script de Descarga y Verificación de Bases de Datos NetCDF4 para Oleaje Chile.
Compatible con Windows (PowerShell/CMD) y Linux/WSL.

Descarga los archivos binarios pesados publicados en GitHub Releases si no están presentes:
- matriz_transferencia_chile.nc (~985 MB)
- hindcast_ap_1deg_chile.nc (~91 MB)
- hindcast_uv_14nodos.nc (~46 MB, opcional)
"""

import os
import sys
import shutil
import urllib.request
from pathlib import Path

GITHUB_REPO = "INH-IDI/hindcast-oleaje-chile"
RELEASE_TAG = "v1.0.0"
BASE_URL = f"https://github.com/{GITHUB_REPO}/releases/download/{RELEASE_TAG}"

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

FILES = [
    {
        "name": "matriz_transferencia_chile.nc",
        "size_mb": 985,
        "required": True,
        "desc": "Matriz de transferencia SWAN (chile_250k)",
    },
    {
        "name": "hindcast_ap_1deg_chile.nc",
        "size_mb": 91,
        "required": True,
        "desc": "Base de datos AP (28 boyas cada 1° latitud, 1980-2015)",
    },
    {
        "name": "hindcast_uv_14nodos.nc",
        "size_mb": 46,
        "required": False,
        "desc": "Base de datos AP oficial Atlas UV (14 nodos, 1980-2015)",
    },
]


def download_with_progress(url: str, dest_path: Path):
    print(f"\nDescargando: {url}")
    print(f"Destino: {dest_path}")

    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 100 / totalsize
            mb_read = readsofar / (1024 * 1024)
            mb_tot = totalsize / (1024 * 1024)
            bar_len = 35
            filled_len = int(bar_len * percent // 100)
            bar = "=" * filled_len + "-" * (bar_len - filled_len)
            sys.stdout.write(f"\r  [{bar}] {percent:5.1f}% ({mb_read:6.1f} / {mb_tot:6.1f} MB)")
            sys.stdout.flush()
        else:
            mb_read = readsofar / (1024 * 1024)
            sys.stdout.write(f"\r  Descargados {mb_read:6.1f} MB...")
            sys.stdout.flush()

    tmp_path = dest_path.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(url, tmp_path, reporthook=reporthook)
        print()
        if tmp_path.exists():
            tmp_path.replace(dest_path)
            print(f"OK: {dest_path.name} completado ({dest_path.stat().st_size / (1024*1024):.1f} MB)")
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise e


def check_local_parent():
    """Si este paquete se encuentra dentro del repositorio superSimple, vincula los datos locales."""
    super_simple = Path(__file__).resolve().parents[1]
    candidates = [
        (super_simple / "trabajo_swan" / "matrices" / "matriz_transferencia_chile.nc", DATA_DIR / "matriz_transferencia_chile.nc"),
        (super_simple / "datos_ap_uv" / "processed" / "hindcast_ap_1deg_chile.nc", DATA_DIR / "hindcast_ap_1deg_chile.nc"),
        (super_simple / "datos_ap_uv" / "processed" / "hindcast_uv_14nodos.nc", DATA_DIR / "hindcast_uv_14nodos.nc"),
    ]
    for src, dst in candidates:
        if src.exists() and not dst.exists():
            try:
                # Intentar enlace simbólico (Linux/WSL)
                os.symlink(src, dst)
                print(f"Vinculado archivo local (symlink): {dst.name} -> {src}")
            except Exception:
                try:
                    # Enlace duro o copia
                    os.link(src, dst)
                    print(f"Vinculado archivo local (hardlink): {dst.name}")
                except Exception:
                    pass


def main():
    print("=" * 70)
    print("  VERIFICACIÓN DE BASES DE DATOS NETCDF - OLEAJE CHILE")
    print("=" * 70)

    # 1. Intentar enlazar si existe copia local en el entorno de desarrollo
    check_local_parent()

    all_ok = True
    for item in FILES:
        fname = item["name"]
        target = DATA_DIR / fname
        if target.exists() and target.stat().st_size > 1024 * 1024:
            size_mb = target.stat().st_size / (1024 * 1024)
            print(f"[OK] {fname} ({size_mb:.1f} MB) presente en {DATA_DIR}")
        else:
            if item["required"]:
                all_ok = False
                print(f"[FALTA] {fname} (~{item['size_mb']} MB) - {item['desc']}")
                url = f"{BASE_URL}/{fname}"
                try:
                    download_with_progress(url, target)
                except Exception as err:
                    print(f"Error descargando {fname}: {err}")
                    print(f"Por favor descargue manualmente {fname} desde:")
                    print(f"  {url}")
                    print(f"y colóquelo dentro de la carpeta: {DATA_DIR}\n")
            else:
                print(f"[OPCIONAL] {fname} no presente (no requerido para modo 1°).")

    print("\nVerificación finalizada.")
    print(f"Ruta de datos: {DATA_DIR.resolve()}\n")


if __name__ == "__main__":
    main()
