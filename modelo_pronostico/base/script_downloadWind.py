import numpy as np
import pandas as pd
import os,sys,shutil
from datetime import datetime, timedelta, date
from urllib.request import urlretrieve
from scipy.interpolate import griddata


def download(fecha_ini, fecha_end):

    urlbase       = 'https://coastwatch.pfeg.noaa.gov/erddap/griddap/'
    dataset_id    = 'NCEP_Global_Best'
    variable1     = 'ugrd10m'
    variable2     = ',vgrd10m'
    extencion     = '.csv?'
    
    
    date_ini    = datetime.strptime(fecha_ini, '%Y%m%d.%H%M%S').isoformat()
    date_end    = datetime.strptime(fecha_end, '%Y%m%d.%H%M%S').isoformat()
    date_paso   = '1'
    latituds    = [-49.5,-10.5]
    longituds   = [-84.0,-67.5]
   

    latitude_ini  = '-50.0'
    latitude_end  = '-10.0'
    longitude_ini = str(360-84)
    longitude_end = str(360-67)
    lati_paso     = '1'
    longi_paso    = '1'
    
    time          = '[(' + date_ini       + ')'  + ':' + date_paso   +  ':'  + '(' + date_end      + ')]'
    latitude      = '[(' + latitude_ini   + ')'  + ':' + lati_paso   +  ':'  + '(' + latitude_end  + ')]'
    longitude     = '[(' + longitude_ini  + ')'  + ':' + longi_paso  +  ':'  + '(' + longitude_end + ')]'
    
    url  = urlbase+dataset_id+extencion+variable1+time+latitude+longitude+variable2+time+latitude+longitude
    print(url)
    urlretrieve(url, '/home/doprev/1_SWAN/modelo_pronostico/bound/wind/vientos_ERDDAP.csv')
        
    # %% SE DEFINEN ALGUNAS VARIABLES
    
    #CARGA LOS VIENTOS
    data     = pd.read_csv('/home/doprev/1_SWAN/modelo_pronostico/bound/wind/vientos_ERDDAP.csv', skiprows = 2, names = ['Time','Lat','Lon','U','V'] ) 
    data.Lon   = -360 + data.Lon 
    
    #CARGA LAS COORDENADAS DE LOS NODOS DE LA MALLA NOESTRUCTURADA EN GRADOS
    #C_malla  = np.loadtxt('./final/nodes.txt') # 
    deltaxey=0.5
    y_dist = np.abs(data.Lat.max() - data.Lat.min())
    x_dist = np.abs(data.Lon.max() - data.Lon.min())
    
    nx, ny = (int(x_dist/deltaxey), int(y_dist/deltaxey))
    xx = np.linspace(data.Lon.min(), data.Lon.max(), nx+1)
    yy = np.linspace(data.Lat.min(), data.Lat.max(), ny+1)
    xv, yv = np.meshgrid(xx, yy)
    
    
    #GENERA EL VECTOR TIEMPO EN FORMATO SWAN
    fecha_ini = date_ini[0:13]
    fecha_end = date_end[0:13]
    
    data1    = pd.date_range(start=fecha_ini, end=fecha_end,freq='3 H')
    df       = pd.DataFrame(data1,columns=['Time'], dtype=str)
    df.Time     = df['Time'].str.replace(".000000000", "")
    df.Time     = df['Time'].str.replace("T", ".")
    df.Time     = df['Time'].str.replace(":", "")
    df.Time     = df['Time'].str.replace("-", "")
    df.Time     = df['Time'].str.replace("Z", "")
    ttiempo  = df
    
    #LONGITUD DEL VECTOR TIEMPO
    Ntim     = len(ttiempo)
    
    #CONVERTIR TIEMPO A STR PARA ESCRIBIR
    timp = np.array(ttiempo.Time, dtype=str)
    
    #NOMBRE DEL ARCHIVO DE ESCRITURA
    ff   = open('/home/doprev/1_SWAN/modelo_pronostico/bound/vientos.bot','w+')
    #VECTOR DE VIENTO
    vec  = ['WIND_X\n','WIND_Y\n']
    
    #VARIABLE PIVOTE
    v    = 0
    
    #ESCRITURA DEL ARCHIVO 
    for cara in np.arange(Ntim): # Loop en cada tiempo
        #XI      = co_malla[['Lon','Lat']]
        point   = np.array(data[['Lon','Lat']][data.Time==data.Time.unique()[cara]],dtype=float)
        W_x = griddata(point, data.U[data.Time==data.Time.unique()[cara]], (xv,yv), method='linear')
        W_y = griddata(point, data.V[data.Time==data.Time.unique()[cara]], (xv,yv), method='linear')
        arbolx = pd.DataFrame(W_x)
        arboly = pd.DataFrame(W_y)
        arbolx2 = pd.DataFrame(xv)
        arboly2 = pd.DataFrame(yv)
        ff.write(timp[cara]+'\n')
        ff.write(vec[v])
        ff.write(arbolx.to_string(header=False,index=False, justify='right',float_format='%.3f'))
        ff.write('\n')
        ff.write(vec[v+1])
        ff.write(arboly.to_string(header=False,index=False, justify='right',float_format='%.3f'))
        ff.write('\n')
    ff.close()
    str2= "INPGRID WIND REG"
    
    str3=  str(data.Lon.min()) +' '+ str(data.Lat.min())+' 0.0 ' + str(nx) + \
    ' '+  str(ny) + ' ' + str(deltaxey) + ' ' + str(deltaxey)+ ' '
    
    str4= "NONSTATionary "+ timp[0] +" 3.0 HR "+ timp[Ntim-1] 
    str5 = str2 + ' ' + str3 + ' '+ str4
    
    ff   = open('/home/doprev/1_SWAN/modelo_pronostico/log/log.descarga_wind_ERDAP','w+')
    ff.write(str5)
    #print (str2,str3,str4)
    ff.close()

    return
