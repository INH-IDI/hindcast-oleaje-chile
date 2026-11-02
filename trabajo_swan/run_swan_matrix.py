#!/usr/bin/env python3
"""
Orquestador paralelo para generar las corridas de oleaje unitario (Hs = 1.0 m)
en SWAN sobre la malla chile_250k (255,521 nodos).

Estrategia de optimización:
- Divide el rango de periodos T ∈ [6, 8, 10, 12, 14, 16, 18, 20, 22] s en 9 workers paralelos.
- Cada worker carga la malla chile_250k UNA SOLA VEZ (ahorrando >18 horas de lectura de malla)
  y ejecuta múltiples comandos COMPUTE STAT consecutivos usando un archivo TPAR con reinicio
  en caliente (hot-start en memoria entre direcciones sucesivas).
- Ordena las direcciones en dos pasadas dentro de cada worker:
    * Pasada 1: cada 10° (180°, 190°, ..., 360° -> 19 direcciones por periodo = 171 casos)
    * Pasada 2: intermedias cada 5° (185°, 195°, ..., 355° -> 18 direcciones por periodo = 162 casos)
  De este modo, tras la Pasada 1 ya se dispone de cobertura completa [180°..360°] cada 10°,
  y al terminar la Pasada 2 queda completa la matriz de 333 casos cada 5°.
- Además exporta cada caso individual a trabajo_swan/DataSet/{case_id}_chile.mat.
"""

import argparse
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
import numpy as np
import pandas as pd
import scipy.io as sio


TRABAJO_DIR = Path(__file__).resolve().parent
MESH_DIR = TRABAJO_DIR.parent / "modelo_pronostico" / "malla"
SWAN_BIN = Path(shutil.which("swan.exe") or "/home/model2/local/bin/swan.exe")
SWANINIT_SRC = TRABAJO_DIR.parent / "modelo_pronostico" / "run" / "swaninit"


def generate_direction_order(dmin: float = 180.0, dmax: float = 360.0, step: float = 5.0) -> List[float]:
    """
    Genera las direcciones en tres pasadas progresivas (30° -> 10° -> 5°) dentro de cada worker:
    - Pasada 1 (7 dirs): 180°, 210°, 240°, 270°, 300°, 330°, 360° (cobertura completa del rango en pocos minutos)
    - Pasada 2 (12 dirs): múltiplos restantes de 10° en barrido regresivo 350° -> 190°
    - Pasada 3 (18 dirs): múltiplos impares de 5° en barrido progresivo 185° -> 355°
    Total: 37 direcciones por periodo (333 casos para 9 periodos).
    """
    all_dirs = [float(round(d, 2)) for d in np.arange(dmin, dmax + 0.1, step)]
    if abs(step - 5.0) < 1e-6:
        pass1 = [d for d in all_dirs if int(round(d - dmin)) % 30 == 0]
        pass2 = [d for d in reversed(all_dirs) if (int(round(d)) % 10 == 0) and (d not in pass1)]
        pass3 = [d for d in all_dirs if (d not in pass1) and (d not in pass2)]
        return pass1 + pass2 + pass3
    return all_dirs


