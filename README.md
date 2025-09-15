# SunPower-PSV6-Supervisor-Supervisor
Raspberry Pi + python script to exfiltrate Photovoltaic solar data from unsupported hardware, without paying fees.

## Approach
This

## Background
For reference, this project was made for a SunPower PV system installed in 2019.  Residential house in the northeast with a roof mounted system.  2 circuits, each with 6 Sunpower (actually Maxeon) PV panels, with an attached Enphase microinverter. 


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
