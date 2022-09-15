#csv2csv: Interpolate hourly DWD data to finer time grid, especially Rad1h.
#And merge station data, because not every station offers every information.
#Copyright (C) 2022 makischu

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import dateutil.parser as dp
import dateutil.tz as tz
import datetime as dt
import csv
import io
import matplotlib.pyplot as plt
import numpy as np


#file2ram
def load(dwd_csv_filename):
    filecontent = None
    with open(dwd_csv_filename, 'r', errors='ignore') as file:
        filecontent = file.read()
    return filecontent

#csv string >>> list of dicts
def split(dwd_csvfile_content):
    reader = csv.DictReader(io.StringIO(dwd_csvfile_content),delimiter=';')
    csv_data = list(reader)
    return csv_data

# parse strings inside list of dicts
def parse(csv_data, floatColumns=[], dateColumns=['t']):
    for linedict in csv_data:
        for el in dateColumns:
            linedict[el] = dp.parse(linedict[el])
        for el in floatColumns:
            try:
                linedict[el] = float(linedict[el])
            except:
                continue
    return csv_data

# merge float values of two stations
# nachdem ich ziemlich genau zwischen zwei stationen wohne, die Rad1h-Daten haben,
# nehm ich den den mittelwert der beiden stationen zum weiterrechnen
def merge(csv_data, csv_data2, floatColumns=[]):
    if len(csv_data)!=len(csv_data2):
        return None
    for i in range(0,len(csv_data)):
        t1 = csv_data[i]['t']
        t2 = csv_data2[i]['t']
        if t1!=t2:
            return None
        for el in floatColumns:
            csv_data[i][el] = (csv_data[i][el] + csv_data2[i][el])*0.5
    return csv_data

#overwrite a column by values from another station
# weil in der mir am naechsten station Rad1h-Werte nicht geliefert werden.
def overwrite(csv_data, csv_data_alternative_source, overwriteColumns=['Rad1h']):
    if len(csv_data)!=len(csv_data_alternative_source):
        return None
    for i in range(0,len(csv_data)):
        t1 = csv_data[i]['t']
        t2 = csv_data_alternative_source[i]['t']
        if t1!=t2:
            return None
        for el in overwriteColumns:
            csv_data[i][el] = csv_data_alternative_source[i][el]
    return csv_data

#add a local date column next to 't'
def addlocaldate(csv_data):
    for i in range(0,len(csv_data)):
        row = {}
        for (key,val) in csv_data[i].items():
            if key == 't':
                row['t'] = val
                row['tLocal'] = val.astimezone(tz.tzlocal())
            else:
                row[key] = val
        csv_data[i] = row
    return csv_data

#ignore data outside wanted date range
def limit(csv_data, date_start, date_end=None):
    if date_end is None:
        date_end = date_start + dt.timedelta(days=1)
    filtered_data = [line for line in csv_data if line['t']>=date_start and line['t']<=date_end ]
    return filtered_data

def myformat(key,val):
    if key == 't':
        return val.strftime('%Y-%m-%dT%H:%M:%S.000Z') 
    elif key == 'tLocal':
        return val.isoformat()
    elif isinstance(val,float):
        return round(val,2)
    else:
        return val

#ram2file
def save(csv_filename, data):
    try: 
        content = None
        with io.StringIO() as file:
            mywriter = csv.writer(file, delimiter=';')
            mywriter.writerow(data[0].keys())
            for i in range(0,len(data)):
                mywriter.writerow([myformat(key,val) for (key,val) in data[i].items()])
            content = file.getvalue()
        if csv_filename:
            with open(csv_filename, 'w') as file:
                file.write(content)
    except Exception as e:
        print(e)    
    return 

       
