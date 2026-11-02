#!/bin/bash
module load Python/3.7.2
module load netCDF/4.7.3-hdf1.10.4

# Configurar swan (vientos y olas)
python3 ./base/configura_swan.py

# Correr swan
sbatch ./swan_slurm.sh



