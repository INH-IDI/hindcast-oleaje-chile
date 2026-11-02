import datetime
from dateutil.relativedelta import relativedelta as deltat
from netCDF4 import Dataset


def cambia_formato(file_input, file_output):

    # Lectura de variables
    # --------------------
    
    nc_file = file_input
    data    = Dataset(nc_file, mode='r')
    
    time          = data.variables['time'][:]            # Tiempo inicia 1990-01-01 00:00:00
    lat           = data.variables['latitude'][:]
    lon           = data.variables['longitude'][:]
    direction     = data.variables['direction'][:]       # Direccion
    efth          = data.variables['efth'][:]            # Espectro para cada "Time" X=frecuencia Y=direccion
    frc           = data.variables['frequency'][:]       # Frecuencia center band
    # frc1          = data.variables['frequency1'][:]    # Frecuencia lower band
    # frc2          = data.variables['frequency2'][:]    # Frecuencia upper band
    # station       = data.variables['station'][:]       # Station id
    # string16      = data.variables['string16'][:]      # Station id
    # station_name  = data.variables['station'][:]       # Station id
    # dpt           = data.variables['dpt'][:]           # Depth
    
    data.close()
    
    #print(len(time))
    #print(len(efth))
    #print(len(direction)) # eje X de eftg 24
    #print(len(frc))       # eje Y de efth 32 
    
    
    # Archivo de salida en formato SWAN
    # ---------------------------------
    file_spc  = open(file_output, 'w')
            
    file_spc.write('SWAN 1' + '\n')
    file_spc.write('TIME'   + '\n')
    file_spc.write('1'      + '\n')
    file_spc.write('LONLAT' + '\n')
    file_spc.write('1'      + '\n')
    file_spc.write('{:9.4f}'.format(lon[0][0]) + ' ' + '{:9.4f}'.format(lat[0][0]) + '\n')
    
    # frecuencias
    file_spc.write('AFREQ'       + '\n')
    file_spc.write('    ' + "{}".format(len(frc)) + '\n')
    for i in range(len(frc)):
        file_spc.write("    {:7.5f}".format(frc[i]) + '\n')
    
    # direcciones
    file_spc.write('CDIR'       + '\n')
    file_spc.write('    ' +  "{}".format(len(direction)) + '\n')
    for i in range(len(direction)):
        angle = i * ( 360 / len (direction) )
        file_spc.write("    " + str(angle) + '\n')
    #   file_spc.write("    {:6.2f}".format(direction[i]) + '\n')
    
    # otros - revisar
    file_spc.write('QUANT'      + '\n')
    file_spc.write('    1'      + '\n')
    file_spc.write('VaDens'     + '\n')
    file_spc.write('m2/Hz/degr' + '\n')
    file_spc.write('-99'        + '\n')
    
    fecha_ini  = datetime.datetime(1990, 1, 1 , 0, 0, 0) + deltat(days = time[0])
    # print(fecha_ini)
    for i in range(len(efth)):
        fecha = fecha_ini + deltat(hours = i)
        file_spc.write(fecha.strftime("%Y%m%d.%H%M%S") + '\n')    # fecha
        file_spc.write('FACTOR'                        + '\n')
        file_spc.write('0.00001747'                    + '\n')    # esto es 0.001*0.262/15 (paso de m2/hz/rad a m2/hz/degr)
        for u in range(len(frc)):
            for w in range(len(direction)):
                if w <= (len(direction) - 2):
                    file_spc.write("{:5.0f}".format(efth[i][0][u][w] * 1E3) + " ")
                else:
                    file_spc.write("{:5.0f}".format(efth[i][0][u][w] * 1E3) + "\n")
    
    file_spc.close()
    
    # Fin archivo salida
    # ------------------

    return