#estimate intermediate values
#Rad1h: by assuming a continous curve instead of 1 hour steps - without changing the integral
#cont: by linear interpolation of floats
#degr: linear, but shortest way modulo 360
#else: '-', no interpolation at all.
def interpolate(data, resolution_in_minutes=5, continuous_columns=['Neff','N','FF','PPPP','TTT','Td'], degree_columns=['DD']):
    #sanity check. we require values in 1h grid.
    for i in range(1,len(data)):
        if (data[i]['t']-data[i-1]['t']).total_seconds() != 3600:
            raise Exception("interpolRad1h requires 1h grid")
    if 30 % resolution_in_minutes != 0:
        raise Exception("interpolRad1h requires that multiple of resolution_in_minutes result in 1/2hour")
    
    #initialize two lines per point in time - 1/2h before and 1/2h after it.
    lines = [ {'left': {'a':0, 'b':data[i]['Rad1h']}, 'right': {'a':0, 'b': (0 if i+1==len(data) else data[i+1]['Rad1h'])}}  for i in range(0,len(data))]
    
    #find connected data ranges not equal zero
    i_start = None
    i_end   = None
    connected_ranges = []
    for i in range(1,len(data)-1):
        if i_start == None:
            if data[i-1]['Rad1h'] == 0 and data[i]['Rad1h'] != 0:
                i_start = i-1 #muss mit 0 anfangen
        elif i_end == None:
            if data[i]['Rad1h'] != 0 and data[i+1]['Rad1h'] == 0:
                i_end = i+1   #muss mit 0 aufhoeren (der letzte eintrag gehoert also nicht mehr richtig dazu.)
        if i_start and i_end:
            connected_ranges.append((i_start,i_end));
            i_start = None
            i_end = None
    
    #determine continous linear fit
    for myrange in connected_ranges:
        i0, iN1 = myrange
        #iN = iN1-1
        iLen = iN1-i0
        d = 2*(iLen-1)
        A = np.zeros((d,d))
        b = np.zeros((d,1))
        A[0:2,0:3]  = np.array([[ 1/4,    -1/4,   1],[ 1/2,     1/2,   -1]])
        A[-2:,-3:]  = np.array([[ 1/4, 1, -1/4     ],[ 1/2,  1, 1/2      ]])
        for j in range(1,iLen-2):
            A[j*2:j*2+2,2*j-1:2*j+3] = np.array([[ 1/4, 1, -1/4,   1],[ 1/2,  1, 1/2,   -1]])
        for j in range(0,iLen-1):
            b[j*2] = 2*data[i0+j+1]['Rad1h']
        x = np.linalg.solve(A, b)
        rangelines = [ {} for i in range(0,iLen)]
        rangelines[0]     = { 'a' : x[0],  'b' : 0}
        rangelines[-1]    = { 'a' : x[-1], 'b' : 0}
        for j in range(1,iLen-1):
            rangelines[j] = { 'a' : x[2*j-1],  'b' : x[2*j]}
           
        
        #choose between fit and original
        for j in range(1, iLen):
            dRLeft  = data[i0+j]['Rad1h'] - data[i0+j-1]['Rad1h'];
            dRRight = data[i0+j+1]['Rad1h'] - data[i0+j]['Rad1h'];
            laLeft = rangelines[j-1]['a']
            laRight = rangelines[j]['a']
            if dRLeft*laLeft >= 0 and dRRight*laRight >= 0: #vorzeichen der steigung ok, links wie rechtsseitig.
                lines[i0+j-1]['right'] = rangelines[j-1]
                lines[i0+j  ]['left']  = rangelines[j]
    
    #interpolate Rad1h
    t0 = data[0]['t']
    n_per_hour = int((60/resolution_in_minutes))
    n_halfhour = int(      n_per_hour / 2)
    t_interp = [None]*(n_per_hour*len(data))
    R_interp = [None]*(n_per_hour*len(data))
    dx = resolution_in_minutes/60
    for i in range(0,len(t_interp)):
        t_interp[i] = t0 + dt.timedelta(minutes = (i+1)*resolution_in_minutes)
    for i in range(0,len(lines)-1):
        lineA = lines[i]['right']
        lineB = lines[i+1]['left']
        for j in range(0,n_halfhour):
            x = 0+(j+1)*dx
            R_interp[i*n_per_hour+j] = float(lineA['a']*x + lineA['b'])
            x = -0.5+(j+1)*dx
            R_interp[i*n_per_hour+j+n_halfhour] = float( lineB['a']*x + lineB['b'])

    #interpolate other columns - much easier.
    interpData = []
    for i in range(0,len(data)-1):
        for j in range(0,n_per_hour):
            row = { }
            for key in data[i].keys():
                if key == 't':
                    row[key] = t_interp[i*n_per_hour+j]
                elif key == 'Rad1h':
                    row[key] = R_interp[i*n_per_hour+j]
                elif key in continuous_columns:
                    if isinstance(data[i][key],float) and isinstance(data[i+1][key],float):
                        f = (j+1)/n_per_hour
                        row[key] = data[i][key]*(1-f) + data[i+1][key]*(f)
                    elif (j+1)==n_per_hour:
                        row[key] = data[i+1][key]
                    else:
                        row[key] = '-'
                elif key in degree_columns:
                    if isinstance(data[i][key],float) and isinstance(data[i+1][key],float):
                        delta = data[i+1][key] - data[i][key]
                        if delta > 180:
                            delta -= 360
                        if delta < -180:
                            delta += 360
                        f = (j+1)/n_per_hour
                        row[key] = data[i][key]+ delta*(f)
                    elif (j+1)==n_per_hour:
                        row[key] = data[i+1][key]
                    else:
                        row[key] = '-'
                else:
                    if (j+1)==n_per_hour:
                        row[key] = data[i+1][key]
                    else:
                        row[key] = '-'
            interpData.append(row)
    
    return interpData
    
        
