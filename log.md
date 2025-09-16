# Project Log, in reverse chronological order

## 15 Sept 2025
Raspberry Pi 4B
32 GB SD card
Raspberry Pi OS Lite 64
account created with password & login, wifi set up to local wifi network, SSH turned on

Updates
- `sudo apt update && sudo apt upgrade -y`
- `sudo apt install python3-pip -y`
- `sudo apt install git`  install git to get this package
- `cd ~/solar-supervisor-supervisor`
- `python3 -m venv venv` create virtual environment, otherwise there are later errors
- `source venv/bin/activate` activate the virtual environment
- `pip install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib` install google API
- `deactivate` turns off virtual enviroment
- `sudo nano /etc/dhcpcd.conf` edit / create this file to prevent the Pi from using ethernet to PVS6 as gateway
- Add these 2 lines at the end of the file:
`interface eth0`
`nogateway`
- (Not covered here, but for reference) other guides show how to access the PVS6 web interface on your intranet, for example to connect the solar to [Home Assistant](https://community.home-assistant.io/t/options-for-sunpower-solar-integration/289621) Outside the scope of this project.
- `sudo shutdown -r now`
- **Safely!** install rasberry Pi in PVS6 case, with ethernet to 'LAN1' (black) port and USB to left-most USB port


Using my free Gmail account, in [Google Cloud Console](https://console.cloud.google.com)
- created project "SunPower-PVS6-Supervisor"
- Enable Google Sheets API
- Create credentials (Service Account NOT OATH) 
- Create and download the key file as JSON
- get the service account email you created, something like `solar-monitor@skilful-frame-1234567-u7.iam.gserviceaccount.com`
- created `nano ~/google-api-credentials.json` paste in text from google API
- `chmod +r ~/google-api-credentials.json` made script readable
- `nano ~/google-sheet-spreadsheet-id.txt` get ID from google sheet you created, paste in here (e.g. https://docs.google.com/spreadsheets/d/SHEET_ID/edit)
- `chmod +r ~/google-sheet-spreadsheet-id.txt` made script readable

Pulling file fom this GitHub repo
- `git clone https://github.com/steveturbek/SunPower-PVS6-Supervisor-Supervisor`
- `git pull origin main` to update

To run script,
- SSH into Raspberry Pi with account, `ssh sunpoweradmin@123.123.0.123` (get IP address from router if need be)
- `cd ~/solar-supervisor-supervisor`
- `python3 -m venv venv` create virtual environment, otherwise there are later errors
- `source venv/bin/activate` activate the virtual environment
-  **`python ~/SunPower-PVS6-Supervisor-Supervisor/SunPower-PVS6-Supervisor-Supervisor.py` run program!**
- `deactivate` turns off virtual enviroment
