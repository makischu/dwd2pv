#dwd2csv: Extract open data from DWD to a CSV file.
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


import xml.etree.ElementTree as ET
import csv
from zipfile import ZipFile
import requests
import io
import os
from datetime import datetime


# extract certain values from KML file
#nimm inhalt einer xml-datei aus MOSMIX_L/single_stations und extrahiere daraus die gesuchten eintraege. 
#ist in der implementierung nur fuer die single_stations-Variante gemacht - fuer all_stations geht es zwar prinzipiell auch aber duerfte ganz schoen auf den speicherverbrauch gehen.
#<kml:kml xmlns:dwd="https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:xal="urn:oasis:names:tc:ciq:xsdschema:xAL:2.0" xmlns:kml="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom">
#    <kml:Document>
#        <kml:ExtendedData>
#            <dwd:ProductDefinition>
#                <dwd:ForecastTimeSteps>
#                    <dwd:TimeStep>2021-07-11T16:00:00.000Z</dwd:TimeStep> ...
#        <kml:Placemark>
#            <kml:name>10836</kml:name>
#            <kml:description>STOETTEN</kml:description>
#            <kml:ExtendedData>
#               <dwd:Forecast dwd:elementName="Rad1h"> <dwd:value>   1840.00    1270.00  ...
def parseKML(kml_content, elements):
    timestamps = []
    stationValues = {}
    try:
        # the following definition of ns is taken from https://github.com/kilianknoll/DWDForecast/blob/master/dwdforecast.py
        ns  = {'dwd': 'https://opendata.dwd.de/weather/lib/pointforecast_dwd_extension_V1_0.xsd', 'gx': 'http://www.google.com/kml/ext/2.2',
                'kml': 'http://www.opengis.net/kml/2.2', 'atom': 'http://www.w3.org/2005/Atom', 'xal':'urn:oasis:names:tc:ciq:xsdschema:xAL:2.0'}
        xmlroot = ET.fromstring(kml_content)

        xtimestamps = xmlroot.findall('kml:Document/kml:ExtendedData/dwd:ProductDefinition/dwd:ForecastTimeSteps/dwd:TimeStep',ns)
        timestamps  = [ ts.text  for ts in xtimestamps ]   
                
        xstations   = xmlroot.findall('kml:Document/kml:Placemark',ns)
        for xstation in xstations:
            xstationname= xstation.find('./kml:name',ns)
            stationname = xstationname.text
            stationValues[stationname] = {key: [] for key in elements}
    
            for key in elements:
                xvaluesEl= xstation.find('./kml:ExtendedData/dwd:Forecast[@dwd:elementName="{}"]/dwd:value'.format(key),ns)
                valuesEl = xvaluesEl.text.split()
                stationValues[stationname][key] =  valuesEl
    except Exception as e:
        print(e)
        
    return timestamps, stationValues


# save extracted values as csv
def save_csv(csv_filename, stationname, timestamps, valuesDict):
    try: 
        extendedDict = {}
        extendedDict['t'] = timestamps
        extendedDict.update(valuesDict.copy())
        content = None
        with io.StringIO() as file:
            mywriter = csv.writer(file, delimiter=';')
            mywriter.writerow(extendedDict.keys())
            mywriter.writerows(zip(*extendedDict.values()))
            content = file.getvalue()
        if csv_filename:
            with open(csv_filename, 'w') as file:
                file.write(content)
    except Exception as e:
        print(e)
    return 


#download a certain kmz file, de-zip the kml file inside, and optionally save it locally.
def download_kml(dwd_url_kmz, local_folder_for_kml=None, local_folder_for_kmz=None):
    kml_content = ''
    outfilename_kml = None
    outfilename_kmz = None
    try: 
        bytesio = io.BytesIO(requests.get(dwd_url_kmz).content)
        zipfile = ZipFile(bytesio)
        kml_content = zipfile.open(zipfile.namelist()[0]).read().decode("utf-8") 
        if local_folder_for_kml:
            outfilename_kml = os.path.join(local_folder_for_kml, zipfile.namelist()[0])
            with open(outfilename_kml, "w") as f:
                f.write(kml_content)
        if local_folder_for_kmz:
            outfilename_kmz = dwd_url_kmz.split('/')[-1]
            nowstr = datetime.now().strftime('%Y%m%d_%H%M')
            outfilename_kmz = outfilename_kmz[:-4] + '_' + nowstr + outfilename_kmz[-4:]
            outfilename_kmz = os.path.join(local_folder_for_kmz, outfilename_kmz)
            with open(outfilename_kmz, 'bw') as file:
                file.write(bytesio.getvalue())
    except Exception as e:
        print(e)
    return kml_content, outfilename_kml, outfilename_kmz

#read content of a kml file to memory
def read_kml(local_kml_filename):
    data = None
    with open(local_kml_filename, 'r') as file:
        data = file.read()
    return data

#all together as a single function for easy external usage.
def download_latest_to_csv(station='10850', kml_elements=['Rad1h','Neff'], dir_csv='./data', dir_kml=None, dir_kmz=None):
    #dwd_url        = 'https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/10836/kml/MOSMIX_L_LATEST_10836.kmz' 
    dwd_url        = 'https://opendata.dwd.de/weather/local_forecasts/mos/MOSMIX_L/single_stations/' + station + '/kml/MOSMIX_L_LATEST_'+station+'.kmz' 
    kml_content, kml_filename, kmz_filename = download_kml(dwd_url,dir_kml,dir_kmz)
    timestamps, stationValuesDict = parseKML( kml_content, kml_elements)
    if station not in stationValuesDict.keys():
        print('station not included in data? strange.')
    else:
        valuesDict = stationValuesDict[station]
        todaystr = datetime.now().strftime('%Y-%m-%d')
        csv_filename = os.path.join(dir_csv, 'mosmix_'+station+'_'+todaystr+'.csv')
        save_csv(csv_filename, station, timestamps, valuesDict)

    return csv_filename, kml_filename, kmz_filename


if __name__ == "__main__":
    # example usage (executed when called directly - what I will do from a cron job)
    kml_elements=['Rad1h','Neff','N','DD','FF','FX1','PPPP','DRR1','RR1c','RRad1','SunD1','SunD','TTT','Td','ww','WPc11']
    dir_kml = dir_kmz = dir_csv = './data'
    #you need to determine station [list] from offical sources like
    # https://www.dwd.de/DE/leistungen/met_verfahren_mosmix/mosmix_stationskatalog.cfg 
    # or 3rd party services like https://wettwarn.de/mosmix/mosmix.html
    # or see readme.md for another option to visualize the stationlist.
    stations = ['10850','10836', 'Q491','Q485','P501']
    for station in stations:
        download_latest_to_csv(station, kml_elements, dir_kml=dir_kml, dir_kmz=dir_kmz, dir_csv=dir_csv)