#!/bin/bash
# ----------------SLURM Parameters----------------
#SBATCH -J SWAN_CFG
#SBATCH -p general
#SBATCH -n 1
#SBATCH --ntasks-per-node=1
#SBATCH -c 1
#SBATCH --mem=500
#SBATCH --mail-user=andrestapia@inh.cl
#SBATCH --mail-type=FAIL
#SBATCH -o ./log/SWAN_CFG_%j.out
#SBATCH -e ./log/SWAN_CFG_%j.err


ml Python/3.7.2
ml netCDF/4.7.3-hdf1.10.4

# Configurar swan (vientos y olas)
python3 ./base/configura_swan.py &> log/log.configura_swan

