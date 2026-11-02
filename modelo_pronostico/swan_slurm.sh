#!/bin/bash
# ----------------SLURM Parameters----------------
#SBATCH -J SWAN_INH
#SBATCH -p general
#SBATCH -n 1
#SBATCH --ntasks-per-node=1
#SBATCH -c 40
#SBATCH --mem=25000
#SBATCH --mail-user=andrestapia@inh.cl
#SBATCH --mail-type=FAIL
#SBATCH -o ./log/SWAN_RUN_%j.out
#SBATCH -e ./log/SWAN_RUN_%j.err

# Ejecutar swan.exe
module load SWAN/41.31-omp

echo "Ejecutando SWAN"
cd ./run
swan.exe
echo "done"