def prepare_workers(
    periods: List[float],
    directions_ordered: List[float],
    spreading: float = 25.0,
    mxitst: int = 12,
) -> pd.DataFrame:
    """
    Crea los directorios de trabajo worker_TXX, enlaces simbólicos cortos a la malla
    (para respetar el límite de caracteres de Fortran en SWAN), archivos casos.tpar e INPUT.
    Retorna el DataFrame catálogo de todos los casos.
    """
    template_text = (TRABAJO_DIR / "base" / "INPUT_template.swn").read_text(encoding="utf-8")
    workers_dir = TRABAJO_DIR / "workers"
    workers_dir.mkdir(parents=True, exist_ok=True)

    # Crear enlace simbólico corto a la malla dentro de trabajo_swan/malla
    local_mesh_dir = TRABAJO_DIR / "malla"
    if not local_mesh_dir.exists():
        os.symlink(MESH_DIR, local_mesh_dir)

    catalog_rows: List[Dict] = []
    base_time = datetime(2024, 1, 1, 0, 0, 0)
    case_global_id = 0

    for p in periods:
        p_int = int(round(p))
        w_name = f"worker_T{p_int:02d}"
        w_dir = workers_dir / w_name
        w_dir.mkdir(parents=True, exist_ok=True)

        # Copiar swaninit
        if SWANINIT_SRC.exists():
            shutil.copy(SWANINIT_SRC, w_dir / "swaninit")

        tpar_lines = ["TPAR"]
        compute_lines = []

        for step_idx, d in enumerate(directions_ordered):
            t_cur = base_time + timedelta(hours=step_idx)
            t_str = t_cur.strftime("%Y%m%d.%H%M%S")
            t_key = t_cur.strftime("%Y%m%d_%H%M%S")
            # Evitar exactamente 360.0 si SWAN prefiere 0.0 o 359.99, aunque 360.0 funciona en SWAN
            d_swan = 359.99 if abs(d - 360.0) < 1e-4 else d
            tpar_lines.append(f"{t_str} 1.0 {p:.2f} {d_swan:.2f} {spreading:.1f}")
            compute_lines.append(f"COMPUTE STAT {t_str}")

            catalog_rows.append({
                "case_id": case_global_id,
                "worker": w_name,
                "period": float(p),
                "frequency": float(1.0 / p),
                "direction": float(d),
                "spreading": float(spreading),
                "step_idx": step_idx,
                "swan_time": t_str,
                "mat_suffix": t_key,
                "out_mat": str(w_dir / f"out_T{p_int:02d}.mat"),
            })
            case_global_id += 1

        (w_dir / "casos.tpar").write_text("\n".join(tpar_lines) + "\n", encoding="utf-8")

        inp_content = template_text.format(
            WORKER_ID=f"T{p_int:02d}",
            MESH_PREFIX="../../malla/chile_250k",
            BOT_FILE="../../malla/chile_250k.bot",
            MXITST=mxitst,
            OUT_MAT=f"out_T{p_int:02d}.mat",
            COMPUTE_COMMANDS="\n".join(compute_lines),
        )
        (w_dir / "INPUT").write_text(inp_content, encoding="utf-8")

    cat_df = pd.DataFrame(catalog_rows)
    cat_df.to_csv(TRABAJO_DIR / "casos_catalogo.csv", index=False)
    return cat_df


def split_worker_mat_to_dataset(cat_df: pd.DataFrame) -> int:
    """
    Lee los archivos out_TXX.mat de cada worker y guarda (o actualiza) los archivos
    individuales por caso en trabajo_swan/DataSet/case_{id:03d}_T{T}_D{Dir}.mat
    para mantener trazabilidad por caso individual.
    Retorna el número total de casos extraídos exitosamente.
    """
    dataset_dir = TRABAJO_DIR / "DataSet"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    completed_count = 0

    for w_name, group in cat_df.groupby("worker"):
        mat_path = Path(group.iloc[0]["out_mat"])
        if not mat_path.exists() or mat_path.stat().st_size < 1000:
            continue
        try:
            m = sio.loadmat(mat_path)
        except Exception:
            continue

        for _, row in group.iterrows():
            suf = row["mat_suffix"]
            k_hs = f"Hsig_{suf}"
            k_dir = f"Dir_{suf}"
            k_pk = f"PkDir_{suf}"
            if k_hs in m and k_dir in m:
                completed_count += 1
                indiv_file = dataset_dir / f"case_{int(row['case_id']):03d}_T{int(row['period']):02d}_D{int(row['direction']):03d}.mat"
                if not indiv_file.exists():
                    sio.savemat(
                        indiv_file,
                        {
                            "Hsig": m[k_hs],
                            "Dir": m[k_dir],
                            "PkDir": m.get(k_pk, m[k_dir]),
                            "period": np.float32(row["period"]),
                            "direction": np.float32(row["direction"]),
                        },
                        do_compression=False,
                    )
    return completed_count


