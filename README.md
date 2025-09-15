# SunPower PSV6 Supervisor Supervisor
Make a Raspberry Pi + python script to exfiltrate Photovoltaic solar data from unsupported hardware, without paying fees.

## Approach
The basic approach, demonstrated by other projects, is that the PVS6 has a small computer inside running a web server.  If you plug a laptop or other deivce into the internal ethernet port, and go to a 'web page' made for technicians, it will output the current state of the system, but no history or alerting. A Raspberry Pi inserted in the PVS6 case periodically calls a python script to run the code in this github project to catch the status and save for the future.

We want to:
1. Get the data off the PVS6, for future reference 
1. Make it available to review trends by non programmers, e.g. a spreadsheet
1. Send me alerts if something goes wrong.

BUT we don't want a dashboard that I have to look at it!  

## Background
For reference, this project was made for a SunPower PV system installed in 2019.  Residential house in the northeast USA with a roof mounted system.  2 circuits, each with 6 Sunpower (actually Maxeon) PV panels & attached Enphase microinverters. 

Sadly, I had a microinverter go bad but did not learn about it untill **years later** when another 5 died.  I only noticed that when our electric bill going up and went' down the rabbit hole'.  Monitoring should NOT be left up to the user!  Solar has to be come more friendly or it will not catch on in america.  This project is hopefully is a small contribution to that.


## Script Actions
In this script, running on the Raspberry Pi

1. Query the PVS6 web interface
1. Save the output as a JSON file with filename of current timestamp
2.   in SSH you can manually pull the data to a file `curl http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList -o "$HOME/PVS6outputJSON/$(date +%Y%m%d_%H%M%S).json"`
1. Parses the JSON to extract key metrics
1. Load a weather API to get how cloudy it is locally
1. Save Parsed data to a local CSV file
1. Submit data to add row to Google sheet via API
1. Check for anomalies and send alerts
1. Monthly summary by email 


### Your friend, the PVS6 PhotoVoltaic Supervisor version 6

The Sunpower PVS6 PhotoVoltaic Supervisor 6 is monitoring unit, typically installed near the near electrical panel.  It just measures, does not control the microinverters.  Your solar panels will generate power and offset your consumption regardless of whether the PVS6 is online. 

[User Manual](https://usermanual.wiki/SunPower/539848-Z.Users-Manual-rev-6022522.pdf)

Note there are several ways for solar systems to work, mine has a microinverter on each solar panel, but other systems have one big inverter or even a battery.  **Please keep in mind this software is only tested on a basic microinverter system.**  

PVS6 were manufactured and sold in the US by SunPower, which unfotunately went out of business.  SunStrong has resusitated the server and has an app with a monthly subscription.  It works well, but has limited information and no alerting.  

### How does it work?
It is suprisingly simple! The PVS6 'listens' to certain circuits the Solar Panels & Microinverters are on.  The microinverters send a message on the AC electical wiring, called "Power Line Communication". 
PVS6 has white and black, white and red braided cables. These are consumption Current Transformers how it measures (estimates but accurate. )   Solar ones are a lot more accurate, and get the data from micro inverters as a fall back. NO wireless communication from micro inverters to PVS6.


## References
I am indebted to other projects that inspired and informed this project.  I hope I can pay it back to help others

- [Gruby](https://blog.gruby.com/2020/04/28/monitoring-a-sunpower-solar-system/)
- [ginoledesma/sunpower-pvs-exporter](https://github.com/ginoledesma/sunpower-pvs-exporter/blob/master/sunpower_pvs_notes.md)
- [Starreveld](https://starreveld.com/PVS6%20Access%20and%20API.pdf)

also
- [https://github.com/krbaker/hass-sunpower](https://github.com/krbaker/hass-sunpower)
- [https://github.com/jrconlin/sunpower_hass/tree/main/direct]{(https://github.com/jrconlin/sunpower_hass/tree/main/direct)

## Gotchas
- The inverter(s) send a message approximately every 15 seconds when the microinverter is up and running -- which means when there's sunlight. The microinverters may report an error when there's heavy shading or at night.
- The PVS6 remembers each microinverter for a while (?) if it is not connected, it will report 'error', not disconnected
