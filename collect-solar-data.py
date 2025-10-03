#!/usr/bin/env python3
"""
Solar Data Collection Script (runs every 15 minutes)
Fetches data from PVS6 and saves locally to JSON and CSV files
"""

import json
import requests
import sys
import base64
import csv
from pathlib import Path
from datetime import datetime

# Import config
try:
    from config import PVS6_IP, PVS6_SERIAL_LAST5
except ImportError:
    print("Error: config.py not found. Copy config.py.example to config.py and add your values.")
    sys.exit(1)

# Configuration
OUTPUT_DIR = Path('PVS6_output')
OVERVIEW_CSV = OUTPUT_DIR / 'PVS6_output_overview.csv'
INVERTERS_CSV = OUTPUT_DIR / 'PVS6_output_inverters.csv'

class SolarDataCollector:
    def __init__(self):
        # Ensure output directory exists
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / 'raw_JSON_output_files').mkdir(exist_ok=True)
    
    def fetch_pvs6_data(self):
        """Fetch data from PVS6 using VarServer API"""
        session = requests.Session()
        
        # Create basic auth header
        auth_string = f"ssm_owner:{PVS6_SERIAL_LAST5}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        base_url = f"https://{PVS6_IP}"
        headers = {"Authorization": f"Basic {auth_b64}"}
        
        try:
            # Step 1: Login
            login_response = session.get(
                f"{base_url}/auth?login",
                headers=headers,
                verify=False,
                timeout=10
            )
            login_response.raise_for_status()
            
            # Step 2: Get all data
            data_response = session.get(
                f"{base_url}/vars?match=/&fmt=obj",
                verify=False,
                timeout=10
            )
            data_response.raise_for_status()
            
            return data_response.json()
            
        except Exception as e:
            print(f"Error fetching PVS6 data: {e}")
            return None
        finally:
            session.close()
    
    def save_json_output(self, pvs6_data):
          # Ensure raw JSON subfolder exists
        json_dir = OUTPUT_DIR / 'raw_JSON_output_files'
        json_dir.mkdir(exist_ok=True)

        """Save raw JSON output to file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file = json_dir / f'PVS6_output_{timestamp}.json'

        try:
            with open(json_file, 'w') as f:
                json.dump(pvs6_data, f, indent=2)
            print(f"✓ Saved JSON to {json_file}")
        except Exception as e:
            print(f"❌ Error saving JSON: {e}")
    
    def parse_overview_data(self, pvs6_data):
        """Extract overview data from PVS6 response"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get livedata summary - both instantaneous and lifetime
        pv_en = float(pvs6_data.get('/sys/livedata/pv_en', 0))
        pv_p = float(pvs6_data.get('/sys/livedata/pv_p', 0))
        site_load_p = float(pvs6_data.get('/sys/livedata/site_load_p', 0))
        site_load_en = float(pvs6_data.get('/sys/livedata/site_load_en', 0))
        net_p = float(pvs6_data.get('/sys/livedata/net_p', 0))
        net_en = float(pvs6_data.get('/sys/livedata/net_en', 0))
        
        return {
            'timestamp': timestamp,
            'lifetime_pv_kwh': pv_en,
            'lifetime_site_load_kwh': site_load_en,
            'lifetime_net_kwh': net_en,
            'current_pv_kw': pv_p,
            'current_consumption_kw': site_load_p,
            'net_power_kw': net_p
        }
    
    def parse_inverter_data(self, pvs6_data):
        """Extract inverter data from PVS6 response"""
        inverters = []
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        inverter_index = 0
        while True:
            inverter_key = f'/sys/devices/inverter/{inverter_index}/sn'
            if inverter_key not in pvs6_data:
                break
            
            serial = pvs6_data.get(inverter_key, '')
            power = float(pvs6_data.get(f'/sys/devices/inverter/{inverter_index}/p3phsumKw', 0))
            energy = float(pvs6_data.get(f'/sys/devices/inverter/{inverter_index}/ltea3phsumKwh', 0))
            
            # Determine state based on power output
            if power > 0:
                state = 'working'
            else:
                state = 'idle'
            
            inverters.append({
                'timestamp': timestamp,
                'serial': serial,
                'state': state,
                'power_kw': power,
                'lifetime_kwh': energy
            })
            
            inverter_index += 1
        
        return inverters
    
    def write_overview_to_csv(self, data):
        """Write overview data to local CSV"""
        # Check if file exists to determine if we need headers
        file_exists = OVERVIEW_CSV.exists()
        
        try:
            with open(OVERVIEW_CSV, 'a', newline='') as f:
                writer = csv.writer(f)
                
                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        'Timestamp', 
                        'Lifetime PV Production (kWh)',
                        'Lifetime Site Consumption (kWh)',
                        'Lifetime Net (kWh)',
                        'Current PV Production (kW)', 
                        'Current Consumption (kW)', 
                        'Current Net Power (kW)'
                    ])
                
                # Write data row
                writer.writerow([
                    data['timestamp'],
                    data['lifetime_pv_kwh'],
                    data['lifetime_site_load_kwh'],
                    data['lifetime_net_kwh'],
                    data['current_pv_kw'],
                    data['current_consumption_kw'],
                    data['net_power_kw']
                ])
            
            print(f"✓ Appended overview to {OVERVIEW_CSV}")
            
        except Exception as e:
            print(f"❌ Error writing overview CSV: {e}")
    
    def write_inverters_to_csv(self, data):
        """Write inverter data to local CSV"""
        # Check if file exists to determine if we need headers
        
        file_exists = INVERTERS_CSV.exists()
        
        try:
            with open(INVERTERS_CSV, 'a', newline='') as f:
                writer = csv.writer(f)
                
                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        'Timestamp', 
                        'Serial Number', 
                        'State', 
                        'Current PV Production  (kW)', 
                        'Lifetime PV Production (kWh)'
                    ])
                
                # Write data rows
                for inverter in data:
                    writer.writerow([
                        inverter['timestamp'],
                        inverter['serial'],
                        inverter['state'],
                        inverter['power_kw'],
                        inverter['lifetime_kwh']
                    ])
            
            print(f"✓ Appended {len(data)} inverter rows to {INVERTERS_CSV}")
            
        except Exception as e:
            print(f"❌ Error writing inverters CSV: {e}")
    
    def run_test(self):
        """Run a test using sample data file"""
        print("Solar Data Collector - Test Mode")
        print("="*40)
        
        # Load sample data
        print("Loading sample data file...")
        sample_file = Path('example_data/PVS6_varserver_output_20250930_115822.json')
        
        if not sample_file.exists():
            print(f"❌ Sample file not found: {sample_file}")
            print("Attempting to fetch real PVS6 data...")
            pvs6_data = self.fetch_pvs6_data()
        else:
            with open(sample_file, 'r') as f:
                pvs6_data = json.load(f)
            print(f"✓ Loaded sample data from {sample_file}")
        
        if pvs6_data:
            # Save JSON output
            print("\nSaving JSON output...")
            self.save_json_output(pvs6_data)
            
            # Parse and write overview data
            print("\nProcessing overview data...")
            overview_data = self.parse_overview_data(pvs6_data)
            print(f"Overview: {overview_data['current_pv_kw']:.3f} kW production")
            print(f"Lifetime: PV={overview_data['lifetime_pv_kwh']:.1f} kWh, Load={overview_data['lifetime_site_load_kwh']:.1f} kWh, Net={overview_data['lifetime_net_kwh']:.1f} kWh")
            self.write_overview_to_csv(overview_data)
            
            # Parse and write inverter data
            print("\nProcessing inverter data...")
            inverter_data = self.parse_inverter_data(pvs6_data)
            print(f"Found {len(inverter_data)} inverters")
            self.write_inverters_to_csv(inverter_data)
            
            print("\n✓ Test completed!")
        else:
            print("❌ Could not load or fetch PVS6 data")
    
    def run(self):
        """Run normal data collection"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Solar Data Collector - {timestamp}")
        
        # Fetch PVS6 data
        pvs6_data = self.fetch_pvs6_data()
        
        if pvs6_data:
            # Save JSON output
            self.save_json_output(pvs6_data)
            
            # Parse and write to CSV files
            overview_data = self.parse_overview_data(pvs6_data)
            self.write_overview_to_csv(overview_data)
            
            inverter_data = self.parse_inverter_data(pvs6_data)
            self.write_inverters_to_csv(inverter_data)
            
            print(f"✓ Collection completed - {len(inverter_data)} inverters, {overview_data['current_pv_kw']:.3f} kW")
        else:
            print("❌ Could not fetch PVS6 data")

if __name__ == '__main__':
    # Disable SSL warnings for self-signed cert
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    collector = SolarDataCollector()
    
    # Check if running in test mode
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        collector.run_test()
    else:
        collector.run()