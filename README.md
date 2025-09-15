# SunPower-PSV6-Supervisor-Supervisor
Raspberry Pi + python script to exfiltrate Photovoltaic solar data from unsupported hardware, without paying fees.

## Approach
The basic approach, demonstrated by other projects, is that the PVS6 has a small computer inside running a web server.  If you plug a laptop or other deivce into the internal ethernet device, and go to a 'web page' at http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList, it will output the current state of the system, but no history or alerting. A Raspberry Pi inserted in the PVS6 case periodically calls a python script to run the code in this github project

### Script Actions

1 Query the PVS6 web interface
1 Save the output as a JSON file with filename of current timestamp 
1 Parses the response to extract key metrics
1 Load a local weather API to get how cloudy it is
1 Save curated data to a local CSV file
1 Submits data to Google sheet via API
1 Check for anomalies and sends alerts

Reasoning - This is fairly nerdy and we want to 
a Get the data off the device
a make it easily available to review trends, e.g. a spreadsheet
a send me alerts if something goes wrong.

## Background
For reference, this project was made for a SunPower PV system installed in 2019.  Residential house in the northeast with a roof mounted system.  2 circuits, each with 6 Sunpower (actually Maxeon) PV panels, with an attached Enphase microinverter. 

Sadly, I had a microinverter go bad but did not learn about it untill I dug in - monitoring is really up to the user!


### PVS6 PhotoVoltaic Supervisor version 6

The Sunpower PVS6 PhotoVoltaic Supervisor 6 is monitoring unit, typically installed near the near electrical panel.  It just measures, does not control the microinverters.  Your solar panels will generate power and offset your consumption regardless of whether the PVS6 is online. 

[User Manual](https://usermanual.wiki/SunPower/539848-Z.Users-Manual-rev-6022522.pdf)

Note there are several ways for solar systems to work, mine has a microinverter on each solar panel, but other systems have one big inverter or even a battery.  **Please keep in mind this software is only tested on a basic microinverter system.**  

PVS6 were manufactured and sold in the US by SunPower, which unfotunately went out of business.  SunStrong has resusitated the server and has an app with a monthly subscription.  It works well, but has limited information and no alerting.  

### How does it work?
It is suprisingly simple! The PVS6 'listens' to certain circuits the Solar Panels & Microinverters are on.  The microinverters send a message on the AC electical wiring, called "Power Line Communication". 
PVS6 has white and black, white and red braided cables. These are consumption Current Transformers how it measures (estimates but accurate. )   Solar ones are a lot more accurate, and get the data from micro inverters as a fall back. 

## References
I am indebted to other projects that inspired and informed this project.  I hope I can pay it back to help others

- [Gruby](https://blog.gruby.com/2020/04/28/monitoring-a-sunpower-solar-system/)
- [ginoledesma/sunpower-pvs-exporter](https://github.com/ginoledesma/sunpower-pvs-exporter/blob/master/sunpower_pvs_notes.md)
- [Starreveld](https://starreveld.com/PVS6%20Access%20and%20API.pdf)


## Gotchas
- The inverter(s) send a message approximately every 15 seconds when the microinverter is up and running -- which means when there's sunlight. The microinverters may report an error when there's heavy shading or at night.
