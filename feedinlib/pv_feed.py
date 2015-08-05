"""
#!/usr/bin/python
# -*- coding: utf-8

from oemof.feedinlib import pv_feed
import logging
logging.getLogger('pvlib').setLevel(logging.DEBUG)  # or at least INFO

# Database connection parameter
DIC = {
    'ip': 'IP address',
    'db': 'DB name',
    'user': 'username',
    'password': 'password',
    'port': 'port'}

# Plant and site parameter
site = {'module_name': 'Advent_Solar_Ventura_210___2008_',
        'Area': 1,
        'azimuth': 0,
        'tilt': 30,
        'parallelStrings': 1,
        'seriesModules': 1,
        'TZ': 'Europe/Berlin',
        'albedo': 0.2,
        'latitude': 52.1438,
        'longitude': 8.07932}

obj = pv_feed.PvFeed(DIC, site, '2010')
"""
from matplotlib import pyplot as plt
from .base_feed import Feed
import numpy as np
import pandas as pd
import sys
import os.path as path
sys.path.append(path.join(path.dirname(__file__), 'pvlib-python'))
import pvlib


class PvFeed(Feed):

    def __init__(self, conn, geo, site, year, params=None,
                 elevation_mean=False):
        """
        private class for the implementation of a Phovoltaic Feed as timeseries
        :param DIC: database parameters
        :param site: site and plant parameters
        :param year: the year to get the data for
        """
        super(PvFeed, self).__init__(conn, geo, site, year, params,
                                     elevation_mean=elevation_mean)

        self.conn = conn
        self.year = year

    def _apply_model(self, site, year, weather, elevation_mean):
        """
        implementation of the model to generate the _timeseries data from the
        weatherdata
        :return:
        """
        data = weather.data
        self._timeseries = "pv timeseries"
        # TODO: setup the model, currently being done by caro

        # 1. Fetch module parameter from Sandia Database
        module_data = (pvlib.pvsystem.retrieve_sam('SandiaMod')
                       [site['module_name']])

        # 2. Overwriting module area (better: switch on and off this option)
        module_data['Area'] = site['Area']

        # temporary fix of site information (changed from struct to object in
        # pvlib-python
        location = pvlib.location.Location(site['latitude'], site['longitude'],
                                           site['TZ'])

        # 3. Determine the postion of the sun
        DaFrOut = pvlib.solarposition.get_solarposition(
            time=data.index, location=location, method='pyephem')
        DaFrOut_b = pvlib.solarposition.get_solarposition(
            time=data.index, location=location, method='ephemeris')

        # 3a. add column with mean elevation (based on 5-minutes values)
        # for each hour
        if elevation_mean:
            data_5min = pd.DataFrame(
                index=pd.date_range(DaFrOut_b.index[0],
                                    periods=site['hoy']*12, freq='5Min',
                                    tz=site['TZ']))
            DFrOut_5min = pvlib.solarposition.get_solarposition(
                time=data_5min.index, location=location, method='ephemeris')
            data['SunEl_b_mean'] = (
                DFrOut_5min['elevation'].clip_lower(0).resample(
                    'H', how='mean'))

        # temporary: changed new data structure of pvlib-python to that one
        # which was used so far to ensure functionality
        data['SunAz'] = DaFrOut['azimuth']
        data['SunAz'] = DaFrOut['azimuth']
        data['SunEl'] = DaFrOut['elevation']
        data['AppSunEl'] = DaFrOut['apparent_elevation']
        data['SunZen'] = DaFrOut['zenith']
        data['SunZen_b'] = DaFrOut_b['zenith']
        data['SunEl_b'] = DaFrOut_b['elevation']
        # DaFrOut['apparent_zenith']  # unused?

        # 4. Determine the global horizontal irradiation
        data['ghi'] = data['dirhi'] + data['dhi']

        # 5. Determine the extraterrestrial radiation
        data['HExtra'] = pvlib.irradiance.extraradiation(
            datetime_or_doy=data.index.dayofyear)

        data['SunZen'][data['SunZen'] > 90] = 90

        # 6. Determine the relative air mass
        data['AM'] = pvlib.atmosphere.relativeairmass(data['SunZen'])

        # 7. Determine the angle of incidence
        data['AOI'] = pvlib.irradiance.aoi(solar_azimuth=data['SunAz'],
            solar_zenith=data['SunZen'], surface_tilt=site['tilt'],
            surface_azimuth=site['azimuth'])

#########################################################################
#        data['AOI'][data['AOI'] > 90] = 90


        # Direktnormalstrahlung? AOI = 0?
##########################################################################

        # 8. Determine direct normal irradiation
        if elevation_mean:
            data['dni'] = (data['dirhi']) / np.sin(np.radians(
                data['SunEl_b_mean']))
        else:
            data['dni'] = (data['dirhi']) / np.sin(np.radians(
                data['SunEl_b']))
        #data['DNI'] = (data['GHI'] - data['DHI']) / np.sin(h)

        # what for??
        data['dni'][data['SunZen'] > 88] = data['dirhi']
#        plt.plot(data['ghi'])
        plt.show()

        #print(sum(data['GHI']))
        #print(sum(data['DHI']))
        #print(sum(data['DirHI']))
        #print(sum(data['DNI']))

