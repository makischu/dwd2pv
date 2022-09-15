#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#stationlist2csv.py script to convert dwd's station-list to umap.openstreetmap.fr-format.
# and prepare filtering out stations that do not offer irradiation data.

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

#source:
#https://www.dwd.de/EN/ourservices/met_application_mosmix/mosmix_stations.html
#https://www.dwd.de/DE/leistungen/met_verfahren_mosmix/faq/einheit_laenge_breite.html
#Für die Stationsliste im cfg-Format gilt: Die Angabe der Längen- und Breitengrade erfolgt in Grad und Minuten. (52.23 bedeutet 53°23‘).
#destination 1: visualization
#https://umap.openstreetmap.fr/de/map/dwd-stations_802117
#Komma-, tabulator-, oder semikolongetrennte Werte. SRS WGS84 ist impliziert. Nur Punktgeometrien werden importiert. Beim Import wird nach Spaltenüberschriften mit jeder Nennung von „lat“ und „lon“ am Anfang der Überschrift gesucht (ohne Beachtung von Groß-/Kleinschreibung). Alle anderen Spalten werden als Merkmale importiert.
#destination 2: counting (binning to country/continent)
#conda install -c conda-forge geopy
#conda install -c konstantinstadler country_converter
from geopy.geocoders import Nominatim
import country_converter as coco
import time
geolocator = Nominatim(user_agent="stationlist2csv.py")
cc = coco.CountryConverter()

#for Filtering (Find out which station offers Rad1h-values (and which not))
import dwd2csv
import csv
import pandas as pd

#not all stations provide all data.
#generate a list of stations, aggregated with the information wether it offers certain data, e.g. Rad1h
def mosmix_stationoffers(elements=['Rad1h'], csv_filename = None):
    stations = {}
    
    #we use a local cache... (the date doesn't matter). preparation:
    #download and extract from https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_S/all_stations/kml/
    a_local_allstations_kml_filename = './data/MOSMIX_S_2022090109_240.kml'
    
    with open(a_local_allstations_kml_filename, 'r', errors='ignore') as file:
        mosmix_s_kml_content = file.read()
    timestamps, stationValues = dwd2csv.parseKML(mosmix_s_kml_content, ['Rad1h'])

    for (stationName,stationData) in stationValues.items():
        stationDict = {}
        for el in elements:
            if el in stationData.keys():
                elementValues = stationData[el]
                dataExistsOnce = False
                dataExistsAll  = True
                for val in elementValues:
                    if val != '-':
                        dataExistsOnce = True
                    else:
                        dataExistsAll = False
                stationDict[el] = (dataExistsOnce,dataExistsAll)
        stations[stationName] = stationDict
        
    if csv_filename:
        with open(csv_filename, 'w') as file:
            mywriter = csv.writer(file, delimiter=';')
            header = ['stationid'] + elements
            mywriter.writerow(header)
            for statName, statElements in stations.items():
                mywriter.writerow([statName] + [1 if exO else 0 for (exO,exA) in statElements.values()])
        
    return stations     

#dwd's station.cfg-file is not directly importable to umap.openstreetmap.fr
#convert it that it is. and aggregate additional information.
def station_cfg_to_umap_csv(filename_i = './mosmix_stations.cfg', filename_o = './mosmix_stations.csv', stationOffers=None):
    #filename_i shall point to a local copy of the file downloaded from
    #https://www.dwd.de/EN/ourservices/met_application_mosmix/mosmix_stations.html 
    
    filecontent = None
    with open(filename_i, 'r', errors='ignore') as file:
        filecontent = file.read()
    fileo = open(filename_o, 'w')
    fileo.write('lat;lon;id;name;cc;country;continent;offersRad1h\n')
        
    lines = filecontent.splitlines()
    for l in lines:
        ids = l[12:18].strip()
        nam = l[23:43].strip()
        lat = l[44:51]
        lon = l[51:59]
        
        try:
            latf = float(lat)
            lonf = float(lon)
        except:
            latf = lonf = None
            continue
        
        if latf and lonf:
            lats = lat.strip().split('.')
            lats = lats[0]+'°'+lats[1]+'\''
            lons = lon.strip().split('.')
            lons = lons[0]+'°'+lons[1]+'\''
            #e.g. 44°27', 12°18' results in 'nominatim.openstreetmap.org:443/reverse?lat=44.45&lon=12.3&format=json&addressdetails=1
            
            coordinates = lats + ', ' + lons #"48.69978, 10.24177"
            print(coordinates)
            location = None
            for i in range(0,10):
                try:
                    location = geolocator.reverse(coordinates)
                except: #timeout ReadTimeoutError MaxRetryError ConnectionError GeocoderUnavailable
                    print('geolocator failed.')
                    time.sleep(5)
                else:
                    break
            if location:
                address = location.raw['address']
                country = address.get('country', '')
                country_code = address.get('country_code', '')
                print(country_code)
                
                continent = cc.convert(country_code.upper(),to='continent')
                print(continent)
            else:
                country='-'
                country_code='-'
                continent='-'
            
            offersRad1h = '-'
            if stationOffers and ids in stationOffers.keys() and 'Rad1h' in stationOffers[ids].keys():
                (exO,exA) = stationOffers[ids]['Rad1h']
                offersRad1h = '1' if exO else '0' 
            print(offersRad1h)
            fileo.write(lats+';'+lons+';'+ids+';'+nam+';'+country_code+';'+country+';'+continent+';'+offersRad1h+'\n')
            
    fileo.close()


#filter the stations. for example assume that we only want to keep european stations that offer radiation data.
def filter_stations( filename_i = './mosmix_stations_all.csv',  filename_o = './mosmix_stations_filtered.csv'):
    alls = pd.read_csv(filename_i, sep=';', dtype=str)
    myst  = alls[(alls['offersRad1h'] == '1')&(alls['continent'] == 'Europe')]
    myst.to_csv(filename_o, sep=';', index=False) #encoding='latin1', errors='replace', 
    
    #some statistics
    print('#rows with any coordinates: \t' + str(len(alls)))
    offersrads = alls[(alls['offersRad1h'] == '1')]
    withcontinent = alls[(alls['continent'] != 'not found')&(alls['continent'] != '-')]
    print('#rows with valid continent: \t' + str(len(withcontinent)))
    ineurope = alls[(alls['continent'] == 'Europe')]
    print('#rows with continent Europe: \t' + str(len(ineurope)))
    ingermany = alls[(alls['cc'] == 'de')]
    print('#rows with country Germany: \t' + str(len(ingermany)))
    ingermanyrad = ingermany[(ingermany['offersRad1h'] == '1')]
    print('#rows that offer Rad1h in Germany: \t' + str(len(ingermanyrad)))
    print('#rows that offer Rad1h worldwide: \t' + str(len(offersrads)))
    
    
   

if __name__ == "__main__":
    stations = mosmix_stationoffers(elements=['Rad1h'], csv_filename='./data/stationoffers.csv')
    # #file output: 
    # #stationid;Rad1h
    # #01028;0
    # #[...]
    # #04097;1
    # #[...]
    # (the following takes ~1hour because the geo-lookup is done online for thousends of entries)
    station_cfg_to_umap_csv(stationOffers = stations, filename_i = './data/mosmix_stations.cfg', filename_o = './data/mosmix_stations_all.csv')
    
    filter_stations(filename_i = './data/mosmix_stations_all.csv', filename_o = './data/mosmix_stations_filtered.csv')
