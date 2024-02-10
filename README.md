# SOFAR Inverter G3 + LSW-3/LSE to pvoutput.org
Small utility to read data from SOFAR K-TLX G3 inverters through the Solarman (LSW-3/LSE) datalogger 
and upload total power of both strings and daily energy yield to pvoutput.org.
Fill in the necessary info in the config file before running the script.
Optionally, additional parameters, such as e.g. inverter temperature, voltage / current / power of each string, can be uploaded.

The script will try up to 10 times to connect to the inverter and obtain valid data.

Python 3.2 or later is required to run the script.
Use cron (linux) or the task scheduler (Windows) to run the script every 5 minutes 

*Thanks to @MichaluxPL https://github.com/MichaluxPL

# Required python modules
To run, the script requires the following python modules:
```
libscrc
requests
```

# Configuration
Edit the config.cfg and enter the following data:
```
[general]
log_path=                       # path to log file (without file name), if empty, the current folder is used
log_level=ERROR                 # possible log levels: 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'
                                # there are no 'CRITICAL' errors defined -> 'CRITICAL' will result in an empty log file
[SofarInverter]
inverter_ip=X.X.X.X             # data logger IP address
inverter_port=8899              # data logger port
inverter_sn=XXXXXXXXXX          # data logger serial number

[pvoutput]
pvo_system_size=X.X             # system size in kW used for validity checks of the produced power / energy, can be left empty 
pvo_apikey=XXXXXXXXXX           # API key from pvoutput.org
pvo_systemid=XXXX               # ID of the system to upload to
pvo_upload_temperature=true     # if true, upload inverter temperature 
pvo_upload_voltage=true         # if true, upload line voltage
pvo_v7=PVOutput.Power_PV1       # optional parameter: [parameter range].[parameter name]
pvo_v8=PVOutput.Power_PV2       # optional parameter: [parameter range].[parameter name]
pvo_v9=PVOutput.Voltage_PV1     # optional parameter: [parameter range].[parameter name]
pvo_v10=PVOutput.Voltage_PV2    # optional parameter: [parameter range].[parameter name]
pvo_v11=SystemInfo.Temperature_Env1         # optional parameter: [parameter range].[parameter name]
pvo_v12=SystemInfo.Temperature_HeatSink1    # optional parameter: [parameter range].[parameter name]
pvo_single_url=https://pvoutput.org/service/r2/addstatus.jsp?key=       # do NOT edit
```

# Run
```
python3 sofar2PVO.py  or ./sofar2PVO.py
```
There is no output, unless an error occurs. Errors may be also written to the log file.

# Contribution
You're welcome to send me errors or ideas for improvement.
Please fork your own project if you want to rewrite or/add change something yourself.