#        plt.plot(data['SunAz'], 90 - data['SunZen'], '.')
#        plt.show()

        ## what is this??
        #plt.plot((90 - data['SunZen']) * 10)
        #plt.plot((data['SunZen']))
        #plt.plot((np.cos(data['SunZen'] / 180 * np.pi) * 100))
        #plt.show()

        # 9a. Determine the sky diffuse irradiation in plane
        # with model of Perez (switch would be good, see 9b)
        data['In_Plane_SkyDiffuseP'] = pvlib.irradiance.perez(
            surface_tilt=site['tilt'],
            surface_azimuth=site['azimuth'],
            dhi=data['dhi'],
            dni=data['dni'],
            dni_extra=data['HExtra'],
            solar_zenith=data['SunZen'],
            solar_azimuth=data['SunAz'],
            airmass=data['AM'])

        # what for ??
        data['In_Plane_SkyDiffuseP'][pd.isnull(data['In_Plane_SkyDiffuseP'])] \
        = 0

        # 9b. Determine the sky diffuse irradiation in plane
        # with model of Perez (switch would be good)
        data['In_Plane_SkyDiffuse'] = pvlib.irradiance.klucher(site['tilt'],
            site['azimuth'], data['dhi'], data['ghi'], data['SunZen'],
            data['SunAz'])

        #print(sum(data['In_Plane_SkyDiffuse']))
        #print(sum(data['In_Plane_SkyDiffuseP']))
        #print(sum(data['DHI']))

        # 10. Determine the diffuse irradiation from ground reflection in plane
        data['GR'] = pvlib.irradiance.grounddiffuse(ghi=data['ghi'],
            albedo=site['albedo'], surface_tilt=site['tilt'])

        # 11. Determine total in-plane irradiance
        DFr = pvlib.irradiance.globalinplane(
            aoi=data['AOI'],
            dni=data['dni'],
            poa_sky_diffuse=data['In_Plane_SkyDiffuse'],
            poa_ground_diffuse=data['GR'])

        # method pvlib.irradiance.globalinplane is not working yet
        # (PVLIB Issue)
        data['E'] = DFr['poa_global']
        data['Eb'] = DFr['poa_direct']
        data['EDiff'] = DFr['poa_diffuse']

        # warum wird E negativ?
        #print(data['AOI'][data['AOI'] > 90])
        #print data['AOI'][data['E'] < 0]
        #plt.plot(data['E'])
        #plt.show()

        # 12. Determine module and cell temperature
        data['temp_C'] = data['temp_air'] - 273.15
        DataFrame = pvlib.pvsystem.sapm_celltemp(
            irrad=data['E'],
            wind=data['v_wind'],
            temp=data['temp_C'],
            model='Open_rack_cell_polymerback')

        # 13. Apply the Sandia PV Array Performance Model (SAPM) to get a
        # dataframe with all relevant electric output parameters
        data_tmp = pvlib.pvsystem.sapm(
            poa_direct=data['Eb'],
            poa_diffuse=data['EDiff'],
            temp_cell=DataFrame['temp_cell'],
            airmass_absolute=data['AM'],
            aoi=data['AOI'],
            module=module_data)

        data['Pmp'] = data_tmp['p_mp']

##############################################################################
        # DIVERSE AUSWERTUNGEN

        #print sum(data['E'])
        #print sum(data['GHI'])
        #print sum(DFOut['Pmp'])

        #Data['Imp']=DFOut['Imp']*meta['parallelStrings']
        #Data['Voc']=DFOut['Voc']
        #Data['Vmp']=DFOut['Vmp']*meta['seriesModules']
        #Data['Pmp']=Data.Imp*Data.Vmp
        #Data['Ix']=DFOut['Ix']
        #Data['Ixx']=DFOut['Ixx']

#        return DFOut['Pmp']

        ## Einfallswinkel
        #out.write_csv('/home/caro/rliserver/04_Projekte/026_Berechnungstool/' +
        #'04-Projektinhalte/PV_Modell_Vergleich/2015_PV_Modell_Vergleich_3/PVLIB_Python/results', 'aoi.csv',
        #data['AOI'])

        ## Direktstrahlung auf geneigte Ebene
        #out.write_csv('/home/caro/rliserver/04_Projekte/026_Berechnungstool/' +
        #'04-Projektinhalte/PV_Modell_Vergleich/2015_PV_Modell_Vergleich_3/PVLIB_Python/results', 'eb.csv',
        #data['Eb'])


        ## Diffusstrahlung auf geneigte Ebene (gesamt)
        #out.write_csv('/home/caro/rliserver/04_Projekte/026_Berechnungstool/' +
        #'04-Projektinhalte/PV_Modell_Vergleich/2015_PV_Modell_Vergleich_3/PVLIB_Python/results', 'ediff.csv',
        #data['EDiff'])

        ## Globalstrahlung auf geneigte Ebene
        #out.write_csv('/home/caro/rliserver/04_Projekte/026_Berechnungstool/' +
        #'04-Projektinhalte/PV_Modell_Vergleich/2015_PV_Modell_Vergleich_3/PVLIB_Python/results', 'e.csv',
        #data['E'])

        ##out.write_csv('/home/caro/rliserver/04_Projekte/026_Berechnungstool/' +
        ##'04-Projektinhalte/PV_Modell_Vergleich/PVLIB_Python/results', 'pmp.csv',
        ##data['Pmp'])

        ##print(module_data['Area'])


        ##results = db.read_data_from_file('3d_3.csv',
            ##'/home/likewise-open/RL-INSTITUT/birgit.schachler')

        ##fig = plt.figure()

        ##tilt, azimuth = np.meshgrid(tilt, azimuth)
        ##print(results)

        ##fig = plt.figure()
        ##ax = Axes3D(fig)

        ##surf = ax.plot_surface(tilt, azimuth, results,
            ##rstride=1, cstride=1, cmap=cm.jet, linewidth=0, antialiased=False)
        ##fig.colorbar(surf)

        ##plt.show()