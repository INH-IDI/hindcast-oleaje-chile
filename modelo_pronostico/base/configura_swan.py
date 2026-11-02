import sys
from datetime import datetime, timedelta, date
import script_downloadWind  as down_wind
import script_fechas        as mod_fecha
import script_netcdf2spc    as netCDF2spc
#sys.path.append('/home/andres/Python/')


def main():

    # Fechas a resolver
    #
    if len(sys.argv) == 2 :
        mdias     = int(sys.argv[1])

    else:
        mdias     = 7
    
    f0        = date.today()
    f1        = f0 + timedelta(days = mdias)
    fecha_ini = f0.strftime('%Y%m%d.%H%M%S')
    fecha_end = f1.strftime('%Y%m%d.%H%M%S')
    print('Fechas a resolver: ' + fecha_ini[0:8] + ' - '+ fecha_end[0:8])


    # Modificar archivo input y descarga de vientos
    #
    # aca deberia ir la extension espacial donde se descargan
    # los vientos
    mod_fecha.swan_inp(fecha_ini, fecha_end)  # Modifica 'input'
    down_wind.download(fecha_ini, fecha_end)  # Descarga viento


    # Convertir espectros desde .nc a .spc
    #
    fecha_ini = f0.strftime('%Y%m%d.%H%M%S')
    
    print('Nodos NC a utilizar:')
    nc_files = []
    for i in range(29):  # 000 - 028
        file_input = '/home/doprev/0_WW3/FORECAST/6_out_nc/C06/' + fecha_ini[0:6] + '/' + fecha_ini[0:8] + '/' + fecha_ini[0:8] + 'C06_INH_' + str(i).zfill(3) + '_glob.nc'
        nc_files.append(file_input)
        print(file_input)

    print('Guardando espectros:')
    for i in range(len(nc_files)):
        file_input = nc_files[i]
        file_output = '/home/doprev/1_SWAN/modelo_pronostico/bound/lado_' + str(i).zfill(3) + '.spc'
        print(file_output)

        netCDF2spc.cambia_formato(file_input, file_output)


main()