#combine everything in the way it makes sense for ME. not a general solution.
def refine_my_latest_csv():
    floatcolumns=['Rad1h','Neff','N','DD','FF','FX1','PPPP','DRR1','RR1c','RRad1','SunD1','SunD','TTT','Td','ww','WPc11']
    datenow = dt.datetime.now() #- dt.timedelta(days=7)
    datestart = dt.datetime(datenow.year, datenow.month, datenow.day, tzinfo=dt.timezone.utc)
    dateend   = datestart + dt.timedelta(days=3)
    todaystr  = datenow.strftime('%Y-%m-%d')
    data10836 = parse(split(load('./data/mosmix_10836_'+todaystr+'.csv')), ['Rad1h'])
    data10850 = parse(split(load('./data/mosmix_10850_'+todaystr+'.csv')), ['Rad1h'])
    dataRad1h = merge(data10836,data10850, ['Rad1h'])
    dataQ491 = parse(split(load('./data/mosmix_Q491_'+todaystr+'.csv')), floatcolumns)
    dataCombined = overwrite(dataQ491, dataRad1h, ['Rad1h'])
    dataCombined = limit(dataCombined, datestart, dateend)
    dataInterpol = interpolate(dataCombined)
    dataInterpol = addlocaldate(dataInterpol)
    save('./data/mosmix_refined_'+todaystr+'.csv', dataInterpol)


#reload what we have saved in plot some illustrative results - for demonstration only.
def plot_my_latest_csv():
    floatcolumns=['Rad1h','Neff','N','DD','FF','FX1','PPPP','DRR1','RR1c','RRad1','SunD1','SunD','TTT','Td','ww','WPc11']
    datenow = dt.datetime.now()
    datenow = dt.datetime(2022,8,25)
    todaystr  = datenow.strftime('%Y-%m-%d')
    data10836 = parse(split(load('./data/mosmix_10836_'+todaystr+'.csv')), ['Rad1h'])
    data10850 = parse(split(load('./data/mosmix_10850_'+todaystr+'.csv')), ['Rad1h'])
    dataQ491 = parse(split(load('./data/mosmix_Q491_'+todaystr+'.csv')), floatcolumns)
    dataInterp = parse(split(load('./data/mosmix_refined_'+todaystr+'.csv')), floatcolumns)
                
    plt.close('all')
    f, axs = plt.subplots(3,1)
    
    t =  [ line['t'] for line in data10836]
    r =  [ line['Rad1h'] for line in data10836]
    tm1 = [ e - dt.timedelta(hours=1) for e in t]
    t1 = [j for i in zip(tm1,t) for j in i]
    r1 = [j for i in zip(r,r) for j in i]
    axs[0].plot(t1,r1,'b-',label='Rad1h | 10836')
    axs[0].plot(t,r,'bx',label='Rad1h | 10836')
    
    t =  [ line['t'] for line in data10850]
    r =  [ line['Rad1h'] for line in data10850]
    tm1 = [ e - dt.timedelta(hours=1) for e in t]
    t1 = [j for i in zip(tm1,t) for j in i]
    r1 = [j for i in zip(r,r) for j in i]
    axs[0].plot(t1,r1,'k-',label='Rad1h | 10850')
    axs[0].plot(t,r,'kx',label='Rad1h | 10850')
    
    t =  [ line['t'] for line in dataInterp]
    r =  [ line['Rad1h'] for line in dataInterp]
    axs[0].plot(t,r,'r-',label='Rad1h interp',linewidth=3)
    axs[0].fill_between(t,[0 for i in r],r, facecolor='red', alpha=0.5)
    
    tmin = t[0]
    tmax = t[-1]
    axs[0].set_xlim((tmin,tmax))
    axs[0].set_xlabel('t [UTC]')
    axs[0].set_ylabel('Global Irradiance [kJ/m²[/h]]')
    axs[0].legend()
    axs[0].grid()
    
        
    t =  [ line['t'] for line in dataInterp]
    N =  [ line['N'] for line in dataInterp]
    Neff =  [ line['Neff'] for line in dataInterp]
    axs[1].plot(t, N, 'k-', label='N=total | Q491')
    axs[1].plot(t, Neff, 'b-', label='Neff=effective | Q491')
    axs[1].legend(loc='lower right')
    axs[1].set_xlabel("t [UTC]")
    axs[1].set_ylabel("cloud cover [%]")
    axs[1].grid()
    axs[1].set_xlim((tmin,tmax))
    axs[1].set_ylim((0,100))
    t =  [ line['t'] for line in dataQ491]
    c =  [ line['TTT']-273.15 for line in dataQ491]
    axs[2].plot(t, c, 'k-', label='TTT=2m above surface | Q491')
    axs[2].legend()
    axs[2].set_xlabel("t [UTC]")
    axs[2].set_ylabel("Temperature [°C]")
    axs[2].grid()
    axs[2].set_xlim((tmin,tmax))
    
    plt.show()

    
                             
    

if __name__ == "__main__":
    # example usage (executed when called directly - what I will do from a cron job)
    refine_my_latest_csv()
    plot_my_latest_csv()
    
