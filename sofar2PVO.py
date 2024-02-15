#!/usr/bin/python3
# =============================================================================================================
#
# @file     sofar2PVO.py
# @author   Matthias Klemm <Matthias_Klemm@gmx.net>
# @version  1.0.2
# @Python   >= 3.2 required
# @date     February, 2024
#
# Based on a script by Michalux: https://github.com/MichaluxPL/Sofar_LSW3
#
# @section  LICENSE
#
# Copyright (C) 2024, Matthias Klemm. All rights reserved.
#
# GNU GENERAL PUBLIC LICENSE
# Version 3, 29 June 2007
#
#
# @brief    A script to gathering data from a Sofar Solar Inverter (K-TLX)
#           via logger module LSW-3/LSE and upload it to www.pvoutput.org.
#           Provide IP address, port and serial number of the inverter in the config file.


import configparser
import ipaddress
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

from sofarDevice import sofarDevice


def isValidString(s):
    return bool(isinstance(s, str) and s and not s.isspace())


os.chdir(os.path.dirname(sys.argv[0]))

# handle config file
configParser = configparser.RawConfigParser()
configFilePath = Path(os.getcwd())
configFilePath = configFilePath.joinpath('config.cfg')
if not configFilePath.is_file():
    print('Config file not found at: ' + str(configFilePath))
    sys.exit(1)
configParser.read(configFilePath)
# prepare log file
allowedLogLevels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
cfgLogLevel = configParser.get('general', 'log_level')
if not isValidString(cfgLogLevel) or not (cfgLogLevel.upper()) in allowedLogLevels:
    configParser.set('general', 'log_level', 'ERROR')
logPath = Path(configParser.get('general', 'log_path'))
if not logPath.is_dir():
    logPath = Path(os.getcwd())
logging.basicConfig(filename=logPath.joinpath('sofar2PVO.log'), filemode='a', level=getattr(logging, configParser.get('general', 'log_level')), format='%(asctime)s - %(levelname)s: %(message)s')
# open protocol file
sofarProtocolPath = Path(os.getcwd())
sofarProtocolPath = sofarProtocolPath.joinpath('sofarProtocol.json')
if not sofarProtocolPath.is_file():
    logging.error('File with protocol definition not found at: ' + str(sofarProtocolPath))
    print('File with protocol definition not found at: ' + str(sofarProtocolPath))
    sys.exit(1)
spFile = open(sofarProtocolPath)
sofarProtocol = json.load(spFile)
spFile.close()
# check optional pvoutput.org parameters
allRegRanges = ['GridOutput', 'SystemInfo', 'EnergyTodayTotals', 'PVOutput']
requiredRegRanges = ['GridOutput', 'EnergyTodayTotals', 'PVOutput']
for i in range(7, 13, 1):
    tmp = configParser.get('pvoutput', 'pvo_v' + str(i))
    if isValidString(tmp):
        tmp = tmp.split('.')
        if len(tmp) == 2 and tmp[0] in allRegRanges:
            requiredRegRanges += [tmp[0]]
        else:
            configParser.set('pvoutput', 'pvo_v' + str(i), '')
    else:
        configParser.set('pvoutput', 'pvo_v' + str(i), '')
requiredRegRanges = list(set(requiredRegRanges))
# check if ip address is valid
inverter_ip = configParser.get('SofarInverter', 'inverter_ip')
try:
    ipaddress.ip_address(inverter_ip)
except Exception as err:
    logging.error('IP address: \'%s\' is not valid', str(inverter_ip))
    print('IP address: \'' + str(inverter_ip) + '\' is not valid.')
    sys.exit(1)
inverter_port = int(configParser.get('SofarInverter', 'inverter_port'))
inverter_sn = int(configParser.get('SofarInverter', 'inverter_sn'))
# create object to connect to the inverter
sDev = sofarDevice(configParser.get('SofarInverter', 'inverter_ip'),
                   int(configParser.get('SofarInverter', 'inverter_port')),
                   int(configParser.get('SofarInverter', 'inverter_sn')),
                   float(configParser.get('pvoutput', 'pvo_system_size')), sofarProtocol)
# read current pv data from the inverter
currentValues = sDev.getRegisterRangeData(requiredRegRanges)
# sanity check
if not currentValues:
    # something went wrong -> nothing to do -> exit
    sys.exit(1)
for regRangeName in sofarProtocol:
    if regRangeName not in currentValues:
        # required registers have not been read from the inverter
        tmpStr = "Could not get %s from the inverter - exiting...", regRangeName
        logging.error(tmpStr)
        print(tmpStr)
        sys.exit(1)
if float(configParser.get('pvoutput', 'pvo_system_size')) > 0 and currentValues['EnergyTodayTotals']['PV_Generation_Today'] > 10 * float(configParser.get('pvoutput', 'pvo_system_size')):
    tmpStr = "Energy yield today too large for system size (" + configParser.get('pvoutput', 'pvo_system_size') + "kW): " + str(currentValues['EnergyTodayTotals']['PV_Generation_Today']) + "kWh"
    logging.error(tmpStr)
    print(tmpStr)
    sys.exit(1)
# compute total power of both strings
powerTotal = currentValues['PVOutput']['Power_PV1'] + currentValues['PVOutput']['Power_PV2']
if powerTotal < 10:
    # this usually happens at the beginning of a new day
    logging.warning("Zero power, ignoring today's energy yield (could be from yesterday)")
    print("Zero power, ignoring today's energy yield (could be from yesterday)")
    sys.exit(1)
if float(configParser.get('pvoutput', 'pvo_system_size')) > 0 and powerTotal > 1200 * float(configParser.get('pvoutput', 'pvo_system_size')):
    # allow 20% larger production than system size (e.g. a cold windy and sunny day)
    logging.error("Total power much larger than system size -> ignoring...")
    print("Total power much larger than system size -> ignoring...")
    sys.exit(1)

# upload data to pvoutput.org
now = datetime.now()  # current date and time
uploadStr = configParser.get('pvoutput', 'pvo_single_url') + configParser.get('pvoutput', 'pvo_apikey') + "&sid=" + configParser.get('pvoutput', 'pvo_systemid') + "&d=" + str(now.strftime("%Y%m%d")) + "&t=" + str(now.strftime("%H:%M")) + "&c1=0" + "&v1=" + str(int(currentValues['EnergyTodayTotals']['PV_Generation_Today'] * 1000)) + "&v2=" + str(powerTotal)
# handle optional pvoutput.org parameters
if bool(configParser.get('pvoutput', 'pvo_upload_temperature')):
    uploadStr = uploadStr + "&v5=" + str(currentValues['SystemInfo']['Temperature_Env1'])
if bool(configParser.get('pvoutput', 'pvo_upload_voltage')):
    uploadStr = uploadStr + "&v6=" + str(currentValues['GridOutput']['Voltage_Phase_R'])
for i in range(7, 13, 1):
    tmp = configParser.get('pvoutput', 'pvo_v' + str(i))
    if isValidString(tmp):
        try:
            tmp = tmp.split('.')
            uploadStr = uploadStr + "&v" + str(i) + "=" + str(int(currentValues[tmp[0]][tmp[1]]))
        except Exception as err:
            logging.warning("Optional pvoutput parameter pvo_v%d failed: %s", i, err)
            continue
r = requests.get(uploadStr)
if r.status_code != 200:
    logging.error('Uploader to pvoutput.org failed: %s', r.text)
    print('Uploader to pvoutput.org failed: ', r.text)
