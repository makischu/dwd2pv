#csv2pv: Use DWD data as csv to estimate photovoltaics power over time.
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


# DEMONSTRATION ONLY... many parameters are plant-specific!


import datetime as dt
import math 
import sunpos
import numpy as np
import csv2csv #reuse load and save functions from previous file
import matplotlib.pyplot as plt
import pandas as pd
import pytz

##plant-specific...
location = (48.69978, 10.24177) # Nattheim. change it to your location.

#wrapper for sunpos.
def calc_sunpos(ts):
    elevation = 0.0
    azimuth = 0.0
    try:
        when = (ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, ts.utcoffset().total_seconds()/3600)    #when = (2021, 7, 13, 17, 00, 0, +2)
        # sunpos implementation is available from https://levelup.gitconnected.com/python-sun-position-for-solar-energy-and-research-7a4ead801777?gi=4826148a2672
        azimuth, elevation = sunpos.sunpos(when, location, False)
    except Exception as e:
        print(e)
    return azimuth, elevation

#angle between two (az,el)-vectors
#https://stackoverflow.com/questions/18685275/angle-between-two-pairs-of-azimuth-and-altitude
#https://stackoverflow.com/questions/2827393/angles-between-two-n-dimensional-vectors-in-python
def angle_between(az1, el1, az2, el2):
    v1 = (math.cos(el1)*math.sin(az1), math.cos(el1)*math.cos(az1),math.sin(el1))
    v2 = (math.cos(el2)*math.sin(az2), math.cos(el2)*math.cos(az2),math.sin(el2))
    v1_u = v1 / np.linalg.norm(v1)
    v2_u = v2 / np.linalg.norm(v2)
    return np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))

#wir denken in grad, die python-funktionen rechnen in rad.
def sin_d(angle):
    return math.sin(math.radians(angle))
def cos_d(angle):
    return math.cos(math.radians(angle))
def angle_between_d(az1, el1, az2, el2):
    return round(math.degrees(angle_between(math.radians(az1),math.radians(el1),math.radians(az2),math.radians(el2))),2)

# Schaetze den Anteil der diffusen Strahlung an der Gesamtstrahlung
# Nimm als Basis "Effective cloud cover" in Prozent von 0 bis 100.
# 100% Wolken => 100% diffus => Anteil Diffus/Normal 1/0
#   0% Wolken => 0%   diffus => Anteil Diffus/Normal 0/1
def diffuse_normal_ratio(dwd_Neff):
    diffus = 0.5
    try:
        if dwd_Neff >= 0 and dwd_Neff <= 100:
            diffus = dwd_Neff / 100.0
    except Exception as e:
        print(e)
    normal = 1-diffus
    return diffus, normal


# abschaetzung fuer einen reduktionsfaktor der globalstrahlung 
# wegen ausrichtung+neigung der pv-anlage 
def calc_tiltfactor(timestamp, Neff,plant_azimut,plant_elevat):
    tcf = tcf_diff = tcf_norm = 1.0
    try:
        az, el = calc_sunpos(timestamp)
        r_diff, r_norm  = diffuse_normal_ratio(Neff)
        tcf_norm = 0
        if el > 0.5:
            fsun = 1/sin_d(el)
            beta = angle_between_d(az, el, plant_azimut, 90-plant_elevat)
            if beta < 90:
                tcf_norm = cos_d(beta)*fsun
                
                
            ##plant-specific...
            #abschattung... das stimmt natuerlich nur fuer genau meine anlage(n)
            if az > 225 and el < 17:
                tcf_norm = 0
            ##...plant-specific
                
        tcf = r_diff * tcf_diff + r_norm * tcf_norm
    except Exception as e:
        print(e)
    return tcf


# Calculate irradiance-power relative to the photovoltaic plant instaed of flat earth.
def calc_pv_E(timestamp, Rad1h, Neff,plant_azimut,plant_elevat):
    # Einheit von Global Irradiance Rad1h ist kJ/m2, d.h. Energie pro Fläche, in Zeitraum 1h bzw. normiert auf 1h.
    rad_W   = Rad1h / 3.6                   #Ziel soll sein Watt, d.h. die kJ/m2/h sollen in W=J/s umgerechnet werden.
    tiltf   = calc_tiltfactor(timestamp, Neff,plant_azimut,plant_elevat)
    E_Wm2   = rad_W * tiltf 
    E_Wm2 = round(E_Wm2,2)
    return E_Wm2

# Estimate the temperature of the pv module.
def calc_pv_T(E, T_ambient):
    #Sehr einfaches modell... ohne wind, ohne alles
    #Stefan-Boltzmann-Gesetz https://de.wikipedia.org/wiki/W%C3%A4rmestrahlung
    eps = 0.85
    bol = 5.67e-8
    A   = 1.0
    T4  = E/(eps*bol*A)
    Tb  = np.power(T4, 1/4)
    T = max(T_ambient, Tb)
    return T


