import json
import requests
from pathlib import Path
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
PVS6_URL = 'http://172.27.153.1/cgi-bin/dl_cgi?Command=DeviceList'
CREDENTIALS_FILE = Path.home() / 'google-api-credentials.json'
SPREADSHEET_ID_FILE = Path.home() / 'google-sheet-spreadsheet-id.txt'
SPREADSHEET_ID = SPREADSHEET_ID_FILE.read_text().strip()
SHEET_NAME = 'SolarDataDaily'

class SolarMonitor:
    def __init__(self):
        # Setup Google Sheets
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        self.service = build('sheets', 'v4', credentials=creds)
        self.sheet = self.service.spreadsheets()
    
    def fetch_pvs6_data(self):
        """Fetch data from PVS6"""
        try:
            response = requests.get(PVS6_URL, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error fetching PVS6 data: {e}")
            return None
    
    def parse_inverter_data(self, pvs6_data):
        """Extract inverter data from PVS6 response"""
        inverters = []
        
        for device in pvs6_data.get('devices', []):
            if device.get('DEVICE_TYPE') == 'Inverter':
                inverters.append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'serial': device.get('SERIAL', ''),
                    'state': device.get('STATE', ''),
                    'power_kw': float(device.get('p_3phsum_kw', 0)),
                    'energy_kwh': float(device.get('ltea_3phsum_kwh', 0)),
                    'voltage': float(device.get('v_mppt1_v', 0)),
                    'current': float(device.get('i_mppt1_a', 0)),
                    'temp_c': int(device.get('t_htsnk_degc', 0)),
                    'frequency': float(device.get('freq_hz', 0))
                })
        
        return inverters
    
    def write_to_sheets(self, data):
        """Write inverter data to Google Sheets"""
        # Prepare rows for sheets
        rows = []
        for inverter in data:
            rows.append([
                inverter['timestamp'],
                inverter['serial'],
                inverter['state'],
                inverter['power_kw'],
                inverter['energy_kwh'],
                inverter['voltage'],
                inverter['current'],
                inverter['temp_c'],
                inverter['frequency']
            ])
        
        if not rows:
            print("No data to write")
            return
        
        try:
            # Append data to sheet
            result = self.sheet.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f'{SHEET_NAME}!A:I',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': rows}
            ).execute()
            
            print(f"✅ Written {len(rows)} rows to Google Sheets")
            print(f"Updated range: {result.get('updates', {}).get('updatedRange')}")
            
        except Exception as e:
            print(f"❌ Error writing to sheets: {e}")
    
    def setup_sheet_headers(self):
        """Create headers if sheet is empty"""
        headers = [[
            'Timestamp', 'Serial Number', 'State', 'Power (kW)', 
            'Total Energy (kWh)', 'Voltage (V)', 'Current (A)', 
            'Temperature (°C)', 'Frequency (Hz)'
        ]]
        
        try:
            # Check if headers exist
            result = self.sheet.values().get(
                spreadsheetId=SPREADSHEET_ID,
                range=f'{SHEET_NAME}!A1:I1'
            ).execute()
            
            if not result.get('values'):
                # Write headers
                self.sheet.values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f'{SHEET_NAME}!A1:I1',
                    valueInputOption='RAW',
                    body={'values': headers}
                ).execute()
                print("✅ Headers created")
                
                # Format headers
                self.format_headers()
                
        except Exception as e:
            print(f"Error setting up headers: {e}")
    
    def format_headers(self):
        """Apply formatting to header row"""
        requests = [{
            'repeatCell': {
                'range': {
                    'sheetId': 0,  # Adjust if using different sheet
                    'startRowIndex': 0,
                    'endRowIndex': 1
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.1, 'green': 0.3, 'blue': 0.5},
                        'textFormat': {
                            'foregroundColor': {'red': 1, 'green': 1, 'blue': 1},
                            'bold': True
                        }
                    }
                },
                'fields': 'userEnteredFormat'
            }
        }]
        
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={'requests': requests}
        ).execute()
    
    def run_test(self):
        """Run a complete test"""
        print("Solar Monitor - Google Sheets Test")
        print("="*40)
        
        # Setup headers
        print("1. Setting up sheet headers...")
        self.setup_sheet_headers()
        
        # Test with sample data (if PVS6 not accessible)
        print("\n2. Testing with sample data...")
        sample_data = [
            {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'serial': 'E00121948024216',
                'state': 'working',
                'power_kw': 0.265,
                'energy_kwh': 2671.548,
                'voltage': 53.62,
                'current': 5.17,
                'temp_c': 47,
                'frequency': 60.01
            }
        ]
        self.write_to_sheets(sample_data)
        
        # Try real PVS6 data
        print("\n3. Attempting to fetch real PVS6 data...")
        pvs6_data = self.fetch_pvs6_data()
        if pvs6_data:
            inverter_data = self.parse_inverter_data(pvs6_data)
            if inverter_data:
                print(f"Found {len(inverter_data)} inverters")
                self.write_to_sheets(inverter_data)
            else:
                print("No inverter data found in PVS6 response")
        else:
            print("Could not connect to PVS6")
        
        print("\n✅ Test completed!")

if __name__ == '__main__':
    monitor = SolarMonitor()
    monitor.run_test()
