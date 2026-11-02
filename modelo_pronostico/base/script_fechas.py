def swan_inp(fecha_ini, fecha_end):

    # MODIFICA FECHAS: INPUT SWAN
    input_base = open('/home/doprev/1_SWAN/modelo_pronostico/base/swan_INPUT.swn', 'rt')
    data = input_base.read()
    input_base.close()
    
    data = data.replace('FILE_NAME', fecha_ini[0:8] + '_' + fecha_end[0:8])
    data = data.replace('FECHA_INI', fecha_ini)
    data = data.replace('FECHA_FIN', fecha_end)
    
    input_swan = open('/home/doprev/1_SWAN/modelo_pronostico/run/INPUT', 'wt')
    input_swan.write(data)
    input_swan.close()

    return


## def file_wnd(fecha_ini, fecha_end):
##     
##     # MODIFICA FECHAS: DESCARGA DE VIENTOS
##     wind_base = open('/home/doprev/1_SWAN/modelo_pronostico/base/descarga_wind.py', 'rt')
##     data = wind_base.read()
##     wind_base.close()
##     
##     data = data.replace('FECHA_INI', fecha_ini)
##     data = data.replace('FECHA_FIN', fecha_end)
##     
##     input_swan = open('/home/doprev/1_SWAN/modelo_pronostico/scripts/descarga_wind.py', 'wt')
##     input_swan.write(data)
##     input_swan.close()
## 
##     return