# Umrechnung der dwd-progrose in ac-leistung unserer pv
def calc_pvpower(timestamp, Rad1h, Neff, TTT):
    
    ##plant-specific...
    plant_name = 'West'
    plant_azimut = 270              # 270° = West
    plant_elevat = 20               # Dachneigung in Grad
    ##...plant-specific
    
    E = calc_pv_E(timestamp, Rad1h, Neff,plant_azimut,plant_elevat)
    T = calc_pv_T(E,TTT)
    
    ##plant-specific...
    temp_factor   = 1+(T-(273.15+25))*(-0.00375) # Datenblatt sagt "Temperaturkoeffizient von Pmax = -0.375 %/°C" ... nimm an das ist für den wirkungsgrad dann auch nicht sooo falsch.
    plant_area    = 28*1.65*0.99    #in m2
    plant_eff    = 0.189 * 0.976    #optimistisch, nach datenblaetter
    pwr = E * plant_area * plant_eff * temp_factor
    pwr = min(pwr, 7000)            # Wechselrichter-limit in Watt
    ##...plant-specific
    
    pwr = round(pwr)
    return plant_name, pwr, E, T


#implemented for 1 specific plant only
def add_pv_power(data):
    for line in data:
        name, P, E, T = calc_pvpower(line['t'], line['Rad1h'], line['Neff'], line['TTT'])
        line['pv'+name+'E'] = E
        line['pv'+name+'P'] = P
        line['pv'+name+'T'] = T
    return data


#use latest csv2csv-output and translate the data to photovoltaic power. maybe not a generic solution for everybody.
def evaluate_my_latest_csv():
    datecolumns =['t', 'tLocal']
    floatcolumns=['Rad1h','Neff','N','DD','FF','PPPP','TTT']
    datenow = dt.datetime.now() #- dt.timedelta(days=7)
    todaystr  = datenow.strftime('%Y-%m-%d')
    data = csv2csv.parse(csv2csv.split(csv2csv.load('./data/mosmix_refined_'+todaystr+'.csv')), floatcolumns, datecolumns)
    data = add_pv_power(data)
    csv2csv.save('./data/mosmix_pvest_'+todaystr+'.csv', data)



#reload what we have saved in plot some illustrative results - for demonstration only.
def plot_my_latest_csv():
    datecolumns =['t', 'tLocal']
    floatcolumns=['Rad1h','Neff','N','DD','FF','PPPP','TTT','pvWestP','pvWestE','pvWestT']
    date0 = dt.datetime.now() #- dt.timedelta(days=2)
    datestr = date0.strftime('%Y-%m-%d')
    data = csv2csv.parse(csv2csv.split(csv2csv.load('./data/mosmix_pvest_'+datestr+'.csv')), floatcolumns, datecolumns)
    
    tu = [ line['t'] for line in data]
    tl = [ line['tLocal'] for line in data]
    rad = [ line['Rad1h']/3.6 for line in data]
    ttt = [ line['TTT']-273.15 for line in data]
    e = [ line['pvWestE'] for line in data]
    p = [ line['pvWestP'] for line in data]
    temppv = [ line['pvWestT']-273.15 for line in data]
    tumin = tu[0]
    tumax = tu[-1]
    tlmin = tl[0]
    tlmax = tl[-1]
    
    plt.close('all')
    f, axs = plt.subplots(3,1)
    axs[0].plot(tu,rad,'-k',label='flat earth')
    axs[0].plot(tu,e,'-r',label='in my pv plane')
    axs[0].legend()
    axs[0].set_xlabel("t [UTC]")
    axs[0].set_ylabel("E radiation [W/m²]")
    axs[0].grid()
    axs[0].set_xlim((tumin,tumax))
    axs[1].plot(tl,p,'-r',label='estimation in advance')
    axs[1].legend()
    axs[1].set_xlabel("t [local=MESZ]")
    axs[1].set_ylabel("PV AC Power [W]")
    axs[1].grid()
    axs[1].set_xlim((tlmin,tlmax))
    axs[2].plot(tu,ttt,'-k',label='TTT = ambient')
    axs[2].plot(tu,temppv,'-b',label='estimation for pv panel')
    axs[2].legend()
    axs[2].set_xlabel("t [UTC]")
    axs[2].set_ylabel("Temperature [°C]")
    axs[2].grid()
    axs[2].set_xlim((tumin,tumax))
    plt.show()
    





if __name__ == "__main__":
    # example usage (executed when called directly - what I will do from a cron job)
    evaluate_my_latest_csv()
    plot_my_latest_csv()
    
