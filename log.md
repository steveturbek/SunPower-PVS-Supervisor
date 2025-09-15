# Project Log, in reverse chronological order

## 15 Sept 2025
Raspberry Pi 4B
32 GB SD card
Raspberry Pi OS Lite 64

Updates
- `sudo apt update && sudo apt upgrade -y`
- `sudo apt install python3-pip -y`
- `mkdir solar-supervisor-supervisor`
- `sudo apt install git`  install git to get this package
- `cd ~/solar-supervisor-supervisor`
- `python3 -m venv venv` create virtual environment, otherwise there are later errors
- `source venv/bin/activate` activate the virtual environment
- `pip install requests google-api-python-client google-auth-httplib2 google-auth-oauthlib` install google API
- `deactivate` turns off virtual enviroment 

Using my free Gmail account, in [Google Cloud Console](https://console.cloud.google.com)
- created project "SunPower-PVS6-Supervisor"
- Enable Google Sheets API
- Create credentials (Service Account NOT OATH) 
- Create and download the key file as JSON
- get the service account email, something you kind of created like `solar-monitor@skilful-frame-1234567-u7.iam.gserviceaccount.com`
- created `nano ~/google-api-credentials.json` paste in text from google API
- `chmod +r ~/google-api-credentials.json` made script readable
- `nano ~/google-sheet-spreadsheet-id.txt` get ID from google sheet you created, paste in here (e.g. https://docs.google.com/spreadsheets/d/SHEET_ID/edit)
- `chmod +r ~/google-sheet-spreadsheet-id.txt` made script readable

Pulling file fom this GitHub repo
- `git clone https://github.com/steveturbek/SunPower-PVS6-Supervisor-Supervisor`
- `git pull origin main` to update
- **`python SunPower-PVS6-Supervisor-Supervisor.py` run program**

