# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ARPAweather
                                 A QGIS plugin
 Simplifies the process of collecting and analyzing meteorological ground sensor data. The data are provided by the Environmental Protection Agency of Lombardia Region (ARPA Lombardia) in Northern Italy and include  comprehensive open datasets of weather observations collected over multiple years.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2023-02-14
        git sha              : $Format:%H$
        copyright            : (C) 2023 by Emanuele Capizzi - Politecnico di Milano
        email                : emanuele.capizzi@polimi.it
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant, QDate
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QFileDialog
from qgis.core import QgsProject, QgsVectorLayer, QgsFields, QgsField, QgsGeometry, QgsPointXY, QgsFeature, Qgis, QgsVectorFileWriter, QgsApplication
from qgis.utils import iface
from PyQt5.QtCore import QTextCodec

# Import libraries
from sodapy import Socrata
import pandas as pd
from datetime import datetime, timedelta
import requests
from io import BytesIO
from zipfile import ZipFile
import os
import time
import json
import numpy as np
import dask.dataframe as dd

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .arpaweather_dialog import ARPAweatherDialog
import os.path

# Set the directory to this script path
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Create tmp folder to save csv files
tmp_dir = os.path.join(script_dir, 'tmp')
if not os.path.exists(tmp_dir):
    os.mkdir(tmp_dir)

# Weather sensors types
sensors_types = ["Altezza Neve", "Direzione Vento", "Livello Idrometrico", "Precipitazione", "Radiazione Globale", "Temperatura",
                 "Umidità Relativa", "Velocità Vento"]

switcher = {
            '2023': "https://www.dati.lombardia.it/download/48xr-g9b9/application%2Fzip",
            '2022': "https://www.dati.lombardia.it/download/mvvc-nmzv/application%2Fzip",
            '2021': "https://www.dati.lombardia.it/download/49n9-866s/application%2Fzip",
            '2020': "https://www.dati.lombardia.it/download/erjn-istm/application%2Fzip",
            '2019': "https://www.dati.lombardia.it/download/wrhf-6ztd/application%2Fzip",
            '2018': "https://www.dati.lombardia.it/download/sfbe-yqe8/application%2Fzip",
            '2017': "https://www.dati.lombardia.it/download/vx6g-atiu/application%2Fzip",
            '2016': "https://www.dati.lombardia.it/download/kgxu-frcw/application%2Fzip"
        }

