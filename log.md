# Project Log, in reverse chronological order

## 15 Sept 2025
Raspberry Pi 4B
32 GB SD card
Raspberry Pi OS Lite 64

Updates
- `sudo apt update && sudo apt upgrade -y`
- `sudo apt install python3-pip python3-venv -y`
- `mkdir solar-supervisor-supervisor`
- `cd ~/solar-supervisor-supervisor`

Using my free Gmail account, in [Google Cloud Console](https://console.cloud.google.com)
- created project "SunPower-PVS6-Supervisor"
- Enable Google Sheets API
- Create credentials (Service Account) 
- Download the JSON key file
- created `google-api-credentials.json` file in ~/solar-supervisor-supervisor
