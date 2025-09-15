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

## Gotchas
- The inverter(s) send a message approximately every 15 seconds when the microinverter is up and running -- which means when there's sunlight. The microinverters may report an error when there's heavy shading or at night.
- The PVS6 remembers each microinverter for a while (?) if it is not connected, it will report 'error', not disconnected

## References
I am indebted to other projects that inspired and informed this project.  I hope I can pay it back to help others

- [Gruby](https://blog.gruby.com/2020/04/28/monitoring-a-sunpower-solar-system/)
- [ginoledesma/sunpower-pvs-exporter](https://github.com/ginoledesma/sunpower-pvs-exporter/blob/master/sunpower_pvs_notes.md)
- [Starreveld](https://starreveld.com/PVS6%20Access%20and%20API.pdf)

also
- [https://github.com/krbaker/hass-sunpower](https://github.com/krbaker/hass-sunpower)
- [https://github.com/jrconlin/sunpower_hass/tree/main/direct](https://github.com/jrconlin/sunpower_hass/tree/main/direct)


### Your friend, the PVS6 PhotoVoltaic Supervisor version 6

The Sunpower PVS6 PhotoVoltaic Supervisor 6 is monitoring unit, typically installed near the near electrical panel.  It just measures, does not control the microinverters.  Your solar panels will generate power and offset your consumption regardless of whether the PVS6 is online. 

[User Manual](https://usermanual.wiki/SunPower/539848-Z.Users-Manual-rev-6022522.pdf)

Note there are several ways for solar systems to work, mine has a microinverter on each solar panel, but other systems have one big inverter or even a battery.  **Please keep in mind this software is only tested on a basic microinverter system.**  

PVS6 were manufactured and sold in the US by SunPower, which unfotunately went out of business.  SunStrong has resuscitated the server and has an app with a monthly subscription.  It works well, but has limited information and no alerting.  If you ask, they will enable panel level monitoring, which can show if one panel is not working.  

### How does it work?
It is suprisingly simple! The PVS6 'listens' to certain circuits the Solar Panels & Microinverters are on.  The microinverters send a message on the AC electical wiring, called "Power Line Communication". 
PVS6 has white/black, white/red braided cables. These go to Current Transformers which measures electical consumption on your circuit breaker (estimates but accurate).   Solar production Current Transformers are more accurate, and get the data from micro inverters as a fall back. NO wireless communication from micro inverters to PVS6. The PVS6 does not talk to your electrical grid, so these are all estimates, but said to be faily accurrate. 


### Understanding the data output

The PVS6, when queried, returns JSON formatted data, like this actual reading. Serial numbers are somewhat obscured, with only 1 of the 12 panels shown for brevity.

<pre>
{
	"devices":	[{
			"DETAIL":	"detail",
			"STATE":	"working",
			"STATEDESCR":	"Working",
			"SERIAL":	"ZT1PVS6M12345678",
			"MODEL":	"PV Supervisor PVS6",
			"HWVER":	"6.02",
			"SWVER":	"2025.06, Build 61839",
			"DEVICE_TYPE":	"PVS",
			"DATATIME":	"2025,09,12,21,11,12",
			"dl_err_count":	"0",
			"dl_comm_err":	"0",
			"dl_skipped_scans":	"0",
			"dl_scan_time":	"0",
			"dl_untransmitted":	"0",
			"dl_uptime":	"37",
			"dl_cpu_load":	"0.91",
			"dl_mem_used":	"49692",
			"dl_flash_avail":	"59039",
			"panid":	123456789,
			"CURTIME":	"2025,09,12,21,21,15"
		}, {
			"ISDETAIL":	true,
			"SERIAL":	"PVS6M12345678p",
			"TYPE":	"PVS5-METER-P",
			"STATE":	"working",
			"STATEDESCR":	"Working",
			"MODEL":	"PVS6M0400p",
			"DESCR":	"Power Meter PVS6M12345678p",
			"DEVICE_TYPE":	"Power Meter",
			"interface":	"mime",
			"production_subtype_enum":	"GROSS_PRODUCTION_SITE",
			"subtype":	"GROSS_PRODUCTION_SITE",
			"SWVER":	"3000",
			"PORT":	"",
			"DATATIME":	"2025,09,12,21,21,15",
			"ct_scl_fctr":	"50",
			"net_ltea_3phsum_kwh":	"27692.41",
			"p_3phsum_kw":	"0.2948",
			"q_3phsum_kvar":	"0.1939",
			"s_3phsum_kva":	"0.3586",
			"tot_pf_rto":	"0.7696",
			"freq_hz":	"60",
			"i_a":	"1.7114",
			"v12_v":	"209.5409",
			"CAL0":	"50",
			"origin":	"data_logger",
			"OPERATION":	"noop",
			"CURTIME":	"2025,09,12,21,21,15"
		}, {
			"ISDETAIL":	true,
			"SERIAL":	"PVS6M12345678c",
			"TYPE":	"PVS5-METER-C",
			"STATE":	"working",
			"STATEDESCR":	"Working",
			"MODEL":	"PVS6M0400c",
			"DESCR":	"Power Meter PVS6M12345678c",
			"DEVICE_TYPE":	"Power Meter",
			"interface":	"mime",
			"consumption_subtype_enum":	"NET_CONSUMPTION_LOADSIDE",
			"subtype":	"NET_CONSUMPTION_LOADSIDE",
			"SWVER":	"3000",
			"PORT":	"",
			"DATATIME":	"2025,09,12,21,21,15",
			"ct_scl_fctr":	"100",
			"net_ltea_3phsum_kwh":	"13906.91",
			"p_3phsum_kw":	"-0.1187",
			"q_3phsum_kvar":	"-0.5931",
			"s_3phsum_kva":	"0.7018",
			"tot_pf_rto":	"-0.1376",
			"freq_hz":	"60",
			"i1_a":	"2.5116",
			"i2_a":	"3.315",
			"v1n_v":	"122.3436",
			"v2n_v":	"119.0097",
			"v12_v":	"209.5409",
			"p1_kw":	"-0.189",
			"p2_kw":	"0.0703",
			"neg_ltea_3phsum_kwh":	"19044.29",
			"pos_ltea_3phsum_kwh":	"32951.2099",
			"CAL0":	"100",
			"origin":	"data_logger",
			"OPERATION":	"noop",
			"CURTIME":	"2025,09,12,21,21,16"
		}, {
			"ISDETAIL":	true,
			"SERIAL":	"E00123456789",
			"TYPE":	"SOLARBRIDGE",
			"STATE":	"error",
			"STATEDESCR":	"Error",
			"MODEL":	"AC_Module_Type_E",
			"DESCR":	"Inverter E00123456789",
			"DEVICE_TYPE":	"Inverter",
			"hw_version":	"4405",
			"interface":	"mime",
			"SWVER":	"4.40.1",
			"PORT":	"",
			"MOD_SN":	"",
			"NMPLT_SKU":	"",
			"DATATIME":	"2025,09,12,21,12,42",
			"ltea_3phsum_kwh":	"2696.2471",
			"p_3phsum_kw":	"0",
			"vln_3phavg_v":	"209.05",
			"i_3phsum_a":	"0",
			"p_mppt1_kw":	"0.0012",
			"v_mppt1_v":	"62.14",
			"i_mppt1_a":	"0.02",
			"t_htsnk_degc":	"37",
			"freq_hz":	"0",
			"stat_ind":	"0",
			"origin":	"data_logger",
			"OPERATION":	"noop",
			"CURTIME":	"2025,09,12,21,21,16"
		}],
	"result":	"succeed"
}
</pre>



## Detailed Script Description

- `crontab -e` -edit crontab on raspberry pi
- `*/15 6-21 * * * /home/pi/solar-monitor/venv/bin/python /home/pi/solar-monitor/solar_monitor.py >> /home/pi/solar-monitor/logs/solar.log 2>&1` Run every 15 minutes from 6 AM to 9 PM