class ARPAweather:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'ARPAweather_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&ARPA Weather')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('ARPAweather', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/arpaweather/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'ARPA Weather'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&ARPA Weather'),
                action)
            self.iface.removeToolBarIcon(action)

    def select_output_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        filename, _filter = QFileDialog.getSaveFileName(self.dlg, "Save Layer As", "", "Shapefiles (*.shp);;Geopackages (*.gpkg);;CSV Files (*.csv)", options=options)
        self.dlg.leOutputFileName.setText(filename)

    def connect_ARPA_api(self, token=""):
        """
        Connect to the ARPA API using the provided authentication token.

        If no token is provided, the client will be unauthenticated and subject to strict throttling limits.
        An authentication token can be obtained from the Open Data Lombardia website.

        Parameters:
            token (str): The authentication token obtained from the Open Data Lombardia website.

        Returns:
            Socrata: A client session object for accessing the ARPA API.
        """
        # Connect to Open Data Lombardia using the token
        if token == "":
            print("No token provided. Requests made without an app_token will be subject to strict throttling limits.")
            client = Socrata("www.dati.lombardia.it", None)
        else:
            print("Using provided token.")
            client = Socrata("www.dati.lombardia.it", app_token=token)

        return client

    def ARPA_sensors_info(self, client) -> pd.DataFrame:
        """
        Convert the ARPA sensors information obtained from a Socrata client to a Pandas dataframe and fix the data types.

        Parameters:
            client (Socrata): A Socrata client session object for accessing the ARPA API.

        Returns:
            pd.DataFrame: A dataframe containing ARPA sensors information, with fixed data types.
        """

        # Select meteo stations dataset containing positions and information about sensors
        stationsId = "nf78-nj6b"
        sensors_info = client.get_all(stationsId)

        # Convert the sensor information to a Pandas dataframe and fix the data types
        sensors_df = pd.DataFrame(sensors_info)
        sensors_df["idsensore"] = sensors_df["idsensore"].astype("int32")
        sensors_df["tipologia"] = sensors_df["tipologia"].astype("category")
        sensors_df["idstazione"] = sensors_df["idstazione"].astype("int32")
        sensors_df["quota"] = sensors_df["quota"].astype("int16")
        sensors_df["unit_dimisura"] = sensors_df["unit_dimisura"].astype("category")
        sensors_df["provincia"] = sensors_df["provincia"].astype("category")
        sensors_df["storico"] = sensors_df["storico"].astype("category")
        sensors_df["datastart"] = pd.to_datetime(sensors_df["datastart"])
        sensors_df["datastop"] = pd.to_datetime(sensors_df["datastop"])
        sensors_df = sensors_df.drop(columns=[":@computed_region_6hky_swhk", ":@computed_region_ttgh_9sm5"])

        return sensors_df

    def req_ARPA_start_end_date_API(self, client):
        """
        Requests the start and end date of data available in the ARPA API.

        Parameters:
            client (sodapy.Socrata): Client session for interacting with the ARPA API.

        Returns:
            Tuple[datetime, datetime]: The earliest and latest dates available in the ARPA API.

        Raises:
            Exception: If there is an issue making the API request or parsing the response.

        """
        try:
            with client:
                # Dataset ID for weather sensors on Open Data Lombardia
                weather_sensor_id = "647i-nhxk"

                # Query the API for the minimum and maximum dates available
                query = """ select MAX(data), MIN(data) limit 9999999999999999"""

                # Extract the min and max dates from the API response
                min_max_dates = client.get(weather_sensor_id, query=query)[0]

                # Start and minimum dates from the dict obtained from the API
                start_API_date = min_max_dates['MIN_data']
                end_API_date = min_max_dates['MAX_data']

                # Convert the date strings to datetime objects
                start_API_date = datetime.strptime(
                    start_API_date, "%Y-%m-%dT%H:%M:%S.%f")
                end_API_date = datetime.strptime(
                    end_API_date, "%Y-%m-%dT%H:%M:%S.%f")

                return start_API_date, end_API_date

        except Exception as e:
            # If there's an error, print a message and raise an exception
            print(f"Error fetching ARPA API data: {e}")
            raise Exception("Error fetching ARPA API data")

    def req_ARPA_data_API(self, client, start_date, end_date, sensors_list):
        """
        Function to request data from available weather sensors in the ARPA API using a query.

        Parameters:
            client (requests.Session): the client session
            start_date (datetime): the start date in datetime format
            end_date (datetime): the end date in datetime format
            sensors_list (list of int): list of selected sensor ids

        Returns:
            pandas.DataFrame: dataframe with idsensore, data and valore of the weather sensors within the specific time period
        """

        # Select the Open Data Lombardia Meteo sensors dataset
        weather_sensor_id = "647i-nhxk"

        # Convert to string in year-month-day format, accepted by ARPA query
        start_date = start_date.strftime("%Y-%m-%dT%H:%M:%S.%f")
        end_date = end_date.strftime("%Y-%m-%dT%H:%M:%S.%f")

        # Query data
        query = """
        select
            *
        where data >= \'{}\' and data <= \'{}\' limit 9999999999999999
        """.format(start_date, end_date)

        # Get time series and evaluate time spent to request them
        time_series = client.get(weather_sensor_id, query=query)

        # Create dataframe
        df = pd.DataFrame(time_series, columns=['idsensore', 'data', 'valore'])

        # Convert types
        df['valore'] = df['valore'].astype('float32')
        df['idsensore'] = df['idsensore'].astype('int32')
        df['data'] = pd.to_datetime(df['data'])
        df = df.sort_values(by='data', ascending=True).reset_index(drop=True)

        # Filter with selected sensors list
        try:
            df = df[df['value'] != -9999]
        except:
            df = df[df['valore'] != -9999]
        df = df[df['idsensore'].isin(sensors_list)]

        return df

    def download_extract_csv_from_year(self, year, switcher):
        """
        Downloads a zipped CSV file of meteorological data from ARPA sensors for a given year from the Open Data Lombardia website.
        If the file has already been downloaded, it will be skipped.
        Extracts the downloaded zip file and saves the CSV file to the temporary directory (tmp).

        Parameters:
            year (str): The selected year for downloading the CSV file containing the meteorological sensors time series.

        Returns:
            None
        """
        
        # Create a dictionary with years and corresponding download links on Open Data Lombardia - REQUIRES TO BE UPDATED EVERY YEAR
        switcher = switcher
        
        # Select the URL based on the year and make request
        url = switcher[year]
        filename = 'meteo_'+str(year)+'.zip'
        
        # If year.csv file is already downloaded, skip download
        if not os.path.exists(os.path.join(tmp_dir, f"{year}.csv")):
            print("--- Starting download ---")
            t = time.time()
            print((f'Downloading {filename} -> Started. It might take a while... Please wait!'))
            response = requests.get(url, stream=True)
            
            block_size = 1024
            wrote = 0 
            
            # Writing the file to the local file system
            with open(os.path.join(tmp_dir, filename), "wb") as f:
                for data in response.iter_content(block_size):
                    wrote = wrote + len(data)
                    f.write(data)
                    #percentage = wrote / (block_size*block_size)
                    #print("\rDownloaded: {:0.2f} MB".format(percentage), end="")
                
            elapsed = time.time() - t
            
            print((f'\nDownloading {filename} -> Completed. Time required for download: {elapsed:0.2f} s.'))

            print((f"Starting unzipping: {filename}"))

            #Loading the .zip and creating a zip object
            with ZipFile(os.path.join(tmp_dir, filename), 'r') as zObject:
                # Extracting all the members of the zip into a specific location
                zObject.extractall(tmp_dir)

            csv_file=str(year)+'.csv'
            print((f"File unzipped: {filename}"))
            print((f"File csv saved: {filename}"))

            #Remove the zip folder
            if os.path.exists(os.path.join(tmp_dir, filename)):
                print(("{filename} removed").format(filename=filename))
                os.remove(os.path.join(tmp_dir, filename))
            else:
                print((f"The file {filename} does not exist in this folder"))
        
        else:
            print(f"{year}.csv already exists. It won't be downloaded.")

    def process_ARPA_csv(self, csv_file, start_date, end_date, sensors_list):
        """
        Reads an ARPA csv file into a Dask dataframe, applies data processing and returns a computed and filtered Dask dataframe. 

        Args:
            csv_file (str): File name of the csv file
            start_date (datetime): Start date for processing
            end_date (datetime): End date for processing
            sensors_list (list of str): List of selected sensors

        Returns:
            df (Dask dataframe): Computed filtered Dask dataframe
        """
        
        print("--- Starting processing csv data ---")
        print(("The time range used for the processing is {start_date} to {end_date}").format(start_date=start_date,end_date=end_date))
        
        #Read csv file with Dask dataframe
        csv_file = os.path.join(tmp_dir, csv_file)
        df = dd.read_csv(csv_file, usecols=['IdSensore','Data','Valore', 'Stato']) 
        
        # Rename columns to match API column names
        df = df.rename(columns={'IdSensore': 'idsensore', 'Data': 'data', 'Valore': 'valore', 'Stato':'stato'})
        
        # Format data types
        df['valore'] = df['valore'].astype('float32')
        df['idsensore'] = df['idsensore'].astype('int32')
        df['data'] = dd.to_datetime(df.data, format='%d/%m/%Y %H:%M:%S')
        df['stato'] = df['stato'].astype(str)
        
        # Filter out invalid data and select sensors within the specified range and list
        df = df[df['valore'] != -9999]
        df = df.loc[(df['data'] >= start_date) & (df['data'] <= end_date)]
        sensors_list = list(map(int, sensors_list))
        df = df[df['idsensore'].isin(sensors_list)] #keep only sensors in the list (for example providing a list of temperature sensors, will keep only those)
        df = df[df.stato.isin(["VA", "VV"])] #keep only validated data identified by stato equal to VA and VV
        df = df.drop(['stato'], axis=1)
        
        # Sort the dataframe by date
        df = df.sort_values(by='data', ascending=True).reset_index(drop=True)
        
        print("Starting computing dataframe")
        
        #Compute df
        t = time.time()
        df = df.compute()
        elapsed = time.time() - t
        print("Time used for computing dataframe {time:0.2f} s.".format(time=elapsed))
        
        return df 

    def aggregate_group_data(self, df):
        """
        Aggregates ARPA data using statistical aggregation functions (mean, max, min, std, and count), except for wind direction (Direzione Vento).
        The dataframe is grouped by sensor ID (`idsensore`).

        Parameters:
            df (DataFrame): ARPA DataFrame containing the following columns: `idsensore` (int), 
                            `data` (datetime), and `valore` (float)

        Returns:
            DataFrame: aggregated DataFrame containing the following columns: `idsensore` (int), 
                        `mean` (float), `max` (float), `min` (float), `std` (float), and `count` (int)
        """

        # Group the DataFrame by 'idsensore' and compute the statistical metrics
        grouped = df.groupby('idsensore')['valore'].agg(['mean', 'max', 'min', 'std', 'count'])

        # Reset the index to make 'idsensore' a column again
        grouped = grouped.reset_index()

        return grouped
    
    def aggregate_group_data_wind_dir(self, df):
        """
        Aggregates ARPA wind direction data using mode and count functions. The dataframe is grouped by sensor id (idsensore).

        Parameters:
            df(dataframe): ARPA dataframe containing the following columns: "idsensore"(int), "data"(datetime) and "valore"(float)

        Returns:
            df(dataframe): computed filtered and aggregated dask dataframe
        """

        # Group by sensor id and aggregate wind direction values using mode and count functions
        grouped = df.groupby('idsensore')['valore'].agg([lambda x: pd.Series.mode(x)[0], 'count']).rename({'<lambda_0>': 'mode'}, axis=1)
        grouped = grouped.reset_index()

        return grouped

    def cleanup_csv_files():
        """
        Deletes all the CSV files present in the temporary folder (tmp).
        """
        folder_path = tmp_dir
        for filename in os.listdir(folder_path):
            if filename.endswith(".csv"):
                file_path = os.path.join(folder_path, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print("Error while deleting file:", e)

    def toggle_group_box(self):
        if self.dlg.rb1.isChecked():
            self.dlg.gb1.setEnabled(True)
            self.dlg.gb2.setEnabled(False)
        else:
            self.dlg.gb1.setEnabled(False)
            self.dlg.gb2.setEnabled(True)

# --- RUN ------------

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = ARPAweatherDialog()
            self.dlg.pbOutputSave.clicked.connect(self.select_output_file)
            # Group box toggled
            self.dlg.gb1.setEnabled(True) # Set group box 1 (API) enabled
            self.dlg.gb2.setEnabled(False) # Set group box 2 (CSV) disabled
            self.dlg.rb1.setChecked(True) # Radio button 1 (API) checked at the beginning
            self.dlg.rb1.toggled.connect(self.toggle_group_box)
            self.dlg.rb2.toggled.connect(self.toggle_group_box)
    

        # Add sensors type
        self.dlg.cbSensorsType.clear()
        self.dlg.cbSensorsType.addItems([str(sensor) for sensor in sensors_types])
        self.dlg.leOutputFileName.clear()

        # Add documentation link
        self.dlg.labelLinkDoc.setText('<a href="https://github.com/capizziemanuele/ARPA_Weather_plugin">GitHub Doc</a>')
        self.dlg.labelLinkDoc.setOpenExternalLinks(True)


        # Modifiy initial widgets
        try:
            # Connect to the ARPA API
            client = self.connect_ARPA_api()

            # Request the start and end dates from the API
            start_date_API, end_date_API = self.req_ARPA_start_end_date_API(client)

            # Convert start and end dates to string format
            label_name_start = start_date_API.strftime("%Y-%m-%d %H:%M:%S")
            label_name_end = end_date_API.strftime("%Y-%m-%d %H:%M:%S")

            # Update date labels in the GUI
            self.dlg.label_startAPIdate.setText(label_name_start)
            self.dlg.label_endAPIdate.setText(label_name_end)

        except requests.exceptions.RequestException as e:
            # Raise an error message if there is an issue with the request
            QMessageBox.warning(self.dlg, "Error", str(e))

        # List of available years in CSV files
        self.dlg.cb_list_years.addItems(list(switcher.keys()))
        
        # Get the selected year from the combo box
        selected_year = self.dlg.cb_list_years.currentText()
        # Get the current date and time from the datetime widget
        self.dlg.cb_list_years.currentIndexChanged.connect(self.updateDateTime)

        # Options for the calendar (date selection)
        self.dlg.dtStartTime_api.setDisplayFormat("dd-MM-yyyy hh:mm:ss")
        self.dlg.dtEndTime_api.setDisplayFormat("dd-MM-yyyy hh:mm:ss")
        self.dlg.dtStartTime_api.setDate(start_date_API)
        self.dlg.dtEndTime_api.setDate(end_date_API)
        self.dlg.dtStartTime_api.setCalendarPopup(True)
        self.dlg.dtEndTime_api.setCalendarPopup(True)

        self.dlg.dtStartTime_csv.setDisplayFormat("dd-MM-yyyy hh:mm:ss")
        self.dlg.dtEndTime_csv.setDisplayFormat("dd-MM-yyyy hh:mm:ss")
        #self.dlg.dtStartTime_csv.setDate(today)
        #self.dlg.dtEndTime_csv.setDate(today)
        self.dlg.dtStartTime_csv.setCalendarPopup(True)
        self.dlg.dtEndTime_csv.setCalendarPopup(True)

        # It gets the datetime of the first day of current month. It is used to decide if require data from csv or API.
        # api_start_limit = datetime(datetime.today().year, datetime.today().month, 1)  #not used


        # Show the dialog
        self.dlg.show()

        # Run the dialog event loop
        result = self.dlg.exec_()

        if result:

            # Get the start and the end date from the gui
            if self.dlg.rb1.isChecked():
                start_date = self.dlg.dtStartTime_api.dateTime().toPyDateTime()
                end_date = self.dlg.dtEndTime_api.dateTime().toPyDateTime()
                if start_date.year != end_date.year:
                    QMessageBox.warning(None, "Invalid Date Range", "Dates must be in the same year!")
            else:
                start_date = self.dlg.dtStartTime_csv.dateTime().toPyDateTime()
                end_date = self.dlg.dtEndTime_csv.dateTime().toPyDateTime()

            # Create client
            if self.dlg.rb1.isChecked():
                arpa_token = self.dlg.leToken.text()
            else:
                arpa_token = ""

            client = self.connect_ARPA_api(arpa_token)

            with client:
                # Dataframe containing sensors information
                sensors_df = self.ARPA_sensors_info(client)

                # Get the selected sensorfrom the gui
                sensor_sel = self.dlg.cbSensorsType.currentText()

                # Filter the sensors depending on the "tipologia" field (sensor type)
                sensors_list = (sensors_df.loc[sensors_df['tipologia'] == sensor_sel]).idsensore.tolist()

                year = start_date.year 
                # Check that the start and end dates are in the same year
                if start_date.year != end_date.year:
                    QMessageBox.warning(None, "Invalid Date Range", "Dates must be in the same year!")
                    return
                elif start_date > end_date:
                    QMessageBox.warning(None, "Invalid Date Range", "Start date must be before end date")
                    return

                # Request time series
                if start_date < start_date_API:
                    print("Requesting CSV. This will take a while.")
                    sensors_values = self.download_extract_csv_from_year(str(year), switcher) #download the csv corresponding to the selected year
                    csv_file = str(year)+'.csv'

                    sensors_values = self.process_ARPA_csv(csv_file, start_date, end_date, sensors_list) #process csv file with dask

                #If the chosen start date is equal or after the start date of API -> request data from API
                elif start_date >= start_date_API:
                    print("Requesting from API")
                    sensors_values = self.req_ARPA_data_API(client, start_date, end_date, sensors_list) #request data from ARPA API


                # Calculate statistics on the whole dataset
                if sensor_sel != "Direzione Vento":
                    sensor_test_agg = self.aggregate_group_data(sensors_values)
                
                if sensor_sel == "Direzione Vento":
                    sensor_test_agg = self.aggregate_group_data_wind_dir(sensors_values)

                # Merge the values with the sensors info
                merged_df = pd.merge(sensor_test_agg, sensors_df, on='idsensore')

                merged_df['lng'] = merged_df['lng'].astype('float64')
                merged_df['lat'] = merged_df['lat'].astype('float64')
                merged_df['idsensore'] = merged_df['idsensore'].astype('int32')
                merged_df['tipologia'] = merged_df['tipologia'].astype(str)
                merged_df['datastart'] = merged_df['datastart'].astype(str)

                # print(os.getcwd())
                # merged_df.to_csv('./test.csv', index=False)

                # Create vector layer
                
                layer_date_start = max(start_date_API, start_date)
                layer_date_end = min(end_date_API, end_date)


                layer = QgsVectorLayer("Point?crs=EPSG:4326", sensor_sel+' ({start} / {end})'.format(start=layer_date_start, end=layer_date_end), "memory")

                if sensor_sel != "Direzione Vento":
                    layer.dataProvider().addAttributes([QgsField("idsensore", QVariant.Int), QgsField("mean", QVariant.Double), QgsField("max", QVariant.Double),
                                                        QgsField("min", QVariant.Double), QgsField("std", QVariant.Double), QgsField("count", QVariant.Int),
                                                        QgsField("tipologia", QVariant.String),
                                                        QgsField("unit_dimisura", QVariant.String), QgsField("idstazione", QVariant.Int),
                                                        QgsField("nomestazione", QVariant.String), QgsField("quota", QVariant.Double),
                                                        QgsField("provincia", QVariant.String), QgsField("datastart", QVariant.String),
                                                        QgsField("storico", QVariant.String),
                                                        QgsField("cgb_nord", QVariant.Int), QgsField("cgb_est", QVariant.Int),
                                                        QgsField("lng", QVariant.Double), QgsField("lat", QVariant.Double)])
                
                if sensor_sel == "Direzione Vento":
                    layer.dataProvider().addAttributes([QgsField("idsensore", QVariant.Int), QgsField("mode", QVariant.Double), QgsField("count", QVariant.Int),
                                                        QgsField("tipologia", QVariant.String),
                                                        QgsField("unit_dimisura", QVariant.String), QgsField("idstazione", QVariant.Int),
                                                        QgsField("nomestazione", QVariant.String), QgsField("quota", QVariant.Double),
                                                        QgsField("provincia", QVariant.String), QgsField("datastart", QVariant.String),
                                                        QgsField("storico", QVariant.String),
                                                        QgsField("cgb_nord", QVariant.Int), QgsField("cgb_est", QVariant.Int),
                                                        QgsField("lng", QVariant.Double), QgsField("lat", QVariant.Double)])

                # Update fields and start editing
                layer.updateFields()
                layer.startEditing()

                # Features creation
                features = []
                if sensor_sel != "Direzione Vento":         # If wind direction sensor is NOT selected
                    for index, row in merged_df.iterrows():
                        point = QgsPointXY(row['lng'], row['lat'])
                        feature = QgsFeature()
                        feature.setGeometry(QgsGeometry.fromPointXY(point))
                        feature.setAttributes([QVariant(row['idsensore']), QVariant(row['mean']), QVariant(row['max']),
                                            QVariant(row['min']), QVariant(row['std']), QVariant(row['count']),
                                            QVariant(row['tipologia']), QVariant(row['unit_dimisura']),
                                            QVariant(row['idstazione']), QVariant(row['nomestazione']),
                                            QVariant(row['quota']), QVariant(row['provincia']), QVariant(row['datastart']), 
                                            QVariant(row['storico']), QVariant(row['cgb_nord']),
                                            QVariant(row['cgb_est']), QVariant(row['lng']), QVariant(row['lat'])])
                        features.append(feature)
                
                if sensor_sel == "Direzione Vento":         # If wind direction sensor is selected
                    for index, row in merged_df.iterrows():
                        point = QgsPointXY(row['lng'], row['lat'])
                        feature = QgsFeature()
                        feature.setGeometry(QgsGeometry.fromPointXY(point))
                        feature.setAttributes([QVariant(row['idsensore']), QVariant(row['mode']), QVariant(row['count']),
                                            QVariant(row['tipologia']), QVariant(row['unit_dimisura']),
                                            QVariant(row['idstazione']), QVariant(row['nomestazione']),
                                            QVariant(row['quota']), QVariant(row['provincia']), QVariant(row['datastart']), 
                                            QVariant(row['storico']), QVariant(row['cgb_nord']),
                                            QVariant(row['cgb_est']), QVariant(row['lng']), QVariant(row['lat'])])
                        features.append(feature)

                # Add features and commit changes
                layer.addFeatures(features)
                layer.commitChanges()

                # Add the layer to the QGIS project
                QgsProject.instance().addMapLayer(layer)
                layer.updateExtents()

                # Save file as shp/gpkg/csv
                filename = self.dlg.leOutputFileName.text()
                context = QgsProject.instance().transformContext()

                if filename != "":
                    if filename.endswith(".shp"):
                        # Save as a shapefile
                        options = QgsVectorFileWriter.SaveVectorOptions()
                        options.driverName = 'ESRI Shapefile'
                        QgsVectorFileWriter.writeAsVectorFormatV3(layer, filename, context, options)
                    elif filename.endswith(".gpkg"):
                        # Save as a geopackage
                        options = QgsVectorFileWriter.SaveVectorOptions()
                        options.driverName = 'GPKG'
                        QgsVectorFileWriter.writeAsVectorFormatV3(layer, filename, context, options)
                    elif filename.endswith(".csv"):
                        # Save as csv
                        merged_df.to_csv(filename, index=False)
                    
                    # Write message
                    self.iface.messageBar().pushMessage("Success", "Output file written at " + filename, level=Qgis.Success, duration=3)

            pass

    QgsApplication.instance().aboutToQuit.connect(cleanup_csv_files)