def run_all_workers(cat_df: pd.DataFrame, threads_per_worker: int = 3):
    """Lanza todos los workers de SWAN en paralelo y monitorea su avance."""
    workers = sorted(cat_df["worker"].unique())
    procs = {}
    log_files = {}

    print(f"[SWAN] Lanzando {len(workers)} workers paralelos ({threads_per_worker} hilos OpenMP c/u)...")
    t_start = time.time()

    for w_name in workers:
        w_dir = TRABAJO_DIR / "workers" / w_name
        log_path = TRABAJO_DIR / "logs" / f"{w_name}.log"
        f_log = open(log_path, "w")
        log_files[w_name] = f_log

        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = str(threads_per_worker)

        proc = subprocess.Popen(
            [str(SWAN_BIN)],
            cwd=str(w_dir),
            stdout=f_log,
            stderr=subprocess.STDOUT,
            env=env,
        )
        procs[w_name] = proc

    total_cases = len(cat_df)
    try:
        while True:
            alive = [w for w, p in procs.items() if p.poll() is None]
            done_cases = 0
            for w_name, group in cat_df.groupby("worker"):
                mat_path = Path(group.iloc[0]["out_mat"])
                if mat_path.exists():
                    # Cada caso añade 3 arrays de 255521 float32 (~3.066 MB)
                    approx_cases = int(mat_path.stat().st_size // 3_060_000)
                    done_cases += min(len(group), approx_cases)

            elapsed = time.time() - t_start
            print(
                f"[{elapsed:6.1f}s] Workers activos: {len(alive)}/{len(workers)} | "
                f"Casos completados aprox: {done_cases}/{total_cases}",
                flush=True,
            )
            if not alive:
                break
            time.sleep(15)
    finally:
        for f_log in log_files.values():
            f_log.close()

    # Verificar códigos de salida y extraer archivos individuales
    for w_name, p in procs.items():
        print(f"  Worker {w_name} finalizó con código {p.returncode}")

    extracted = split_worker_mat_to_dataset(cat_df)
    print(f"[OK] Total casos extraídos en DataSet/: {extracted}/{total_cases}")


def main():
    parser = argparse.ArgumentParser(description="Ejecutor paralelo de matriz de oleaje unitario SWAN")
    parser.add_argument("--dt", type=float, default=2.0, help="Paso de periodo en segundos (default: 2.0)")
    parser.add_argument("--tmin", type=float, default=6.0, help="Periodo mínimo en segundos (default: 6.0)")
    parser.add_argument("--tmax", type=float, default=22.0, help="Periodo máximo en segundos (default: 22.0)")
    parser.add_argument("--ddir", type=float, default=5.0, help="Paso direccional en grados (default: 5.0)")
    parser.add_argument("--dmin", type=float, default=180.0, help="Dirección mínima en grados (default: 180.0)")
    parser.add_argument("--dmax", type=float, default=360.0, help="Dirección máxima en grados (default: 360.0)")
    parser.add_argument("--mxitst", type=int, default=10, help="Iteraciones estacionarias máx por paso (default: 10)")
    parser.add_argument("--threads", type=int, default=3, help="Hilos OpenMP por worker (default: 3)")
    args = parser.parse_args()

    periods = list(np.arange(args.tmin, args.tmax + 0.1, args.dt))
    directions = generate_direction_order(args.dmin, args.dmax, args.ddir)
    print(f"Periodos ({len(periods)}): {periods}")
    print(f"Direcciones ({len(directions)}): {directions}")
    print(f"Total combinaciones: {len(periods) * len(directions)}")

    cat_df = prepare_workers(periods, directions, spreading=25.0, mxitst=args.mxitst)
    run_all_workers(cat_df, threads_per_worker=args.threads)


if __name__ == "__main__":
    main()
